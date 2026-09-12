"""Thirty-eighth-round leftover mix-source / fail-open paths.

Closes residual fail-open / silent mix that round 37 left documented:
- leftover TickFlow minute / adj / depth / quote / financial / pool files
  no longer leftover-serve after a custom or unresolved daily
- feature_availability websocket no longer advertises live TickFlow after
  a custom daily just because Cap.WEBSOCKET is present
- TickFlow provider primitives skip leftover TickFlow after custom daily
- settings route refresh stops leftover TickFlow MinuteRefresh loops
- MinuteRefresh leftover TickFlow capability skips after custom daily
- catalog leftover TickFlow-routed datasets hide after custom daily
- ALL expansion leftover TickFlow also follows leftover_tickflow_follow_daily
- data_lab leftover-glob fallback stays fail-closed when import fails

Keeps remaining TickFlow leftover contracts:
- leftover TickFlow still sees untagged-only partitions
- leftover TickFlow + free realtime stays mode=none
- leftover TickFlow daily + public realtime overlay stays labeled
- leftover TickFlow single-symbol minute public view stays
- explicit adj=public / depth5=public / financial=public / pool=public stay
- catalog / /api/data storage walks still see leftover bytes
- after-hours default clock times / .env / auth stay out of scope
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl

from app.api import kline as kline_api
from app.api import settings as settings_api
from app.data_catalog.scanner import _catalog_file_usable
from app.data_providers.tickflow_provider import TickFlowProvider
from app.services import kline_sync, preferences
from app.services.depth_service import depth_cache_usable
from app.services.financial_sync import financial_cache_usable
from app.services.instrument_sync import instrument_cache_usable
from app.services.minute_refresh import MinuteRefreshService
from app.services.quote_service import QuoteService, quote_snapshot_cache_usable
from app.services.universe_scope import tickflow_all_a_expansion_allowed
from app.tickflow import pools
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet, feature_availability
from app.tickflow.capabilities import minute_availability


def _prefs_boom(*_a, **_k):
    raise RuntimeError("prefs unreadable")


def _daily_df(symbol: str = "000001.SZ", *, route: str | None = None, day: date | None = None) -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "date": [day or date(2026, 7, 17)],
        "open": [10.0],
        "high": [10.2],
        "low": [9.9],
        "close": [10.1],
        "volume": [100.0],
        "amount": [101000.0],
        "change_pct": [0.01],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _quote_df(*, route: str | None = None, day: date | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "date": [day or date(2026, 7, 18)],
        "open": [10.0],
        "high": [10.2],
        "low": [9.9],
        "close": [10.1],
        "volume": [100.0],
        "amount": [1010.0],
        "source": ["tencent"],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _adj_df(*, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "trade_date": [date(2026, 7, 17)],
        "ex_factor": [1.0],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _minute_df(*, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "datetime": [date(2026, 7, 17)],
        "open": [10.0],
        "high": [10.2],
        "low": [9.9],
        "close": [10.1],
        "volume": [100.0],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _fin_df(*, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "end_date": [date(2026, 3, 31)],
        "revenue": [1.0],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _depth_df(*, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "sealed": [True],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _pool_df(*, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "as_of": [date(2026, 7, 17)],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _patch_custom_daily(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset, wanted=name: n == wanted and dataset == "daily",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _capset(*caps: Cap) -> CapabilitySet:
    return CapabilitySet({cap: CapabilityLimits() for cap in caps})


def test_leftover_tickflow_files_hide_after_custom_daily(monkeypatch):
    tagged = _daily_df(route="tickflow")
    untagged = _daily_df()
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert kline_sync.daily_cache_usable(tagged, "tickflow") is True
    assert kline_sync.daily_cache_usable(untagged, "tickflow") is True
    assert kline_sync.minute_cache_usable(_minute_df(route="tickflow"), "tickflow") is True
    assert kline_sync.adj_cache_usable(_adj_df(route="tickflow"), "tickflow") is True
    assert depth_cache_usable(_depth_df(route="tickflow"), "tickflow") is True
    assert quote_snapshot_cache_usable(_quote_df(route="tickflow"), "tickflow") is True
    assert financial_cache_usable(_fin_df(route="tickflow"), "tickflow") is True
    assert pools.pool_cache_usable(_pool_df(route="tickflow"), "tickflow") is True
    assert instrument_cache_usable(_daily_df(route="tickflow"), "tickflow") is True
    _patch_custom_daily(monkeypatch)
    assert kline_sync.leftover_tickflow_files_allowed("tickflow") is False
    assert kline_sync.leftover_tickflow_files_allowed("public") is True
    assert kline_sync.leftover_tickflow_files_allowed("fuyao") is True
    assert kline_sync.daily_cache_usable(tagged, "tickflow") is False
    assert kline_sync.daily_cache_usable(untagged, "tickflow") is False
    assert kline_sync.minute_cache_usable(_minute_df(route="tickflow"), "tickflow") is False
    assert kline_sync.minute_cache_usable(_minute_df(), "tickflow") is False
    assert kline_sync.adj_cache_usable(_adj_df(route="tickflow"), "tickflow") is False
    assert depth_cache_usable(_depth_df(route="tickflow"), "tickflow") is False
    assert quote_snapshot_cache_usable(_quote_df(route="tickflow"), "tickflow") is False
    assert financial_cache_usable(_fin_df(route="tickflow"), "tickflow") is False
    assert pools.pool_cache_usable(_pool_df(route="tickflow"), "tickflow") is False
    assert instrument_cache_usable(_daily_df(route="tickflow"), "tickflow") is False


def test_public_files_still_serve_after_custom_daily(monkeypatch):
    _patch_custom_daily(monkeypatch)
    assert kline_sync.adj_cache_usable(_adj_df(route="public"), "public") is True
    assert depth_cache_usable(_depth_df(route="public"), "public") is True
    assert quote_snapshot_cache_usable(_quote_df(route="public"), "public") is True
    assert financial_cache_usable(_fin_df(route="public"), "public") is True
    assert pools.pool_cache_usable(_pool_df(route="public"), "public") is True
    assert kline_sync.minute_cache_usable(_minute_df(route="public"), "public") is True


def test_websocket_does_not_advertise_tickflow_after_custom_daily(monkeypatch):
    _patch_custom_daily(monkeypatch)
    feats = feature_availability(_capset(Cap.WEBSOCKET))
    assert feats["websocket"]["source"] != "tickflow"
    assert feats["websocket"]["available"] is False
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    feats = feature_availability(_capset(Cap.WEBSOCKET))
    assert feats["websocket"]["source"] == "tickflow"
    assert feats["websocket"]["available"] is True


def test_tickflow_provider_primitives_skip_after_custom_daily(monkeypatch):
    _patch_custom_daily(monkeypatch)
    tf = MagicMock(side_effect=AssertionError("must not probe leftover TickFlow"))
    monkeypatch.setattr("app.data_providers.tickflow_provider.get_client", tf)
    provider = TickFlowProvider()
    assert provider.get_instruments("stock").is_empty()
    assert provider.get_daily(["000001.SZ"], None, None, "stock").is_empty()
    assert provider.get_adj_factors(["000001.SZ"], None, None, "stock").is_empty()
    assert provider.get_realtime(symbols=["000001.SZ"]).is_empty()
    assert provider.get_depth_batch(["000001.SZ"]) == {}
    tf.assert_not_called()


def test_tickflow_provider_still_uses_leftover_tickflow(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    client = SimpleNamespace(
        exchanges=SimpleNamespace(get_instruments=lambda *a, **k: []),
        klines=SimpleNamespace(batch=lambda *a, **k: {}, ex_factors=lambda *a, **k: []),
        quotes=SimpleNamespace(get=lambda *a, **k: [], get_by_universes=lambda *a, **k: []),
        depth=SimpleNamespace(batch=lambda *a, **k: {}),
    )
    monkeypatch.setattr("app.data_providers.tickflow_provider.get_client", lambda: client)
    provider = TickFlowProvider()
    assert provider.get_instruments("stock").is_empty()
    assert provider.get_realtime(symbols=["000001.SZ"]).is_empty()
    assert provider.get_depth_batch(["000001.SZ"]) == {}


def test_minute_refresh_capability_skips_after_custom_daily(monkeypatch):
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(preferences, "get_full_minute_data_provider", lambda: "tickflow")
    svc = MinuteRefreshService(SimpleNamespace())
    svc.set_app_state(SimpleNamespace(capabilities=_capset(Cap.INTRADAY_UNIVERSE)))
    assert svc.capability_ok() is False
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert svc.capability_ok() is True


def test_minute_refresh_custom_stays_after_custom_daily(monkeypatch):
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(preferences, "get_full_minute_data_provider", lambda: "fuyao")
    svc = MinuteRefreshService(SimpleNamespace())
    svc.set_app_state(SimpleNamespace(capabilities=_capset(Cap.INTRADAY_UNIVERSE)))
    assert svc.capability_ok() is True


def test_refresh_route_surfaces_stops_leftover_minute_refresh(monkeypatch):
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_full_minute_data_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.kline_sync.refresh_route_surfaces", lambda repo=None: None)
    qs = SimpleNamespace(_running=True, stop=MagicMock())
    ds = SimpleNamespace(_running=True, stop_polling=MagicMock())
    mrs = SimpleNamespace(stop=MagicMock())
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                repo=None,
                capabilities=_capset(Cap.DEPTH5_BATCH, Cap.QUOTE_BATCH, Cap.INTRADAY_UNIVERSE),
                financial_scheduler=None,
                quote_service=qs,
                depth_service=ds,
                minute_refresh=mrs,
            ),
        ),
    )
    settings_api._refresh_route_surfaces(request)
    qs.stop.assert_called_once_with(persist=False)
    ds.stop_polling.assert_called_once()
    mrs.stop.assert_called_once()


def test_refresh_route_surfaces_keeps_custom_minute_refresh(monkeypatch):
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "public")
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "public")
    monkeypatch.setattr(preferences, "get_full_minute_data_provider", lambda: "fuyao")
    monkeypatch.setattr("app.services.kline_sync.refresh_route_surfaces", lambda repo=None: None)
    mrs = SimpleNamespace(stop=MagicMock())
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                repo=None,
                capabilities=_capset(),
                financial_scheduler=None,
                quote_service=None,
                depth_service=None,
                minute_refresh=mrs,
            ),
        ),
    )
    settings_api._refresh_route_surfaces(request)
    mrs.stop.assert_not_called()


def test_catalog_leftover_tickflow_minute_hides_after_custom_daily(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    path = part / "part.parquet"
    _minute_df(route="tickflow").write_parquet(path)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    assert _catalog_file_usable("stock_minute", path) is True
    _patch_custom_daily(monkeypatch)
    assert _catalog_file_usable("stock_minute", path) is False


def test_catalog_public_adj_stays_after_custom_daily(monkeypatch, tmp_path):
    folder = tmp_path / "adj_factor"
    folder.mkdir(parents=True)
    path = folder / "all.parquet"
    _adj_df(route="public").write_parquet(path)
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "public")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda *a, **k: True)
    _patch_custom_daily(monkeypatch)
    assert _catalog_file_usable("stock_adj_factor", path) is True


def test_all_a_expansion_follows_leftover_daily(monkeypatch):
    monkeypatch.setattr(pools, "pool_route", lambda: "tickflow")
    monkeypatch.setattr(kline_sync, "daily_provider_is_custom", lambda: False)
    monkeypatch.setattr(kline_sync, "leftover_tickflow_follow_daily", lambda: True)
    assert tickflow_all_a_expansion_allowed(_capset(Cap.KLINE_DAILY_BATCH), scope="ALL") is True
    monkeypatch.setattr(kline_sync, "leftover_tickflow_follow_daily", lambda: False)
    assert tickflow_all_a_expansion_allowed(_capset(Cap.KLINE_DAILY_BATCH), scope="ALL") is False


def test_untagged_only_still_serves_leftover_tickflow(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert kline_sync.usable_daily_partition_dates(tmp_path) == [date(2026, 7, 17)]
    assert kline_sync.read_usable_daily_partition(part)["close"].to_list() == [10.1]
    assert kline_sync.minute_cache_usable(_minute_df(), "tickflow") is True
    assert kline_sync.adj_cache_usable(_adj_df(), "tickflow") is True


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"


def test_quote_overlay_keeps_public_realtime_on_leftover_daily(monkeypatch, tmp_path):
    part = tmp_path / "quote_snapshot" / "asset_type=stock" / "date=2026-07-18"
    part.mkdir(parents=True)
    _quote_df().write_parquet(part / "part.parquet")
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    rows = [{
        "symbol": "000001.SZ",
        "date": "2026-07-17",
        "open": 10.0,
        "high": 10.0,
        "low": 10.0,
        "close": 10.0,
    }]
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "public")
    overlaid, meta = kline_api._overlay_persisted_quote_candles(
        repo, "000001.SZ", rows, date(2026, 7, 17), date(2026, 7, 18),
    )
    assert meta["applied"] is True
    assert overlaid[-1]["is_quote_snapshot"] is True
    _patch_custom_daily(monkeypatch)
    overlaid, meta = kline_api._overlay_persisted_quote_candles(
        repo, "000001.SZ", rows, date(2026, 7, 17), date(2026, 7, 18),
    )
    assert meta["applied"] is False
    assert len(overlaid) == 1


def test_minute_availability_keeps_public_view_after_custom_daily(monkeypatch):
    monkeypatch.setattr(preferences, "get_minute_data_provider", lambda: "tickflow")
    _patch_custom_daily(monkeypatch)
    info = minute_availability(_capset(Cap.KLINE_MINUTE_BATCH), user_enabled=True)
    assert info["available"] is False
    assert info["full_market_sync_allowed"] is False
    assert info["source"] != "tickflow"
    assert info["view_available"] is True


def test_after_hours_default_clock_stays_ops_schedule(monkeypatch):
    monkeypatch.setattr(preferences, "load_server", lambda: {})
    monkeypatch.setattr(preferences, "load", lambda: {})
    assert preferences.get_pipeline_schedule() == {"hour": 15, "minute": 30}
    assert preferences.get_instruments_schedule() == {"hour": 9, "minute": 10}
    assert preferences.get_depth_finalize_time() == {"hour": 15, "minute": 2}


def test_unreadable_prefs_stay_fail_closed(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", _prefs_boom)
    monkeypatch.setattr(preferences, "get_depth5_data_provider", _prefs_boom)
    monkeypatch.setattr(preferences, "get_realtime_data_provider", _prefs_boom)
    monkeypatch.setattr(preferences, "get_full_minute_data_provider", _prefs_boom)
    assert kline_sync.leftover_tickflow_follow_daily() is False
    assert kline_sync.leftover_tickflow_files_allowed("tickflow") is False
    assert QuoteService.realtime_mode() == "none"
    assert kline_sync.minute_cache_usable(_minute_df(route="tickflow"), "tickflow") is False
    assert kline_sync.adj_cache_usable(_adj_df(route="tickflow"), "tickflow") is False
    tf = MagicMock(side_effect=AssertionError("must not probe leftover TickFlow"))
    monkeypatch.setattr("app.data_providers.tickflow_provider.get_client", tf)
    assert TickFlowProvider().get_instruments("stock").is_empty()
    tf.assert_not_called()
    svc = MinuteRefreshService(SimpleNamespace())
    svc.set_app_state(SimpleNamespace(capabilities=_capset(Cap.INTRADAY_UNIVERSE)))
    assert svc.capability_ok() is False
