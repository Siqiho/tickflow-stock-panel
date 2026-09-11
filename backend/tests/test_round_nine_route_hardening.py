"""Ninth-round leftover mix-source / fail-open paths.

Keeps prior TickFlow leftover contracts:
- leftover TickFlow + free realtime stays mode=none
- undeclared daily / minute / full_minute / adj still fall back to TickFlow
- leftover TickFlow + no ADJ cap still uses the public sina adapter
- entitled TickFlow minute fallback after a custom *call* failure
- TickFlow default depth empty result may still use public L1
- leftover TickFlow single-symbol minute view may still use public / TDX
- A-share / index / ETF instruments stay TickFlow (no instrument_provider)
- Lab /api/free-ext public writes stay explicit public endpoints
"""
from __future__ import annotations

import inspect
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import indices as indices_api
from app.api import kline as kline_api
from app.api import settings as settings_api
from app.jobs import daily_pipeline
from app.services import financial_sync, kline_sync, preferences
from app.services.quote_service import QuoteService
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet
from app.tickflow.repository import DataStore, KlineRepository


def _capset(*caps: Cap) -> CapabilitySet:
    return CapabilitySet({c: CapabilityLimits(rpm=60, batch=100) for c in caps})


def _prefs_boom(*_a, **_k):
    raise RuntimeError("prefs unreadable")


def test_daily_prefs_unreadable_is_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow daily"))
    monkeypatch.setattr(kline_sync, "sync_daily_batch", tf)
    monkeypatch.setattr(kline_sync, "get_client", tf)

    assert kline_sync.daily_provider_is_custom() is True
    assert kline_sync.routed_daily_source_label() == "none"
    written = kline_sync.sync_and_persist_daily_batch(
        ["000001.SZ"],
        KlineRepository(DataStore(tmp_path)),
        _capset(Cap.KLINE_DAILY_BATCH),
    )
    assert written == 0
    out = kline_sync.fetch_routed_daily(
        ["000001.SZ"],
        start_time=datetime(2026, 1, 1),
        end_time=datetime(2026, 1, 31),
        capset=_capset(Cap.KLINE_DAILY_BATCH),
    )
    assert out.is_empty()
    tf.assert_not_called()


def test_pipeline_quote_pool_branch_uses_custom_daily_gate():
    source = inspect.getsource(daily_pipeline.run_now)
    assert "daily_provider_is_custom()" in source
    assert "sync_daily_by_quotes" in source


def test_resolve_universe_scope_prefs_failure_skips_tickflow_all_a(monkeypatch):
    monkeypatch.setattr(
        daily_pipeline._prefs,
        "get_pipeline_universe_scope",
        _prefs_boom,
    )
    monkeypatch.setattr(
        daily_pipeline,
        "get_pool",
        lambda pool_id, **kwargs: (_ for _ in ()).throw(
            AssertionError(f"must not refresh {pool_id} via TickFlow")
        ),
    )
    monkeypatch.setattr(
        "app.services.universe_scope.resolve_symbols",
        lambda *a, **k: ["000001.SZ"],
    )
    symbols = daily_pipeline.resolve_universe(_capset(Cap.KLINE_DAILY_BATCH))
    assert symbols == ["000001.SZ"]


def test_index_live_prefs_failure_does_not_tickflow(monkeypatch):
    monkeypatch.setattr(kline_sync, "daily_provider_is_custom", _prefs_boom)
    monkeypatch.setattr(
        kline_sync,
        "fetch_routed_daily",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not live-fetch")),
    )
    repo = SimpleNamespace(
        get_index_instruments=lambda: pl.DataFrame(),
        get_index_daily=lambda *a, **k: pl.DataFrame(),
    )
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo, capabilities=_capset())))
    out = indices_api.get_index_daily(
        req, symbol="000001.SH", days=20, start_date=None, end_date=None,
    )
    assert out["rows"] == []
    assert out["source"] == "none"


