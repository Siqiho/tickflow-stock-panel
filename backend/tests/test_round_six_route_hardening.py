"""Sixth-round leftover mix-source / fail-open paths.

Keeps prior contracts:
- leftover TickFlow + free realtime stays mode=none
- undeclared daily / minute / full_minute / adj still fall back to TickFlow
- leftover TickFlow + no ADJ cap still uses the public sina adapter
- entitled TickFlow minute fallback after a custom *call* failure
- TickFlow default depth empty result may still use public L1
- leftover TickFlow single-symbol minute view may still use public intraday
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

import polars as pl

from app.jobs import daily_pipeline
from app.services import kline_sync, minute_refresh
from app.services.minute_refresh import MinuteRefreshService
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet, feature_availability
from app.tickflow.repository import DataStore, KlineRepository


def _minute(symbol: str = "600000.SH") -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": [symbol],
        "datetime": [datetime(2026, 7, 17, 9, 31)],
        "open": [10.0], "high": [10.1], "low": [9.9], "close": [10.0],
        "volume": [1.0], "amount": [1000.0],
    })


def test_public_eod_does_not_overlay_custom_daily():
    assert daily_pipeline.should_use_public_eod_fallback(
        pull_a_share=True, today_missing=True, weekday=0, has_quote_pool=False,
        daily_is_custom=True,
    ) is False
    assert daily_pipeline.should_use_public_eod_fallback(
        pull_a_share=True, today_missing=True, weekday=0, has_quote_pool=False,
        daily_is_custom=False,
    ) is True


def test_declared_daily_resolve_failure_does_not_call_tickflow(monkeypatch, tmp_path):
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
        CapabilitySet({Cap.KLINE_DAILY_BATCH: CapabilityLimits()}),
    )
    assert written == 0
    live = kline_sync.fetch_routed_daily(
        ["000001.SZ"],
        start_time=datetime(2026, 1, 1),
        end_time=datetime(2026, 1, 2),
        capset=CapabilitySet({Cap.KLINE_DAILY_BATCH: CapabilityLimits()}),
    )
    assert live.is_empty()
    tf.assert_not_called()


def test_undeclared_daily_still_falls_back_to_tickflow(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "fuyao")
    monkeypatch.setattr("app.data_providers.custom.provider_has_dataset", lambda name, dataset: False)
    provider, fallback, err = kline_sync._resolve_daily_provider("fuyao")
    assert provider is None
    assert fallback is True
    assert err is None
    assert kline_sync.routed_daily_source_label() == "tickflow_batch"


def test_declared_minute_resolve_failure_is_fail_closed(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "sdk")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: True,
    )
    monkeypatch.setattr(
        "app.data_providers.custom.get_provider",
        lambda name: (_ for _ in ()).throw(RuntimeError("plugin missing")),
    )
    df, fallback = kline_sync._try_custom_minute(["600000.SH"], None, None)
    assert df is None
    assert fallback is False
    support = kline_sync.intraday_monitor_support(CapabilitySet({
        Cap.KLINE_MINUTE_BATCH: CapabilityLimits(),
    }))
    assert support["available"] is False


def test_fetch_minute_single_custom_call_fail_skips_public(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "sdk")
    provider = MagicMock()
    provider.get_minute.side_effect = RuntimeError("minute dump down")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: name == "sdk" and dataset == "minute",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda name: provider)
    monkeypatch.setattr(
        kline_sync,
        "get_client",
        lambda: (_ for _ in ()).throw(RuntimeError("tickflow down")),
    )
    public = MagicMock(side_effect=AssertionError("must not mix public minute"))
    monkeypatch.setattr(kline_sync, "_public_minute_fallback", public)

    out = kline_sync.fetch_minute_single(
        "600000.SH",
        date(2026, 7, 17),
        capset=CapabilitySet({Cap.KLINE_MINUTE_BY_SYMBOL: CapabilityLimits()}),
    )
    assert out.is_empty()
    public.assert_not_called()


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
        lambda symbol, trade_date: _minute(symbol),
    )
    out = kline_sync.fetch_minute_single("600000.SH", date(2026, 7, 17), capset=CapabilitySet())
    assert out["symbol"].to_list() == ["600000.SH"]


def test_persist_minute_resolve_fail_skips_entitled_tickflow(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "sdk")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: (_ for _ in ()).throw(RuntimeError("registry corrupted")),
    )
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    monkeypatch.setattr(kline_sync, "sync_minute_batch", tf)

    written = kline_sync.sync_and_persist_minute(
        ["600000.SH"],
        KlineRepository(DataStore(tmp_path)),
        CapabilitySet({Cap.KLINE_MINUTE_BATCH: CapabilityLimits()}),
    )
    assert written == 0
    tf.assert_not_called()


def test_full_minute_resolve_failure_does_not_degrade_to_tickflow(monkeypatch):
    monkeypatch.setattr(
        minute_refresh.preferences, "get_full_minute_data_provider", lambda: "myfm",
    )
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: True,
    )
    monkeypatch.setattr(
        "app.data_providers.custom.get_provider",
        lambda name: (_ for _ in ()).throw(RuntimeError("plugin missing")),
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


def test_custom_full_minute_batch_failure_is_fail_closed():
    provider = MagicMock()
    provider.get_intraday_batch.side_effect = RuntimeError("batch down")
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    out, requests = kline_sync.fetch_intraday_custom_batch(
        provider, "myfm", ["600000.SH"],
    )
    assert out.is_empty()
    assert requests == 1
    tf.assert_not_called()


def test_custom_full_minute_latest_missing_uses_minute_window():
    provider = MagicMock()
    provider.get_intraday_batch = None
    provider.get_intraday_latest = None
    provider.get_minute.return_value = _minute()

    def _minute_fn(symbols, start_time=None, end_time=None, asset_type="stock",
                   freq="1m", on_chunk_done=None):
        if on_chunk_done:
            on_chunk_done(1, 4)
        return _minute()

    provider.get_minute.side_effect = _minute_fn
    out, requests = kline_sync.fetch_intraday_custom_batch(
        provider, "myfm", ["600000.SH"],
    )
    assert out["symbol"].to_list() == ["600000.SH"]
    assert requests == 4


def test_burst_without_intraday_cap_is_empty(monkeypatch):
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    df, requests = kline_sync.fetch_intraday_full_market_burst(
        ["S0", "S1"], CapabilitySet(),
    )
    assert df.is_empty()
    assert requests == 0
    tf.assert_not_called()


def test_etf_adj_allowed_for_custom_without_tickflow_cap(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "fuyao")
    monkeypatch.setattr(
        kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: False,
    )
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: name == "fuyao" and dataset == "adj_factor",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda name: object())
    assert kline_sync.adj_live_fetch_allowed(CapabilitySet()) is True


def test_feature_custom_depth_does_not_advertise_public_l1(monkeypatch):
    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "public")
    monkeypatch.setattr("app.services.preferences.get_depth5_data_provider", lambda: "depth_src")
    monkeypatch.setattr("app.services.preferences.get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_minute_data_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.is_public_financial_provider", lambda: False)
    monkeypatch.setattr("app.services.preferences.is_public_adj_factor_provider", lambda: False)
    monkeypatch.setattr("app.services.financial_normalize.local_financials_ready", lambda d: False)
    monkeypatch.setattr("app.services.financial_normalize.local_adj_factor_ready", lambda d: False)
    feats = feature_availability(CapabilitySet())
    assert feats["depth"]["source"] == "depth_src"
    assert feats["depth"]["fallback"] is None
