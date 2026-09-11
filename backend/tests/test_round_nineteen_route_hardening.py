"""Nineteenth-round leftover mix-source / fail-open paths.

Closes remaining except-fallback leftover globs and leftover-shadowed
reads that round 18 left on the calendar / view / loader side:
- auction / dragon-tiger calendars no longer leftover-glob on probe error
- auction enrich skips leftover TickFlow closes under a custom daily
- scan_usable_daily / partition paths fail-closed when the probe throws
- chips loader does not let leftover enriched shadow custom daily
- screener warmup history stays on the current route
- integrity prune does not wipe leftover TickFlow during a custom repair
- repo latest/earliest dates and mining/regime calendars use safe dates
- DuckDB re-gate failure empties leftover-visible SQL instead of leaving
  the first-pass ungated view

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

from app.jobs import daily_pipeline
from app.services import auction_benchmark, dragon_tiger, kline_sync
from app.services.data_integrity import prune_enriched_partitions
from app.services.free_sources.kline_loader import load_daily_bars_for_symbol
from app.services.mining_preflight import enriched_partition_dates
from app.services.quote_service import QuoteService
from app.services.regime_builder import enriched_date_set
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


def test_auction_dragon_calendars_never_fail_open(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(kline_sync, "usable_daily_partition_dates", _prefs_boom)
    assert auction_benchmark._local_trading_days(tmp_path) == []
    assert dragon_tiger._local_trading_days(tmp_path) == []


def test_auction_enrich_skips_leftover_under_custom(monkeypatch, tmp_path):
    leftover = pl.DataFrame({
        "symbol": ["600519.SH"],
        "open": [10.0],
        "close": [11.0],
        "route": ["tickflow"],
    })
    custom = pl.DataFrame({
        "symbol": ["600519.SH"],
        "open": [10.0],
        "close": [10.5],
        "route": ["fuyao"],
        "date": [date(2026, 7, 16)],
    })
    _write_part(tmp_path, "kline_daily", "2026-07-17", leftover)
    _write_part(tmp_path, "kline_daily", "2026-07-16", custom)
    _patch_custom_daily(monkeypatch)
    items = [{"thscode": "600519.SH", "ticker": "600519", "name": "茅台", "auction_pct": 1.0}]
    leftover_day = auction_benchmark._enrich(tmp_path, date(2026, 7, 17), items)
    assert leftover_day[0]["day0_oc"] is None
    custom_day = auction_benchmark._enrich(tmp_path, date(2026, 7, 16), items)
    assert custom_day[0]["day0_oc"] == pytest.approx(0.05)


def test_auction_enrich_keeps_untagged_leftover_tickflow(monkeypatch, tmp_path):
    _write_part(
        tmp_path,
        "kline_daily",
        "2026-07-17",
        pl.DataFrame({"symbol": ["600519.SH"], "open": [10.0], "close": [11.0]}),
    )
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    items = [{"thscode": "600519.SH", "ticker": "600519", "name": "茅台"}]
    out = auction_benchmark._enrich(tmp_path, date(2026, 7, 17), items)
    assert out[0]["day0_oc"] == pytest.approx(0.1)


def test_scan_usable_daily_never_fail_open(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df())
    monkeypatch.setattr(kline_sync, "usable_daily_partition_dates", _prefs_boom)
    assert kline_sync.usable_daily_partition_paths(tmp_path, table="kline_daily_enriched") == []
    assert kline_sync.scan_usable_daily(tmp_path, table="kline_daily_enriched") is None


def test_kline_loader_prefers_custom_daily_over_leftover_enriched(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _write_part(
        tmp_path,
        "kline_daily",
        "2026-07-16",
        _daily_df(route="fuyao", day=date(2026, 7, 16)),
    )
    _patch_custom_daily(monkeypatch)
    rows = load_daily_bars_for_symbol(tmp_path, "000001.SZ", days=10)
    assert [str(r["date"])[:10] for r in rows] == ["2026-07-16"]


def test_kline_loader_leftover_only_still_raises_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    with pytest.raises((FileNotFoundError, ValueError)):
        load_daily_bars_for_symbol(tmp_path, "000001.SZ", days=10)


def test_screener_warmup_skips_leftover_under_custom(monkeypatch, tmp_path):
    for day in (date(2026, 7, 13), date(2026, 7, 14), date(2026, 7, 15), date(2026, 7, 16)):
        leftover = _daily_df(route="tickflow", day=day).with_columns(pl.lit(999.0).alias("close"))
        _write_part(tmp_path, "kline_daily_enriched", day.isoformat(), leftover)
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-17",
        _daily_df(route="fuyao").with_columns(pl.lit(10.0).alias("close")),
    )
    _patch_custom_daily(monkeypatch)
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        get_enriched_latest=lambda: (None, None),
        get_enriched_history=lambda *_a, **_k: None,
        get_instruments=lambda: pl.DataFrame(),
    )
    out = ScreenerService(repo)._load_enriched_for_date(date(2026, 7, 17))
    assert not out.is_empty()
    assert float(out["close"][0]) == pytest.approx(10.0)
    if "ma5" in out.columns:
        ma5 = out["ma5"][0]
        assert ma5 is None or float(ma5) < 50.0


def test_integrity_prune_skips_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-16",
        _daily_df(route="fuyao", day=date(2026, 7, 16)),
    )
    _patch_custom_daily(monkeypatch)
    removed = prune_enriched_partitions(tmp_path, date(2026, 7, 16))
    assert removed == 1
    assert (tmp_path / "kline_daily_enriched" / "date=2026-07-17" / "part.parquet").exists()
    assert not (tmp_path / "kline_daily_enriched" / "date=2026-07-16").exists()


def test_repo_dates_never_fail_open(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df())
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df())
    monkeypatch.setattr(kline_sync, "usable_daily_partition_dates", _prefs_boom)
    monkeypatch.setattr(kline_sync, "usable_minute_partition_dates", _prefs_boom)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.latest_daily_date() is None
    assert repo.earliest_daily_date() is None
    assert repo.latest_enriched_date("stock") is None
    assert repo.latest_minute_date_global() is None
    assert repo.earliest_minute_date() is None


def test_mining_and_regime_calendars_never_fail_open(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(kline_sync, "usable_daily_partition_dates", _prefs_boom)
    assert enriched_partition_dates(tmp_path, "stock") == []
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert enriched_date_set(repo) == set()


def test_regate_failure_empties_leftover_sql(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.db.execute("SELECT count(*) FROM kline_daily").fetchone()[0] == 0
    d = tmp_path.as_posix()
    repo.db.execute(
        f"CREATE OR REPLACE VIEW kline_daily AS "
        f"SELECT * FROM read_parquet('{d}/kline_daily/**/*.parquet', union_by_name=true)"
    )
    assert repo.db.execute("SELECT count(*) FROM kline_daily").fetchone()[0] == 1
    monkeypatch.setattr(
        repo.store,
        "_register_gated_catalog_views",
        _prefs_boom,
    )
    repo.store.re_gate_catalog_views()
    assert repo.db.execute("SELECT count(*) FROM kline_daily").fetchone()[0] == 0


def test_refresh_daily_view_empties_leftover_on_gate_boom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    monkeypatch.setattr(repo.store, "_register_gated_catalog_views", _prefs_boom)
    kline_sync._refresh_daily_view(repo)
    assert repo.db.execute("SELECT count(*) FROM kline_daily").fetchone()[0] == 0


def test_pipeline_refresh_empties_leftover_on_gate_boom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    monkeypatch.setattr(repo.store, "_register_gated_catalog_views", _prefs_boom)
    daily_pipeline._refresh_single_view(repo, "kline_daily")
    assert repo.db.execute("SELECT count(*) FROM kline_daily").fetchone()[0] == 0


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"


def test_daily_prefs_unreadable_stays_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df())
    assert kline_sync.scan_usable_daily(tmp_path, table="kline_daily_enriched") is None
    assert kline_sync.filter_daily_cache(_daily_df()).is_empty()
    assert auction_benchmark._local_trading_days(tmp_path) == []
    with pytest.raises((FileNotFoundError, ValueError)):
        load_daily_bars_for_symbol(tmp_path, "000001.SZ", days=10)
