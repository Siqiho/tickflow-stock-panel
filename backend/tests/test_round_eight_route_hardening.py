"""Eighth-round leftover mix-source / fail-open paths.

Keeps prior TickFlow leftover contracts:
- leftover TickFlow + free realtime stays mode=none
- undeclared daily / minute / full_minute / adj still fall back to TickFlow
- leftover TickFlow + no ADJ cap still uses the public sina adapter
- entitled TickFlow minute fallback after a custom *call* failure
- TickFlow default depth empty result may still use public L1
- leftover TickFlow single-symbol minute view no longer uses public intraday
"""
from __future__ import annotations

import inspect
from datetime import date, datetime
from unittest.mock import MagicMock

import polars as pl

from app.api import financials as financials_api
from app.api import kline as kline_api
from app.jobs import daily_pipeline
from app.services import extend_history, financial_sync, kline_sync, preferences
from app.services.quote_service import QuoteService
from app.services.universe_scope import tickflow_all_a_expansion_allowed
from app.tickflow import pools
from app.tickflow.capabilities import (
    Cap,
    CapabilityLimits,
    CapabilitySet,
    daily_availability,
    feature_availability,
)
from app.tickflow.repository import DataStore, KlineRepository


def _capset(*caps: Cap) -> CapabilitySet:
    return CapabilitySet({c: CapabilityLimits(rpm=60, batch=100) for c in caps})


def test_get_pool_provider_preserves_custom_when_registry_empty(tmp_path, monkeypatch):
    server = tmp_path / "server_preferences.json"
    server.write_text('{"pool_provider":"fuyao_pool"}', encoding="utf-8")
    monkeypatch.setattr(preferences, "_server_path", lambda: server)
    monkeypatch.setattr(preferences, "_allowed_data_providers", lambda: {"tickflow"})
    preferences._invalidate_cache()
    assert preferences.get_pool_provider() == "fuyao_pool"
    assert preferences.is_public_pool_provider() is False


def test_get_pool_provider_unset_still_defaults_public(tmp_path, monkeypatch):
    server = tmp_path / "server_preferences.json"
    server.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(preferences, "_server_path", lambda: server)
    preferences._invalidate_cache()
    assert preferences.get_pool_provider() == "public"


def test_custom_pool_does_not_call_tickflow(monkeypatch):
    monkeypatch.setattr(preferences, "get_pool_provider", lambda: "fuyao_pool")
    monkeypatch.setattr(preferences, "is_public_pool_provider", lambda name=None: False)
    get_client = MagicMock(side_effect=AssertionError("must not fall back to TickFlow"))
    monkeypatch.setattr("app.tickflow.pools.get_client", get_client)
    assert pools.pool_route() == "custom"
    assert pools._fetch_pool("CN_Equity_A") == []
    assert pools._fetch_pool("CSI300") == []
    get_client.assert_not_called()


def test_pool_prefs_unreadable_does_not_call_tickflow_or_public(monkeypatch):
    monkeypatch.setattr(
        preferences,
        "get_pool_provider",
        lambda: (_ for _ in ()).throw(RuntimeError("prefs unreadable")),
    )
    get_client = MagicMock(side_effect=AssertionError("must not fall back to TickFlow"))
    monkeypatch.setattr("app.tickflow.pools.get_client", get_client)
    public = MagicMock(side_effect=AssertionError("must not fetch public CSI"))
    monkeypatch.setattr(
        "app.services.free_sources.pools_public.fetch_pool_constituents",
        public,
    )
    assert pools.pool_route() == "unresolved"
    assert pools._fetch_pool("CN_Equity_A") == []
    assert pools._fetch_pool("CSI300") == []
    get_client.assert_not_called()
    public.assert_not_called()


