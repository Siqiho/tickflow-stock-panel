from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import pytest

from app.data_catalog.control_db import CatalogControlDB
from app.data_catalog.models import ArtifactRecord, DatasetState, SourceHealth, SyncRun


def make_state(dataset_id: str = "stock_daily") -> DatasetState:
    return DatasetState(
        dataset_id=dataset_id,
        schema_version="1",
        unit_version="cn_market_v1",
        quality_status="healthy",
        row_count=12,
        symbol_count=3,
        expected_symbol_count=4,
        earliest_time="2026-07-01",
        latest_time="2026-07-21",
        managed_bytes=123,
        last_run_id="run-1",
        updated_at="2026-07-21T10:00:00Z",
        payload={"z": "中文", "a": 1},
    )


def make_run(run_id: str = "run-1", dataset_id: str = "stock_daily") -> SyncRun:
    return SyncRun(
        run_id=run_id,
        dataset_id=dataset_id,
        provider="public_quote_eod",
        operation="sync_daily",
        started_at="2026-07-21T09:00:00Z",
        finished_at="2026-07-21T09:01:00Z",
        status="succeeded",
        rows_fetched=13,
        rows_published=12,
        quality_status="healthy",
        error_code="none",
        error_message="保留错误细节",
    )


def make_artifact(path: str, run_id: str = "run-1") -> ArtifactRecord:
    return ArtifactRecord(
        run_id=run_id,
        dataset_id="stock_daily",
        path=path,
        sha256="a" * 64,
        row_count=12,
        bytes=123,
        partition_value="2026-07-21",
        published_at="2026-07-21T09:01:00Z",
    )


def test_initialize_creates_contract_schema_pragmas_and_no_fresh_backup(tmp_path: Path) -> None:
    db = CatalogControlDB(tmp_path)

    assert not (tmp_path / "control").exists()

    db.initialize()

    assert db.path == tmp_path / "control" / "catalog.sqlite3"
    assert db.path.exists()
    assert not (tmp_path / "control" / "migration_backups").exists()
    with db.transaction() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert {"dataset_state", "sync_runs", "artifacts", "source_health", "catalog_meta"} <= tables


def test_dataset_state_upsert_round_trips_deterministic_json_and_key_order(tmp_path: Path) -> None:
    db = CatalogControlDB(tmp_path)
    state = make_state()
    db.upsert_dataset_state(state)
    db.upsert_dataset_state(make_state("etf_daily").model_copy(update={"row_count": 2}))

    assert db.has_dataset_states() is True
    assert db.get_dataset_state("stock_daily") == state
    assert [item.dataset_id for item in db.list_dataset_states()] == ["etf_daily", "stock_daily"]
    with sqlite3.connect(db.path) as connection:
        payload_json = connection.execute(
            "SELECT payload_json FROM dataset_state WHERE dataset_id = ?", ("stock_daily",)
        ).fetchone()[0]
    assert payload_json == '{"a": 1, "z": "中文"}'

    db.delete_dataset_state("stock_daily")
    assert db.get_dataset_state("stock_daily") is None


def test_sync_runs_preserve_lifecycle_details_and_list_newest_first(tmp_path: Path) -> None:
    db = CatalogControlDB(tmp_path)
    older = make_run("run-older").model_copy(update={"started_at": "2026-07-20T09:00:00Z"})
    newer = make_run("run-newer").model_copy(update={"started_at": "2026-07-21T09:00:00Z"})
    db.upsert_sync_run(older)
    db.upsert_sync_run(newer)

    assert db.get_sync_run("run-newer") == newer
    assert [item.run_id for item in db.list_sync_runs("stock_daily", limit=1)] == ["run-newer"]
    assert [item.run_id for item in db.list_sync_runs(limit=10)] == ["run-newer", "run-older"]
    assert db.get_sync_run("run-newer").error_message == "保留错误细节"  # type: ignore[union-attr]


