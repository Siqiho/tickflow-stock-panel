"""Fifteenth-round leftover mix-source / fail-open paths.

Keeps prior TickFlow leftover contracts:
- leftover TickFlow + free realtime stays mode=none
- undeclared daily / minute / full_minute / adj still fall back to TickFlow
- leftover TickFlow + no ADJ cap still uses the public sina adapter
- leftover TickFlow adj reads may serve public-sina tags
- leftover TickFlow adj coverage / public sina writes stay for tickflow|public
- entitled TickFlow minute fallback after a custom *call* failure
- TickFlow default depth empty result may still use public L1
- leftover TickFlow depth reads may serve public-tagged sealed files
- leftover TickFlow single-symbol minute view may still use public / TDX
- A-share / index / ETF instruments stay TickFlow (no instrument_provider)
- Lab /api/free-ext public writes stay explicit public endpoints
- historical daily / enriched HTTP / screener reads stay until re-sync
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import polars as pl

from app.api import data as data_api
from app.indicators import pipeline
from app.services import kline_sync, preferences
from app.services.free_sources.adj_factor_public import merge_write_adj_factor
from app.services.free_sources.financials_public import merge_write_financial_table
from app.services.quote_service import QuoteService
from app.services.reference_derived import (
    _seal_fund_map,
    build_limit_up_events,
    build_valuation_daily,
    list_partition_dates,
)
from app.services.regime_builder import enriched_date_set
from app.tickflow.repository import DataStore, KlineRepository


def _prefs_boom(*_a, **_k):
    raise RuntimeError("prefs unreadable")


def _daily_df(symbol: str = "000001.SZ", *, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "date": [date(2026, 7, 17)],
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


def _enriched_df(symbol: str = "000001.SZ", *, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "date": [date(2026, 7, 17)],
        "open": [10.0],
        "high": [10.2],
        "low": [9.9],
        "close": [10.1],
        "volume": [100.0],
        "amount": [1010.0],
        "raw_close": [10.1],
        "raw_high": [10.2],
        "raw_low": [9.9],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _metrics_df(*, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "period_end": [date(2026, 3, 31)],
        "roe": [12.0],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _adj_df(*, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "trade_date": [date(2026, 3, 31)],
        "ex_factor": [1.1],
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


def _patch_custom_financial(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: name)
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)


def _patch_custom_depth(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == name and dataset == "depth5",
    )


def _fake_compute_enriched(raw: pl.DataFrame, **_kwargs) -> pl.DataFrame:
    return raw.with_columns(
        pl.col("close").alias("raw_close"),
        pl.col("high").alias("raw_high"),
        pl.col("low").alias("raw_low"),
        pl.lit(None, dtype=pl.Float64).alias("turnover_rate"),
        pl.lit(0, dtype=pl.UInt32).alias("consecutive_limit_ups"),
        pl.lit(0, dtype=pl.UInt32).alias("consecutive_limit_downs"),
    )


def test_usable_daily_dates_hide_stale_custom(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(part / "part.parquet")
    _patch_custom_daily(monkeypatch)
    assert kline_sync.usable_daily_partition_dates(tmp_path) == []
    assert kline_sync.daily_partition_usable(part / "part.parquet") is False


def test_unreadable_leftover_tickflow_date_marker_still_counts(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily_enriched" / "date=2026-07-17"
    part.mkdir(parents=True)
    (part / "part.parquet").write_bytes(b"")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert kline_sync.usable_daily_partition_dates(
        tmp_path, table="kline_daily_enriched",
    ) == [date(2026, 7, 17)]
    _patch_custom_daily(monkeypatch)
    assert kline_sync.usable_daily_partition_dates(
        tmp_path, table="kline_daily_enriched",
    ) == []


def test_usable_daily_dates_keep_untagged_leftover_tickflow(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df().write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert kline_sync.usable_daily_partition_dates(tmp_path) == [date(2026, 7, 17)]


def test_latest_daily_and_enriched_ignore_stale_custom(monkeypatch, tmp_path):
    daily = tmp_path / "kline_daily" / "date=2026-07-17"
    daily.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(daily / "part.parquet")
    enr = tmp_path / "kline_daily_enriched" / "date=2026-07-17"
    enr.mkdir(parents=True)
    _enriched_df(route="tickflow").write_parquet(enr / "part.parquet")
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.latest_daily_date() is None
    assert repo.earliest_daily_date() is None
    assert repo.latest_enriched_date("stock") is None


def test_daily_status_skips_stale_custom(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(part / "part.parquet")
    _patch_custom_daily(monkeypatch)
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert data_api._safe_aggregate_daily(repo) is None

    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    stats = data_api._safe_aggregate_daily(repo)
    assert stats is not None
    assert stats["trading_days"] == 1
    assert stats["earliest_date"] == "2026-07-17"


def test_enriched_status_skips_stale_custom(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily_enriched" / "date=2026-07-17"
    part.mkdir(parents=True)
    _enriched_df(route="tickflow").write_parquet(part / "part.parquet")
    _patch_custom_daily(monkeypatch)
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        execute_all=lambda *_a, **_k: [],
    )
    assert data_api._safe_aggregate_enriched(repo) is None


def test_adj_status_daily_window_ignores_stale_custom_daily(monkeypatch, tmp_path):
    daily = tmp_path / "kline_daily" / "date=2026-07-17"
    daily.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(daily / "part.parquet")
    adj = tmp_path / "adj_factor"
    adj.mkdir(parents=True)
    _adj_df(route="tickflow").write_parquet(adj / "all.parquet")
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert data_api._safe_aggregate_adj_factor(repo) is None


def test_coverage_gap_replaces_stale_enriched(monkeypatch, tmp_path):
    daily = tmp_path / "kline_daily" / "date=2026-07-17"
    daily.mkdir(parents=True)
    _daily_df("600000.SH", route="fuyao").write_parquet(daily / "part.parquet")
    enr = tmp_path / "kline_daily_enriched" / "date=2026-07-17"
    enr.mkdir(parents=True)
    _enriched_df("000001.SZ", route="tickflow").write_parquet(enr / "part.parquet")
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(pipeline, "compute_enriched", _fake_compute_enriched)
    added = pipeline.fill_enriched_coverage_gap(tmp_path, target_date="2026-07-17")
    assert added == 1
    saved = pl.read_parquet(enr / "part.parquet")
    assert saved["symbol"].to_list() == ["600000.SH"]
    assert saved["route"].to_list() == ["fuyao"]


def test_coverage_gap_skips_stale_daily_under_custom(monkeypatch, tmp_path):
    daily = tmp_path / "kline_daily" / "date=2026-07-17"
    daily.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(daily / "part.parquet")
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(pipeline, "compute_enriched", _fake_compute_enriched)
    assert pipeline.fill_enriched_coverage_gap(tmp_path, target_date="2026-07-17") == 0
    assert not (tmp_path / "kline_daily_enriched").exists() or list(
        (tmp_path / "kline_daily_enriched").rglob("*.parquet")
    ) == []


def test_run_pipeline_skips_stale_daily_under_custom(monkeypatch, tmp_path):
    daily = tmp_path / "kline_daily" / "date=2026-07-17"
    daily.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(daily / "part.parquet")
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(pipeline, "compute_enriched", _fake_compute_enriched)
    assert pipeline.run_pipeline(data_dir=tmp_path) == 0
    assert list((tmp_path / "kline_daily_enriched").rglob("*.parquet")) == []


def test_run_pipeline_replaces_stale_enriched_on_new_dates(monkeypatch, tmp_path):
    daily = tmp_path / "kline_daily" / "date=2026-07-17"
    daily.mkdir(parents=True)
    _daily_df("600000.SH", route="fuyao").write_parquet(daily / "part.parquet")
    enr = tmp_path / "kline_daily_enriched" / "date=2026-07-17"
    enr.mkdir(parents=True)
    _enriched_df("000001.SZ", route="tickflow").write_parquet(enr / "part.parquet")
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(pipeline, "compute_enriched", _fake_compute_enriched)
    written = pipeline.run_pipeline(data_dir=tmp_path, new_dates_only=True)
    assert written == 1
    saved = pl.read_parquet(enr / "part.parquet")
    assert saved["symbol"].to_list() == ["600000.SH"]
    assert saved["route"].to_list() == ["fuyao"]


def test_publish_enriched_skips_unresolved(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    out = tmp_path / "kline_daily_enriched" / "date=2026-07-17" / "part.parquet"
    out.parent.mkdir(parents=True)
    pipeline._publish_enriched_partition(
        tmp_path,
        out,
        _enriched_df(),
        scope="ALL",
        calculation_mode="test",
    )
    assert not out.exists()


def test_untagged_pipeline_still_runs_leftover_tickflow(monkeypatch, tmp_path):
    daily = tmp_path / "kline_daily" / "date=2026-07-17"
    daily.mkdir(parents=True)
    _daily_df().write_parquet(daily / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    monkeypatch.setattr(pipeline, "compute_enriched", _fake_compute_enriched)
    written = pipeline.run_pipeline(data_dir=tmp_path)
    assert written == 1
    saved = pl.read_parquet(
        tmp_path / "kline_daily_enriched" / "date=2026-07-17" / "part.parquet"
    )
    assert saved["symbol"].to_list() == ["000001.SZ"]
    assert saved["route"].to_list() == ["tickflow"]


def test_public_financial_merge_fail_closed_when_gate_raises(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "metrics" / "part.parquet"
    path.parent.mkdir(parents=True)
    _metrics_df(route="tickflow").write_parquet(path)

    def _boom():
        raise RuntimeError("gate down")

    monkeypatch.setattr("app.services.financial_sync.financial_write_route", _boom)
    incoming = pl.DataFrame({
        "symbol": ["600000.SH"],
        "period_end": [date(2026, 6, 30)],
        "roe": [8.0],
    })
    n = merge_write_financial_table(incoming, tmp_path, "metrics")
    assert n == 1
    saved = pl.read_parquet(path)
    assert saved["symbol"].to_list() == ["000001.SZ"]


def test_public_adj_merge_fail_closed_when_gate_raises(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor" / "all.parquet"
    path.parent.mkdir(parents=True)
    _adj_df(route="tickflow").write_parquet(path)

    def _boom():
        raise RuntimeError("gate down")

    monkeypatch.setattr("app.services.kline_sync.adj_public_write_allowed", _boom)
    added, affected = merge_write_adj_factor(
        pl.DataFrame({
            "symbol": ["600000.SH"],
            "trade_date": [date(2026, 6, 30)],
            "ex_factor": [1.2],
        }),
        tmp_path,
    )
    assert added == 0
    assert affected == []
    saved = pl.read_parquet(path)
    assert saved["symbol"].to_list() == ["000001.SZ"]


def test_leftover_tickflow_still_merges_public_financial(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    n = merge_write_financial_table(_metrics_df(), tmp_path, "metrics")
    assert n == 1
    saved = pl.read_parquet(tmp_path / "financials" / "metrics" / "part.parquet")
    assert saved["symbol"].to_list() == ["000001.SZ"]


def test_reference_valuation_skips_stale_daily(monkeypatch, tmp_path):
    daily = tmp_path / "kline_daily" / "date=2026-07-17"
    daily.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(daily / "part.parquet")
    _patch_custom_daily(monkeypatch)
    assert build_valuation_daily(tmp_path, date(2026, 7, 17)).is_empty()
    assert list_partition_dates(tmp_path, "kline_daily") == []


def test_reference_valuation_still_reads_untagged_leftover(monkeypatch, tmp_path):
    daily = tmp_path / "kline_daily" / "date=2026-07-17"
    daily.mkdir(parents=True)
    _daily_df().write_parquet(daily / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    out = build_valuation_daily(tmp_path, date(2026, 7, 17))
    assert out["symbol"].to_list() == ["000001.SZ"]


def test_limit_events_skip_stale_daily(monkeypatch, tmp_path):
    daily = tmp_path / "kline_daily" / "date=2026-07-17"
    daily.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(daily / "part.parquet")
    _patch_custom_daily(monkeypatch)
    assert build_limit_up_events(tmp_path, date(2026, 7, 17)).is_empty()


def test_seal_fund_map_skips_stale_custom_depth(monkeypatch, tmp_path):
    part = tmp_path / "sealed_l1" / "date=2026-07-17"
    part.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "sealed_up": [True],
        "bid1_vol": [1000.0],
        "route": ["tickflow"],
    }).write_parquet(part / "part.parquet")
    _patch_custom_depth(monkeypatch)
    assert _seal_fund_map(tmp_path, date(2026, 7, 17)) == {}


def test_seal_fund_map_still_reads_untagged_leftover(monkeypatch, tmp_path):
    part = tmp_path / "sealed_l1" / "date=2026-07-17"
    part.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "sealed_up": [True],
        "bid1_vol": [1000.0],
    }).write_parquet(part / "part.parquet")
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "tickflow")
    assert _seal_fund_map(tmp_path, date(2026, 7, 17)) == {"000001.SZ": 1000.0}


def test_regime_dates_ignore_stale_enriched(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily_enriched" / "date=2026-07-17"
    part.mkdir(parents=True)
    _enriched_df(route="tickflow").write_parquet(part / "part.parquet")
    _patch_custom_daily(monkeypatch)
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert enriched_date_set(repo) == set()

    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert enriched_date_set(repo) == {date(2026, 7, 17)}


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"


def test_undeclared_daily_still_falls_back_to_tickflow(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: False,
    )
    provider, fallback, err = kline_sync._resolve_daily_provider("fuyao")
    assert provider is None
    assert fallback is False
    assert err is not None
    assert kline_sync.daily_route() == "unresolved"


def test_daily_prefs_unreadable_stays_fail_closed(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    assert kline_sync.daily_route() == "unresolved"
    assert kline_sync.live_daily_persist_allowed() is False
    assert kline_sync.daily_cache_usable(_daily_df(), "unresolved") is False
