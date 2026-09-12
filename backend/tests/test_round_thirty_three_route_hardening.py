"""Thirty-third-round leftover mix-source / fail-open paths.

Closes residual fail-open / silent mix that round 32 left documented:
- in-memory instrument caches no longer leftover-glob untagged extras
- leftover-part-only enriched / minute / adj / financial remounts still
  serve extras-only leftover TickFlow
- leftover TickFlow trading-day probe and corporate-actions public-sina
  skip after a custom or leftover TickFlow adj route
- user-ext factor frames keep extras visible; unreadable hithink markers
  no longer mint latest

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

from app.api import kline as kline_api
from app.factors import ext_factors
from app.services import corporate_actions_sync, kline_sync, preferences, trading_day
from app.services.ext_data import ExtConfig, ExtField
from app.services.free_sources import hithink_finance
from app.services.instrument_sync import read_usable_instruments
from app.services.quote_service import QuoteService
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


def _minute_df(*, route: str | None = None, symbol: str = "000001.SZ") -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "datetime": [datetime(2026, 7, 17, 9, 31)],
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


def _inst_df(*, route: str | None = None, name: str = "平安银行", symbol: str = "000001.SZ") -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "name": [name],
        "code": [symbol.split(".", 1)[0]],
        "exchange": [symbol.split(".", 1)[1]],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _adj_df(*, route: str | None = None, symbol: str = "000001.SZ") -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "trade_date": [date(2026, 6, 1)],
        "ex_factor": [1.1],
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


def _patch_custom_daily(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset, wanted=name: n == wanted and dataset == "daily",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _capset(*caps: Cap) -> CapabilitySet:
    return CapabilitySet({cap: CapabilityLimits() for cap in caps})


def test_instrument_cache_does_not_mix_untagged_extras(monkeypatch, tmp_path):
    root = tmp_path / "instruments"
    root.mkdir(parents=True)
    _inst_df(route="tickflow", name="平安银行").write_parquet(root / "instruments.parquet")
    _inst_df(name="混入", symbol="000002.SZ").write_parquet(root / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.get_instruments()["symbol"].to_list() == ["000001.SZ"]
    assert read_usable_instruments(tmp_path)["name"].to_list() == ["平安银行"]


def test_index_instrument_cache_does_not_mix_untagged_extras(monkeypatch, tmp_path):
    root = tmp_path / "instruments_index"
    root.mkdir(parents=True)
    _inst_df(route="tickflow", name="上证指数", symbol="000001.SH").write_parquet(
        root / "instruments_index.parquet"
    )
    _inst_df(name="混入", symbol="000002.SH").write_parquet(root / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.get_index_instruments()["symbol"].to_list() == ["000001.SH"]


def test_unreadable_tagged_leftover_still_fail_loud_without_extras(monkeypatch, tmp_path):
    good = tmp_path / "kline_daily" / "date=2026-07-17"
    good.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(good / "part.parquet")
    bad = tmp_path / "kline_daily" / "date=2026-07-18"
    bad.mkdir(parents=True)
    (bad / "part.parquet").write_bytes(b"")
    _daily_df(symbol="000002.SZ", day=date(2026, 7, 18)).write_parquet(bad / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert kline_sync.usable_daily_partition_dates(tmp_path) == [date(2026, 7, 17)]
    assert [path.name for path in kline_sync.usable_daily_partition_files(bad)] == ["part.parquet"]
    assert kline_sync.read_usable_daily_partition(bad).is_empty()


def test_extras_only_enriched_still_serves_leftover_tickflow(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily_enriched" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    repo = KlineRepository(DataStore(tmp_path))
    df, latest = repo.get_enriched_latest()
    assert latest == date(2026, 7, 17)
    assert df["symbol"].to_list() == ["000001.SZ"]


def test_extras_only_minute_latest_still_serves_leftover_tickflow(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    _minute_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.latest_minute_date("000001.SZ") == date(2026, 7, 17)


def test_extras_only_adj_still_serves_leftover_tickflow(monkeypatch, tmp_path):
    folder = tmp_path / "adj_factor"
    folder.mkdir(parents=True)
    _adj_df().write_parquet(folder / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    assert kline_sync.get_adj_factor_df(tmp_path)["symbol"].to_list() == ["000001.SZ"]
    store = DataStore(tmp_path)
    assert [row[0] for row in store.db.query("SELECT symbol FROM adj_factor").fetchall()] == [
        "000001.SZ",
    ]


def test_tagged_adj_does_not_concat_untagged_extras(monkeypatch, tmp_path):
    folder = tmp_path / "adj_factor"
    folder.mkdir(parents=True)
    _adj_df(route="tickflow", symbol="000001.SZ").write_parquet(folder / "all.parquet")
    _adj_df(symbol="000002.SZ").write_parquet(folder / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    assert kline_sync.get_adj_factor_df(tmp_path)["symbol"].to_list() == ["000001.SZ"]


def test_unreadable_tagged_adj_does_not_mix_untagged(monkeypatch, tmp_path):
    folder = tmp_path / "adj_factor"
    folder.mkdir(parents=True)
    (folder / "all.parquet").write_bytes(b"")
    _adj_df().write_parquet(folder / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    assert kline_sync.get_adj_factor_df(tmp_path).is_empty()


def test_extras_only_financials_still_remount_leftover_tickflow(monkeypatch, tmp_path):
    folder = tmp_path / "financials" / "metrics"
    folder.mkdir(parents=True)
    _fin_df().write_parquet(folder / "extra.parquet")
    monkeypatch.setattr("app.services.financial_sync._financial_route", lambda: "tickflow")
    store = DataStore(tmp_path)
    assert [row[0] for row in store.db.query("SELECT symbol FROM financials_metrics").fetchall()] == [
        "000001.SZ",
    ]


def test_leftover_tickflow_trading_day_skips_after_custom_daily(monkeypatch):
    trading_day.reset_cache()
    _patch_custom_daily(monkeypatch)
    tf = MagicMock(side_effect=AssertionError("must not probe leftover TickFlow"))
    monkeypatch.setattr("app.tickflow.client.get_client", tf)
    monday = datetime(2026, 9, 7, 10, 0, tzinfo=timezone(timedelta(hours=8)))
    assert trading_day._probe_tickflow(monday) is None
    tf.assert_not_called()


def test_leftover_tickflow_trading_day_still_probes_entitled_tickflow(monkeypatch):
    trading_day.reset_cache()
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")

    class _FakeQuotes:
        def get(self, symbols):
            return [{"timestamp": monday.timestamp() * 1000}]

    monday = datetime(2026, 9, 7, 10, 0, tzinfo=timezone(timedelta(hours=8)))
    monkeypatch.setattr(
        "app.tickflow.client.get_client",
        lambda: SimpleNamespace(quotes=_FakeQuotes()),
    )
    assert trading_day._probe_tickflow(monday) is True


def test_leftover_tickflow_adj_does_not_write_public_sina(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kline_sync.adj_route", lambda: "tickflow")
    public = MagicMock(side_effect=AssertionError("must not write public sina"))
    monkeypatch.setattr(corporate_actions_sync, "sync_adj_factor_public", public)
    report = corporate_actions_sync.run_corporate_actions_loop(
        tmp_path,
        symbols=["000001.SZ"],
        fetch_missing_adj=True,
        fetch_sharebonus=False,
        publish_actions=False,
    )
    assert report["adj_sync"]["skipped"] is True
    public.assert_not_called()


def test_explicit_public_adj_still_fills_corporate_actions(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.kline_sync.adj_route", lambda: "public")
    public = MagicMock(return_value={"rows_written": 1, "symbols_done": 1})
    monkeypatch.setattr(corporate_actions_sync, "sync_adj_factor_public", public)
    report = corporate_actions_sync.run_corporate_actions_loop(
        tmp_path,
        symbols=["000001.SZ"],
        fetch_missing_adj=True,
        fetch_sharebonus=False,
        publish_actions=False,
    )
    assert report["adj_sync"]["ok"] is True
    public.assert_called_once()


def test_ext_factor_snapshot_keeps_extras_beside_leftover_part(tmp_path):
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
    frame = ext_factors._snapshot_frame(tmp_path, config, config.fields)
    assert sorted(frame["symbol"].to_list()) == ["000001.SZ", "000002.SZ"]


def test_unreadable_hithink_marker_does_not_mint_latest(tmp_path):
    root = tmp_path / hithink_finance.LIMIT_POOL_ROOT
    latest = root / "date=2026-07-18"
    latest.mkdir(parents=True)
    (latest / "part.parquet").write_bytes(b"")
    older = root / "date=2026-07-17"
    older.mkdir(parents=True)
    row = {name: None for name in hithink_finance.LIMIT_POOL_SCHEMA}
    row.update({
        "pool_kind": "limit_up",
        "symbol": "000001.SZ",
        "ticker": "000001",
        "name": "平安银行",
        "trade_date": date(2026, 7, 17),
    })
    pl.DataFrame([row], schema=hithink_finance.LIMIT_POOL_SCHEMA).write_parquet(older / "part.parquet")
    resolved, frame = hithink_finance.query_limit_pool(tmp_path)
    assert resolved == date(2026, 7, 17)
    assert frame["symbol"].to_list() == ["000001.SZ"]


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
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", _prefs_boom)
    assert kline_sync.leftover_tickflow_follow_daily() is False
    assert kline_sync.get_adj_factor_df("/tmp/missing-adj-round33").is_empty()
    monday = datetime(2026, 9, 7, 10, 0, tzinfo=timezone(timedelta(hours=8)))
    assert trading_day._probe_tickflow(monday) is None
