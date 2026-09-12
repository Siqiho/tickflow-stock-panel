"""Thirty-fourth-round leftover mix-source / fail-open paths.

Closes residual fail-open / silent mix that round 33 left documented:
- catalog / reference leftover-glob no longer mix untagged extras beside
  tagged leftover
- leftover-part-only hithink / ext snapshot / financial PIT / fund-flow
  HTTP still serve extras-only leftover
- leftover TickFlow watchlist quotes skip after a custom or unresolved daily
- remount leftover-union of unreadable extras stays fail-closed

Keeps remaining TickFlow leftover contracts:
- leftover TickFlow still sees untagged-only partitions
- leftover TickFlow + free realtime stays mode=none
- leftover TickFlow daily + public realtime overlay stays labeled
- explicit adj=public / depth5=public / financial=public / pool=public stay
- after-hours default clock times / .env / auth stay out of scope
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl

from app.api import ext_data as ext_api
from app.api import free_ext as free_ext_api
from app.api import kline as kline_api
from app.data_catalog.provenance import ProvenanceService
from app.data_catalog.scanner import CatalogScanner, _catalog_file_usable
from app.services import kline_sync, preferences
from app.services.ext_data import ExtConfig, ExtField
from app.services.financial_pit import migrate_existing_financials_to_pit
from app.services.free_sources import hithink_finance
from app.services.quote_service import QuoteService
from app.services.reference_query import query_reference_dataset
from app.services.watchlist import fetch_quotes
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet
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


def _val_df(symbol: str = "000001.SZ", *, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "trade_date": [date(2026, 7, 17)],
        "close": [10.1],
        "total_mv": [100.0],
        "shares_pit_safe": [True],
        "unit_version": ["valuation_daily_v2"],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _fin_df(*, route: str | None = None, symbol: str = "000001.SZ") -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "period_end": [date(2026, 3, 31)],
        "float_shares": [1.0e10],
        "roe": [0.12],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _hithink_row(*, symbol: str = "000001.SZ", day: date | None = None) -> dict:
    row = {name: None for name in hithink_finance.LIMIT_POOL_SCHEMA}
    row.update({
        "pool_kind": "limit_up",
        "symbol": symbol,
        "ticker": symbol.split(".", 1)[0],
        "name": "平安银行",
        "trade_date": day or date(2026, 7, 17),
    })
    return row


def _patch_custom_daily(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset, wanted=name: n == wanted and dataset == "daily",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _capset(*caps: Cap) -> CapabilitySet:
    return CapabilitySet({cap: CapabilityLimits() for cap in caps})


def test_catalog_does_not_mix_untagged_extras_beside_tagged(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(part / "part.parquet")
    _daily_df(symbol="000002.SZ").write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    result = CatalogScanner(tmp_path).scan_dataset("stock_daily", "run-round34")
    assert result.state.symbol_count == 1
    assert [item.path for item in result.artifacts] == ["kline_daily/date=2026-07-17/part.parquet"]


def test_catalog_untagged_only_still_serves_leftover_tickflow(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    result = CatalogScanner(tmp_path).scan_dataset("stock_daily", "run-round34")
    assert result.state.symbol_count == 1
    assert [item.path for item in result.artifacts] == ["kline_daily/date=2026-07-17/extra.parquet"]


def test_catalog_unreadable_tagged_leftover_stays_fail_loud(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    (part / "part.parquet").write_bytes(b"")
    _daily_df(symbol="000002.SZ").write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert _catalog_file_usable("stock_daily", part / "part.parquet") is True
    result = CatalogScanner(tmp_path).scan_dataset("stock_daily", "run-round34")
    errors = result.state.payload.get("scan_errors") or []
    assert result.state.quality_status == "failed" or any("part.parquet" in str(err) for err in errors)


def test_reference_query_does_not_mix_untagged_extras(monkeypatch, tmp_path):
    part = tmp_path / "reference" / "valuation_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _val_df(route="tickflow").write_parquet(part / "part.parquet")
    _val_df(symbol="000002.SZ").write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    out = query_reference_dataset(tmp_path, "valuation_daily", symbol="000001.SZ")
    assert out["count"] == 1
    assert out["data"][0]["symbol"] == "000001.SZ"
    mixed = query_reference_dataset(tmp_path, "valuation_daily", start_date="2026-07-17")
    assert [row["symbol"] for row in mixed["data"]] == ["000001.SZ"]


def test_reference_query_untagged_only_still_serves_leftover(monkeypatch, tmp_path):
    part = tmp_path / "reference" / "valuation_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _val_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    out = query_reference_dataset(tmp_path, "valuation_daily", start_date="2026-07-17")
    assert [row["symbol"] for row in out["data"]] == ["000001.SZ"]


def test_extras_only_hithink_still_serves_leftover(tmp_path):
    part = tmp_path / hithink_finance.LIMIT_POOL_ROOT / "date=2026-07-17"
    part.mkdir(parents=True)
    pl.DataFrame(
        [_hithink_row()],
        schema=hithink_finance.LIMIT_POOL_SCHEMA,
    ).write_parquet(part / "extra.parquet")
    resolved, frame = hithink_finance.query_limit_pool(tmp_path)
    assert resolved == date(2026, 7, 17)
    assert frame["symbol"].to_list() == ["000001.SZ"]
    loaded = hithink_finance.load_limit_pool_for_date(tmp_path, date(2026, 7, 17))
    assert loaded is not None
    assert loaded["symbol"].to_list() == ["000001.SZ"]


def test_unreadable_hithink_marker_does_not_mint_latest(tmp_path):
    latest = tmp_path / hithink_finance.LIMIT_POOL_ROOT / "date=2026-07-18"
    latest.mkdir(parents=True)
    (latest / "part.parquet").write_bytes(b"")
    older = tmp_path / hithink_finance.LIMIT_POOL_ROOT / "date=2026-07-17"
    older.mkdir(parents=True)
    pl.DataFrame(
        [_hithink_row()],
        schema=hithink_finance.LIMIT_POOL_SCHEMA,
    ).write_parquet(older / "part.parquet")
    resolved, frame = hithink_finance.query_limit_pool(tmp_path)
    assert resolved == date(2026, 7, 17)
    assert frame["symbol"].to_list() == ["000001.SZ"]


def test_ext_snapshot_keeps_extras_beside_leftover_part(tmp_path):
    root = tmp_path / "ext_data" / "ext_demo"
    root.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "v": [1.0]}).write_parquet(root / "part.parquet")
    pl.DataFrame({"symbol": ["000002.SZ"], "v": [2.0]}).write_parquet(root / "extra.parquet")
    config = ExtConfig(
        id="ext_demo",
        label="demo",
        mode="snapshot",
        fields=[ExtField(name="v", label="v", dtype="float")],
    )
    assert ext_api._latest_sync_date(config, tmp_path) is not None
    assert ProvenanceService(tmp_path)._extension_materialized("ext_demo") is True


def test_ext_snapshot_extras_only_still_materialized(tmp_path):
    root = tmp_path / "ext_data" / "ext_demo"
    root.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "v": [1.0]}).write_parquet(root / "extra.parquet")
    config = ExtConfig(
        id="ext_demo",
        label="demo",
        mode="snapshot",
        fields=[ExtField(name="v", label="v", dtype="float")],
    )
    assert ext_api._latest_sync_date(config, tmp_path) is not None
    assert ProvenanceService(tmp_path)._extension_materialized("ext_demo") is True


def test_ext_latest_glob_does_not_leftover_union_unreadable(tmp_path):
    part = tmp_path / "ext_data" / "ext_demo" / "timeseries" / "date=2026-07-17"
    part.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "v": [1.0]}).write_parquet(part / "extra.parquet")
    (part / "part.parquet").write_bytes(b"")
    glob = ext_api._latest_date_partition_glob(part.parent)
    assert glob is not None
    assert "extra.parquet" in glob
    assert "*.parquet" not in glob


def test_fund_flow_http_keeps_extras_beside_leftover_part(tmp_path):
    root = tmp_path / "ext_data" / "ext_fund_flow_bk"
    root.mkdir(parents=True)
    pl.DataFrame({"code": ["BK001"], "name": ["银行"], "main_net": [1.0]}).write_parquet(
        root / "part.parquet"
    )
    pl.DataFrame({"code": ["BK002"], "name": ["混入"], "main_net": [2.0]}).write_parquet(
        root / "extra.parquet"
    )
    items = free_ext_api._load_fund_flow_snapshot(tmp_path, "ext_fund_flow_bk", 20)
    assert sorted(item["code"] for item in items) == ["BK001", "BK002"]


def test_financial_pit_migrate_sees_extras_only_leftover(monkeypatch, tmp_path):
    folder = tmp_path / "financials" / "metrics"
    folder.mkdir(parents=True)
    _fin_df().write_parquet(folder / "extra.parquet")
    monkeypatch.setattr("app.services.financial_sync._financial_route", lambda: "tickflow")
    report = migrate_existing_financials_to_pit(tmp_path, tables=("metrics",))
    assert report["tables"]["metrics"].get("exists") is True
    assert report["tables"]["metrics"].get("skipped") is not True


def test_leftover_tickflow_watchlist_skips_after_custom_daily(monkeypatch):
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    tf = MagicMock(side_effect=AssertionError("must not probe leftover TickFlow"))
    monkeypatch.setattr("app.services.watchlist.get_client", tf)
    assert fetch_quotes(["000001.SZ"], _capset(Cap.QUOTE_BATCH)) == []
    tf.assert_not_called()


def test_leftover_tickflow_watchlist_still_probes_entitled_tickflow(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    quotes = MagicMock(return_value=pl.DataFrame({"symbol": ["000001.SZ"], "last_price": [10.1]}).to_pandas())
    monkeypatch.setattr(
        "app.services.watchlist.get_client",
        lambda: SimpleNamespace(quotes=SimpleNamespace(get=quotes)),
    )
    rows = fetch_quotes(["000001.SZ"], _capset(Cap.QUOTE_BATCH))
    assert rows[0]["symbol"] == "000001.SZ"
    quotes.assert_called_once()


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
    assert kline_sync.leftover_tickflow_follow_daily() is False
    assert fetch_quotes(["000001.SZ"], _capset(Cap.QUOTE_BATCH)) == []
