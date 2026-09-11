from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import kline


class _Repo:
    def __init__(self, data_dir, daily: pl.DataFrame):
        self.store = SimpleNamespace(data_dir=data_dir)
        self._daily = daily

    def execute_one(self, *_args, **_kwargs):
        return ("立航科技", None, None)

    def get_daily(self, _symbol, start, end):
        return self._daily.filter(pl.col("date").is_between(start, end))


def _daily_rows() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "symbol": "603261.SH",
                "date": date(2026, 7, 30),
                "open": 43.22,
                "high": 44.66,
                "low": 42.80,
                "close": 41.26,
                "volume": 18_000.0,
            },
            {
                "symbol": "603261.SH",
                "date": date(2026, 7, 31),
                "open": 43.00,
                "high": 45.39,
                "low": 43.00,
                "close": 45.39,
                "volume": 20_000.0,
            },
        ]
    )


def _write_snapshot(data_dir, trade_date: str, **values) -> None:
    path = (
        data_dir
        / "quote_snapshot"
        / "asset_type=stock"
        / f"date={trade_date}"
        / "part.parquet"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        [
            {
                "symbol": "603261.SH",
                "date": trade_date,
                "open": values["open"],
                "high": values["high"],
                "low": values["low"],
                "close": values["close"],
                "prev_close": values["prev_close"],
                # 行情快照保存百分点;Kline API 对外统一为小数比例。
                "change_pct": values["change_pct"],
                "change_amount": values["change_amount"],
                "volume": values["volume"],
                "amount": values["amount"],
                "source": "tencent",
                "quality_status": "intraday_partial",
                "fetched_at": f"{trade_date}T15:06:52+08:00",
            }
        ]
    ).write_parquet(path)


def _client(tmp_path, daily: pl.DataFrame) -> TestClient:
    app = FastAPI()
    app.include_router(kline.router)
    app.state.repo = _Repo(tmp_path, daily)
    return TestClient(app)


def test_daily_response_overlays_newer_persisted_quote_snapshots_without_writing_daily(
    monkeypatch,
    tmp_path,
):
    _write_snapshot(
        tmp_path,
        "2026-08-03",
        open=47.89,
        high=49.93,
        low=45.55,
        close=49.93,
        prev_close=45.39,
        change_pct=10.002203,
        change_amount=4.54,
        volume=19_853.0,
        amount=98_360_000.0,
    )
    _write_snapshot(
        tmp_path,
        "2026-08-07",
        open=50.46,
        high=50.97,
        low=48.67,
        close=49.11,
        prev_close=50.45,
        change_pct=-2.656095,
        change_amount=-1.34,
        volume=24_954.0,
        amount=123_710_000.0,
    )
    monkeypatch.setattr(
        kline.kline_sync,
        "sync_daily_batch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must stay local")),
    )

    response = _client(tmp_path, _daily_rows()).get(
        "/api/kline/daily",
        params={
            "symbol": "603261.SH",
            "start_date": "2026-07-01",
            "end_date": "2026-08-08",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    latest = payload["rows"][-1]
    assert latest["date"] == "2026-08-07"
    assert latest["close"] == 49.11
    assert latest["prev_close"] == 50.45
    assert latest["change_amount"] == -1.34
    assert latest["change_pct"] == pytest.approx(-0.02656095)
    assert latest["is_quote_snapshot"] is True
    assert latest["quote_source"] == "tencent"
    assert payload["quote_overlay"] == {
        "applied": True,
        "row_count": 2,
        "latest_date": "2026-08-07",
        "latest_source": "tencent",
        "latest_fetched_at": "2026-08-07T15:06:52+08:00",
    }
    assert not (tmp_path / "kline_daily").exists()


def test_daily_response_respects_historical_end_date(tmp_path):
    _write_snapshot(
        tmp_path,
        "2026-08-07",
        open=50.46,
        high=50.97,
        low=48.67,
        close=49.11,
        prev_close=50.45,
        change_pct=-2.656095,
        change_amount=-1.34,
        volume=24_954.0,
        amount=123_710_000.0,
    )

    response = _client(tmp_path, _daily_rows()).get(
        "/api/kline/daily",
        params={
            "symbol": "603261.SH",
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"][-1]["date"] == "2026-07-31"
    assert payload["quote_overlay"]["applied"] is False
