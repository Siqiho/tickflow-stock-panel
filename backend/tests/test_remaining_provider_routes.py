"""Remaining silent wrong-source routes after PR #2–#4.

Covers Cap.QUOTE_POOL overwrite, public pool_provider fail-closed,
live daily HTTP routing, and depth source labels.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl

from app.jobs import daily_pipeline
from app.services import kline_sync
from app.services.depth_service import DepthService
from app.tickflow import pools
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet
from app.tickflow.repository import DataStore, KlineRepository
from tests.test_repair_daily_override import _stub_common


def _daily(symbol: str, day: date) -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": [symbol], "date": [day], "open": [10.0], "high": [11.0],
        "low": [9.0], "close": [10.5], "volume": [100.0], "amount": [1050.0],
    })


def test_quote_pool_does_not_overwrite_custom_daily(monkeypatch, tmp_path):
    """Cap.QUOTE_POOL must not flush TickFlow quotes over a custom daily source."""
    today = date.today()
    repo, captured = _stub_common(monkeypatch, tmp_path, latest=today)
    monkeypatch.setattr(kline_sync, "daily_provider_is_custom", lambda: True)

    result = daily_pipeline.run_now(
        repo,
        CapabilitySet({
            Cap.KLINE_DAILY_BATCH: CapabilityLimits(),
            Cap.QUOTE_POOL: CapabilityLimits(),
            Cap.ADJ_FACTOR: CapabilityLimits(),
        }),
    )
    assert captured.get("quotes") is None
    assert "daily" in captured
    assert result["daily_source"] == "tickflow_batch"


def test_public_pool_csi_failure_does_not_call_tickflow(monkeypatch):
    monkeypatch.setattr(
        "app.services.preferences.is_public_pool_provider",
        lambda name=None: True,
    )
    monkeypatch.setattr(
        "app.services.free_sources.pools_public.fetch_pool_constituents",
        lambda pool_id: (_ for _ in ()).throw(RuntimeError("xls down")),
    )
    get_client = MagicMock(side_effect=AssertionError("must not fall back to TickFlow"))
    monkeypatch.setattr("app.tickflow.pools.get_client", get_client)

    assert pools._fetch_pool("CSI300") == []
    get_client.assert_not_called()


def test_public_pool_cannot_serve_cn_equity_via_tickflow(monkeypatch):
    monkeypatch.setattr(
        "app.services.preferences.is_public_pool_provider",
        lambda name=None: True,
    )
    get_client = MagicMock(side_effect=AssertionError("must not use TickFlow universes"))
    monkeypatch.setattr("app.tickflow.pools.get_client", get_client)
    assert pools._fetch_pool("CN_Equity_A") == []
    get_client.assert_not_called()


def test_resolve_universe_public_pool_skips_tickflow_all_a(monkeypatch):
    monkeypatch.setattr(daily_pipeline._prefs, "get_pipeline_universe_scope", lambda: "ALL")
    monkeypatch.setattr(daily_pipeline._prefs, "is_public_pool_provider", lambda: True)
    monkeypatch.setattr(
        daily_pipeline,
        "get_pool",
        lambda pool_id, **kwargs: (_ for _ in ()).throw(
            AssertionError(f"must not refresh {pool_id} via TickFlow")
        ),
    )
    monkeypatch.setattr(
        "app.services.universe_scope.resolve_symbols",
        lambda *a, **k: ["000001.SZ", "600000.SH"],
    )
    symbols = daily_pipeline.resolve_universe(
        CapabilitySet({Cap.KLINE_DAILY_BATCH: CapabilityLimits()}),
    )
    assert symbols == ["000001.SZ", "600000.SH"]


def test_index_live_daily_uses_routed_provider(monkeypatch, tmp_path):
    from app.api import indices as indices_api

    provider_df = _daily("000001.SH", date(2020, 1, 2))
    monkeypatch.setattr(kline_sync, "daily_provider_is_custom", lambda: True)
    monkeypatch.setattr(kline_sync, "fetch_routed_daily", lambda *a, **k: provider_df)
    hit = {"batch": False}
    monkeypatch.setattr(
        kline_sync,
        "sync_daily_batch",
        lambda *a, **k: hit.__setitem__("batch", True) or pl.DataFrame(),
    )
    monkeypatch.setattr(
        "app.api.indices.compute_enriched",
        lambda raw, factors=None, instruments=None: raw,
    )
    repo = KlineRepository(DataStore(tmp_path))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        repo=repo,
        capabilities=CapabilitySet(),
    )))
    payload = indices_api.get_index_daily(
        request,
        symbol="000001.SH",
        days=10,
        start_date="2020-01-01",
        end_date="2020-01-02",
    )
    assert hit["batch"] is False
    assert payload["source"] == "live"
    assert payload["rows"]


def test_depth_source_reports_custom_provider(monkeypatch):
    monkeypatch.setattr(
        "app.services.preferences.get_depth5_data_provider",
        lambda: "depth_src",
    )
    assert DepthService()._depth_source() == "depth_src"
