from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import stock_f10
from app.services.free_sources.margin_trading_public import (
    MarginTradingQualityError,
    MarginTradingSyncResult,
    merge_margin_trading,
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
    app.include_router(stock_f10.router)
    return TestClient(app), catalog


def _seed(tmp_path: Path) -> None:
    merge_margin_trading(
        tmp_path,
        pl.DataFrame(
            {
                "symbol": ["600519.SH"],
                "name": ["贵州茅台"],
                "market": ["沪市"],
                "trade_date": [date(2026, 8, 4)],
                "financing_balance": [100.0],
                "financing_buy_amount": [30.0],
                "financing_repayment_amount": [20.0],
                "financing_net_buy_amount": [10.0],
                "securities_lending_balance": [5.0],
                "securities_lending_sell_volume": [2],
                "securities_lending_repayment_volume": [1],
                "securities_lending_balance_volume": [8],
                "margin_balance": [105.0],
                "source": ["eastmoney_rzrq"],
                "unit_version": ["stock_margin_trading_v1"],
            }
        ),
    )


def test_margin_trading_query_reads_only_local_rows(tmp_path: Path) -> None:
    _seed(tmp_path)
    client, _ = _client(tmp_path)

    response = client.get("/api/f10/margin-trading?symbol=600519.SH&limit=20")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["source"] == "local"
    assert body["data"][0]["trade_date"] == "2026-08-04"
    assert body["data"][0]["margin_balance"] == 105.0


def test_margin_trading_sync_refreshes_catalog_after_publish(tmp_path: Path, monkeypatch) -> None:
    client, catalog = _client(tmp_path)
    result = MarginTradingSyncResult(
        symbols_requested=1,
        symbols_with_data=1,
        empty_symbols=(),
        rows_fetched=50,
        rows_published=50,
        latest_trade_date="2026-08-04",
        artifact_path="f10/stock_margin_trading/part.parquet",
        lineage_path="lineage/stock_margin_trading/date=2026-08-04/run.json",
    )
    monkeypatch.setattr(stock_f10, "sync_margin_trading", lambda *args, **kwargs: result)

    response = client.post(
        "/api/f10/margin-trading/sync",
        json={"symbols": ["600519.SH"], "rows_per_symbol": 50},
    )

    assert response.status_code == 200
    assert response.json()["rows_published"] == 50
    assert response.json()["catalog_refreshed"] is True
    assert catalog.refreshed == ["stock_margin_trading"]


def test_margin_trading_sync_exposes_bounded_upstream_error(tmp_path: Path, monkeypatch) -> None:
    client, catalog = _client(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("upstream body must not leak")

    monkeypatch.setattr(stock_f10, "sync_margin_trading", fail)
    response = client.post(
        "/api/f10/margin-trading/sync",
        json={"symbols": ["600519.SH"], "rows_per_symbol": 50},
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "code": "margin_trading_upstream_failed",
            "message": "融资融券数据源暂时不可用",
        }
    }
    assert catalog.refreshed == []


def test_margin_trading_sync_maps_source_quality_failure_to_bounded_502(
    tmp_path: Path, monkeypatch
) -> None:
    client, catalog = _client(tmp_path)

    def fail(*args, **kwargs):
        raise MarginTradingQualityError("raw upstream row must not leak")

    monkeypatch.setattr(stock_f10, "sync_margin_trading", fail)
    response = client.post(
        "/api/f10/margin-trading/sync",
        json={"symbols": ["600519.SH"], "rows_per_symbol": 50},
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "code": "margin_trading_upstream_failed",
            "message": "融资融券数据源返回了不完整数据",
        }
    }
    assert catalog.refreshed == []
