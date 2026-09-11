"""Daily sync must honor daily_data_provider (not always TickFlow)."""
from __future__ import annotations

from datetime import date, datetime

import polars as pl

from app.services import kline_sync
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet
from app.tickflow.repository import DataStore, KlineRepository


def _daily(symbol: str, day: date) -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": [symbol], "date": [day], "open": [10.0], "high": [11.0],
        "low": [9.0], "close": [10.5], "volume": [100.0], "amount": [1050.0],
    })


class _BatchProvider:
    def __init__(self, df: pl.DataFrame):
        self.df = df
        self.calls = 0

    def get_daily(self, *args, **kwargs):
        self.calls += 1
        return self.df


def test_custom_daily_get_daily_is_used_without_tickflow_cap(monkeypatch, tmp_path):
    provider = _BatchProvider(_daily("000001.SZ", date(2020, 1, 2)))
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "myhttp")
    from app.data_providers import custom
    monkeypatch.setattr(
        custom,
        "provider_has_dataset",
        lambda name, dataset: name == "myhttp" and dataset == "daily",
    )
    monkeypatch.setattr(custom, "get_provider", lambda name: provider)

    repo = KlineRepository(DataStore(tmp_path))
    written = kline_sync.sync_and_persist_daily_batch(
        ["000001.SZ"],
        repo,
        CapabilitySet(),
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2020, 1, 2),
    )
    assert written == 1
    assert provider.calls == 1
    stored = pl.read_parquet(
        repo.store.data_dir / "kline_daily" / "date=2020-01-02" / "part.parquet"
    )
    assert stored["symbol"].to_list() == ["000001.SZ"]


def test_tickflow_daily_still_requires_batch_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    hit = {"batch": False}
    monkeypatch.setattr(
        kline_sync,
        "sync_daily_batch",
        lambda *a, **k: hit.__setitem__("batch", True) or pl.DataFrame(),
    )
    repo = KlineRepository(DataStore(tmp_path))
    written = kline_sync.sync_and_persist_daily_batch(
        ["000001.SZ"],
        repo,
        CapabilitySet(),
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2020, 1, 2),
    )
    assert written == 0
    assert hit["batch"] is False

    written = kline_sync.sync_and_persist_daily_batch(
        ["000001.SZ"],
        repo,
        CapabilitySet({Cap.KLINE_DAILY_BATCH: CapabilityLimits()}),
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2020, 1, 2),
    )
    assert hit["batch"] is True
    assert written == 0
