from __future__ import annotations

import os
import socket
import time
from dataclasses import replace
from datetime import date
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

from app.data_catalog.control_db import CatalogControlDB
from app.data_catalog.definitions import (
    DatasetDefinition,
    get_dataset_definition,
)
from app.data_catalog.models import (
    DatasetState,
)
from app.data_catalog.scanner import CatalogScanner
from app.data_catalog.service import CatalogService
from app.data_providers.base import ProviderDatasetManifest


def _write_parquet(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path)
    return path


def _bar(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "date": date(2026, 7, 21),
        "open": 10.0,
        "high": 11.0,
        "low": 9.0,
        "close": 10.5,
        "volume": 12.0,
        "amount": 1_200.0,
        "change_pct": 1.0,
    }


def _payload(*, file_count: int = 0, field_count: int = 0) -> dict:
    return {
        "file_count": file_count,
        "field_count": field_count,
        "trading_days": 0,
        "named_count": 0,
        "coverage": [],
        "lineage": [],
        "scan_errors": [],
        "depth5_available": False,
    }


def _state(
    dataset_id: str,
    *,
    quality: str = "unknown",
    managed_bytes: int = 0,
    file_count: int = 0,
) -> DatasetState:
    definition = get_dataset_definition(dataset_id)
    return DatasetState(
        dataset_id=dataset_id,
        schema_version=definition.descriptor.schema_version,
        unit_version=definition.descriptor.unit_version,
        quality_status=quality,
        managed_bytes=managed_bytes,
        updated_at="2026-07-21T10:00:00Z",
        payload=_payload(file_count=file_count),
    )


def _manifest(
    dataset_id: str,
    *,
    provider: str = "paid",
    entitlement_required: str | None = "pro",
) -> ProviderDatasetManifest:
    return ProviderDatasetManifest(
        provider=provider,
        dataset_id=dataset_id,
        asset_types=["stock"],
        operations=["daily"],
        entitlement_required=entitlement_required,
        history_guarantee=None,
        verified_at=None,
    )


def _definition(dataset_id: str, *, provider: str | None) -> DatasetDefinition:
    return replace(get_dataset_definition(dataset_id), provider=provider)


def test_availability_keeps_provider_entitlement_local_and_serving_independent(
    tmp_path: Path,
) -> None:
    definitions = (
        _definition("stock_daily", provider="unsupported"),
        _definition("stock_enriched", provider="paid"),
        _definition("stock_minute", provider="public"),
        _definition("stock_adj_factor", provider="paid"),
    )
    manifests = (
        _manifest("stock_enriched"),
        _manifest("stock_minute", provider="public", entitlement_required=None),
        _manifest("stock_adj_factor"),
    )
    db = CatalogControlDB(tmp_path)
    db.upsert_dataset_state(
        _state("stock_adj_factor", quality="healthy", managed_bytes=10, file_count=1)
    )
    service = CatalogService(
        tmp_path,
        db,
        definitions=definitions,
        manifests=manifests,
        entitlement_resolver=lambda manifest: manifest.dataset_id == "stock_minute",
    )

    entries = {entry.descriptor.dataset_id: entry for entry in service.list_catalog().datasets}

    unsupported = entries["stock_daily"].descriptor.availability
    assert unsupported.model_dump() == {
        "provider_supported": False,
        "entitled": False,
        "local_materialized": False,
        "serving_ready": False,
        "reason_code": "provider_unsupported",
    }
    not_entitled = entries["stock_enriched"].descriptor.availability
    assert not_entitled.model_dump() == {
        "provider_supported": True,
        "entitled": False,
        "local_materialized": False,
        "serving_ready": False,
        "reason_code": "not_entitled",
    }
    entitled_not_local = entries["stock_minute"].descriptor.availability
    assert entitled_not_local.model_dump() == {
        "provider_supported": True,
        "entitled": True,
        "local_materialized": False,
        "serving_ready": False,
        "reason_code": "not_materialized",
    }
    local_not_entitled = entries["stock_adj_factor"].descriptor.availability
    assert local_not_entitled.model_dump() == {
        "provider_supported": True,
        "entitled": False,
        "local_materialized": True,
        "serving_ready": True,
        "reason_code": None,
    }


def test_local_failed_quality_remains_materialized_but_not_serving_ready(tmp_path: Path) -> None:
    db = CatalogControlDB(tmp_path)
    db.upsert_dataset_state(
        _state("stock_daily", quality="failed", managed_bytes=10, file_count=1)
    )
    service = CatalogService(
        tmp_path,
        db,
        definitions=(_definition("stock_daily", provider=None),),
        manifests=(),
    )

    entry = service.get_dataset("stock_daily")

    assert entry is not None
    assert entry.provider == "local"
    assert entry.descriptor.availability.model_dump() == {
        "provider_supported": True,
        "entitled": True,
        "local_materialized": True,
        "serving_ready": False,
        "reason_code": "quality_failed",
    }


