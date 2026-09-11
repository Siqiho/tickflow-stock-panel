"""Thirteenth-round leftover mix-source / fail-open paths.

Keeps prior TickFlow leftover contracts:
- leftover TickFlow + free realtime stays mode=none
- undeclared daily / minute / full_minute / adj still fall back to TickFlow
- leftover TickFlow + no ADJ cap still uses the public sina adapter
- leftover TickFlow adj reads may serve public-sina tags
- entitled TickFlow minute fallback after a custom *call* failure
- TickFlow default depth empty result may still use public L1
- leftover TickFlow depth reads may serve public-tagged sealed files
- leftover TickFlow single-symbol minute view may still use public / TDX
- A-share / index / ETF instruments stay TickFlow (no instrument_provider)
- Lab /api/free-ext public writes stay explicit public endpoints
- historical daily / enriched partitions stay until re-sync
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import polars as pl

from app.api import data as data_api
from app.services import kline_sync, preferences
from app.services.corporate_actions_sync import run_corporate_actions_loop
from app.services.financial_pit import append_shares_history
from app.services.free_sources.financials_public import merge_write_financial_table
from app.services.quote_service import QuoteService
from app.tickflow.repository import DataStore, KlineRepository


def _prefs_boom(*_a, **_k):
    raise RuntimeError("prefs unreadable")


def _minute_df(symbol: str = "000001.SZ", *, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "datetime": [datetime(2026, 7, 17, 9, 30)],
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


def _metrics_df(*, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "period_end": [date(2026, 3, 31)],
        "roe": [12.0],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _shares_df(*, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "period_end": [date(2026, 3, 31)],
        "announce_date": [date(2026, 4, 1)],
        "float_shares": [1.0e10],
        "total_shares": [1.2e10],
        "source": ["tickflow"],
        "table": ["shares"],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _patch_custom_minute(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == name and dataset == "minute",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _patch_custom_adj(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == name and dataset == "adj_factor",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _patch_custom_financial(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: name)
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)


def test_usable_minute_dates_skip_stale_custom(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    _minute_df(route="tickflow").write_parquet(part / "part.parquet")
    _patch_custom_minute(monkeypatch)
    assert kline_sync.usable_minute_partition_dates(tmp_path) == []
    assert kline_sync.latest_usable_minute_datetime(tmp_path) is None


def test_usable_minute_dates_keep_untagged_leftover_tickflow(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    _minute_df().write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    assert kline_sync.usable_minute_partition_dates(tmp_path) == [date(2026, 7, 17)]
    assert kline_sync.latest_usable_minute_datetime(tmp_path) is not None


def test_latest_minute_datetime_ignores_stale_sql(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    _minute_df(route="tickflow").write_parquet(part / "part.parquet")
    _patch_custom_minute(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    # Even if DuckDB is temporarily ungated, incremental start must not advance.
    d = tmp_path.as_posix()
    repo.db.execute(
        f"CREATE OR REPLACE VIEW kline_minute AS "
        f"SELECT * FROM read_parquet('{d}/kline_minute/**/*.parquet', union_by_name=true)"
    )
    assert repo.db.execute("SELECT count(*) FROM kline_minute").fetchone()[0] == 1
    assert kline_sync._latest_minute_datetime(repo) is None


def test_persist_routed_minute_replaces_stale_and_regates(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    stale = _minute_df("000001.SZ", route="tickflow")
    stale.write_parquet(part / "part.parquet")
    _patch_custom_minute(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    fresh = _minute_df("600000.SH", route="fuyao")
    written = kline_sync.persist_routed_minute_bars(fresh, repo)
    assert written == 1
    saved = pl.read_parquet(part / "part.parquet")
    assert saved["symbol"].to_list() == ["600000.SH"]
    assert saved["route"].to_list() == ["fuyao"]
    assert repo.db.execute("SELECT count(*) FROM kline_minute").fetchone()[0] == 1
    stale_rows = repo.db.execute(
        "SELECT count(*) FROM kline_minute WHERE symbol = '000001.SZ'"
    ).fetchone()[0]
    assert stale_rows == 0


def test_minute_status_skips_stale_custom(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    _minute_df(route="tickflow").write_parquet(part / "part.parquet")
    _patch_custom_minute(monkeypatch)
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert data_api._safe_aggregate_minute(repo) is None

    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    stats = data_api._safe_aggregate_minute(repo)
    assert stats is not None
    assert stats["trading_days"] == 1
    assert stats["earliest_date"] == "2026-07-17"


def test_financial_status_skips_stale_custom(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "metrics" / "part.parquet"
    path.parent.mkdir(parents=True)
    _metrics_df(route="tickflow").write_parquet(path)
    _patch_custom_financial(monkeypatch)
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert data_api._safe_aggregate_financials(repo) is None


def test_financial_status_counts_untagged_leftover_tickflow(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "metrics" / "part.parquet"
    path.parent.mkdir(parents=True)
    _metrics_df().write_parquet(path)
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "tickflow")
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    result = data_api._safe_aggregate_financials(repo)
    assert result is not None
    assert result["rows"] == 1
    assert result["tables"]["metrics"] == {"rows": 1, "symbols": 1}


def test_clear_data_regates_stale_adj(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor"
    path.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "trade_date": [date(2026, 3, 31)],
        "ex_factor": [1.1],
        "route": ["tickflow"],
    }).write_parquet(path / "all.parquet")
    _patch_custom_adj(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    # Simulate the raw refresh clear_data does before re-gate.
    d = tmp_path.as_posix()
    repo.db.execute(
        f"CREATE OR REPLACE VIEW adj_factor AS "
        f"SELECT * FROM read_parquet('{d}/adj_factor/**/*.parquet', union_by_name=true)"
    )
    assert repo.db.execute("SELECT count(*) FROM adj_factor").fetchone()[0] == 1
    repo.store._register_gated_catalog_views()
    assert repo.db.execute("SELECT count(*) FROM adj_factor").fetchone()[0] == 0


def test_index_view_refresh_keeps_adj_gate(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor"
    path.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "trade_date": [date(2026, 3, 31)],
        "ex_factor": [1.1],
        "route": ["tickflow"],
    }).write_parquet(path / "all.parquet")
    _patch_custom_adj(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.db.execute("SELECT count(*) FROM adj_factor").fetchone()[0] == 0
    repo.refresh_index_views()
    assert repo.db.execute("SELECT count(*) FROM adj_factor").fetchone()[0] == 0


def test_public_financial_merge_skips_custom_route(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "income" / "part.parquet"
    path.parent.mkdir(parents=True)
    _metrics_df(route="tickflow").rename({"roe": "total_revenue"}).write_parquet(path)
    _patch_custom_financial(monkeypatch)
    incoming = pl.DataFrame({
        "symbol": ["600000.SH"],
        "period_end": [date(2026, 6, 30)],
        "total_revenue": [2.0],
        "source": ["eastmoney_hsf10"],
        "table": ["income"],
    })
    n = merge_write_financial_table(incoming, tmp_path, "income")
    assert n == 1
    saved = pl.read_parquet(path)
    assert saved["symbol"].to_list() == ["000001.SZ"]


def test_append_shares_skips_stale_custom(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "shares" / "part.parquet"
    path.parent.mkdir(parents=True)
    _shares_df(route="tickflow").write_parquet(path)
    _patch_custom_financial(monkeypatch)
    incoming = pl.DataFrame({
        "symbol": ["600000.SH"],
        "period_end": [date(2026, 6, 30)],
        "announce_date": [date(2026, 7, 1)],
        "float_shares": [2.0e9],
        "total_shares": [3.0e9],
        "source": ["custom"],
        "table": ["shares"],
    })
    merged = append_shares_history(tmp_path, incoming, effective_date=date(2026, 6, 30))
    assert merged["symbol"].to_list() == ["600000.SH"]
    assert "000001.SZ" not in merged["symbol"].to_list()
    assert merged["route"].to_list() == ["fuyao"]


def test_corporate_actions_does_not_write_public_adj_under_custom(monkeypatch, tmp_path):
    called = {"n": 0}

    def _boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("public adj write must not run")

    _patch_custom_adj(monkeypatch)
    monkeypatch.setattr(
        "app.services.corporate_actions_sync.sync_adj_factor_public",
        _boom,
    )
    report = run_corporate_actions_loop(
        tmp_path,
        symbols=["000001.SZ"],
        fetch_missing_adj=True,
        publish_actions=False,
    )
    assert called["n"] == 0
    assert report["adj_sync"]["skipped"] is True


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
    assert fallback is True
    assert err is None
    assert kline_sync.daily_route() == "tickflow"


def test_daily_prefs_unreadable_stays_fail_closed(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    assert kline_sync.daily_route() == "unresolved"
    assert kline_sync.live_daily_persist_allowed() is False
    assert kline_sync.live_enriched_overlay_allowed() is False
