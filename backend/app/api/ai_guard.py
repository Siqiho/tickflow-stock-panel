"""HTTP guard shared by every user-facing AI generation route."""
from __future__ import annotations

from fastapi import HTTPException

from app.services.ai_provider import ai_access_status


def require_ai_http_access() -> dict[str, object]:
    status = ai_access_status()
    if not status["allowed"]:
        http_status = 402 if status["state"] == "subscription_required" else 503
        raise HTTPException(
            status_code=http_status,
            detail={
                "code": status["state"],
                "message": status["message"],
            },
        )

    from app.services import auth, user_context

    user = user_context.current()
    try:
        quota = auth.consume_quota(user)
    except PermissionError as exc:
        raise HTTPException(
            status_code=429,
            detail={"code": "ai_quota_exhausted", "message": str(exc)},
        ) from exc
    return {**status, "quota": quota}
