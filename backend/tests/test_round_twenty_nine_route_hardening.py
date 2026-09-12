"""Twenty-ninth-round leftover mix-source / fail-open paths.

Closes residual fail-open / silent mix that round 28 left after it gated
entitled minute call-failure fallback and instruments-follow-daily:
- remaining leftover TickFlow instrument readers after a custom switch
- pipeline remount of leftover TickFlow via raw DuckDB glob
- ST-symbol TTL cache reused leftover TickFlow after a daily switch
- Lab shadow leftover extras[0] / leftover part
- HTTP ext leftover-part-only (extras-blind)
- fund-flow snapshot leftover part hiding extras

Keeps remaining TickFlow leftover contracts that round 30 later closed or kept:
- leftover TickFlow + free realtime stays mode=none
- leftover TickFlow still sees untagged-only partitions
- after-hours default clock times / .env / auth stay out of scope
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import polars as pl

from app.api import ext_data as ext_api
from app.jobs import daily_pipeline
from app.services import instrument_sync, kline_sync, reference_derived
from app.services.ext_data import (
    ExtConfig,
    ExtField,
    build_code_lookup,
    latest_ext_parquet_files,
    usable_ext_snapshot_files,
)
from app.services.financial_sync import _get_symbols
from app.services.free_sources.daily_quality import run_daily_quality_check
from app.services.free_sources.financials_public import build_shares_from_instruments
from app.services.free_sources.fund_flow import load_board_snapshot_items
from app.services.market_mainline import load_risk_warning_symbols
from app.services.quote_service import QuoteService
from app.tickflow.repository import DataStore, KlineRepository


def _prefs_boom(*_a, **_k):
    raise RuntimeError("prefs unreadable")


def _inst_df(*, route: str | None = None, name: str = "平安银行", symbol: str = "000001.SZ") -> pl.DataFrame:
    data = {
        "symbol": [symbol],
        "name": [name],
        "code": [symbol.split(".", 1)[0]],
        "exchange": [symbol.split(".", 1)[1]],
        "listing_date": [date(1991, 4, 3)],
    }
    if route is not None:
        data["route"] = [route]
    return pl.DataFrame(data)


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


def _patch_custom_daily(monkeypatch, name: str = "fuyao") -> None:
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: name)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda n, dataset, wanted=name: n == wanted and dataset == "daily",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda n: SimpleNamespace())


def _write_instruments(tmp_path, df: pl.DataFrame):
    path = tmp_path / "instruments" / "instruments.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)
    return path


def test_read_usable_instruments_hides_leftover_after_switch(monkeypatch, tmp_path):
    _write_instruments(tmp_path, _inst_df(route="tickflow"))
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert instrument_sync.read_usable_instruments(tmp_path)["symbol"].to_list() == ["000001.SZ"]
    _patch_custom_daily(monkeypatch)
    assert instrument_sync.read_usable_instruments(tmp_path).is_empty()


def test_untagged_instruments_still_serve_leftover_tickflow(monkeypatch, tmp_path):
    _write_instruments(tmp_path, _inst_df())
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert instrument_sync.read_usable_instruments(tmp_path)["symbol"].to_list() == ["000001.SZ"]


def test_reference_derived_hides_leftover_instruments(monkeypatch, tmp_path):
    _write_instruments(tmp_path, _inst_df(route="tickflow", name="*ST示例"))
    _patch_custom_daily(monkeypatch)
    assert reference_derived._read_instruments(tmp_path).is_empty()


def test_financial_symbols_hide_leftover_after_switch(monkeypatch, tmp_path):
    _write_instruments(tmp_path, _inst_df(route="tickflow"))
    monkeypatch.setattr("app.services.preferences.get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.is_public_financial_provider", lambda name=None: False)
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert _get_symbols(tmp_path) == ["000001.SZ"]
    _patch_custom_daily(monkeypatch)
    assert _get_symbols(tmp_path) == []


def test_shares_from_instruments_skip_leftover_after_switch(monkeypatch, tmp_path):
    _write_instruments(
        tmp_path,
        _inst_df(route="tickflow").with_columns(
            pl.lit(1.0).alias("total_shares"),
            pl.lit(1.0).alias("float_shares"),
        ),
    )
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert build_shares_from_instruments(tmp_path).height == 1
    _patch_custom_daily(monkeypatch)
    assert build_shares_from_instruments(tmp_path).is_empty()


def test_daily_quality_does_not_compare_leftover_universe(monkeypatch, tmp_path):
    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df(route="fuyao").write_parquet(part / "part.parquet")
    leftover = _inst_df(route="tickflow")
    for i in range(20):
        leftover = leftover.vstack(_inst_df(route="tickflow", symbol=f"00000{i}.SZ"))
    _write_instruments(tmp_path, leftover)
    _patch_custom_daily(monkeypatch)
    report = run_daily_quality_check(tmp_path, date="2026-07-17")
    assert report["metrics"].get("instruments", 0) == 0
    assert report["metrics"].get("missing_vs_instruments", 0) == 0
    assert not any(issue.get("code") == "low_coverage" for issue in report["issues"])


def test_code_lookup_hides_leftover_after_switch(monkeypatch, tmp_path):
    _write_instruments(tmp_path, _inst_df(route="tickflow"))
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert build_code_lookup(tmp_path) == {"000001": "000001.SZ"}
    _patch_custom_daily(monkeypatch)
    assert build_code_lookup(tmp_path) == {}


def test_ext_api_names_hide_leftover_after_switch(monkeypatch, tmp_path):
    _write_instruments(tmp_path, _inst_df(route="tickflow"))
    frame = pl.DataFrame({"symbol": ["000001.SZ"], "v": [1.0]})
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    named = ext_api._with_instrument_name(frame, tmp_path)
    assert named["name"].to_list() == ["平安银行"]
    _patch_custom_daily(monkeypatch)
    hidden = ext_api._with_instrument_name(frame, tmp_path)
    assert "name" not in hidden.columns or hidden["name"].null_count() == hidden.height


def test_pipeline_does_not_remount_leftover_instruments(monkeypatch, tmp_path):
    _write_instruments(tmp_path, _inst_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.db.execute("SELECT count(*) FROM instruments").fetchone()[0] == 0
    daily_pipeline._refresh_instruments_view(repo)
    assert repo.db.execute("SELECT count(*) FROM instruments").fetchone()[0] == 0
    assert repo.get_instruments().is_empty()


def test_st_cache_drops_leftover_after_switch(monkeypatch, tmp_path):
    _write_instruments(tmp_path, _inst_df(route="tickflow", name="*ST示例"))
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    import app.services.market_mainline as mainline

    mainline.invalidate_st_symbols_cache()
    assert "000001.SZ" in load_risk_warning_symbols(tmp_path)
    _patch_custom_daily(monkeypatch)
    # Same process cache must not keep leftover TickFlow ST names.
    assert load_risk_warning_symbols(tmp_path) == frozenset()


def test_refresh_route_surfaces_clears_st_cache(monkeypatch, tmp_path):
    import app.services.market_mainline as mainline

    mainline._ST_SYMBOLS_CACHE = (0.0, "tickflow", frozenset({"000001.SZ"}))
    kline_sync.refresh_route_surfaces(None)
    assert mainline._ST_SYMBOLS_CACHE is None


def test_lab_shadow_skips_leftover_daily_after_switch(monkeypatch, tmp_path):
    from app.data_lab.sources.shadow_coverage import (
        _iter_daily_partitions,
        build_status_history_shadow,
    )

    leftover = tmp_path / "kline_daily" / "date=2026-07-17"
    leftover.mkdir(parents=True)
    _daily_df(route="tickflow").with_columns(
        pl.lit(0.0).alias("open"),
        pl.lit(0.0).alias("high"),
    ).write_parquet(leftover / "part.parquet")
    current = tmp_path / "kline_daily" / "date=2026-07-18"
    current.mkdir(parents=True)
    _daily_df(route="fuyao", day=date(2026, 7, 18)).with_columns(
        pl.lit(0.0).alias("open"),
        pl.lit(0.0).alias("high"),
    ).write_parquet(current / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    leftover_days = [day for day, _ in _iter_daily_partitions(tmp_path / "kline_daily")]
    assert leftover_days == [date(2026, 7, 17)]
    _patch_custom_daily(monkeypatch)
    custom_days = [day for day, _ in _iter_daily_partitions(tmp_path / "kline_daily")]
    assert custom_days == [date(2026, 7, 18)]
    frame = build_status_history_shadow(
        tmp_path / "kline_daily",
        sample_days=5,
        as_of=date(2026, 7, 18),
    )
    assert frame["symbol"].to_list() == ["000001.SZ"]


def test_lab_shadow_still_sees_untagged_leftover(monkeypatch, tmp_path):
    from app.data_lab.sources.shadow_coverage import _iter_daily_partitions

    part = tmp_path / "kline_daily" / "date=2026-07-17"
    part.mkdir(parents=True)
    _daily_df().write_parquet(part / "extra.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    assert [day for day, _ in _iter_daily_partitions(tmp_path / "kline_daily")] == [date(2026, 7, 17)]


def test_ext_http_sees_extra_behind_leftover_part(tmp_path):
    cfg = ExtConfig(
        id="ext_demo",
        label="demo",
        mode="timeseries",
        fields=[ExtField(name="v", label="v", dtype="float")],
    )
    old = tmp_path / "ext_data" / "ext_demo" / "timeseries" / "date=2026-07-17"
    old.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "v": [1.0]}).write_parquet(old / "part.parquet")
    new = tmp_path / "ext_data" / "ext_demo" / "timeseries" / "date=2026-07-18"
    new.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"], "v": [2.0]}).write_parquet(new / "extra.parquet")
    files = latest_ext_parquet_files(tmp_path, cfg)
    assert [path.name for path in files] == ["extra.parquet"]
    frame, latest = ext_api._read_ext_dataframe(cfg, tmp_path)
    assert latest == "2026-07-18"
    assert frame["v"].to_list() == [2.0]


def test_ext_snapshot_sees_extras_beside_leftover_part(tmp_path):
    root = tmp_path / "ext_data" / "ext_fund_flow_bk"
    root.mkdir(parents=True)
    pl.DataFrame({"code": ["BK0001"], "name": ["leftover"]}).write_parquet(root / "part.parquet")
    pl.DataFrame({"code": ["BK0002"], "name": ["current"]}).write_parquet(root / "extra.parquet")
    files = usable_ext_snapshot_files(tmp_path, "ext_fund_flow_bk")
    assert {path.name for path in files} == {"part.parquet", "extra.parquet"}
    items = load_board_snapshot_items(tmp_path)
    assert {row["code"] for row in items} == {"BK0001", "BK0002"}


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"


def test_unreadable_prefs_instruments_stay_fail_closed(monkeypatch, tmp_path):
    _write_instruments(tmp_path, _inst_df())
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", _prefs_boom)
    monkeypatch.setattr("app.services.preferences.get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.is_public_financial_provider", lambda name=None: False)
    assert instrument_sync.read_usable_instruments(tmp_path).is_empty()
    assert build_code_lookup(tmp_path) == {}
    assert _get_symbols(tmp_path) == []
