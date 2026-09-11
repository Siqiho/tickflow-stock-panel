"""Eighteenth-round leftover mix-source / fail-open paths.

Closes remaining fail-open except fallbacks and leftover coverage calendars
that round 17 left on the write/status/matrix side:
- market overview / daily quality / integrity no longer glob leftover on error
- pipeline incremental / partial prune / index+ETF start / minute cover
- extend-history and rebuild-enriched day counts
- backtest matrix bounds / fingerprints / dataset
- regime stale detection, RPS as_of, enriched lineage reconcile
- index/ETF status calendars

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
import pytest

from app.api import data as data_api
from app.backtest import matrix as matrix_mod
from app.indicators.pipeline import _reconcile_enriched_lineage
from app.jobs import daily_pipeline
from app.services import kline_sync
from app.services.data_integrity import scan_recent_integrity
from app.services.free_sources.daily_quality import _latest_partition_date
from app.services.market_overview_builder import latest_official_enriched_date
from app.services.quote_service import QuoteService
from app.services.regime_builder import detect_stale_dates
from app.services.rps_rotation import _latest_enriched_date
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


def test_safe_usable_daily_dates_never_fail_open(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df())
    monkeypatch.setattr(kline_sync, "usable_daily_partition_dates", _prefs_boom)
    assert kline_sync.safe_usable_daily_partition_dates(tmp_path) == []


def test_overview_latest_does_not_glob_leftover_on_error(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(kline_sync, "usable_daily_partition_dates", _prefs_boom)
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert latest_official_enriched_date(repo) is None


def test_daily_quality_latest_does_not_glob_leftover_on_error(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(kline_sync, "usable_daily_partition_dates", _prefs_boom)
    assert _latest_partition_date(tmp_path / "kline_daily") is None


def test_integrity_does_not_glob_leftover_on_error(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(kline_sync, "usable_daily_partition_dates", _prefs_boom)
    assert scan_recent_integrity(tmp_path, today=date(2026, 7, 18), lookback_days=7) == []


def test_pipeline_calendars_hide_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _write_part(
        tmp_path,
        "kline_daily",
        "2026-07-16",
        _daily_df(route="fuyao", day=date(2026, 7, 16)),
    )
    _patch_custom_daily(monkeypatch)
    daily, enriched = daily_pipeline._coverage_calendars(tmp_path)
    assert daily == [date(2026, 7, 16)]
    assert enriched == []


def test_pipeline_calendars_keep_untagged_leftover_tickflow(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df())
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    daily, _enriched = daily_pipeline._coverage_calendars(tmp_path)
    assert daily == [date(2026, 7, 17)]


def test_prune_partial_does_not_delete_custom_vs_leftover_daily(monkeypatch, tmp_path):
    leftover_daily = pl.DataFrame({
        "symbol": ["000001.SZ", "000002.SZ"],
        "close": [10.0, 11.0],
        "route": ["tickflow", "tickflow"],
    })
    custom_enr = pl.DataFrame({
        "symbol": ["000001.SZ"],
        "raw_close": [10.0],
        "route": ["fuyao"],
    })
    _write_part(tmp_path, "kline_daily", "2026-07-17", leftover_daily)
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", custom_enr)
    _patch_custom_daily(monkeypatch)
    pruned = daily_pipeline._prune_partial_enriched_partitions(
        tmp_path / "kline_daily", tmp_path / "kline_daily_enriched",
    )
    assert pruned == []
    assert (tmp_path / "kline_daily_enriched" / "date=2026-07-17" / "part.parquet").exists()


def test_index_etf_calendars_skip_leftover(monkeypatch, tmp_path):
    _write_part(
        tmp_path,
        "kline_index_enriched",
        "2026-07-17",
        _daily_df("000001.SH", route="tickflow"),
    )
    _write_part(
        tmp_path,
        "kline_etf_enriched",
        "2026-07-17",
        _daily_df("510300.SH", route="tickflow"),
    )
    _write_part(
        tmp_path,
        "kline_index_enriched",
        "2026-07-16",
        _daily_df("000001.SH", route="fuyao", day=date(2026, 7, 16)),
    )
    _patch_custom_daily(monkeypatch)
    assert daily_pipeline._usable_partition_dates(tmp_path, "kline_index_enriched") == [
        date(2026, 7, 16),
    ]
    assert daily_pipeline._usable_partition_dates(tmp_path, "kline_etf_enriched") == []


def test_minute_cover_skips_leftover_under_custom(monkeypatch, tmp_path):
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
    assert kline_sync.safe_usable_minute_partition_dates(tmp_path) == []


def test_status_index_hides_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_index_daily", "2026-07-17", _daily_df("000001.SH", route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        execute_one=MagicMock(side_effect=RuntimeError("ungated view")),
        execute_all=MagicMock(side_effect=RuntimeError("no describe")),
    )
    assert data_api._safe_aggregate_index_daily(repo) is None
    assert data_api._safe_aggregate_index_enriched(repo) is None
    assert data_api._safe_aggregate_etf_daily(repo) is None
    assert data_api._safe_aggregate_etf_enriched(repo) is None


def test_matrix_bounds_hide_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-16",
        _daily_df(route="fuyao", day=date(2026, 7, 16)),
    )
    _patch_custom_daily(monkeypatch)
    root = tmp_path / "kline_daily_enriched"
    assert matrix_mod._partition_date_bounds(root) == (date(2026, 7, 16), date(2026, 7, 16))
    prints = matrix_mod._partition_fingerprints(root, date(2026, 7, 1), date(2026, 7, 20))
    assert list(prints) == ["2026-07-16"]


def test_matrix_load_hides_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    with pytest.raises(ValueError, match="本地指标数据为空"):
        matrix_mod.load_market_data_matrix_from_parquet(
            tmp_path / "kline_daily_enriched",
            date(2026, 7, 1),
            date(2026, 7, 20),
            field_columns=set(),
        )


def test_matrix_keeps_untagged_leftover_tickflow(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df())
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    root = tmp_path / "kline_daily_enriched"
    assert matrix_mod._partition_date_bounds(root) == (date(2026, 7, 17), date(2026, 7, 17))


def test_regime_stale_skips_leftover_under_custom(monkeypatch, tmp_path):
    from app.services import regime_builder

    regime_builder.upsert_regime_history(tmp_path, pl.DataFrame({
        "date": [date(2026, 7, 17)],
        "state": ["range"],
        "score": [50],
    }))
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert detect_stale_dates(tmp_path, repo) == []


def test_rps_latest_skips_leftover_cache(monkeypatch, tmp_path):
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-16",
        _daily_df(route="fuyao", day=date(2026, 7, 16)),
    )
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    repo._enriched_history_cache = _daily_df(route="tickflow")
    assert _latest_enriched_date(repo) == date(2026, 7, 16)


def test_lineage_reconcile_skips_leftover(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    reconciled, unread = _reconcile_enriched_lineage(
        tmp_path,
        tmp_path / "kline_daily_enriched",
        scope="ALL",
        strict_unreadable=False,
    )
    assert reconciled == 0
    assert not (tmp_path / "lineage").exists() or unread == set()


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"


def test_daily_prefs_unreadable_stays_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df())
    assert kline_sync.safe_usable_daily_partition_dates(
        tmp_path, table="kline_daily_enriched",
    ) == []
    assert daily_pipeline._coverage_calendars(tmp_path) == ([], [])
    assert kline_sync.filter_daily_cache(_daily_df()).is_empty()
