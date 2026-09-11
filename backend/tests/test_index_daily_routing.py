"""Index/ETF daily must honor daily_data_provider (not always TickFlow)."""
from __future__ import annotations

from datetime import date, datetime

import polars as pl

from app.services import index_sync, kline_sync
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet
from app.tickflow.repository import DataStore, KlineRepository


def _daily(symbol: str, day: date) -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": [symbol], "date": [day], "open": [10.0], "high": [11.0],
        "low": [9.0], "close": [10.5], "volume": [100.0], "amount": [1050.0],
    })


class _RecordingProvider:
    def __init__(self, df: pl.DataFrame | None):
        self.df = df
        self.calls: list[dict] = []

    def get_daily(self, *args, **kwargs):
        self.calls.append(kwargs)
        return self.df if self.df is not None else pl.DataFrame()


def _route_daily(monkeypatch, provider, name: str = "myhttp"):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: name)
    from app.data_providers import custom
    monkeypatch.setattr(
        custom,
        "provider_has_dataset",
        lambda n, dataset: n == name and dataset == "daily",
    )
    monkeypatch.setattr(custom, "get_provider", lambda n: provider)


def test_index_daily_uses_custom_daily_provider(monkeypatch, tmp_path):
    provider = _RecordingProvider(_daily("000001.SH", date(2020, 1, 2)))
    _route_daily(monkeypatch, provider)
    hit = {"batch": False}
    monkeypatch.setattr(
        kline_sync,
        "sync_daily_batch",
        lambda *a, **k: hit.__setitem__("batch", True) or pl.DataFrame(),
    )

    repo = KlineRepository(DataStore(tmp_path))
    written = index_sync.sync_and_persist_index_daily(
        repo,
        CapabilitySet(),
        symbols_override=["000001.SH"],
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2020, 1, 2),
    )
    assert written == 1
    assert provider.calls and provider.calls[0]["asset_type"] == "index"
    assert hit["batch"] is False
    stored = pl.read_parquet(
        repo.store.data_dir / "kline_index_daily" / "date=2020-01-02" / "part.parquet"
    )
    assert stored["symbol"].to_list() == ["000001.SH"]


def test_index_daily_stock_only_custom_does_not_fall_back_to_tickflow(monkeypatch, tmp_path):
    provider = _RecordingProvider(pl.DataFrame())
    _route_daily(monkeypatch, provider)
    hit = {"batch": False}
    monkeypatch.setattr(
        kline_sync,
        "sync_daily_batch",
        lambda *a, **k: hit.__setitem__("batch", True) or _daily("000001.SH", date(2020, 1, 2)),
    )

    repo = KlineRepository(DataStore(tmp_path))
    written = index_sync.sync_and_persist_index_daily(
        repo,
        CapabilitySet({Cap.KLINE_DAILY_BATCH: CapabilityLimits()}),
        symbols_override=["000001.SH"],
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2020, 1, 2),
    )
    assert written == 0
    assert hit["batch"] is False
    assert provider.calls and provider.calls[0]["asset_type"] == "index"


def test_etf_daily_uses_custom_daily_provider(monkeypatch, tmp_path):
    provider = _RecordingProvider(_daily("510300.SH", date(2020, 1, 2)))
    _route_daily(monkeypatch, provider)
    hit = {"batch": False}
    monkeypatch.setattr(
        kline_sync,
        "sync_daily_batch",
        lambda *a, **k: hit.__setitem__("batch", True) or pl.DataFrame(),
    )

    repo = KlineRepository(DataStore(tmp_path))
    written = index_sync.sync_and_persist_etf_daily(
        repo,
        CapabilitySet(),
        symbols_override=["510300.SH"],
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2020, 1, 2),
    )
    assert written == 1
    assert provider.calls and provider.calls[0]["asset_type"] == "etf"
    assert hit["batch"] is False


def test_index_daily_tickflow_still_requires_batch_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    hit = {"batch": False}
    monkeypatch.setattr(
        kline_sync,
        "sync_daily_batch",
        lambda *a, **k: hit.__setitem__("batch", True) or pl.DataFrame(),
    )
    repo = KlineRepository(DataStore(tmp_path))
    written = index_sync.sync_and_persist_index_daily(
        repo,
        CapabilitySet(),
        symbols_override=["000001.SH"],
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2020, 1, 2),
    )
    assert written == 0
    assert hit["batch"] is False
