"""SQLite-backed catalog composition and explicit local rescans."""
# ruff: noqa: RUF001

from __future__ import annotations

import os
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
    ControlSummaryResponse,
    DatasetAvailability,
    DatasetCatalogEntry,
    DatasetState,
    FieldContract,
    LineageSummary,
    MarketCoverage,
    StorageBreakdown,
    StorageCategory,
    SyncRun,
    UnregisteredPhysicalData,
)
from .scanner import CatalogScanner, DatasetScanResult

_CATEGORY_TITLES = {
    "stocks": "股票",
    "etfs": "ETF",
    "indices": "指数",
    "quote_snapshot": "行情快照",
    "sealed_l1": "封板 L1",
    "depth5": "五档盘口",
    "pools": "股票池",
    "financials": "财务",
    "f10": "股票 F10",
    "ext_data": "扩展数据",
    "reference": "参考数据",
    "lineage": "血缘",
    "job_store": "任务库",
    "logs": "日志",
    "user_data": "用户数据",
    "control": "控制库",
    "operational_other": "其他运行文件",
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
    "ext_data": (
        "ext_data",
        "ext_fund_flow_bk",
        "ext_fund_flow_bk_daily",
        "ext_fund_flow_concept",
        "ext_fund_flow_concept_daily",
        "ext_fund_flow_stock",
        "ext_gn_ths",
        "ext_hy_ths",
    ),
    "f10": ("stock_margin_trading",),
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
        all_runs: list[SyncRun] = []
        retained_runs: list[SyncRun] = []
        for scanned_dataset_id, result in scan_results.items():
            run_status = _run_status(result)
            error_code, error_message = _scan_run_diagnostics(result, run_status)
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
                error_code=error_code,
                error_message=error_message,
            )
            all_runs.append(run)
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
                retained_runs.append(run)
                continue
            persisted.append((result.state, run, result.artifacts))
        for run in retained_runs:
            self.control_db.upsert_sync_run(run)
        retained_failure = bool(retained_runs)
        any_failed = retained_failure or any(
            _run_status(result) == "failed" for result in scan_results.values()
        )
        meta_updates["catalog_stale"] = {"value": any_failed}
        meta_updates["catalog_route_token"] = {"value": self._catalog_route_token()}
        if retained_failure and not persisted:
            # Nothing new to admit; keep the prior snapshot and mark it stale.
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
        storage = storage.model_copy(
            update={
                "categories": [
                    category.model_copy(
                        update={"title": _CATEGORY_TITLES.get(category.key, category.title)}
                    )
                    for category in storage.categories
                ]
            }
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

    def control_summary(self) -> ControlSummaryResponse:
        refreshed_meta = self.control_db.read_meta("catalog_refreshed_at")
        stale_meta = self.control_db.read_meta("catalog_stale")
        has_states = self.control_db.has_dataset_states_readonly()
        return ControlSummaryResponse(
            generated_at=_utc_now(),
            catalog_refreshed_at=refreshed_meta.get("value") if refreshed_meta else None,
            catalog_stale=not has_states or bool((stale_meta or {}).get("value")),
            source_health=self.control_db.read_source_health(),
            dataset_policies=self.control_db.list_dataset_policies(),
            sync_checkpoints=self.control_db.list_sync_checkpoints(),
            query_audits=self.control_db.list_query_audits(),
            unregistered_physical=self._unregistered_reference_data(),
        )

    def _unregistered_reference_data(self) -> list[UnregisteredPhysicalData]:
        reference_root = self.data_dir / "reference"
        if not reference_root.is_dir() or reference_root.is_symlink():
            return []
        registered = {
            parts[1]
            for definition in self.definitions
            for root in definition.roots
            if len(parts := Path(root).parts) >= 2 and parts[0] == "reference"
        }
        alerts: list[UnregisteredPhysicalData] = []
        try:
            directories = sorted(reference_root.iterdir(), key=lambda path: path.name)
        except OSError:
            return []
        for directory in directories:
            if (
                directory.name.startswith(".")
                or directory.name in registered
                or directory.is_symlink()
                or not directory.is_dir()
            ):
                continue
            file_count = 0
            total_bytes = 0
            latest_mtime: float | None = None
            for root, directories, files in os.walk(directory, followlinks=False):
                directories[:] = [
                    name
                    for name in directories
                    if not (Path(root) / name).is_symlink() and not name.startswith(".")
                ]
                for name in files:
                    path = Path(root) / name
                    if path.is_symlink() or name.startswith("."):
                        continue
                    try:
                        stat_result = path.stat()
                    except OSError:
                        continue
                    if not path.is_file():
                        continue
                    file_count += 1
                    total_bytes += stat_result.st_size
                    latest_mtime = max(latest_mtime or stat_result.st_mtime, stat_result.st_mtime)
            if file_count == 0:
                continue
            alerts.append(
                UnregisteredPhysicalData(
                    key=directory.name,
                    title=directory.name.replace("_", " "),
                    relative_path=f"reference/{directory.name}",
                    files=file_count,
                    bytes=total_bytes,
                    updated_at=(
                        datetime.fromtimestamp(latest_mtime, UTC).isoformat().replace("+00:00", "Z")
                        if latest_mtime is not None
                        else None
                    ),
                )
            )
        return alerts

    def compatibility_status(self) -> dict[str, Any]:
        states = {state.dataset_id: state for state in self.control_db.list_dataset_states()}
        route_fresh = self._catalog_route_fresh()
        return {
            "daily": self._table_stats(states.get("stock_daily")) if route_fresh else None,
            "enriched": (
                self._table_stats(states.get("stock_enriched"), enriched=True)
                if route_fresh else None
            ),
            "index_daily": self._table_stats(states.get("index_daily")) if route_fresh else None,
            "index_enriched": (
                self._table_stats(states.get("index_enriched"), enriched=True)
                if route_fresh else None
            ),
            "index_instruments": self._instrument_stats(states.get("index_instruments")),
            "etf_daily": self._table_stats(states.get("etf_daily")) if route_fresh else None,
            "etf_enriched": (
                self._table_stats(states.get("etf_enriched"), enriched=True)
                if route_fresh else None
            ),
            "etf_instruments": self._instrument_stats(states.get("etf_instruments")),
            "minute": self._table_stats(states.get("stock_minute")) if route_fresh else None,
            "adj_factor": self._table_stats(states.get("stock_adj_factor")) if route_fresh else None,
            "instruments": self._instrument_stats(states.get("stock_instruments")),
            "financials": self._financial_stats(states) if route_fresh else None,
            "storage": self._legacy_storage(),
            "next_pipeline_run": None,
            "next_instruments_run": None,
            "last_pipeline_run": None,
            "last_instruments_run": None,
            "checked_at": _utc_now(),
        }

    @staticmethod
    def _catalog_route_token() -> str:
        """Prefs-only token. Must not read parquet (compatibility_status is a hot path)."""
        try:
            from app.services.financial_sync import financial_write_route
            from app.services.kline_sync import daily_route, minute_route
            from app.tickflow.pools import pool_route

            return "|".join((
                daily_route() or "unresolved",
                minute_route() or "unresolved",
                financial_write_route() or "unresolved",
                pool_route() or "unresolved",
            ))
        except Exception:
            return "unresolved"

    def _catalog_route_fresh(self) -> bool:
        """False after a provider switch until the next catalog rescan.

        Last-scan leftover TickFlow coverage must not serve as current
        status. Missing token (pre-round-23 control DBs) stays visible so
        existing snapshots keep working until the next rescan.
        """
        scanned = self.control_db.get_meta("catalog_route_token") or {}
        stored = scanned.get("value")
        if not stored:
            return True
        return stored == self._catalog_route_token()

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
        if definition.coverage_policy == "on_demand":
            return None
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


def lineage_quality_details(lineage: Sequence[Any]) -> str | None:
    """Explain a degraded catalog snapshot from current lineage records."""
    counts: dict[str, int] = {}
    sources: dict[str, int] = {}
    for item in lineage:
        if isinstance(item, Mapping):
            status = str(item.get("quality_status") or "unknown")
            source = str(item.get("source") or "").strip()
        else:
            status = str(getattr(item, "quality_status", None) or "unknown")
            source = str(getattr(item, "source", None) or "").strip()
        counts[status] = counts.get(status, 0) + 1
        if status in {"degraded", "failed", "unknown"} and source:
            sources[source] = sources.get(source, 0) + 1
    if not counts:
        return None
    parts: list[str] = []
    if "legacy_local_artifact" in sources:
        parts.append("这些是补录的 legacy lineage，目录扫描因此降级，不代表当日正式日 K 丢失")
    parts.append(
        "当前分区 lineage 质量: "
        + "、".join(f"{status} {count} 条" for status, count in sorted(counts.items()))
    )
    if sources:
        parts.append(
            "降级/未知来源: "
            + "、".join(f"{source} {count} 条" for source, count in sorted(sources.items()))
        )
    return "；".join(parts)


def _scan_run_diagnostics(
    result: DatasetScanResult, run_status: str
) -> tuple[str | None, str | None]:
    if run_status == "succeeded":
        return None, None
    scan_errors = [
        str(item).strip()
        for item in result.state.payload.get("scan_errors", [])
        if str(item).strip()
    ]
    if scan_errors:
        code = (
            "catalog_quality_failed" if run_status == "failed" else "catalog_quality_degraded"
        )
        return code, "; ".join(scan_errors)[:500]
    if run_status == "degraded":
        details = lineage_quality_details(result.lineage) or (
            "目录扫描因 lineage 质量降级，但未记录分区级 scan_errors"
        )
        return "catalog_quality_degraded", details[:500]
    return "catalog_quality_failed", None


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