def test_provider_selection_prefers_latest_lineage_source_not_payload_order(tmp_path: Path) -> None:
    db = CatalogControlDB(tmp_path)
    state = _state("stock_daily", quality="healthy", managed_bytes=10, file_count=1)
    state.payload["lineage"] = [
        {
            "source": "paid",
            "fetched_at": "2026-07-21T10:00:00Z",
            "unit_version": "cn_market_v1",
            "quality_status": "healthy",
        },
        {
            "source": "public",
            "fetched_at": "2026-07-20T10:00:00Z",
            "unit_version": "cn_market_v1",
            "quality_status": "healthy",
        },
    ]
    db.upsert_dataset_state(state)
    service = CatalogService(
        tmp_path,
        db,
        definitions=(_definition("stock_daily", provider=None),),
        manifests=(
            _manifest("stock_daily", provider="paid"),
            _manifest("stock_daily", provider="public", entitlement_required=None),
        ),
        entitlement_resolver=lambda manifest: manifest.provider == "public",
    )

    entry = service.get_dataset("stock_daily")

    assert entry is not None
    assert entry.provider == "paid"


def test_rescan_is_local_only_and_persists_real_parquet_without_network(
    tmp_path: Path, monkeypatch
) -> None:
    _write_parquet(tmp_path / "kline_daily" / "date=2026-07-21" / "part.parquet", [_bar("600000.SH")])

    def deny_network(*args, **kwargs):
        raise AssertionError("catalog rescan attempted network access")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    db = CatalogControlDB(tmp_path)
    service = CatalogService(tmp_path, db, manifests=())

    response = service.rescan("stock_daily")

    state = db.get_dataset_state("stock_daily")
    assert state is not None
    assert state.row_count == 1
    assert state.quality_status == "healthy"
    assert response.refreshed_at is not None
    run = db.list_sync_runs("stock_daily", limit=1)[0]
    assert run.operation == "catalog_rescan"
    assert run.status == "succeeded"
    assert run.rows_published == 1


def test_fatal_scan_failure_records_failed_run_and_preserves_last_good_snapshot(
    tmp_path: Path,
) -> None:
    parquet = _write_parquet(
        tmp_path / "kline_daily" / "date=2026-07-21" / "part.parquet",
        [_bar("600000.SH")],
    )
    db = CatalogControlDB(tmp_path)
    service = CatalogService(tmp_path, db, manifests=())
    service.rescan("stock_daily")
    old_state = db.get_dataset_state("stock_daily")
    old_artifacts = db.list_artifacts("stock_daily")
    old_meta = {
        key: db.get_meta(key)
        for key in ("storage_breakdown", "dataset_storage", "catalog_refreshed_at")
    }
    parquet.unlink()

    class FailingScanner:
        def scan_dataset(self, dataset_id, run_id, *, expected_by_market=None):
            raise RuntimeError("fatal scanner failure with a very long private detail" * 20)

    failed_service = CatalogService(
        tmp_path,
        db,
        scanner=FailingScanner(),  # type: ignore[arg-type]
        manifests=(),
    )

    response = failed_service.rescan("stock_daily")

    assert db.get_dataset_state("stock_daily") == old_state
    assert db.list_artifacts("stock_daily") == old_artifacts
    assert {
        key: db.get_meta(key)
        for key in ("storage_breakdown", "dataset_storage", "catalog_refreshed_at")
    } == old_meta
    failed_run = db.list_sync_runs("stock_daily", limit=1)[0]
    assert failed_run.status == "failed"
    assert failed_run.error_code == "catalog_scan_failed"
    assert failed_run.error_message is not None
    assert len(failed_run.error_message) <= 500
    assert response.datasets


def test_dataset_rescan_replaces_only_target_snapshot_and_rebuilds_cached_totals(
    tmp_path: Path,
) -> None:
    _write_parquet(tmp_path / "kline_daily" / "part.parquet", [_bar("600000.SH")])
    _write_parquet(tmp_path / "kline_index_daily" / "part.parquet", [_bar("000001.SH")])
    db = CatalogControlDB(tmp_path)
    service = CatalogService(tmp_path, db, manifests=())
    service.rescan()
    index_state = db.get_dataset_state("index_daily")
    index_artifacts = db.list_artifacts("index_daily")
    old_dataset_storage = db.get_meta("dataset_storage")
    assert old_dataset_storage is not None

    _write_parquet(
        tmp_path / "kline_daily" / "part.parquet",
        [_bar("600000.SH"), _bar("000001.SZ")],
    )
    service.rescan("stock_daily")

    assert db.get_dataset_state("stock_daily").row_count == 2  # type: ignore[union-attr]
    assert db.get_dataset_state("index_daily") == index_state
    assert db.list_artifacts("index_daily") == index_artifacts
    new_dataset_storage = db.get_meta("dataset_storage")
    assert new_dataset_storage is not None
    assert new_dataset_storage["index_daily"] == old_dataset_storage["index_daily"]
    storage = db.get_meta("storage_breakdown")
    assert storage is not None
    assert storage["total_bytes"] == storage["managed_data_bytes"] + storage["operational_bytes"]


