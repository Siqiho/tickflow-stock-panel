from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import hithink
from app.services.free_sources.hithink_finance import (
    DatasetPublishStats,
    HiThinkFinanceError,
    HiThinkSyncResult,
    normalize_limit_pool,
)
from app.services.free_sources.hithink_finance import _publish as publish_limit_pool


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
    app.include_router(hithink.router)
    return TestClient(app), catalog


def _seed_limit_pool(tmp_path: Path, trade_date: date) -> None:
    frame = normalize_limit_pool(
        "limit_up",
        [
            {
                "thscode": "600519.SH",
                "ticker": "600519",
                "name": "贵州茅台",
                "limit_up_reason": "业绩预增",
                "limit_up_time": "09:30:01",
            }
        ],
        trade_date,
        timestamp_ms=1,
    )
    publish_limit_pool(
        tmp_path,
        "hithink_limit_pool",
        "hithink_limit_pool_v1",
        Path("reference") / "hithink_limit_pool" / f"date={trade_date.isoformat()}" / "part.parquet",
        frame,
        trade_date,
        {"endpoints": ["https://fuyao.aicubes.cn/api/a-share/special-data/limit-up-pool"]},
    )


def test_hithink_query_reads_only_local_partition(tmp_path: Path, monkeypatch) -> None:
    trade_date = date(2026, 8, 25)
    _seed_limit_pool(tmp_path, trade_date)
    client, _ = _client(tmp_path)

    def fail(*args, **kwargs):
        raise AssertionError("GET must not call official API")

    monkeypatch.setattr(hithink, "sync_hithink_special_data", fail)
    response = client.get(f"/api/hithink/limit-pool?trade_date={trade_date.isoformat()}")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["source"] == "local"
    assert body["producer"] == "hithink_fuyao"
    assert body["row_count"] == 1
    assert body["rows"][0]["limit_up_reason"] == "业绩预增"


def test_hithink_sync_refreshes_catalog_after_publish(tmp_path: Path, monkeypatch) -> None:
    trade_date = date(2026, 8, 25)
    client, catalog = _client(tmp_path)
    result = HiThinkSyncResult(
        requested_date=trade_date.isoformat(),
        resolved_date=trade_date.isoformat(),
        rows_published=4,
        datasets=(
            DatasetPublishStats(
                dataset_id="hithink_limit_pool",
                rows_published=3,
                artifact_path=f"reference/hithink_limit_pool/date={trade_date.isoformat()}/part.parquet",
                lineage_path=f"lineage/hithink_limit_pool/date={trade_date.isoformat()}/run.json",
                extra={"limit_up_rows": 1, "limit_down_rows": 1, "limit_break_rows": 1},
            ),
            DatasetPublishStats(
                dataset_id="hithink_dragon_tiger",
                rows_published=1,
                artifact_path=f"reference/hithink_dragon_tiger/date={trade_date.isoformat()}/part.parquet",
                lineage_path=f"lineage/hithink_dragon_tiger/date={trade_date.isoformat()}/run.json",
                extra={"board_type": "all"},
            ),
        ),
    )
    monkeypatch.setattr(hithink, "sync_hithink_special_data", lambda *args, **kwargs: result)

    response = client.post("/api/hithink/sync", json={"trade_date": trade_date.isoformat(), "include": ["limit_pool", "dragon_tiger"]})

    assert response.status_code == 200
    body = response.json()
    assert body["rows_published"] == 4
    assert body["catalog_refreshed"] == ["hithink_limit_pool", "hithink_dragon_tiger"]
    assert catalog.refreshed == ["hithink_limit_pool", "hithink_dragon_tiger"]
    assert "test-key" not in str(body)
    assert "X-api-key" not in str(body)


def test_hithink_sync_exposes_bounded_upstream_error(tmp_path: Path, monkeypatch) -> None:
    client, catalog = _client(tmp_path)

    def fail(*args, **kwargs):
        raise HiThinkFinanceError("upstream body must not leak secret-key", code=5001, request_id="abc")

    monkeypatch.setattr(hithink, "sync_hithink_special_data", fail)
    response = client.post("/api/hithink/sync", json={})

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "code": "hithink_upstream_failed",
            "message": "同花顺官方特色数据暂时不可用",
        }
    }
    assert "secret-key" not in response.text
    assert catalog.refreshed == []
