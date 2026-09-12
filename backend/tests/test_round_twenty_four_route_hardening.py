"""Twenty-fourth-round leftover mix-source / fail-open paths.

Closes remaining except-fallback leftover globs and leftover-shadowed
reads that round 23 left on the catalog-rescan / reference / quote-snapshot
side:
- catalog rescan skips leftover TickFlow calendars after a provider switch
- catalog list/get hide leftover serving after adj/depth/realtime/daily switch
- membership history refuses leftover rewrite after a pool switch
- reference query skips leftover valuation / membership / actions
- quote snapshots tag + filter by realtime route
- corporate-actions prior merge skips leftover after an adj switch
- daily quality skips leftover enriched turnover after a daily switch

Keeps remaining TickFlow leftover contracts:
- leftover TickFlow + free realtime stays mode=none
- entitled TickFlow minute fallback after a custom *call* failure
- leftover TickFlow single-symbol minute view may still use public / TDX
- A-share / index / ETF instruments stay TickFlow (no instrument_provider)
- quote_snapshot overlay stays an isolated live asset
- after-hours default times / .env / auth stay out of scope
- leftover TickFlow still sees untagged partitions
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import polars as pl
import pytest

from app.api import kline as kline_api
from app.data_catalog.control_db import CatalogControlDB
from app.data_catalog.service import CatalogService
from app.services import kline_sync
from app.services.market_overview_builder import latest_quote_snapshot_date
from app.services.market_snapshot import _latest_quote_snapshot
from app.services.free_sources.daily_quality import run_daily_quality_check
from app.services.quote_service import QuoteService
from app.services.reference_derived import rebuild_reference_derived
from app.services.reference_query import query_reference_dataset
from app.tickflow.repository import DataStore, KlineRepository


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
        "amount": [1010.0],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _quote_df(symbol: str = "000001.SZ", *, route: str | None = None, day: date | None = None) -> pl.DataFrame:
    day = day or date(2026, 7, 17)
    data = {
        "symbol": [symbol],
        "date": [day],
        "open": [10.0],
        "high": [10.2],
        "low": [9.9],
        "close": [10.1],
        "volume": [100.0],
        "amount": [1010.0],
        "source": ["tencent"],
        "unit_version": ["cn_quote_v1"],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _patch_custom_datasets(monkeypatch, name: str = "fuyao", datasets: set[str] | None = None) -> None:
    wanted = datasets or {"daily", "minute"}
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset, wanted=wanted, name=name: n == name and dataset in wanted,
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _patch_custom_daily(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: name)
    _patch_custom_datasets(monkeypatch, name, {"daily"})


def _write_part(root, table: str, day: str, df: pl.DataFrame) -> None:
    part = root / table / f"date={day}"
    part.mkdir(parents=True, exist_ok=True)
    df.write_parquet(part / "part.parquet")


def _write_snapshot(root, day: str, df: pl.DataFrame) -> None:
    part = root / "quote_snapshot" / "asset_type=stock" / f"date={day}"
    part.mkdir(parents=True, exist_ok=True)
    df.write_parquet(part / "part.parquet")


def test_catalog_rescan_drops_leftover_after_switch(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    service = CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())
    service.rescan()
    first = service.compatibility_status()
    assert first["daily"] is not None
    assert first["daily"]["latest_date"] == "2026-07-17"
    _patch_custom_daily(monkeypatch)
    service.rescan()
    second = service.compatibility_status()
    assert second["daily"] is None


def test_catalog_rescan_keeps_untagged_leftover_tickflow(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df())
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    service = CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())
    service.rescan()
    status = service.compatibility_status()
    assert status["daily"] is not None
    assert status["daily"]["latest_date"] == "2026-07-17"


def test_catalog_rescan_never_fail_open(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    monkeypatch.setattr(kline_sync, "daily_route", _prefs_boom)
    service = CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())
    service.rescan()
    assert service.compatibility_status()["daily"] is None


def test_membership_rebuild_skips_leftover_after_pool_switch(monkeypatch, tmp_path):
    target = tmp_path / "reference" / "index_membership_history" / "members.parquet"
    target.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["600000.SH"],
        "index_code": ["000300"],
        "pool_id": ["CSI300"],
        "as_of": [date(2026, 7, 17)],
        "effective_from": [date(2026, 7, 17)],
        "effective_to": [None],
        "route": ["tickflow"],
    }).write_parquet(target)
    monkeypatch.setattr("app.services.preferences.get_pool_provider", lambda: "fuyao")
    report = rebuild_reference_derived(
        tmp_path, datasets=["index_membership_history"],
    )
    info = report["datasets"]["index_membership_history"]
    assert info["ok"] is False
    saved = pl.read_parquet(target)
    assert saved["symbol"].to_list() == ["600000.SH"]
    queried = query_reference_dataset(tmp_path, "index_membership_history")
    assert queried["data"] == []


def test_membership_rebuild_keeps_untagged_leftover_tickflow(monkeypatch, tmp_path):
    pools = tmp_path / "pools"
    pools.mkdir()
    pl.DataFrame({
        "symbol": ["600000.SH"],
        "as_of": [date(2026, 7, 17)],
        "index_code": ["000300"],
        "source": ["csindex"],
        "pool_id": ["CSI300"],
    }).write_parquet(pools / "CSI300.parquet")
    monkeypatch.setattr("app.services.preferences.get_pool_provider", lambda: "tickflow")
    report = rebuild_reference_derived(
        tmp_path, datasets=["index_membership_history"],
    )
    assert report["datasets"]["index_membership_history"]["ok"] is True
    saved = pl.read_parquet(
        tmp_path / "reference" / "index_membership_history" / "members.parquet"
    )
    assert saved["symbol"].to_list() == ["600000.SH"]
    assert saved["route"].to_list() == ["tickflow"]


def test_membership_rebuild_never_fail_open(monkeypatch, tmp_path):
    target = tmp_path / "reference" / "index_membership_history" / "members.parquet"
    target.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["600000.SH"],
        "index_code": ["000300"],
        "pool_id": ["CSI300"],
        "as_of": [date(2026, 7, 17)],
        "effective_from": [date(2026, 7, 17)],
        "effective_to": [None],
        "route": ["tickflow"],
    }).write_parquet(target)
    monkeypatch.setattr("app.services.preferences.get_pool_provider", _prefs_boom)
    report = rebuild_reference_derived(
        tmp_path, datasets=["index_membership_history"],
    )
    assert report["datasets"]["index_membership_history"]["ok"] is False
    saved = pl.read_parquet(target)
    assert saved["symbol"].to_list() == ["600000.SH"]


def test_reference_query_drops_leftover_valuation_after_switch(monkeypatch, tmp_path):
    _write_part(
        tmp_path,
        "reference/valuation_daily",
        "2026-07-17",
        pl.DataFrame({
            "symbol": ["000001.SZ"],
            "trade_date": [date(2026, 7, 17)],
            "close": [10.1],
            "route": ["tickflow"],
        }),
    )
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    first = query_reference_dataset(tmp_path, "valuation_daily", symbol="000001.SZ")
    assert first["count"] == 1
    _patch_custom_daily(monkeypatch)
    second = query_reference_dataset(tmp_path, "valuation_daily", symbol="000001.SZ")
    assert second["data"] == []


def test_reference_query_keeps_untagged_leftover_tickflow(monkeypatch, tmp_path):
    _write_part(
        tmp_path,
        "reference/valuation_daily",
        "2026-07-17",
        pl.DataFrame({
            "symbol": ["000001.SZ"],
            "trade_date": [date(2026, 7, 17)],
            "close": [10.1],
        }),
    )
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    result = query_reference_dataset(tmp_path, "valuation_daily", symbol="000001.SZ")
    assert result["count"] == 1


def test_quote_snapshot_write_tags_realtime_route(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.preferences.get_realtime_data_provider",
        lambda: "public",
    )
    repo = KlineRepository(DataStore(tmp_path))
    repo.write_quote_snapshot_asset("stock", _quote_df())
    saved = pl.read_parquet(
        tmp_path / "quote_snapshot" / "asset_type=stock" / "date=2026-07-17" / "part.parquet"
    )
    assert saved["route"].to_list() == ["public"]


def test_quote_snapshot_write_never_fail_open(monkeypatch, tmp_path):
    leftover = _quote_df(route="tickflow")
    _write_snapshot(tmp_path, "2026-07-17", leftover)
    monkeypatch.setattr(
        "app.services.preferences.get_realtime_data_provider",
        _prefs_boom,
    )
    repo = KlineRepository(DataStore(tmp_path))
    repo.write_quote_snapshot_asset("stock", _quote_df())
    saved = pl.read_parquet(
        tmp_path / "quote_snapshot" / "asset_type=stock" / "date=2026-07-17" / "part.parquet"
    )
    assert saved["route"].to_list() == ["tickflow"]


def test_market_snapshot_drops_leftover_after_realtime_switch(monkeypatch, tmp_path):
    _write_snapshot(tmp_path, "2026-07-17", _quote_df(route="tickflow"))
    monkeypatch.setattr(
        "app.services.preferences.get_realtime_data_provider",
        lambda: "tickflow",
    )
    day, frame = _latest_quote_snapshot(tmp_path)
    assert day == date(2026, 7, 17)
    assert not frame.is_empty()
    monkeypatch.setattr(
        "app.services.preferences.get_realtime_data_provider",
        lambda: "public",
    )
    day2, frame2 = _latest_quote_snapshot(tmp_path)
    assert day2 is None
    assert frame2.is_empty()


def test_market_snapshot_keeps_untagged_leftover_public(monkeypatch, tmp_path):
    _write_snapshot(tmp_path, "2026-07-17", _quote_df())
    monkeypatch.setattr(
        "app.services.preferences.get_realtime_data_provider",
        lambda: "public",
    )
    day, frame = _latest_quote_snapshot(tmp_path)
    assert day == date(2026, 7, 17)
    assert frame["close"].to_list() == [10.1]


def test_overview_latest_snapshot_drops_leftover_after_switch(monkeypatch, tmp_path):
    _write_snapshot(tmp_path, "2026-07-17", _quote_df(route="tickflow"))
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    monkeypatch.setattr(
        "app.services.preferences.get_realtime_data_provider",
        lambda: "tickflow",
    )
    assert latest_quote_snapshot_date(repo) == date(2026, 7, 17)
    monkeypatch.setattr(
        "app.services.preferences.get_realtime_data_provider",
        lambda: "public",
    )
    assert latest_quote_snapshot_date(repo) is None


def test_kline_overlay_skips_leftover_after_realtime_switch(monkeypatch, tmp_path):
    _write_snapshot(
        tmp_path,
        "2026-07-18",
        _quote_df(day=date(2026, 7, 18), route="tickflow"),
    )
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    rows = [{
        "symbol": "000001.SZ",
        "date": "2026-07-17",
        "open": 10.0,
        "high": 10.0,
        "low": 10.0,
        "close": 10.0,
    }]
    monkeypatch.setattr(
        "app.services.preferences.get_realtime_data_provider",
        lambda: "public",
    )
    overlaid, meta = kline_api._overlay_persisted_quote_candles(
        repo, "000001.SZ", rows, date(2026, 7, 17), date(2026, 7, 18),
    )
    assert meta["applied"] is False
    assert len(overlaid) == 1


def test_kline_overlay_keeps_untagged_leftover_public(monkeypatch, tmp_path):
    _write_snapshot(tmp_path, "2026-07-18", _quote_df(day=date(2026, 7, 18)))
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    rows = [{
        "symbol": "000001.SZ",
        "date": "2026-07-17",
        "open": 10.0,
        "high": 10.0,
        "low": 10.0,
        "close": 10.0,
    }]
    monkeypatch.setattr(
        "app.services.preferences.get_realtime_data_provider",
        lambda: "public",
    )
    overlaid, meta = kline_api._overlay_persisted_quote_candles(
        repo, "000001.SZ", rows, date(2026, 7, 17), date(2026, 7, 18),
    )
    assert meta["applied"] is True
    assert overlaid[-1]["is_quote_snapshot"] is True


def test_corporate_actions_skip_leftover_prior_after_adj_switch(monkeypatch, tmp_path):
    path = tmp_path / "reference" / "corporate_actions" / "actions.parquet"
    path.parent.mkdir(parents=True)
    pl.DataFrame({
        "action_id": ["leftover-1"],
        "symbol": ["000001.SZ"],
        "ex_date": [date(2026, 7, 17)],
        "announce_date": [date(2026, 7, 1)],
        "action_type": ["dividend"],
        "cash_div": [0.1],
        "bonus_shares": [0.0],
        "transfer_shares": [0.0],
        "source": ["leftover"],
        "is_verification_signal": [False],
        "route": ["tickflow"],
    }).write_parquet(path)
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "fuyao")
    _patch_custom_datasets(monkeypatch, "fuyao", {"adj_factor"})
    queried = query_reference_dataset(tmp_path, "corporate_actions", symbol="000001.SZ")
    assert queried["data"] == []


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"


def test_valuation_write_tags_daily_route(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df())
    inst = tmp_path / "instruments" / "instruments.parquet"
    inst.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "name": ["pingan"],
        "total_shares": [100.0],
        "float_shares": [80.0],
    }).write_parquet(inst)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    report = rebuild_reference_derived(
        tmp_path,
        datasets=["valuation_daily"],
        start=date(2026, 7, 17),
        end=date(2026, 7, 17),
    )
    assert report["datasets"]["valuation_daily"]["written"] == 1
    saved = pl.read_parquet(
        tmp_path / "reference" / "valuation_daily" / "date=2026-07-17" / "part.parquet"
    )
    assert saved["route"].to_list() == ["tickflow"]


def _catalog_by_id(service: CatalogService) -> dict:
    return {entry.descriptor.dataset_id: entry for entry in service.list_catalog().datasets}


def _write_instruments(root) -> None:
    path = root / "instruments" / "instruments.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "name": ["pingan"],
        "code": ["000001"],
        "exchange": ["SZSE"],
        "region": ["CN"],
        "type": ["stock"],
        "listing_date": [date(1991, 4, 3)],
        "total_shares": [100.0],
        "float_shares": [80.0],
        "tick_size": [0.01],
        "limit_up": [11.0],
        "limit_down": [9.0],
        "as_of": [date(2026, 7, 17)],
    }).write_parquet(path)


def test_catalog_list_hides_leftover_serving_after_switch(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _write_instruments(tmp_path)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    service = CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())
    service.rescan()
    first = _catalog_by_id(service)
    assert first["stock_daily"].state.latest_time == "2026-07-17"
    assert first["stock_instruments"].state.latest_time == "2026-07-17"
    instrument_ready = first["stock_instruments"].descriptor.availability.serving_ready
    _patch_custom_daily(monkeypatch)
    second = _catalog_by_id(service)
    assert second["stock_daily"].descriptor.availability.serving_ready is False
    assert second["stock_daily"].state.latest_time is None
    assert second["stock_daily"].coverage == []
    assert second["stock_instruments"].state.latest_time == "2026-07-17"
    assert second["stock_instruments"].descriptor.availability.serving_ready is instrument_ready


def test_catalog_status_drops_adj_after_adj_switch(monkeypatch, tmp_path):
    path = tmp_path / "adj_factor" / "all.parquet"
    path.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "trade_date": [date(2026, 7, 17)],
        "ex_factor": [1.0],
        "route": ["tickflow"],
    }).write_parquet(path)
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    service = CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())
    service.rescan()
    first = service.compatibility_status()
    assert first["adj_factor"] is not None
    assert first["adj_factor"]["latest_date"] == "2026-07-17"
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "fuyao")
    _patch_custom_datasets(monkeypatch, "fuyao", {"adj_factor"})
    assert service.compatibility_status()["adj_factor"] is None


def test_catalog_list_hides_quote_snapshot_after_realtime_switch(monkeypatch, tmp_path):
    _write_snapshot(tmp_path, "2026-07-17", _quote_df(route="tickflow"))
    monkeypatch.setattr(
        "app.services.preferences.get_realtime_data_provider",
        lambda: "tickflow",
    )
    service = CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())
    service.rescan()
    first = _catalog_by_id(service)
    assert first["quote_snapshot"].state.latest_time == "2026-07-17"
    monkeypatch.setattr(
        "app.services.preferences.get_realtime_data_provider",
        lambda: "public",
    )
    second = _catalog_by_id(service)
    assert second["quote_snapshot"].descriptor.availability.serving_ready is False
    assert second["quote_snapshot"].state.latest_time is None
    assert second["quote_snapshot"].coverage == []


def test_financial_stats_leftover_only_after_rescan(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "metrics" / "part.parquet"
    path.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "period_end": [date(2026, 3, 31)],
        "roe": [12.0],
        "route": ["tickflow"],
    }).write_parquet(path)
    from app.services import preferences

    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    _patch_custom_datasets(monkeypatch, "fuyao", {"financial"})
    service = CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())
    service.rescan()
    assert service.compatibility_status()["financials"] is None


def test_daily_quality_skips_leftover_enriched(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df())
    _write_part(
        tmp_path,
        "kline_daily_enriched",
        "2026-07-17",
        pl.DataFrame({
            "symbol": ["000001.SZ"],
            "date": [date(2026, 7, 17)],
            "open": [10.0],
            "high": [10.2],
            "low": [9.9],
            "close": [10.1],
            "volume": [100.0],
            "amount": [1010.0],
            "turnover_rate": [250.0],
            "route": ["tickflow"],
        }),
    )
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "public")
    report = run_daily_quality_check(tmp_path)
    assert report["date"] == "2026-07-17"
    assert "turnover_unit_mismatch" not in {issue["code"] for issue in report["issues"]}
    assert "turnover_rate_over_100" not in report["metrics"]
