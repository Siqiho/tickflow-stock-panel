from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import market_pulse
from app.services.free_sources.market_pulse_public import (
    MarketPulseSyncResult,
    normalize_market_pulse,
    publish_market_pulse,
)


class CatalogStub:
    def __init__(self) -> None:
        self.refreshed: list[str] = []

    def refresh_after_mutation(self, dataset_id: str):
        self.refreshed.append(dataset_id)


def _client(tmp_path: Path) -> tuple[TestClient, CatalogStub]:
    app = FastAPI()
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    catalog = CatalogStub()
    app.state.catalog_service = catalog
    app.include_router(market_pulse.router)
    return TestClient(app), catalog


def _seed(tmp_path: Path, trade_date: date) -> None:
    frame = normalize_market_pulse(
        [
            {
                "date": int(trade_date.strftime("%Y%m%d")),
                "minute": 930,
                "last_px": 3943.816,
                "change": 0.001,
                "preclose_px": 3939.966,
                "open_px": 3939.966,
                "business_amount": 494_465_500,
                "business_balance": 11_238_430_879,
            }
        ],
        [
            {
                "symbol_code": "cls80427",
                "symbol_name": "影视",
                "article_id": 2449591,
                "c_time": f"{trade_date.isoformat()} 09:28:51",
                "float": "up",
            }
        ],
        trade_date,
    )
    publish_market_pulse(tmp_path, trade_date, frame)


def test_market_pulse_query_reads_only_local_partition(tmp_path: Path) -> None:
    trade_date = date.today()
    _seed(tmp_path, trade_date)
    client, _ = _client(tmp_path)

    response = client.get(f"/api/market-pulse?trade_date={trade_date.isoformat()}")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["source"] == "local"
    assert body["producer"] == "cls"
    assert body["minute_rows"] == 1
    assert body["event_rows"] == 1
    assert body["points"][0]["event_time"].endswith("09:30:00")


def test_market_pulse_sync_refreshes_catalog_after_publish(tmp_path: Path, monkeypatch) -> None:
    trade_date = date.today()
    client, catalog = _client(tmp_path)
    result = MarketPulseSyncResult(
        requested_date=trade_date.isoformat(),
        resolved_date=trade_date.isoformat(),
        minute_rows=241,
        event_rows=22,
        rows_published=263,
        artifact_path=f"market/pulse/date={trade_date.isoformat()}/part.parquet",
        lineage_path=f"lineage/market_pulse/date={trade_date.isoformat()}/run.json",
    )
    monkeypatch.setattr(market_pulse, "sync_market_pulse", lambda *args, **kwargs: result)

    response = client.post(
        "/api/market-pulse/sync",
        json={"trade_date": trade_date.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["rows_published"] == 263
    assert response.json()["catalog_refreshed"] is True
    assert catalog.refreshed == ["market_pulse"]


def test_market_pulse_sync_exposes_bounded_upstream_error(tmp_path: Path, monkeypatch) -> None:
    client, catalog = _client(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("upstream body must not leak")

    monkeypatch.setattr(market_pulse, "sync_market_pulse", fail)
    response = client.post("/api/market-pulse/sync", json={})

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "code": "market_pulse_upstream_failed",
            "message": "财联社市场脉搏暂时不可用",
        }
    }
    assert catalog.refreshed == []
