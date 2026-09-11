"""Local HTTP access to the SQLite-backed data catalog."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.services import user_context

from .models import (
    CatalogResponse,
    ControlSummaryResponse,
    DatasetCatalogEntry,
    StorageBreakdown,
)
from .provenance import SourceProvenanceModule
from .provenance_models import SourceProvenanceResponse
from .service import CatalogRescanInProgress

router = APIRouter(prefix="/api/data", tags=["data-catalog"])


def _service(request: Request):
    service = getattr(request.app.state, "catalog_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail={"code": "catalog_unavailable"})
    return service


def _missing_dataset(dataset_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "dataset_not_found", "dataset_id": dataset_id},
    )


def _shared_market_entry(entry: DatasetCatalogEntry) -> DatasetCatalogEntry:
    """Remove server-internal paths and scan diagnostics from a public entry."""
    public = entry.model_copy(deep=True)
    public.lineage = [
        item.model_copy(update={"artifact_path": None}) for item in public.lineage
    ]
    payload = dict(public.state.payload)
    payload.pop("lineage", None)
    payload.pop("scan_errors", None)
    public.state = public.state.model_copy(update={"payload": payload})
    return public


def _catalog_for_request(catalog: CatalogResponse) -> CatalogResponse:
    if user_context.is_admin():
        return catalog
    managed_categories = [
        item.model_copy(deep=True)
        for item in catalog.storage.categories
        if item.kind == "managed"
    ]
    managed_bytes = sum(item.bytes for item in managed_categories)
    storage = StorageBreakdown(
        managed_data_bytes=managed_bytes,
        operational_bytes=0,
        total_bytes=managed_bytes,
        categories=managed_categories,
    )
    return catalog.model_copy(
        update={
            "datasets": [_shared_market_entry(item) for item in catalog.datasets],
            "storage": storage,
        }
    )


@router.get("/catalog", response_model=CatalogResponse)
def list_catalog(request: Request) -> CatalogResponse:
    return _catalog_for_request(_service(request).list_catalog())


@router.get("/catalog/{dataset_id}", response_model=DatasetCatalogEntry)
def get_catalog_dataset(request: Request, dataset_id: str) -> DatasetCatalogEntry:
    entry = _service(request).get_dataset(dataset_id)
    if entry is None:
        raise _missing_dataset(dataset_id)
    return entry if user_context.is_admin() else _shared_market_entry(entry)


@router.get("/catalog/{dataset_id}/schema")
def get_catalog_schema(request: Request, dataset_id: str) -> dict:
    service = _service(request)
    fields = service.get_schema(dataset_id)
    if fields is None:
        raise _missing_dataset(dataset_id)
    entry = service.get_dataset(dataset_id)
    assert entry is not None
    return {
        "dataset_id": dataset_id,
        "schema_version": entry.descriptor.schema_version,
        "unit_version": entry.descriptor.unit_version,
        "fields": fields,
    }


@router.get("/runs")
def list_runs(request: Request, dataset_id: str | None = None) -> dict:
    return {
        "dataset_id": dataset_id,
        "runs": _service(request).list_runs(dataset_id),
    }


@router.get("/control-summary", response_model=ControlSummaryResponse)
def get_control_summary(request: Request) -> ControlSummaryResponse:
    return _service(request).control_summary()


@router.get("/source-provenance", response_model=SourceProvenanceResponse)
def get_source_provenance(request: Request) -> SourceProvenanceResponse:
    return SourceProvenanceModule(_service(request)).list_sources()


@router.post("/catalog/rescan", response_model=CatalogResponse)
def rescan_catalog(request: Request, dataset_id: str | None = None) -> CatalogResponse:
    service = _service(request)
    try:
        return service.rescan(dataset_id)
    except CatalogRescanInProgress:
        raise HTTPException(
            status_code=409,
            detail={"code": "catalog_rescan_in_progress"},
        ) from None
    except KeyError:
        raise _missing_dataset(dataset_id or "") from None
