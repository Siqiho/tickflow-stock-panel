"""Explicit local-file scanner for catalog refreshes."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .definitions import DATASET_DEFINITIONS, DatasetDefinition
from .models import (
    ArtifactRecord,
    DatasetState,
    LineageSummary,
    MarketCoverage,
    StorageBreakdown,
    StorageCategory,
)

_MARKETS = ("SH", "SZ", "BJ", "OTHER")
_MAX_SCAN_ERRORS = 20
_OPERATIONAL_CATEGORIES = {
    "lineage": "Lineage",
    "job_store": "Job store",
    "logs": "Logs",
    "user_data": "User data",
    "control": "SQLite control files",
    "operational_other": "Other operational files",
}
_MANAGED_TITLES = {
    "stocks": "Stocks",
    "etfs": "ETFs",
    "indices": "Indices",
    "quote_snapshot": "Quote snapshot",
    "sealed_l1": "Sealed L1",
    "depth5": "True depth5",
    "pools": "Pools",
    "financials": "Financials",
    "ext_data": "External data",
}


@dataclass(frozen=True)
class DatasetScanResult:
    state: DatasetState
    artifacts: tuple[ArtifactRecord, ...]
    coverage: tuple[MarketCoverage, ...]
    lineage: tuple[LineageSummary, ...]
    depth5_available: bool = False


@dataclass(frozen=True)
class CatalogScanSnapshot:
    datasets: dict[str, DatasetScanResult]
    storage: StorageBreakdown
    dataset_storage: dict[str, dict[str, int]]
    refreshed_at: str


@dataclass(frozen=True)
class _FileSnapshot:
    path: Path
    relative: PurePosixPath
    bytes: int
    published_at: str
    device: int
    inode: int
    mtime_ns: int


@dataclass(frozen=True)
class _ParquetFacts:
    columns: tuple[str, ...]
    schema: pa.Schema
    row_count: int
    symbols: tuple[str, ...]
    times: tuple[str, ...]
    named_count: int
    sha256: str


class CatalogScanner:
    def __init__(
        self,
        data_dir: Path,
        definitions: tuple[DatasetDefinition, ...] = DATASET_DEFINITIONS,
    ) -> None:
        self.data_dir = Path(data_dir)
        self._resolved_data_dir = self.data_dir.resolve(strict=False)
        self.definitions = tuple(definitions)
        self._by_id = {
            definition.descriptor.dataset_id: definition for definition in self.definitions
        }

    def scan_all(self, run_ids: Mapping[str, str]) -> CatalogScanSnapshot:
        missing = sorted(set(self._by_id) - set(run_ids))
        if missing:
            raise ValueError(f"missing scan run IDs: {', '.join(missing)}")
        refreshed_at = _utc_now()
        files = self._walk_snapshot(self.data_dir)
        fact_cache: dict[Path, _ParquetFacts | Exception] = {}
        owned: dict[str, list[_FileSnapshot]] = {dataset_id: [] for dataset_id in self._by_id}
        category_counts = self._empty_category_counts()

        for file in files:
            dataset_id = self._owner_for_file(file, fact_cache)
            if dataset_id is None:
                category = self._operational_category(file.relative)
            else:
                owned[dataset_id].append(file)
                category = self._by_id[dataset_id].storage_category
            category_counts[category]["bytes"] += file.bytes
            category_counts[category]["files"] += 1

        results = {
            dataset_id: self._scan_files(
                definition,
                tuple(owned[dataset_id]),
                files,
                run_ids[dataset_id],
                refreshed_at,
                fact_cache,
                expected_by_market=None,
            )
            for dataset_id, definition in self._by_id.items()
        }
        results = self._apply_full_scan_expectations(results)
        dataset_storage = {
            dataset_id: {
                "bytes": sum(file.bytes for file in dataset_files),
                "files": len(dataset_files),
            }
            for dataset_id, dataset_files in owned.items()
        }
        storage = self._storage_breakdown(category_counts)
        if storage.total_bytes != sum(file.bytes for file in files):
            raise RuntimeError("catalog scan byte invariant failed")
        return CatalogScanSnapshot(
            datasets=results,
            storage=storage,
            dataset_storage=dataset_storage,
            refreshed_at=refreshed_at,
        )

    def scan_dataset(
        self,
        dataset_id: str,
        run_id: str,
        *,
        expected_by_market: Mapping[str, int] | None = None,
    ) -> DatasetScanResult:
        try:
            definition = self._by_id[dataset_id]
        except KeyError as error:
            raise KeyError(f"unknown dataset_id: {dataset_id}") from error
        refreshed_at = _utc_now()
        files_by_path: dict[PurePosixPath, _FileSnapshot] = {}
        for root in definition.roots:
            root_path = self.data_dir.joinpath(*PurePosixPath(root).parts)
            if root_path.exists():
                for file in self._walk_snapshot(root_path):
                    files_by_path[file.relative] = file
        lineage_files: dict[PurePosixPath, _FileSnapshot] = {}
        for lineage_root in self._lineage_roots(definition):
            if lineage_root.exists():
                for file in self._walk_snapshot(lineage_root):
                    lineage_files[file.relative] = file

        fact_cache: dict[Path, _ParquetFacts | Exception] = {}
        owned = tuple(
            file
            for file in sorted(files_by_path.values(), key=lambda item: item.relative.as_posix())
            if self._owner_for_file(file, fact_cache) == dataset_id
        )
        return self._scan_files(
            definition,
            owned,
            tuple(lineage_files.values()),
            run_id,
            refreshed_at,
            fact_cache,
            expected_by_market=expected_by_market,
        )

    def _walk_snapshot(self, root: Path) -> tuple[_FileSnapshot, ...]:
        if not self._is_safe_directory(root):
            return ()
        files: list[_FileSnapshot] = []
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            directory_path = Path(directory)
            if not self._is_safe_directory(directory_path):
                dirnames.clear()
                continue
            dirnames[:] = sorted(
                dirname for dirname in dirnames if self._is_safe_directory(directory_path / dirname)
            )
            filenames.sort()
            for filename in filenames:
                path = directory_path / filename
                try:
                    file_stat = path.stat(follow_symlinks=False)
                except OSError:
                    continue
                if not stat.S_ISREG(file_stat.st_mode):
                    continue
                if not self._resolves_within_data_dir(path):
                    continue
                try:
                    relative = PurePosixPath(path.relative_to(self.data_dir).as_posix())
                except ValueError as error:
                    raise ValueError(f"scan root is outside data_dir: {root}") from error
                files.append(
                    _FileSnapshot(
                        path=path,
                        relative=relative,
                        bytes=file_stat.st_size,
                        published_at=datetime.fromtimestamp(file_stat.st_mtime, UTC)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        device=file_stat.st_dev,
                        inode=file_stat.st_ino,
                        mtime_ns=file_stat.st_mtime_ns,
                    )
                )
        return tuple(files)

    def _is_safe_directory(self, path: Path) -> bool:
        try:
            mode = path.lstat().st_mode
        except OSError:
            return False
        return (
            stat.S_ISDIR(mode) and not stat.S_ISLNK(mode) and self._resolves_within_data_dir(path)
        )

    def _resolves_within_data_dir(self, path: Path) -> bool:
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            return False
        return resolved == self._resolved_data_dir or resolved.is_relative_to(
            self._resolved_data_dir
        )

    def _owner_for_file(
        self,
        file: _FileSnapshot,
        fact_cache: dict[Path, _ParquetFacts | Exception],
    ) -> str | None:
        matches: list[DatasetDefinition] = []
        for definition in self.definitions:
            if any(
                _has_path_prefix(file.relative.parts, PurePosixPath(root).parts)
                for root in definition.roots
            ):
                matches.append(definition)
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0].descriptor.dataset_id
        if {item.descriptor.dataset_id for item in matches} != {"sealed_l1", "depth5"}:
            raise RuntimeError(f"ambiguous dataset ownership: {file.relative.as_posix()}")
        return "depth5" if self._has_true_depth_schema(file, fact_cache) else "sealed_l1"

    def _has_true_depth_schema(
        self,
        file: _FileSnapshot,
        fact_cache: dict[Path, _ParquetFacts | Exception],
    ) -> bool:
        if file.path.suffix.lower() != ".parquet":
            return False
        facts = self._parquet_facts(file, self._by_id["depth5"], fact_cache)
        if isinstance(facts, Exception):
            return False
        normalized = {column.lower() for column in facts.columns}
        if {"bid_price5", "ask_price5"} <= normalized or {
            "bid_price_5",
            "ask_price_5",
        } <= normalized:
            return True
        if not {"bid_prices", "ask_prices"} <= normalized:
            return False
        try:
            return all(
                pa.types.is_list(facts.schema.field(column).type)
                or pa.types.is_large_list(facts.schema.field(column).type)
                or pa.types.is_fixed_size_list(facts.schema.field(column).type)
                for column in ("bid_prices", "ask_prices")
            )
        except (KeyError, pa.ArrowException):
            return False

    def _scan_files(
        self,
        definition: DatasetDefinition,
        files: tuple[_FileSnapshot, ...],
        all_snapshot_files: tuple[_FileSnapshot, ...],
        run_id: str,
        refreshed_at: str,
        fact_cache: dict[Path, _ParquetFacts | Exception],
        *,
        expected_by_market: Mapping[str, int] | None,
    ) -> DatasetScanResult:
        artifacts: list[ArtifactRecord] = []
        errors: list[str] = []
        symbols: set[str] = set()
        times: set[str] = set()
        fields: set[str] = set()
        named_count = 0
        row_count = 0
        material_files = tuple(
            file
            for file in sorted(files, key=lambda item: item.relative.as_posix())
            if file.path.suffix.lower() == ".parquet"
            and file.path.name not in definition.ignored_parquet_names
        )
        fatal_errors: list[str] = []
        for file in material_files:
            facts = self._parquet_facts(file, definition, fact_cache)
            if isinstance(facts, Exception):
                fatal_errors.append(self._bounded_error(file, facts))
                continue
            schema_error = self._schema_error(definition, facts.columns)
            if schema_error is not None:
                fatal_errors.append(f"{file.relative.as_posix()}: {schema_error}")
                continue
            row_count += facts.row_count
            symbols.update(facts.symbols)
            times.update(facts.times)
            fields.update(facts.columns)
            named_count += facts.named_count
            artifacts.append(
                ArtifactRecord(
                    run_id=run_id,
                    dataset_id=definition.descriptor.dataset_id,
                    path=file.relative.as_posix(),
                    sha256=facts.sha256,
                    row_count=facts.row_count,
                    bytes=file.bytes,
                    partition_value=self._partition_value(file.relative, definition.partition_key),
                    published_at=file.published_at,
                )
            )

        lineage, lineage_errors = self._read_lineage(definition, all_snapshot_files)
        fatal_errors.extend(lineage_errors)
        artifact_paths = {artifact.path for artifact in artifacts}
        lineage = tuple(item for item in lineage if item.artifact_path in artifact_paths)
        unit_version, unit_errors, unit_failed = self._admit_units(
            definition,
            tuple(artifacts),
            lineage,
        )
        errors.extend(fatal_errors)
        errors.extend(unit_errors)
        errors = sorted(set(errors))[:_MAX_SCAN_ERRORS]
        coverage = self._coverage(symbols, expected_by_market)
        quality_status = self._quality_status(
            bool(artifacts),
            lineage,
            has_fatal_errors=bool(fatal_errors) or unit_failed,
            units_verified=(definition.unit_policy == "reference" or not unit_errors),
        )
        depth5_available = (
            definition.descriptor.dataset_id == "depth5"
            and bool(artifacts)
            and quality_status in {"healthy", "degraded"}
        )
        payload = {
            "file_count": len(material_files),
            "field_count": len(fields),
            "trading_days": len({_calendar_day(value) for value in times}),
            "named_count": named_count,
            "coverage": [item.model_dump(mode="json") for item in coverage],
            "lineage": [item.model_dump(mode="json") for item in lineage],
            "scan_errors": errors,
            "depth5_available": depth5_available,
        }
        expected_total = (
            sum(max(0, int(expected_by_market.get(market, 0))) for market in _MARKETS)
            if expected_by_market is not None
            else None
        )
        state = DatasetState(
            dataset_id=definition.descriptor.dataset_id,
            schema_version=definition.descriptor.schema_version,
            unit_version=unit_version,
            quality_status=quality_status,
            row_count=row_count,
            symbol_count=len(symbols),
            expected_symbol_count=expected_total,
            earliest_time=min(times) if times else None,
            latest_time=max(times) if times else None,
            managed_bytes=sum(file.bytes for file in files),
            last_run_id=run_id,
            updated_at=refreshed_at,
            payload=payload,
        )
        return DatasetScanResult(
            state=state,
            artifacts=tuple(artifacts),
            coverage=coverage,
            lineage=lineage,
            depth5_available=depth5_available,
        )

    def _parquet_facts(
        self,
        file: _FileSnapshot,
        definition: DatasetDefinition,
        cache: dict[Path, _ParquetFacts | Exception],
    ) -> _ParquetFacts | Exception:
        if file.path in cache:
            cached = cache[file.path]
            if isinstance(cached, Exception):
                return cached
            required = {
                column
                for column in (definition.symbol_column, definition.time_column, "name")
                if column
            }
            if required <= set(cached.columns) or not required:
                return cached
        try:
            with file.path.open("rb") as handle:
                before = os.fstat(handle.fileno())
                self._assert_same_file(file, before)
                parquet = pq.ParquetFile(handle)
                schema = parquet.schema_arrow
                columns = tuple(schema.names)
                requested = (
                    definition.symbol_column,
                    definition.time_column,
                    "name",
                )
                selected = [column for column in requested if column and column in columns]
                table = parquet.read(columns=list(dict.fromkeys(selected))) if selected else None
                row_count = parquet.metadata.num_rows
                handle.seek(0)
                digest = _sha256_handle(handle)
                after = os.fstat(handle.fileno())
                self._assert_same_file(file, after)
                current = file.path.stat(follow_symlinks=False)
                self._assert_same_file(file, current)
            symbols = _column_strings(table, definition.symbol_column)
            times = _column_strings(table, definition.time_column)
            names = _column_strings(table, "name")
            facts = _ParquetFacts(
                columns=columns,
                schema=schema,
                row_count=row_count,
                symbols=tuple(symbols),
                times=tuple(times),
                named_count=sum(bool(value.strip()) for value in names),
                sha256=digest,
            )
            cache[file.path] = facts
            return facts
        except (OSError, pa.ArrowException, ValueError) as error:
            cache[file.path] = error
            return error

    @staticmethod
    def _assert_same_file(file: _FileSnapshot, observed: os.stat_result) -> None:
        identity = (
            observed.st_dev,
            observed.st_ino,
            observed.st_size,
            observed.st_mtime_ns,
        )
        expected = (file.device, file.inode, file.bytes, file.mtime_ns)
        if identity != expected:
            raise OSError("file changed during scan")

    @staticmethod
    def _schema_error(
        definition: DatasetDefinition,
        columns: tuple[str, ...],
    ) -> str | None:
        if definition.schema_policy == "opaque_dynamic":
            return None if columns else "opaque parquet schema has no columns"
        available = set(columns)
        required_sets = (
            definition.required_column_sets
            if definition.required_column_sets
            else (definition.required_columns,)
        )
        if any(set(required) <= available for required in required_sets):
            return None
        required = min(required_sets, key=lambda item: len(set(item) - available))
        missing = sorted(set(required) - available)
        return f"missing required columns: {', '.join(missing)}"

    @staticmethod
    def _admit_units(
        definition: DatasetDefinition,
        artifacts: tuple[ArtifactRecord, ...],
        lineage: tuple[LineageSummary, ...],
    ) -> tuple[str, list[str], bool]:
        if not artifacts:
            return "unknown", [], False
        if definition.unit_policy == "reference":
            return definition.descriptor.unit_version, [], False
        by_artifact: dict[str, list[LineageSummary]] = {}
        for summary in lineage:
            if summary.artifact_path is not None:
                by_artifact.setdefault(summary.artifact_path, []).append(summary)
        errors: list[str] = []
        failed = False
        for artifact in artifacts:
            matches = by_artifact.get(artifact.path, [])
            if not matches:
                errors.append(f"{artifact.path}: matching lineage is missing")
                continue
            mismatches = sorted(
                {
                    summary.unit_version
                    for summary in matches
                    if summary.unit_version != definition.descriptor.unit_version
                }
            )
            if mismatches:
                failed = True
                errors.append(
                    f"{artifact.path}: unit_version mismatch: "
                    f"expected {definition.descriptor.unit_version}, got {', '.join(mismatches)}"
                )
        if errors:
            return "unknown", errors, failed
        return definition.descriptor.unit_version, [], False

    def _read_lineage(
        self,
        definition: DatasetDefinition,
        files: tuple[_FileSnapshot, ...],
    ) -> tuple[tuple[LineageSummary, ...], list[str]]:
        prefixes = {
            ("lineage", *PurePosixPath(identifier).parts)
            for identifier in self._lineage_ids(definition)
        }
        summaries: list[LineageSummary] = []
        errors: list[str] = []
        for file in sorted(files, key=lambda item: item.relative.as_posix()):
            if file.path.suffix.lower() != ".json" or not any(
                _has_path_prefix(file.relative.parts, prefix) for prefix in prefixes
            ):
                continue
            try:
                payload = json.loads(file.path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("lineage sidecar must be an object")
                source = payload.get("source")
                unit_version = payload.get("unit_version")
                if not isinstance(source, str) or not source.strip():
                    raise ValueError("lineage source is missing")
                if not isinstance(unit_version, str) or not unit_version.strip():
                    raise ValueError("lineage unit_version is missing")
                artifact_path = payload.get("target_artifact") or payload.get("artifact")
                if artifact_path is not None:
                    artifact_path = self._canonical_artifact_path(str(artifact_path))
                summaries.append(
                    LineageSummary(
                        run_id=_optional_text(
                            payload.get("run_id") or payload.get("source_job_id")
                        ),
                        source=source.strip(),
                        fetched_at=_optional_text(payload.get("fetched_at")),
                        unit_version=unit_version.strip(),
                        quality_status=_quality_word(
                            payload.get("quality_status") or payload.get("quality")
                        ),
                        scope=_optional_text(payload.get("scope")),
                        artifact_path=artifact_path,
                        row_count=_optional_nonnegative_int(payload.get("row_count")),
                    )
                )
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                errors.append(self._bounded_error(file, error))
        summaries.sort(
            key=lambda item: (
                item.fetched_at or "",
                item.source,
                item.artifact_path or "",
                item.run_id or "",
            )
        )
        return tuple(summaries), errors

    def _lineage_ids(self, definition: DatasetDefinition) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                (
                    definition.descriptor.dataset_id,
                    *definition.lineage_ids,
                    *definition.roots,
                )
            )
        )

    def _lineage_roots(self, definition: DatasetDefinition) -> tuple[Path, ...]:
        return tuple(
            self.data_dir / "lineage" / Path(*PurePosixPath(identifier).parts)
            for identifier in self._lineage_ids(definition)
        )

    def _canonical_artifact_path(self, value: str) -> str:
        path = Path(value)
        if path.is_absolute():
            try:
                return path.relative_to(self.data_dir).as_posix()
            except ValueError:
                return path.name
        return PurePosixPath(value).as_posix()

    @staticmethod
    def _coverage(
        symbols: set[str], expected_by_market: Mapping[str, int] | None
    ) -> tuple[MarketCoverage, ...]:
        actual = {market: 0 for market in _MARKETS}
        for symbol in symbols:
            actual[_symbol_market(symbol)] += 1
        coverage: list[MarketCoverage] = []
        for market in _MARKETS:
            expected = (
                max(0, int(expected_by_market.get(market, 0)))
                if expected_by_market is not None
                else None
            )
            ratio = None if expected in (None, 0) else min(actual[market] / expected, 1.0)
            coverage.append(
                MarketCoverage(
                    market=market,
                    symbol_count=actual[market],
                    expected_symbol_count=expected,
                    ratio=ratio,
                )
            )
        return tuple(coverage)

    def _apply_full_scan_expectations(
        self, results: dict[str, DatasetScanResult]
    ) -> dict[str, DatasetScanResult]:
        instrument_ids = {
            "stock": "stock_instruments",
            "etf": "etf_instruments",
            "index": "index_instruments",
        }
        expected = {
            asset_type: {item.market: item.symbol_count for item in results[dataset_id].coverage}
            for asset_type, dataset_id in instrument_ids.items()
        }
        updated: dict[str, DatasetScanResult] = {}
        for dataset_id, result in results.items():
            definition = self._by_id[dataset_id]
            asset_types = definition.descriptor.asset_types
            expected_by_market = expected.get(asset_types[0]) if len(asset_types) == 1 else None
            if expected_by_market is None:
                updated[dataset_id] = result
                continue
            coverage = tuple(
                MarketCoverage(
                    market=item.market,
                    symbol_count=item.symbol_count,
                    expected_symbol_count=expected_by_market[item.market],
                    ratio=(
                        None
                        if expected_by_market[item.market] == 0
                        else min(item.symbol_count / expected_by_market[item.market], 1.0)
                    ),
                )
                for item in result.coverage
            )
            payload = dict(result.state.payload)
            payload["coverage"] = [item.model_dump(mode="json") for item in coverage]
            state = result.state.model_copy(
                update={
                    "expected_symbol_count": sum(expected_by_market.values()),
                    "payload": payload,
                }
            )
            updated[dataset_id] = DatasetScanResult(
                state=state,
                artifacts=result.artifacts,
                coverage=coverage,
                lineage=result.lineage,
                depth5_available=result.depth5_available,
            )
        return updated

    @staticmethod
    def _quality_status(
        has_readable_parquet: bool,
        lineage: tuple[LineageSummary, ...],
        *,
        has_fatal_errors: bool,
        units_verified: bool,
    ) -> str:
        if has_fatal_errors:
            return "failed"
        statuses = {item.quality_status for item in lineage}
        if "failed" in statuses:
            return "failed"
        if "degraded" in statuses:
            return "degraded"
        if has_readable_parquet and units_verified:
            return "healthy"
        return "unknown"

    @staticmethod
    def _partition_value(relative: PurePosixPath, partition_key: str | None) -> str | None:
        if partition_key is None:
            return None
        prefix = f"{partition_key}="
        for part in relative.parts:
            if part.startswith(prefix):
                return part[len(prefix) :]
        return None

    @staticmethod
    def _bounded_error(file: _FileSnapshot, error: Exception) -> str:
        detail = " ".join(str(error).split())[:160]
        return f"{file.relative.as_posix()}: {type(error).__name__}: {detail}"

    def _empty_category_counts(self) -> dict[str, dict[str, int]]:
        return {
            key: {"bytes": 0, "files": 0} for key in (*_MANAGED_TITLES, *_OPERATIONAL_CATEGORIES)
        }

    @staticmethod
    def _operational_category(relative: PurePosixPath) -> str:
        first = relative.parts[0] if relative.parts else ""
        return (
            first
            if first in _OPERATIONAL_CATEGORIES and first != "operational_other"
            else "operational_other"
        )

    @staticmethod
    def _storage_breakdown(counts: dict[str, dict[str, int]]) -> StorageBreakdown:
        categories = [
            StorageCategory(
                key=key,
                title=(
                    _MANAGED_TITLES[key] if key in _MANAGED_TITLES else _OPERATIONAL_CATEGORIES[key]
                ),
                kind="managed" if key in _MANAGED_TITLES else "operational",
                bytes=value["bytes"],
                files=value["files"],
            )
            for key, value in counts.items()
        ]
        managed = sum(item.bytes for item in categories if item.kind == "managed")
        operational = sum(item.bytes for item in categories if item.kind == "operational")
        return StorageBreakdown(
            managed_data_bytes=managed,
            operational_bytes=operational,
            total_bytes=managed + operational,
            categories=categories,
        )


def _has_path_prefix(parts: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    return len(parts) >= len(prefix) and parts[: len(prefix)] == prefix


def _sha256_handle(handle) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def _column_strings(table: pa.Table | None, column: str | None) -> list[str]:
    if table is None or column is None or column not in table.column_names:
        return []
    values: list[str] = []
    for value in table[column].to_pylist():
        if value is None:
            continue
        if isinstance(value, (datetime, date)):
            values.append(value.isoformat())
        else:
            values.append(str(value))
    return values


def _symbol_market(symbol: str) -> str:
    suffix = symbol.strip().upper().rsplit(".", 1)
    return suffix[-1] if len(suffix) == 2 and suffix[-1] in {"SH", "SZ", "BJ"} else "OTHER"


def _calendar_day(value: str) -> str:
    return value[:10]


def _quality_word(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "fail" in text or "error" in text:
        return "failed"
    if "degrad" in text or "warn" in text:
        return "degraded"
    if text in {"healthy", "pass", "passed", "success", "succeeded"}:
        return "healthy"
    return "unknown"


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