def test_sync_run_state_machine_is_monotonic_and_terminal_absorbs_late_callbacks(
    tmp_path: Path,
) -> None:
    db = CatalogControlDB(tmp_path)
    pending = make_run("run-race").model_copy(
        update={
            "status": "pending",
            "started_at": None,
            "finished_at": None,
            "quality_status": "unknown",
            "error_code": None,
            "error_message": None,
        }
    )
    running = pending.model_copy(update={"status": "running", "started_at": "2026-07-21T09:00:00Z"})
    terminal = running.model_copy(
        update={
            "status": "succeeded",
            "finished_at": "2026-07-21T09:01:00Z",
            "quality_status": "healthy",
            "rows_published": 12,
        }
    )
    late_running = running.model_copy(
        update={"started_at": "2026-07-21T09:00:30Z", "rows_published": 999}
    )
    late_failed = terminal.model_copy(
        update={
            "status": "failed",
            "finished_at": "2026-07-21T09:02:00Z",
            "quality_status": "failed",
            "error_code": "late",
            "error_message": "late terminal",
        }
    )

    for callback in (pending, running, terminal, late_running, pending, late_failed):
        db.upsert_sync_run(callback)

    persisted = db.get_sync_run("run-race")
    assert persisted is not None
    assert persisted.status == "succeeded"
    assert persisted.started_at == "2026-07-21T09:00:00Z"
    assert persisted.finished_at == "2026-07-21T09:01:00Z"
    assert persisted.rows_published == 12
    assert persisted.quality_status == "healthy"
    assert persisted.error_code is None
    assert persisted.error_message is None


def test_replace_artifacts_is_atomic_and_replaces_the_target_dataset_snapshot(
    tmp_path: Path,
) -> None:
    db = CatalogControlDB(tmp_path)
    db.upsert_sync_run(make_run())
    db.upsert_sync_run(make_run("run-2"))
    db.replace_artifacts("stock_daily", "run-1", [make_artifact("first.parquet")])
    db.replace_artifacts("stock_daily", "run-2", [make_artifact("second.parquet", "run-2")])
    db.replace_artifacts("stock_daily", "run-1", [make_artifact("replacement.parquet")])

    assert [(item.path, item.run_id) for item in db.list_artifacts("stock_daily")] == [
        ("replacement.parquet", "run-1"),
    ]
    with pytest.raises(ValueError, match="dataset_id"):
        db.replace_artifacts(
            "stock_daily",
            "run-1",
            [make_artifact("bad.parquet").model_copy(update={"dataset_id": "etf_daily"})],
        )
    assert [item.path for item in db.list_artifacts("stock_daily")] == ["replacement.parquet"]


def test_source_health_and_meta_are_deterministic_and_ordered(tmp_path: Path) -> None:
    db = CatalogControlDB(tmp_path)
    db.upsert_source_health(
        SourceHealth(provider="zeta", operation="daily", consecutive_failures=1)
    )
    health = SourceHealth(
        provider="alpha",
        operation="daily",
        last_success_at="2026-07-21T10:00:00Z",
        consecutive_failures=0,
    )
    db.upsert_source_health(health)
    db.set_meta("storage", {"z": "中文", "a": 1})

    assert db.get_source_health("alpha", "daily") == health
    assert [(item.provider, item.operation) for item in db.list_source_health()] == [
        ("alpha", "daily"),
        ("zeta", "daily"),
    ]
    assert db.get_meta("storage") == {"a": 1, "z": "中文"}
    with sqlite3.connect(db.path) as connection:
        value_json = connection.execute(
            "SELECT value_json FROM catalog_meta WHERE key = ?", ("storage",)
        ).fetchone()[0]
    assert value_json == json.dumps({"a": 1, "z": "中文"}, ensure_ascii=False, sort_keys=True)


