"""SQLite control-plane storage for the local data catalog."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import ArtifactRecord, DatasetState, SourceHealth, SyncRun

_MIGRATION_PATTERN = re.compile(r"^(?P<version>\d+)_.*\.sql$")
_MIGRATIONS_DIR = Path(__file__).with_name("migrations")
_SYNC_RUN_UPSERT_SQL = """
    INSERT INTO sync_runs (
        run_id, dataset_id, provider, operation, started_at, finished_at, status,
        rows_fetched, rows_published, quality_status, error_code, error_message
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(run_id) DO UPDATE SET
        dataset_id = sync_runs.dataset_id,
        provider = COALESCE(sync_runs.provider, excluded.provider),
        operation = sync_runs.operation,
        started_at = CASE
            WHEN sync_runs.started_at IS NULL THEN excluded.started_at
            WHEN excluded.started_at IS NULL THEN sync_runs.started_at
            WHEN excluded.started_at < sync_runs.started_at THEN excluded.started_at
            ELSE sync_runs.started_at
        END,
        finished_at = CASE
            WHEN sync_runs.status IN ('succeeded', 'degraded', 'failed')
                THEN sync_runs.finished_at
            WHEN sync_runs.status = 'running' AND excluded.status = 'pending'
                THEN sync_runs.finished_at
            ELSE excluded.finished_at
        END,
        status = CASE
            WHEN sync_runs.status IN ('succeeded', 'degraded', 'failed')
                THEN sync_runs.status
            WHEN sync_runs.status = 'running' AND excluded.status = 'pending'
                THEN sync_runs.status
            ELSE excluded.status
        END,
        rows_fetched = CASE
            WHEN sync_runs.status IN ('succeeded', 'degraded', 'failed')
                OR (sync_runs.status = 'running' AND excluded.status = 'pending')
                THEN sync_runs.rows_fetched
            ELSE excluded.rows_fetched
        END,
        rows_published = CASE
            WHEN sync_runs.status IN ('succeeded', 'degraded', 'failed')
                OR (sync_runs.status = 'running' AND excluded.status = 'pending')
                THEN sync_runs.rows_published
            ELSE excluded.rows_published
        END,
        quality_status = CASE
            WHEN sync_runs.status IN ('succeeded', 'degraded', 'failed')
                OR (sync_runs.status = 'running' AND excluded.status = 'pending')
                THEN sync_runs.quality_status
            ELSE excluded.quality_status
        END,
        error_code = CASE
            WHEN sync_runs.status IN ('succeeded', 'degraded', 'failed')
                OR (sync_runs.status = 'running' AND excluded.status = 'pending')
                THEN sync_runs.error_code
            ELSE excluded.error_code
        END,
        error_message = CASE
            WHEN sync_runs.status IN ('succeeded', 'degraded', 'failed')
                OR (sync_runs.status = 'running' AND excluded.status = 'pending')
                THEN sync_runs.error_message
            ELSE excluded.error_message
        END
"""


class CatalogControlDB:
    """Short-lived SQLite connections and repositories for catalog metadata."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "control" / "catalog.sqlite3"
        self._initialize_lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        """Create or transactionally migrate the catalog database."""
        with self._initialize_lock:
            if self._initialized:
                return

            existing_nonempty = self.path.exists() and self.path.stat().st_size > 0
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = self._connect()
            try:
                current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                for target_version, migration_path in self._migration_files():
                    if target_version <= current_version:
                        continue
                    if existing_nonempty:
                        self._backup_before_migration(connection, current_version, target_version)
                    self._apply_migration(connection, target_version, migration_path)
                    current_version = target_version
            finally:
                connection.close()
            self._initialized = True

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Yield a transaction on an independent configured SQLite connection."""
        self.initialize()
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def has_dataset_states(self) -> bool:
        return self._read_one("SELECT 1 FROM dataset_state LIMIT 1") is not None

    def upsert_dataset_state(self, state: DatasetState) -> None:
        values = (
            state.dataset_id,
            state.schema_version,
            state.unit_version,
            state.quality_status,
            state.row_count,
            state.symbol_count,
            state.expected_symbol_count,
            state.earliest_time,
            state.latest_time,
            state.managed_bytes,
            state.last_run_id,
            state.updated_at,
            self._json_dumps(state.payload),
        )
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO dataset_state (
                    dataset_id, schema_version, unit_version, quality_status, row_count, symbol_count,
                    expected_symbol_count, earliest_time, latest_time, managed_bytes, last_run_id,
                    updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    unit_version = excluded.unit_version,
                    quality_status = excluded.quality_status,
                    row_count = excluded.row_count,
                    symbol_count = excluded.symbol_count,
                    expected_symbol_count = excluded.expected_symbol_count,
                    earliest_time = excluded.earliest_time,
                    latest_time = excluded.latest_time,
                    managed_bytes = excluded.managed_bytes,
                    last_run_id = excluded.last_run_id,
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                values,
            )

    def get_dataset_state(self, dataset_id: str) -> DatasetState | None:
        row = self._read_one("SELECT * FROM dataset_state WHERE dataset_id = ?", (dataset_id,))
        return self._dataset_state_from_row(row) if row is not None else None

    def list_dataset_states(self) -> list[DatasetState]:
        return [
            self._dataset_state_from_row(row)
            for row in self._read_all("SELECT * FROM dataset_state ORDER BY dataset_id")
        ]

    def delete_dataset_state(self, dataset_id: str) -> None:
        with self.transaction() as connection:
            connection.execute("DELETE FROM dataset_state WHERE dataset_id = ?", (dataset_id,))

    def upsert_sync_run(self, run: SyncRun) -> None:
        values = (
            run.run_id,
            run.dataset_id,
            run.provider,
            run.operation,
            run.started_at,
            run.finished_at,
            run.status,
            run.rows_fetched,
            run.rows_published,
            run.quality_status,
            run.error_code,
            run.error_message,
        )
        with self.transaction() as connection:
            connection.execute(_SYNC_RUN_UPSERT_SQL, values)

    def get_sync_run(self, run_id: str) -> SyncRun | None:
        row = self._read_one("SELECT * FROM sync_runs WHERE run_id = ?", (run_id,))
        return self._sync_run_from_row(row) if row is not None else None

    def list_sync_runs(self, dataset_id: str | None = None, limit: int = 100) -> list[SyncRun]:
        bounded_limit = min(max(limit, 1), 1000)
        if dataset_id is None:
            rows = self._read_all(
                "SELECT * FROM sync_runs ORDER BY started_at DESC, run_id ASC LIMIT ?",
                (bounded_limit,),
            )
        else:
            rows = self._read_all(
                """
                SELECT * FROM sync_runs WHERE dataset_id = ?
                ORDER BY started_at DESC, run_id ASC LIMIT ?
                """,
                (dataset_id, bounded_limit),
            )
        return [self._sync_run_from_row(row) for row in rows]

    def replace_artifacts(
        self, dataset_id: str, run_id: str, artifacts: Sequence[ArtifactRecord]
    ) -> None:
        for artifact in artifacts:
            if artifact.dataset_id != dataset_id:
                raise ValueError("artifact dataset_id must match replacement dataset_id")
            if artifact.run_id != run_id:
                raise ValueError("artifact run_id must match replacement run_id")

        with self.transaction() as connection:
            connection.execute("DELETE FROM artifacts WHERE dataset_id = ?", (dataset_id,))
            connection.executemany(
                """
                INSERT INTO artifacts (
                    dataset_id, path, run_id, sha256, row_count, bytes, partition_value, published_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id, path) DO UPDATE SET
                    run_id = excluded.run_id,
                    sha256 = excluded.sha256,
                    row_count = excluded.row_count,
                    bytes = excluded.bytes,
                    partition_value = excluded.partition_value,
                    published_at = excluded.published_at
                """,
                [
                    (
                        artifact.dataset_id,
                        artifact.path,
                        artifact.run_id,
                        artifact.sha256,
                        artifact.row_count,
                        artifact.bytes,
                        artifact.partition_value,
                        artifact.published_at,
                    )
                    for artifact in artifacts
                ],
            )

    def list_artifacts(self, dataset_id: str | None = None) -> list[ArtifactRecord]:
        if dataset_id is None:
            rows = self._read_all("SELECT * FROM artifacts ORDER BY dataset_id, path")
        else:
            rows = self._read_all(
                "SELECT * FROM artifacts WHERE dataset_id = ? ORDER BY dataset_id, path",
                (dataset_id,),
            )
        return [self._artifact_from_row(row) for row in rows]

    def upsert_source_health(self, health: SourceHealth) -> None:
        values = (
            health.provider,
            health.operation,
            health.last_success_at,
            health.last_failure_at,
            health.consecutive_failures,
            health.cooldown_until,
            health.last_error_code,
        )
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO source_health (
                    provider, operation, last_success_at, last_failure_at, consecutive_failures,
                    cooldown_until, last_error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, operation) DO UPDATE SET
                    last_success_at = excluded.last_success_at,
                    last_failure_at = excluded.last_failure_at,
                    consecutive_failures = excluded.consecutive_failures,
                    cooldown_until = excluded.cooldown_until,
                    last_error_code = excluded.last_error_code
                """,
                values,
            )

    def get_source_health(self, provider: str, operation: str) -> SourceHealth | None:
        row = self._read_one(
            "SELECT * FROM source_health WHERE provider = ? AND operation = ?",
            (provider, operation),
        )
        return self._source_health_from_row(row) if row is not None else None

    def list_source_health(self) -> list[SourceHealth]:
        return [
            self._source_health_from_row(row)
            for row in self._read_all("SELECT * FROM source_health ORDER BY provider, operation")
        ]

    def set_meta(self, key: str, value: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO catalog_meta (key, value_json, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, self._json_dumps(value), self._utc_now()),
            )

    def get_meta(self, key: str) -> dict[str, Any] | None:
        row = self._read_one("SELECT value_json FROM catalog_meta WHERE key = ?", (key,))
        return json.loads(row["value_json"]) if row is not None else None

    def commit_scan_results(
        self,
        results: Sequence[tuple[DatasetState, SyncRun, Sequence[ArtifactRecord]]],
        meta_updates: Mapping[str, dict[str, Any]],
    ) -> None:
        """Atomically publish completed dataset scans and their cached metadata."""
        for state, run, artifacts in results:
            if run.dataset_id != state.dataset_id:
                raise ValueError("run dataset_id must match state dataset_id")
            if state.last_run_id != run.run_id:
                raise ValueError("state last_run_id must match run run_id")
            for artifact in artifacts:
                if artifact.dataset_id != state.dataset_id:
                    raise ValueError("artifact dataset_id must match state dataset_id")
                if artifact.run_id != run.run_id:
                    raise ValueError("artifact run_id must match run run_id")

        with self.transaction() as connection:
            for state, run, artifacts in results:
                connection.execute(
                    _SYNC_RUN_UPSERT_SQL,
                    (
                        run.run_id,
                        run.dataset_id,
                        run.provider,
                        run.operation,
                        run.started_at,
                        run.finished_at,
                        run.status,
                        run.rows_fetched,
                        run.rows_published,
                        run.quality_status,
                        run.error_code,
                        run.error_message,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO dataset_state (
                        dataset_id, schema_version, unit_version, quality_status, row_count,
                        symbol_count, expected_symbol_count, earliest_time, latest_time,
                        managed_bytes, last_run_id, updated_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(dataset_id) DO UPDATE SET
                        schema_version = excluded.schema_version,
                        unit_version = excluded.unit_version,
                        quality_status = excluded.quality_status,
                        row_count = excluded.row_count,
                        symbol_count = excluded.symbol_count,
                        expected_symbol_count = excluded.expected_symbol_count,
                        earliest_time = excluded.earliest_time,
                        latest_time = excluded.latest_time,
                        managed_bytes = excluded.managed_bytes,
                        last_run_id = excluded.last_run_id,
                        updated_at = excluded.updated_at,
                        payload_json = excluded.payload_json
                    """,
                    (
                        state.dataset_id,
                        state.schema_version,
                        state.unit_version,
                        state.quality_status,
                        state.row_count,
                        state.symbol_count,
                        state.expected_symbol_count,
                        state.earliest_time,
                        state.latest_time,
                        state.managed_bytes,
                        state.last_run_id,
                        state.updated_at,
                        self._json_dumps(state.payload),
                    ),
                )
                connection.execute(
                    "DELETE FROM artifacts WHERE dataset_id = ?", (state.dataset_id,)
                )
                connection.executemany(
                    """
                    INSERT INTO artifacts (
                        dataset_id, path, run_id, sha256, row_count, bytes,
                        partition_value, published_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            artifact.dataset_id,
                            artifact.path,
                            artifact.run_id,
                            artifact.sha256,
                            artifact.row_count,
                            artifact.bytes,
                            artifact.partition_value,
                            artifact.published_at,
                        )
                        for artifact in artifacts
                    ],
                )
            for key, value in meta_updates.items():
                connection.execute(
                    """
                    INSERT INTO catalog_meta (key, value_json, updated_at) VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value_json = excluded.value_json,
                        updated_at = excluded.updated_at
                    """,
                    (key, self._json_dumps(value), self._utc_now()),
                )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _migration_files(self) -> list[tuple[int, Path]]:
        migrations: list[tuple[int, Path]] = []
        seen_versions: set[int] = set()
        for path in _MIGRATIONS_DIR.glob("*.sql"):
            match = _MIGRATION_PATTERN.match(path.name)
            if match is None:
                continue
            version = int(match.group("version"))
            if version in seen_versions:
                raise ValueError(f"duplicate migration version: {version}")
            seen_versions.add(version)
            migrations.append((version, path))
        return sorted(migrations, key=lambda migration: migration[0])

    def _backup_before_migration(
        self, source: sqlite3.Connection, source_version: int, target_version: int
    ) -> None:
        backup_dir = self.path.parent / "migration_backups"
        backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = (
            backup_dir / f"catalog-v{source_version}-to-v{target_version}-{timestamp}.sqlite3"
        )
        destination = sqlite3.connect(backup_path)
        try:
            source.backup(destination)
        finally:
            destination.close()

    def _apply_migration(
        self, connection: sqlite3.Connection, target_version: int, migration_path: Path
    ) -> None:
        try:
            connection.execute("BEGIN IMMEDIATE")
            for statement in self._sql_statements(migration_path.read_text(encoding="utf-8")):
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {target_version}")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    @staticmethod
    def _sql_statements(script: str) -> Iterator[str]:
        statement = ""
        for line in script.splitlines(keepends=True):
            statement += line
            if sqlite3.complete_statement(statement):
                if statement.strip():
                    yield statement
                statement = ""
        if statement.strip():
            raise ValueError("migration contains an incomplete SQL statement")

    def _read_one(self, query: str, values: Sequence[Any] = ()) -> sqlite3.Row | None:
        self.initialize()
        connection = self._connect()
        try:
            return connection.execute(query, values).fetchone()
        finally:
            connection.close()

    def _read_all(self, query: str, values: Sequence[Any] = ()) -> list[sqlite3.Row]:
        self.initialize()
        connection = self._connect()
        try:
            return connection.execute(query, values).fetchall()
        finally:
            connection.close()

    @staticmethod
    def _json_dumps(value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _dataset_state_from_row(row: sqlite3.Row) -> DatasetState:
        return DatasetState(
            dataset_id=row["dataset_id"],
            schema_version=row["schema_version"],
            unit_version=row["unit_version"],
            quality_status=row["quality_status"],
            row_count=row["row_count"],
            symbol_count=row["symbol_count"],
            expected_symbol_count=row["expected_symbol_count"],
            earliest_time=row["earliest_time"],
            latest_time=row["latest_time"],
            managed_bytes=row["managed_bytes"],
            last_run_id=row["last_run_id"],
            updated_at=row["updated_at"],
            payload=json.loads(row["payload_json"]),
        )

    @staticmethod
    def _sync_run_from_row(row: sqlite3.Row) -> SyncRun:
        return SyncRun(
            run_id=row["run_id"],
            dataset_id=row["dataset_id"],
            provider=row["provider"],
            operation=row["operation"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            status=row["status"],
            rows_fetched=row["rows_fetched"],
            rows_published=row["rows_published"],
            quality_status=row["quality_status"],
            error_code=row["error_code"],
            error_message=row["error_message"],
        )

    @staticmethod
    def _artifact_from_row(row: sqlite3.Row) -> ArtifactRecord:
        return ArtifactRecord(
            run_id=row["run_id"],
            dataset_id=row["dataset_id"],
            path=row["path"],
            sha256=row["sha256"],
            row_count=row["row_count"],
            bytes=row["bytes"],
            partition_value=row["partition_value"],
            published_at=row["published_at"],
        )

    @staticmethod
    def _source_health_from_row(row: sqlite3.Row) -> SourceHealth:
        return SourceHealth(
            provider=row["provider"],
            operation=row["operation"],
            last_success_at=row["last_success_at"],
            last_failure_at=row["last_failure_at"],
            consecutive_failures=row["consecutive_failures"],
            cooldown_until=row["cooldown_until"],
            last_error_code=row["last_error_code"],
        )
