"""Twenty-fifth-round leftover mix-source / fail-open paths.

Closes remaining except-fallback leftover globs and leftover-shadowed
reads that round 24 left on the panel-cache / financial-depth / catalog-token
/ ext-view / derived-warmup side:
- backtest PanelCache keys by daily route
- public financial depth probe uses gated income (no leftover light mode)
- catalog missing token hides leftover after a custom switch
- regime batch / enriched warmup row-filter leftover TickFlow
- DuckDB / screener ext views use latest timeseries partition only
- RPS map cache keys by daily route
- unknown list_partition_dates calendars fail-closed

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

from app.api.ext_data import _latest_date_partition_glob, _parquet_glob
from app.backtest.engine import PanelCache
from app.data_catalog.control_db import CatalogControlDB
from app.data_catalog.service import CatalogService
from app.indicators.pipeline import _load_recent_history
from app.jobs.daily_pipeline import _public_financial_income_median_periods
from app.services import kline_sync, rps_rotation
from app.services.ext_data import ExtConfig, ExtField
from app.services.quote_service import QuoteService
from app.services.reference_derived import list_partition_dates
from app.services.regime_builder import _compute_batch
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
        "amount": [1010.0],
        "change_pct": [0.01],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


def _income_df(*, route: str | None = None, periods: int = 8) -> pl.DataFrame:
    data = {
        "symbol": ["000001.SZ"] * periods,
        "period_end": [date(2024, 3, 31).replace(year=2024 + i // 4) for i in range(periods)],
        "net_profit": [1.0] * periods,
    }
    if route is not None:
        data["route"] = [route] * periods
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


def _catalog_by_id(service: CatalogService) -> dict:
    return {entry.descriptor.dataset_id: entry for entry in service.list_catalog().datasets}


def test_panel_cache_key_isolates_daily_route(monkeypatch):
    args = (["000001.SZ"], date(2026, 7, 17), date(2026, 7, 17), None, "stock")
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    left = PanelCache._make_key(*args)
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    right = PanelCache._make_key(*args)
    assert left != right
    assert left.endswith(":tickflow")
    assert right.endswith(":fuyao")


def test_panel_cache_does_not_reuse_leftover_after_switch(monkeypatch):
    cache = PanelCache()
    leftover = _daily_df(route="tickflow")
    calls: list[str] = []

    def compute(*_a, **_k):
        route = kline_sync.daily_route()
        calls.append(route)
        return leftover if route == "tickflow" else leftover.head(0)

    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    first = cache.get_or_compute(
        ["000001.SZ"], date(2026, 7, 17), date(2026, 7, 17), None, compute, "stock",
    )
    assert first["close"].to_list() == [10.1]
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    second = cache.get_or_compute(
        ["000001.SZ"], date(2026, 7, 17), date(2026, 7, 17), None, compute, "stock",
    )
    assert second.is_empty()
    assert calls == ["tickflow", "fuyao"]


def test_panel_cache_never_fail_open(monkeypatch):
    cache = PanelCache()
    leftover = _daily_df(route="tickflow")

    def compute(*_a, **_k):
        return leftover if kline_sync.daily_route() == "tickflow" else leftover.head(0)

    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    first = cache.get_or_compute(
        ["000001.SZ"], date(2026, 7, 17), date(2026, 7, 17), None, compute, "stock",
    )
    assert not first.is_empty()
    monkeypatch.setattr(kline_sync, "daily_route", _prefs_boom)
    second = cache.get_or_compute(
        ["000001.SZ"], date(2026, 7, 17), date(2026, 7, 17), None, compute, "stock",
    )
    assert second.is_empty()
    tickflow_key = PanelCache._make_key(
        ["000001.SZ"], date(2026, 7, 17), date(2026, 7, 17), None, "stock",
    )
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    leftover_key = PanelCache._make_key(
        ["000001.SZ"], date(2026, 7, 17), date(2026, 7, 17), None, "stock",
    )
    assert tickflow_key.endswith(":unresolved")
    assert leftover_key.endswith(":tickflow")
    assert tickflow_key != leftover_key


def test_financial_depth_skips_leftover_after_switch(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "income" / "part.parquet"
    path.parent.mkdir(parents=True)
    _income_df(route="tickflow").write_parquet(path)
    monkeypatch.setattr("app.services.financial_sync.financial_write_route", lambda: "tickflow")
    assert _public_financial_income_median_periods(tmp_path, ["000001.SZ"]) == 8.0
    monkeypatch.setattr("app.services.financial_sync.financial_write_route", lambda: "public")
    assert _public_financial_income_median_periods(tmp_path, ["000001.SZ"]) == 0.0


def test_financial_depth_keeps_untagged_leftover_public(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "income" / "part.parquet"
    path.parent.mkdir(parents=True)
    _income_df().write_parquet(path)
    monkeypatch.setattr("app.services.financial_sync.financial_write_route", lambda: "public")
    assert _public_financial_income_median_periods(tmp_path, ["000001.SZ"]) == 8.0


def test_financial_depth_never_fail_open(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "income" / "part.parquet"
    path.parent.mkdir(parents=True)
    _income_df(route="tickflow").write_parquet(path)
    monkeypatch.setattr("app.services.financial_sync.financial_write_route", _prefs_boom)
    assert _public_financial_income_median_periods(tmp_path, ["000001.SZ"]) == 0.0


def test_catalog_missing_token_hides_leftover_after_custom_switch(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _write_instruments(tmp_path)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    service = CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())
    service.rescan()
    first = _catalog_by_id(service)
    assert first["stock_daily"].state.latest_time == "2026-07-17"
    service.control_db.set_meta("catalog_route_token", {})
    _patch_custom_daily(monkeypatch)
    second = _catalog_by_id(service)
    assert second["stock_daily"].descriptor.availability.serving_ready is False
    assert second["stock_daily"].state.latest_time is None
    assert second["stock_daily"].coverage == []


def test_catalog_missing_token_keeps_leftover_tickflow(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _write_instruments(tmp_path)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    service = CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())
    service.rescan()
    service.control_db.set_meta("catalog_route_token", {})
    listed = _catalog_by_id(service)
    assert listed["stock_daily"].state.latest_time == "2026-07-17"


def test_catalog_unresolved_token_never_fail_open(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _write_instruments(tmp_path)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    service = CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())
    service.rescan()
    monkeypatch.setattr(CatalogService, "_catalog_route_token", staticmethod(lambda: "unresolved"))
    listed = _catalog_by_id(service)
    assert listed["stock_daily"].state.latest_time is None
    assert listed["stock_daily"].descriptor.availability.serving_ready is False


def test_regime_batch_skips_leftover_after_switch(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    first = _compute_batch(
        repo, tmp_path / "kline_daily_enriched", None, None,
        date(2026, 7, 17), date(2026, 7, 17), 40,
    )
    assert not first.is_empty()
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    second = _compute_batch(
        repo, tmp_path / "kline_daily_enriched", None, None,
        date(2026, 7, 17), date(2026, 7, 17), 40,
    )
    assert second.is_empty()


def test_regime_batch_keeps_untagged_leftover_tickflow(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df())
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    out = _compute_batch(
        repo, tmp_path / "kline_daily_enriched", None, None,
        date(2026, 7, 17), date(2026, 7, 17), 40,
    )
    assert not out.is_empty()


def test_enriched_warmup_skips_leftover_after_switch(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df(route="tickflow"))
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    first = _load_recent_history(tmp_path / "kline_daily_enriched", ["000001.SZ"], 90)
    assert first.height == 1
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    second = _load_recent_history(tmp_path / "kline_daily_enriched", ["000001.SZ"], 90)
    assert second.is_empty()


def test_enriched_warmup_keeps_untagged_leftover_tickflow(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily_enriched", "2026-07-17", _daily_df())
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    out = _load_recent_history(tmp_path / "kline_daily_enriched", ["000001.SZ"], 90)
    assert out.height == 1
    assert "route" not in out.columns


def test_rps_map_cache_isolates_daily_route(tmp_path, monkeypatch):
    rps_rotation._map_cache.clear()
    rps_rotation._map_ts.clear()
    config = SimpleNamespace(id="ext_gn_ths")
    monkeypatch.setattr(rps_rotation.ExtConfigStore, "load_all", lambda self: [config])
    monkeypatch.setattr(
        rps_rotation, "_dimension_field",
        lambda cfg, kind: "所属概念" if kind == "concept" else None,
    )
    loads: list[str] = []

    def _rows(*_a, **_k):
        loads.append(kline_sync.daily_route())
        return [{"symbol": "s1.SH", "所属概念": "人工智能"}]

    monkeypatch.setattr(rps_rotation, "_read_ext_rows", _rows)
    monkeypatch.setattr(
        rps_rotation, "_symbol_keys", lambda row, cfg: [row["symbol"].upper()],
    )
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "tickflow")
    first = rps_rotation._load_concept_map_df(repo, "concept")
    again = rps_rotation._load_concept_map_df(repo, "concept")
    assert first[1] == 1
    assert again[0].equals(first[0])
    monkeypatch.setattr(kline_sync, "daily_route", lambda: "fuyao")
    switched = rps_rotation._load_concept_map_df(repo, "concept")
    assert switched[1] == 1
    assert loads == ["tickflow", "fuyao"]


def test_list_partition_dates_unknown_table_fail_closed(tmp_path):
    _write_part(tmp_path, "mystery_table", "2026-07-17", _daily_df(route="tickflow"))
    assert list_partition_dates(tmp_path, "mystery_table") == []


def test_latest_timeseries_glob_skips_old_partitions(tmp_path):
    ts = tmp_path / "timeseries"
    for day, close in (("2026-07-17", 1.0), ("2026-07-18", 2.0)):
        part = ts / f"date={day}"
        part.mkdir(parents=True)
        pl.DataFrame({"symbol": ["000001.SZ"], "close": [close]}).write_parquet(part / "part.parquet")
    glob = _latest_date_partition_glob(ts)
    assert glob is not None
    assert "2026-07-18" in glob
    assert "2026-07-17" not in glob


def test_parquet_glob_timeseries_is_latest_only(tmp_path):
    cfg_dir = tmp_path / "ext_data" / "ext_demo" / "timeseries"
    for day in ("2026-07-17", "2026-07-18"):
        part = cfg_dir / f"date={day}"
        part.mkdir(parents=True)
        pl.DataFrame({"symbol": ["000001.SZ"], "v": [1]}).write_parquet(part / "part.parquet")
    config = ExtConfig(
        id="ext_demo",
        label="demo",
        mode="timeseries",
        fields=[ExtField(name="v", label="v", dtype="float")],
    )
    glob = _parquet_glob(config, tmp_path)
    assert "2026-07-18" in glob
    assert "**" not in glob


def test_kline_ext_view_uses_latest_partition(tmp_path):
    for day, value in (("2026-07-17", 1.0), ("2026-07-18", 2.0)):
        part = tmp_path / "kline_ext" / f"date={day}"
        part.mkdir(parents=True)
        pl.DataFrame({
            "symbol": ["000001.SZ"],
            "date": [date.fromisoformat(day)],
            "factor": [value],
        }).write_parquet(part / "part.parquet")
    store = DataStore(tmp_path)
    rows = store.db.query("SELECT factor FROM kline_ext").fetchall()
    assert [row[0] for row in rows] == [2.0]


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"
