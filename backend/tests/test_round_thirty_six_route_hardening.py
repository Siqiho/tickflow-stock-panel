"""Thirty-sixth-round leftover mix-source / fail-open paths.

Closes residual fail-open / silent mix that round 35 left documented:
- FinancialScheduler lifecycle stops after a custom or unresolved daily
- ext remount no longer keeps a stale leftover-union on empty / parse fail
- snapshot DESCRIBE glob no longer leftover-unions unreadable extras
- share-capital / public financial height no longer leftover-part-only
  fail-open when the gated reader throws
- leftover TickFlow index-instrument primitive skips after custom daily
- financial HTTP / capability status no longer advertise live TickFlow
  after a custom daily just because Cap.FINANCIAL is present
- sector-monitor stamps no longer leftover-glob unreadable extras

Keeps remaining TickFlow leftover contracts:
- leftover TickFlow still sees untagged-only partitions
- leftover TickFlow + free realtime stays mode=none
- leftover TickFlow daily + public realtime overlay stays labeled
- explicit adj=public / depth5=public / financial=public / pool=public stay
- after-hours default clock times / .env / auth stay out of scope
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl

from app.api import ext_data as ext_api
from app.api import financials as financials_api
from app.api import kline as kline_api
from app.api import settings as settings_api
from app.services import financial_sync, index_sync, kline_sync, preferences
from app.services.ext_data import ExtConfig, ExtField
from app.services.free_sources.financials_public import sync_financials_public
from app.services.free_sources.share_capital_public import sync_share_capital_public
from app.services.quote_service import QuoteService
from app.services.sector_monitor import SectorMonitorService
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet, feature_availability
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


def _shares_df(symbol: str = "000001.SZ", *, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "period_end": [date(2026, 3, 31)],
        "announce_date": [date(2026, 4, 1)],
        "effective_date": [date(2026, 3, 31)],
        "float_shares": [1.0e10],
        "total_shares": [1.2e10],
        "source": ["public"],
        "table": ["shares"],
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


def _tickflow_financial(monkeypatch) -> None:
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)


def _ext_request(store: DataStore):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                repo=SimpleNamespace(store=store, clear_cache=lambda: None),
            ),
        ),
    )


def test_financial_scheduler_stops_after_custom_daily(monkeypatch, tmp_path):
    _tickflow_financial(monkeypatch)
    _patch_custom_daily(monkeypatch)
    sched = financial_sync.FinancialScheduler()
    sched._running = True
    sched._task = None
    sched._data_dir = tmp_path
    sched.update_capabilities(_capset(Cap.FINANCIAL))
    assert sched._running is False
    sched._running = True
    sched.start(tmp_path, _capset(Cap.FINANCIAL), auto_schedule=False)
    assert sched._running is False


def test_financial_scheduler_still_runs_on_leftover_tickflow(monkeypatch, tmp_path):
    _tickflow_financial(monkeypatch)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    sched = financial_sync.FinancialScheduler()
    sched._running = True
    sched.update_capabilities(_capset(Cap.FINANCIAL))
    assert sched._running is True
    assert financial_sync.financials_live_allowed(_capset(Cap.FINANCIAL)) is True


def test_refresh_route_surfaces_stops_leftover_financial_scheduler(monkeypatch, tmp_path):
    _tickflow_financial(monkeypatch)
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr("app.services.kline_sync.refresh_route_surfaces", lambda repo=None: None)
    sched = financial_sync.FinancialScheduler()
    sched._running = True
    sched._capset = _capset(Cap.FINANCIAL)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                repo=None,
                capabilities=_capset(Cap.FINANCIAL),
                financial_scheduler=sched,
            ),
        ),
    )
    settings_api._refresh_route_surfaces(request)
    assert sched._running is False


def test_ext_refresh_views_empties_stale_on_unreadable(tmp_path):
    root = tmp_path / "ext_data" / "ext_demo"
    root.mkdir(parents=True)
    (root / "config.json").write_text(
        '{"id": "ext_demo", "mode": "snapshot"}', encoding="utf-8",
    )
    store = DataStore(tmp_path)
    store.db.execute("CREATE OR REPLACE VIEW ext_ext_demo AS SELECT '000002.SZ' AS symbol")
    (root / "part.parquet").write_bytes(b"")
    ext_api._refresh_views(_ext_request(store))
    rows = store.db.query("SELECT * FROM ext_ext_demo").fetchall()
    assert rows == []


def test_ext_refresh_views_empties_on_parse_failure(tmp_path):
    root = tmp_path / "ext_data" / "ext_demo"
    root.mkdir(parents=True)
    (root / "config.json").write_text("{not-json", encoding="utf-8")
    store = DataStore(tmp_path)
    store.db.execute("CREATE OR REPLACE VIEW ext_ext_demo AS SELECT '000002.SZ' AS symbol")
    ext_api._refresh_views(_ext_request(store))
    rows = store.db.query("SELECT * FROM ext_ext_demo").fetchall()
    assert rows == []


def test_parquet_glob_snapshot_skips_unreadable(tmp_path):
    root = tmp_path / "ext_data" / "ext_demo"
    root.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "v": [1.0]}).write_parquet(root / "extra.parquet")
    (root / "part.parquet").write_bytes(b"")
    config = ExtConfig(
        id="ext_demo",
        label="demo",
        mode="snapshot",
        fields=[ExtField(name="v", label="v", dtype="float")],
    )
    glob = ext_api._parquet_glob(config, tmp_path)
    assert "extra.parquet" in glob
    assert "part.parquet" not in glob
    (root / "extra.parquet").unlink()
    empty = ext_api._parquet_glob(config, tmp_path)
    assert "__none__" in empty


def test_share_capital_prefs_throw_does_not_read_leftover_part(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "public")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: True)
    folder = tmp_path / "financials" / "shares"
    folder.mkdir(parents=True)
    _shares_df(symbol="000001.SZ", route="tickflow").write_parquet(folder / "part.parquet")
    monkeypatch.setattr("app.services.financial_sync.get_financial_df", _prefs_boom)
    incoming = _shares_df(symbol="000002.SZ", route="public")
    monkeypatch.setattr(
        "app.services.free_sources.share_capital_public.fetch_share_capital_history",
        lambda *_a, **_k: {"ok": 1},
    )
    monkeypatch.setattr(
        "app.services.free_sources.share_capital_public.normalize_share_capital",
        lambda *_a, **_k: incoming,
    )
    stats = sync_share_capital_public(["000002.SZ"], tmp_path, sleep_s=0)
    assert stats["published"] is True
    saved = pl.read_parquet(folder / "part.parquet")
    assert saved["symbol"].to_list() == ["000002.SZ"]


def test_financials_public_height_fail_closed_on_reader_throw(monkeypatch, tmp_path):
    folder = tmp_path / "financials" / "metrics"
    folder.mkdir(parents=True)
    _fin_df(route="tickflow").write_parquet(folder / "part.parquet")
    monkeypatch.setattr("app.services.financial_sync.get_financial_df", _prefs_boom)
    result = sync_financials_public([], tmp_path, tables=["metrics"], resume=False)
    assert result["rows"]["metrics"] == 0


def test_index_instruments_primitive_skips_after_custom_daily(monkeypatch):
    _patch_custom_daily(monkeypatch)
    tf = MagicMock(side_effect=AssertionError("must not probe leftover TickFlow"))
    monkeypatch.setattr(index_sync, "get_client", tf)
    assert index_sync._fetch_instruments_by_type("index", "index").is_empty()
    tf.assert_not_called()


def test_index_instruments_primitive_still_uses_leftover_tickflow(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    items = MagicMock(return_value=[{"symbol": "000001.SH", "name": "上证指数"}])
    monkeypatch.setattr(
        index_sync,
        "get_client",
        lambda: SimpleNamespace(exchanges=SimpleNamespace(get_instruments=items)),
    )
    frame = index_sync._fetch_instruments_by_type("index", "index")
    assert "000001.SH" in frame["symbol"].to_list()
    items.assert_called()


def test_financial_status_provider_local_after_custom_daily(monkeypatch, tmp_path):
    _tickflow_financial(monkeypatch)
    _patch_custom_daily(monkeypatch)
    folder = tmp_path / "financials" / "metrics"
    folder.mkdir(parents=True)
    _fin_df().write_parquet(folder / "part.parquet")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                capabilities=_capset(Cap.FINANCIAL),
                repo=SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path)),
                financial_scheduler=None,
            ),
        ),
    )
    status = financials_api.financial_status(request)
    assert status["available"] is True
    assert status["provider"] == "local"


def test_feature_availability_does_not_advertise_tickflow_fin_after_custom_daily(
    monkeypatch, tmp_path,
):
    _tickflow_financial(monkeypatch)
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(preferences, "get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_minute_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "public")
    monkeypatch.setattr(preferences, "is_public_adj_factor_provider", lambda name=None: False)
    folder = tmp_path / "financials" / "metrics"
    folder.mkdir(parents=True)
    _fin_df().write_parquet(folder / "part.parquet")
    feats = feature_availability(_capset(Cap.FINANCIAL), data_dir=tmp_path)
    assert feats["financial"]["source"] == "local"
    assert feats["financial"]["available"] is True


def test_sector_monitor_stamp_skips_unreadable_extras(tmp_path):
    root = tmp_path / "ext_data" / "ext_demo"
    root.mkdir(parents=True)
    (root / "config.json").write_text(
        '{"id": "ext_demo", "label": "demo", "mode": "snapshot", '
        '"fields": [{"name": "concept", "label": "概念", "dtype": "string"}]}',
        encoding="utf-8",
    )
    pl.DataFrame({"symbol": ["000001.SZ"], "concept": ["银行"]}).write_parquet(
        root / "extra.parquet",
    )
    (root / "part.parquet").write_bytes(b"")
    monitor = SectorMonitorService(SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path)))
    names = [Path(item[0]).name for item in monitor._data_signature()]
    assert "extra.parquet" in names
    assert "part.parquet" not in names


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
    monkeypatch.setattr(index_sync, "get_client", tf)
    assert index_sync._fetch_instruments_by_type("index", "index").is_empty()
    tf.assert_not_called()
    sched = financial_sync.FinancialScheduler()
    sched._running = True
    sched.update_capabilities(_capset(Cap.FINANCIAL))
    assert sched._running is False
