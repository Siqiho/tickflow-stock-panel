"""Fourteenth-round leftover mix-source / fail-open paths.

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
- historical daily / enriched partitions stay until re-sync
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import polars as pl

from app.api import data as data_api
from app.services import financial_sync, kline_sync, preferences
from app.services.free_sources.adj_factor_public import (
    merge_write_adj_coverage,
    merge_write_adj_factor,
    read_adj_coverage,
    sync_adj_factor_public,
)
from app.services.free_sources.share_capital_public import sync_share_capital_public
from app.services.quote_service import QuoteService
from app.services.reference_derived import _load_pit_safe_shares
from app.tickflow.capabilities import CapabilitySet
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


def _shares_df(*, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "period_end": [date(2026, 3, 31)],
        "announce_date": [date(2026, 4, 1)],
        "effective_date": [date(2026, 3, 31)],
        "float_shares": [1.0e10],
        "total_shares": [1.2e10],
        "source": ["tickflow"],
        "table": ["shares"],
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


def test_daily_write_replaces_stale_other_route(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df("000001.SZ", route="tickflow").write_parquet(part / "part.parquet")
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    repo.append_daily(_daily_df("600000.SH"))
    saved = pl.read_parquet(part / "part.parquet")
    assert saved["symbol"].to_list() == ["600000.SH"]
    assert saved["route"].to_list() == ["fuyao"]


def test_daily_write_keeps_untagged_leftover_tickflow_merge(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df("000001.SZ").write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    repo = KlineRepository(DataStore(tmp_path))
    repo.append_daily(_daily_df("600000.SH"))
    saved = pl.read_parquet(part / "part.parquet")
    assert set(saved["symbol"].to_list()) == {"000001.SZ", "600000.SH"}


def test_daily_unresolved_skips_write(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    repo = KlineRepository(DataStore(tmp_path))
    repo.append_daily(_daily_df("000001.SZ"))
    assert not (tmp_path / "kline_daily").exists()


def test_merge_live_daily_replaces_stale_custom(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df("000001.SZ", route="tickflow").write_parquet(part / "part.parquet")
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    repo.merge_live_daily_asset("stock", _daily_df("600000.SH"))
    saved = pl.read_parquet(part / "part.parquet")
    assert saved["symbol"].to_list() == ["600000.SH"]
    assert saved["route"].to_list() == ["fuyao"]


def test_merge_live_daily_preserves_leftover_same_route(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    repo = KlineRepository(DataStore(tmp_path))
    repo.flush_live_daily_asset("stock", _daily_df("000001.SZ"))
    repo.merge_live_daily_asset("stock", _daily_df("600000.SH"))
    saved = pl.read_parquet(
        tmp_path / "kline_daily" / "date=2026-07-17" / "part.parquet"
    )
    assert set(saved["symbol"].to_list()) == {"000001.SZ", "600000.SH"}


def test_merge_live_enriched_replaces_stale_disk(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily_enriched" / "date=2026-07-17"
    part.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "date": [date(2026, 7, 17)],
        "open": [10.0],
        "high": [10.2],
        "low": [9.9],
        "close": [10.1],
        "volume": [100.0],
        "amount": [1010.0],
        "route": ["tickflow"],
    }).write_parquet(part / "part.parquet")
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    incoming = pl.DataFrame({
        "symbol": ["600000.SH"],
        "date": [date(2026, 7, 17)],
        "open": [20.0],
        "high": [20.2],
        "low": [19.9],
        "close": [20.1],
        "volume": [200.0],
        "amount": [4020.0],
    })
    repo.merge_live_enriched_asset("stock", incoming)
    saved = pl.read_parquet(part / "part.parquet")
    assert saved["symbol"].to_list() == ["600000.SH"]


def test_adj_coverage_hidden_under_custom(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor" / "coverage.parquet"
    path.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "status": ["no_event"],
        "source": ["sina"],
        "events_n": [0],
        "checked_at": ["2026-07-17T00:00:00"],
        "note": ["leftover"],
    }).write_parquet(path)
    _patch_custom_adj(monkeypatch)
    cov = read_adj_coverage(tmp_path)
    assert cov.is_empty()


def test_adj_coverage_still_serves_leftover_tickflow(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor" / "coverage.parquet"
    path.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "status": ["no_event"],
        "source": ["sina"],
        "events_n": [0],
        "checked_at": ["2026-07-17T00:00:00"],
        "note": ["leftover"],
    }).write_parquet(path)
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    cov = read_adj_coverage(tmp_path)
    assert cov["symbol"].to_list() == ["000001.SZ"]


def test_adj_status_skips_leftover_coverage_under_custom(monkeypatch, tmp_path):
    daily = tmp_path / "kline_daily" / "date=2026-07-17"
    daily.mkdir(parents=True)
    _daily_df().write_parquet(daily / "part.parquet")
    cov = tmp_path / "adj_factor" / "coverage.parquet"
    cov.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "status": ["no_event"],
        "source": ["sina"],
        "events_n": [0],
        "checked_at": ["2026-07-17T00:00:00"],
        "note": ["leftover"],
    }).write_parquet(cov)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "trade_date": [date(2026, 3, 31)],
        "ex_factor": [1.1],
        "route": ["tickflow"],
    }).write_parquet(tmp_path / "adj_factor" / "all.parquet")
    _patch_custom_adj(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert data_api._safe_aggregate_adj_factor(repo) is None


def test_public_adj_write_skips_custom_route(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor" / "all.parquet"
    path.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "trade_date": [date(2026, 3, 31)],
        "ex_factor": [1.1],
        "route": ["tickflow"],
    }).write_parquet(path)
    _patch_custom_adj(monkeypatch)
    incoming = pl.DataFrame({
        "symbol": ["600000.SH"],
        "trade_date": [date(2026, 6, 30)],
        "ex_factor": [1.2],
    })
    added, affected = merge_write_adj_factor(incoming, tmp_path)
    assert added == 0
    assert affected == []
    saved = pl.read_parquet(path)
    assert saved["symbol"].to_list() == ["000001.SZ"]
    assert merge_write_adj_coverage(
        [{
            "symbol": "600000.SH",
            "status": "events",
            "source": "sina",
            "events_n": 1,
            "checked_at": "2026-07-17T00:00:00",
            "note": "mix",
        }],
        tmp_path,
    ) == 0
    assert not (tmp_path / "adj_factor" / "coverage.parquet").exists()


def test_sync_adj_factor_public_skips_custom(monkeypatch, tmp_path):
    called = {"n": 0}

    def _boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("public adj fetch must not run")

    _patch_custom_adj(monkeypatch)
    monkeypatch.setattr(
        "app.services.free_sources.adj_factor_public.fetch_adj_factors_symbol_meta",
        _boom,
    )
    out = sync_adj_factor_public(["000001.SZ"], tmp_path, workers=1)
    assert called["n"] == 0
    assert out["skipped"] is True
    assert out["ok"] is False


def test_leftover_tickflow_still_writes_public_adj(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    incoming = pl.DataFrame({
        "symbol": ["000001.SZ"],
        "trade_date": [date(2026, 3, 31)],
        "ex_factor": [1.1],
    })
    added, affected = merge_write_adj_factor(incoming, tmp_path)
    assert added == 1
    assert affected == ["000001.SZ"]
    n = merge_write_adj_coverage(
        [{
            "symbol": "000001.SZ",
            "status": "events",
            "source": "sina",
            "events_n": 1,
            "checked_at": "2026-07-17T00:00:00",
            "note": "leftover",
        }],
        tmp_path,
    )
    assert n == 1


def test_share_capital_public_skips_custom_financial(monkeypatch, tmp_path):
    called = {"n": 0}

    def _boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("public share-capital fetch must not run")

    _patch_custom_financial(monkeypatch)
    monkeypatch.setattr(
        "app.services.free_sources.share_capital_public.fetch_share_capital_history",
        _boom,
    )
    path = tmp_path / "financials" / "shares" / "part.parquet"
    path.parent.mkdir(parents=True)
    _shares_df(route="tickflow").write_parquet(path)
    stats = sync_share_capital_public(["000001.SZ"], tmp_path, sleep_s=0)
    assert called["n"] == 0
    assert stats["skipped"] is True
    assert stats["published"] is False
    saved = pl.read_parquet(path)
    assert saved["symbol"].to_list() == ["000001.SZ"]


def test_reference_derived_shares_skip_stale_custom(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "shares" / "part.parquet"
    path.parent.mkdir(parents=True)
    _shares_df(route="tickflow").write_parquet(path)
    _patch_custom_financial(monkeypatch)
    out = _load_pit_safe_shares(tmp_path, date(2026, 6, 30))
    assert out.is_empty()


def test_financial_last_sync_skips_stale_custom(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "metrics" / "part.parquet"
    path.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "period_end": [date(2026, 3, 31)],
        "roe": [12.0],
        "route": ["tickflow"],
    }).write_parquet(path)
    _patch_custom_financial(monkeypatch)
    written: dict[str, str] = {}
    monkeypatch.setattr(preferences, "get_financial_sync_times", lambda: {})
    monkeypatch.setattr(
        preferences,
        "set_financial_sync_time",
        lambda table, ts: written.__setitem__(table, ts),
    )
    sched = financial_sync.FinancialScheduler()
    sched.start(tmp_path, CapabilitySet(), auto_schedule=False)
    assert "metrics" not in written
    assert "metrics" not in sched._last_sync


def test_latest_minute_date_ignores_stale_sql(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    _minute_df(route="tickflow").write_parquet(part / "part.parquet")
    _patch_custom_minute(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    d = tmp_path.as_posix()
    repo.db.execute(
        f"CREATE OR REPLACE VIEW kline_minute AS "
        f"SELECT * FROM read_parquet('{d}/kline_minute/**/*.parquet', union_by_name=true)"
    )
    assert repo.db.execute("SELECT count(*) FROM kline_minute").fetchone()[0] == 1
    assert repo.latest_minute_date("000001.SZ") is None
    assert repo.earliest_minute_date() is None
    assert repo.latest_minute_date_global() is None


def test_untagged_minute_dates_still_serve_leftover_tickflow(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    _minute_df().write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.latest_minute_date("000001.SZ") == date(2026, 7, 17)
    assert repo.earliest_minute_date() == date(2026, 7, 17)
    assert repo.latest_minute_date_global() == date(2026, 7, 17)


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
    assert kline_sync.daily_cache_usable(_daily_df(), "unresolved") is False
