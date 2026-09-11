"""Request-scoped identity and per-user storage paths.

Market data remains shared under ``DATA_DIR``. Mutable user-owned state lives in
an isolated ``user_data`` directory selected by the authenticated principal.
Background jobs deliberately fall back to the legacy owner context so existing
single-user server behavior remains stable.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any

_principal: ContextVar[dict[str, Any] | None] = ContextVar(
    "one_trading_principal",
    default=None,
)


def bind(principal: dict[str, Any]) -> Token:
    return _principal.set(dict(principal))


def reset(token: Token) -> None:
    _principal.reset(token)


def current() -> dict[str, Any]:
    principal = _principal.get()
    if principal is not None:
        return principal
    return {
        "id": "owner",
        "username": "admin",
        "role": "admin",
        "legacy_home": True,
    }


def is_admin() -> bool:
    return current().get("role") == "admin"


def user_data_dir_for(
    principal: dict[str, Any],
    data_dir: Path | None = None,
    *,
    create: bool = True,
) -> Path:
    """Resolve one account's mutable workspace without changing request context.

    This is the only cross-account path seam used by administrator read/run
    operations.  Market data never goes through this function and therefore
    remains shared under ``DATA_DIR``.
    """
    from app.config import settings

    base = Path(data_dir or settings.data_dir)
    if principal.get("legacy_home"):
        target = base / "user_data"
    else:
        user_id = str(principal.get("id") or "").strip()
        if not user_id or any(
            ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for ch in user_id
        ):
            raise RuntimeError("invalid authenticated user id")
        target = base / "tenants" / user_id / "user_data"
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def user_data_dir(data_dir: Path | None = None) -> Path:
    return user_data_dir_for(current(), data_dir)


def user_path(*parts: str, data_dir: Path | None = None) -> Path:
    return user_data_dir(data_dir).joinpath(*parts)