def test_minute_prefs_unreadable_skips_tickflow_and_public(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", _prefs_boom)
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow minute"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    public = MagicMock(side_effect=AssertionError("must not public-minute"))
    monkeypatch.setattr(kline_sync, "_public_minute_fallback", public)
    assert kline_sync.minute_may_use_leftover_public() is False
    out = kline_sync.fetch_minute_single("000001.SZ", date(2026, 7, 17), capset=CapabilitySet())
    assert out.is_empty()
    tf.assert_not_called()
    public.assert_not_called()


def test_declared_custom_minute_skips_watchlist_tdx(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync, "minute_may_use_leftover_public", lambda: False)
    monkeypatch.setattr(kline_sync, "minute_provider_is_custom", lambda: True)
    monkeypatch.setattr(kline_sync, "fetch_minute_single", lambda *a, **k: pl.DataFrame())
    monkeypatch.setattr("app.services.watchlist.contains", lambda *a, **k: True)

    def fail_tdx(*_a, **_k):
        raise AssertionError("declared custom minute must not TDX-mix")

    monkeypatch.setattr(
        "app.services.free_sources.tdx_history_minute.fetch_history_minute",
        fail_tdx,
    )
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        get_minute=lambda *a, **k: pl.DataFrame(),
        get_daily=lambda *a, **k: pl.DataFrame({"date": [date(2026, 6, 29)]}),
        execute_one=lambda *a, **k: None,
    )
    app = FastAPI()
    app.include_router(kline_api.router)
    app.state.repo = repo
    app.state.capabilities = CapabilitySet()
    resp = TestClient(app).get("/api/kline/minute?symbol=000001.SZ&date=2026-06-29")
    assert resp.status_code == 200
    assert resp.json()["source"] == "none"
    assert resp.json()["rows"] == []


def test_leftover_tickflow_watchlist_minute_still_allows_tdx(monkeypatch, tmp_path):
    rows = pl.DataFrame({
        "symbol": ["301526.SZ"],
        "datetime": [datetime(2026, 6, 29, 9, 30)],
        "open": [50.92], "high": [50.92], "low": [50.92], "close": [50.92],
        "volume": [89645.0], "amount": [4562723.4],
    })
    monkeypatch.setattr(kline_sync, "minute_may_use_leftover_public", lambda: True)
    monkeypatch.setattr("app.services.watchlist.contains", lambda *a, **k: True)
    monkeypatch.setattr(
        "app.services.free_sources.tdx_history_minute.fetch_history_minute",
        lambda *a, **k: rows,
    )
    calls = []

    def fake_persist(candidate, _repo, symbol, trade_date, _daily, *, source, adapter):
        calls.append((source, adapter))
        return {"row_count": candidate.height}

    monkeypatch.setattr(kline_sync, "persist_historical_minute", fake_persist)
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        get_minute=lambda *a, **k: rows,
        get_daily=lambda *a, **k: pl.DataFrame({"date": [date(2026, 6, 29)]}),
        execute_one=lambda *a, **k: None,
    )
    app = FastAPI()
    app.include_router(kline_api.router)
    app.state.repo = repo
    resp = TestClient(app).get("/api/kline/minute?symbol=301526.SZ&date=2026-06-29")
    assert resp.status_code == 200
    assert resp.json()["provider"] == "easy_tdx_1.20.6"
    assert calls == [("tdx_public", "easy_tdx_1.20.6")]


def test_watchlist_quotes_prefs_failure_is_fail_closed(monkeypatch):
    qs = QuoteService.__new__(QuoteService)
    monkeypatch.setattr(preferences, "get_realtime_watchlist_symbols", lambda: ["000001.SZ"])
    monkeypatch.setattr(preferences, "get_realtime_data_provider", _prefs_boom)
    paid = MagicMock(side_effect=AssertionError("must not call TickFlow quotes"))
    monkeypatch.setattr("app.tickflow.client.get_paid_realtime_client", paid)
    public = MagicMock(side_effect=AssertionError("must not public-mix"))
    monkeypatch.setattr(qs, "_fetch_public_quote_rows", public)
    qs._fetch_watchlist_quotes()
    paid.assert_not_called()
    public.assert_not_called()


