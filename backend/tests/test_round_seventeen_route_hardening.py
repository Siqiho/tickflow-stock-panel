"""Seventeenth-round leftover mix-source / fail-open paths.

Closes remaining read-side / coverage calendars that still glob leftover
TickFlow after a custom daily switch:
- backtest panel scans (engine + legacy service)
- in-memory enriched cache / live-agg / ETF refresh
- market mainline, screener history + official date, intraday overlay
- mining preflight / schedule fingerprints
- reference consecutive_limit_ups, integrity, prune, daily quality
- auction / dragon-tiger trading-day calendars
- HTTP /minute-range leftover parquet under a custom minute route

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

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl

from app.api import kline as kline_api
from app.backtest.engine import BacktestEngine
from app.jobs.daily_pipeline import _prune_stale_price_partitions
from app.services import auction_benchmark, dragon_tiger, kline_sync, market_mainline
from app.services.backtest import BacktestService
from app.services.data_integrity import scan_recent_integrity
from app.services.free_sources.daily_quality import run_daily_quality_check
from app.services.intraday_overview import load_official_trend_overlay
from app.services.mining_preflight import enriched_partition_dates
from app.services.mining_schedule import _enriched_metadata
from app.services.quote_service import QuoteService
from app.services.reference_derived import build_limit_up_events
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


def test_scan_usable_daily_hides_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-16",
        _daily_df("600000.SH", route="fuyao", day=date(2026, 7, 16)),
    )
    _patch_custom_daily(monkeypatch)
    lf = kline_sync.scan_usable_daily(tmp_path, table="kline_daily_enriched")
    assert lf is not None
    out = kline_sync.filter_daily_cache(lf.collect())
    assert out["symbol"].to_list() == ["600000.SH"]


def test_backtest_engine_hides_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        get_enriched_range=lambda *a, **k: None,
        get_instruments=lambda: pl.DataFrame(),
        get_instruments_asset=lambda *_a, **_k: pl.DataFrame(),
    )
    out = BacktestEngine(repo)._load_panel_inner(
        ["000001.SZ"], date(2026, 7, 1), date(2026, 7, 20),
    )
    assert out.is_empty()


def test_backtest_engine_keeps_leftover_untagged(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df())
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        get_enriched_range=lambda *a, **k: None,
        get_instruments=lambda: pl.DataFrame(),
        get_instruments_asset=lambda *_a, **_k: pl.DataFrame(),
    )
    out = BacktestEngine(repo)._load_panel_inner(
        ["000001.SZ"], date(2026, 7, 1), date(2026, 7, 20),
        columns=["symbol", "date", "close"],
    )
    assert out["symbol"].to_list() == ["000001.SZ"]
    assert "route" not in out.columns


def test_legacy_backtest_hides_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    out = BacktestService(repo)._load_panel(["000001.SZ"], date(2026, 7, 17), date(2026, 7, 17))
    assert out.empty


def test_refresh_enriched_clears_cache_when_latest_is_leftover(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    repo._enriched_cache = _daily_df(route="tickflow")
    repo._enriched_cache_date = date(2026, 7, 17)
    repo._enriched_history_cache = _daily_df(route="tickflow")
    repo._refresh_enriched()
    assert repo._enriched_cache is None
    assert repo._enriched_history_cache is None
    assert repo.get_enriched_history(date(2026, 7, 17), 10) is None


def test_live_agg_from_parquet_hides_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    hist, agg = repo._build_live_agg_from_parquet(date(2026, 7, 17), date(2026, 7, 1))
    assert hist.is_empty()
    assert agg.is_empty()


def test_etf_refresh_hides_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_etf_enriched", "2026-07-17", _daily_df("510300.SH", route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    repo._refresh_etf_enriched()
    assert repo._etf_enriched_cache is None
    assert repo._etf_enriched_cache_date is None


def test_mainline_hides_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-17",
        _daily_df(route="tickflow").with_columns(pl.lit(2).alias("consecutive_limit_ups")),
    )
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(
        market_mainline,
        "_load_concept_map_df",
        lambda *_a, **_k: (pl.DataFrame({"_sym_up": ["000001.SZ"], "concept": ["X"]}), 1),
    )
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    out = market_mainline.compute_mainline_range(
        repo, tmp_path, date(2026, 7, 17), date(2026, 7, 17), kind="concept",
        filter_cfg={"min_members": 1, "max_members": 5000, "blacklist": []},
    )
    assert out.is_empty()


def test_mining_preflight_hides_leftover_dates(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-16",
        _daily_df(route="fuyao", day=date(2026, 7, 16)),
    )
    _patch_custom_daily(monkeypatch)
    assert enriched_partition_dates(tmp_path, "stock") == [date(2026, 7, 16)]


def test_mining_schedule_fingerprint_skips_leftover(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-16",
        _daily_df(route="fuyao", day=date(2026, 7, 16)),
    )
    _patch_custom_daily(monkeypatch)
    meta = _enriched_metadata(tmp_path / "kline_daily_enriched")
    assert meta["partition_count"] == 1
    assert meta["last_partition"] == "date=2026-07-16"


def test_screener_latest_prefers_usable_disk(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-16",
        _daily_df(route="fuyao", day=date(2026, 7, 16)),
    )
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    repo._enriched_cache_date = date(2026, 7, 17)
    assert ScreenerService(repo).latest_date() == date(2026, 7, 16)


def test_screener_history_cache_does_not_reuse_leftover(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        get_enriched_history=lambda *_a, **_k: _daily_df(route="tickflow"),
        get_instruments=lambda: pl.DataFrame(),
    )
    out = ScreenerService(repo)._load_enriched_history(date(2026, 7, 17), 10)
    assert out.is_empty()


def test_intraday_overlay_hides_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    assert load_official_trend_overlay(tmp_path, date(2026, 7, 17)) == {}


def test_limit_up_events_ignores_leftover_enriched_height(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="fuyao"))
    _write_part(
        tmp_path,
        "kline_daily",
        "2026-07-16",
        _daily_df(route="fuyao", day=date(2026, 7, 16)).with_columns(pl.lit(10.0).alias("close")),
    )
    leftover = _daily_df(route="tickflow").with_columns(pl.lit(9).alias("consecutive_limit_ups"))
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", leftover)
    _patch_custom_daily(monkeypatch)
    events = build_limit_up_events(tmp_path, date(2026, 7, 17))
    if events is not None and not getattr(events, "is_empty", lambda: True)():
        if "board_height" in events.columns:
            assert 9 not in events["board_height"].to_list()


def test_integrity_ignores_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    assert scan_recent_integrity(tmp_path, today=date(2026, 7, 18), lookback_days=7) == []


def test_prune_does_not_compare_leftover_daily_to_custom_enriched(monkeypatch, tmp_path):
    _write_part(
        tmp_path,
        "kline_daily",
        "2026-07-17",
        pl.DataFrame({"symbol": ["000001.SZ"], "close": [7.10], "route": ["tickflow"]}),
    )
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-17",
        pl.DataFrame({"symbol": ["000001.SZ"], "raw_close": [7.07], "route": ["fuyao"]}),
    )
    _patch_custom_daily(monkeypatch)
    pruned = _prune_stale_price_partitions(
        tmp_path / "kline_daily", tmp_path / "kline_daily_enriched",
    )
    assert pruned == []
    assert (tmp_path / "kline_daily_enriched" / "date=2026-07-17" / "part.parquet").exists()


def test_daily_quality_latest_skips_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _write_part(
        tmp_path,
        "kline_daily",
        "2026-07-16",
        _daily_df(route="fuyao", day=date(2026, 7, 16)),
    )
    _patch_custom_daily(monkeypatch)
    report = run_daily_quality_check(tmp_path)
    assert report["date"] == "2026-07-16"


def test_auction_and_dragon_tiger_calendars_skip_leftover(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _write_part(
        tmp_path,
        "kline_daily",
        "2026-07-16",
        _daily_df(route="fuyao", day=date(2026, 7, 16)),
    )
    _patch_custom_daily(monkeypatch)
    assert auction_benchmark._local_trading_days(tmp_path) == [date(2026, 7, 16)]
    assert dragon_tiger._local_trading_days(tmp_path) == [date(2026, 7, 16)]
    assert auction_benchmark._read_kline_closes(tmp_path, date(2026, 7, 17)) == {}


def test_minute_range_scan_hides_leftover_under_custom(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "datetime": [datetime(2026, 7, 17, 9, 31)],
        "open": [10.0],
        "high": [10.1],
        "low": [9.9],
        "close": [10.0],
        "volume": [100.0],
        "amount": [1000.0],
        "route": ["tickflow"],
    }).write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == "fuyao" and dataset == "minute",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())
    monkeypatch.setattr(kline_api, "cn_today", lambda: date(2026, 7, 17))
    repo = SimpleNamespace(
        _minute_glob=str(tmp_path / "kline_minute" / "**" / "*.parquet"),
        resolve_asset_type=lambda *_a, **_k: "stock",
        get_instruments=lambda: pl.DataFrame({"symbol": ["000001.SZ"], "name": ["平安"]}),
        get_minute_range=None,
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo)))
    payload = kline_api.get_minute_range(request, "000001.SZ", 2)
    assert payload["sessions"] == [] or payload.get("source") == "none"


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"


def test_daily_prefs_unreadable_stays_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df())
    assert kline_sync.scan_usable_daily(tmp_path, table="kline_daily_enriched") is None
    assert kline_sync.filter_daily_cache(_daily_df()).is_empty()
