"""Twenty-third-round leftover mix-source / fail-open paths.

Closes remaining except-fallback leftover globs and leftover-shadowed
reads that round 22 left on the DuckDB-init / derived-history / pool /
financial-migration / catalog-status side:
- DataStore init skips ungated leftover kline/adj/financial/depth globs
- regime / mainline history tag + filter by daily route
- pool membership seeds skip leftover TickFlow after a pool switch
- financial PIT migration refuses leftover rewrite after a financial switch
- catalog compatibility calendars overlay usable partitions

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

from app.data_catalog.control_db import CatalogControlDB
from app.data_catalog.service import CatalogService
from app.services import kline_sync
from app.services.financial_pit import (
    migrate_existing_financials_to_pit,
    migrate_financial_table_to_v2,
)
from app.services.market_mainline import (
    load_mainline_history,
    upsert_mainline_history,
)
from app.services.quote_service import QuoteService
from app.services.reference_derived import build_index_membership_from_pools
from app.services.regime_builder import (
    load_regime_history,
    upsert_regime_history,
)
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


def test_register_views_skips_ungated_kline_glob(tmp_path):
    sqls: list[str] = []
    store = DataStore.__new__(DataStore)
    store.data_dir = tmp_path
    store.db = SimpleNamespace(execute=lambda sql, *_a, **_k: sqls.append(str(sql)))
    store._register_gated_catalog_views = lambda: sqls.append("gated")
    store._register_unified_views = lambda: sqls.append("unified")
    store._register_views()
    assert "gated" in sqls
    assert "unified" in sqls
    assert not any("instruments/**/*.parquet" in item and "WHERE" not in item for item in sqls)
    assert not any(
        "kline_daily/**/*.parquet" in item and "WHERE" not in item
        for item in sqls
    )
    assert not any("financials/metrics/*.parquet" in item and "WHERE" not in item for item in sqls)
    assert not any("depth5/**/*.parquet" in item and "WHERE" not in item for item in sqls)


def test_datastore_init_keeps_leftover_gated(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    _write_part(tmp_path, "kline_minute", "2026-07-17", _minute_df(route="tickflow"))
    _patch_custom_daily(monkeypatch)
    monkeypatch.setattr(kline_sync.preferences, "get_minute_data_provider", lambda: "fuyao")
    _patch_custom_datasets(monkeypatch, "fuyao", {"daily", "minute"})
    repo = KlineRepository(DataStore(tmp_path))
    assert repo.db.execute("SELECT count(*) FROM kline_daily").fetchone()[0] == 0
    assert repo.db.execute("SELECT count(*) FROM kline_minute").fetchone()[0] == 0


def test_regime_history_drops_leftover_after_switch(monkeypatch, tmp_path):
    leftover = pl.DataFrame({
        "date": [date(2026, 7, 17)],
        "state": ["leftover"],
        "score": [99.0],
        "route": ["tickflow"],
    })
    (tmp_path / "regime_history").mkdir(parents=True)
    leftover.write_parquet(tmp_path / "regime_history" / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    first = load_regime_history(tmp_path)
    assert first["state"].to_list() == ["leftover"]
    _patch_custom_daily(monkeypatch)
    second = load_regime_history(tmp_path)
    assert second.is_empty()


def test_regime_upsert_does_not_merge_leftover(monkeypatch, tmp_path):
    (tmp_path / "regime_history").mkdir(parents=True)
    pl.DataFrame({
        "date": [date(2026, 7, 17)],
        "state": ["leftover"],
        "score": [99.0],
        "route": ["tickflow"],
    }).write_parquet(tmp_path / "regime_history" / "part.parquet")
    _patch_custom_daily(monkeypatch)
    upsert_regime_history(tmp_path, pl.DataFrame({
        "date": [date(2026, 7, 16)],
        "state": ["custom"],
        "score": [10.0],
    }))
    loaded = load_regime_history(tmp_path)
    assert loaded["state"].to_list() == ["custom"]
    assert loaded["date"].to_list() == [date(2026, 7, 16)]
    saved = pl.read_parquet(tmp_path / "regime_history" / "part.parquet")
    assert saved["route"].to_list() == ["fuyao"]


def test_regime_upsert_never_fail_open(monkeypatch, tmp_path):
    (tmp_path / "regime_history").mkdir(parents=True)
    leftover = pl.DataFrame({
        "date": [date(2026, 7, 17)],
        "state": ["leftover"],
        "score": [99.0],
        "route": ["tickflow"],
    })
    leftover.write_parquet(tmp_path / "regime_history" / "part.parquet")
    monkeypatch.setattr(kline_sync, "daily_route", _prefs_boom)
    upsert_regime_history(tmp_path, pl.DataFrame({
        "date": [date(2026, 7, 16)],
        "state": ["custom"],
        "score": [10.0],
    }))
    saved = pl.read_parquet(tmp_path / "regime_history" / "part.parquet")
    assert saved["state"].to_list() == ["leftover"]


def test_mainline_history_drops_leftover_after_switch(monkeypatch, tmp_path):
    leftover = pl.DataFrame({
        "date": [date(2026, 7, 17)],
        "kind": ["concept"],
        "member": ["leftover"],
        "limit_up_count": [9],
        "rank": [1],
        "route": ["tickflow"],
    })
    (tmp_path / "mainline_history").mkdir(parents=True)
    leftover.write_parquet(tmp_path / "mainline_history" / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    first = load_mainline_history(tmp_path)
    assert first["member"].to_list() == ["leftover"]
    _patch_custom_daily(monkeypatch)
    second = load_mainline_history(tmp_path)
    assert second.is_empty()


def test_mainline_upsert_does_not_merge_leftover(monkeypatch, tmp_path):
    leftover = pl.DataFrame({
        "date": [date(2026, 7, 17)],
        "kind": ["concept"],
        "member": ["leftover"],
        "limit_up_count": [9],
        "rank": [1],
        "route": ["tickflow"],
    })
    (tmp_path / "mainline_history").mkdir(parents=True)
    leftover.write_parquet(tmp_path / "mainline_history" / "part.parquet")
    _patch_custom_daily(monkeypatch)
    incoming = pl.DataFrame({
        "date": [date(2026, 7, 16)],
        "kind": ["concept"],
        "member": ["custom"],
        "limit_up_count": [4],
        "rank": [1],
    })
    upsert_mainline_history(tmp_path, incoming)
    loaded = load_mainline_history(tmp_path)
    assert loaded["member"].to_list() == ["custom"]
    saved = pl.read_parquet(tmp_path / "mainline_history" / "part.parquet")
    assert saved["route"].to_list() == ["fuyao"]


def test_pool_membership_skips_leftover_under_custom(monkeypatch, tmp_path):
    pools = tmp_path / "pools"
    pools.mkdir()
    pl.DataFrame({
        "symbol": ["600000.SH"],
        "as_of": [date(2026, 7, 17)],
        "index_code": ["000300"],
        "source": ["tickflow"],
        "pool_id": ["CSI300"],
        "route": ["tickflow"],
    }).write_parquet(pools / "CSI300.parquet")
    monkeypatch.setattr(
        "app.services.preferences.get_pool_provider",
        lambda: "fuyao",
    )
    assert build_index_membership_from_pools(tmp_path).is_empty()


def test_pool_membership_keeps_untagged_leftover_tickflow(monkeypatch, tmp_path):
    pools = tmp_path / "pools"
    pools.mkdir()
    pl.DataFrame({
        "symbol": ["600000.SH"],
        "as_of": [date(2026, 7, 17)],
        "index_code": ["000300"],
        "source": ["csindex"],
        "pool_id": ["CSI300"],
    }).write_parquet(pools / "CSI300.parquet")
    monkeypatch.setattr(
        "app.services.preferences.get_pool_provider",
        lambda: "tickflow",
    )
    mem = build_index_membership_from_pools(tmp_path)
    assert mem["symbol"].to_list() == ["600000.SH"]


def test_pool_membership_never_fail_open(monkeypatch, tmp_path):
    pools = tmp_path / "pools"
    pools.mkdir()
    pl.DataFrame({
        "symbol": ["600000.SH"],
        "as_of": [date(2026, 7, 17)],
        "index_code": ["000300"],
        "source": ["tickflow"],
        "pool_id": ["CSI300"],
    }).write_parquet(pools / "CSI300.parquet")
    monkeypatch.setattr(
        "app.services.preferences.get_pool_provider",
        _prefs_boom,
    )
    assert build_index_membership_from_pools(tmp_path).is_empty()


def test_financial_pit_migrate_skips_leftover_under_custom(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "income" / "part.parquet"
    path.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "period_end": [date(2026, 3, 31)],
        "notice_date": [date(2026, 4, 1)],
        "net_profit": [1.0],
        "source": ["tickflow"],
        "table": ["income"],
        "route": ["tickflow"],
    }).write_parquet(path)
    from app.services import preferences

    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    report = migrate_existing_financials_to_pit(tmp_path, tables=["income"])
    assert report["tables"]["income"]["skipped"] is True
    assert report["tables"]["income"]["reason"] == "stale_route"
    saved = pl.read_parquet(path)
    assert "restatement_id" not in saved.columns


def test_financial_pit_v2_skips_leftover_under_custom(monkeypatch, tmp_path):
    path = tmp_path / "financials" / "metrics" / "part.parquet"
    path.parent.mkdir(parents=True)
    pl.DataFrame({
        "symbol": ["000001.SZ"],
        "period_end": [date(2026, 3, 31)],
        "roe": [12.0],
        "source": ["tickflow"],
        "table": ["metrics"],
        "route": ["tickflow"],
    }).write_parquet(path)
    from app.services import preferences

    monkeypatch.setattr(preferences, "get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr(preferences, "is_public_financial_provider", lambda name=None: False)
    result = migrate_financial_table_to_v2(tmp_path, "metrics")
    assert result["skipped"] is True
    assert result["reason"] == "stale_route"


def test_catalog_status_drops_leftover_calendar_after_switch(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df(route="tickflow"))
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    service = CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())
    service.rescan()
    first = service.compatibility_status()
    assert first["daily"] is not None
    assert first["daily"]["latest_date"] == "2026-07-17"
    _patch_custom_daily(monkeypatch)
    second = service.compatibility_status()
    assert second["daily"] is None


def test_catalog_status_keeps_untagged_leftover_tickflow(monkeypatch, tmp_path):
    _write_part(tmp_path, "kline_daily", "2026-07-17", _daily_df())
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    service = CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())
    service.rescan()
    status = service.compatibility_status()
    assert status["daily"] is not None
    assert status["daily"]["latest_date"] == "2026-07-17"


def test_leftover_tickflow_realtime_stays_none(monkeypatch):
    monkeypatch.setattr(kline_sync.preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "free"))
    assert QuoteService.realtime_mode() == "none"


def test_untagged_leftover_still_serves_regime(monkeypatch, tmp_path):
    (tmp_path / "regime_history").mkdir(parents=True)
    pl.DataFrame({
        "date": [date(2026, 7, 17)],
        "state": ["range"],
        "score": [50.0],
    }).write_parquet(tmp_path / "regime_history" / "part.parquet")
    monkeypatch.setattr(kline_sync.preferences, "get_daily_data_provider", lambda: "tickflow")
    loaded = load_regime_history(tmp_path)
    assert loaded["state"].to_list() == ["range"]
