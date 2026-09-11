from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import data
from app.data_catalog.api import router
from app.data_catalog.control_db import CatalogControlDB
from app.data_catalog.definitions import get_dataset_definition
from app.data_catalog.models import DatasetState, SourceHealth
from app.data_catalog.service import CatalogRescanInProgress, CatalogService
from app.services import user_context


def _service(tmp_path) -> CatalogService:
    return CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())


def _client(service: CatalogService, *, role: str = "admin") -> TestClient:
    app = FastAPI()
    app.state.catalog_service = service
    if role != "admin":
        @app.middleware("http")
        async def bind_regular_user(request, call_next):
            token = user_context.bind(
                {"id": "regular-test-user", "username": "alice", "role": role}
            )
            try:
                return await call_next(request)
            finally:
                user_context.reset(token)
    app.include_router(router)
    return TestClient(app)


def _persist_daily_state(service: CatalogService) -> None:
    definition = get_dataset_definition("stock_daily")
    service.control_db.upsert_dataset_state(
        DatasetState(
            dataset_id="stock_daily",
            schema_version=definition.descriptor.schema_version,
            unit_version=definition.descriptor.unit_version,
            quality_status="healthy",
            row_count=1,
            managed_bytes=12,
            updated_at="2026-07-21T09:00:00Z",
            payload={"file_count": 1},
        )
    )


def test_catalog_endpoints_return_catalog_detail_schema_and_runs(tmp_path) -> None:
    service = _service(tmp_path)
    _persist_daily_state(service)
    client = _client(service)

    listed = client.get("/api/data/catalog")
    detail = client.get("/api/data/catalog/stock_daily")
    schema = client.get("/api/data/catalog/stock_daily/schema")
    runs = client.get("/api/data/runs", params={"dataset_id": "stock_daily"})

    assert listed.status_code == 200
    assert any(
        item["descriptor"]["dataset_id"] == "stock_daily" for item in listed.json()["datasets"]
    )
    assert detail.status_code == 200
    assert detail.json()["state"]["row_count"] == 1
    assert schema.json()["dataset_id"] == "stock_daily"
    assert schema.json()["fields"]
    assert runs.json() == {"dataset_id": "stock_daily", "runs": []}


def test_regular_user_catalog_contains_only_shared_market_storage(tmp_path) -> None:
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "runtime.log").write_text("server-only", encoding="utf-8")
    (tmp_path / "user_data").mkdir()
    (tmp_path / "user_data" / "preferences.json").write_text(
        '{"private": true}', encoding="utf-8"
    )
    service = _service(tmp_path)
    service.rescan()

    admin = _client(service).get("/api/data/catalog").json()
    regular = _client(service, role="user").get("/api/data/catalog").json()
    detail = _client(service, role="user").get(
        "/api/data/catalog/stock_daily"
    ).json()

    assert admin["storage"]["operational_bytes"] > 0
    assert regular["storage"]["operational_bytes"] == 0
    assert regular["storage"]["total_bytes"] == regular["storage"]["managed_data_bytes"]
    assert all(item["kind"] == "managed" for item in regular["storage"]["categories"])
    assert all(item["key"] != "user_data" for item in regular["storage"]["categories"])
    assert "lineage" not in detail["state"]["payload"]
    assert "scan_errors" not in detail["state"]["payload"]


def test_control_summary_exposes_optional_control_facts_without_triggering_a_rescan(
    tmp_path,
) -> None:
    service = _service(tmp_path)
    _persist_daily_state(service)
    service.control_db.upsert_source_health(
        SourceHealth(
            provider="data_sync",
            operation="sync:trading_calendar",
            last_success_at="2026-07-22T05:45:05Z",
        )
    )
    with service.control_db.transaction() as connection:
        connection.executescript(
            """
            CREATE TABLE dataset_policies (
                dataset_id TEXT PRIMARY KEY, phase TEXT NOT NULL,
                max_lag_trading_days INTEGER, sync_mode TEXT, schedule_cron TEXT,
                source_policy_json TEXT NOT NULL DEFAULT '{}',
                retention_policy_json TEXT NOT NULL DEFAULT '{}',
                supports_backfill INTEGER NOT NULL DEFAULT 0,
                supports_repair INTEGER NOT NULL DEFAULT 0, updated_at TEXT
            );
            CREATE TABLE sync_checkpoints (
                dataset_id TEXT NOT NULL, scope TEXT NOT NULL,
                cursor_json TEXT NOT NULL DEFAULT '{}', watermark TEXT,
                last_success_run_id TEXT, updated_at TEXT,
                PRIMARY KEY (dataset_id, scope)
            );
            CREATE TABLE agent_query_audit (
                audit_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                dataset_id TEXT NOT NULL, tool_name TEXT, row_count INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER, status TEXT NOT NULL, error_code TEXT
            );
            INSERT INTO dataset_policies VALUES (
                'trading_calendar', 'production', 1, 'scheduled', '20 8 * * 1-5',
                '{}', '{}', 1, 1, '2026-07-22T05:45:05Z'
            );
            INSERT INTO sync_checkpoints VALUES (
                'trading_calendar', 'default', '{"date": "2026-08-31"}', '2026-08-31',
                'run-42', '2026-07-22T05:45:05Z'
            );
            INSERT INTO agent_query_audit VALUES (
                'audit-1', '2026-07-22T06:00:00Z', 'trading_calendar',
                'get_trading_days', 12, 8, 'succeeded', NULL
            );
            """
        )
    unregistered = tmp_path / "reference" / "governance_events"
    unregistered.mkdir(parents=True)
    (unregistered / "part.parquet").write_bytes(b"physical-side-data")

    response = _client(service).get("/api/data/control-summary")

    assert response.status_code == 200
    body = response.json()
    assert body["source_health"][0]["operation"] == "sync:trading_calendar"
    assert body["dataset_policies"][0]["phase"] == "production"
    assert body["sync_checkpoints"][0] == {
        "dataset_id": "trading_calendar",
        "scope": "default",
        "watermark": "2026-08-31",
        "updated_at": "2026-07-22T05:45:05Z",
        "cursor": {"date": "2026-08-31"},
        "last_success_run_id": "run-42",
    }
    assert body["query_audits"][0]["tool_name"] == "get_trading_days"
    assert body["unregistered_physical"][0]["relative_path"] == "reference/governance_events"
    assert body["physical_scan_scope"] == "reference"