def test_tickflow_pool_still_uses_client(monkeypatch):
    monkeypatch.setattr(preferences, "get_pool_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "is_public_pool_provider", lambda name=None: False)
    tf = MagicMock()
    tf.universes.list.return_value = []
    monkeypatch.setattr("app.tickflow.pools.get_client", lambda: tf)
    assert pools.pool_route() == "tickflow"
    assert pools._fetch_pool("CN_Index") == []
    tf.quotes.get_by_universes.assert_called()


def test_resolve_universe_custom_daily_skips_tickflow_all_a(monkeypatch):
    monkeypatch.setattr(daily_pipeline._prefs, "get_pipeline_universe_scope", lambda: "ALL")
    monkeypatch.setattr(pools, "pool_route", lambda: "tickflow")
    monkeypatch.setattr(kline_sync, "daily_provider_is_custom", lambda: True)
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


def test_resolve_universe_custom_pool_skips_tickflow_all_a(monkeypatch):
    monkeypatch.setattr(daily_pipeline._prefs, "get_pipeline_universe_scope", lambda: "ALL")
    monkeypatch.setattr(pools, "pool_route", lambda: "custom")
    monkeypatch.setattr(kline_sync, "daily_provider_is_custom", lambda: False)
    monkeypatch.setattr(
        daily_pipeline,
        "get_pool",
        lambda pool_id, **kwargs: (_ for _ in ()).throw(
            AssertionError(f"must not refresh {pool_id} via TickFlow")
        ),
    )
    monkeypatch.setattr(
        "app.services.universe_scope.resolve_symbols",
        lambda *a, **k: ["600000.SH"],
    )
    symbols = daily_pipeline.resolve_universe(_capset(Cap.KLINE_DAILY_BATCH))
    assert symbols == ["600000.SH"]


def test_tickflow_all_a_allowed_only_for_leftover_tickflow(monkeypatch):
    monkeypatch.setattr(pools, "pool_route", lambda: "tickflow")
    monkeypatch.setattr(kline_sync, "daily_provider_is_custom", lambda: False)
    monkeypatch.setattr(kline_sync, "leftover_tickflow_follow_daily", lambda: True)
    assert tickflow_all_a_expansion_allowed(_capset(Cap.KLINE_DAILY_BATCH), scope="ALL") is True
    assert tickflow_all_a_expansion_allowed(_capset(Cap.KLINE_DAILY_BATCH), scope="CSI300") is False
    monkeypatch.setattr(kline_sync, "daily_provider_is_custom", lambda: True)
    assert tickflow_all_a_expansion_allowed(_capset(Cap.KLINE_DAILY_BATCH), scope="ALL") is False
    monkeypatch.setattr(kline_sync, "daily_provider_is_custom", lambda: False)
    monkeypatch.setattr(kline_sync, "leftover_tickflow_follow_daily", lambda: False)
    assert tickflow_all_a_expansion_allowed(_capset(Cap.KLINE_DAILY_BATCH), scope="ALL") is False
    monkeypatch.setattr(kline_sync, "leftover_tickflow_follow_daily", lambda: True)
    monkeypatch.setattr(pools, "pool_route", lambda: "public")
    assert tickflow_all_a_expansion_allowed(_capset(Cap.KLINE_DAILY_BATCH), scope="ALL") is False


def test_extend_history_custom_daily_skips_tickflow_all_a(monkeypatch):
    monkeypatch.setattr(
        "app.services.preferences.get_pipeline_universe_scope",
        lambda: "ALL",
    )
    monkeypatch.setattr(pools, "pool_route", lambda: "tickflow")
    monkeypatch.setattr(kline_sync, "daily_provider_is_custom", lambda: True)
    monkeypatch.setattr(
        "app.tickflow.pools.get_pool",
        lambda pool_id, **kwargs: (_ for _ in ()).throw(
            AssertionError(f"must not refresh {pool_id} via TickFlow")
        ),
    )
    monkeypatch.setattr(
        "app.services.universe_scope.resolve_symbols",
        lambda *a, **k: ["000338.SZ"],
    )
    symbols = extend_history._resolve_universe(_capset(Cap.KLINE_DAILY_BATCH))
    assert symbols == ["000338.SZ"]


def test_extend_history_honors_csi_scope(monkeypatch):
    monkeypatch.setattr(
        "app.services.preferences.get_pipeline_universe_scope",
        lambda: "CSI300",
    )
    monkeypatch.setattr(pools, "pool_route", lambda: "tickflow")
    monkeypatch.setattr(kline_sync, "daily_provider_is_custom", lambda: False)
    monkeypatch.setattr(
        "app.tickflow.pools.get_pool",
        lambda pool_id, **kwargs: (_ for _ in ()).throw(
            AssertionError(f"must not refresh {pool_id} via TickFlow ALL")
        ),
    )
    monkeypatch.setattr(
        "app.services.universe_scope.resolve_symbols",
        lambda scope, **k: ["000001.SZ"] if scope == "CSI300" else [],
    )
    symbols = extend_history._resolve_universe(_capset(Cap.KLINE_DAILY_BATCH))
    assert symbols == ["000001.SZ"]


def test_sync_minute_http_uses_shared_universe_resolver():
    source = inspect.getsource(kline_api.sync_minute)
    assert "_resolve_minute_universe" in source
    assert "CN_Equity_A" not in source


def test_ensure_csi_pool_tickflow_skips_public_sync(monkeypatch, tmp_path):
    from app.services import universe_scope

    monkeypatch.setattr(pools, "pool_route", lambda: "tickflow")
    monkeypatch.setattr(
        "app.services.free_sources.pools_public.load_pool_symbols",
        lambda *a, **k: [],
    )
    public_sync = MagicMock(side_effect=AssertionError("must not public-sync under TickFlow pool"))
    monkeypatch.setattr(
        "app.data_providers.registry.get_provider",
        lambda name: SimplePublic(public_sync) if name == "public" else None,
    )
    monkeypatch.setattr(pools, "get_pool", lambda pool_id, **kwargs: ["000001.SZ"])
    out = universe_scope._ensure_csi_pool("CSI300", tmp_path, refresh_if_missing=True)
    assert out == ["000001.SZ"]
    public_sync.assert_not_called()


class SimplePublic:
    def __init__(self, sync_pools):
        self.sync_pools = sync_pools


def test_ensure_csi_pool_custom_is_fail_closed(monkeypatch, tmp_path):
    from app.services import universe_scope

    monkeypatch.setattr(pools, "pool_route", lambda: "custom")
    monkeypatch.setattr(
        "app.services.free_sources.pools_public.load_pool_symbols",
        lambda *a, **k: [],
    )
    public_sync = MagicMock(side_effect=AssertionError("must not public-sync under custom pool"))
    monkeypatch.setattr(
        "app.data_providers.registry.get_provider",
        lambda name: SimplePublic(public_sync) if name == "public" else None,
    )
    monkeypatch.setattr(
        pools,
        "get_pool",
        lambda pool_id, **kwargs: (_ for _ in ()).throw(AssertionError("must not TickFlow")),
    )
    assert universe_scope._ensure_csi_pool("CSI300", tmp_path, refresh_if_missing=True) == []
    public_sync.assert_not_called()


def test_daily_availability_prefs_failure_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        preferences,
        "get_daily_data_provider",
        lambda: (_ for _ in ()).throw(RuntimeError("prefs unreadable")),
    )
    info = daily_availability(_capset(Cap.KLINE_DAILY_BATCH))
    assert info["available"] is False
    assert info["reason_code"] == "resolve_failed"
    assert info["source"] == "none"