def test_watchlist_quotes_public_does_not_call_tickflow(monkeypatch):
    qs = QuoteService.__new__(QuoteService)
    monkeypatch.setattr(preferences, "get_realtime_watchlist_symbols", lambda: ["000001.SZ"])
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "public")
    paid = MagicMock(side_effect=AssertionError("public realtime must not TickFlow"))
    monkeypatch.setattr("app.tickflow.client.get_paid_realtime_client", paid)
    monkeypatch.setattr(qs, "_fetch_public_quote_rows", lambda *a, **k: [])
    qs._fetch_watchlist_quotes()
    paid.assert_not_called()


def test_full_market_quotes_prefs_failure_is_fail_closed(monkeypatch):
    qs = QuoteService.__new__(QuoteService)
    qs._repo = None
    monkeypatch.setattr(preferences, "get_realtime_data_provider", _prefs_boom)
    custom = MagicMock(side_effect=AssertionError("must not custom-mix"))
    tf = MagicMock(side_effect=AssertionError("must not TickFlow-mix"))
    pub = MagicMock(side_effect=AssertionError("must not public-mix"))
    monkeypatch.setattr(qs, "_fetch_custom_full_market_records", custom)
    monkeypatch.setattr(qs, "_fetch_tickflow_full_market_records", tf)
    monkeypatch.setattr(qs, "_fetch_public_full_market_records", pub)
    qs._fetch_full_market_quotes()
    custom.assert_not_called()
    tf.assert_not_called()
    pub.assert_not_called()


def test_custom_financial_uses_pipeline_scope_not_instruments(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    monkeypatch.setattr(preferences, "get_pipeline_universe_scope", lambda: "CSI300")
    inst = tmp_path / "instruments"
    inst.mkdir()
    pl.DataFrame({"symbol": ["000001.SZ", "600000.SH", "300750.SZ"]}).write_parquet(
        inst / "instruments.parquet",
    )
    monkeypatch.setattr(
        "app.services.universe_scope.resolve_symbols",
        lambda scope, **k: ["000001.SZ"] if scope == "CSI300" else ["600000.SH"],
    )
    assert financial_sync._get_symbols(tmp_path) == ["000001.SZ"]


def test_custom_financial_scope_failure_is_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    monkeypatch.setattr(preferences, "get_pipeline_universe_scope", lambda: "CSI300")
    monkeypatch.setattr(
        "app.services.universe_scope.resolve_symbols",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("pool empty")),
    )
    inst = tmp_path / "instruments"
    inst.mkdir()
    pl.DataFrame({"symbol": ["000001.SZ", "600000.SH"]}).write_parquet(inst / "instruments.parquet")
    assert financial_sync._get_symbols(tmp_path) == []