def test_hot_reads_use_sqlite_only_and_warmed_catalog_query_is_under_200ms(
    tmp_path: Path, monkeypatch
) -> None:
    _write_parquet(tmp_path / "kline_daily" / "part.parquet", [_bar("600000.SH")])
    db = CatalogControlDB(tmp_path)
    scanner = CatalogScanner(tmp_path)
    service = CatalogService(tmp_path, db, scanner=scanner, manifests=())
    service.rescan()

    def forbidden(*args, **kwargs):
        raise AssertionError("hot read touched scanner/filesystem/data engine")

    monkeypatch.setattr(scanner, "scan_all", forbidden)
    monkeypatch.setattr(scanner, "scan_dataset", forbidden)
    monkeypatch.setattr(os, "walk", forbidden)
    monkeypatch.setattr(Path, "rglob", forbidden)
    monkeypatch.setattr(pl, "read_parquet", forbidden)
    monkeypatch.setattr(pq, "ParquetFile", forbidden)
    import duckdb

    monkeypatch.setattr(duckdb, "connect", forbidden)

    service.list_catalog()
    started = time.perf_counter()
    response = service.list_catalog()
    elapsed = time.perf_counter() - started

    assert elapsed < 0.2
    assert service.get_dataset("stock_daily") is not None
    assert service.get_schema("stock_daily")
    assert service.list_runs(limit=5)
    assert service.compatibility_status()["daily"] is not None
    assert response.datasets


def test_compatibility_status_preserves_exact_legacy_keys_and_all_financial_tables(
    tmp_path: Path,
) -> None:
    _write_parquet(tmp_path / "kline_daily" / "date=2026-07-21" / "part.parquet", [_bar("600000.SH")])
    _write_parquet(
        tmp_path / "instruments" / "part.parquet",
        [{"symbol": "600000.SH", "name": "浦发银行", "as_of": date(2026, 7, 21)}],
    )
    for table, field in {
        "metrics": ("roe", 12.0),
        "income": ("revenue", 100.0),
        "balance_sheet": ("total_assets", 200.0),
        "cash_flow": ("net_operating_cash_flow", 50.0),
        "shares": ("total_shares", 1_000.0),
    }.items():
        name, value = field
        _write_parquet(
            tmp_path / "financials" / table / "part.parquet",
            [{"symbol": "600000.SH", "period_end": date(2026, 6, 30), name: value}],
        )
    service = CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())
    service.rescan()

    status = service.compatibility_status()

    assert set(status) == {
        "daily",
        "enriched",
        "index_daily",
        "index_enriched",
        "index_instruments",
        "etf_daily",
        "etf_enriched",
        "etf_instruments",
        "minute",
        "adj_factor",
        "instruments",
        "financials",
        "storage",
        "next_pipeline_run",
        "next_instruments_run",
        "last_pipeline_run",
        "last_instruments_run",
        "checked_at",
    }
    assert set(status["daily"]) == {
        "rows",
        "earliest_date",
        "latest_date",
        "symbols_covered",
        "trading_days",
    }
    assert set(status["instruments"]) == {
        "rows",
        "symbols_covered",
        "latest_as_of",
        "named",
    }
    assert set(status["financials"]["tables"]) == {
        "metrics",
        "income",
        "balance_sheet",
        "cash_flow",
        "shares",
    }
    assert status["financials"]["rows"] == 5
    assert set(status["storage"]) == {
        "daily_files",
        "daily_size_mb",
        "enriched_files",
        "enriched_size_mb",
        "index_daily_files",
        "index_daily_size_mb",
        "index_enriched_files",
        "index_enriched_size_mb",
        "index_instruments_files",
        "index_instruments_size_mb",
        "etf_daily_files",
        "etf_daily_size_mb",
        "etf_enriched_files",
        "etf_enriched_size_mb",
        "etf_instruments_files",
        "etf_instruments_size_mb",
        "etf_adj_factor_files",
        "etf_adj_factor_size_mb",
        "minute_files",
        "minute_size_mb",
        "adj_factor_files",
        "adj_factor_size_mb",
        "instruments_files",
        "instruments_size_mb",
        "ext_data_files",
        "ext_data_size_mb",
        "financials_files",
        "financials_size_mb",
        "total_size_mb",
    }
    assert status["next_pipeline_run"] is None
    assert status["next_instruments_run"] is None


def test_compatibility_checked_at_uses_fresh_clock_without_changing_catalog_freshness(
    tmp_path: Path, monkeypatch
) -> None:
    db = CatalogControlDB(tmp_path)
    db.set_meta("catalog_refreshed_at", {"value": "2026-07-21T08:00:00Z"})
    service = CatalogService(tmp_path, db, manifests=())
    import app.data_catalog.service as service_module

    clock = iter(("2026-07-21T09:00:00Z", "2026-07-21T09:00:01Z"))
    monkeypatch.setattr(service_module, "_utc_now", lambda: next(clock))

    first = service.compatibility_status()
    second = service.compatibility_status()

    assert first["checked_at"] == "2026-07-21T09:00:00Z"
    assert second["checked_at"] == "2026-07-21T09:00:01Z"
    assert service.list_catalog().refreshed_at == "2026-07-21T08:00:00Z"
