from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api import kline
from app.tickflow.repository import DataStore, KlineReadError, KlineRepository


def test_scan_daily_symbol_empty_when_no_files(tmp_path) -> None:
    repo = KlineRepository(DataStore(tmp_path))
    frame = repo._scan_daily_symbol("000001.SZ", date(2026, 8, 1), date(2026, 8, 4), None)
    assert frame.is_empty()


def test_scan_daily_symbol_raises_on_corrupt_parquet(tmp_path) -> None:
    repo = KlineRepository(DataStore(tmp_path))
    dest = tmp_path / "kline_daily_enriched" / "date=2026-08-04" / "part.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"not a parquet")
    with pytest.raises(KlineReadError):
        repo._scan_daily_symbol("000001.SZ", date(2026, 8, 1), date(2026, 8, 4), None)


def test_get_minute_empty_when_no_files(tmp_path) -> None:
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.get_minute("000001.SZ", date(2026, 6, 29)).is_empty()


def test_get_minute_raises_on_corrupt_parquet(tmp_path) -> None:
    repo = KlineRepository(DataStore(tmp_path))
    dest = tmp_path / "kline_minute" / "date=2026-06-29" / "part.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"not a parquet")
    with pytest.raises(KlineReadError):
        repo.get_minute("000001.SZ", date(2026, 6, 29))


class _DailyFailRepo:
    def get_daily(self, *_args, **_kwargs):
        raise KlineReadError("日K读取失败: corrupt parquet")

    def get_daily_asset(self, *_args, **_kwargs):
        raise AssertionError("daily asset path must not run after get_daily")


class _MinuteFailRepo:
    def __init__(self, data_dir):
        self.store = SimpleNamespace(data_dir=data_dir)

    def execute_one(self, *_args, **_kwargs):
        return None

    def get_minute(self, *_args, **_kwargs):
        raise KlineReadError("分钟K读取失败: corrupt parquet")

    def get_daily(self, *_args, **_kwargs):
        raise AssertionError("minute persist path must not read daily after read failure")


def test_daily_api_does_not_fetch_when_local_read_fails(monkeypatch) -> None:
    called = {"fetch": 0}

    def fail_fetch(*_args, **_kwargs):
        called["fetch"] += 1
        raise AssertionError("TickFlow fetch must not run on corrupt local daily")

    monkeypatch.setattr(kline.kline_sync, "sync_daily_batch", fail_fetch)
    app = FastAPI()
    app.include_router(kline.router)
    app.state.repo = _DailyFailRepo()
    response = TestClient(app).get("/api/kline/daily?symbol=000001.SZ&days=120")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "kline_daily_read_failed"
    assert called["fetch"] == 0


def test_minute_api_does_not_persist_when_local_read_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.services.watchlist.contains", lambda *_args, **_kwargs: True)

    def fail_tdx(*_args, **_kwargs):
        raise AssertionError("TDX must not run on corrupt local minute")

    def fail_persist(*_args, **_kwargs):
        raise AssertionError("persist must not run on corrupt local minute")

    monkeypatch.setattr(
        "app.services.free_sources.tdx_history_minute.fetch_history_minute",
        fail_tdx,
    )
    monkeypatch.setattr(kline.kline_sync, "persist_historical_minute", fail_persist)
    monkeypatch.setattr(kline.kline_sync, "fetch_minute_single", fail_tdx)

    app = FastAPI()
    app.include_router(kline.router)
    app.state.repo = _MinuteFailRepo(tmp_path)
    response = TestClient(app).get("/api/kline/minute?symbol=301526.SZ&date=2026-06-29")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "kline_minute_read_failed"
