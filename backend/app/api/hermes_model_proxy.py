"""Authenticated loopback bridge from every Profile to one server Grok subscription."""

from __future__ import annotations

import ipaddress

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from app.services.hermes_model_proxy import HermesModelProxyError, HermesUserConsoleModelAdapter
from app.services.hermes_tenant import HermesTenantError, HermesTenantRegistry

router = APIRouter(prefix="/api/hermes-xai/v1", tags=["hermes-model-proxy"])


def _require_loopback(request: Request) -> None:
    host = request.client.host if request.client else ""
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise HTTPException(status_code=403, detail="Hermes 模型桥接仅允许本机访问")


def _principal(profile: str, authorization: str | None) -> dict:
    try:
        user, _tenant = HermesTenantRegistry().authenticate(
            profile,
            authorization,
            purpose="bridge",
        )
        return user
    except HermesTenantError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _bind(user: dict):
    from app.services import user_context

    return user_context, user_context.bind(user)


def _consume_quota(user: dict) -> None:
    from app.services import auth

    try:
        auth.consume_quota(user)
    except PermissionError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.get("/profiles/{profile}/models")
async def models(
    profile: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict:
    _require_loopback(request)
    user = _principal(profile, authorization)
    adapter = HermesUserConsoleModelAdapter()
    context, token = _bind(user)
    try:
        model = adapter.model
    except HermesModelProxyError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    finally:
        context.reset(token)
    return {"object": "list", "data": [{"id": model, "object": "model"}]}


@router.get("/profiles/{profile}/api/v1/models", include_in_schema=False)
@router.get("/profiles/{profile}/api/tags", include_in_schema=False)
@router.get("/profiles/{profile}/v1/props", include_in_schema=False)
@router.get("/profiles/{profile}/props", include_in_schema=False)
@router.get("/profiles/{profile}/version", include_in_schema=False)
async def reject_local_model_server_probe(
    profile: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    """Stop Hermes' localhost detector from mistaking the SPA fallback for LM Studio."""
    _require_loopback(request)
    _principal(profile, authorization)
    return Response(status_code=404)


@router.post("/profiles/{profile}/responses")
async def responses(
    profile: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_loopback(request)
    user = _principal(profile, authorization)
    adapter = HermesUserConsoleModelAdapter()
    context, token = _bind(user)
    try:
        adapter.require_ready()
        _consume_quota(user)
        upstream = await adapter.open_responses(await request.body())
    except HermesModelProxyError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    finally:
        context.reset(token)
    return StreamingResponse(
        upstream.body,
        status_code=upstream.status_code,
        headers=upstream.headers,
    )


@router.post("/profiles/{profile}/chat/completions")
async def chat_completions(
    profile: str,
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_loopback(request)
    user = _principal(profile, authorization)
    adapter = HermesUserConsoleModelAdapter()
    context, token = _bind(user)
    try:
        adapter.require_ready()
        _consume_quota(user)
        upstream = await adapter.open_chat_completions(await request.body())
    except HermesModelProxyError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    finally:
        context.reset(token)
    return StreamingResponse(
        upstream.body,
        status_code=upstream.status_code,
        headers=upstream.headers,
    )
