"""Fifth-round leftover mix-source / fail-open paths.

Keeps prior contracts:
- leftover TickFlow + free realtime stays mode=none (no silent public)
- entitled TickFlow minute fallback after a custom call failure
Round 16 closed undeclared custom → TickFlow and leftover silent sina qfq.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

import polars as pl

from app.services import kline_sync, preferences
from app.services.quote_service import QuoteService
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet
from app.tickflow.repository import DataStore, KlineRepository


def _adj_df(symbol: str = "000001.SZ") -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": [symbol],
        "trade_date": [date(2020, 6, 1)],
        "ex_factor": [1.1],
    })


def _route_custom_adj(monkeypatch, provider, *, name: str = "fuyao", declared: bool = True):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: name)
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda *a, **k: False)
    from app.data_providers import custom
    monkeypatch.setattr(
        custom,
        "provider_has_dataset",
        lambda n, dataset: n == name and declared and dataset == "adj_factor",
    )
    monkeypatch.setattr(custom, "get_provider", lambda n: provider)


def test_custom_adj_sync_does_not_call_tickflow(monkeypatch, tmp_path):
    provider = MagicMock()
    provider.get_adj_factors.return_value = _adj_df()
    _route_custom_adj(monkeypatch, provider)
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr(kline_sync, "get_client", tf)

    repo = KlineRepository(DataStore(tmp_path))
    rows, symbols = kline_sync.sync_adj_factor(
        ["000001.SZ"],
        repo,
        CapabilitySet({Cap.ADJ_FACTOR: CapabilityLimits()}),
    )
    assert rows == 1
    assert symbols == ["000001.SZ"]
    provider.get_adj_factors.assert_called_once()
    tf.assert_not_called()
    stored = pl.read_parquet(tmp_path / "adj_factor" / "all.parquet")
    assert stored["symbol"].to_list() == ["000001.SZ"]


def test_custom_adj_failure_is_fail_closed(monkeypatch, tmp_path):
    provider = MagicMock()
    provider.get_adj_factors.side_effect = RuntimeError("adj dump down")
    _route_custom_adj(monkeypatch, provider)
    public = MagicMock(side_effect=AssertionError("must not use public adapter"))
    monkeypatch.setattr(kline_sync, "_sync_public_adj_factor", public)
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr(kline_sync, "get_client", tf)

    rows, symbols = kline_sync.sync_adj_factor(
        ["000001.SZ"],
        KlineRepository(DataStore(tmp_path)),
        CapabilitySet({Cap.ADJ_FACTOR: CapabilityLimits()}),
    )
    assert rows == 0
    assert symbols == []
    tf.assert_not_called()
    public.assert_not_called()


def test_undeclared_custom_adj_is_fail_closed(monkeypatch, tmp_path):
    provider = MagicMock()
    _route_custom_adj(monkeypatch, provider, declared=False)
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    public = MagicMock(side_effect=AssertionError("must not use public adapter"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    monkeypatch.setattr(kline_sync, "_sync_public_adj_factor", public)

    rows, symbols = kline_sync.sync_adj_factor(
        ["000001.SZ"],
        KlineRepository(DataStore(tmp_path)),
        CapabilitySet({Cap.ADJ_FACTOR: CapabilityLimits()}),
    )
    assert rows == 0
    assert symbols == []
    provider.get_adj_factors.assert_not_called()
    tf.assert_not_called()
    public.assert_not_called()
    assert kline_sync.adj_route() == "unresolved"


def test_fetch_adj_single_uses_custom_provider(monkeypatch):
    provider = MagicMock()
    provider.get_adj_factors.return_value = _adj_df()
    _route_custom_adj(monkeypatch, provider)
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr(kline_sync, "get_client", tf)

    out = kline_sync.fetch_adj_factor_single("000001.SZ")
    assert out["symbol"].to_list() == ["000001.SZ"]
    tf.assert_not_called()


def test_fetch_adj_single_uses_public_when_selected(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "sina")
    monkeypatch.setattr(
        kline_sync.preferences,
        "is_public_adj_factor_provider",
        lambda name=None: True,
    )
    monkeypatch.setattr(
        "app.services.free_sources.adj_factor_public.fetch_adj_factors_symbol",
        lambda symbol, **kw: _adj_df(symbol),
    )
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr(kline_sync, "get_client", tf)

    out = kline_sync.fetch_adj_factor_single("000001.SZ")
    assert out["ex_factor"].to_list() == [1.1]
    tf.assert_not_called()


def test_adj_live_fetch_allowed_for_custom_without_tickflow_cap(monkeypatch):
    provider = MagicMock()
    _route_custom_adj(monkeypatch, provider)
    assert kline_sync.adj_live_fetch_allowed(CapabilitySet()) is True


def test_realtime_mode_prefs_failure_is_none(monkeypatch):
    monkeypatch.setattr(
        preferences,
        "get_realtime_data_provider",
        lambda: (_ for _ in ()).throw(RuntimeError("prefs unreadable")),
    )
    monkeypatch.setattr(QuoteService, "_current_tier", lambda: "pro")
    assert QuoteService.realtime_mode() == "none"
    assert QuoteService.is_realtime_allowed() is False


def test_watchlist_does_not_public_fallback_when_tickflow(monkeypatch):
    qs = QuoteService.__new__(QuoteService)
    monkeypatch.setattr(preferences, "get_realtime_watchlist_symbols", lambda: ["000001.SZ"])
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(
        "app.tickflow.client.get_paid_realtime_client",
        lambda: None,
    )
    hit = {"public": False}
    monkeypatch.setattr(
        qs,
        "_fetch_public_quote_rows",
        lambda *a, **k: hit.__setitem__("public", True) or [],
    )
    qs._fetch_watchlist_quotes()
    assert hit["public"] is False


def test_undeclared_daily_still_falls_back_to_tickflow(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "fuyao")
    from app.data_providers import custom
    monkeypatch.setattr(custom, "provider_has_dataset", lambda name, dataset: False)
    provider, fallback, err = kline_sync._resolve_daily_provider("fuyao")
    assert provider is None
    assert fallback is False
    assert err is not None


def test_intraday_monitor_batch_uses_custom_minute(monkeypatch):
    df = pl.DataFrame({
        "symbol": ["600000.SH"],
        "datetime": [datetime(2026, 7, 17, 9, 31)],
        "open": [10.0], "high": [10.1], "low": [9.9], "close": [10.0],
        "volume": [1.0], "amount": [1000.0],
    })
    monkeypatch.setattr(
        kline_sync,
        "_try_custom_minute",
        lambda *a, **k: (df, False),
    )
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    out = kline_sync.fetch_intraday_monitor_batch(
        ["600000.SH"],
        CapabilitySet(),
        now=datetime(2026, 7, 17, 10, 0),
    )
    assert out["symbol"].to_list() == ["600000.SH"]
    tf.assert_not_called()


def test_intraday_monitor_batch_entitled_tickflow_after_custom_failure(monkeypatch):
    monkeypatch.setattr(
        kline_sync,
        "_try_custom_minute",
        lambda *a, **k: (None, True),
    )
    ts = int(datetime(2026, 7, 17, 9, 30).timestamp() * 1000)

    class FakeKlines:
        def intraday_batch(self, symbols, count, as_dataframe, show_progress, batch_size):
            return {
                "600000.SH": {
                    "timestamp": [ts],
                    "open": [10.0], "high": [10.1], "low": [9.9], "close": [10.0],
                    "volume": [1.0], "amount": [1000.0],
                },
            }

    class FakeClient:
        klines = FakeKlines()

    monkeypatch.setattr(kline_sync, "get_client", lambda: FakeClient())
    out = kline_sync.fetch_intraday_monitor_batch(
        ["600000.SH"],
        CapabilitySet({Cap.INTRADAY_BATCH: CapabilityLimits(batch=20, rpm=30)}),
        now=datetime(2026, 7, 17, 10, 0),
    )
    assert out["symbol"].to_list() == ["600000.SH"]


def test_intraday_monitor_batch_leftover_free_is_empty(monkeypatch):
    monkeypatch.setattr(
        kline_sync,
        "_try_custom_minute",
        lambda *a, **k: (None, True),
    )
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    out = kline_sync.fetch_intraday_monitor_batch(["600000.SH"], CapabilitySet())
    assert out.is_empty()
    tf.assert_not_called()