def test_tickflow_financial_still_uses_instruments(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    inst = tmp_path / "instruments"
    inst.mkdir()
    pl.DataFrame({"symbol": ["000001.SZ", "600000.SH"]}).write_parquet(inst / "instruments.parquet")
    assert financial_sync._get_symbols(tmp_path) == ["000001.SZ", "600000.SH"]


def test_update_data_providers_persists_custom_pool(tmp_path, monkeypatch):
    server = tmp_path / "server_preferences.json"
    server.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(preferences, "_server_path", lambda: server)
    monkeypatch.setattr(preferences, "_path", lambda: tmp_path / "user.json")
    monkeypatch.setattr(settings_api, "detect_capabilities", lambda: CapabilitySet())
    preferences._invalidate_cache()
    req = MagicMock()
    req.model_dump = lambda exclude_none: {"pool_provider": "fuyao_pool"}
    out = settings_api.update_data_providers(req, MagicMock())
    assert out["pool_provider"] == "fuyao_pool"
    assert preferences.get_pool_provider() == "fuyao_pool"


def test_dedicated_puts_accept_custom_names(tmp_path, monkeypatch):
    server = tmp_path / "server_preferences.json"
    server.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(preferences, "_server_path", lambda: server)
    preferences._invalidate_cache()
    assert settings_api.update_pool_provider(
        settings_api.PoolProviderPrefs(pool_provider="fuyao_pool"),
    )["pool_provider"] == "fuyao_pool"
    assert settings_api.update_financial_provider(
        settings_api.FinancialProviderPrefs(financial_provider="fuyao"),
    )["financial_provider"] == "fuyao"
    assert settings_api.update_adj_factor_provider(
        settings_api.AdjFactorProviderPrefs(adj_factor_provider="fuyao"),
    )["adj_factor_provider"] == "fuyao"


def test_delete_data_source_resets_custom_pool(tmp_path, monkeypatch):
    server = tmp_path / "server_preferences.json"
    server.write_text('{"pool_provider":"fuyao_pool"}', encoding="utf-8")
    monkeypatch.setattr(preferences, "_server_path", lambda: server)
    monkeypatch.setattr(settings_api, "detect_capabilities", lambda: CapabilitySet())
    monkeypatch.setattr("app.data_providers.custom.delete_config", lambda name: None)
    monkeypatch.setattr("app.data_providers.custom.load_all", lambda: None)
    preferences._invalidate_cache()
    settings_api.delete_data_source("fuyao_pool", MagicMock())
    assert preferences.get_pool_provider() == "public"


def test_capability_matrix_includes_pool(monkeypatch):
    from app.data_providers import custom as custom_sources
    from app.data_providers.capabilities import CAPABILITY_REGISTRY, build_capability_matrix

    monkeypatch.setattr(custom_sources, "list_plugins", lambda: [])
    monkeypatch.setattr(custom_sources, "list_sources", lambda: [])
    assert any(c["id"] == "pool" for c in CAPABILITY_REGISTRY)
    pool = next(c for c in CAPABILITY_REGISTRY if c["id"] == "pool")
    assert pool["field"] == "pool_provider"
    assert pool["default"] == "public"
    matrix = build_capability_matrix(
        {
            "daily_data_provider": "tickflow",
            "adj_factor_provider": "tickflow",
            "minute_data_provider": "tickflow",
            "full_minute_data_provider": "tickflow",
            "depth5_data_provider": "tickflow",
            "realtime_data_provider": "public",
            "financial_data_provider": "tickflow",
            "pool_provider": "public",
        },
        tickflow_tier="expert",
    )
    cap = next(c for c in matrix["capabilities"] if c["id"] == "pool")
    assert cap["effective"] == "public"
    assert cap["usable"] is True
    assert "public" in [c["name"] for c in cap["candidates"]]


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


def test_get_pool_skips_stale_cache_for_custom(monkeypatch, tmp_path):
    from app.tickflow import pools

    cache = tmp_path / "pools"
    cache.mkdir()
    pl.DataFrame({
        "symbol": ["000001.SZ", "600000.SH"],
        "as_of": [date(2026, 1, 1), date(2026, 1, 1)],
    }).write_parquet(cache / "CSI300.parquet")
    monkeypatch.setattr(
        pools,
        "_pool_cache_path",
        lambda pool_id: cache / f"{pool_id}.parquet",
    )
    monkeypatch.setattr(pools, "pool_route", lambda: "custom")
    monkeypatch.setattr(pools, "_fetch_pool", lambda pool_id: [])
    assert pools.get_pool("CSI300") == []


def test_get_pool_skips_tickflow_tagged_cache_for_public(monkeypatch, tmp_path):
    from app.tickflow import pools

    cache = tmp_path / "pools"
    cache.mkdir()
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "as_of": [date(2026, 1, 1)],
        "route": ["tickflow"],
    }).write_parquet(cache / "CSI300.parquet")
    monkeypatch.setattr(
        pools,
        "_pool_cache_path",
        lambda pool_id: cache / f"{pool_id}.parquet",
    )
    monkeypatch.setattr(pools, "pool_route", lambda: "public")
    monkeypatch.setattr(pools, "_fetch_pool", lambda pool_id: [])
    assert pools.get_pool("CSI300") == []


def test_custom_pool_uses_declared_provider(monkeypatch):
    from app.tickflow import pools

    class _P:
        def get_constituents(self, pool_id):
            return ["000001.SZ"] if pool_id == "CSI300" else []

    monkeypatch.setattr(preferences, "get_pool_provider", lambda: "fuyao_pool")
    monkeypatch.setattr(preferences, "is_public_pool_provider", lambda name=None: False)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: name == "fuyao_pool" and dataset == "pool",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda name: _P())
    tf = MagicMock(side_effect=AssertionError("must not TickFlow"))
    monkeypatch.setattr(pools, "get_client", tf)
    assert pools.pool_route() == "custom"
    assert pools._fetch_pool("CSI300") == ["000001.SZ"]
    tf.assert_not_called()


