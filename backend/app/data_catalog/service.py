"""SQLite-backed catalog composition and explicit local rescans."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.data_providers.base import ProviderDatasetManifest

from .control_db import CatalogControlDB
from .definitions import DATASET_DEFINITIONS, DatasetDefinition
from .models import (
    CatalogResponse,
    DatasetAvailability,
    DatasetCatalogEntry,
    DatasetState,
    FieldContract,
    LineageSummary,
    MarketCoverage,
    StorageBreakdown,
    StorageCategory,
    SyncRun,
)
from .scanner import CatalogScanner, DatasetScanResult

_CATEGORY_TITLES = {
    "stocks": "Stocks",
    "etfs": "ETFs",
    "indices": "Indices",
    "quote_snapshot": "Quote snapshot",
    "sealed_l1": "Sealed L1",
    "depth5": "True depth5",
    "pools": "Pools",
    "financials": "Financials",
    "ext_data": "External data",
    "lineage": "Lineage",
    "job_store": "Job store",
    "logs": "Logs",
    "user_data": "User data",
    "control": "SQLite control files",
    "operational_other": "Other operational files",
}
_OPERATIONAL_KEYS = {
    "lineage",
    "job_store",
    "logs",
    "user_data",
    "control",
    "operational_other",
}
_LEGACY_STORAGE_DATASETS = {
    "daily": ("stock_daily",),
    "enriched": ("stock_enriched",),
    "index_daily": ("index_daily",),
    "index_enriched": ("index_enriched",),
    "index_instruments": ("index_instruments",),
    "etf_daily": ("etf_daily",),
    "etf_enriched": ("etf_enriched",),
    "etf_instruments": ("etf_instruments",),
    "etf_adj_factor": ("etf_adj_factor",),
    "minute": ("stock_minute",),
    "adj_factor": ("stock_adj_factor",),
    "instruments": ("stock_instruments",),
    "ext_data": ("ext_data",),
    "financials": (
        "financial_metrics",
        "financial_income",
        "financial_balance_sheet",
        "financial_cash_flow",
        "financial_shares",
    ),
}


class CatalogRescanInProgress(RuntimeError):  # noqa: N818
    """Raised when a second local rescan would overlap the active snapshot."""

    def __init__(self) -> None:
        super().__init__("catalog rescan already in progress")


class CatalogService:
    def __init__(
        self,
        data_dir: Path,
        control_db: CatalogControlDB,
        *,
        scanner: CatalogScanner | None = None,
        definitions: Sequence[DatasetDefinition] = DATASET_DEFINITIONS,
        manifests: Sequence[ProviderDatasetManifest] | None = None,
        entitlement_resolver: Callable[[ProviderDatasetManifest], bool] | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.control_db = control_db
        self.definitions = tuple(definitions)
        self._by_id = {
            definition.descriptor.dataset_id: definition for definition in self.definitions
        }
        self.scanner = scanner or CatalogScanner(self.data_dir, self.definitions)
        if manifests is None:
            from app.data_providers.registry import list_provider_manifests

            manifests = list_provider_manifests()
        self.manifests = tuple(
            sorted(
                (manifest.model_copy(deep=True) for manifest in manifests),
                key=lambda item: (item.dataset_id, item.provider, item.operations),
            )
        )
        self.entitlement_resolver = entitlement_resolver
        self._rescan_lock = threading.Lock()
        self.control_db.initialize()

    def rescan(self, dataset_id: str | None = None) -> CatalogResponse:
        if not self._rescan_lock.acquire(blocking=False):
            raise CatalogRescanInProgress()
        try:
            return self._rescan_locked(dataset_id)
        finally:
            self._rescan_lock.release()

    def refresh_after_mutation(self, dataset_id: str | None = None) -> CatalogResponse:
        """Serialize a writer-triggered refresh behind any explicit scan.

        Mutations must not silently lose their refresh merely because a manual
        scan was already in flight.  The public rescan endpoint remains
        non-blocking/409; writer completion instead waits and publishes the
        post-mutation snapshot before returning.
        """
        with self._rescan_lock:
            return self._rescan_locked(dataset_id)

    def _rescan_locked(self, dataset_id: str | None = None) -> CatalogResponse:
        if dataset_id is not None and dataset_id not in self._by_id:
            raise KeyError(f"unknown dataset_id: {dataset_id}")
        dataset_ids = [dataset_id] if dataset_id is not None else list(self._by_id)
        started_at = _utc_now()
        run_ids = {item: f"catalog-{uuid.uuid4().hex}" for item in dataset_ids}
        try:
            if dataset_id is None:
                snapshot = self.scanner.scan_all(run_ids)
                scan_results = snapshot.datasets
                meta_updates = {
                    "storage_breakdown": snapshot.storage.model_dump(mode="json"),
                    "dataset_storage": snapshot.dataset_storage,
                    "catalog_refreshed_at": {"value": snapshot.refreshed_at},
                }
            else:
                expected = self._cached_expected_by_market(dataset_id)
                result = self.scanner.scan_dataset(
                    dataset_id,
                    run_ids[dataset_id],
                    expected_by_market=expected,
                )
                scan_results = {dataset_id: result}
                refreshed_at = result.state.updated_at
                dataset_storage = self.control_db.get_meta("dataset_storage") or {}
                dataset_storage[dataset_id] = {
                    "bytes": result.state.managed_bytes,
                    "files": int(result.state.payload.get("file_count", 0)),
                }
                storage = self._rebuild_storage(dataset_storage)
                meta_updates = {
                    "storage_breakdown": storage.model_dump(mode="json"),
                    "dataset_storage": dataset_storage,
                    "catalog_refreshed_at": {"value": refreshed_at},
                }
        except Exception as error:
            finished_at = _utc_now()
            message = " ".join(str(error).split())[:500] or type(error).__name__
            for failed_dataset_id in dataset_ids:
                self.control_db.upsert_sync_run(
                    SyncRun(
                        run_id=run_ids[failed_dataset_id],
                        dataset_id=failed_dataset_id,
                        provider="local",
                        operation="catalog_rescan",
                        started_at=started_at,
                        finished_at=finished_at,
                        status="failed",
                        quality_status="failed",
                        error_code="catalog_scan_failed",
                        error_message=message,
                    )
                )
            self.control_db.set_meta("catalog_stale", {"value": True})
            # A failed local scan must never discard the prior committed snapshot.
            # Make the retained response explicit so callers do not mistake it for a fresh scan.
            return self.list_catalog().model_copy(update={"stale": True})

        finished_at = _utc_now()
        persisted = []
        retained_failure = False
        for scanned_dataset_id, result in scan_results.items():
            run_status = _run_status(result)
            run = SyncRun(
                run_id=run_ids[scanned_dataset_id],
                dataset_id=scanned_dataset_id,
                provider="local",
                operation="catalog_rescan",
                started_at=started_at,
                finished_at=finished_at,
                status=run_status,
                rows_fetched=0,
                rows_published=result.state.row_count,
                quality_status=result.state.quality_status,
                error_code=("catalog_quality_failed" if run_status == "failed" else None),
                error_message=(
                    "; ".join(result.state.payload.get("scan_errors", []))[:500]
                    if run_status == "failed"
                    else None
                ),
            )
            previous = self.control_db.get_dataset_state(scanned_dataset_id)
            if (
                run_status == "failed"
                and previous is not None
                and previous.quality_status
                in {
                    "healthy",
                    "degraded",
                }
            ):
                self.control_db.upsert_sync_run(run)
                retained_failure = True
                continue
            persisted.append((result.state, run, result.artifacts))
        any_failed = retained_failure or any(
            _run_status(result) == "failed" for result in scan_results.values()
        )
        meta_updates["catalog_stale"] = {"value": any_failed}
        if retained_failure and not persisted:
            # Preserve the previous successful state/artifact/storage snapshot.
            self.control_db.set_meta("catalog_stale", {"value": True})
        else:
            self.control_db.commit_scan_results(persisted, meta_updates)
        return self.list_catalog()

    def list_catalog(self) -> CatalogResponse:
        states = {state.dataset_id: state for state in self.control_db.list_dataset_states()}
        refreshed_meta = self.control_db.get_meta("catalog_refreshed_at")
        refreshed_at = refreshed_meta.get("value") if refreshed_meta else None
        entries = [
            self._catalog_entry(
                definition, states.get(definition.descriptor.dataset_id), refreshed_at
            )
            for definition in self.definitions
        ]
        storage_meta = self.control_db.get_meta("storage_breakdown")
        storage = (
            StorageBreakdown.model_validate(storage_meta)
            if storage_meta is not None
            else StorageBreakdown()
        )
        stale_meta = self.control_db.get_meta("catalog_stale")
        return CatalogResponse(
            datasets=entries,
            storage=storage,
            refreshed_at=refreshed_at,
            stale=not bool(states) or bool((stale_meta or {}).get("value")),
        )

    def get_dataset(self, dataset_id: str) -> DatasetCatalogEntry | None:
        if dataset_id not in self._by_id:
            return None
        state = self.control_db.get_dataset_state(dataset_id)
        refreshed_meta = self.control_db.get_meta("catalog_refreshed_at")
        refreshed_at = refreshed_meta.get("value") if refreshed_meta else None
        return self._catalog_entry(self._by_id[dataset_id], state, refreshed_at)

    def get_schema(self, dataset_id: str) -> list[FieldContract] | None:
        definition = self._by_id.get(dataset_id)
        if definition is None:
            return None
        return [field.model_copy(deep=True) for field in definition.descriptor.fields]

    def list_runs(self, dataset_id: str | None = None, limit: int = 100) -> list[SyncRun]:
        return self.control_db.list_sync_runs(dataset_id, limit)

    def compatibility_status(self) -> dict[str, Any]:
        states = {state.dataset_id: state for state in self.control_db.list_dataset_states()}
        return {
            "daily": self._table_stats(states.get("stock_daily")),
            "enriched": self._table_stats(states.get("stock_enriched"), enriched=True),
            "index_daily": self._table_stats(states.get("index_daily")),
            "index_enriched": self._table_stats(states.get("index_enriched"), enriched=True),
            "index_instruments": self._instrument_stats(states.get("index_instruments")),
            "etf_daily": self._table_stats(states.get("etf_daily")),
            "etf_enriched": self._table_stats(states.get("etf_enriched"), enriched=True),
            "etf_instruments": self._instrument_stats(states.get("etf_instruments")),
            "minute": self._table_stats(states.get("stock_minute")),
            "adj_factor": self._table_stats(states.get("stock_adj_factor")),
            "instruments": self._instrument_stats(states.get("stock_instruments")),
            "financials": self._financial_stats(states),
            "storage": self._legacy_storage(),
            "next_pipeline_run": None,
            "next_instruments_run": None,
            "last_pipeline_run": None,
            "last_instruments_run": None,
            "checked_at": _utc_now(),
        }

    def _catalog_entry(
        self,
        definition: DatasetDefinition,
        state: DatasetState | None,
        refreshed_at: str | None,
    ) -> DatasetCatalogEntry:
        if state is None:
            state = DatasetState(
                dataset_id=definition.descriptor.dataset_id,
                schema_version=definition.descriptor.schema_version,
                unit_version=definition.descriptor.unit_version,
                updated_at=refreshed_at or "1970-01-01T00:00:00Z",
                payload=_empty_payload(),
            )
        coverage = [
            MarketCoverage.model_validate(item) for item in state.payload.get("coverage", [])
        ]
        lineage = [LineageSummary.model_validate(item) for item in state.payload.get("lineage", [])]
        provider, provider_supported, entitled = self._provider_resolution(definition, lineage)
        local_materialized = bool(state.managed_bytes or int(state.payload.get("file_count", 0)))
        serving_ready = local_materialized and state.quality_status in {"healthy", "degraded"}
        reason_code: str | None
        if serving_ready:
            reason_code = None
        elif local_materialized:
            reason_code = (
                "quality_failed" if state.quality_status == "failed" else "quality_unknown"
            )
        elif not provider_supported:
            reason_code = "provider_unsupported"
        elif not entitled:
            reason_code = "not_entitled"
        else:
            reason_code = "not_materialized"
        availability = DatasetAvailability(
            provider_supported=provider_supported,
            entitled=entitled,
            local_materialized=local_materialized,
            serving_ready=serving_ready,
            reason_code=reason_code,
        )
        descriptor = definition.descriptor.model_copy(
            deep=True, update={"availability": availability}
        )
        return DatasetCatalogEntry(
            descriptor=descriptor,
            state=state,
            provider=provider,
            coverage=coverage,
            lineage=lineage,
            depth5_available=bool(state.payload.get("depth5_available", False)),
        )

    def _provider_resolution(
        self,
        definition: DatasetDefinition,
        lineage: Sequence[LineageSummary],
    ) -> tuple[str | None, bool, bool]:
        candidates = [
            manifest
            for manifest in self.manifests
            if manifest.dataset_id == definition.descriptor.dataset_id
            and (definition.provider is None or manifest.provider == definition.provider)
        ]
        local_supported = definition.provider is None and not candidates
        if not candidates:
            if local_supported:
                return "local", True, True
            return definition.provider, False, False

        entitled_candidates = [manifest for manifest in candidates if self._is_entitled(manifest)]
        lineage_source = (
            max(lineage, key=lambda item: (_lineage_timestamp(item.fetched_at), item.source)).source
            if lineage
            else None
        )
        chosen = next(
            (manifest for manifest in candidates if manifest.provider == lineage_source),
            None,
        )
        if chosen is None:
            chosen = (entitled_candidates or candidates)[0]
        return chosen.provider, True, bool(entitled_candidates)

    def _is_entitled(self, manifest: ProviderDatasetManifest) -> bool:
        if self.entitlement_resolver is not None:
            return bool(self.entitlement_resolver(manifest))
        return manifest.provider in {"public", "local"} or manifest.entitlement_required is None

    def _cached_expected_by_market(self, dataset_id: str) -> dict[str, int] | None:
        definition = self._by_id[dataset_id]
        asset_types = definition.descriptor.asset_types
        if len(asset_types) != 1:
            return None
        instrument_id = {
            "stock": "stock_instruments",
            "etf": "etf_instruments",
            "index": "index_instruments",
        }.get(asset_types[0])
        if instrument_id is None:
            return None
        state = self.control_db.get_dataset_state(instrument_id)
        if state is None:
            return None
        return {
            item.market: item.symbol_count
            for item in (
                MarketCoverage.model_validate(value) for value in state.payload.get("coverage", [])
            )
        }

    def _rebuild_storage(self, dataset_storage: Mapping[str, Any]) -> StorageBreakdown:
        previous = self.control_db.get_meta("storage_breakdown")
        previous_categories = {item["key"]: item for item in (previous or {}).get("categories", [])}
        category_values: dict[str, dict[str, int]] = {
            key: {"bytes": 0, "files": 0}
            for key in _CATEGORY_TITLES
            if key not in _OPERATIONAL_KEYS
        }
        for definition in self.definitions:
            values = dataset_storage.get(definition.descriptor.dataset_id, {})
            category = category_values.setdefault(
                definition.storage_category, {"bytes": 0, "files": 0}
            )
            category["bytes"] += max(0, int(values.get("bytes", 0)))
            category["files"] += max(0, int(values.get("files", 0)))
        categories: list[StorageCategory] = []
        for key, title in _CATEGORY_TITLES.items():
            if key in _OPERATIONAL_KEYS:
                values = previous_categories.get(key, {})
            else:
                values = category_values.get(key, {})
            categories.append(
                StorageCategory(
                    key=key,
                    title=title,
                    kind="operational" if key in _OPERATIONAL_KEYS else "managed",
                    bytes=max(0, int(values.get("bytes", 0))),
                    files=max(0, int(values.get("files", 0))),
                )
            )
        managed = sum(item.bytes for item in categories if item.kind == "managed")
        operational = sum(item.bytes for item in categories if item.kind == "operational")
        return StorageBreakdown(
            managed_data_bytes=managed,
            operational_bytes=operational,
            total_bytes=managed + operational,
            categories=categories,
        )

    @staticmethod
    def _table_stats(
        state: DatasetState | None, *, enriched: bool = False
    ) -> dict[str, Any] | None:
        if state is None or not _is_materialized(state):
            return None
        stats: dict[str, Any] = {
            "rows": state.row_count,
            "earliest_date": state.earliest_time,
            "latest_date": state.latest_time,
            "symbols_covered": state.symbol_count,
            "trading_days": int(state.payload.get("trading_days", 0)),
        }
        if enriched:
            stats["fields"] = int(state.payload.get("field_count", 0))
        return stats

    @staticmethod
    def _instrument_stats(state: DatasetState | None) -> dict[str, Any] | None:
        if state is None or not _is_materialized(state):
            return None
        return {
            "rows": state.row_count,
            "symbols_covered": state.symbol_count,
            "latest_as_of": state.latest_time,
            "named": int(state.payload.get("named_count", 0)),
        }

    @staticmethod
    def _financial_stats(states: Mapping[str, DatasetState]) -> dict[str, Any] | None:
        table_ids = {
            "metrics": "financial_metrics",
            "income": "financial_income",
            "balance_sheet": "financial_balance_sheet",
            "cash_flow": "financial_cash_flow",
            "shares": "financial_shares",
        }
        tables = {
            name: {
                "rows": states[dataset_id].row_count if dataset_id in states else 0,
                "symbols": states[dataset_id].symbol_count if dataset_id in states else 0,
            }
            for name, dataset_id in table_ids.items()
        }
        if not any(
            _is_materialized(states[dataset_id])
            for dataset_id in table_ids.values()
            if dataset_id in states
        ):
            return None
        return {"rows": sum(item["rows"] for item in tables.values()), "tables": tables}

    def _legacy_storage(self) -> dict[str, Any]:
        dataset_storage = self.control_db.get_meta("dataset_storage") or {}
        values: dict[str, Any] = {}
        for legacy_key, dataset_ids in _LEGACY_STORAGE_DATASETS.items():
            files = sum(
                int(dataset_storage.get(dataset_id, {}).get("files", 0))
                for dataset_id in dataset_ids
            )
            raw_bytes = sum(
                int(dataset_storage.get(dataset_id, {}).get("bytes", 0))
                for dataset_id in dataset_ids
            )
            values[f"{legacy_key}_files"] = files
            values[f"{legacy_key}_size_mb"] = round(raw_bytes / 1_048_576, 2)
        storage = self.control_db.get_meta("storage_breakdown") or {}
        values["total_size_mb"] = round(int(storage.get("total_bytes", 0)) / 1_048_576, 2)
        return values


def _run_status(result: DatasetScanResult) -> str:
    if result.state.quality_status == "failed":
        return "failed"
    if result.state.quality_status == "unknown" and result.state.payload.get("scan_errors"):
        return "failed"
    if result.state.quality_status == "degraded":
        return "degraded"
    return "succeeded"


def _empty_payload() -> dict[str, Any]:
    return {
        "file_count": 0,
        "field_count": 0,
        "trading_days": 0,
        "named_count": 0,
        "coverage": [],
        "lineage": [],
        "scan_errors": [],
        "depth5_available": False,
    }


def _is_materialized(state: DatasetState) -> bool:
    return bool(state.managed_bytes or int(state.payload.get("file_count", 0)))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _lineage_timestamp(value: str | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
