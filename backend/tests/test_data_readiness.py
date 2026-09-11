from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import overview
from app.main import _frontend_fallback


class _CatalogService:
    def compatibility_status(self) -> dict:
        return {
            "daily": {
                "earliest_date": "2024-01-02",
                "latest_date": "2026-08-11",
                "trading_days": 620,
                "rows": 3_000_000,
                "symbols_covered": 5_400,
            },
            "enriched": {
                "earliest_date": "2024-01-02",
                "latest_date": "2026-08-11",
                "trading_days": 620,
                "rows": 3_000_000,
                "symbols_covered": 5_400,
            },
            "storage": {"total_size_mb": 1234},
            "next_pipeline_run": "2026-08-12T15:15:00+08:00",
        }


def test_shared_data_readiness_exposes_only_date_coverage() -> None:
    app = FastAPI()
    app.state.catalog_service = _CatalogService()
    app.include_router(overview.router)

    response = TestClient(app).get("/api/overview/data-readiness")

    assert response.status_code == 200
    assert response.json() == {
        "daily": {
            "earliest_date": "2024-01-02",
            "latest_date": "2026-08-11",
            "trading_days": 620,
        },
        "enriched": {
            "earliest_date": "2024-01-02",
            "latest_date": "2026-08-11",
            "trading_days": 620,
        },
    }


def test_unknown_api_route_never_returns_the_spa() -> None:
    response = _frontend_fallback("api/admin/audit")

    assert response.status_code == 404
    assert json.loads(response.body) == {"detail": "Not Found"}
