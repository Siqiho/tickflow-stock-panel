from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import kline


class _Repo:
    def __init__(self, data_dir):
        self.store = SimpleNamespace(data_dir=data_dir)
        self._minute = pl.DataFrame()

    def execute_one(self, *_args, **_kwargs):
        return None

    def get_minute(self, _symbol, _trade_date):
        return self._minute

    def get_daily(self, _symbol, _start, _end):
        return pl.DataFrame()


def test_historical_minute_endpoint_rejects_rows_from_another_trade_date(monkeypatch, tmp_path):
    wrong_day = pl.DataFrame(
        {
            "symbol": ["301526.SZ", "301526.SZ"],
            "datetime": [datetime(2026, 8, 5, 9, 30), datetime(2026, 8, 5, 9, 31)],
            "open": [28.8, 28.8],
            "high": [28.8, 29.0],
            "low": [28.8, 28.8],
            "close": [28.8, 29.0],
            "volume": [100.0, 200.0],
            "amount": [2880.0, 5800.0],
        }
    )
    monkeypatch.setattr(kline.kline_sync, "fetch_minute_single", lambda *_args, **_kwargs: wrong_day)
    monkeypatch.setattr("app.services.watchlist.contains", lambda *_args, **_kwargs: False)

    app = FastAPI()
    app.include_router(kline.router)
    app.state.repo = _Repo(tmp_path)
    client = TestClient(app)

    response = client.get("/api/kline/minute?symbol=301526.SZ&date=2026-07-20")

    assert response.status_code == 200
    assert response.json()["date"] == "2026-07-20"
    assert response.json()["rows"] == []
    assert response.json()["source"] == "none"


def test_watchlist_historical_minute_fetches_and_persists_exact_day(monkeypatch, tmp_path):
    rows = pl.DataFrame(
        {
            "symbol": ["301526.SZ"],
            "datetime": [datetime(2026, 6, 29, 9, 30)],
            "open": [50.92],
            "high": [50.92],
            "low": [50.92],
            "close": [50.92],
            "volume": [89645.0],
            "amount": [4562723.4],
        }
    )
    repo = _Repo(tmp_path)
    repo._minute = rows
    repo.get_daily = lambda *_args: pl.DataFrame({"date": [datetime(2026, 6, 29).date()]})
    calls = []

    monkeypatch.setattr("app.services.watchlist.contains", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(kline.kline_sync, "minute_may_use_leftover_public", lambda: True)
    monkeypatch.setattr(
        "app.services.free_sources.tdx_history_minute.fetch_history_minute",
        lambda *_args: rows,
    )

    def fake_persist(candidate, _repo, symbol, trade_date, _daily, *, source, adapter):
        calls.append((candidate.height, symbol, trade_date.isoformat(), source, adapter))
        return {"row_count": candidate.height}

    monkeypatch.setattr(kline.kline_sync, "persist_historical_minute", fake_persist)

    app = FastAPI()
    app.include_router(kline.router)
    app.state.repo = repo
    response = TestClient(app).get(
        "/api/kline/minute?symbol=301526.SZ&date=2026-06-29"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "local"
    assert payload["provider"] == "easy_tdx_1.20.6"
    assert payload["persisted"] is True
    assert payload["rows"][0]["datetime"].startswith("2026-06-29")
    assert calls == [
        (1, "301526.SZ", "2026-06-29", "tdx_public", "easy_tdx_1.20.6")
    ]


def test_non_watchlist_historical_minute_never_uses_tdx(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.watchlist.contains", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(kline.kline_sync, "fetch_minute_single", lambda *_args, **_kwargs: pl.DataFrame())

    def fail_tdx(*_args):
        raise AssertionError("TDX must stay scoped to the watchlist")

    monkeypatch.setattr(
        "app.services.free_sources.tdx_history_minute.fetch_history_minute",
        fail_tdx,
    )
    app = FastAPI()
    app.include_router(kline.router)
    app.state.repo = _Repo(tmp_path)

    response = TestClient(app).get(
        "/api/kline/minute?symbol=000001.SZ&date=2026-06-29"
    )

    assert response.status_code == 200
    assert response.json()["source"] == "none"


def test_minute_batch_preserves_null_amount(tmp_path):
    repo = _Repo(tmp_path)
    repo._minute = pl.DataFrame(
        {
            "datetime": [datetime(2026, 7, 15, 9, 30)],
            "open": [10.0],
            "high": [10.1],
            "low": [9.9],
            "close": [10.0],
            "volume": [100.0],
            "amount": [None],
        },
        schema={
            "datetime": pl.Datetime,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
        },
    )
    app = FastAPI()
    app.include_router(kline.router)
    app.state.repo = repo
    response = TestClient(app).post(
        "/api/kline/minute-batch",
        json={"symbols": ["600000.SH"], "date": "2026-07-15"},
    )
    assert response.status_code == 200
    rows = response.json()["data"]["600000.SH"]
    assert rows[0]["amount"] is None