def test_initialize_backs_up_existing_database_before_pending_migration(tmp_path: Path) -> None:
    control_dir = tmp_path / "control"
    control_dir.mkdir()
    path = control_dir / "catalog.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE legacy (value TEXT NOT NULL)")
        connection.execute("INSERT INTO legacy VALUES ('before migration')")

    db = CatalogControlDB(tmp_path)
    db.initialize()
    db.initialize()

    backups = list((control_dir / "migration_backups").glob("catalog-v0-to-v1-*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("SELECT value FROM legacy").fetchone()[0] == "before migration"
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 0


def test_transaction_rolls_back_invalid_write(tmp_path: Path) -> None:
    db = CatalogControlDB(tmp_path)
    db.initialize()

    with pytest.raises(sqlite3.IntegrityError), db.transaction() as connection:
        connection.execute(
            "INSERT INTO dataset_state (dataset_id, schema_version, unit_version, quality_status, "
            "row_count, symbol_count, managed_bytes, updated_at, payload_json) "
            "VALUES ('bad', '1', 'v1', 'healthy', -1, 0, 0, '2026-07-21', '{}')"
        )
    assert db.get_dataset_state("bad") is None


def test_wal_reader_completes_while_writer_transaction_is_open(tmp_path: Path) -> None:
    db = CatalogControlDB(tmp_path)
    db.upsert_dataset_state(make_state())
    entered_write = threading.Event()
    release_write = threading.Event()
    writer_error: list[BaseException] = []

    def hold_writer() -> None:
        try:
            with db.transaction() as connection:
                connection.execute(
                    "UPDATE dataset_state SET row_count = ? WHERE dataset_id = ?",
                    (99, "stock_daily"),
                )
                entered_write.set()
                assert release_write.wait(timeout=2)
        except BaseException as error:  # pragma: no cover - asserted below
            writer_error.append(error)

    writer = threading.Thread(target=hold_writer)
    writer.start()
    assert entered_write.wait(timeout=2)

    read_complete = threading.Event()
    observed: list[int] = []

    def read_during_write() -> None:
        observed.append(db.get_dataset_state("stock_daily").row_count)  # type: ignore[union-attr]
        read_complete.set()

    reader = threading.Thread(target=read_during_write)
    reader.start()
    assert read_complete.wait(timeout=1), "WAL reader was blocked by the writer"
    release_write.set()
    reader.join(timeout=2)
    writer.join(timeout=2)

    assert not writer_error
    assert observed == [12]
    assert db.get_dataset_state("stock_daily").row_count == 99  # type: ignore[union-attr]


def test_commit_scan_results_atomically_replaces_snapshots_runs_and_meta(tmp_path: Path) -> None:
    db = CatalogControlDB(tmp_path)
    state = make_state()
    run = make_run()
    artifact = make_artifact("part.parquet")

    db.commit_scan_results(
        [(state, run, (artifact,))],
        {
            "dataset_storage": {"stock_daily": {"bytes": 123, "files": 1}},
            "catalog_refreshed_at": {"value": "2026-07-21T10:00:00Z"},
        },
    )

    assert db.get_dataset_state("stock_daily") == state
    assert db.get_sync_run("run-1") == run
    assert db.list_artifacts("stock_daily") == [artifact]
    assert db.get_meta("dataset_storage") == {"stock_daily": {"bytes": 123, "files": 1}}


def test_commit_scan_results_rolls_back_every_table_when_meta_serialization_fails(
    tmp_path: Path,
) -> None:
    db = CatalogControlDB(tmp_path)

    with pytest.raises(TypeError):
        db.commit_scan_results(
            [(make_state(), make_run(), (make_artifact("part.parquet"),))],
            {"invalid": {"not_json": object()}},
        )

    assert db.get_dataset_state("stock_daily") is None
    assert db.get_sync_run("run-1") is None
    assert db.list_artifacts("stock_daily") == []
    assert db.get_meta("invalid") is None
