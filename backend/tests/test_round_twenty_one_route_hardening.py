"""Twenty-first-round leftover mix-source / fail-open paths.

Closes remaining except-fallback leftover globs and leftover-shadowed
reads that round 20 left on the minute / live-rebuild / index / persist side:
- minute scans use usable partitions so leftover schema cannot empty the route
- HTTP minute-range fallback no longer leftover-globs
- live enriched full-rebuild hist stays on current daily route
- index benchmark / overview / SSE quote fallbacks use file provenance
- process caches key by daily route so a switch cannot reuse leftover
- minute null-datetime cleanup does not wipe leftover TickFlow
- live publish / daily write refuse custom or unreadable prefs
- adj status does not count leftover DuckDB rows
- HTTP minute-range filters leftover getter frames and skips index stock scans
- live index-quote cache drops leftover TickFlow after a realtime switch

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

from app.api import data as data_api
from app.api import intraday as intraday_api
from app.api import kline as kline_api
from app.indicators.pipeline import load_benchmark_momentum
from app.services import kline_sync
from app.services.abnormal_moves import _hist_cache, _hist_snapshot
from app.services.market_overview_builder import _index_quotes
from app.services.quote_service import QuoteService
from app.tickflow.repository import DataStore, KlineReadError, KlineRepository


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
        "raw_close": [10.1],
        "raw_high": [10.2],
        "raw_low": [9.9],
        "turnover_rate": [1.0],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _index_df(symbol: str = "000001.SH", *, route: str | None = None, day: date | None = None, close: float = 10.1) -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "date": [day or date(2026, 7, 17)],
        "open": [close],
        "high": [close],
        "low": [close],
        "close": [close],
        "volume": [100.0],
        "amount": [1010.0],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _minute_df(symbol: str = "000001.SZ", *, route: str | None = None, day: date | None = None) -> pl.DataFrame:
    day = day or date(2026, 7, 17)
    data = {
        "symbol": [symbol],
        "datetime": [datetime(day.year, day.month, day.day, 9, 31)],
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


def _patch_custom_adj(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset: n == name and dataset in {"daily", "adj_factor"},
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _write_part(root, table: str, day: str, df: pl.DataFrame) -> None:
    part = root / table / f"date={day}"
    part.mkdir(parents=True, exist_ok=True)
    df.write_parquet(part / "part.parquet")


def test_get_minute_skips_leftover_schema_poison(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_minute", "2026-07-16", _minute_df(route="fuyao", day=date(2026, 7, 16)))
    leftover = pl.DataFrame({
        "symbol": ["000001.SZ"],
        "datetime": [20260717],
        "open": [999],
        "close": [999],
        "volume": [1],
        "amount": [1],
        "route": ["tickflow"],
    })
    _write_part(tmp_path, "kline_minute", "2026-07-17", leftover)
    _patch_custom_minute(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    out = repo.get_minute("000001.SZ", date(2026, 7, 16))
    assert not out.is_empty()
    assert float(out["close"][0]) == pytest.approx(10.1)
    assert repo.get_minute("000001.SZ", date(2026, 7, 17)).is_empty()
    ranged = repo.get_minute_range(["000001.SZ"], date(2026, 7, 16), date(2026, 7, 17))
    assert not ranged.is_empty()
    days = [d.date() if hasattr(d, "date") else d for d in ranged["datetime"].to_list()]
    assert date(2026, 7, 17) not in days


def test_get_minute_batch_skips_leftover_under_custom(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_minute", "2026-07-17", _minute_df(route="tickflow"))
    _patch_custom_minute(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.get_minute_batch(["000001.SZ"], date(2026, 7, 17)).is_empty()


def test_scan_usable_minute_never_fail_open(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_minute", "2026-07-17", _minute_df(route="tickflow"))
    _patch_custom_minute(monkeypatch)
    monkeypatch.setattr(kline_sync, "usable_minute_partition_dates", _prefs_boom)
    assert kline_sync.scan_usable_minute(tmp_path) is None
    assert kline_sync.usable_minute_partition_paths(tmp_path) == []


def test_minute_range_http_skips_leftover_schema_poison(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_minute", "2026-07-16", _minute_df(route="fuyao", day=date(2026, 7, 16)))
    _write_part(tmp_path, "kline_minute", "2026-07-17", _minute_df(route="tickflow"))
    _patch_custom_minute(monkeypatch)
    monkeypatch.setattr(kline_api, "cn_today", lambda: date(2026, 7, 17))
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        resolve_asset_type=lambda *_a, **_k: "stock",
        get_instruments=lambda: pl.DataFrame({"symbol": ["000001.SZ"], "name": ["平安"]}),
        get_minute_range=None,
        execute_one=lambda *_a, **_k: None,
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo)))
    payload = kline_api.get_minute_range(request, "000001.SZ", 2)
    dates = [session["date"] for session in payload.get("sessions") or []]
    assert "2026-07-17" not in dates
    if payload.get("sessions"):
        assert payload["sessions"][0]["date"] == "2026-07-16"


def test_live_rebuild_skips_other_route_hist(monkeypatch, tmp_path):
    custom = _daily_df(route="fuyao", day=date(2026, 7, 16)).with_columns(pl.lit(999.0).alias("close"))
    _write_part(tmp_path, "kline_daily", "2026-07-16", custom)
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    repo = KlineRepository(DataStore(tmp_path))
    captured = {}

    def _fake_compute(full_df, **_k):
        captured["dates"] = [
            d if isinstance(d, date) else d for d in full_df["date"].to_list()
        ]
        captured["closes"] = [float(v) for v in full_df["close"].to_list()]
        return full_df

    monkeypatch.setattr("app.indicators.pipeline.compute_enriched", _fake_compute)
    monkeypatch.setattr(repo, "get_live_agg", lambda: pl.DataFrame())
    monkeypatch.setattr(repo, "get_enriched_latest", lambda: (pl.DataFrame(), None))
    service = QuoteService()
    service.set_repo(repo)
    today_df = _daily_df(route="tickflow", day=date.today())
    service._flush_live_enriched(today_df, persist=False)
    assert date(2026, 7, 16) not in captured.get("dates", [])
    if captured.get("closes"):
        assert 999.0 not in captured["closes"]


def test_benchmark_skips_leftover_index_under_custom(monkeypatch, tmp_path):
    from app.indicators import pipeline as pipeline_mod

    pipeline_mod._benchmark_cache.clear()
    _write_part(
        tmp_path,
        "kline_index_daily",
        "2026-07-16",
        _index_df(route="fuyao", day=date(2026, 7, 16), close=10.0),
    )
    _write_part(
        tmp_path,
        "kline_index_daily",
        "2026-07-17",
        _index_df(route="tickflow", close=999.0),
    )
    _patch_custom_daily(monkeypatch)
    frame = load_benchmark_momentum(tmp_path)
    assert frame is not None and not frame.is_empty()
    dates = [d if isinstance(d, date) else d for d in frame["date"].to_list()]
    assert date(2026, 7, 17) not in dates


def test_benchmark_cache_does_not_reuse_leftover_after_switch(monkeypatch, tmp_path):
    from app.indicators import pipeline as pipeline_mod

    pipeline_mod._benchmark_cache.clear()
    _write_part(tmp_path, "kline_index_daily", "2026-07-17", _index_df(route="tickflow", close=999.0))
    leftover = load_benchmark_momentum(tmp_path)
    assert leftover is not None and not leftover.is_empty()
    _write_part(
        tmp_path,
        "kline_index_daily",
        "2026-07-16",
        _index_df(route="fuyao", day=date(2026, 7, 16), close=10.0),
    )
    _patch_custom_daily(monkeypatch)
    custom = load_benchmark_momentum(tmp_path)
    if custom is not None and not custom.is_empty():
        dates = [d if isinstance(d, date) else d for d in custom["date"].to_list()]
        assert date(2026, 7, 17) not in dates
    else:
        assert custom is None or custom.is_empty()


def test_index_quotes_skip_leftover_sql(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_index_daily", "2026-07-16", _index_df(route="fuyao", day=date(2026, 7, 16), close=10.0))
    _write_part(tmp_path, "kline_index_daily", "2026-07-17", _index_df(route="tickflow", close=999.0))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    monkeypatch.setattr(
        repo,
        "execute_all",
        lambda *_a, **_k: [("000001.SH", date(2026, 7, 17), 999.0, 1.0)],
    )
    rows = _index_quotes(repo, None)
    by_symbol = {r["symbol"]: r for r in rows}
    assert by_symbol["000001.SH"]["last_price"] == pytest.approx(10.0)


def test_intraday_index_fallback_skips_leftover(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_index_daily", "2026-07-16", _index_df(route="fuyao", day=date(2026, 7, 16), close=10.0))
    _write_part(tmp_path, "kline_index_daily", "2026-07-17", _index_df(route="tickflow", close=999.0))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    monkeypatch.setattr(
        repo,
        "execute_all",
        lambda *_a, **_k: [("000001.SH", date(2026, 7, 17), 999.0, 1.0)],
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo)))
    rows = intraday_api._fallback_index_quotes_from_daily(request, ["000001.SH"])
    assert rows
    assert rows[0]["last_price"] == pytest.approx(10.0)


def test_cleanup_null_datetime_does_not_wipe_leftover(monkeypatch, tmp_path):
    leftover = tmp_path / "kline_minute" / "date=2026-07-17"
    leftover.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "datetime": [None],
        "open": [10.0],
        "close": [10.0],
        "route": ["tickflow"],
    }).write_parquet(leftover / "part.parquet")
    custom = _minute_df(route="fuyao", day=date(2026, 7, 16))
    _write_part(tmp_path, "kline_minute", "2026-07-16", custom)
    _patch_custom_minute(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    kline_sync._cleanup_null_datetime_minute(repo)
    assert (leftover / "part.parquet").exists()
    assert (tmp_path / "kline_minute" / "date=2026-07-16" / "part.parquet").exists()


def test_publish_live_refuses_custom(monkeypatch, tmp_path):
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    repo.publish_live_enriched_asset("stock", _daily_df(route="tickflow", day=date.today()))
    cached, latest = repo.get_enriched_latest()
    assert cached.is_empty()
    assert latest is None


def test_daily_write_context_never_fail_open(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync, "_tag_daily_route", _prefs_boom)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo._daily_write_context(_daily_df()) is None
    repo.flush_live_daily(_daily_df(day=date.today()))
    assert not list((tmp_path / "kline_daily").glob("date=*"))


def test_latest_enriched_duckdb_uses_provenance(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-16", _daily_df(route="fuyao", day=date(2026, 7, 16)))
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo._latest_enriched_date_duckdb() == date(2026, 7, 16)


def test_adj_status_does_not_count_leftover_sql(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-16", _daily_df(route="fuyao", day=date(2026, 7, 16)))
    (tmp_path / "adj_factor").mkdir(parents=True, exist_ok=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "trade_date": [date(2026, 3, 31)],
        "ex_factor": [1.1],
        "route": ["tickflow"],
    }).write_parquet(tmp_path / "adj_factor" / "all.parquet")
    _patch_custom_daily(monkeypatch)
    _patch_custom_adj(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    monkeypatch.setattr(
        repo,
        "execute_one",
        lambda *_a, **_k: (99, 99, 99),
    )
    assert data_api._safe_aggregate_adj_factor(repo) is None
    assert data_api._safe_aggregate(repo, "unknown_view") is None


def test_hist_snapshot_cache_keys_by_route(monkeypatch, tmp_path):
    _hist_cache.clear()
    leftover = _daily_df(route="tickflow").with_columns(pl.lit(0.99).alias("change_pct"))
    custom = _daily_df(route="fuyao", day=date(2026, 7, 16)).with_columns(pl.lit(0.02).alias("change_pct"))
    repo = SimpleNamespace(get_enriched_latest=lambda: (leftover, date(2026, 7, 17)))
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    first = _hist_snapshot(repo)
    assert first["rows"]["000001.SZ"]["rt_pct"] == pytest.approx(0.99)
    repo.get_enriched_latest = lambda: (custom, date(2026, 7, 16))
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    second = _hist_snapshot(repo)
    assert second["rows"]["000001.SZ"]["rt_pct"] == pytest.approx(0.02)


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
    ranged = repo.get_minute_range(["000001.SZ"], date(2026, 7, 17), date(2026, 7, 17))
    assert not ranged.is_empty()


def test_get_minute_still_raises_on_corrupt_leftover_tickflow(tmp_path):
    repo = KlineRepository(DataStore(tmp_path))
    dest = tmp_path / "kline_minute" / "date=2026-06-29" / "part.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"not a parquet")
    with pytest.raises(KlineReadError):
        repo.get_minute("000001.SZ", date(2026, 6, 29))


def test_minute_range_http_filters_getter_leftover(monkeypatch):
    _patch_custom_minute(monkeypatch)
    leftover = _minute_df(route="tickflow")
    repo = SimpleNamespace(
        resolve_asset_type=lambda *_a, **_k: "stock",
        get_minute_range=lambda *_a, **_k: leftover,
        get_instruments=lambda: pl.DataFrame(),
        execute_one=lambda *_a, **_k: None,
        store=None,
        get_daily_asset=None,
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo)))
    payload = kline_api.get_minute_range(request, "000001.SZ", 2)
    assert payload["sessions"] == []
    assert payload["source"] == "none"


def test_index_quotes_cache_drops_leftover_after_realtime_switch(monkeypatch):
    service = QuoteService()
    service._index_quotes_cache = pl.DataFrame({
        "symbol": ["000001.SH"],
        "last_price": [999.0],
    })
    service._index_quotes_cache_token = "tickflow"
    monkeypatch.setattr(QuoteService, "_realtime_cache_token", staticmethod(lambda: "tickflow"))
    assert not service.get_index_quotes(["000001.SH"]).is_empty()
    monkeypatch.setattr(QuoteService, "_realtime_cache_token", staticmethod(lambda: "fuyao"))
    assert service.get_index_quotes(["000001.SH"]).is_empty()


def test_daily_prefs_unreadable_stays_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    _write_part(tmp_path, "kline_index_daily", "2026-07-17", _index_df())
    assert kline_sync.scan_usable_daily(tmp_path, table="kline_index_daily") is None
    assert kline_sync.load_usable_index_latest_quotes(tmp_path, ["000001.SH"]) == []
    from app.indicators import pipeline as pipeline_mod
    pipeline_mod._benchmark_cache.clear()
    assert load_benchmark_momentum(tmp_path) is None
    repo = KlineRepository(DataStore(tmp_path))
    repo.publish_live_enriched_asset("stock", _daily_df(day=date.today()))
    cached, _ = repo.get_enriched_latest()
    assert cached.is_empty()
