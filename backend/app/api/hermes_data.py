"""Authenticated loopback Interface for Hermes user-console data tools."""

from __future__ import annotations

import ipaddress
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.services.hermes_tenant import HermesTenantError, HermesTenantRegistry
from app.services.user_console_data import UserConsoleDataError, UserConsoleDataModule

router = APIRouter(prefix="/api/hermes-data/v1", tags=["hermes-data"])


class UserConsoleQueryRequest(BaseModel):
    view: str = Field(min_length=1, max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)
    max_items: int = Field(default=100, ge=1, le=500)


def _require_loopback(request: Request) -> None:
    host = request.client.host if request.client else ""
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise HTTPException(status_code=403, detail="Hermes 用户台数据桥接仅允许本机访问")


def _tenant(profile: str, authorization: str | None):
    try:
        return HermesTenantRegistry().authenticate(profile, authorization, purpose="data")
    except HermesTenantError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/profiles/{profile}/catalog")
async def catalog(
    profile: str,
    request: Request,
    domain: str = Query(default="", max_length=50),
    search: str = Query(default="", max_length=100),
    authorization: str | None = Header(default=None),
) -> dict:
    _require_loopback(request)
    user, tenant = _tenant(profile, authorization)
    from app.services import user_context

    token = user_context.bind(user)
    try:
        module = UserConsoleDataModule(
            app=request.app,
            api_key=tenant.data_key,
            profile=tenant.profile,
        )
        return module.catalog(domain=domain, search=search)
    finally:
        user_context.reset(token)


@router.post("/profiles/{profile}/query")
async def query(
    profile: str,
    request: Request,
    body: UserConsoleQueryRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    _require_loopback(request)
    user, tenant = _tenant(profile, authorization)
    from app.services import user_context

    token = user_context.bind(user)
    try:
        module = UserConsoleDataModule(
            app=request.app,
            api_key=tenant.data_key,
            profile=tenant.profile,
        )
        return await module.query(body.view, body.params, max_items=body.max_items)
    except UserConsoleDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    finally:
        user_context.reset(token)
