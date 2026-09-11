"""Eleventh-round leftover mix-source / fail-open paths.

Keeps prior TickFlow leftover contracts:
- leftover TickFlow + free realtime stays mode=none
- undeclared daily / minute / full_minute / adj still fall back to TickFlow
- leftover TickFlow + no ADJ cap still uses the public sina adapter
- entitled TickFlow minute fallback after a custom *call* failure
- TickFlow default depth empty result may still use public L1
- leftover TickFlow single-symbol minute view may still use public / TDX
- A-share / index / ETF instruments stay TickFlow (no instrument_provider)
- Lab /api/free-ext public writes stay explicit public endpoints
- historical daily / enriched partitions stay until re-sync
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import financials as financials_api
from app.api import kline as kline_api
from app.api import watchlist as watchlist_api
from app.backtest.fundamentals import load_fundamental_snapshot
from app.services import financial_sync, kline_sync, preferences
from app.services.financial_normalize import local_adj_factor_ready, local_financials_ready
from app.services.quote_service import QuoteService
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet
from app.tickflow.repository import DataStore, KlineRepository


def _capset(*caps: Cap) -> CapabilitySet:
    return CapabilitySet({c: CapabilityLimits(rpm=60, batch=100) for c in caps})


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


def _metrics_df(*, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "period_end": [date(2026, 3, 31)],
        "announce_date": [date(2026, 4, 20)],
        "roe": [12.0],
        "gross_margin": [30.0],
        "net_margin": [8.0],
        "revenue_yoy": [10.0],
        "net_income_yoy": [9.0],
        "debt_to_asset_ratio": [40.0],
        "bps": [5.0],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _live_daily() -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": ["000001.SZ"],
        "date": [date.today()],
        "open": [10.0],
        "high": [10.2],
        "low": [9.9],
        "close": [10.1],
        "volume": [100.0],
        "amount": [1010.0],
    })


def test_custom_daily_skips_live_enriched_publish(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: name == "fuyao" and dataset == "daily",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda name: SimpleNamespace())
    assert kline_sync.live_enriched_overlay_allowed() is False

    repo = KlineRepository(DataStore(tmp_path))
    published = []
    monkeypatch.setattr(repo, "publish_live_enriched_asset", lambda *a, **k: published.append(a))
    monkeypatch.setattr(repo, "flush_live_enriched_asset", lambda *a, **k: published.append(("flush", a)))
    service = QuoteService()
    service.set_repo(repo)
    service._flush_live_enriched(_live_daily(), persist=False)
    assert published == []
    cached, _ = repo.get_enriched_latest()
    assert cached.is_empty()


def test_leftover_tickflow_still_publishes_live_enriched(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert kline_sync.live_enriched_overlay_allowed() is True

    repo = KlineRepository(DataStore(tmp_path))
    published = []
    monkeypatch.setattr(
        repo,
        "publish_live_enriched_asset",
        lambda *a, **k: published.append(k.get("asset_type") or a[0]),
    )
    monkeypatch.setattr(repo, "get_live_agg", lambda: pl.DataFrame({"symbol": ["000001.SZ"]}))
    monkeypatch.setattr(
        repo,
        "get_enriched_latest",
        lambda: (pl.DataFrame({"symbol": ["000001.SZ"], "close": [9.0]}), date.today()),
    )
    monkeypatch.setattr(repo, "get_instruments", lambda: pl.DataFrame())
    monkeypatch.setattr(
        "app.indicators.pipeline.compute_enriched_today",
        lambda **k: _live_daily(),
    )
    monkeypatch.setattr(
        "app.indicators.pipeline.attach_deviation_columns_today",
        lambda df, *a, **k: df,
    )
    service = QuoteService()
    service.set_repo(repo)
    service._flush_live_enriched(_live_daily(), persist=False)
    assert "stock" in published


def test_get_enriched_latest_drops_live_cache_for_custom_daily(monkeypatch, tmp_path):
    repo = KlineRepository(DataStore(tmp_path))
    live = _live_daily()
    repo.publish_live_enriched_asset("stock", live)
    cached, cached_date = repo.get_enriched_latest()
    assert cached_date == date.today()
    assert cached["symbol"].to_list() == ["000001.SZ"]

    monkeypatch.setattr(kline_sync, "live_enriched_overlay_allowed", lambda: False)
    dropped, dropped_date = repo.get_enriched_latest()
    assert dropped.is_empty()
    assert dropped_date is None
    assert repo._enriched_cache_live is False


def test_daily_latest_http_skips_live_overlay_for_custom(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync, "live_enriched_overlay_allowed", lambda: False)
    repo = KlineRepository(DataStore(tmp_path))
    repo.publish_live_enriched_asset("stock", _live_daily())
    app = FastAPI()
    app.include_router(kline_api.router)
    app.state.repo = repo
    app.state.quote_service = SimpleNamespace(
        get_enriched_today=lambda: (_live_daily(), date.today()),
    )
    app.state.capabilities = CapabilitySet()
    request = SimpleNamespace(app=app)
    assert kline_api._latest_live_candle(request, "000001.SZ") is None
    rows = [{"date": str(date.today()), "close": 9.0}]
    assert kline_api._maybe_inject_live_candle(request, "000001.SZ", rows) == rows


def test_adj_cache_rejects_stale_tickflow_for_custom(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor"
    path.mkdir(parents=True)
    _adj_df(route="tickflow").write_parquet(path / "all.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: name == "fuyao" and dataset == "adj_factor",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda name: SimpleNamespace())
    assert kline_sync.adj_route() == "fuyao"
    assert kline_sync.get_adj_factor_df(tmp_path).is_empty()
    assert local_adj_factor_ready(tmp_path) is False


def test_adj_write_tags_custom_route(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: name == "fuyao" and dataset == "adj_factor",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda name: SimpleNamespace())
    repo = KlineRepository(DataStore(tmp_path))
    added, affected = kline_sync._persist_adj_factor_df(_adj_df(), repo, "stock")
    assert added == 1
    assert affected == ["000001.SZ"]
    saved = pl.read_parquet(tmp_path / "adj_factor" / "all.parquet")
    assert saved["route"].to_list() == ["fuyao"]
    out = kline_sync.get_adj_factor_df(tmp_path)
    assert out["symbol"].to_list() == ["000001.SZ"]
    assert "route" not in out.columns


def test_adj_persist_replaces_stale_other_route(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor"
    path.mkdir(parents=True)
    _adj_df(route="tickflow").write_parquet(path / "all.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: name == "fuyao" and dataset == "adj_factor",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda name: SimpleNamespace())
    repo = KlineRepository(DataStore(tmp_path))
    custom = pl.DataFrame({
        "symbol": ["600000.SH"],
        "trade_date": [date(2026, 6, 1)],
        "ex_factor": [1.2],
    })
    kline_sync._persist_adj_factor_df(custom, repo, "stock")
    saved = pl.read_parquet(path / "all.parquet")
    assert saved["symbol"].to_list() == ["600000.SH"]
    assert saved["route"].to_list() == ["fuyao"]


def test_untagged_adj_still_serves_leftover_tickflow(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor"
    path.mkdir(parents=True)
    _adj_df().write_parquet(path / "all.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    out = kline_sync.get_adj_factor_df(tmp_path)
    assert out["symbol"].to_list() == ["000001.SZ"]
    assert local_adj_factor_ready(tmp_path) is True


def test_leftover_tickflow_adj_accepts_public_sina_tag(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor"
    path.mkdir(parents=True)
    _adj_df(route="public").write_parquet(path / "all.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    assert kline_sync.adj_cache_usable(_adj_df(route="public"), "tickflow") is False
    assert kline_sync.get_adj_factor_df(tmp_path).is_empty()


def test_watchlist_financial_join_skips_stale_custom(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "metrics"
    path.mkdir(parents=True)
    _metrics_df(route="tickflow").write_parquet(path / "part.parquet")
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    base = pl.DataFrame({"symbol": ["000001.SZ"], "close": [10.0]})
    out = watchlist_api._join_local_financial_metrics(base, repo, ["000001.SZ"])
    assert out.columns == ["symbol", "close"]


def test_fundamental_snapshot_skips_stale_custom(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "metrics"
    path.mkdir(parents=True)
    _metrics_df(route="tickflow").write_parquet(path / "part.parquet")
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    assert load_fundamental_snapshot(tmp_path) is None
    assert local_financials_ready(tmp_path) is False


def test_financial_status_counts_gated_rows(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "metrics"
    path.mkdir(parents=True)
    _metrics_df(route="tickflow").write_parquet(path / "part.parquet")
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    monkeypatch.setattr(financials_api, "_fin_available", lambda *a, **k: True)
    monkeypatch.setattr(financials_api, "_public_fin", lambda: False)
    monkeypatch.setattr(financials_api, "_custom_fin", lambda: True)
    monkeypatch.setattr(financials_api, "_local_fin_ready", lambda *a, **k: False)
    app = FastAPI()
    app.include_router(financials_api.router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    app.state.capabilities = _capset(Cap.FINANCIAL)
    app.state.financial_scheduler = SimpleNamespace(last_sync={}, is_syncing=False)
    resp = TestClient(app).get("/api/financials/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tables"]["metrics"] == {"rows": 0, "symbols": 0}


def test_duckdb_financial_view_hides_stale_custom(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "metrics"
    path.mkdir(parents=True)
    _metrics_df(route="tickflow").write_parquet(path / "part.parquet")
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    store = DataStore(tmp_path)
    rows = store.db.execute("SELECT count(*) FROM financials_metrics").fetchone()
    assert rows[0] == 0


def test_duckdb_adj_view_hides_stale_custom(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor"
    path.mkdir(parents=True)
    _adj_df(route="tickflow").write_parquet(path / "all.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: name == "fuyao" and dataset == "adj_factor",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda name: SimpleNamespace())
    store = DataStore(tmp_path)
    rows = store.db.execute("SELECT count(*) FROM adj_factor").fetchone()
    assert rows[0] == 0


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
    assert kline_sync.live_enriched_overlay_allowed() is False


def test_daily_prefs_unreadable_blocks_live_overlay(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    assert kline_sync.daily_route() == "unresolved"
    assert kline_sync.live_enriched_overlay_allowed() is False
    assert kline_sync.live_daily_persist_allowed() is False