def test_control_summary_does_not_initialize_a_missing_control_database(tmp_path) -> None:
    service = object.__new__(CatalogService)
    service.data_dir = tmp_path
    service.control_db = CatalogControlDB(tmp_path)
    service.definitions = ()

    summary = service.control_summary()

    assert summary.catalog_stale is True
    assert summary.source_health == []
    assert not service.control_db.path.exists()


def test_catalog_unknown_dataset_ids_have_stable_404_detail(tmp_path) -> None:
    client = _client(_service(tmp_path))
    expected = {"detail": {"code": "dataset_not_found", "dataset_id": "missing"}}

    for url, method in [
        ("/api/data/catalog/missing", client.get),
        ("/api/data/catalog/missing/schema", client.get),
        ("/api/data/catalog/rescan?dataset_id=missing", client.post),
    ]:
        response = method(url)
        assert response.status_code == 404
        assert response.json() == expected


def test_catalog_rescan_failure_keeps_prior_snapshot_and_marks_it_stale(tmp_path) -> None:
    service = _service(tmp_path)
    _persist_daily_state(service)

    class FailingScanner:
        def scan_all(self, run_ids):
            raise RuntimeError("scanner exploded")

    service.scanner = FailingScanner()
    response = _client(service).post("/api/data/catalog/rescan")

    assert response.status_code == 200
    body = response.json()
    daily = next(
        item for item in body["datasets"] if item["descriptor"]["dataset_id"] == "stock_daily"
    )
    assert body["stale"] is True
    assert daily["state"]["row_count"] == 1
    assert service.list_runs("stock_daily")[0].status == "failed"


def test_catalog_api_without_service_has_stable_unavailable_error() -> None:
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).get("/api/data/catalog")

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "catalog_unavailable"}}


def test_catalog_rescan_in_progress_has_stable_409_detail() -> None:
    class BusyCatalog:
        def rescan(self, dataset_id=None):
            raise CatalogRescanInProgress()

    response = _client(BusyCatalog()).post("/api/data/catalog/rescan")  # type: ignore[arg-type]

    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "catalog_rescan_in_progress"}}


def test_status_delegates_to_catalog_and_keeps_legacy_top_level_shape() -> None:
    class Catalog:
        def compatibility_status(self):
            return {
                key: None
                for key in (
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
                )
            }

        def list_runs(self, dataset_id, limit=100):
            return []

    app = FastAPI()
    app.state.catalog_service = Catalog()
    app.state.scheduler = None
    app.include_router(data.router)

    response = TestClient(app).get("/api/data/status")

    assert response.status_code == 200
    assert set(response.json()) == {
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


def test_regular_user_status_total_excludes_operational_storage() -> None:
    class Catalog:
        def compatibility_status(self):
            return {
                "storage": {
                    "daily_size_mb": 1.25,
                    "enriched_size_mb": 2.5,
                    "total_size_mb": 99.0,
                }
            }

        def list_runs(self, dataset_id, limit=100):
            return []

    app = FastAPI()
    app.state.catalog_service = Catalog()
    app.state.scheduler = None

    @app.middleware("http")
    async def bind_regular_user(request, call_next):
        token = user_context.bind(
            {"id": "regular-test-user", "username": "alice", "role": "user"}
        )
        try:
            return await call_next(request)
        finally:
            user_context.reset(token)

    app.include_router(data.router)

    response = TestClient(app).get("/api/data/status")

    assert response.status_code == 200
    assert response.json()["storage"]["total_size_mb"] == 3.75
