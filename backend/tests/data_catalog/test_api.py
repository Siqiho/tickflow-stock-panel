from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import data
from app.data_catalog.api import router
from app.data_catalog.control_db import CatalogControlDB
from app.data_catalog.definitions import get_dataset_definition
from app.data_catalog.models import DatasetState
from app.data_catalog.service import CatalogRescanInProgress, CatalogService


def _service(tmp_path) -> CatalogService:
    return CatalogService(tmp_path, CatalogControlDB(tmp_path), manifests=())


def _client(service: CatalogService) -> TestClient:
    app = FastAPI()
    app.state.catalog_service = service
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
