"""Sixteenth-round leftover mix-source / fail-open paths.

Closes leftover contracts that round 15 documented but did not fix:
- undeclared custom daily / minute / full_minute / adj no longer TickFlow-mix
- leftover TickFlow + no ADJ cap no longer silent-mixes public sina qfq
- leftover TickFlow adj reads no longer serve public-sina tags
- leftover TickFlow empty depth no longer mixes public L1
- leftover TickFlow depth reads no longer serve public-tagged sealed files
- Lab /api/free-ext public fetch/write refuses custom / unresolved routes
- historical daily / enriched HTTP / screener / chips reads use provenance

Keeps remaining TickFlow leftover contracts:
- leftover TickFlow + free realtime stays mode=none
- entitled TickFlow minute fallback after a custom *call* failure
- leftover TickFlow single-symbol minute view may still use public / TDX
- A-share / index / ETF instruments stay TickFlow (no instrument_provider)
- quote_snapshot overlay stays an isolated live asset
- after-hours default times / .env / auth stay out of scope
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import free_ext
from app.services import kline_sync, preferences
from app.services.depth_service import DepthService, depth_cache_usable
from app.services.free_sources.kline_loader import load_daily_bars_for_symbol
from app.services.market_overview_builder import latest_official_enriched_date
from app.services.quote_service import QuoteService
from app.services.screener import ScreenerService
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
        "raw_close": [10.1],
        "raw_high": [10.2],
        "raw_low": [9.9],
        "turnover_rate": [1.0],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _adj_df(*, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "trade_date": [date(2026, 3, 31)],
        "ex_factor": [1.1],
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


def _patch_undeclared(monkeypatch, module, attr: str, name: str = "fuyao") -> None:
    monkeypatch.setattr(module, attr, lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: False,
    )


def _write_enriched(tmp_path, df: pl.DataFrame, day: str = "2026-07-17") -> None:
    part = tmp_path / "kline_daily_enriched" / f"date={day}"
    part.mkdir(parents=True)
    df.write_parquet(part / "part.parquet")


def test_undeclared_daily_is_fail_closed(monkeypatch):
    _patch_undeclared(monkeypatch, kline_sync.preferences, "get_daily_data_provider")
    provider, fallback, err = kline_sync._resolve_daily_provider("fuyao")
    assert provider is None
    assert fallback is False
    assert err is not None
    assert kline_sync.daily_route() == "unresolved"
    assert kline_sync.live_daily_persist_allowed() is False


def test_undeclared_minute_is_fail_closed(monkeypatch):
    _patch_undeclared(monkeypatch, kline_sync.preferences, "get_minute_data_provider")
    provider, fallback, err = kline_sync._resolve_minute_provider("fuyao")
    assert provider is None
    assert fallback is False
    assert err is not None
    assert kline_sync.minute_route() == "unresolved"
    assert kline_sync.minute_may_use_leftover_public() is False


def test_undeclared_full_minute_is_fail_closed(monkeypatch):
    _patch_undeclared(monkeypatch, kline_sync.preferences, "get_full_minute_data_provider")
    provider, fallback, err = kline_sync._resolve_full_minute_provider("fuyao")
    assert provider is None
    assert fallback is False
    assert err is not None
    assert kline_sync.full_minute_route() == "unresolved"
    assert kline_sync.full_minute_may_use_minute_fallback() is False


def test_undeclared_adj_is_fail_closed(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "fuyao")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: False)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: False,
    )
    custom, fate = kline_sync._try_custom_adj_provider("fuyao")
    assert custom is None
    assert fate == "skip"
    assert kline_sync.adj_route() == "unresolved"
    assert kline_sync.adj_live_fetch_allowed(CapabilitySet()) is False
    assert kline_sync.adj_public_write_allowed() is False


def test_leftover_tickflow_adj_without_cap_does_not_use_sina(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: False)
    public = MagicMock(side_effect=AssertionError("must not use public sina"))
    monkeypatch.setattr(kline_sync, "_sync_public_adj_factor", public)
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow without ADJ cap"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    rows, symbols = kline_sync.sync_adj_factor(
        ["000001.SZ"],
        KlineRepository(DataStore(tmp_path)),
        CapabilitySet(),
    )
    assert rows == 0
    assert symbols == []
    public.assert_not_called()
    tf.assert_not_called()
    assert kline_sync.adj_live_fetch_allowed(CapabilitySet()) is False
    assert kline_sync.fetch_adj_factor_single("000001.SZ", capset=CapabilitySet()).is_empty()


def test_explicit_public_adj_still_uses_sina(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "sina")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: True)
    assert kline_sync.adj_route() == "public"
    assert kline_sync.adj_public_write_allowed() is True
    assert kline_sync.adj_live_fetch_allowed(CapabilitySet()) is True


def test_leftover_tickflow_adj_refuses_public_tag(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor"
    path.mkdir(parents=True)
    _adj_df(route="public").write_parquet(path / "all.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    assert kline_sync.adj_cache_usable(_adj_df(route="public"), "tickflow") is False
    assert kline_sync.get_adj_factor_df(tmp_path).is_empty()


def test_leftover_tickflow_untagged_adj_still_serves(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor"
    path.mkdir(parents=True)
    _adj_df().write_parquet(path / "all.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    assert kline_sync.get_adj_factor_df(tmp_path)["symbol"].to_list() == ["000001.SZ"]


def test_leftover_tickflow_depth_empty_does_not_use_public_l1(monkeypatch):
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "tickflow")
    svc = DepthService()
    svc._app_state = SimpleNamespace(capabilities=CapabilitySet())
    public = MagicMock(side_effect=AssertionError("must not mix public L1"))
    monkeypatch.setattr(svc, "_call_public_depth_l1", public)
    monkeypatch.setattr(svc, "_call_routed_depth_batch", lambda *a, **k: {})
    monkeypatch.setattr(svc, "_has_tickflow_depth", lambda: False)
    assert svc._call_depth_batch(["A"]) == {}
    public.assert_not_called()


def test_explicit_public_depth_still_uses_l1(monkeypatch):
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "public")
    svc = DepthService()
    monkeypatch.setattr(svc, "_call_public_depth_l1", lambda symbols: {"A": {"ask_volumes": [1]}})
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow depth"))
    monkeypatch.setattr(svc, "_call_tickflow_depth_batch", tf)
    monkeypatch.setattr(svc, "_call_routed_depth_batch", tf)
    assert svc._call_depth_batch(["A"]) == {"A": {"ask_volumes": [1]}}
    tf.assert_not_called()


def test_leftover_tickflow_depth_refuses_public_tag():
    sealed = pl.DataFrame({
        "symbol": ["000001.SZ"],
        "sealed_up": [True],
        "route": ["public"],
    })
    assert depth_cache_usable(sealed, "tickflow") is False
    assert depth_cache_usable(sealed.drop("route"), "tickflow") is True


def test_filter_daily_cache_drops_leftover_rows_under_custom(monkeypatch):
    _patch_custom_daily(monkeypatch)
    mixed = pl.concat([
        _daily_df(route="tickflow"),
        _daily_df("600000.SH", route="fuyao"),
    ], how="diagonal_relaxed")
    out = kline_sync.filter_daily_cache(mixed)
    assert out["symbol"].to_list() == ["600000.SH"]
    assert kline_sync.filter_daily_cache(_daily_df()).is_empty()


def test_http_daily_scan_hides_leftover_under_custom(monkeypatch, tmp_path):
    _write_enriched(tmp_path, _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.get_daily("000001.SZ", date(2026, 7, 1), date(2026, 7, 20)).is_empty()


def test_http_daily_scan_keeps_custom_and_leftover_untagged(monkeypatch, tmp_path):
    _write_enriched(tmp_path, _daily_df(route="fuyao"))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    out = repo.get_daily("000001.SZ", date(2026, 7, 1), date(2026, 7, 20))
    assert "000001.SZ" in out["symbol"].to_list()

    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    leftover_dir = tmp_path / "kline_daily_enriched" / "date=2026-07-16"
    leftover_dir.mkdir(parents=True)
    _daily_df(route=None).write_parquet(leftover_dir / "part.parquet")
    repo2 = KlineRepository(DataStore(tmp_path))
    leftover = repo2.get_daily("000001.SZ", date(2026, 7, 16), date(2026, 7, 16))
    assert leftover["symbol"].to_list() == ["000001.SZ"]


def test_screener_hides_leftover_enriched_under_custom(monkeypatch, tmp_path):
    _write_enriched(tmp_path, _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        get_enriched_latest=lambda: (None, None),
        get_enriched_history=lambda *_a, **_k: None,
        get_instruments=lambda: pl.DataFrame(),
    )
    assert ScreenerService(repo)._load_enriched_for_date(date(2026, 7, 17)).is_empty()


def test_screener_keeps_leftover_untagged_for_tickflow(monkeypatch, tmp_path):
    _write_enriched(tmp_path, _daily_df())
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        get_enriched_latest=lambda: (None, None),
        get_enriched_history=lambda *_a, **_k: None,
        get_instruments=lambda: pl.DataFrame(),
    )
    out = ScreenerService(repo)._load_enriched_for_date(date(2026, 7, 17))
    assert out["symbol"].to_list() == ["000001.SZ"]


def test_chips_loader_skips_leftover_daily_under_custom(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(part / "part.parquet")
    _patch_custom_daily(monkeypatch)
    try:
        load_daily_bars_for_symbol(tmp_path, "000001.SZ", days=10)
        raised = False
    except (FileNotFoundError, ValueError):
        raised = True
    assert raised is True


def test_overview_latest_hides_leftover_enriched(monkeypatch, tmp_path):
    _write_enriched(tmp_path, _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert latest_official_enriched_date(repo) is None

    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert latest_official_enriched_date(repo) == date(2026, 7, 17)


def test_lab_adj_refuses_custom_route(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "fuyao")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: False)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == "fuyao" and dataset == "adj_factor",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())
    app = FastAPI()
    app.include_router(free_ext.router)
    client = TestClient(app)
    resp = client.get("/api/free/adj-factor/000001.SZ")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "lab_public_refused"


def test_lab_financial_refuses_custom_route(monkeypatch):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == "fuyao" and dataset == "financial",
    )
    app = FastAPI()
    app.include_router(free_ext.router)
    client = TestClient(app)
    resp = client.get("/api/free/financials/000001.SZ")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "lab_public_refused"


def test_lab_adj_still_allows_leftover_tickflow(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: False)
    monkeypatch.setattr(
        "app.api.free_ext.fetch_adj_factors_symbol",
        lambda symbol: _adj_df(),
    )
    app = FastAPI()
    app.include_router(free_ext.router)
    client = TestClient(app)
    resp = client.get("/api/free/adj-factor/000001.SZ")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["source"] == "sina_qfq"


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"


def test_daily_prefs_unreadable_stays_fail_closed(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    assert kline_sync.daily_route() == "unresolved"
    assert kline_sync.filter_daily_cache(_daily_df()).is_empty()
