"""Twenty-sixth-round leftover mix-source / fail-open paths.

Closes remaining except-fallback leftover extras and leftover-unioned
reads that round 25 left on the integrity / quality / prune / ext-view /
provider-switch side:
- integrity quote_ts / snapshot scans skip leftover extras in a current date
- daily quality concat skips leftover extras before metrics
- prune row counts skip leftover extras
- overview / RPS / watchlist ext timeseries use latest date=* only
- settings provider switch re-gates DuckDB and drops process caches

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

from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl

from app.api import overview as overview_api
from app.api import settings as settings_api
from app.api.watchlist import _read_ext_for_watchlist
from app.jobs.daily_pipeline import _partition_row_count
from app.market_time import CN_TZ
from app.services import kline_sync
from app.services.data_integrity import _quote_ts_max_ms, scan_recent_integrity
from app.services.ext_data import ExtConfig, ExtField, latest_ext_parquet_files
from app.services.free_sources.daily_quality import run_daily_quality_check
from app.services.market_overview_builder import _ext_files, _read_ext_rows
from app.services.quote_service import QuoteService


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
        "change_pct": [0.01],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _write_part(root, table: str, day: str, df: pl.DataFrame, name: str = "part.parquet") -> None:
    part = root / table / f"date={day}"
    part.mkdir(parents=True, exist_ok=True)
    df.write_parquet(part / name)


def _ts_ms(day: date, t: time) -> int:
    return int(datetime.combine(day, t, tzinfo=CN_TZ).timestamp() * 1000)


def test_usable_files_skip_leftover_extras(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df(route="fuyao").write_parquet(part / "part.parquet")
    leftover = _daily_df(route="tickflow").with_columns(pl.lit(999.0).alias("close"))
    leftover.write_parquet(part / "leftover.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    files = kline_sync.usable_daily_partition_files(part)
    assert [path.name for path in files] == ["part.parquet"]
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    leftover_only = kline_sync.usable_daily_partition_files(part)
    assert [path.name for path in leftover_only] == ["leftover.parquet"]


def test_usable_files_never_fail_open(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", _prefs_boom)
    assert kline_sync.usable_daily_partition_files(part) == []


def test_integrity_quote_ts_skips_leftover_extras(monkeypatch, tmp_path):
    friday = date(2026, 8, 21)
    part = tmp_path / "kline_daily" / f"date={friday.isoformat()}"
    part.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "quote_ts": [None],
        "route": ["fuyao"],
    }).write_parquet(part / "part.parquet")
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "quote_ts": [_ts_ms(friday, time(11, 30))],
        "route": ["tickflow"],
    }).write_parquet(part / "leftover.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    assert _quote_ts_max_ms(part) is None


def test_integrity_scan_skips_leftover_snapshot_extras(monkeypatch, tmp_path):
    today = date(2026, 8, 24)
    friday = date(2026, 8, 21)
    part = tmp_path / "kline_daily" / f"date={friday.isoformat()}"
    part.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "date": [friday],
        "open": [10.0],
        "high": [10.1],
        "low": [9.9],
        "close": [10.0],
        "volume": [100.0],
        "amount": [1000.0],
        "quote_ts": [None],
        "route": ["fuyao"],
    }).write_parquet(part / "part.parquet")
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "date": [friday],
        "open": [10.0],
        "high": [10.1],
        "low": [9.9],
        "close": [10.0],
        "volume": [100.0],
        "amount": [1000.0],
        "quote_ts": [_ts_ms(friday, time(11, 30))],
        "route": ["tickflow"],
    }).write_parquet(part / "leftover.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    issues = scan_recent_integrity(tmp_path, today=today)
    assert not any(issue.table == "kline_daily" and issue.kind == "snapshot" for issue in issues)


def test_integrity_quote_ts_never_fail_open(monkeypatch, tmp_path):
    part = tmp_path / "date=2026-08-21"
    part.mkdir()
    pl.DataFrame({
        "symbol": ["a"],
        "quote_ts": [2000],
        "route": ["tickflow"],
    }).write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", _prefs_boom)
    assert _quote_ts_max_ms(part) is None


def test_quality_skips_leftover_extras(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df(route="fuyao").write_parquet(part / "part.parquet")
    leftover = _daily_df(route="tickflow").with_columns(pl.lit(-5.0).alias("volume"))
    leftover.write_parquet(part / "leftover.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    report = run_daily_quality_check(tmp_path, date="2026-07-17")
    assert report["ok"] is True
    assert "negative_volume" not in {issue["code"] for issue in report["issues"]}


def test_quality_leftover_only_is_unusable(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    report = run_daily_quality_check(tmp_path, date="2026-07-17")
    assert report["ok"] is False
    assert "unusable_route" in {issue["code"] for issue in report["issues"]}


def test_quality_never_fail_open(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    monkeypatch.setattr(kline_sync, "daily_route", _prefs_boom)
    report = run_daily_quality_check(tmp_path, date="2026-07-17")
    assert report["ok"] is False
    assert "unusable_route" in {issue["code"] for issue in report["issues"]}


def test_prune_row_count_skips_leftover_extras(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df(route="fuyao").write_parquet(part / "part.parquet")
    leftover = pl.concat([_daily_df(route="tickflow", symbol=f"00000{i}.SZ") for i in range(3)])
    leftover.write_parquet(part / "leftover.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    assert _partition_row_count(part) == 1


def test_prune_row_count_never_fail_open(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", _prefs_boom)
    assert _partition_row_count(part) is None


def _ext_config() -> ExtConfig:
    return ExtConfig(
        id="ext_demo",
        label="demo",
        mode="timeseries",
        fields=[ExtField(name="v", label="v", dtype="float")],
    )


def _write_ext_day(root, day: str, value: float) -> None:
    part = root / "ext_data" / "ext_demo" / "timeseries" / f"date={day}"
    part.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "date": [date.fromisoformat(day)],
        "v": [value],
        "所属概念": ["人工智能"],
    }).write_parquet(part / "part.parquet")


def test_latest_ext_files_skips_old_partitions(tmp_path):
    _write_ext_day(tmp_path, "2026-07-17", 1.0)
    _write_ext_day(tmp_path, "2026-07-18", 2.0)
    files = latest_ext_parquet_files(tmp_path, _ext_config())
    assert len(files) == 1
    assert "2026-07-18" in str(files[0])
    assert "2026-07-17" not in str(files[0])


def test_overview_ext_rows_use_latest_partition(tmp_path):
    _write_ext_day(tmp_path, "2026-07-17", 1.0)
    _write_ext_day(tmp_path, "2026-07-18", 2.0)
    config = _ext_config()
    globs = _ext_files(tmp_path, config)
    assert len(globs) == 1
    assert "2026-07-18" in globs[0]
    rows = _read_ext_rows(tmp_path, config, "所属概念")
    assert rows == [{"所属概念": "人工智能", "symbol": "000001.SZ"}]


def test_overview_api_ext_files_latest_only(tmp_path):
    _write_ext_day(tmp_path, "2026-07-17", 1.0)
    _write_ext_day(tmp_path, "2026-07-18", 2.0)
    globs = overview_api._ext_files(tmp_path, _ext_config())
    assert len(globs) == 1
    assert "2026-07-18" in globs[0]
    assert "2026-07-17" not in globs[0]


def test_watchlist_ext_skips_old_partitions(tmp_path):
    _write_ext_day(tmp_path, "2026-07-17", 1.0)
    _write_ext_day(tmp_path, "2026-07-18", 2.0)
    out = _read_ext_for_watchlist(_ext_config(), tmp_path, ["000001.SZ"])
    assert out["v"].to_list() == [2.0]


def test_refresh_route_surfaces_regates_and_clears(monkeypatch, tmp_path):
    calls: list[str] = []
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        clear_cache=lambda: calls.append("clear"),
    )
    monkeypatch.setattr(kline_sync, "refresh_gated_catalog_views", lambda _repo: calls.append("gate"))
    monkeypatch.setattr("app.api.data.invalidate_data_cache", lambda table=None: calls.append("data"))
    monkeypatch.setattr("app.api.overview.invalidate_overview_cache", lambda: calls.append("overview"))
    monkeypatch.setattr("app.api.regime.invalidate_regime_cache", lambda: calls.append("regime"))
    kline_sync.refresh_route_surfaces(repo)
    assert calls[:2] == ["gate", "clear"]
    assert "data" in calls
    assert "overview" in calls
    assert "regime" in calls


def test_refresh_route_surfaces_fail_closed(monkeypatch, tmp_path):
    closed: list[str] = []
    store = SimpleNamespace(_fail_closed_route_views=lambda: closed.append("empty"))
    repo = SimpleNamespace(store=store, clear_cache=lambda: None)

    def _boom(_repo):
        raise RuntimeError("gate failed")

    monkeypatch.setattr(kline_sync, "refresh_gated_catalog_views", _boom)
    kline_sync.refresh_route_surfaces(repo)
    assert closed == ["empty"]


def test_update_data_providers_refreshes_surfaces(monkeypatch):
    calls: list[object] = []
    monkeypatch.setattr("app.services.preferences.save_server", lambda upd: None)
    monkeypatch.setattr(settings_api, "detect_capabilities", lambda: SimpleNamespace())
    monkeypatch.setattr(
        settings_api,
        "_refresh_route_surfaces",
        lambda request=None: calls.append(request),
    )
    mock_request = MagicMock()
    settings_api.update_data_providers(
        MagicMock(model_dump=lambda exclude_none: {"daily_data_provider": "fuyao"}),
        mock_request,
    )
    assert calls == [mock_request]


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"


def test_untagged_leftover_still_counts_for_tickflow(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df().write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    assert _partition_row_count(part) == 1
    report = run_daily_quality_check(tmp_path, date="2026-07-17")
    assert report["date"] == "2026-07-17"
    assert report["metrics"]["rows"] == 1
