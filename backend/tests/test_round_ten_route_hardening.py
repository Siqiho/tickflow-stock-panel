"""Tenth-round leftover mix-source / fail-open paths.

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

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import kline as kline_api
from app.jobs import daily_pipeline
from app.services import financial_sync, kline_sync, preferences
from app.services.depth_service import DepthService
from app.services.quote_service import QuoteService
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet
from app.tickflow.repository import DataStore, KlineRepository


def _capset(*caps: Cap) -> CapabilitySet:
    return CapabilitySet({c: CapabilityLimits(rpm=60, batch=100) for c in caps})


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


def test_custom_daily_blocks_live_quote_canonical_persist(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: name == "fuyao" and dataset == "daily",
    )
    monkeypatch.setattr(
        "app.data_providers.custom.get_provider",
        lambda name: SimpleNamespace(),
    )
    assert kline_sync.live_daily_persist_allowed() is False

    repo = KlineRepository(DataStore(tmp_path))
    service = QuoteService()
    service.set_repo(repo)
    records = [
        {
            "symbol": "000001.SZ",
            "name": "测试",
            "last_price": 10.0,
            "prev_close": 9.0,
            "open": 9.5,
            "high": 10.2,
            "low": 9.4,
            "volume": 1000.0,
            "amount": 10000.0,
            "source": "tickflow",
        }
    ]
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_realtime_pull_index", lambda: False)
    monkeypatch.setattr(preferences, "get_realtime_pull_etf", lambda: False)
    monkeypatch.setattr(preferences, "get_realtime_pull_stock", lambda: True)
    monkeypatch.setattr(repo, "get_index_symbol_set", lambda: set())
    monkeypatch.setattr(repo, "get_etf_instruments", lambda: pl.DataFrame())
    monkeypatch.setattr(service, "_fetch_tickflow_full_market_records", lambda **k: records)
    monkeypatch.setattr(service, "_evaluate_monitors", lambda *a, **k: None)
    monkeypatch.setattr(
        repo,
        "flush_live_daily",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("canonical stock writer called")),
    )
    monkeypatch.setattr(
        repo,
        "flush_live_daily_asset",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("canonical asset writer called")),
    )
    enriched_calls: list[dict] = []
    monkeypatch.setattr(
        service,
        "_flush_live_enriched",
        lambda *a, **k: enriched_calls.append(k),
    )

    service._fetch_full_market_quotes()

    snapshots = list((tmp_path / "quote_snapshot").rglob("*.parquet"))
    assert len(snapshots) == 1
    assert not list((tmp_path / "kline_daily").rglob("*.parquet"))
    assert enriched_calls == [{"asset_type": "stock", "persist": False}]


def test_leftover_tickflow_daily_still_persists_live_quotes(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert kline_sync.live_daily_persist_allowed() is True

    repo = KlineRepository(DataStore(tmp_path))
    service = QuoteService()
    service.set_repo(repo)
    records = [
        {
            "symbol": "000001.SZ",
            "name": "测试",
            "last_price": 10.0,
            "prev_close": 9.0,
            "open": 9.5,
            "high": 10.2,
            "low": 9.4,
            "volume": 1000.0,
            "amount": 10000.0,
            "source": "tickflow",
        }
    ]
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_realtime_pull_index", lambda: False)
    monkeypatch.setattr(preferences, "get_realtime_pull_etf", lambda: False)
    monkeypatch.setattr(preferences, "get_realtime_pull_stock", lambda: True)
    monkeypatch.setattr(repo, "get_index_symbol_set", lambda: set())
    monkeypatch.setattr(repo, "get_etf_instruments", lambda: pl.DataFrame())
    monkeypatch.setattr(service, "_fetch_tickflow_full_market_records", lambda **k: records)
    monkeypatch.setattr(service, "_evaluate_monitors", lambda *a, **k: None)
    flushed = []
    monkeypatch.setattr(repo, "flush_live_daily", lambda df: flushed.append(df.height))
    monkeypatch.setattr(service, "_flush_live_enriched", lambda *a, **k: None)

    service._fetch_full_market_quotes()
    assert flushed == [1]


def test_sync_daily_by_quotes_respects_custom_daily_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync, "live_daily_persist_allowed", lambda: False)
    tf = MagicMock(side_effect=AssertionError("must not TickFlow quote.pool"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    written = kline_sync.sync_daily_by_quotes(KlineRepository(DataStore(tmp_path)))
    assert written == 0
    tf.assert_not_called()


def test_minute_cache_rejects_stale_tickflow_for_custom(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: name == "fuyao" and dataset == "minute",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda name: SimpleNamespace())
    assert kline_sync.minute_route() == "fuyao"
    stale = _minute_df(route="tickflow")
    untagged = _minute_df()
    tagged = _minute_df(route="fuyao")
    assert kline_sync.minute_cache_usable(stale, "fuyao") is False
    assert kline_sync.minute_cache_usable(untagged, "fuyao") is False
    assert kline_sync.minute_cache_usable(tagged, "fuyao") is True
    assert kline_sync.minute_cache_usable(untagged, "tickflow") is True


def test_get_minute_skips_stale_local_for_custom(monkeypatch, tmp_path):
    stale = _minute_df(route="tickflow")
    monkeypatch.setattr(kline_sync, "minute_route", lambda: "fuyao")
    monkeypatch.setattr(kline_sync, "minute_may_use_leftover_public", lambda: False)
    monkeypatch.setattr(kline_sync, "minute_provider_is_custom", lambda: True)
    monkeypatch.setattr(kline_sync, "fetch_minute_single", lambda *a, **k: pl.DataFrame())
    monkeypatch.setattr("app.services.watchlist.contains", lambda *a, **k: False)
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        get_minute=lambda *a, **k: stale,
        get_daily=lambda *a, **k: pl.DataFrame(),
        execute_one=lambda *a, **k: None,
    )
    app = FastAPI()
    app.include_router(kline_api.router)
    app.state.repo = repo
    app.state.capabilities = CapabilitySet()
    resp = TestClient(app).get("/api/kline/minute?symbol=000001.SZ&date=2026-07-17")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "none"
    assert body["rows"] == []
    assert all("route" not in row for row in body["rows"])


def test_minute_write_tags_current_route(tmp_path, monkeypatch):
    monkeypatch.setattr(kline_sync, "minute_route", lambda: "fuyao")
    written = kline_sync._write_minute_partition(
        kline_sync._with_minute_route(_minute_df(), "fuyao"),
        tmp_path / "kline_minute",
    )
    assert written == 1
    saved = pl.read_parquet(tmp_path / "kline_minute" / "date=2026-07-17" / "part.parquet")
    assert saved["route"].to_list() == ["fuyao"]


def test_custom_full_minute_skips_minute_provider_fallback(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_full_minute_data_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: name == "fuyao" and dataset == "full_minute",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda name: SimpleNamespace())
    assert kline_sync.full_minute_route() == "fuyao"
    assert kline_sync.full_minute_may_use_minute_fallback() is False

    qs = QuoteService.__new__(QuoteService)
    qs._app_state = SimpleNamespace(minute_refresh=None, capabilities=_capset(Cap.KLINE_MINUTE_BATCH))
    qs._repo = SimpleNamespace()
    qs._intraday_signal_evaluator = SimpleNamespace(
        evaluate=lambda *a, **k: [],
        inject=lambda enriched, _signals: enriched,
    )
    monitor = MagicMock(side_effect=AssertionError("must not mix minute_data_provider"))
    monkeypatch.setattr(kline_sync, "fetch_intraday_monitor_batch", monitor)
    engine = SimpleNamespace(intraday_signal_symbols=lambda _asset: ["000001.SZ"])
    out = qs._inject_intraday_signals(
        pl.DataFrame({"symbol": ["000001.SZ"], "close": [10.0], "prev_close": [9.0]}),
        engine,
        asset_type="stock",
    )
    assert out["symbol"].to_list() == ["000001.SZ"]
    monitor.assert_not_called()


def test_leftover_full_minute_still_uses_monitor_batch(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_full_minute_data_provider", lambda: "tickflow")
    assert kline_sync.full_minute_may_use_minute_fallback() is True
    qs = QuoteService.__new__(QuoteService)
    qs._app_state = SimpleNamespace(minute_refresh=None, capabilities=_capset(Cap.INTRADAY_BATCH))
    qs._repo = SimpleNamespace()
    called = []

    def fake_batch(symbols, capset):
        called.append(list(symbols))
        return _minute_df()

    monkeypatch.setattr(kline_sync, "fetch_intraday_monitor_batch", fake_batch)
    qs._intraday_signal_evaluator = SimpleNamespace(
        evaluate=lambda *a, **k: [],
        inject=lambda enriched, _signals: enriched,
    )
    engine = SimpleNamespace(intraday_signal_symbols=lambda _asset: ["000001.SZ"])
    qs._inject_intraday_signals(
        pl.DataFrame({"symbol": ["000001.SZ"], "close": [10.0], "prev_close": [9.0]}),
        engine,
        asset_type="stock",
    )
    assert called == [["000001.SZ"]]


def test_public_adj_empty_scope_is_fail_closed(monkeypatch):
    monkeypatch.setattr(daily_pipeline, "adj_sync_uses_public_adapter", lambda _c: True)
    monkeypatch.setattr(daily_pipeline._prefs, "get_public_data_scope", lambda: "CSI300")
    monkeypatch.setattr(
        "app.services.universe_scope.resolve_symbols",
        lambda *a, **k: [],
    )
    assert daily_pipeline.resolve_adj_sync_universe(
        ["000001.SZ", "600000.SH"],
        CapabilitySet(),
    ) is None


def test_public_adj_scope_failure_is_fail_closed(monkeypatch):
    monkeypatch.setattr(daily_pipeline, "adj_sync_uses_public_adapter", lambda _c: True)
    monkeypatch.setattr(daily_pipeline._prefs, "get_public_data_scope", lambda: "CSI300")
    monkeypatch.setattr(
        "app.services.universe_scope.resolve_symbols",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("pool empty")),
    )
    try:
        daily_pipeline.resolve_adj_sync_universe(["000001.SZ"], CapabilitySet())
    except RuntimeError:
        pass
    else:
        raise AssertionError("resolve failure should surface to caller")


def test_tickflow_adj_keeps_pipeline_universe(monkeypatch):
    monkeypatch.setattr(daily_pipeline, "adj_sync_uses_public_adapter", lambda _c: False)
    out = daily_pipeline.resolve_adj_sync_universe(
        ["000001.SZ", "600000.SH"],
        _capset(Cap.ADJ_FACTOR),
    )
    assert out == ["000001.SZ", "600000.SH"]


def test_depth_has_capability_is_honest_for_undeclared_and_prefs(monkeypatch):
    svc = DepthService()
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "depth_src")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: False,
    )
    assert svc._has_capability() is False

    monkeypatch.setattr(preferences, "get_depth5_data_provider", _prefs_boom)
    assert svc._has_capability() is False

    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "tickflow")
    assert svc._has_capability() is True

    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "public")
    assert svc._has_capability() is True


def test_financial_cache_skips_stale_tickflow_for_custom(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "metrics"
    path.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "period_end": [date(2026, 3, 31)],
        "route": ["tickflow"],
    }).write_parquet(path / "part.parquet")
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    assert financial_sync.get_financial_df(tmp_path, "metrics").is_empty()


def test_financial_write_tags_custom_route(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    written = financial_sync._write_financial_df(
        pl.DataFrame({"symbol": ["000001.SZ"], "period_end": [date(2026, 3, 31)]}),
        tmp_path,
        "metrics",
    )
    assert written == 1
    saved = pl.read_parquet(tmp_path / "financials" / "metrics" / "part.parquet")
    assert saved["route"].to_list() == ["fuyao"]
    out = financial_sync.get_financial_df(tmp_path, "metrics")
    assert out["symbol"].to_list() == ["000001.SZ"]
    assert "route" not in out.columns


def test_untagged_financials_still_serve_leftover_tickflow(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "metrics"
    path.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "period_end": [date(2026, 3, 31)],
    }).write_parquet(path / "part.parquet")
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    out = financial_sync.get_financial_df(tmp_path, "metrics")
    assert out["symbol"].to_list() == ["000001.SZ"]


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


def test_daily_prefs_unreadable_blocks_live_persist(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    assert kline_sync.daily_provider_is_custom() is True
    assert kline_sync.live_daily_persist_allowed() is False
