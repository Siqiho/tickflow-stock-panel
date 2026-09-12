"""Twenty-eighth-round leftover mix-source / fail-open paths.

Closes residual fail-open / silent mix that round 27 left documented:
- declared custom minute *call* failure no longer TickFlow-mixes
- leftover TickFlow + free realtime stays mode=none (no silent public)
- instruments follow the daily route; TickFlow sync skipped after custom
- quote_snapshot overlay requires matching daily + realtime routes
- Lab leftover TickFlow refuses public sina unless adj/depth is explicit public
- after-hours TickFlow instrument / index jobs skip after custom daily
- leftover TickFlow prefers tagged extras; unreadable extras stay fail-closed

Keeps remaining TickFlow leftover contracts that round 30 later closed:
- leftover TickFlow still sees untagged-only partitions
- after-hours default clock times / .env / auth stay out of scope
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import free_ext
from app.api import kline as kline_api
from app.jobs import daily_pipeline
from app.services import instrument_sync, kline_sync, universe_scope
from app.services.index_sync import sync_etf_instruments, sync_index_instruments
from app.services.market_mainline import load_risk_warning_symbols
from app.services.quote_service import QuoteService, usable_quote_snapshot_files
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


def _setup_failing_custom_minute(monkeypatch) -> MagicMock:
    mock_provider = MagicMock()
    mock_provider.get_minute.side_effect = RuntimeError("custom source unavailable")
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "fuyao")
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == "fuyao" and dataset == "minute",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: mock_provider)
    return mock_provider


def test_custom_minute_call_failure_stays_fail_closed(monkeypatch):
    _setup_failing_custom_minute(monkeypatch)
    tickflow = MagicMock()
    get_client = MagicMock(return_value=tickflow)
    monkeypatch.setattr(kline_sync, "get_client", get_client)
    capset = CapabilitySet({Cap.KLINE_MINUTE_BATCH: CapabilityLimits()})

    df, fallback = kline_sync._try_custom_minute(["000001.SZ"], None, None)
    assert fallback is False
    assert df is None

    out = kline_sync.sync_minute_batch(
        ["000001.SZ"],
        start_time=datetime(2026, 7, 17, 9, 25),
        end_time=datetime(2026, 7, 17, 15, 5),
        capset=capset,
    )
    assert out.is_empty()
    get_client.assert_not_called()


def test_fetch_minute_single_custom_call_failure_skips_tickflow(monkeypatch):
    _setup_failing_custom_minute(monkeypatch)
    get_client = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr(kline_sync, "get_client", get_client)
    monkeypatch.setattr(kline_sync, "_public_minute_fallback", lambda *_a, **_k: pl.DataFrame({"x": [1]}))
    out = kline_sync.fetch_minute_single(
        "000001.SZ",
        date(2026, 7, 17),
        capset=CapabilitySet({Cap.KLINE_MINUTE_BY_SYMBOL: CapabilityLimits()}),
    )
    assert out.is_empty()
    get_client.assert_not_called()


def test_leftover_tickflow_minute_still_uses_entitled_tickflow(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    tickflow = MagicMock()
    tickflow.klines.batch.return_value = {}
    get_client = MagicMock(return_value=tickflow)
    monkeypatch.setattr(kline_sync, "get_client", get_client)
    out = kline_sync.sync_minute_batch(
        ["000001.SZ"],
        start_time=datetime(2026, 7, 17, 9, 25),
        end_time=datetime(2026, 7, 17, 15, 5),
        capset=CapabilitySet({Cap.KLINE_MINUTE_BATCH: CapabilityLimits()}),
    )
    assert out.is_empty()
    get_client.assert_called_once()


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"


def test_instruments_sync_skips_after_custom_daily(monkeypatch, tmp_path):
    path = tmp_path / "instruments" / "instruments.parquet"
    path.parent.mkdir(parents=True)
    leftover = _inst_df(route="tickflow")
    leftover.write_parquet(path)
    _patch_custom_daily(monkeypatch)
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr(instrument_sync, "get_client", tf)
    result = instrument_sync.sync_instruments_result(tmp_path)
    assert result.outcome == "kept_prior"
    assert result.error_code == "instrument_route_refused"
    tf.assert_not_called()
    assert pl.read_parquet(path)["route"].to_list() == ["tickflow"]


def test_instruments_hidden_after_custom_daily(monkeypatch, tmp_path):
    path = tmp_path / "instruments" / "instruments.parquet"
    path.parent.mkdir(parents=True)
    _inst_df(route="tickflow").write_parquet(path)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert universe_scope._load_instruments(tmp_path) == ["000001.SZ"]
    _patch_custom_daily(monkeypatch)
    assert universe_scope._load_instruments(tmp_path) == []
    assert universe_scope.resolve_symbols("ALL", data_dir=tmp_path) == []


def test_untagged_instruments_still_serve_leftover_tickflow(monkeypatch, tmp_path):
    path = tmp_path / "instruments" / "instruments.parquet"
    path.parent.mkdir(parents=True)
    _inst_df().write_parquet(path)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert universe_scope._load_instruments(tmp_path) == ["000001.SZ"]
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.get_instruments()["symbol"].to_list() == ["000001.SZ"]


def test_index_etf_instrument_sync_skips_after_custom_daily(monkeypatch, tmp_path):
    _patch_custom_daily(monkeypatch)
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        save_index_instruments=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("write")),
        save_etf_instruments=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("write")),
        refresh_index_views=lambda: None,
    )
    tf = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr("app.services.index_sync.get_client", tf)
    assert sync_index_instruments(repo) == 0
    assert sync_etf_instruments(repo) == 0
    tf.assert_not_called()


def test_pipeline_skips_tickflow_instruments_after_custom_daily(monkeypatch, tmp_path):
    _patch_custom_daily(monkeypatch)
    called = []
    monkeypatch.setattr(instrument_sync, "get_client", lambda: called.append("tf") or (_ for _ in ()).throw(AssertionError()))
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    result = daily_pipeline.run_instruments_sync(repo)
    assert result["error_code"] == "instrument_route_refused"
    assert called == []


def test_mainline_st_skips_leftover_instruments_after_switch(monkeypatch, tmp_path):
    path = tmp_path / "instruments" / "instruments.parquet"
    path.parent.mkdir(parents=True)
    _inst_df(route="tickflow", name="*ST示例").write_parquet(path)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    import app.services.market_mainline as mainline

    mainline._ST_SYMBOLS_CACHE = None
    assert "000001.SZ" in load_risk_warning_symbols(tmp_path)
    _patch_custom_daily(monkeypatch)
    mainline._ST_SYMBOLS_CACHE = None
    assert load_risk_warning_symbols(tmp_path) == frozenset()


def test_quote_overlay_skips_leftover_on_custom_daily(monkeypatch, tmp_path):
    part = tmp_path / "quote_snapshot" / "asset_type=stock" / "date=2026-07-18"
    part.mkdir(parents=True)
    _quote_df(route="tickflow").write_parquet(part / "part.parquet")
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    rows = [{
        "symbol": "000001.SZ",
        "date": "2026-07-17",
        "open": 10.0,
        "high": 10.0,
        "low": 10.0,
        "close": 10.0,
    }]
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "tickflow")
    overlaid, meta = kline_api._overlay_persisted_quote_candles(
        repo, "000001.SZ", rows, date(2026, 7, 17), date(2026, 7, 18),
    )
    assert meta["applied"] is False
    assert len(overlaid) == 1


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


def test_quote_overlay_keeps_matching_leftover_tickflow(monkeypatch, tmp_path):
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
    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "tickflow")
    overlaid, meta = kline_api._overlay_persisted_quote_candles(
        repo, "000001.SZ", rows, date(2026, 7, 17), date(2026, 7, 18),
    )
    assert meta["applied"] is True
    assert overlaid[-1]["is_quote_snapshot"] is True


def test_lab_leftover_tickflow_refuses_public(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: False)
    app = FastAPI()
    app.include_router(free_ext.router)
    client = TestClient(app)
    resp = client.get("/api/free/adj-factor/000001.SZ")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "lab_public_refused"


def test_lab_explicit_public_adj_still_allowed(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "public")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: True)
    monkeypatch.setattr(
        "app.api.free_ext.fetch_adj_factors_symbol",
        lambda symbol: pl.DataFrame({
            "symbol": ["000001.SZ"],
            "date": [date(2026, 7, 17)],
            "adj_factor": [1.0],
        }),
    )
    app = FastAPI()
    app.include_router(free_ext.router)
    client = TestClient(app)
    resp = client.get("/api/free/adj-factor/000001.SZ")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_leftover_tickflow_prefers_tagged_extras(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    leftover_untagged = _daily_df().with_columns(pl.lit(1.0).alias("close"))
    leftover_untagged.write_parquet(part / "extra.parquet")
    _daily_df(route="tickflow").write_parquet(part / "part.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    paths = kline_sync.usable_daily_partition_paths(tmp_path)
    assert [path.name for path in paths] == ["part.parquet"]
    frame = kline_sync.read_usable_daily_partition(part)
    assert frame["close"].to_list() == [10.1]


def test_leftover_tickflow_still_sees_untagged_only(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    assert kline_sync.usable_daily_partition_dates(tmp_path) == [date(2026, 7, 17)]
    assert kline_sync.read_usable_daily_partition(part)["close"].to_list() == [10.1]


def test_unreadable_extras_are_fail_closed_for_leftover_tickflow(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    (part / "part.parquet").write_bytes(b"")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert kline_sync.usable_daily_partition_dates(tmp_path) == []
    _patch_custom_daily(monkeypatch)
    assert kline_sync.usable_daily_partition_dates(tmp_path) == []


def test_minute_prefers_tagged_leftover_extras(monkeypatch, tmp_path):
    part = tmp_path / "kline_minute" / "date=2026-07-17"
    part.mkdir(parents=True)
    _minute_df().write_parquet(part / "extra.parquet")
    current_ts = datetime(2026, 7, 17, 14, 55)
    _minute_df(route="tickflow", ts=current_ts).write_parquet(part / "current.parquet")
    monkeypatch.setattr(kline_sync, "minute_route", lambda: "tickflow")
    assert [path.name for path in kline_sync.usable_minute_partition_files(part)] == [
        "current.parquet",
    ]
    assert kline_sync.latest_usable_minute_datetime(tmp_path) == current_ts


def test_quote_snapshot_prefers_tagged_leftover_extras(monkeypatch, tmp_path):
    part = tmp_path / "quote_snapshot" / "asset_type=stock" / "date=2026-07-17"
    part.mkdir(parents=True)
    _quote_df(day=date(2026, 7, 17)).with_columns(pl.lit(1.0).alias("close")).write_parquet(
        part / "extra.parquet",
    )
    _quote_df(day=date(2026, 7, 17), route="tickflow").write_parquet(part / "current.parquet")
    monkeypatch.setattr("app.services.quote_service.realtime_route", lambda: "tickflow")
    assert [path.name for path in usable_quote_snapshot_files(part)] == ["current.parquet"]


def test_instrument_views_hide_leftover_after_custom_switch(monkeypatch, tmp_path):
    path = tmp_path / "instruments" / "instruments.parquet"
    path.parent.mkdir(parents=True)
    _inst_df(route="tickflow").write_parquet(path)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    leftover = KlineRepository(DataStore(tmp_path))
    assert leftover.db.execute("SELECT count(*) FROM instruments").fetchone()[0] == 1
    _patch_custom_daily(monkeypatch)
    custom = KlineRepository(DataStore(tmp_path))
    assert custom.db.execute("SELECT count(*) FROM instruments").fetchone()[0] == 0
    assert custom.get_instruments().is_empty()


def test_instruments_prefs_unreadable_stays_fail_closed(monkeypatch, tmp_path):
    path = tmp_path / "instruments" / "instruments.parquet"
    path.parent.mkdir(parents=True)
    _inst_df().write_parquet(path)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    assert instrument_sync.instrument_route() == "unresolved"
    assert instrument_sync.instruments_sync_allowed() is False
    assert universe_scope._load_instruments(tmp_path) == []
