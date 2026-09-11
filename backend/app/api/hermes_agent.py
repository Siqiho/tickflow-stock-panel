"""Local Hermes Agent chat seam for the one-trading user console."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.hermes_agent import HermesAgentAdapter, HermesAgentError

router = APIRouter(prefix="/api/hermes-agent", tags=["hermes-agent"])


class CreateSessionRequest(BaseModel):
    title: str = Field(default="", max_length=120)


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12_000)


def _require_local_gateway_admin(request: Request) -> None:
    from app.services import user_context

    user_agent = request.headers.get("user-agent", "").lower()
    if "one-trading-android/" in user_agent:
        raise HTTPException(status_code=403, detail="APK 不能启动本机 Hermes 内部网关")
    if not user_context.is_admin():
        raise HTTPException(status_code=403, detail="仅服务器管理员可以启动内部网关")


@router.post("/gateway/start")
def start_gateway(request: Request) -> dict:
    from app.services.hermes_runtime import HermesRuntimeConfigError, start_managed_gateway

    _require_local_gateway_admin(request)
    try:
        return start_managed_gateway()
    except HermesRuntimeConfigError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/status")
async def status() -> dict:
    try:
        return await HermesAgentAdapter().status()
    except HermesAgentError as exc:
        return {
            "connected": False,
            "profile": None,
            "isolation": "dedicated_profile",
            "model_source": "server_grok_subscription",
            "model_subscription_active": False,
            "message": str(exc),
        }


@router.post("/sessions")
async def create_session(req: CreateSessionRequest) -> dict:
    try:
        session = await HermesAgentAdapter().create_session(req.title)
    except HermesAgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"session": session}


@router.get("/sessions")
async def list_sessions() -> dict:
    try:
        sessions = await HermesAgentAdapter().list_sessions()
    except HermesAgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"sessions": sessions}


@router.patch("/sessions/{session_id}")
async def rename_session(session_id: str, req: RenameSessionRequest) -> dict:
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="对话标题不能为空")
    try:
        session = await HermesAgentAdapter().rename_session(session_id, title)
    except HermesAgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"session": session}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    try:
        return await HermesAgentAdapter().delete_session(session_id)
    except HermesAgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/messages")
async def session_messages(session_id: str) -> dict:
    try:
        messages = await HermesAgentAdapter().get_messages(session_id)
    except HermesAgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"session_id": session_id, "messages": messages}


@router.post("/sessions/{session_id}/chat")
async def chat(session_id: str, req: ChatRequest):
    # Resolve the account/Profile while the authenticated request ContextVar is
    # definitely bound. StreamingResponse may consume its body in another task.
    try:
        adapter = HermesAgentAdapter()
    except HermesAgentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    async def stream():
        try:
            async for event in adapter.stream_chat(session_id, req.message.strip()):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except HermesAgentError as exc:
            yield (
                json.dumps(
                    {"type": "error", "message": str(exc)},
                    ensure_ascii=False,
                )
                + "\n"
            )

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