def test_feature_undeclared_minute_keeps_tickflow_source(monkeypatch):
    monkeypatch.setattr(preferences, "get_minute_data_provider", lambda: "sdk")
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda: False)
    monkeypatch.setattr(preferences, "is_public_adj_factor_provider", lambda: False)
    monkeypatch.setattr("app.services.financial_normalize.local_financials_ready", lambda d: False)
    monkeypatch.setattr("app.services.financial_normalize.local_adj_factor_ready", lambda d: False)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: False,
    )
    feats = feature_availability(_capset(Cap.KLINE_MINUTE_BATCH), minute_user_enabled=True)
    assert feats["minute"]["source"] == "sdk"
    assert feats["minute"]["status"] == "unavailable"


def test_financial_prefs_failure_does_not_tickflow(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.preferences.get_financial_provider",
        lambda: (_ for _ in ()).throw(RuntimeError("prefs unreadable")),
    )
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow financials"))
    monkeypatch.setattr("app.tickflow.client.get_client", tf)
    rows = financial_sync._sync_table(
        "income",
        ["000001.SZ"],
        tmp_path,
        _capset(Cap.FINANCIAL),
        latest_only=True,
    )
    assert rows == 0
    assert financial_sync.financials_live_allowed(_capset(Cap.FINANCIAL)) is False
    tf.assert_not_called()


def test_public_financial_scope_failure_does_not_widen(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "public")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: True)
    monkeypatch.setattr(preferences, "get_public_data_scope", lambda: "CSI300")
    monkeypatch.setattr(
        "app.services.universe_scope.resolve_symbols",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("pool empty")),
    )
    inst = tmp_path / "instruments"
    inst.mkdir()
    pl.DataFrame({"symbol": ["000001.SZ", "600000.SH"]}).write_parquet(inst / "instruments.parquet")
    assert financial_sync._get_symbols(tmp_path) == []


def test_financial_scheduler_allows_custom_without_tickflow_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    monkeypatch.setattr(preferences, "get_financial_sync_times", lambda: {})
    sched = financial_sync.FinancialScheduler()
    sched.start(tmp_path, CapabilitySet(), auto_schedule=False)
    assert sched._data_dir == tmp_path
    assert financial_sync.financials_live_allowed(CapabilitySet()) is True
    assert financials_api._fin_available(CapabilitySet(), None) is True


def test_financial_scheduler_run_now_custom_without_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    monkeypatch.setattr(financial_sync, "_get_symbols", lambda data_dir: ["000001.SZ"])
    monkeypatch.setattr(financial_sync, "_sync_table", lambda *a, **k: 3)
    monkeypatch.setattr(financial_sync, "_refresh_financials_views", lambda data_dir: None)
    sched = financial_sync.FinancialScheduler()
    sched._data_dir = tmp_path
    sched._capset = CapabilitySet()
    assert sched.run_now("income") == {"income": 3}


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


def test_leftover_tickflow_adj_without_cap_still_uses_public(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda: False)
    hit = {"public": False}
    monkeypatch.setattr(
        kline_sync,
        "_sync_public_adj_factor",
        lambda *a, **k: (hit.__setitem__("public", True) or (1, ["000001.SZ"])),
    )
    rows, symbols = kline_sync.sync_adj_factor(
        ["000001.SZ"],
        KlineRepository(DataStore(tmp_path)),
        CapabilitySet(),
    )
    assert hit["public"] is False
    assert rows == 0
    assert symbols == []


def test_fetch_minute_single_leftover_tickflow_skips_public(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    monkeypatch.setattr(
        kline_sync,
        "get_client",
        lambda: (_ for _ in ()).throw(RuntimeError("tickflow down")),
    )
    public = MagicMock(side_effect=AssertionError("must not mix public minute"))
    monkeypatch.setattr(kline_sync, "_public_minute_fallback", public)
    out = kline_sync.fetch_minute_single("600000.SH", date(2026, 7, 17), capset=CapabilitySet())
    assert out.is_empty()
    public.assert_not_called()
