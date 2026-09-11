"""Administrator-only account and AI usage insight."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.services.admin_console import AdminConsole, AdminConsoleError

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _admin(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if not isinstance(user, dict) or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅服务器管理员可以访问用户管理")
    return user


def _translate(exc: AdminConsoleError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/users")
async def list_users(request: Request) -> dict:
    admin = _admin(request)
    try:
        return await AdminConsole().list_users(admin)
    except AdminConsoleError as exc:
        raise _translate(exc) from exc


@router.get("/users/{user_id}/conversations")
async def list_user_conversations(
    user_id: str,
    request: Request,
) -> dict:
    admin = _admin(request)
    try:
        return await AdminConsole().list_user_sessions(admin, user_id)
    except AdminConsoleError as exc:
        raise _translate(exc) from exc


@router.get("/users/{user_id}/strategies")
def list_user_strategies(user_id: str, request: Request) -> dict:
    admin = _admin(request)
    try:
        return AdminConsole().list_user_strategies(admin, user_id)
    except AdminConsoleError as exc:
        raise _translate(exc) from exc


@router.get("/users/{user_id}/conversations/{session_id}/messages")
async def get_user_messages(
    user_id: str,
    session_id: str,
    request: Request,
) -> dict:
    admin = _admin(request)
    try:
        return await AdminConsole().get_user_messages(
            admin,
            user_id,
            session_id,
        )
    except AdminConsoleError as exc:
        raise _translate(exc) from exc
