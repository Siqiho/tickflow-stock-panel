from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import stock_f10
from app.services.free_sources.margin_trading_public import merge_margin_trading


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    app.include_router(stock_f10.router)
    return TestClient(app)


def _seed_local(tmp_path: Path) -> None:
    merge_margin_trading(
        tmp_path,
        pl.DataFrame(
            {
                "symbol": ["300502.SZ"],
                "name": ["新易盛"],
                "market": ["深市"],
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


def _write_offline(root: Path, symbol: str, rows: list[dict]) -> Path:
    dest = root / "2_base_sector" / "margin_trading" / f"{symbol}.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(dest)
    return dest


def test_local_default_stays_compatible(tmp_path: Path) -> None:
    _seed_local(tmp_path)
    response = _client(tmp_path).get("/api/f10/margin-trading?symbol=300502.SZ&limit=20")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "local"
    assert body["count"] == 1
    assert body["status"] == "ok"
    assert body["data"][0]["margin_balance"] == 105.0


def test_offline_quantdb_returns_mapped_rows_and_nulls(tmp_path: Path, monkeypatch) -> None:
    _write_offline(
        tmp_path,
        "000001.SZ",
        [
            {
                "time": date(2026, 8, 4),
                "Symbol": "000001.SZ",
                "finance_balance": 100.0,
                "slo_volume": 12.0,
                "finance_buy": 3.0,
                "slo_sell_amount": 2.5,
                "finance_repay": 7.0,
                "slo_repay": 4.0,
                "finance_net": 0.5,
            }
        ],
    )
    monkeypatch.setattr(stock_f10.settings, "offline_quantdb_root", tmp_path)
    response = _client(tmp_path).get(
        "/api/f10/margin-trading",
        params={"symbol": "000001.SZ", "source": "offline_quantdb", "limit": 20},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "offline_quantdb"
    assert body["count"] == 1
    assert body["as_of"] == "2026-08-04"
    assert body["status"] == "ok"
    row = body["data"][0]
    assert row["financing_balance"] == 1_000_000.0
    assert row["securities_lending_balance"] is None
    assert row["margin_balance"] is None


def test_offline_unconfigured_and_missing_file_are_not_empty_success(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(stock_f10.settings, "offline_quantdb_root", None)
    unconfigured = _client(tmp_path).get(
        "/api/f10/margin-trading",
        params={"symbol": "000001.SZ", "source": "offline_quantdb"},
    )
    assert unconfigured.status_code == 503
    assert unconfigured.json()["detail"]["code"] == "margin_trading_offline_unconfigured"

    monkeypatch.setattr(stock_f10.settings, "offline_quantdb_root", tmp_path)
    missing = _client(tmp_path).get(
        "/api/f10/margin-trading",
        params={"symbol": "000001.SZ", "source": "offline_quantdb"},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "margin_trading_offline_not_found"


def test_offline_invalid_symbol_and_empty_window(tmp_path: Path, monkeypatch) -> None:
    _write_offline(
        tmp_path,
        "000001.SZ",
        [
            {
                "time": date(2026, 8, 4),
                "Symbol": "000001.SZ",
                "finance_balance": 1.0,
                "slo_volume": 1.0,
                "finance_buy": 1.0,
                "slo_sell_amount": 1.0,
                "finance_repay": 1.0,
                "slo_repay": 1.0,
                "finance_net": 1.0,
            }
        ],
    )
    monkeypatch.setattr(stock_f10.settings, "offline_quantdb_root", tmp_path)
    client = _client(tmp_path)
    invalid = client.get(
        "/api/f10/margin-trading",
        params={"symbol": "../secret", "source": "offline_quantdb"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == "margin_trading_invalid_request"

    empty = client.get(
        "/api/f10/margin-trading",
        params={
            "symbol": "000001.SZ",
            "source": "offline_quantdb",
            "start_date": "2010-01-01",
            "end_date": "2010-01-02",
        },
    )
    assert empty.status_code == 200
    body = empty.json()
    assert body["status"] == "empty"
    assert body["count"] == 0
    assert body["as_of"] == "2026-08-04"
