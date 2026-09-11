from __future__ import annotations

from datetime import date, timedelta

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.stock_analysis import router
from app.services.stock_analyzer import KLINE_ANALYSIS_COLS


class _FakeRepo:
    def __init__(self, daily: pl.DataFrame, instruments: pl.DataFrame | None = None) -> None:
        self._daily = daily
        self._instruments = instruments if instruments is not None else pl.DataFrame()
        self.get_daily_calls: list[tuple[str, date, date]] = []

    def get_daily(self, symbol: str, start: date, end: date) -> pl.DataFrame:
        self.get_daily_calls.append((symbol, start, end))
        return self._daily

    def get_instruments(self) -> pl.DataFrame:
        return self._instruments


def _client(repo: _FakeRepo) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.repo = repo
    return TestClient(app)


def _wide_daily(n: int, start: date) -> pl.DataFrame:
    rows = []
    for i in range(n):
        day = start + timedelta(days=i)
        close = 100.0 + i
        rows.append(
            {
                "date": day,
                "open": close - 1,
                "high": close + 1,
                "low": close - 2,
                "close": close,
                "volume": 1_000_000 + i,
                "change_pct": 0.01,
                "ma5": close,
                "ma10": close,
                "ma20": close,
                "ma60": close,
                "macd_dif": 0.1,
                "macd_dea": 0.2,
                "macd_hist": -0.1,
                "kdj_k": 50.0,
                "kdj_d": 50.0,
                "kdj_j": 50.0,
                "rsi_6": 55.0,
                "rsi_14": 50.0,
                "rsi_24": 45.0,
                "boll_upper": close + 5,
                "boll_mid": close,
                "boll_lower": close - 5,
                "atr_14": 2.0,
                "vol_ratio_5d": 1.1,
                "turnover_rate": 1.2,
                "consecutive_limit_ups": 0,
                "signal_limit_up": False,
                "extra_wide_column": 999,
                "stock_info_should_not_leak": "nope",
            }
        )
    return pl.DataFrame(rows)


def test_daily_window_projects_analysis_columns_only():
    repo = _FakeRepo(
        _wide_daily(5, date(2026, 8, 1)),
        pl.DataFrame({"symbol": ["300750.SZ"], "name": ["宁德时代"]}),
    )
    client = _client(repo)

    payload = client.get(
        "/api/stock-analysis/daily-window",
        params={"symbol": "300750.SZ", "days": 90},
    ).json()

    assert payload["symbol"] == "300750.SZ"
    assert payload["name"] == "宁德时代"
    assert payload["source"] == "local_enriched"
    assert payload["returned"] == 5
    assert set(payload["rows"][0]) <= set(KLINE_ANALYSIS_COLS)
    assert "extra_wide_column" not in payload["rows"][0]
    assert "stock_info" not in payload
    assert "quote_overlay" not in payload


def test_daily_window_keeps_the_latest_tail_when_local_bars_exceed_days():
    start = date(2026, 1, 1)
    repo = _FakeRepo(_wide_daily(120, start))
    client = _client(repo)

    payload = client.get(
        "/api/stock-analysis/daily-window",
        params={"symbol": "300750.SZ", "days": 90},
    ).json()

    assert payload["available"] == 120
    assert payload["returned"] == 90
    assert payload["truncated"] is True
    assert payload["truncated_side"] == "tail"
    assert payload["first_date"] == (start + timedelta(days=30)).isoformat()
    assert payload["last_date"] == (start + timedelta(days=119)).isoformat()
    assert payload["rows"][-1]["date"] == payload["last_date"]


def test_daily_window_returns_empty_rows_without_syncing_when_local_bars_missing():
    repo = _FakeRepo(pl.DataFrame())
    repo.sync_called = False

    def _forbidden(*_args, **_kwargs):
        repo.sync_called = True
        raise AssertionError("daily-window must not sync")

    repo.sync_daily_batch = _forbidden
    client = _client(repo)
    payload = client.get(
        "/api/stock-analysis/daily-window",
        params={"symbol": "000000.SZ", "days": 90},
    ).json()

    assert payload["rows"] == []
    assert payload["returned"] == 0
    assert payload["available"] == 0
    assert payload["first_date"] is None
    assert payload["last_date"] is None
    assert payload["truncated"] is False
    assert payload["truncated_side"] is None
    assert repo.sync_called is False
    assert repo.get_daily_calls
