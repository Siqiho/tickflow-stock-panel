"""Thirtieth-round leftover mix-source / fail-open paths.

Closes residual fail-open / silent mix that round 29 left documented:
- leftover TickFlow single-symbol minute no longer mixes public / TDX
- leftover TickFlow minute / depth / full-minute / adj jobs skip after custom daily
- leftover TickFlow daily + public realtime still overlays (default install)
- unreadable leftover TickFlow date markers are fail-closed
- DuckDB remount no longer fail-opens an ungated leftover TickFlow view
- HTTP ext remount no longer leftover-globs instruments_ext

Keeps remaining TickFlow leftover contracts:
- leftover TickFlow still sees untagged-only partitions
- leftover TickFlow + free realtime stays mode=none
- leftover TickFlow daily + public realtime overlay stays labeled
- explicit adj=public / depth5=public stay user-selected
- after-hours default clock times / .env / auth stay out of scope
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ext_data as ext_api
from app.api import kline as kline_api
from app.services import kline_sync, preferences
from app.services.depth_service import DepthService
from app.services.minute_refresh import MinuteRefreshService
from app.services.quote_service import QuoteService, quote_snapshot_partition_usable
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


def _minute_df(*, route: str | None = None, ts: datetime | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "datetime": [ts or datetime(2026, 7, 17, 9, 31)],
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


def _inst_df(*, route: str | None = None, name: str = "平安银行") -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "name": [name],
        "code": ["000001"],
        "exchange": ["SZ"],
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


def test_leftover_tickflow_minute_skips_public(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    monkeypatch.setattr(
        kline_sync,
        "get_client",
        lambda: (_ for _ in ()).throw(RuntimeError("tickflow down")),
    )
    public = MagicMock(side_effect=AssertionError("must not mix public minute"))
    monkeypatch.setattr(kline_sync, "_public_minute_fallback", public)
    assert kline_sync.minute_may_use_leftover_public() is False
    out = kline_sync.fetch_minute_single(
        "000001.SZ",
        date(2026, 7, 17),
        capset=_capset(Cap.KLINE_MINUTE_BY_SYMBOL),
    )
    assert out.is_empty()
    public.assert_not_called()


def test_explicit_public_minute_still_uses_public(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "public")
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    monkeypatch.setattr(kline_sync, "_public_minute_fallback", lambda symbol, trade_date: _minute_df())
    assert kline_sync.minute_may_use_leftover_public() is True
    out = kline_sync.fetch_minute_single("000001.SZ", date(2026, 7, 17), capset=CapabilitySet())
    assert out["symbol"].to_list() == ["000001.SZ"]
    tf.assert_not_called()


def test_leftover_tickflow_minute_skips_after_custom_daily(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    _patch_custom_daily(monkeypatch)
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow minute after custom daily"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    public = MagicMock(side_effect=AssertionError("must not mix public minute"))
    monkeypatch.setattr(kline_sync, "_public_minute_fallback", public)
    assert kline_sync.leftover_tickflow_follow_daily() is False
    assert kline_sync.minute_sync_allowed(_capset(Cap.KLINE_MINUTE_BATCH)) is False
    out = kline_sync.fetch_minute_single(
        "000001.SZ",
        date(2026, 7, 17),
        capset=_capset(Cap.KLINE_MINUTE_BY_SYMBOL),
    )
    assert out.is_empty()
    tf.assert_not_called()
    public.assert_not_called()


def test_leftover_tickflow_minute_still_uses_entitled_tickflow(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    tickflow = MagicMock()
    tickflow.klines.batch.return_value = {}
    get_client = MagicMock(return_value=tickflow)
    monkeypatch.setattr(kline_sync, "get_client", get_client)
    assert kline_sync.minute_sync_allowed(_capset(Cap.KLINE_MINUTE_BATCH)) is True
    out = kline_sync.fetch_minute_single(
        "000001.SZ",
        date(2026, 7, 17),
        capset=_capset(Cap.KLINE_MINUTE_BY_SYMBOL),
    )
    assert out.is_empty()
    get_client.assert_called_once()


def test_leftover_tickflow_watchlist_minute_skips_tdx(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    monkeypatch.setattr(kline_sync, "fetch_minute_single", lambda *a, **k: pl.DataFrame())
    monkeypatch.setattr("app.services.watchlist.contains", lambda *a, **k: True)

    def fail_tdx(*_a, **_k):
        raise AssertionError("leftover TickFlow minute must not TDX-mix")

    monkeypatch.setattr(
        "app.services.free_sources.tdx_history_minute.fetch_history_minute",
        fail_tdx,
    )
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        get_minute=lambda *a, **k: pl.DataFrame(),
        get_daily=lambda *a, **k: pl.DataFrame({"date": [date(2026, 6, 29)]}),
        execute_one=lambda *a, **k: None,
    )
    app = FastAPI()
    app.include_router(kline_api.router)
    app.state.repo = repo
    resp = TestClient(app).get("/api/kline/minute?symbol=000001.SZ&date=2026-06-29")
    assert resp.status_code == 200
    assert resp.json()["source"] == "none"
    assert resp.json()["rows"] == []


def test_explicit_public_watchlist_minute_still_allows_tdx(monkeypatch, tmp_path):
    rows = _minute_df()
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "public")
    monkeypatch.setattr("app.services.watchlist.contains", lambda *a, **k: True)
    monkeypatch.setattr(
        "app.services.free_sources.tdx_history_minute.fetch_history_minute",
        lambda *a, **k: rows,
    )
    calls = []

    def fake_persist(candidate, _repo, symbol, trade_date, _daily, *, source, adapter):
        calls.append((source, adapter))
        return {"row_count": candidate.height}

    monkeypatch.setattr(kline_sync, "persist_historical_minute", fake_persist)
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        get_minute=lambda *a, **k: rows,
        get_daily=lambda *a, **k: pl.DataFrame({"date": [date(2026, 6, 29)]}),
        execute_one=lambda *a, **k: None,
    )
    app = FastAPI()
    app.include_router(kline_api.router)
    app.state.repo = repo
    resp = TestClient(app).get("/api/kline/minute?symbol=000001.SZ&date=2026-06-29")
    assert resp.status_code == 200
    assert resp.json()["provider"] == "easy_tdx_1.20.6"
    assert calls == [("tdx_public", "easy_tdx_1.20.6")]


def test_unreadable_daily_marker_is_fail_closed(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    (part / "part.parquet").write_bytes(b"")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert kline_sync.usable_daily_partition_dates(tmp_path) == []


def test_unreadable_minute_marker_is_fail_closed(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    (part / "part.parquet").write_bytes(b"")
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    assert kline_sync.usable_minute_partition_dates(tmp_path) == []


def test_unreadable_quote_snapshot_marker_is_fail_closed(monkeypatch, tmp_path):
    part = tmp_path / "quote_snapshot" / "asset_type=stock" / "date=2026-07-17"
    part.mkdir(parents=True)
    path = part / "part.parquet"
    path.write_bytes(b"")
    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "tickflow")
    assert quote_snapshot_partition_usable(path) is False


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


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"


def test_leftover_tickflow_depth_skips_after_custom_daily(monkeypatch):
    monkeypatch.setattr("app.services.preferences.get_depth5_data_provider", lambda: "tickflow")
    _patch_custom_daily(monkeypatch)
    svc = DepthService.__new__(DepthService)
    routed = MagicMock(side_effect=AssertionError("must not call leftover TickFlow depth"))
    public = MagicMock(side_effect=AssertionError("must not mix public L1"))
    monkeypatch.setattr(svc, "_call_routed_depth_batch", routed)
    monkeypatch.setattr(svc, "_call_public_depth_l1", public)
    assert svc._call_depth_batch(["000001.SZ"]) == {}
    routed.assert_not_called()
    public.assert_not_called()


def test_leftover_tickflow_full_minute_skips_after_custom_daily(monkeypatch):
    monkeypatch.setattr(preferences, "get_full_minute_data_provider", lambda: "tickflow")
    _patch_custom_daily(monkeypatch)
    burst = MagicMock(side_effect=AssertionError("must not burst leftover TickFlow"))
    increment = MagicMock(side_effect=AssertionError("must not increment leftover TickFlow"))
    monkeypatch.setattr(kline_sync, "fetch_intraday_full_market_burst", burst)
    monkeypatch.setattr(kline_sync, "fetch_intraday_universe_increment", increment)
    svc = MinuteRefreshService(MagicMock())
    custom, name = svc._resolve_custom()
    assert custom is None
    assert name == "unresolved"
    svc._run_round()
    burst.assert_not_called()
    increment.assert_not_called()


def test_leftover_tickflow_adj_skips_after_custom_daily(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: False)
    _patch_custom_daily(monkeypatch)
    assert kline_sync.adj_live_fetch_allowed(_capset(Cap.ADJ_FACTOR)) is False


def test_explicit_public_adj_and_depth_still_allowed(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "public")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: True)
    monkeypatch.setattr("app.services.preferences.get_depth5_data_provider", lambda: "public")
    _patch_custom_daily(monkeypatch)
    assert kline_sync.adj_live_fetch_allowed(CapabilitySet()) is True
    svc = DepthService.__new__(DepthService)
    public = MagicMock(return_value={"000001.SZ": {"bid1": 10.0}})
    monkeypatch.setattr(svc, "_call_public_depth_l1", public)
    assert svc._call_depth_batch(["000001.SZ"]) == {"000001.SZ": {"bid1": 10.0}}
    public.assert_called_once()


def test_duckdb_custom_view_failure_stays_empty(tmp_path, monkeypatch):
    leftover = tmp_path / "kline_daily" / "date=2026-07-17"
    leftover.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(leftover / "part.parquet")
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.db.execute("SELECT count(*) FROM kline_daily").fetchone()[0] == 0

    class _Boom:
        def __init__(self, inner):
            self.inner = inner
            self.calls: list[str] = []

        def execute(self, sql, *a, **k):
            self.calls.append(str(sql))
            text = str(sql)
            if "WHERE" in text and "1=0" not in text and "DROP" not in text:
                raise RuntimeError("predicate failed")
            return self.inner.execute(sql, *a, **k)

    wrapper = _Boom(repo.store.db)
    repo.store.db = wrapper
    repo.store._register_route_filtered_view(
        "kline_daily",
        f"{tmp_path.as_posix()}/kline_daily/**/*.parquet",
        "fuyao",
    )
    assert any("WHERE 1=0" in sql for sql in wrapper.calls)
    assert not any(
        "CREATE OR REPLACE VIEW kline_daily AS SELECT * FROM read_parquet" in sql
        and "WHERE" not in sql
        for sql in wrapper.calls
    )


def test_ext_http_does_not_leftover_glob_instruments(monkeypatch, tmp_path):
    path = tmp_path / "instruments_ext" / "instruments_ext.parquet"
    path.parent.mkdir(parents=True)
    _inst_df(route="tickflow").write_parquet(path)
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.db.execute("SELECT count(*) FROM instruments_ext").fetchone()[0] == 0
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo)))
    ext_api._refresh_views(request)
    assert repo.db.execute("SELECT count(*) FROM instruments_ext").fetchone()[0] == 0


def test_untagged_only_still_serves_leftover_tickflow(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert kline_sync.usable_daily_partition_dates(tmp_path) == [date(2026, 7, 17)]
    assert kline_sync.read_usable_daily_partition(part)["close"].to_list() == [10.1]


def test_after_hours_default_clock_stays_ops_schedule(monkeypatch):
    monkeypatch.setattr(preferences, "load_server", lambda: {})
    monkeypatch.setattr(preferences, "load", lambda: {})
    assert preferences.get_pipeline_schedule() == {"hour": 15, "minute": 30}
    assert preferences.get_instruments_schedule() == {"hour": 9, "minute": 10}
    assert preferences.get_depth_finalize_time() == {"hour": 15, "minute": 2}


def test_unreadable_prefs_stay_fail_closed(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", _prefs_boom)
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", _prefs_boom)
    assert kline_sync.leftover_tickflow_follow_daily() is False
    assert kline_sync.minute_may_use_leftover_public() is False
    assert kline_sync.minute_sync_allowed(_capset(Cap.KLINE_MINUTE_BATCH)) is False
    assert kline_sync.adj_live_fetch_allowed(_capset(Cap.ADJ_FACTOR)) is False
    assert kline_sync.fetch_minute_single("000001.SZ", date(2026, 7, 17)).is_empty()
