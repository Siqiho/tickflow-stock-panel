"""Local HTTP access to the SQLite-backed data catalog."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from .models import CatalogResponse, DatasetCatalogEntry

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


@router.get("/catalog", response_model=CatalogResponse)
def list_catalog(request: Request) -> CatalogResponse:
    return _service(request).list_catalog()


@router.get("/catalog/{dataset_id}", response_model=DatasetCatalogEntry)
def get_catalog_dataset(request: Request, dataset_id: str) -> DatasetCatalogEntry:
    entry = _service(request).get_dataset(dataset_id)
    if entry is None:
        raise _missing_dataset(dataset_id)
    return entry


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


@router.post("/catalog/rescan", response_model=CatalogResponse)
def rescan_catalog(request: Request, dataset_id: str | None = None) -> CatalogResponse:
    service = _service(request)
    try:
        return service.rescan(dataset_id)
    except KeyError:
        raise _missing_dataset(dataset_id or "") from None
