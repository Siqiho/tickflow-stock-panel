"""Thirty-second-round leftover mix-source / fail-open paths.

Closes residual fail-open / silent mix that round 31 left documented:
- unreadable tagged leftover no longer mixes untagged extras in instruments /
  financials / depth / leftover TickFlow kline_ext remount
- leftover TickFlow DuckDB views no longer coalesce-mix untagged extras
  beside tagged leftover
- leftover TickFlow adj / minute-batch / monitor / burst jobs skip after
  a custom or unresolved daily
- unreadable user-ext date markers no longer mint the latest partition

Keeps remaining TickFlow leftover contracts:
- leftover TickFlow still sees untagged-only partitions
- leftover TickFlow + free realtime stays mode=none
- leftover TickFlow daily + public realtime overlay stays labeled
- explicit adj=public / depth5=public / financial=public / pool=public stay
- after-hours default clock times / .env / auth stay out of scope
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl

from app.api import ext_data as ext_api
from app.api import kline as kline_api
from app.services import financial_sync, kline_sync, preferences
from app.services.depth_service import DepthService
from app.services.ext_data import ExtConfig, ExtField, latest_ext_parquet_files
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


def _fin_df(*, route: str | None = None, symbol: str = "000001.SZ") -> pl.DataFrame:
    data = {"symbol": [symbol], "roe": [0.12]}
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _depth_df(*, route: str | None = None, sealed: bool = True) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "sealed_up": [sealed],
        "bid1_vol": [1000.0],
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


def test_unreadable_tagged_instruments_do_not_mix_untagged(monkeypatch, tmp_path):
    root = tmp_path / "instruments"
    root.mkdir(parents=True)
    (root / "instruments.parquet").write_bytes(b"")
    _inst_df(name="混入").write_parquet(root / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    out = read_usable_instruments(tmp_path)
    assert out.is_empty()


def test_tagged_instruments_do_not_concat_untagged_extras(monkeypatch, tmp_path):
    root = tmp_path / "instruments"
    root.mkdir(parents=True)
    _inst_df(route="tickflow", name="平安银行").write_parquet(root / "instruments.parquet")
    _inst_df(name="混入", symbol="000002.SZ").write_parquet(root / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    out = read_usable_instruments(tmp_path)
    assert out["name"].to_list() == ["平安银行"]
    assert out["symbol"].to_list() == ["000001.SZ"]


def test_untagged_only_instruments_still_serve_leftover_tickflow(monkeypatch, tmp_path):
    root = tmp_path / "instruments"
    root.mkdir(parents=True)
    _inst_df(name="平安银行").write_parquet(root / "instruments.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    out = read_usable_instruments(tmp_path)
    assert out["name"].to_list() == ["平安银行"]


def test_unreadable_tagged_financials_do_not_mix_untagged(monkeypatch, tmp_path):
    folder = tmp_path / "financials" / "metrics"
    folder.mkdir(parents=True)
    (folder / "part.parquet").write_bytes(b"")
    _fin_df().write_parquet(folder / "extra.parquet")
    monkeypatch.setattr(financial_sync, "_financial_route", lambda: "tickflow")
    assert financial_sync.get_financial_df(tmp_path, "metrics").is_empty()


def test_tagged_financials_do_not_concat_untagged_extras(monkeypatch, tmp_path):
    folder = tmp_path / "financials" / "metrics"
    folder.mkdir(parents=True)
    _fin_df(route="tickflow", symbol="000001.SZ").write_parquet(folder / "part.parquet")
    _fin_df(symbol="000002.SZ").write_parquet(folder / "extra.parquet")
    monkeypatch.setattr(financial_sync, "_financial_route", lambda: "tickflow")
    out = financial_sync.get_financial_df(tmp_path, "metrics")
    assert out["symbol"].to_list() == ["000001.SZ"]


def test_unreadable_tagged_depth_does_not_mix_untagged(monkeypatch, tmp_path):
    part = tmp_path / "depth5" / "date=2026-07-17"
    part.mkdir(parents=True)
    (part / "part.parquet").write_bytes(b"")
    _depth_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr("app.services.preferences.get_depth5_data_provider", lambda: "tickflow")
    svc = DepthService.__new__(DepthService)
    svc._repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert svc._sealed_df_for_read(date(2026, 7, 17)) is None
    assert svc._sealed_artifact_for_read(date(2026, 7, 17)) is None


def test_tagged_depth_does_not_use_untagged_extras(monkeypatch, tmp_path):
    part = tmp_path / "depth5" / "date=2026-07-17"
    part.mkdir(parents=True)
    _depth_df(route="tickflow", sealed=True).write_parquet(part / "part.parquet")
    _depth_df(sealed=False).write_parquet(part / "extra.parquet")
    monkeypatch.setattr("app.services.preferences.get_depth5_data_provider", lambda: "tickflow")
    svc = DepthService.__new__(DepthService)
    svc._repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    df = svc._sealed_df_for_read(date(2026, 7, 17))
    assert df is not None
    assert df["sealed_up"].to_list() == [True]


def test_unreadable_tagged_kline_ext_does_not_mix_untagged(monkeypatch, tmp_path):
    latest = tmp_path / "kline_ext" / "date=2026-07-18"
    latest.mkdir(parents=True)
    (latest / "part.parquet").write_bytes(b"")
    pl.DataFrame({"symbol": ["000002.SZ"], "factor": [9.0]}).write_parquet(latest / "extra.parquet")
    older = tmp_path / "kline_ext" / "date=2026-07-17"
    older.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "factor": [1.0]}).write_parquet(older / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    files = kline_sync.latest_preferred_readable_partition_files(tmp_path / "kline_ext", "tickflow")
    assert [path.parent.name for path in files] == ["date=2026-07-17"]
    store = DataStore(tmp_path)
    assert [row[0] for row in store.db.query("SELECT factor FROM kline_ext").fetchall()] == [1.0]


def test_tagged_kline_ext_does_not_union_untagged_extras(monkeypatch, tmp_path):
    part = tmp_path / "kline_ext" / "date=2026-07-18"
    part.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "factor": [2.0], "route": ["tickflow"]}).write_parquet(
        part / "part.parquet"
    )
    pl.DataFrame({"symbol": ["000002.SZ"], "factor": [9.0]}).write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    store = DataStore(tmp_path)
    assert [row[0] for row in store.db.query("SELECT factor FROM kline_ext").fetchall()] == [2.0]


def test_duckdb_leftover_view_skips_untagged_extras_beside_tagged(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df(route="tickflow").write_parquet(part / "part.parquet")
    _daily_df(symbol="000002.SZ").write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    repo = KlineRepository(DataStore(tmp_path))
    symbols = [row[0] for row in repo.db.execute("SELECT symbol FROM kline_daily").fetchall()]
    assert symbols == ["000001.SZ"]


def test_duckdb_untagged_only_still_serves_leftover_tickflow(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.db.execute("SELECT close FROM kline_daily").fetchone()[0] == 10.1


def test_unreadable_ext_marker_does_not_mint_latest(tmp_path):
    root = tmp_path / "ext_data" / "ext_demo" / "timeseries"
    latest = root / "date=2026-07-18"
    latest.mkdir(parents=True)
    (latest / "part.parquet").write_bytes(b"")
    older = root / "date=2026-07-17"
    older.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "v": [1.0]}).write_parquet(older / "part.parquet")
    config = ExtConfig(
        id="ext_demo",
        label="demo",
        mode="timeseries",
        fields=[ExtField(name="v", label="v", dtype="float")],
    )
    files = latest_ext_parquet_files(tmp_path, config)
    assert files
    assert "2026-07-17" in files[0].as_posix()
    assert "2026-07-18" not in files[0].as_posix()
    glob = ext_api._latest_date_partition_glob(root)
    assert glob is not None
    assert "2026-07-17" in glob
    assert "2026-07-18" not in glob


def test_leftover_tickflow_adj_jobs_skip_after_custom_daily(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: False)
    _patch_custom_daily(monkeypatch)
    tf = MagicMock(side_effect=AssertionError("must not call leftover TickFlow adj"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    rows, symbols = kline_sync.sync_adj_factor(
        ["000001.SZ"],
        KlineRepository(DataStore(tmp_path)),
        _capset(Cap.ADJ_FACTOR),
    )
    assert rows == 0
    assert symbols == []
    assert kline_sync.fetch_adj_factor_single("000001.SZ", capset=_capset(Cap.ADJ_FACTOR)).is_empty()
    tf.assert_not_called()


def test_leftover_tickflow_minute_jobs_skip_after_custom_daily(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    _patch_custom_daily(monkeypatch)
    tf = MagicMock(side_effect=AssertionError("must not call leftover TickFlow minute"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    assert kline_sync.sync_minute_batch(["000001.SZ"], capset=_capset(Cap.KLINE_MINUTE_BATCH)).is_empty()
    assert kline_sync.fetch_intraday_monitor_batch(
        ["000001.SZ"],
        _capset(Cap.INTRADAY_BATCH),
        now=datetime(2026, 7, 17, 10, 0),
    ).is_empty()
    burst, burst_n = kline_sync.fetch_intraday_full_market_burst(
        ["000001.SZ"], _capset(Cap.INTRADAY_BATCH),
    )
    assert burst.is_empty()
    assert burst_n == 0
    increment, increment_n = kline_sync.fetch_intraday_universe_increment()
    assert increment.is_empty()
    assert increment_n == 0
    tf.assert_not_called()


def test_leftover_tickflow_adj_still_uses_entitled_tickflow(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: False)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert kline_sync.adj_live_fetch_allowed(_capset(Cap.ADJ_FACTOR)) is True
    assert kline_sync.leftover_tickflow_follow_daily() is True


def test_explicit_public_adj_still_allowed_after_custom_daily(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "public")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: True)
    _patch_custom_daily(monkeypatch)
    public = MagicMock(return_value=(1, ["000001.SZ"]))
    monkeypatch.setattr(kline_sync, "_sync_public_adj_factor", public)
    tf = MagicMock(side_effect=AssertionError("must not call leftover TickFlow adj"))
    monkeypatch.setattr(kline_sync, "get_client", tf)
    rows, symbols = kline_sync.sync_adj_factor(
        ["000001.SZ"],
        KlineRepository(DataStore(tmp_path)),
        CapabilitySet(),
    )
    assert rows == 1
    assert symbols == ["000001.SZ"]
    public.assert_called_once()
    tf.assert_not_called()


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
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", _prefs_boom)
    assert kline_sync.leftover_tickflow_follow_daily() is False
    assert kline_sync.adj_live_fetch_allowed(_capset(Cap.ADJ_FACTOR)) is False
    assert kline_sync.sync_minute_batch(["000001.SZ"], capset=_capset(Cap.KLINE_MINUTE_BATCH)).is_empty()
    assert kline_sync.fetch_intraday_universe_increment()[0].is_empty()