def test_pipeline_empty_custom_pool_skips_demo(monkeypatch):
    from app.tickflow import pools

    monkeypatch.setattr(daily_pipeline._prefs, "get_pipeline_universe_scope", lambda: "ALL")
    monkeypatch.setattr(pools, "pool_route", lambda: "custom")
    monkeypatch.setattr(
        daily_pipeline,
        "get_pool",
        lambda pool_id, **kwargs: (_ for _ in ()).throw(
            AssertionError(f"must not refresh {pool_id}")
        ),
    )
    monkeypatch.setattr(
        "app.services.universe_scope.resolve_symbols",
        lambda *a, **k: [],
    )
    assert daily_pipeline.resolve_universe(_capset(Cap.KLINE_DAILY_BATCH)) == []


def test_extend_history_empty_custom_pool_skips_demo(monkeypatch):
    from app.services import extend_history
    from app.tickflow import pools

    monkeypatch.setattr(
        "app.services.preferences.get_pipeline_universe_scope",
        lambda: "ALL",
    )
    monkeypatch.setattr(pools, "pool_route", lambda: "custom")
    monkeypatch.setattr(
        "app.tickflow.pools.get_pool",
        lambda pool_id, **kwargs: (_ for _ in ()).throw(
            AssertionError(f"must not refresh {pool_id}")
        ),
    )
    monkeypatch.setattr(
        "app.services.universe_scope.resolve_symbols",
        lambda *a, **k: [],
    )
    assert extend_history._resolve_universe(_capset(Cap.KLINE_DAILY_BATCH)) == []


def test_resolve_all_custom_pool_skips_tickflow_cache_and_demo(monkeypatch, tmp_path):
    from app.services import universe_scope
    from app.tickflow import pools

    monkeypatch.setattr(pools, "pool_route", lambda: "custom")
    monkeypatch.setattr(
        pools,
        "get_pool",
        lambda pool_id, **kwargs: (_ for _ in ()).throw(
            AssertionError(f"must not expand {pool_id}")
        ),
    )
    assert universe_scope.resolve_symbols("ALL", data_dir=tmp_path) == []


def test_ensure_csi_skips_stale_disk_for_custom(monkeypatch, tmp_path):
    from app.services import universe_scope
    from app.tickflow import pools

    pools_dir = tmp_path / "pools"
    pools_dir.mkdir()
    pl.DataFrame({"symbol": ["000001.SZ"]}).write_parquet(pools_dir / "CSI300.parquet")
    monkeypatch.setattr(pools, "pool_route", lambda: "custom")
    public_sync = MagicMock(side_effect=AssertionError("must not public-sync"))
    monkeypatch.setattr(
        "app.data_providers.registry.get_provider",
        lambda name: SimpleNamespace(sync_pools=public_sync),
    )
    assert universe_scope._ensure_csi_pool("CSI300", tmp_path) == []
    public_sync.assert_not_called()


