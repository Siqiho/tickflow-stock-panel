"""Read-only administrator insight across isolated product accounts.

The Module exposes account summaries, visible conversation history and user
strategy summaries. It never exposes Hermes write operations and it does not
copy conversation content into the identity control database.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import settings
from app.services import auth
from app.services.hermes_agent import (
    HermesAgentAdapter,
    HermesAgentError,
    HermesConnectionSettings,
)
from app.services.hermes_tenant import HermesTenant, HermesTenantError, HermesTenantRegistry
from app.services.user_strategies import UserStrategyWorkspace

_MAX_SESSION_PAGE = 100


class AdminConsoleError(RuntimeError):
    """Safe failure at the administrator insight seam."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _default_adapter(tenant: HermesTenant) -> HermesAgentAdapter:
    return HermesAgentAdapter(HermesConnectionSettings.from_tenant(tenant))


class AdminConsole:
    """Deep read-only Module for administrator account and chat insight."""

    def __init__(
        self,
        *,
        registry: HermesTenantRegistry | None = None,
        adapter_factory: Callable[[HermesTenant], HermesAgentAdapter] = _default_adapter,
        conversation_probe_timeout_s: float = 2.0,
        probe_concurrency: int = 12,
    ) -> None:
        self._registry = registry or HermesTenantRegistry()
        self._adapter_factory = adapter_factory
        self._probe_timeout_s = max(0.1, float(conversation_probe_timeout_s))
        self._probe_concurrency = max(1, int(probe_concurrency))

    async def list_users(self, admin: dict[str, Any]) -> dict[str, Any]:
        """Return identity, quota, Profile and aggregate conversation status."""
        self._require_admin(admin)
        rows = self._identity_rows()
        semaphore = asyncio.Semaphore(self._probe_concurrency)

        async def add_conversation_summary(row: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                conversation = await self._conversation_summary(row)
            principal = auth.user_by_id(str(row["id"])) or row
            strategy_count = len(
                UserStrategyWorkspace(settings.data_dir, principal).summaries()
            )
            return {**row, **conversation, "strategy_count": strategy_count}

        users = await asyncio.gather(*(add_conversation_summary(row) for row in rows))
        regular_users = [user for user in users if user["role"] == "user"]
        return {
            "users": users,
            "summary": {
                "total_accounts": len(users),
                "regular_users": len(regular_users),
                "active_users_today": sum(
                    1 for user in regular_users if int(user["ai_requests_today"]) > 0
                ),
                "ai_requests_today": sum(
                    int(user["ai_requests_today"]) for user in regular_users
                ),
                "profiles_ready": sum(
                    1 for user in regular_users if user.get("profile_status") == "ready"
                ),
            },
        }

    async def list_user_sessions(
        self,
        admin: dict[str, Any],
        target_user_id: str,
    ) -> dict[str, Any]:
        """Read one ordinary user's visible conversation summaries."""
        self._require_admin(admin)
        target, adapter = self._target_adapter(target_user_id)
        try:
            sessions = await adapter.list_sessions(limit=_MAX_SESSION_PAGE)
        except HermesAgentError as exc:
            raise AdminConsoleError(str(exc), status_code=exc.status_code) from exc
        visible = [self._safe_session(session) for session in sessions]
        return {
            "user": auth.public_user(target),
            "sessions": visible,
            "has_more": len(visible) >= _MAX_SESSION_PAGE,
        }

    async def get_user_messages(
        self,
        admin: dict[str, Any],
        target_user_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        """Read only user/assistant-visible messages from one conversation."""
        self._require_admin(admin)
        safe_session_id = str(session_id or "").strip()
        if not safe_session_id or len(safe_session_id) > 300:
            raise AdminConsoleError("对话标识无效", status_code=422)
        target, adapter = self._target_adapter(target_user_id)
        try:
            messages = await adapter.get_messages(safe_session_id)
        except HermesAgentError as exc:
            raise AdminConsoleError(str(exc), status_code=exc.status_code) from exc
        visible = [
            safe
            for message in messages
            if (safe := self._safe_message(message)) is not None
        ]
        return {
            "user": auth.public_user(target),
            "session_id": safe_session_id,
            "messages": visible,
        }

    def list_user_strategies(
        self,
        admin: dict[str, Any],
        target_user_id: str,
    ) -> dict[str, Any]:
        """Expose target-owned definitions read-only for administrator use."""
        self._require_admin(admin)
        target = self._target_user(target_user_id)
        return {
            "user": auth.public_user(target),
            "strategies": UserStrategyWorkspace(settings.data_dir, target).summaries(),
        }

    def _identity_rows(self) -> list[dict[str, Any]]:
        now = int(time.time())
        today = datetime.now(UTC).date()
        week_start = (today - timedelta(days=6)).isoformat()
        with auth._db() as conn:
            rows = conn.execute(
                """SELECT u.id, u.username, u.role, u.status, u.ai_daily_limit,
                          u.created_at, u.updated_at,
                          hp.profile_name, hp.status AS profile_status,
                          hp.last_error AS profile_last_error,
                          hp.updated_at AS profile_updated_at,
                          COALESCE((
                              SELECT SUM(ud.count) FROM usage_daily ud
                              WHERE ud.user_id=u.id AND ud.metric='ai_requests' AND ud.day=?
                          ), 0) AS ai_requests_today,
                          COALESCE((
                              SELECT SUM(ud.count) FROM usage_daily ud
                              WHERE ud.user_id=u.id AND ud.metric='ai_requests' AND ud.day>=?
                          ), 0) AS ai_requests_7d,
                          COALESCE((
                              SELECT COUNT(*) FROM sessions s
                              WHERE s.user_id=u.id AND s.expires_at>?
                          ), 0) AS active_login_sessions,
                          (SELECT MAX(s.created_at) FROM sessions s WHERE s.user_id=u.id)
                              AS last_login_at
                   FROM users u
                   LEFT JOIN hermes_profiles hp ON hp.user_id=u.id
                   ORDER BY CASE u.role WHEN 'admin' THEN 0 ELSE 1 END,
                            u.created_at ASC, u.username_norm ASC""",
                (today.isoformat(), week_start, now),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for raw in rows:
            row = dict(raw)
            row["ai_daily_limit"] = (
                None
                if row["role"] == "admin"
                else int(
                    row["ai_daily_limit"]
                    if row["ai_daily_limit"] is not None
                    else settings.user_ai_daily_quota
                )
            )
            result.append(row)
        return result

    async def _conversation_summary(self, row: dict[str, Any]) -> dict[str, Any]:
        if not settings.hermes_multiuser_enabled:
            return {
                "conversation_count": None,
                "last_conversation_at": None,
                "conversation_count_capped": False,
                "profile_runtime_status": "disabled",
            }
        if not row.get("profile_name") or row.get("profile_status") != "ready":
            return {
                "conversation_count": 0,
                "last_conversation_at": None,
                "conversation_count_capped": False,
                "profile_runtime_status": "not_ready",
            }
        user = auth.user_by_id(str(row["id"]))
        if user is None:
            return {
                "conversation_count": None,
                "last_conversation_at": None,
                "conversation_count_capped": False,
                "profile_runtime_status": "unavailable",
            }
        try:
            tenant = self._registry.resolve_existing(user)
            sessions = await asyncio.wait_for(
                self._adapter_factory(tenant).list_sessions(limit=_MAX_SESSION_PAGE),
                timeout=self._probe_timeout_s,
            )
        except (
            TimeoutError,
            HermesTenantError,
            HermesAgentError,
            OSError,
            TypeError,
            ValueError,
        ):
            return {
                "conversation_count": None,
                "last_conversation_at": None,
                "conversation_count_capped": False,
                "profile_runtime_status": "unavailable",
            }
        last_active = max(
            (
                float(session.get("last_active") or session.get("started_at") or 0)
                for session in sessions
                if isinstance(session, dict)
            ),
            default=0.0,
        )
        return {
            "conversation_count": len(sessions),
            "last_conversation_at": last_active or None,
            "conversation_count_capped": len(sessions) >= _MAX_SESSION_PAGE,
            "profile_runtime_status": "ready",
        }

    def _target_adapter(
        self,
        target_user_id: str,
    ) -> tuple[dict[str, Any], HermesAgentAdapter]:
        target = self._target_user(target_user_id)
        try:
            tenant = self._registry.resolve_existing(target)
        except HermesTenantError as exc:
            raise AdminConsoleError(str(exc), status_code=exc.status_code) from exc
        return target, self._adapter_factory(tenant)

    @staticmethod
    def _target_user(target_user_id: str) -> dict[str, Any]:
        target = auth.user_by_id(str(target_user_id or "").strip())
        if target is None or target.get("role") != "user":
            raise AdminConsoleError("目标普通用户不存在或已停用", status_code=404)
        return target

    @staticmethod
    def _require_admin(admin: dict[str, Any]) -> None:
        if admin.get("role") != "admin" or not admin.get("id"):
            raise AdminConsoleError("仅服务器管理员可以查看用户使用状况", status_code=403)

    @staticmethod
    def _safe_session(session: dict[str, Any]) -> dict[str, Any]:
        allowed = (
            "id",
            "title",
            "preview",
            "model",
            "started_at",
            "last_active",
            "message_count",
        )
        return {key: session.get(key) for key in allowed if key in session}

    @staticmethod
    def _safe_message(message: dict[str, Any]) -> dict[str, Any] | None:
        role = str(message.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            return None
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            return None
        result: dict[str, Any] = {"role": role, "content": content}
        if message.get("id"):
            result["id"] = str(message["id"])
        timestamp = message.get("timestamp")
        if isinstance(timestamp, (int, float)):
            result["timestamp"] = timestamp
        return result
