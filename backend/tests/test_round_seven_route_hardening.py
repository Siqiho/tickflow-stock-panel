"""Seventh-round leftover mix-source / fail-open paths.

Keeps prior TickFlow leftover contracts:
- leftover TickFlow + free realtime stays mode=none
- undeclared daily / minute / full_minute / adj still fall back to TickFlow
- leftover TickFlow + no ADJ cap still uses the public sina adapter
- entitled TickFlow minute fallback after a custom *call* failure
- TickFlow default depth empty result may still use public L1
- leftover TickFlow single-symbol minute view may still use public intraday
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl

from app.api import kline as kline_api
from app.jobs import daily_pipeline
from app.services import kline_sync, preferences
from app.services.depth_service import DepthService
from app.services.minute_refresh import MinuteRefreshService
from app.services.quote_service import QuoteService
from app.tickflow import pools
from app.tickflow.capabilities import (
    Cap,
    CapabilityLimits,
    CapabilitySet,
    daily_availability,
    feature_availability,
    minute_availability,
)
from app.tickflow.repository import DataStore, KlineRepository


def _capset(*caps: Cap) -> CapabilitySet:
    return CapabilitySet({c: CapabilityLimits(rpm=60, batch=100) for c in caps})


def _feat_patches(monkeypatch, **providers):
    defaults = {
        "get_realtime_data_provider": "tickflow",
        "get_financial_provider": "tickflow",
        "get_adj_factor_provider": "tickflow",
        "get_depth5_data_provider": "tickflow",
        "get_minute_data_provider": "tickflow",
        "get_daily_data_provider": "tickflow",
    }
    defaults.update(providers)
    for name, value in defaults.items():
        monkeypatch.setattr(f"app.services.preferences.{name}", lambda v=value: v)
    monkeypatch.setattr("app.services.preferences.is_public_financial_provider", lambda: False)
    monkeypatch.setattr("app.services.preferences.is_public_adj_factor_provider", lambda: False)
    monkeypatch.setattr("app.services.financial_normalize.local_financials_ready", lambda d: False)
    monkeypatch.setattr("app.services.financial_normalize.local_adj_factor_ready", lambda d: False)


def test_getters_preserve_custom_when_registry_empty(tmp_path, monkeypatch):
    server = tmp_path / "server_preferences.json"
    server.write_text(
        '{"daily_data_provider":"fuyao","minute_data_provider":"sdk",'
        '"full_minute_data_provider":"myfm","depth5_data_provider":"depth_src",'
        '"adj_factor_provider":"fuyao","realtime_data_provider":"fuyao",'
        '"financial_provider":"sdk"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(preferences, "_server_path", lambda: server)
    monkeypatch.setattr(preferences, "_allowed_data_providers", lambda: {"tickflow"})
    preferences._invalidate_cache()

    assert preferences.get_daily_data_provider() == "fuyao"
    assert preferences.get_minute_data_provider() == "sdk"
    assert preferences.get_full_minute_data_provider() == "myfm"
    assert preferences.get_depth5_data_provider() == "depth_src"
    assert preferences.get_adj_factor_provider() == "fuyao"
    assert preferences.get_realtime_data_provider() == "fuyao"
    assert preferences.get_financial_provider() == "sdk"


def test_getters_preserve_custom_when_names_raise(tmp_path, monkeypatch):
    server = tmp_path / "server_preferences.json"
    server.write_text('{"realtime_data_provider":"fuyao","daily_data_provider":"fuyao"}', encoding="utf-8")
    monkeypatch.setattr(preferences, "_server_path", lambda: server)
    monkeypatch.setattr(
        "app.data_providers.custom.names",
        lambda: (_ for _ in ()).throw(RuntimeError("registry down")),
    )
    preferences._invalidate_cache()
    assert preferences.get_realtime_data_provider() == "fuyao"
    assert preferences.get_daily_data_provider() == "fuyao"


def test_realtime_aliases_still_map_to_public(tmp_path, monkeypatch):
    server = tmp_path / "server_preferences.json"
    server.write_text('{"realtime_data_provider":"tencent"}', encoding="utf-8")
    monkeypatch.setattr(preferences, "_server_path", lambda: server)
    preferences._invalidate_cache()
    assert preferences.get_realtime_data_provider() == "public"


def test_depth_public_is_not_healed_to_tickflow(tmp_path, monkeypatch):
    server = tmp_path / "server_preferences.json"
    server.write_text('{"depth5_data_provider":"public"}', encoding="utf-8")
    monkeypatch.setattr(preferences, "_server_path", lambda: server)
    monkeypatch.setattr(preferences, "_allowed_data_providers", lambda: {"tickflow"})
    preferences._invalidate_cache()
    assert preferences.get_depth5_data_provider() == "public"


def test_unset_defaults_unchanged(tmp_path, monkeypatch):
    server = tmp_path / "server_preferences.json"
    server.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(preferences, "_server_path", lambda: server)
    preferences._invalidate_cache()
    assert preferences.get_daily_data_provider() == "tickflow"
    assert preferences.get_realtime_data_provider() == "public"
    assert preferences.get_depth5_data_provider() == "tickflow"


def test_preserved_custom_realtime_does_not_public_mix(monkeypatch):
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: False,
    )
    public = MagicMock(side_effect=AssertionError("must not mix public realtime"))
    qs = QuoteService.__new__(QuoteService)
    qs._repo = None
    monkeypatch.setattr(qs, "_fetch_public_full_market_records", public)
    monkeypatch.setattr(qs, "_fetch_tickflow_full_market_records", public)
    records, replace = qs._fetch_custom_full_market_records()
    assert records == []
    assert replace is False
    public.assert_not_called()


def test_public_depth_does_not_call_tickflow_even_with_cap(monkeypatch):
    monkeypatch.setattr(
        "app.services.preferences.get_depth5_data_provider",
        lambda: "public",
    )
    svc = DepthService()
    svc._app_state = SimpleNamespace(capabilities=_capset(Cap.DEPTH5_BATCH))
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow depth"))
    monkeypatch.setattr(svc, "_call_tickflow_depth_batch", tf)
    monkeypatch.setattr(svc, "_call_routed_depth_batch", tf)
    monkeypatch.setattr(svc, "_call_public_depth_l1", lambda symbols: {"A": {"ask_volumes": [1]}})
    assert svc._call_depth_batch(["A"]) == {"A": {"ask_volumes": [1]}}
    tf.assert_not_called()
    assert svc._depth_source() == "local_public"


def test_depth_prefs_failure_is_fail_closed(monkeypatch):
    monkeypatch.setattr(
        "app.services.preferences.get_depth5_data_provider",
        lambda: (_ for _ in ()).throw(RuntimeError("prefs unreadable")),
    )
    svc = DepthService()
    public = MagicMock(side_effect=AssertionError("must not mix public L1"))
    monkeypatch.setattr(svc, "_call_public_depth_l1", public)
    assert svc._call_depth_batch(["A"]) == {}
    assert svc._depth_source() == "none"
    public.assert_not_called()


def test_feature_public_realtime_with_quote_cap_is_local_public(monkeypatch):
    _feat_patches(monkeypatch, get_realtime_data_provider="public")
    feats = feature_availability(_capset(Cap.QUOTE_BATCH, Cap.KLINE_DAILY_BATCH))
    assert feats["quote"]["source"] == "local_public"
    assert feats["quote"]["mode"] == "full_market_public"
    assert feats["quote"]["status"] == "public_fallback"


def test_feature_public_depth_with_tickflow_cap_is_local_public(monkeypatch):
    _feat_patches(monkeypatch, get_depth5_data_provider="public")
    feats = feature_availability(_capset(Cap.DEPTH5_BATCH))
    assert feats["depth"]["source"] == "local_public"
    assert feats["depth"]["status"] == "public_fallback"
    assert feats["depth"]["fallback"] is None


def test_daily_availability_custom_without_tickflow_cap(monkeypatch):
    monkeypatch.setattr(preferences, "get_daily_data_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: name == "fuyao" and dataset == "daily",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda name: object())
    info = daily_availability(CapabilitySet())
    assert info["available"] is True
    assert info["source"] == "fuyao"
    assert info["reason_code"] == "ok"


def test_daily_availability_resolve_failure_is_unavailable(monkeypatch):
    monkeypatch.setattr(preferences, "get_daily_data_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: (_ for _ in ()).throw(RuntimeError("registry down")),
    )
    info = daily_availability(_capset(Cap.KLINE_DAILY_BATCH))
    assert info["available"] is False
    assert info["reason_code"] == "resolve_failed"
    assert info["source"] == "fuyao"


def test_minute_allowed_resolve_fail_ignores_tickflow_cap(monkeypatch):
    monkeypatch.setattr(preferences, "get_minute_data_provider", lambda: "sdk")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: (_ for _ in ()).throw(RuntimeError("registry down")),
    )
    assert kline_api._minute_allowed(_capset(Cap.KLINE_MINUTE_BATCH)) is False
    assert kline_sync.minute_sync_allowed(_capset(Cap.KLINE_MINUTE_BATCH)) is False


def test_minute_availability_resolve_fail_does_not_advertise_public(monkeypatch):
    monkeypatch.setattr(preferences, "get_minute_data_provider", lambda: "sdk")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: (_ for _ in ()).throw(RuntimeError("registry down")),
    )
    info = minute_availability(_capset(Cap.KLINE_MINUTE_BATCH), user_enabled=True)
    assert info["available"] is False
    assert info["view_available"] is False
    assert info["reason_code"] == "resolve_failed"
    assert info["source"] == "sdk"
    assert info["single_symbol_fallback"] is None


def test_adj_prefs_failure_does_not_mix(monkeypatch, tmp_path):
    monkeypatch.setattr(
        kline_sync.preferences,
        "get_adj_factor_provider",
        lambda: (_ for _ in ()).throw(RuntimeError("prefs unreadable")),
    )
    public = MagicMock(side_effect=AssertionError("must not use public sina"))
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr(kline_sync, "_sync_public_adj_factor", public)
    monkeypatch.setattr(kline_sync, "get_client", tf)

    rows, symbols = kline_sync.sync_adj_factor(
        ["000001.SZ"],
        KlineRepository(DataStore(tmp_path)),
        _capset(Cap.ADJ_FACTOR),
    )
    assert rows == 0
    assert symbols == []
    assert kline_sync.fetch_adj_factor_single("000001.SZ").is_empty()
    assert kline_sync.adj_live_fetch_allowed(_capset(Cap.ADJ_FACTOR)) is False
    assert daily_pipeline.adj_sync_uses_public_adapter(CapabilitySet()) is False
    public.assert_not_called()
    tf.assert_not_called()


def test_minute_refresh_prefs_failure_does_not_tickflow(monkeypatch):
    monkeypatch.setattr(
        preferences,
        "get_full_minute_data_provider",
        lambda: (_ for _ in ()).throw(RuntimeError("prefs unreadable")),
    )
    burst = MagicMock(side_effect=AssertionError("must not burst TickFlow"))
    increment = MagicMock(side_effect=AssertionError("must not increment TickFlow"))
    monkeypatch.setattr(kline_sync, "fetch_intraday_full_market_burst", burst)
    monkeypatch.setattr(kline_sync, "fetch_intraday_universe_increment", increment)
    svc = MinuteRefreshService(MagicMock())
    svc._run_round()
    assert "unresolved" in (svc._state.last_error or "")
    burst.assert_not_called()
    increment.assert_not_called()


def test_public_pool_prefs_failure_does_not_call_tickflow(monkeypatch):
    monkeypatch.setattr(
        "app.services.preferences.is_public_pool_provider",
        lambda name=None: (_ for _ in ()).throw(RuntimeError("prefs unreadable")),
    )
    get_client = MagicMock(side_effect=AssertionError("must not fall back to TickFlow"))
    monkeypatch.setattr("app.tickflow.pools.get_client", get_client)
    assert pools._fetch_pool("CN_Equity_A") == []
    get_client.assert_not_called()


def test_extend_history_public_pool_skips_tickflow_all_a(monkeypatch):
    from app.services import extend_history
    from app.tickflow import pools

    monkeypatch.setattr(
        "app.services.preferences.is_public_pool_provider",
        lambda name=None: True,
    )
    monkeypatch.setattr(pools, "pool_route", lambda: "public")
    def _pool(pool_id, **kwargs):
        if pool_id == "CN_Equity_A":
            raise AssertionError("must not refresh CN_Equity_A via TickFlow")
        return []

    monkeypatch.setattr("app.tickflow.pools.get_pool", _pool)
    symbols = extend_history._resolve_universe(_capset(Cap.KLINE_DAILY_BATCH))
    assert "600000.SH" in symbols


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
    assert hit["public"] is True
    assert rows == 1
    assert symbols == ["000001.SZ"]


def test_declared_daily_resolve_failure_still_skips_tickflow(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: True,
    )
    monkeypatch.setattr(
        "app.data_providers.custom.get_provider",
        lambda name: (_ for _ in ()).throw(RuntimeError("registry down")),
    )
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    monkeypatch.setattr(kline_sync, "sync_daily_batch", tf)
    written = kline_sync.sync_and_persist_daily_batch(
        ["000001.SZ"],
        KlineRepository(DataStore(tmp_path)),
        _capset(Cap.KLINE_DAILY_BATCH),
    )
    assert written == 0
    tf.assert_not_called()


def test_fetch_minute_single_leftover_tickflow_keeps_public(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    monkeypatch.setattr(
        kline_sync,
        "get_client",
        lambda: (_ for _ in ()).throw(RuntimeError("tickflow down")),
    )
    monkeypatch.setattr(
        kline_sync,
        "_public_minute_fallback",
        lambda symbol, trade_date: pl.DataFrame({
            "symbol": [symbol],
            "datetime": [datetime(2026, 7, 17, 9, 31)],
            "open": [10.0], "high": [10.1], "low": [9.9], "close": [10.0],
            "volume": [1.0], "amount": [1000.0],
        }),
    )
    out = kline_sync.fetch_minute_single("600000.SH", date(2026, 7, 17), capset=CapabilitySet())
    assert out["symbol"].to_list() == ["600000.SH"]
