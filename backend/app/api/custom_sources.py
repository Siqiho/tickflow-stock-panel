"""Custom HTTP data-source management APIs (opt-in, staging-first)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.data_providers.custom import (
    data_sources_dir,
    delete_config,
    errors,
    get_config_dict,
    get_provider,
    list_sources,
    load_all,
    names,
    save_config,
)
from app.data_providers.custom.security import UnsafeURLError
from app.data_providers.custom.staging import write_daily_staging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/custom-sources", tags=["custom-sources"])


class SaveSourceRequest(BaseModel):
    name: str
    config: dict[str, Any]


class TestRequest(BaseModel):
    name: str
    dataset: str = "daily"
    symbols: list[str] = Field(default_factory=lambda: ["000001.SZ"])


class StageDailyRequest(BaseModel):
    name: str
    symbols: list[str] = Field(default_factory=lambda: ["000001.SZ"])
    start: str | None = None
    end: str | None = None
    note: str = ""


def _reload() -> None:
    load_all()


@router.get("")
def list_custom_sources() -> dict:
    """List loaded custom YAML sources. Does not change production provider."""
    _reload()
    return {
        "default_provider": "tickflow",
        "sources": list_sources(),
        "names": names(),
        "errors": errors(),
        "data_sources_dir": str(data_sources_dir()),
        "policy": {
            "auto_selected": False,
            "writes_production_kline": False,
            "staging_required": True,
        },
    }


@router.post("/reload")
def reload_custom_sources() -> dict:
    _reload()
    return {"ok": True, "names": names(), "errors": errors()}


@router.get("/{name}")
def get_source(name: str) -> dict:
    _reload()
    cfg = get_config_dict(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"custom source not found: {name}")
    return {"name": name, "config": cfg}


@router.put("/{name}")
def put_source(name: str, req: SaveSourceRequest) -> dict:
    if name != req.name and req.name:
        # keep path key authoritative
        pass
    try:
        path = save_config(name, {**req.config, "name": name})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _reload()
    return {"ok": True, "path": str(path), "names": names(), "errors": errors()}


@router.delete("/{name}")
def remove_source(name: str) -> dict:
    try:
        deleted = delete_config(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _reload()
    return {"ok": True, "deleted": deleted, "names": names()}


@router.post("/test")
def test_source(req: TestRequest) -> dict:
    """Fetch a small sample through the custom provider (no production write)."""
    _reload()
    provider = get_provider(req.name)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"custom source not found: {req.name}")
    try:
        result = provider.test_dataset(req.dataset, symbols=req.symbols)
        return {"ok": True, **result}
    except UnsafeURLError as e:
        raise HTTPException(status_code=400, detail=f"unsafe url: {e}") from e
    except Exception as e:  # noqa: BLE001
        logger.warning("custom source test failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/stage-daily")
def stage_daily(req: StageDailyRequest) -> dict:
    """Fetch daily bars and write to staging only (never production kline_daily)."""
    _reload()
    provider = get_provider(req.name)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"custom source not found: {req.name}")

    def _parse(s: str | None) -> datetime | None:
        if not s:
            return None
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    try:
        df = provider.get_daily(
            symbols=req.symbols,
            start_time=_parse(req.start),
            end_time=_parse(req.end),
            asset_type="stock",
        )
        meta = write_daily_staging(req.name, df, note=req.note or "api stage-daily")
        return {
            "ok": bool(meta.get("ok")),
            "staging": meta,
            "message": "written to staging only; production kline_daily not modified",
        }
    except UnsafeURLError as e:
        raise HTTPException(status_code=400, detail=f"unsafe url: {e}") from e
    except Exception as e:  # noqa: BLE001
        logger.warning("custom stage-daily failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e
