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
_FILE_CHANGED = "file changed during scan"
_PARQUET_READ_ATTEMPTS = 3
_OPERATIONAL_CATEGORIES = {
    "lineage": "血缘",
    "job_store": "任务库",
    "logs": "日志",
    "user_data": "用户数据",
    "control": "控制库",
    "operational_other": "其他运行文件",
}
_MANAGED_TITLES = {
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


_DAILY_DATASETS = {
    "stock_daily",
    "stock_enriched",
    "index_daily",
    "index_enriched",
    "etf_daily",
    "etf_enriched",
    "valuation_daily",
    "limit_up_events",
}
_MINUTE_DATASETS = {"stock_minute", "etf_minute"}
_ADJ_DATASETS = {"stock_adj_factor", "etf_adj_factor"}
_FINANCIAL_DATASETS = {
    "financial_metrics",
    "financial_income",
    "financial_balance_sheet",
    "financial_cash_flow",
    "financial_shares",
}
_DEPTH_DATASETS = {"depth5", "sealed_l1"}
_POOL_DATASETS = {"pools"}
_QUOTE_DATASETS = {"quote_snapshot"}
_MEMBERSHIP_DATASETS = {"index_membership_history"}
_CORP_DATASETS = {"corporate_actions"}
_INSTRUMENT_DATASETS = {"stock_instruments", "etf_instruments", "index_instruments"}


def _route_column_usable(path: Path, route: str, usable_fn) -> bool:
    import polars as pl

    names = pl.read_parquet_schema(path).names()
    if "route" not in names:
        return route in {"tickflow", "public"}
    return usable_fn(pl.read_parquet(path, columns=["route"]), route)


def _catalog_route_token(dataset_id: str) -> str:
    """Route token used to prefer tagged leftover files in one directory."""
    try:
        if dataset_id in _DAILY_DATASETS:
            from app.services.kline_sync import daily_route

            return daily_route()
        if dataset_id in _MINUTE_DATASETS:
            from app.services.kline_sync import minute_route

            return minute_route()
        if dataset_id in _ADJ_DATASETS or dataset_id in _CORP_DATASETS:
            from app.services.kline_sync import adj_route

            return adj_route()
        if dataset_id in _FINANCIAL_DATASETS:
            from app.services.financial_sync import financial_write_route

            return financial_write_route()
        if dataset_id in _DEPTH_DATASETS:
            from app.services.depth_service import depth_route

            return depth_route()
        if dataset_id in _POOL_DATASETS or dataset_id in _MEMBERSHIP_DATASETS:
            from app.tickflow.pools import pool_route

            return pool_route()
        if dataset_id in _QUOTE_DATASETS:
            from app.services.quote_service import realtime_route

            return realtime_route()
        if dataset_id in _INSTRUMENT_DATASETS:
            from app.services.instrument_sync import instrument_route

            return instrument_route()
    except Exception:
        return "unresolved"
    return "tickflow"


def _catalog_file_usable(dataset_id: str, path: Path) -> bool:
    """Current-route parquet only. Storage walks still see leftover files.

    Leftover TickFlow / public still see untagged partitions. Custom /
    unresolved never reuse leftover TickFlow as current coverage after a
    rescan. Instruments follow the daily route. Same-directory untagged
    extras beside tagged leftover are filtered later by
    :func:`_catalog_material_files`. Known leftover TickFlow-routed
    datasets do not leftover-serve after a custom or unresolved daily.
    Ext extras stay visible.
    """
    try:
        if dataset_id in (
            _DAILY_DATASETS
            | _MINUTE_DATASETS
            | _ADJ_DATASETS
            | _FINANCIAL_DATASETS
            | _DEPTH_DATASETS
            | _POOL_DATASETS
            | _QUOTE_DATASETS
            | _MEMBERSHIP_DATASETS
            | _CORP_DATASETS
            | _INSTRUMENT_DATASETS
        ):
            token = _catalog_route_token(dataset_id)
            if token == "tickflow":
                from app.services.kline_sync import leftover_tickflow_follow_daily

                if not leftover_tickflow_follow_daily():
                    return False
        if dataset_id in _DAILY_DATASETS:
            from app.services.kline_sync import daily_partition_usable

            return daily_partition_usable(path)
        if dataset_id in _MINUTE_DATASETS:
            from app.services.kline_sync import minute_partition_usable

            return minute_partition_usable(path)
        if dataset_id in _ADJ_DATASETS:
            from app.services.kline_sync import adj_cache_usable, adj_route

            return _route_column_usable(path, adj_route(), adj_cache_usable)
        if dataset_id in _FINANCIAL_DATASETS:
            from app.services.financial_sync import financial_cache_usable, financial_write_route

            return _route_column_usable(path, financial_write_route(), financial_cache_usable)
        if dataset_id in _DEPTH_DATASETS:
            from app.services.depth_service import depth_cache_usable, depth_route

            return _route_column_usable(path, depth_route(), depth_cache_usable)
        if dataset_id in _POOL_DATASETS or dataset_id in _MEMBERSHIP_DATASETS:
            from app.services.reference_derived import _pool_snapshot_usable
            from app.tickflow.pools import pool_route
            import polars as pl

            return _pool_snapshot_usable(pl.read_parquet(path), pool_route())
        if dataset_id in _QUOTE_DATASETS:
            from app.services.quote_service import quote_snapshot_partition_usable

            return quote_snapshot_partition_usable(path)
        if dataset_id in _CORP_DATASETS:
            from app.services.kline_sync import adj_cache_usable, adj_route

            return _route_column_usable(path, adj_route(), adj_cache_usable)
        if dataset_id in _INSTRUMENT_DATASETS:
            from app.services.instrument_sync import instrument_cache_usable, instrument_route
            import polars as pl

            expected = instrument_route()
            if expected == "unresolved":
                return False
            try:
                names = pl.read_parquet_schema(path).names()
                if "route" not in names:
                    return expected == "tickflow"
                return instrument_cache_usable(
                    pl.read_parquet(path, columns=["route"]), expected,
                )
            except Exception:
                # Leftover TickFlow catalog stays fail-loud on unreadable leftover.
                return expected == "tickflow"
    except Exception:
        return False
    return True


def _catalog_material_files(
    definition: DatasetDefinition,
    files: tuple[_FileSnapshot, ...],
) -> tuple[_FileSnapshot, ...]:
    """Current-route parquet only. Same-dir untagged extras stay out.

    Per-file :func:`_catalog_file_usable` still treats leftover TickFlow
    untagged files as current. Same-directory untagged extras beside a
    tagged leftover used to concat-mix into catalog coverage.
    Unreadable tagged leftover stays in so catalog / get_minute fail-loud.
    Untagged-only leftover TickFlow still serves.
    """
    parquet = [
        file
        for file in sorted(files, key=lambda item: item.relative.as_posix())
        if file.path.suffix.lower() == ".parquet"
        and file.path.name not in definition.ignored_parquet_names
        and _catalog_file_usable(definition.descriptor.dataset_id, file.path)
    ]
    route = _catalog_route_token(definition.descriptor.dataset_id)
    from app.services.kline_sync import prefer_tagged_route_files

    grouped: dict[Path, list[_FileSnapshot]] = {}
    for file in parquet:
        grouped.setdefault(file.path.parent, []).append(file)
    out: list[_FileSnapshot] = []
    for group in grouped.values():
        preferred = set(prefer_tagged_route_files([item.path for item in group], route))
        out.extend(item for item in group if item.path in preferred)
    return tuple(sorted(out, key=lambda item: item.relative.as_posix()))


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
                files.append(self._file_snapshot(path, relative, file_stat))
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
        scored: list[tuple[int, DatasetDefinition]] = []
        for definition in self.definitions:
            matching_len = 0
            for root in definition.roots:
                parts = PurePosixPath(root).parts
                if _has_path_prefix(file.relative.parts, parts):
                    matching_len = max(matching_len, len(parts))
            if matching_len:
                scored.append((matching_len, definition))
        if not scored:
            return None
        longest = max(length for length, _definition in scored)
        winners = [definition for length, definition in scored if length == longest]
        if len(winners) == 1:
            return winners[0].descriptor.dataset_id
        if {item.descriptor.dataset_id for item in winners} == {"sealed_l1", "depth5"}:
            return "depth5" if self._has_true_depth_schema(file, fact_cache) else "sealed_l1"
        raise RuntimeError(f"ambiguous dataset ownership: {file.relative.as_posix()}")

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
        material_files = _catalog_material_files(definition, files)
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
        current_lineage = self._current_artifact_lineage(tuple(artifacts), lineage)
        unit_version, unit_errors, unit_failed = self._admit_units(
            definition,
            tuple(artifacts),
            current_lineage,
        )
        errors.extend(fatal_errors)
        errors.extend(unit_errors)
        errors = sorted(set(errors))[:_MAX_SCAN_ERRORS]
        coverage = self._coverage(symbols, expected_by_market)
        quality_status = self._quality_status(
            bool(artifacts),
            current_lineage,
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
        current = file
        last_error: Exception | None = None
        for _attempt in range(_PARQUET_READ_ATTEMPTS):
            try:
                with current.path.open("rb") as handle:
                    before = os.fstat(handle.fileno())
                    self._assert_same_file(current, before)
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
                    self._assert_same_file(current, after)
                    latest = current.path.stat(follow_symlinks=False)
                    self._assert_same_file(current, latest)
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
                last_error = error
                if _is_file_changed(error):
                    refreshed = self._refresh_file_snapshot(current)
                    if refreshed is not None:
                        current = refreshed
                        continue
                cache[file.path] = error
                return error
        assert last_error is not None
        cache[file.path] = last_error
        return last_error

    @staticmethod
    def _file_snapshot(path: Path, relative: PurePosixPath, file_stat: os.stat_result) -> _FileSnapshot:
        return _FileSnapshot(
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

    def _refresh_file_snapshot(self, file: _FileSnapshot) -> _FileSnapshot | None:
        try:
            file_stat = file.path.stat(follow_symlinks=False)
        except OSError:
            return None
        if not stat.S_ISREG(file_stat.st_mode):
            return None
        return self._file_snapshot(file.path, file.relative, file_stat)

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
            raise OSError(_FILE_CHANGED)

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
                artifact_path = payload.get("target_artifact") or payload.get("artifact_path") or payload.get("artifact")
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

    @staticmethod
    def _current_artifact_lineage(
        artifacts: tuple[ArtifactRecord, ...],
        lineage: tuple[LineageSummary, ...],
    ) -> tuple[LineageSummary, ...]:
        """Choose the lineage record that describes each current artifact.

        Several datasets publish by atomically replacing one stable path. Their
        lineage history therefore contains records for older byte/row versions
        of the same path. Unit admission must not let those superseded records
        invalidate the current file. Prefer an exact current row-count match;
        fall back only to legacy records that predate row-count capture.
        """
        by_artifact: dict[str, list[LineageSummary]] = {}
        for summary in lineage:
            if summary.artifact_path is not None:
                by_artifact.setdefault(summary.artifact_path, []).append(summary)

        selected: list[LineageSummary] = []
        for artifact in artifacts:
            candidates = by_artifact.get(artifact.path, [])
            exact = [item for item in candidates if item.row_count == artifact.row_count]
            legacy = [item for item in candidates if item.row_count is None]
            current = exact or legacy
            if not current:
                continue
            selected.append(max(current, key=_lineage_recency_key))
        return tuple(
            sorted(
                selected,
                key=lambda item: (
                    item.artifact_path or "",
                    _lineage_recency_key(item),
                ),
            )
        )

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
            if definition.coverage_policy == "on_demand":
                updated[dataset_id] = result
                continue
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
        statuses = {_current_quality_word(item.quality_status, item.source) for item in lineage}
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


def _lineage_recency_key(item: LineageSummary) -> tuple[datetime, str, str]:
    value = item.fetched_at
    try:
        stamp = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        stamp = stamp.astimezone(UTC)
    except (TypeError, ValueError):
        stamp = datetime.min.replace(tzinfo=UTC)
    return stamp, item.run_id or "", item.source


def _quality_word(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "fail" in text or "error" in text:
        return "failed"
    if "degrad" in text or "warn" in text:
        return "degraded"
    if text in {"healthy", "pass", "passed", "success", "succeeded"}:
        return "healthy"
    if text in {"pending_gate", "pending"}:
        return "unknown"
    return "unknown"


def _current_quality_word(value: Any, source: str | None = None) -> str:
    """Map a currently selected lineage record to dataset-level quality."""
    raw = str(value or "").strip().lower()
    src = str(source or "").strip().lower()
    if raw in {"pending_gate", "pending"}:
        return "healthy"
    if src == "legacy_local_artifact" and raw in {"degraded", "unknown", ""}:
        return "healthy"
    return _quality_word(value)


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


def _is_file_changed(error: Exception) -> bool:
    return isinstance(error, OSError) and _FILE_CHANGED in str(error)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
