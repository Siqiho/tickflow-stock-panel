"""Thirty-seventh-round leftover mix-source / fail-open paths.

Closes residual fail-open / silent mix that round 36 left documented:
- feature_availability adj / depth / quote no longer advertise live TickFlow
  after a custom or unresolved daily just because Cap is present
- minute_availability leftover TickFlow after custom daily no longer claims
  full-market TickFlow sync
- DepthService lifecycle / labels skip leftover TickFlow after custom daily
- QuoteService leftover TickFlow realtime_mode is none after custom daily
- settings route refresh stops leftover TickFlow depth / quote loops
- leftover TickFlow pool universe primitive skips after custom daily
- catalog instruments no longer leftover-serve after a custom daily switch

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
from app.data_catalog.control_db import CatalogControlDB
from app.data_catalog.scanner import _catalog_file_usable, _catalog_route_token
from app.data_catalog.service import CatalogService
from app.services import kline_sync, preferences
from app.services.depth_service import DepthService
from app.services.quote_service import QuoteService
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


def _patch_custom_daily(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset, wanted=name: n == wanted and dataset == "daily",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _capset(*caps: Cap) -> CapabilitySet:
    return CapabilitySet({cap: CapabilityLimits() for cap in caps})


def _catalog_by_id(service: CatalogService) -> dict:
    return {entry.descriptor.dataset_id: entry for entry in service.list_catalog().datasets}


def test_feature_availability_does_not_advertise_tickflow_after_custom_daily(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_minute_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    monkeypatch.setattr(preferences, "is_public_adj_factor_provider", lambda name=None: False)
    _patch_custom_daily(monkeypatch)
    folder = tmp_path / "adj_factor"
    folder.mkdir(parents=True)
    _adj_df(route="tickflow").write_parquet(folder / "all.parquet")
    feats = feature_availability(
        _capset(Cap.FINANCIAL, Cap.ADJ_FACTOR, Cap.DEPTH5_BATCH, Cap.QUOTE_BATCH),
        data_dir=tmp_path,
    )
    assert feats["adj_factor"]["source"] != "tickflow"
    assert feats["depth"]["source"] == "none"
    assert feats["depth"]["available"] is False
    assert feats["depth"]["fallback"] is None
    assert feats["quote"]["source"] == "none"
    assert feats["quote"]["available"] is False
    assert feats["quote"]["mode"] == "none"


def test_feature_availability_still_advertises_tickflow_on_leftover_daily(monkeypatch):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_minute_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    monkeypatch.setattr(preferences, "is_public_adj_factor_provider", lambda name=None: False)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    feats = feature_availability(
        _capset(Cap.ADJ_FACTOR, Cap.DEPTH5_BATCH, Cap.QUOTE_BATCH),
    )
    assert feats["adj_factor"]["source"] == "tickflow"
    assert feats["depth"]["source"] == "tickflow"
    assert feats["quote"]["source"] == "tickflow"


def test_minute_availability_no_live_tickflow_after_custom_daily(monkeypatch):
    monkeypatch.setattr(preferences, "get_minute_data_provider", lambda: "tickflow")
    _patch_custom_daily(monkeypatch)
    info = minute_availability(_capset(Cap.KLINE_MINUTE_BATCH), user_enabled=True)
    assert info["available"] is False
    assert info["full_market_sync_allowed"] is False
    assert info["source"] != "tickflow"
    assert info["view_available"] is True


def test_depth_has_capability_skips_after_custom_daily(monkeypatch):
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "tickflow")
    _patch_custom_daily(monkeypatch)
    svc = DepthService()
    assert svc._has_capability() is False
    assert svc._depth_source() == "none"


def test_depth_has_capability_still_true_on_leftover_tickflow(monkeypatch):
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "tickflow")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    svc = DepthService()
    assert svc._has_capability() is True


def test_depth_public_stays_available_after_custom_daily(monkeypatch):
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "public")
    _patch_custom_daily(monkeypatch)
    svc = DepthService()
    assert svc._has_capability() is True
    assert svc._depth_source() == "local_public"


def test_quote_realtime_mode_none_after_custom_daily(monkeypatch):
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "pro"))
    _patch_custom_daily(monkeypatch)
    assert QuoteService.realtime_mode() == "none"
    assert QuoteService.is_realtime_allowed() is False


def test_quote_realtime_mode_keeps_paid_on_leftover_daily(monkeypatch):
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "pro"))
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert QuoteService.realtime_mode() == "full_market"


def test_quote_public_stays_full_market_after_custom_daily(monkeypatch):
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "public")
    _patch_custom_daily(monkeypatch)
    assert QuoteService.realtime_mode() == "full_market"


def test_refresh_route_surfaces_stops_leftover_depth_and_quote(monkeypatch):
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.kline_sync.refresh_route_surfaces", lambda repo=None: None)
    qs = SimpleNamespace(_running=True, stop=MagicMock())
    ds = SimpleNamespace(_running=True, stop_polling=MagicMock())
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                repo=None,
                capabilities=_capset(Cap.DEPTH5_BATCH, Cap.QUOTE_BATCH),
                financial_scheduler=None,
                quote_service=qs,
                depth_service=ds,
            ),
        ),
    )
    settings_api._refresh_route_surfaces(request)
    qs.stop.assert_called_once_with(persist=False)
    ds.stop_polling.assert_called_once()


def test_refresh_route_surfaces_keeps_public_quote_after_custom_daily(monkeypatch):
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "public")
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "public")
    monkeypatch.setattr("app.services.kline_sync.refresh_route_surfaces", lambda repo=None: None)
    qs = SimpleNamespace(_running=True, stop=MagicMock())
    ds = SimpleNamespace(_running=True, stop_polling=MagicMock())
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                repo=None,
                capabilities=_capset(),
                financial_scheduler=None,
                quote_service=qs,
                depth_service=ds,
            ),
        ),
    )
    settings_api._refresh_route_surfaces(request)
    qs.stop.assert_not_called()
    ds.stop_polling.assert_not_called()


def test_find_universe_id_skips_after_custom_daily(monkeypatch):
    _patch_custom_daily(monkeypatch)
    tf = MagicMock(side_effect=AssertionError("must not probe leftover TickFlow"))
    monkeypatch.setattr(pools, "get_client", tf)
    assert pools._find_universe_id(["沪深300"]) is None
    tf.assert_not_called()


def test_find_universe_id_still_uses_leftover_tickflow(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    items = [{"id": "csi300", "name": "沪深300"}]
    monkeypatch.setattr(
        pools,
        "get_client",
        lambda: SimpleNamespace(universes=SimpleNamespace(list=lambda: items)),
    )
    assert pools._find_universe_id(["沪深300"]) == "csi300"


def test_catalog_instruments_hide_after_custom_daily(monkeypatch, tmp_path):
    path = tmp_path / "instruments" / "instruments.parquet"
    path.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "name": ["pingan"],
        "code": ["000001"],
        "as_of": [date(2026, 7, 17)],
        "route": ["tickflow"],
    }).write_parquet(path)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert _catalog_file_usable("stock_instruments", path) is True
    assert _catalog_route_token("stock_instruments") == "tickflow"
    service = CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())
    service.rescan()
    first = _catalog_by_id(service)
    assert first["stock_instruments"].state.latest_time == "2026-07-17"
    _patch_custom_daily(monkeypatch)
    assert _catalog_file_usable("stock_instruments", path) is False
    assert _catalog_route_token("stock_instruments") == "fuyao"
    second = _catalog_by_id(service)
    assert second["stock_instruments"].state.latest_time is None
    assert second["stock_instruments"].descriptor.availability.serving_ready is False


def test_catalog_instruments_untagged_still_serve_leftover_tickflow(monkeypatch, tmp_path):
    path = tmp_path / "instruments" / "instruments.parquet"
    path.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "name": ["pingan"],
        "as_of": [date(2026, 7, 17)],
    }).write_parquet(path)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert _catalog_file_usable("stock_instruments", path) is True


def test_untagged_only_still_serves_leftover_tickflow(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert kline_sync.usable_daily_partition_dates(tmp_path) == [date(2026, 7, 17)]
    assert kline_sync.read_usable_daily_partition(part)["close"].to_list() == [10.1]


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
    assert kline_sync.leftover_tickflow_follow_daily() is False
    assert QuoteService.realtime_mode() == "none"
    svc = DepthService()
    assert svc._has_capability() is False
    assert svc._depth_source() == "none"
    tf = MagicMock(side_effect=AssertionError("must not probe leftover TickFlow"))
    monkeypatch.setattr(pools, "get_client", tf)
    assert pools._find_universe_id(["沪深300"]) is None
    tf.assert_not_called()
