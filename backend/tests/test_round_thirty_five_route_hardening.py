"""Thirty-fifth-round leftover mix-source / fail-open paths.

Closes residual fail-open / silent mix that round 34 left documented:
- kline_loader leftover-glob no longer mix untagged extras beside tagged leftover
- leftover TickFlow financial _sync_table / scheduler body skip after custom daily
- leftover TickFlow QuoteService watchlist / full-market skip after custom daily
- financial HTTP availability no longer fail-opens Cap.FINANCIAL on prefs throw
- leftover-part-only public financial / share-capital / period-stats still serve extras
- delete_ext / provenance / remount no longer leftover-union unreadable extras

Keeps remaining TickFlow leftover contracts:
- leftover TickFlow still sees untagged-only partitions
- leftover TickFlow + free realtime stays mode=none
- leftover TickFlow daily + public realtime overlay stays labeled
- explicit adj=public / depth5=public / financial=public / pool=public stay
- after-hours default clock times / .env / auth stay out of scope
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl

from app.api import ext_data as ext_api
from app.api import financials as financials_api
from app.api import kline as kline_api
from app.data_catalog.provenance import SourceProvenanceModule
from app.services import financial_sync, kline_sync, preferences
from app.services.ext_data import delete_ext_parquet
from app.services.free_sources.financials_public import (
    _period_stats_by_symbol,
    merge_write_financial_table,
)
from app.services.free_sources.kline_loader import load_daily_bars_for_symbol
from app.services.quote_service import QuoteService
from app.services import strategy_cache
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet
from app.tickflow.repository import DataStore


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


def _fin_df(*, route: str | None = None, symbol: str = "000001.SZ") -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "period_end": [date(2026, 3, 31)],
        "announce_date": [date(2026, 4, 20)],
        "float_shares": [1.0e10],
        "roe": [0.12],
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


def _provenance(data_dir):
    return SourceProvenanceModule(
        SimpleNamespace(data_dir=data_dir, control_db=SimpleNamespace(), definitions=()),
    )


def _tickflow_financial(monkeypatch) -> None:
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)


def test_kline_loader_does_not_mix_untagged_extras_beside_tagged(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(part / "part.parquet")
    _daily_df(symbol="000002.SZ").write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    rows = load_daily_bars_for_symbol(tmp_path, "000001.SZ", days=10)
    assert [row["close"] for row in rows] == [10.1]
    try:
        load_daily_bars_for_symbol(tmp_path, "000002.SZ", days=10)
        mixed = True
    except (FileNotFoundError, ValueError):
        mixed = False
    assert mixed is False


def test_kline_loader_untagged_only_still_serves_leftover_tickflow(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    rows = load_daily_bars_for_symbol(tmp_path, "000001.SZ", days=10)
    assert [row["close"] for row in rows] == [10.1]


def test_leftover_tickflow_financial_sync_skips_after_custom_daily(monkeypatch, tmp_path):
    _tickflow_financial(monkeypatch)
    _patch_custom_daily(monkeypatch)
    tf = MagicMock(side_effect=AssertionError("must not call leftover TickFlow financials"))
    monkeypatch.setattr("app.tickflow.client.get_client", tf)
    assert financial_sync.sync_metrics(tmp_path, _capset(Cap.FINANCIAL)) == 0
    assert financial_sync._sync_table(
        "income", ["000001.SZ"], tmp_path, _capset(Cap.FINANCIAL), latest_only=True,
    ) == 0
    sched = financial_sync.FinancialScheduler()
    sched._data_dir = tmp_path
    sched._capset = _capset(Cap.FINANCIAL)
    assert sched._run_body("metrics") == {}
    tf.assert_not_called()


def test_leftover_tickflow_financial_still_uses_entitled_tickflow(monkeypatch):
    _tickflow_financial(monkeypatch)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert financial_sync.financials_live_allowed(_capset(Cap.FINANCIAL)) is True


def test_explicit_public_financial_still_allowed_after_custom_daily(monkeypatch):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "public")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: True)
    _patch_custom_daily(monkeypatch)
    assert financial_sync.financials_live_allowed(CapabilitySet()) is True


def test_fin_available_prefs_exception_stays_fail_closed(monkeypatch):
    monkeypatch.setattr(
        financial_sync,
        "financials_live_allowed",
        _prefs_boom,
    )
    monkeypatch.setattr(financials_api, "_public_fin", lambda: False)
    monkeypatch.setattr(financials_api, "_custom_fin", lambda: False)
    monkeypatch.setattr(financials_api, "_local_fin_ready", lambda *_a, **_k: False)
    assert financials_api._fin_available(_capset(Cap.FINANCIAL), None) is False


def test_leftover_tickflow_quote_polls_skip_after_custom_daily(monkeypatch):
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_realtime_watchlist_symbols", lambda: ["000001.SZ"])
    tf = MagicMock(side_effect=AssertionError("must not probe leftover TickFlow"))
    monkeypatch.setattr("app.tickflow.client.get_paid_realtime_client", tf)
    service = QuoteService()
    service._fetch_watchlist_quotes()
    assert service._fetch_tickflow_full_market_records(
        all_index_symbols=set(),
        core_index_symbols=set(),
        all_etf_symbols=set(),
    ) == []
    tf.assert_not_called()


def test_leftover_tickflow_quote_polls_still_use_entitled_tickflow(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_realtime_watchlist_symbols", lambda: ["000001.SZ"])
    quotes = MagicMock(return_value=[{"symbol": "000001.SZ", "last_price": 10.1}])
    monkeypatch.setattr(
        "app.tickflow.client.get_paid_realtime_client",
        lambda: SimpleNamespace(quotes=SimpleNamespace(get=quotes, get_by_universes=quotes)),
    )
    service = QuoteService()
    service._normalize_quote_records = lambda rows: list(rows)
    service._fetch_watchlist_quotes()
    quotes.assert_called()


def test_financial_merge_sees_extras_only_leftover(monkeypatch, tmp_path):
    folder = tmp_path / "financials" / "metrics"
    folder.mkdir(parents=True)
    _fin_df().write_parquet(folder / "extra.parquet")
    _tickflow_financial(monkeypatch)
    incoming = _fin_df(symbol="000002.SZ")
    n = merge_write_financial_table(incoming, tmp_path, "metrics")
    assert n >= 2
    frame = financial_sync.get_financial_df(tmp_path, "metrics")
    assert sorted(frame["symbol"].to_list()) == ["000001.SZ", "000002.SZ"]
    stats = _period_stats_by_symbol(tmp_path, "metrics")
    assert "000001.SZ" in stats


def test_delete_ext_removes_snapshot_extras(tmp_path):
    root = tmp_path / "ext_data" / "ext_demo"
    root.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "v": [1.0]}).write_parquet(root / "part.parquet")
    pl.DataFrame({"symbol": ["000002.SZ"], "v": [2.0]}).write_parquet(root / "extra.parquet")
    delete_ext_parquet("ext_demo", tmp_path)
    assert list(root.glob("*.parquet")) == []


def test_extension_unreadable_only_is_not_materialized(tmp_path):
    root = tmp_path / "ext_data" / "ext_demo"
    root.mkdir(parents=True)
    (root / "part.parquet").write_bytes(b"")
    assert _provenance(tmp_path)._extension_materialized("ext_demo") is False
    pl.DataFrame({"symbol": ["000001.SZ"], "v": [1.0]}).write_parquet(root / "extra.parquet")
    assert _provenance(tmp_path)._extension_materialized("ext_demo") is True


def test_ext_snapshot_remount_does_not_leftover_union_unreadable(tmp_path):
    root = tmp_path / "ext_data" / "ext_demo"
    root.mkdir(parents=True)
    (root / "config.json").write_text(
        '{"id": "ext_demo", "mode": "snapshot"}', encoding="utf-8",
    )
    pl.DataFrame({"symbol": ["000001.SZ"], "v": [1.0]}).write_parquet(root / "extra.parquet")
    (root / "part.parquet").write_bytes(b"")
    store = DataStore(tmp_path)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                repo=SimpleNamespace(store=store, clear_cache=lambda: None),
            ),
        ),
    )
    ext_api._refresh_views(request)
    rows = store.db.query("SELECT symbol FROM ext_ext_demo").fetchall()
    assert [row[0] for row in rows] == ["000001.SZ"]


def test_strategy_cache_mtime_sees_extras_only_leftover(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily_enriched" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert strategy_cache._get_enriched_mtime(tmp_path, "2026-07-17") is not None


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
    monkeypatch.setattr(preferences, "get_financial_provider", _prefs_boom)
    assert kline_sync.leftover_tickflow_follow_daily() is False
    assert financial_sync.financials_live_allowed(_capset(Cap.FINANCIAL)) is False
    tf = MagicMock(side_effect=AssertionError("must not probe leftover TickFlow"))
    monkeypatch.setattr("app.tickflow.client.get_paid_realtime_client", tf)
    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_realtime_watchlist_symbols", lambda: ["000001.SZ"])
    QuoteService()._fetch_watchlist_quotes()
    tf.assert_not_called()
