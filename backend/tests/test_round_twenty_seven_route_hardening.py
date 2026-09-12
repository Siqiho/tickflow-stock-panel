"""Twenty-seventh-round leftover mix-source / fail-open paths.

Closes remaining extras-blind calendars / paths and leftover caches that
round 26 left after it gated integrity / quality / prune extras:
- daily / minute dates see current extras behind leftover part.parquet
- daily / minute paths never take leftover extras[0]
- readers (screener / overview / overlay / prune / pipeline / mining /
  regime / quality / financial / depth / quote_snapshot) skip leftover extras
- strategy cache is stamped by daily route and dropped on provider switch

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

import polars as pl

from app.jobs.daily_pipeline import _prune_partial_enriched_partitions
from app.services import kline_sync, strategy_cache
from app.services.data_integrity import prune_enriched_partitions
from app.services.depth_service import DepthService
from app.services.financial_sync import get_financial_df
from app.services.free_sources.daily_quality import run_daily_quality_check
from app.services.intraday_overview import load_official_trend_overlay
from app.services.market_overview_builder import (
    _has_official_enriched,
    latest_quote_snapshot_date,
)
from app.services.mining_schedule import _enriched_metadata
from app.services.quote_service import QuoteService, usable_quote_snapshot_files
from app.services.reference_derived import _read_usable_daily
from app.services.regime_builder import detect_stale_dates
from app.services.screener import ScreenerService


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


def _write_part(root, table: str, day: str, df: pl.DataFrame, name: str = "part.parquet") -> None:
    part = root / table / f"date={day}"
    part.mkdir(parents=True, exist_ok=True)
    df.write_parquet(part / name)


def test_daily_dates_see_current_extras_behind_leftover_part(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(part / "part.parquet")
    _daily_df(route="fuyao").write_parquet(part / "current.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    assert kline_sync.usable_daily_partition_dates(tmp_path) == [date(2026, 7, 17)]
    paths = kline_sync.usable_daily_partition_paths(tmp_path)
    assert [path.name for path in paths] == ["current.parquet"]
    frame = kline_sync.read_usable_daily_partition(part)
    assert frame["route"].to_list() == ["fuyao"]


def test_daily_paths_never_take_leftover_extras(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    leftover = _daily_df(route="tickflow").with_columns(pl.lit(1.0).alias("close"))
    leftover.write_parquet(part / "aaa.parquet")
    _daily_df(route="fuyao").write_parquet(part / "zzz.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    assert [path.name for path in kline_sync.usable_daily_partition_paths(tmp_path)] == [
        "zzz.parquet",
    ]


def test_daily_dates_and_paths_never_fail_open(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", _prefs_boom)
    assert kline_sync.safe_usable_daily_partition_dates(tmp_path) == []
    assert kline_sync.usable_daily_partition_paths(tmp_path) == []
    assert kline_sync.read_usable_daily_partition(part).is_empty()


def test_minute_dates_see_current_extras_behind_leftover_part(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    _minute_df(route="tickflow", ts=datetime(2026, 7, 17, 9, 30)).write_parquet(part / "part.parquet")
    current_ts = datetime(2026, 7, 17, 14, 55)
    _minute_df(route="fuyao", ts=current_ts).write_parquet(part / "current.parquet")
    monkeypatch.setattr(kline_sync, "minute_route", lambda: "fuyao")
    assert kline_sync.usable_minute_partition_dates(tmp_path) == [date(2026, 7, 17)]
    assert [path.name for path in kline_sync.usable_minute_partition_paths(tmp_path)] == [
        "current.parquet",
    ]
    assert kline_sync.latest_usable_minute_datetime(tmp_path) == current_ts


def test_minute_files_never_fail_open(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    _minute_df(route="tickflow").write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync, "minute_route", _prefs_boom)
    assert kline_sync.usable_minute_partition_files(part) == []
    assert kline_sync.usable_minute_partition_paths(tmp_path) == []


def test_screener_loads_current_extras_not_leftover_part(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily_enriched" / "date=2026-07-17"
    part.mkdir(parents=True)
    leftover = _daily_df(route="tickflow").with_columns(pl.lit(1.0).alias("close"))
    leftover.write_parquet(part / "part.parquet")
    _daily_df(route="fuyao").write_parquet(part / "current.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        get_enriched_history=lambda *_a, **_k: None,
        get_instruments=lambda: pl.DataFrame(),
    )
    service = ScreenerService(repo)
    service._compute_enriched_full = lambda df, _day: df
    out = service._load_enriched_for_date(date(2026, 7, 17))
    assert out["close"].to_list() == [10.1]


def test_overview_official_and_reference_see_current_extras(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(part / "part.parquet")
    _daily_df(route="fuyao").write_parquet(part / "current.parquet")
    enr = tmp_path / "kline_daily_enriched" / "date=2026-07-17"
    enr.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(enr / "part.parquet")
    _daily_df(route="fuyao").write_parquet(enr / "current.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert _has_official_enriched(repo, date(2026, 7, 17)) is True
    frame = _read_usable_daily(tmp_path, date(2026, 7, 17))
    assert frame["route"].to_list() == ["fuyao"]


def test_overlay_and_quality_skip_leftover_extras(monkeypatch, tmp_path):
    day = date(2026, 7, 17)
    enr = tmp_path / "kline_daily_enriched" / f"date={day.isoformat()}"
    enr.mkdir(parents=True)
    leftover = _daily_df(route="tickflow").with_columns(
        pl.lit(1.0).alias("close"),
        pl.lit(999.0).alias("turnover_rate"),
        pl.lit(9).alias("consecutive_limit_ups"),
    )
    leftover.write_parquet(enr / "part.parquet")
    current = _daily_df(route="fuyao").with_columns(
        pl.lit(0.0).alias("turnover_rate"),
        pl.lit(0).alias("consecutive_limit_ups"),
    )
    current.write_parquet(enr / "current.parquet")
    _write_part(tmp_path, "kline_daily", day.isoformat(), _daily_df(route="fuyao"))
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    overlay = load_official_trend_overlay(tmp_path, day)
    assert overlay["000001.SZ"]["consecutive_limit_ups"] == 0
    report = run_daily_quality_check(tmp_path, date=day.isoformat())
    assert report["metrics"].get("turnover_rate_over_100", 0) == 0


def test_prune_and_mining_see_current_extras(monkeypatch, tmp_path):
    daily = tmp_path / "kline_daily" / "date=2026-07-17"
    enr = tmp_path / "kline_daily_enriched" / "date=2026-07-17"
    daily.mkdir(parents=True)
    enr.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(daily / "part.parquet")
    _daily_df(route="fuyao").write_parquet(daily / "current.parquet")
    leftover = pl.concat([_daily_df(route="tickflow", symbol=f"00000{i}.SZ") for i in range(3)])
    leftover.write_parquet(enr / "part.parquet")
    _daily_df(route="fuyao").write_parquet(enr / "current.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    assert _prune_partial_enriched_partitions(
        tmp_path / "kline_daily", tmp_path / "kline_daily_enriched",
    ) == []
    assert (enr / "current.parquet").exists()
    removed = prune_enriched_partitions(tmp_path, date(2026, 7, 17))
    assert removed == 1
    assert not enr.exists()
    _daily_df(route="fuyao").write_parquet(
        (tmp_path / "kline_daily_enriched" / "date=2026-07-17") / "current.parquet"
    )
    meta = _enriched_metadata(tmp_path / "kline_daily_enriched")
    assert meta["partition_count"] == 1
    assert meta["last_partition"] == "date=2026-07-17"


def test_regime_stale_uses_current_extras(monkeypatch, tmp_path):
    enr = tmp_path / "kline_daily_enriched" / "date=2026-07-17"
    enr.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(enr / "part.parquet")
    current = enr / "current.parquet"
    _daily_df(route="fuyao").write_parquet(current)
    regime = tmp_path / "regime_history" / "part.parquet"
    regime.parent.mkdir(parents=True)
    pl.DataFrame({"date": [date(2026, 7, 17)], "phase": ["risk_on"], "route": ["fuyao"]}).write_parquet(regime)
    current.touch()
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    stale = detect_stale_dates(tmp_path, repo)
    assert stale == [date(2026, 7, 17)]


def test_financial_and_depth_skip_leftover_extras(monkeypatch, tmp_path):
    folder = tmp_path / "financials" / "income"
    folder.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "period_end": ["2026-03-31"], "route": ["tickflow"]}).write_parquet(
        folder / "part.parquet",
    )
    pl.DataFrame({"symbol": ["000001.SZ"], "period_end": ["2026-06-30"], "route": ["fuyao"]}).write_parquet(
        folder / "current.parquet",
    )
    monkeypatch.setattr("app.services.financial_sync.financial_write_route", lambda: "fuyao")
    frame = get_financial_df(tmp_path, "income")
    assert frame["period_end"].to_list() == ["2026-06-30"]

    sealed = tmp_path / "sealed_l1" / "date=2026-07-17"
    sealed.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "sealed_up": [True], "route": ["tickflow"]}).write_parquet(
        sealed / "part.parquet",
    )
    pl.DataFrame({"symbol": ["000001.SZ"], "sealed_up": [False], "route": ["fuyao"]}).write_parquet(
        sealed / "current.parquet",
    )
    monkeypatch.setattr("app.services.depth_service.depth_route", lambda: "fuyao")
    service = DepthService()
    service.set_repo(SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path)))
    out = service._sealed_df_for_read(date(2026, 7, 17))
    assert out["sealed_up"].to_list() == [False]


def test_quote_snapshot_extras_skip_leftover(monkeypatch, tmp_path):
    part = tmp_path / "quote_snapshot" / "asset_type=stock" / "date=2026-07-17"
    part.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "close": [1.0], "route": ["tickflow"]}).write_parquet(
        part / "part.parquet",
    )
    pl.DataFrame({"symbol": ["000001.SZ"], "close": [10.1], "route": ["fuyao"]}).write_parquet(
        part / "current.parquet",
    )
    monkeypatch.setattr("app.services.quote_service.realtime_route", lambda: "fuyao")
    files = usable_quote_snapshot_files(part)
    assert [path.name for path in files] == ["current.parquet"]
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert latest_quote_snapshot_date(repo) == date(2026, 7, 17)


def test_strategy_cache_skips_leftover_after_switch(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    strategy_cache.write_cache(tmp_path, "2026-07-17", {
        "s1": {"total": 1, "as_of": "2026-07-17", "rows": [{"symbol": "000001.SZ", "close": 1.0}]},
    })
    cached = strategy_cache.read_cache(tmp_path)
    assert cached["daily_route"] == "tickflow"
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    assert strategy_cache.read_cache(tmp_path) is None
    monkeypatch.setattr(kline_sync, "daily_route", _prefs_boom)
    assert strategy_cache.read_cache(tmp_path) is None


def test_strategy_cache_legacy_stays_leftover_tickflow(monkeypatch, tmp_path):
    path = strategy_cache._cache_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"as_of":"2026-07-17","results":{}}', encoding="utf-8")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    assert strategy_cache.read_cache(tmp_path)["as_of"] == "2026-07-17"
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    assert strategy_cache.read_cache(tmp_path) is None


def test_refresh_route_surfaces_clears_strategy_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    strategy_cache.write_cache(tmp_path, "2026-07-17", {
        "s1": {"total": 1, "as_of": "2026-07-17", "rows": []},
    })
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path), clear_cache=lambda: None)
    monkeypatch.setattr(kline_sync, "refresh_gated_catalog_views", lambda _repo: None)
    kline_sync.refresh_route_surfaces(repo)
    assert strategy_cache.read_cache(tmp_path) is None


def test_leftover_tickflow_still_sees_untagged_extras(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    assert kline_sync.usable_daily_partition_dates(tmp_path) == [date(2026, 7, 17)]
    assert kline_sync.read_usable_daily_partition(part)["close"].to_list() == [10.1]


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"
