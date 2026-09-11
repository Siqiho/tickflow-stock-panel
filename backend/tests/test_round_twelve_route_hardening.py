"""Twelfth-round leftover mix-source / fail-open paths.

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

from app.jobs import daily_pipeline
from app.services import extend_history, kline_sync, preferences
from app.services.depth_service import (
    DepthService,
    depth_cache_usable,
    depth_route,
    depth_stored_usable,
)
from app.services.minute_refresh import MinuteRefreshService
from app.services.quote_service import QuoteService
from app.share_capital import load_share_history
from app.tickflow.repository import DataStore, KlineRepository


def _prefs_boom(*_a, **_k):
    raise RuntimeError("prefs unreadable")


def _adj_df(*, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "trade_date": [date(2026, 3, 31)],
        "ex_factor": [1.1],
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
        "float_shares": [1.0e10],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _sealed_df(*, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "sealed_up": [True],
        "sealed_down": [False],
        "ask1_vol": [0],
        "bid1_vol": [100],
        "status": ["limit_up"],
        "fetched_at": [1.0],
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


def _patch_custom_adj(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == name and dataset == "adj_factor",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _patch_custom_minute(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == name and dataset == "minute",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _patch_custom_depth(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == name and dataset == "depth5",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def test_pipeline_refresh_does_not_ungate_stale_adj(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor"
    path.mkdir(parents=True)
    _adj_df(route="tickflow").write_parquet(path / "all.parquet")
    _patch_custom_adj(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.store.db.execute("SELECT count(*) FROM adj_factor").fetchone()[0] == 0
    daily_pipeline._refresh_views(repo)
    assert repo.store.db.execute("SELECT count(*) FROM adj_factor").fetchone()[0] == 0
    daily_pipeline._refresh_single_view(repo, "adj_factor")
    assert repo.store.db.execute("SELECT count(*) FROM adj_factor").fetchone()[0] == 0


def test_extend_history_refresh_does_not_ungate_stale_adj(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor"
    path.mkdir(parents=True)
    _adj_df(route="tickflow").write_parquet(path / "all.parquet")
    _patch_custom_adj(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    extend_history._refresh_single_view(repo, "adj_factor")
    assert repo.store.db.execute("SELECT count(*) FROM adj_factor").fetchone()[0] == 0


def test_duckdb_minute_view_hides_stale_custom(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    _minute_df(route="tickflow").write_parquet(part / "part.parquet")
    _patch_custom_minute(monkeypatch)
    store = DataStore(tmp_path)
    rows = store.db.execute("SELECT count(*) FROM kline_minute").fetchone()
    assert rows[0] == 0


def test_refresh_minute_views_keeps_minute_gate(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    _minute_df(route="tickflow").write_parquet(part / "part.parquet")
    _patch_custom_minute(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    repo.refresh_minute_views()
    assert repo.db.execute("SELECT count(*) FROM kline_minute").fetchone()[0] == 0


def test_repo_get_minute_skips_stale_custom(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    _minute_df(route="tickflow").write_parquet(part / "part.parquet")
    _patch_custom_minute(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.get_minute("000001.SZ", date(2026, 7, 17)).is_empty()
    assert repo.get_minute_batch(["000001.SZ"], date(2026, 7, 17)).is_empty()


def test_untagged_minute_still_serves_leftover_tickflow(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    _minute_df().write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    repo = KlineRepository(DataStore(tmp_path))
    out = repo.get_minute("000001.SZ", date(2026, 7, 17))
    assert out["symbol"].to_list() == ["000001.SZ"]
    assert repo.db.execute("SELECT count(*) FROM kline_minute").fetchone()[0] == 1


def test_minute_write_replaces_stale_other_route(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    stale = _minute_df("000001.SZ", route="tickflow")
    stale.write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync, "minute_route", lambda: "fuyao")
    fresh = _minute_df("600000.SH", route="fuyao")
    written = kline_sync._write_minute_partition(fresh, tmp_path / "kline_minute")
    assert written == 1
    saved = pl.read_parquet(part / "part.parquet")
    assert saved["symbol"].to_list() == ["600000.SH"]
    assert saved["route"].to_list() == ["fuyao"]


def test_share_history_skips_stale_and_import_failure(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "shares"
    path.mkdir(parents=True)
    _shares_df(route="tickflow").write_parquet(path / "part.parquet")
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    assert load_share_history(tmp_path).is_empty()

    def _boom(_data_dir, _table):
        raise RuntimeError("gated reader exploded")

    monkeypatch.setattr("app.services.financial_sync.get_financial_df", _boom)
    assert load_share_history(tmp_path).is_empty()


def test_adj_coverage_start_ignores_stale_custom(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor_etf"
    path.mkdir(parents=True)
    _adj_df(route="tickflow").write_parquet(path / "all.parquet")
    _patch_custom_adj(monkeypatch)
    fallback = datetime(2026, 6, 1)
    assert kline_sync.adj_coverage_start(tmp_path, "etf", fallback) == fallback


def test_etf_factors_skip_stale_custom(monkeypatch, tmp_path):
    from app.services import index_sync

    path = tmp_path / "adj_factor_etf"
    path.mkdir(parents=True)
    _adj_df(route="tickflow").write_parquet(path / "all.parquet")
    _patch_custom_adj(monkeypatch)
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert index_sync._load_etf_factors(repo).is_empty()


def test_depth_cache_rejects_stale_tickflow_for_custom(monkeypatch, tmp_path):
    _patch_custom_depth(monkeypatch)
    assert depth_route() == "fuyao"
    assert depth_cache_usable(_sealed_df(route="tickflow"), "fuyao") is False
    assert depth_cache_usable(_sealed_df(), "fuyao") is False
    assert depth_cache_usable(_sealed_df(route="fuyao"), "fuyao") is True
    assert depth_stored_usable("tickflow", "fuyao") is False
    assert depth_stored_usable("public", "tickflow") is True

    part = tmp_path / "sealed_l1" / "date=2026-07-17"
    part.mkdir(parents=True)
    _sealed_df(route="tickflow").write_parquet(part / "part.parquet")
    svc = DepthService()
    svc.set_repo(KlineRepository(DataStore(tmp_path)))
    assert svc._persisted_for_date(date(2026, 7, 17)) is False
    assert svc.get_sealed_map(date(2026, 7, 17), is_down=False) == {}
    assert svc.is_sealed_ready(date(2026, 7, 17)) is False


def test_depth_write_tags_current_route(monkeypatch, tmp_path):
    _patch_custom_depth(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    svc = DepthService()
    svc.set_repo(repo)
    svc._sealed_cache = {
        "000001.SZ": {
            "sealed_up": True,
            "sealed_down": False,
            "ask1_vol": 0,
            "bid1_vol": 100,
            "status": "limit_up",
            "fetched_ts": 1.0,
        }
    }
    svc._persist(date(2026, 7, 17))
    saved = pl.read_parquet(tmp_path / "sealed_l1" / "date=2026-07-17" / "part.parquet")
    assert saved["route"].to_list() == ["fuyao"]
    assert svc._persisted_for_date(date(2026, 7, 17)) is True
    sealed = svc.get_sealed_map(date(2026, 7, 17), is_down=False)
    assert sealed["000001.SZ"]["sealed"] is True


def test_leftover_tickflow_depth_accepts_public_tag(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "tickflow")
    assert depth_cache_usable(_sealed_df(route="public"), "tickflow") is True
    part = tmp_path / "sealed_l1" / "date=2026-07-17"
    part.mkdir(parents=True)
    _sealed_df(route="public").write_parquet(part / "part.parquet")
    svc = DepthService()
    svc.set_repo(KlineRepository(DataStore(tmp_path)))
    assert svc._persisted_for_date(date(2026, 7, 17)) is True
    assert "000001.SZ" in svc.get_sealed_map(date(2026, 7, 17), is_down=False)


def test_depth_memory_skips_after_route_switch(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "tickflow")
    svc = DepthService()
    svc.set_repo(KlineRepository(DataStore(tmp_path)))
    svc._sealed_cache = {"000001.SZ": {"sealed_up": True, "bid1_vol": 9}}
    svc._sealed_ready = True
    svc._sealed_date = date(2026, 7, 17)
    svc._sealed_cache_route = "tickflow"
    assert svc.get_sealed_map(date(2026, 7, 17), is_down=False)["000001.SZ"]["sealed"] is True

    _patch_custom_depth(monkeypatch)
    assert svc.get_sealed_map(date(2026, 7, 17), is_down=False) == {}
    assert svc.is_sealed_ready(date(2026, 7, 17)) is False


def test_minute_refresh_coverage_ignores_stale_custom(monkeypatch, tmp_path):
    from app.market_time import cn_today

    today = cn_today()
    part = tmp_path / "kline_minute" / f"date={today.isoformat()}"
    part.mkdir(parents=True)
    _minute_df(route="tickflow").write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_full_minute_data_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == "fuyao" and dataset == "full_minute",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())
    svc = MinuteRefreshService(KlineRepository(DataStore(tmp_path)))
    assert svc._today_coverage_lag_minutes() is None


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