def test_leftover_adj_live_without_cap_uses_public(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr(
        kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: False,
    )
    public = MagicMock(return_value=pl.DataFrame({
        "symbol": ["000001.SZ"],
        "trade_date": [date(2020, 6, 1)],
        "ex_factor": [1.1],
    }))
    monkeypatch.setattr(
        "app.services.free_sources.adj_factor_public.fetch_adj_factors_symbol",
        public,
    )
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow without ADJ cap"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    assert kline_sync.adj_live_fetch_allowed(CapabilitySet()) is False
    out = kline_sync.fetch_adj_factor_single("000001.SZ", capset=CapabilitySet())
    assert out.is_empty()
    public.assert_not_called()
    tf.assert_not_called()


def test_leftover_adj_live_with_cap_still_uses_tickflow(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr(
        kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: False,
    )
    mock_tf = MagicMock()
    mock_tf.klines.ex_factors.return_value = pl.DataFrame({
        "symbol": ["000001.SZ"],
        "trade_date": [date(2020, 6, 1)],
        "ex_factor": [1.2],
    })
    monkeypatch.setattr(kline_sync, "get_client", lambda: mock_tf)
    public = MagicMock(side_effect=AssertionError("must not public when entitled"))
    monkeypatch.setattr(
        "app.services.free_sources.adj_factor_public.fetch_adj_factors_symbol",
        public,
    )
    out = kline_sync.fetch_adj_factor_single("000001.SZ", capset=_capset(Cap.ADJ_FACTOR))
    assert out["ex_factor"].to_list() == [1.2]
    mock_tf.klines.ex_factors.assert_called()
    public.assert_not_called()


def test_sync_and_persist_minute_prefs_failure_is_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", _prefs_boom)
    tf = MagicMock(side_effect=AssertionError("must not TickFlow minute persist"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    written = kline_sync.sync_and_persist_minute(
        ["000001.SZ"],
        KlineRepository(DataStore(tmp_path)),
        _capset(Cap.KLINE_MINUTE_BATCH),
    )
    assert written == 0
    tf.assert_not_called()


def test_intraday_monitor_support_prefs_failure_is_unavailable(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", _prefs_boom)
    info = kline_sync.intraday_monitor_support(_capset(Cap.KLINE_MINUTE_BATCH))
    assert info["available"] is False
    assert info["source"] is None


def test_undeclared_depth_label_is_unavailable(monkeypatch):
    from app.tickflow.capabilities import feature_availability

    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "public")
    monkeypatch.setattr("app.services.preferences.get_depth5_data_provider", lambda: "depth_src")
    monkeypatch.setattr("app.services.preferences.get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_minute_data_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.is_public_financial_provider", lambda: False)
    monkeypatch.setattr("app.services.preferences.is_public_adj_factor_provider", lambda: False)
    monkeypatch.setattr("app.services.financial_normalize.local_financials_ready", lambda d: False)
    monkeypatch.setattr("app.services.financial_normalize.local_adj_factor_ready", lambda d: False)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: False,
    )
    feats = feature_availability(CapabilitySet())
    assert feats["depth"]["available"] is False
    assert feats["depth"]["source"] == "depth_src"
    assert feats["depth"]["status"] == "unavailable"


def test_undeclared_realtime_label_is_unavailable(monkeypatch):
    from app.tickflow.capabilities import feature_availability

    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "fuyao")
    monkeypatch.setattr("app.services.preferences.get_depth5_data_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_minute_data_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.is_public_financial_provider", lambda: False)
    monkeypatch.setattr("app.services.preferences.is_public_adj_factor_provider", lambda: False)
    monkeypatch.setattr("app.services.financial_normalize.local_financials_ready", lambda d: False)
    monkeypatch.setattr("app.services.financial_normalize.local_adj_factor_ready", lambda d: False)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: False,
    )
    feats = feature_availability(_capset(Cap.QUOTE_BATCH))
    assert feats["quote"]["available"] is False
    assert feats["quote"]["source"] == "fuyao"
    assert feats["quote"]["mode"] == "none"


def test_watchlist_fetch_quotes_public_is_fail_closed(monkeypatch):
    from app.services import watchlist

    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "public")
    paid = MagicMock(side_effect=AssertionError("must not TickFlow"))
    monkeypatch.setattr(watchlist, "get_client", paid)
    assert watchlist.fetch_quotes(["000001.SZ"], _capset(Cap.QUOTE_BATCH)) == []
    paid.assert_not_called()


def test_minute_refresh_status_unresolved_is_not_available(monkeypatch, tmp_path):
    from app.services.minute_refresh import MinuteRefreshService

    monkeypatch.setattr(preferences, "get_full_minute_data_provider", _prefs_boom)
    monkeypatch.setattr(preferences, "get_minute_refresh_enabled", lambda: False)
    monkeypatch.setattr(preferences, "get_minute_refresh_interval", lambda: 6)
    svc = MinuteRefreshService(SimpleNamespace())
    st = svc.status()
    assert st["provider_effective"] == "unresolved"
    assert st["available"] is False
    assert st["provider"] == ""
