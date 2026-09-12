"""Thirty-first-round leftover mix-source / fail-open paths.

Closes residual fail-open / silent mix that round 30 left documented:
- unreadable leftover daily / minute probes no longer mint calendars
- unreadable tagged leftover no longer falls back to untagged extras
- leftover TickFlow kline_ext remount skips after custom daily
- unreadable leftover kline_ext date markers no longer mint a view
- leftover TickFlow financial / pool jobs skip after custom daily

Keeps remaining TickFlow leftover contracts:
- leftover TickFlow still sees untagged-only partitions
- leftover TickFlow + free realtime stays mode=none
- leftover TickFlow daily + public realtime overlay stays labeled
- explicit adj=public / depth5=public / financial=public / pool=public stay
- after-hours default clock times / .env / auth stay out of scope
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl

from app.api import ext_data as ext_api
from app.api import kline as kline_api
from app.data_catalog.scanner import _catalog_file_usable
from app.services import financial_sync, kline_sync, preferences, universe_scope
from app.services.quote_service import QuoteService, usable_quote_snapshot_files
from app.tickflow import pools
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet
from app.tickflow.repository import DataStore, KlineRepository


def _prefs_boom(*_a, **_k):
    raise RuntimeError("prefs unreadable")


def _daily_df(symbol: str = "000001.SZ", *, route: str | None = None, day: date | None = None) -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "date": [day or date(2026, 7, 17)],
        "open": [10.0],
        "high": [10.2],
        "low": [9.9],
        "close": [10.1],
        "volume": [100.0],
        "amount": [101000.0],
        "change_pct": [0.01],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _minute_df(*, route: str | None = None, ts: datetime | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "datetime": [ts or datetime(2026, 7, 17, 9, 31)],
        "open": [10.0],
        "high": [10.2],
        "low": [9.9],
        "close": [10.1],
        "volume": [100.0],
        "amount": [1010.0],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _quote_df(*, route: str | None = None, day: date | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "date": [day or date(2026, 7, 18)],
        "open": [10.0],
        "high": [10.2],
        "low": [9.9],
        "close": [10.1],
        "volume": [100.0],
        "amount": [1010.0],
        "source": ["tencent"],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _patch_custom_daily(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset, wanted=name: n == wanted and dataset == "daily",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _capset(*caps: Cap) -> CapabilitySet:
    return CapabilitySet({cap: CapabilityLimits() for cap in caps})


def test_unreadable_daily_probe_is_fail_closed(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17" / "part.parquet"
    part.parent.mkdir(parents=True)
    part.write_bytes(b"")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert kline_sync.daily_partition_usable(part) is False
    assert kline_sync.usable_daily_partition_dates(tmp_path) == []
    assert kline_sync.usable_daily_partition_files(part.parent) == []
    assert kline_sync.read_usable_daily_partition(part.parent).is_empty()


def test_unreadable_minute_probe_is_fail_closed(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17" / "part.parquet"
    part.parent.mkdir(parents=True)
    part.write_bytes(b"")
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    assert kline_sync.minute_partition_usable(part) is False
    assert kline_sync.usable_minute_partition_dates(tmp_path) == []
    assert kline_sync.usable_minute_partition_files(part.parent) == []


def test_unreadable_tagged_leftover_does_not_mix_untagged(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    (part / "part.parquet").write_bytes(b"")
    _daily_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert kline_sync.usable_daily_partition_dates(tmp_path) == []
    assert kline_sync.usable_daily_partition_files(part) == []
    assert kline_sync.read_usable_daily_partition(part).is_empty()


def test_unreadable_tagged_minute_does_not_mix_untagged(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    (part / "part.parquet").write_bytes(b"")
    _minute_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    assert kline_sync.usable_minute_partition_dates(tmp_path) == []
    assert kline_sync.usable_minute_partition_files(part) == []


def test_unreadable_tagged_quote_does_not_mix_untagged(monkeypatch, tmp_path):
    part = tmp_path / "quote_snapshot" / "asset_type=stock" / "date=2026-07-17"
    part.mkdir(parents=True)
    (part / "part.parquet").write_bytes(b"")
    _quote_df(day=date(2026, 7, 17)).write_parquet(part / "extra.parquet")
    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "tickflow")
    assert usable_quote_snapshot_files(part) == []


def test_catalog_skips_unreadable_leftover_daily(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17" / "part.parquet"
    part.parent.mkdir(parents=True)
    part.write_bytes(b"")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert _catalog_file_usable("stock_daily", part) is False


def test_kline_ext_skips_after_custom_daily(monkeypatch, tmp_path):
    part = tmp_path / "kline_ext" / "date=2026-07-17"
    part.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "factor": [1.0]}).write_parquet(part / "part.parquet")
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.db.execute("SELECT count(*) FROM kline_ext").fetchone()[0] == 0
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo)))
    ext_api._refresh_views(request)
    assert repo.db.execute("SELECT count(*) FROM kline_ext").fetchone()[0] == 0


def test_kline_ext_keeps_leftover_tickflow_latest(monkeypatch, tmp_path):
    for day, value in (("2026-07-17", 1.0), ("2026-07-18", 2.0)):
        part = tmp_path / "kline_ext" / f"date={day}"
        part.mkdir(parents=True)
        pl.DataFrame({"symbol": ["000001.SZ"], "factor": [value]}).write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    store = DataStore(tmp_path)
    assert [row[0] for row in store.db.query("SELECT factor FROM kline_ext").fetchall()] == [2.0]


def test_unreadable_kline_ext_marker_does_not_mint(monkeypatch, tmp_path):
    part = tmp_path / "kline_ext" / "date=2026-07-18"
    part.mkdir(parents=True)
    (part / "part.parquet").write_bytes(b"")
    older = tmp_path / "kline_ext" / "date=2026-07-17"
    older.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "factor": [1.0]}).write_parquet(older / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    glob = ext_api._latest_date_partition_glob(tmp_path / "kline_ext")
    assert glob is not None
    assert "2026-07-17" in glob
    assert "2026-07-18" not in glob
    store = DataStore(tmp_path)
    assert [row[0] for row in store.db.query("SELECT factor FROM kline_ext").fetchall()] == [1.0]


def test_kline_ext_date_range_skips_after_custom_daily(monkeypatch, tmp_path):
    part = tmp_path / "kline_ext" / "date=2026-07-17"
    part.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "factor": [1.0]}).write_parquet(part / "part.parquet")
    config = SimpleNamespace(id="legacy", mode="timeseries")
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(ext_api, "_ext_data_dir", lambda *_a, **_k: tmp_path / "missing")
    assert ext_api._date_range(config, tmp_path) is None
    assert ext_api._latest_sync_date(config, tmp_path) is None


def test_leftover_tickflow_financial_skips_after_custom_daily(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    _patch_custom_daily(monkeypatch)
    tf = MagicMock(side_effect=AssertionError("must not call leftover TickFlow financials"))
    monkeypatch.setattr("app.tickflow.client.get_client", tf)
    assert financial_sync.financials_live_allowed(_capset(Cap.FINANCIAL)) is False
    assert financial_sync.sync_all(tmp_path, _capset(Cap.FINANCIAL)) == {}
    tf.assert_not_called()


def test_leftover_tickflow_financial_still_uses_entitled_tickflow(monkeypatch):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert financial_sync.financials_live_allowed(_capset(Cap.FINANCIAL)) is True


def test_explicit_public_financial_still_allowed_after_custom_daily(monkeypatch):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "public")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: True)
    _patch_custom_daily(monkeypatch)
    assert financial_sync.financials_live_allowed(CapabilitySet()) is True


def test_leftover_tickflow_pool_skips_after_custom_daily(monkeypatch, tmp_path):
    monkeypatch.setattr(pools, "pool_route", lambda: "tickflow")
    _patch_custom_daily(monkeypatch)
    tf = MagicMock(side_effect=AssertionError("must not call leftover TickFlow pool"))
    monkeypatch.setattr(pools, "get_client", tf)
    cache = tmp_path / "pools" / "CSI300.parquet"
    cache.parent.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "route": ["tickflow"]}).write_parquet(cache)
    monkeypatch.setattr(pools, "_pool_cache_path", lambda pool_id: cache)
    assert pools.get_pool("CSI300") == []
    assert pools._fetch_pool("CSI300") == []
    assert universe_scope._ensure_csi_pool("CSI300", tmp_path) == []
    tf.assert_not_called()


def test_leftover_tickflow_pool_still_uses_entitled_tickflow(monkeypatch, tmp_path):
    monkeypatch.setattr(pools, "pool_route", lambda: "tickflow")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    cache = tmp_path / "pools" / "CSI300.parquet"
    cache.parent.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "route": ["tickflow"]}).write_parquet(cache)
    monkeypatch.setattr(pools, "_pool_cache_path", lambda pool_id: cache)
    assert pools.get_pool("CSI300") == ["000001.SZ"]


def test_explicit_public_pool_still_allowed_after_custom_daily(monkeypatch, tmp_path):
    monkeypatch.setattr(pools, "pool_route", lambda: "public")
    _patch_custom_daily(monkeypatch)
    cache = tmp_path / "pools" / "CSI300.parquet"
    cache.parent.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "route": ["public"]}).write_parquet(cache)
    monkeypatch.setattr(pools, "_pool_cache_path", lambda pool_id: cache)
    assert pools.get_pool("CSI300") == ["000001.SZ"]


def test_untagged_only_still_serves_leftover_tickflow(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert kline_sync.usable_daily_partition_dates(tmp_path) == [date(2026, 7, 17)]
    assert kline_sync.read_usable_daily_partition(part)["close"].to_list() == [10.1]


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"


def test_quote_overlay_keeps_public_realtime_on_leftover_daily(monkeypatch, tmp_path):
    part = tmp_path / "quote_snapshot" / "asset_type=stock" / "date=2026-07-18"
    part.mkdir(parents=True)
    _quote_df().write_parquet(part / "part.parquet")
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    rows = [{
        "symbol": "000001.SZ",
        "date": "2026-07-17",
        "open": 10.0,
        "high": 10.0,
        "low": 10.0,
        "close": 10.0,
    }]
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "public")
    overlaid, meta = kline_api._overlay_persisted_quote_candles(
        repo, "000001.SZ", rows, date(2026, 7, 17), date(2026, 7, 18),
    )
    assert meta["applied"] is True
    assert overlaid[-1]["is_quote_snapshot"] is True
    _patch_custom_daily(monkeypatch)
    overlaid, meta = kline_api._overlay_persisted_quote_candles(
        repo, "000001.SZ", rows, date(2026, 7, 17), date(2026, 7, 18),
    )
    assert meta["applied"] is False
    assert len(overlaid) == 1


def test_after_hours_default_clock_stays_ops_schedule(monkeypatch):
    monkeypatch.setattr(preferences, "load_server", lambda: {})
    monkeypatch.setattr(preferences, "load", lambda: {})
    assert preferences.get_pipeline_schedule() == {"hour": 15, "minute": 30}
    assert preferences.get_instruments_schedule() == {"hour": 9, "minute": 10}
    assert preferences.get_depth_finalize_time() == {"hour": 15, "minute": 2}


def test_unreadable_prefs_stay_fail_closed(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    monkeypatch.setattr(preferences, "get_financial_provider", _prefs_boom)
    monkeypatch.setattr(pools, "pool_route", lambda: "tickflow")
    assert kline_sync.leftover_tickflow_follow_daily() is False
    assert financial_sync.financials_live_allowed(_capset(Cap.FINANCIAL)) is False
    assert pools.get_pool("CSI300") == []
    assert ext_api._legacy_kline_ext_visible() is False
