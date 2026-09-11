"""Twentieth-round leftover mix-source / fail-open paths.

Closes remaining except-fallback leftover globs and leftover-shadowed
reads that round 19 left on the cache / overview / persist / scan side:
- overview official-day probe throw no longer treats leftover as official
- screener latest_date stays on disk provenance (no leftover cache / SQL)
- in-memory enriched latest / hist / overlay caches drop leftover TickFlow
- live-agg baseline uses file provenance, not temporarily ungated SQL
- leftover TickFlow parquet no longer poisons the full enriched glob
- get_enriched_history / range / live-agg drop leftover TickFlow on throw
- index/ETF status calendars do not count leftover DuckDB rows
- auction enrich / official trend overlay fail-closed when the probe throws
- public EOD persist refuses custom / unresolved daily internally
- reference_derived calendars use safe dates

Keeps remaining TickFlow leftover contracts:
- leftover TickFlow + free realtime stays mode=none
- entitled TickFlow minute fallback after a custom *call* failure
- leftover TickFlow single-symbol minute view may still use public / TDX
- A-share / index / ETF instruments stay TickFlow (no instrument_provider)
- quote_snapshot overlay stays an isolated live asset
- after-hours default times / .env / auth stay out of scope
- leftover TickFlow still sees untagged partitions
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import polars as pl
import pytest

from app.api import data as data_api
from app.services import auction_benchmark, kline_sync, rps_rotation
from app.services.intraday_overview import load_official_trend_overlay
from app.services.market_overview_builder import _has_official_enriched
from app.services.quote_service import QuoteService
from app.services.reference_derived import list_partition_dates
from app.services.screener import ScreenerService
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
        "amount": [1010.0],
        "raw_close": [10.1],
        "raw_high": [10.2],
        "raw_low": [9.9],
        "turnover_rate": [1.0],
        "consecutive_limit_ups": [2],
        "consecutive_limit_downs": [0],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _patch_custom_daily(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == name and dataset == "daily",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _write_part(root, table: str, day: str, df: pl.DataFrame) -> None:
    part = root / table / f"date={day}"
    part.mkdir(parents=True, exist_ok=True)
    df.write_parquet(part / "part.parquet")


def test_has_official_never_fail_open(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(kline_sync, "daily_partition_usable", _prefs_boom)
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert _has_official_enriched(repo, date(2026, 7, 17)) is False


def test_has_official_skips_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert _has_official_enriched(repo, date(2026, 7, 17)) is False


def test_has_official_keeps_untagged_leftover_tickflow(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df())
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert _has_official_enriched(repo, date(2026, 7, 17)) is True


def test_screener_latest_skips_leftover_cache(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-16", _daily_df(route="fuyao", day=date(2026, 7, 16)))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    repo._enriched_cache = _daily_df(route="tickflow")
    repo._enriched_cache_date = date(2026, 7, 17)
    svc = ScreenerService(repo)
    assert svc.latest_date() == date(2026, 7, 16)


def test_screener_latest_never_fail_open(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = SimpleNamespace(
        latest_enriched_date=_prefs_boom,
        enriched_latest_date=lambda: date(2026, 7, 17),
        execute_one=lambda *_a, **_k: (date(2026, 7, 17),),
    )
    assert ScreenerService(repo).latest_date() is None


def test_get_enriched_latest_skips_leftover_cache(monkeypatch, tmp_path):
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-16",
        _daily_df(route="fuyao", day=date(2026, 7, 16)),
    )
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    repo._enriched_cache = _daily_df(route="tickflow")
    repo._enriched_cache_date = date(2026, 7, 17)
    df, latest = repo.get_enriched_latest()
    assert latest == date(2026, 7, 16)
    assert not df.is_empty()
    assert str(df["route"][0]) == "fuyao"


def test_get_daily_skips_leftover_hist_cache(monkeypatch, tmp_path):
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-16",
        _daily_df(route="fuyao", day=date(2026, 7, 16)),
    )
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-17",
        _daily_df(route="tickflow").with_columns(pl.lit(999.0).alias("close")),
    )
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    leftover = _daily_df(route="tickflow").with_columns(pl.lit(999.0).alias("close"))
    repo._enriched_history_cache = leftover
    repo._enriched_history_start = date(2026, 7, 1)
    repo._enriched_cache = leftover
    repo._enriched_cache_date = date(2026, 7, 17)
    df = repo.get_daily("000001.SZ", date(2026, 7, 16), date(2026, 7, 17))
    assert not df.is_empty()
    assert date(2026, 7, 17) not in [d if isinstance(d, date) else d for d in df["date"].to_list()]
    assert float(df.filter(pl.col("date") == date(2026, 7, 16))["close"][0]) == pytest.approx(10.1)


def test_get_daily_batch_skips_leftover_schema_poison(monkeypatch, tmp_path):
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-16",
        _daily_df(route="fuyao", day=date(2026, 7, 16)),
    )
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-17",
        _daily_df(route="tickflow").with_columns(pl.lit(999.0).alias("close")),
    )
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    df = repo.get_daily_batch(["000001.SZ"], date(2026, 7, 16), date(2026, 7, 17))
    assert not df.is_empty()
    assert date(2026, 7, 17) not in [d if isinstance(d, date) else d for d in df["date"].to_list()]


def test_get_index_daily_skips_leftover_schema_poison(monkeypatch, tmp_path):
    _write_part(
        tmp_path,
        "kline_index_enriched",
        "2026-07-16",
        _daily_df("000001.SH", route="fuyao", day=date(2026, 7, 16)),
    )
    _write_part(
        tmp_path,
        "kline_index_enriched",
        "2026-07-17",
        _daily_df("000001.SH", route="tickflow").with_columns(pl.lit(999.0).alias("close")),
    )
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    df = repo.get_index_daily("000001.SH", date(2026, 7, 16), date(2026, 7, 17))
    assert not df.is_empty()
    assert float(df["close"][0]) == pytest.approx(10.1)


def test_get_enriched_range_skips_leftover_hist(monkeypatch, tmp_path):
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    leftover = _daily_df(route="tickflow").with_columns(pl.lit(0.05).alias("change_pct"))
    repo._enriched_history_cache = leftover
    repo._enriched_history_start = date(2026, 7, 1)
    assert repo.get_enriched_range(date(2026, 7, 17), date(2026, 7, 17)) is None
    assert repo.get_enriched_history(date(2026, 7, 17), 1) is None


def test_get_enriched_range_never_fail_open(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    leftover = _daily_df(route="tickflow").with_columns(pl.lit(0.05).alias("change_pct"))
    repo._enriched_history_cache = leftover
    repo._enriched_history_start = date(2026, 7, 1)
    monkeypatch.setattr(kline_sync, "filter_daily_cache", _prefs_boom)
    assert repo.get_enriched_range(date(2026, 7, 17), date(2026, 7, 17)) is None
    assert repo.get_enriched_history(date(2026, 7, 17), 1) is None


def test_get_live_agg_skips_leftover_hist(monkeypatch, tmp_path):
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-16",
        _daily_df(route="fuyao", day=date(2026, 7, 16)),
    )
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    leftover = _daily_df(route="tickflow")
    repo._enriched_history_cache = leftover
    repo._enriched_history_start = date(2026, 7, 1)
    repo._enriched_cache = leftover
    repo._enriched_cache_date = date(2026, 7, 17)
    repo._live_agg_cache = leftover
    repo._live_agg_cache_date = date(2026, 7, 17)
    out = repo.get_live_agg()
    if out is not None and not out.is_empty() and "route" in out.columns:
        assert "tickflow" not in [str(v).lower() for v in out["route"].to_list()]
    assert repo._live_agg_usable() is False or (
        repo._enriched_cache is None or repo._latest_cache_usable(repo._enriched_cache)
    )


def test_status_index_does_not_count_leftover_sql_rows(monkeypatch, tmp_path):
    _write_part(
        tmp_path,
        "kline_index_daily",
        "2026-07-16",
        _daily_df("000001.SH", route="fuyao", day=date(2026, 7, 16)),
    )
    _write_part(
        tmp_path,
        "kline_index_daily",
        "2026-07-17",
        _daily_df("000001.SH", route="tickflow"),
    )
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    stats = data_api._safe_aggregate_index_daily(repo)
    assert stats is not None
    assert stats["latest_date"] == "2026-07-16"
    assert stats["trading_days"] == 1
    assert stats["rows"] == 0


def test_rps_scan_skips_leftover_hist(monkeypatch, tmp_path):
    custom = _daily_df(route="fuyao", day=date(2026, 7, 16)).with_columns(
        pl.lit(0.02).alias("change_pct"),
    )
    leftover = _daily_df(route="tickflow").with_columns(pl.lit(0.99).alias("change_pct"))
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-16", custom)
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", leftover)
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    repo._enriched_history_cache = leftover
    repo._enriched_history_start = date(2026, 7, 1)
    df = rps_rotation._scan_change_pct(repo, date(2026, 7, 16), date(2026, 7, 17))
    assert df is not None and not df.is_empty()
    assert float(df["change_pct"][0]) == pytest.approx(0.02)


def test_filter_cached_skips_leftover_under_custom(monkeypatch, tmp_path):
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    leftover = _daily_df(route="tickflow")
    assert repo._filter_cached(leftover, "000001.SZ", None).is_empty()
    assert repo._filter_cached_batch(leftover, ["000001.SZ"], None).is_empty()


def test_live_agg_baseline_skips_leftover_sql(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-16", _daily_df(route="fuyao", day=date(2026, 7, 16)))
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    monkeypatch.setattr(repo, "execute_one", lambda *_a, **_k: (date(2026, 7, 17),))
    today = date.today()
    assert repo._live_agg_baseline_date(today) == date(2026, 7, 16)


def test_auction_enrich_never_fail_open(monkeypatch, tmp_path):
    leftover = pl.DataFrame({
        "symbol": ["600519.SH"],
        "open": [10.0],
        "close": [11.0],
        "route": ["tickflow"],
    })
    _write_part(tmp_path, "kline_daily", "2026-07-17", leftover)
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(kline_sync, "daily_partition_usable", _prefs_boom)
    items = [{"thscode": "600519.SH", "ticker": "600519", "name": "茅台", "auction_pct": 1.0}]
    out = auction_benchmark._enrich(tmp_path, date(2026, 7, 17), items)
    assert out[0]["day0_oc"] is None


def test_overlay_never_fail_open(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(kline_sync, "daily_partition_usable", _prefs_boom)
    assert load_official_trend_overlay(tmp_path, date(2026, 7, 17)) == {}


def test_overlay_skips_leftover_under_custom(monkeypatch, tmp_path):
    leftover = _daily_df(route="tickflow").with_columns(pl.lit(999.0).alias("close"))
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", leftover)
    _patch_custom_daily(monkeypatch)
    assert load_official_trend_overlay(tmp_path, date(2026, 7, 17)) == {}


def test_public_eod_refuses_custom_internally(monkeypatch, tmp_path):
    _patch_custom_daily(monkeypatch)
    flushed = []
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        flush_live_daily=lambda df: flushed.append(df.height),
        db=SimpleNamespace(execute=lambda *_a, **_k: None),
    )
    monkeypatch.setattr(
        "app.services.free_sources.quote_fallback.fetch_public_market_quotes",
        lambda *_a, **_k: [{"symbol": "000001.SZ", "last": 10.5, "open": 10.0, "high": 10.8, "low": 9.9, "volume": 1000, "amount": 1e6}],
    )
    result = kline_sync.sync_daily_by_public_quotes(
        ["000001.SZ"], repo, trade_date=date(2026, 7, 20),
    )
    assert result["rows"] == 0
    assert flushed == []


def test_public_eod_refuses_unreadable_prefs(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    flushed = []
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        flush_live_daily=lambda df: flushed.append(df.height),
    )
    result = kline_sync.sync_daily_by_public_quotes(
        ["000001.SZ"], repo, trade_date=date(2026, 7, 20),
    )
    assert result["rows"] == 0
    assert flushed == []


def test_reference_derived_dates_never_fail_open(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    monkeypatch.setattr(kline_sync, "usable_daily_partition_dates", _prefs_boom)
    assert list_partition_dates(tmp_path, "kline_daily") == []


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"


def test_untagged_leftover_still_serves_latest(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df())
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    repo = KlineRepository(DataStore(tmp_path))
    df, latest = repo.get_enriched_latest()
    assert latest == date(2026, 7, 17)
    assert not df.is_empty()
    assert ScreenerService(repo).latest_date() == date(2026, 7, 17)
    daily = repo.get_daily("000001.SZ", date(2026, 7, 17), date(2026, 7, 17))
    assert not daily.is_empty()


def test_daily_prefs_unreadable_stays_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df())
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert _has_official_enriched(repo, date(2026, 7, 17)) is False
    assert list_partition_dates(tmp_path, "kline_daily_enriched") == []
    assert load_official_trend_overlay(tmp_path, date(2026, 7, 17)) == {}
    result = kline_sync.sync_daily_by_public_quotes(
        ["000001.SZ"], SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path)),
        trade_date=date(2026, 7, 20),
    )
    assert result["rows"] == 0
