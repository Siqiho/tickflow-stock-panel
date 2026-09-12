"""Twenty-second-round leftover mix-source / fail-open paths.

Closes remaining except-fallback leftover globs and leftover-shadowed
reads that round 21 left on the overlay / ETF-minute / DuckDB / persist side:
- official trend overlay cache keys by daily route
- HTTP minute-range / get_minute pass ETF asset_type (not the stock store)
- DuckDB refresh helpers skip ungated leftover globs
- legacy symbol-partition minute migration does not republish leftover
- depth sealed reads skip stale depth5 and keep current-route sealed_l1
- shares append / historical-shares cache fail-closed on route switch
- regime history cache keys by daily route
- derived calendars for index / ETF / minute stay on usable partitions

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

from datetime import date, datetime
from types import SimpleNamespace

import polars as pl
import pytest

from app.api import kline as kline_api
from app.api import regime as regime_api
from app.jobs import daily_pipeline
from app.services import extend_history, kline_sync
from app.services.depth_service import DepthService
from app.services.financial_pit import append_shares_history
from app.services.intraday_overview import load_official_trend_overlay
from app.services.quote_service import QuoteService
from app.services.reference_derived import list_partition_dates
from app.tickflow.repository import DataStore, KlineRepository


def _prefs_boom(*_a, **_k):
    raise RuntimeError("prefs unreadable")


def _daily_df(symbol: str = "000001.SZ", *, route: str | None = None, day: date | None = None, close: float = 10.1) -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "date": [day or date(2026, 7, 17)],
        "open": [close],
        "high": [close],
        "low": [close],
        "close": [close],
        "volume": [100.0],
        "amount": [1010.0],
        "raw_close": [close],
        "raw_high": [close],
        "raw_low": [close],
        "turnover_rate": [1.0],
        "consecutive_limit_ups": [2],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _index_df(symbol: str = "000001.SH", *, route: str | None = None, day: date | None = None) -> pl.DataFrame:
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


def _minute_df(symbol: str = "000001.SZ", *, route: str | None = None, day: date | None = None, close: float = 10.1) -> pl.DataFrame:
    day = day or date(2026, 7, 17)
    data = {
        "symbol": [symbol],
        "datetime": [datetime(day.year, day.month, day.day, 9, 31)],
        "open": [10.0],
        "high": [10.2],
        "low": [9.9],
        "close": [close],
        "volume": [100.0],
        "amount": [1010.0],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _shares_df(*, route: str | None = None) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"],
        "period_end": [date(2026, 3, 31)],
        "announce_date": [date(2026, 4, 1)],
        "float_shares": [1.0e10],
        "total_shares": [1.2e10],
        "source": ["tickflow"],
        "table": ["shares"],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _sealed_df(*, route: str | None = None, symbol: str = "000001.SZ") -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "sealed_up": [True],
        "sealed_down": [False],
        "ask1_vol": [0],
        "bid1_vol": [100],
        "status": ["limit_up"],
        "fetched_at": [1.0],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _patch_custom_daily(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == name and dataset == "daily",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _patch_custom_minute(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == name and dataset == "minute",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _patch_custom_financial(monkeypatch, name: str = "fuyao") -> None:
    from app.services import preferences

    monkeypatch.setattr(preferences, "get_financial_provider", lambda: name)
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)


def _patch_custom_depth(monkeypatch, name: str = "fuyao") -> None:
    from app.services import preferences

    monkeypatch.setattr(preferences, "get_depth5_data_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == name and dataset == "depth5",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _write_part(root, table: str, day: str, df: pl.DataFrame) -> None:
    part = root / table / f"date={day}"
    part.mkdir(parents=True, exist_ok=True)
    df.write_parquet(part / "part.parquet")


def test_overlay_cache_drops_leftover_after_switch(monkeypatch, tmp_path):
    from app.services import intraday_overview

    intraday_overview._overlay_cache = None
    leftover = _daily_df(route="tickflow").with_columns(pl.lit(999.0).alias("close"))
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", leftover)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    first = load_official_trend_overlay(tmp_path, date(2026, 7, 17))
    assert first
    assert first["000001.SZ"]["consecutive_limit_ups"] == 2
    _patch_custom_daily(monkeypatch)
    second = load_official_trend_overlay(tmp_path, date(2026, 7, 17))
    assert second == {}


def test_overlay_never_fail_open(monkeypatch, tmp_path):
    from app.services import intraday_overview

    intraday_overview._overlay_cache = None
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(kline_sync, "daily_partition_usable", _prefs_boom)
    assert load_official_trend_overlay(tmp_path, date(2026, 7, 17)) == {}


def test_minute_range_http_uses_etf_store(monkeypatch, tmp_path):
    _write_part(
        tmp_path,
        "kline_minute",
        "2026-07-17",
        _minute_df("510300.SH", route="tickflow", close=999.0),
    )
    _write_part(
        tmp_path,
        "kline_etf_minute",
        "2026-07-17",
        _minute_df("510300.SH", route="fuyao", close=1.5),
    )
    _write_part(
        tmp_path,
        "kline_etf_daily",
        "2026-07-16",
        _daily_df("510300.SH", route="fuyao", day=date(2026, 7, 16), close=1.23),
    )
    _write_part(
        tmp_path,
        "kline_daily",
        "2026-07-16",
        _daily_df("510300.SH", route="tickflow", day=date(2026, 7, 16), close=999.0),
    )
    _patch_custom_minute(monkeypatch)
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(kline_api, "cn_today", lambda: date(2026, 7, 17))
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        resolve_asset_type=lambda *_a, **_k: "etf",
        get_minute_range=None,
        get_daily_asset=lambda asset, symbol, start, end: (
            _daily_df(symbol, route="fuyao", day=date(2026, 7, 16), close=1.23)
            if asset == "etf"
            else _daily_df(symbol, route="tickflow", day=date(2026, 7, 16), close=999.0)
        ),
        get_instruments=lambda: pl.DataFrame({"symbol": ["510300.SH"], "name": ["沪深300ETF"]}),
        execute_one=lambda *_a, **_k: None,
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo)), headers={})
    payload = kline_api.get_minute_range(request, "510300.SH", 2)
    assert payload["sessions"]
    assert payload["sessions"][0]["rows"][0]["close"] == pytest.approx(1.5)
    assert payload["sessions"][0]["prev_close"] == pytest.approx(1.23)


def test_get_minute_http_passes_etf_asset_type(monkeypatch):
    seen = {}

    def _get_minute(symbol, trade_date, asset_type="stock"):
        seen["asset_type"] = asset_type
        if asset_type == "etf":
            return _minute_df("510300.SH", route="fuyao", close=1.5)
        return _minute_df("510300.SH", route="tickflow", close=999.0)

    _patch_custom_minute(monkeypatch)
    monkeypatch.setattr(kline_api, "cn_today", lambda: date(2026, 7, 17))
    monkeypatch.setattr(kline_api, "cn_now", lambda: datetime(2026, 7, 17, 8, 0))
    monkeypatch.setattr(kline_api, "in_continuous_session", lambda: False)
    repo = SimpleNamespace(
        resolve_asset_type=lambda *_a, **_k: "etf",
        get_minute=_get_minute,
        execute_one=lambda *_a, **_k: None,
        get_instruments=lambda: pl.DataFrame(),
        store=None,
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo)), headers={})
    payload = kline_api.get_minute(request, "510300.SH", date(2026, 7, 17))
    assert seen["asset_type"] == "etf"
    assert payload["source"] == "local"
    assert payload["rows"][0]["close"] == pytest.approx(1.5)


def test_get_minute_http_skips_index(monkeypatch):
    monkeypatch.setattr(kline_api, "cn_today", lambda: date(2026, 7, 17))
    repo = SimpleNamespace(
        resolve_asset_type=lambda *_a, **_k: "index",
        get_minute=lambda *_a, **_k: _minute_df("000001.SH", route="tickflow", close=999.0),
        execute_one=lambda *_a, **_k: None,
        get_instruments=lambda: pl.DataFrame(),
        store=None,
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo)), headers={})
    payload = kline_api.get_minute(request, "000001.SH", date(2026, 7, 17))
    assert payload["source"] == "none"
    assert payload["rows"] == []


def test_latest_minute_date_uses_etf_store(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_minute", "2026-07-17", _minute_df("510300.SH", route="tickflow"))
    _write_part(
        tmp_path,
        "kline_etf_minute",
        "2026-07-16",
        _minute_df("510300.SH", route="fuyao", day=date(2026, 7, 16)),
    )
    _patch_custom_minute(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.latest_minute_date("510300.SH") is None
    assert repo.latest_minute_date("510300.SH", asset_type="etf") == date(2026, 7, 16)


def test_refresh_helpers_skip_ungated_glob(tmp_path):
    sqls: list[str] = []
    store = SimpleNamespace(
        data_dir=tmp_path,
        refresh_gated_views=lambda: sqls.append("regate"),
        re_gate_catalog_views=lambda: sqls.append("old-regate"),
        _register_unified_views=lambda: sqls.append("unified"),
    )
    repo = SimpleNamespace(
        store=store,
        db=SimpleNamespace(execute=lambda sql, *_a, **_k: sqls.append(str(sql))),
        _lock=None,
    )
    kline_sync._refresh_daily_view(repo)
    daily_pipeline._refresh_views(repo)
    daily_pipeline._refresh_single_view(repo, "kline_daily")
    extend_history._refresh_single_view(repo, "adj_factor")
    assert sqls.count("regate") == 4
    assert not any("read_parquet" in item for item in sqls)


def test_refresh_views_keep_leftover_gated(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.db.execute("SELECT count(*) FROM kline_daily").fetchone()[0] == 0
    kline_sync._refresh_daily_view(repo)
    repo.refresh_index_views()
    repo.refresh_minute_views()
    assert repo.db.execute("SELECT count(*) FROM kline_daily").fetchone()[0] == 0


def test_migrate_symbol_partition_skips_leftover_under_custom(monkeypatch, tmp_path):
    old = tmp_path / "kline_minute" / "symbol=000001.SZ"
    old.mkdir(parents=True)
    _minute_df(route="tickflow").write_parquet(old / "part.parquet")
    _patch_custom_minute(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    kline_sync._migrate_symbol_to_date_partition(repo)
    assert not old.exists()
    assert not list((tmp_path / "kline_minute").glob("date=*"))


def test_migrate_symbol_partition_tags_leftover_tickflow(monkeypatch, tmp_path):
    old = tmp_path / "kline_minute" / "symbol=000001.SZ"
    old.mkdir(parents=True)
    _minute_df().write_parquet(old / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    repo = KlineRepository(DataStore(tmp_path))
    kline_sync._migrate_symbol_to_date_partition(repo)
    assert not old.exists()
    written = tmp_path / "kline_minute" / "date=2026-07-17" / "part.parquet"
    assert written.exists()
    saved = pl.read_parquet(written)
    assert saved["route"].to_list() == ["tickflow"]


def test_migrate_symbol_partition_never_fail_open(monkeypatch, tmp_path):
    old = tmp_path / "kline_minute" / "symbol=000001.SZ"
    old.mkdir(parents=True)
    _minute_df(route="tickflow").write_parquet(old / "part.parquet")
    monkeypatch.setattr(kline_sync, "minute_route", _prefs_boom)
    repo = KlineRepository(DataStore(tmp_path))
    kline_sync._migrate_symbol_to_date_partition(repo)
    assert old.exists()
    assert not list((tmp_path / "kline_minute").glob("date=*"))


def test_sealed_read_skips_stale_depth5_and_uses_sealed_l1(monkeypatch, tmp_path):
    leftover = tmp_path / "depth5" / "date=2026-07-17"
    leftover.mkdir(parents=True)
    _sealed_df(route="tickflow").write_parquet(leftover / "part.parquet")
    current = tmp_path / "sealed_l1" / "date=2026-07-17"
    current.mkdir(parents=True)
    _sealed_df(route="fuyao").write_parquet(current / "part.parquet")
    _patch_custom_depth(monkeypatch)
    svc = DepthService()
    svc.set_repo(KlineRepository(DataStore(tmp_path)))
    assert svc._persisted_for_date(date(2026, 7, 17)) is True
    sealed = svc.get_sealed_map(date(2026, 7, 17), is_down=False)
    assert sealed["000001.SZ"]["sealed"] is True
    assert svc._sealed_artifact_for_read(date(2026, 7, 17)) == current / "part.parquet"


def test_append_shares_never_fail_open(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "shares" / "part.parquet"
    path.parent.mkdir(parents=True)
    _shares_df(route="tickflow").write_parquet(path)
    monkeypatch.setattr(
        "app.services.financial_sync.financial_write_route",
        _prefs_boom,
    )
    incoming = pl.DataFrame({
        "symbol": ["600000.SH"],
        "period_end": [date(2026, 6, 30)],
        "announce_date": [date(2026, 7, 1)],
        "float_shares": [2.0e9],
        "total_shares": [3.0e9],
        "source": ["custom"],
        "table": ["shares"],
    })
    merged = append_shares_history(tmp_path, incoming, effective_date=date(2026, 6, 30))
    assert merged.is_empty() or "000001.SZ" not in merged["symbol"].to_list()
    assert merged.is_empty() or "600000.SH" not in merged["symbol"].to_list()


def test_historical_shares_cache_drops_leftover_after_switch(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "shares" / "part.parquet"
    path.parent.mkdir(parents=True)
    _shares_df(route="tickflow").write_parquet(path)
    monkeypatch.setattr(
        "app.services.financial_sync.financial_write_route",
        lambda: "tickflow",
    )
    repo = KlineRepository(DataStore(tmp_path))
    first = repo.get_historical_shares()
    assert not first.is_empty()
    _patch_custom_financial(monkeypatch)
    monkeypatch.setattr(
        "app.services.financial_sync.financial_write_route",
        lambda: "fuyao",
    )
    second = repo.get_historical_shares()
    assert second.is_empty()


def test_regime_history_cache_keys_by_route(monkeypatch, tmp_path):
    leftover = pl.DataFrame({
        "date": [date(2026, 7, 17)],
        "state": ["leftover"],
    })
    custom = pl.DataFrame({
        "date": [date(2026, 7, 16)],
        "state": ["custom"],
    })
    frames = {"tickflow": leftover, "fuyao": custom}
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    monkeypatch.setattr(
        "app.services.regime_builder.load_regime_history",
        lambda *_a, **_k: frames[kline_sync.daily_route()],
    )
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo)))
    regime_api.invalidate_regime_cache()
    first = regime_api.regime_history(request, None, None, 120)
    assert first["rows"][0]["state"] == "leftover"
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    second = regime_api.regime_history(request, None, None, 120)
    assert second["rows"][0]["state"] == "custom"


def test_list_partition_dates_skips_leftover_index_and_minute(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_index_daily", "2026-07-17", _index_df(route="tickflow"))
    _write_part(tmp_path, "kline_minute", "2026-07-17", _minute_df(route="tickflow"))
    _write_part(
        tmp_path,
        "kline_etf_minute",
        "2026-07-17",
        _minute_df("510300.SH", route="tickflow"),
    )
    _patch_custom_daily(monkeypatch)
    _patch_custom_minute(monkeypatch)
    assert list_partition_dates(tmp_path, "kline_index_daily") == []
    assert list_partition_dates(tmp_path, "kline_minute") == []
    assert list_partition_dates(tmp_path, "kline_etf_minute") == []


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"


def test_untagged_leftover_still_serves_minute(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_minute", "2026-07-17", _minute_df())
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "tickflow")
    repo = KlineRepository(DataStore(tmp_path))
    out = repo.get_minute("000001.SZ", date(2026, 7, 17))
    assert not out.is_empty()


def test_daily_prefs_unreadable_stays_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    _write_part(tmp_path, "kline_index_daily", "2026-07-17", _index_df())
    assert list_partition_dates(tmp_path, "kline_index_daily") == []
    from app.services import intraday_overview

    intraday_overview._overlay_cache = None
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df())
    assert load_official_trend_overlay(tmp_path, date(2026, 7, 17)) == {}
