"""Server-side Adapter for the authenticated account's Hermes Profile."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
import yaml

from app.services.hermes_tenant import HermesTenant, HermesTenantError, HermesTenantRegistry


class HermesAgentError(RuntimeError):
    """A safe, user-facing failure from the Hermes runtime seam."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class HermesConnectionSettings:
    base_url: str
    api_key: str
    profile: str
    api_prefix: str = ""
    model: str = "grok-4.5"
    provider: str = "custom"
    memory_provider: str = "holographic"
    enabled_mcp_servers: tuple[str, ...] = ()
    session_key: str = ""

    @classmethod
    def from_tenant(cls, tenant: HermesTenant) -> HermesConnectionSettings:
        enabled_mcp_servers: tuple[str, ...] = ()
        try:
            loaded = (
                yaml.safe_load((tenant.profile_home / "config.yaml").read_text(encoding="utf-8"))
                or {}
            )
            mcp_cfg = loaded.get("mcp_servers") if isinstance(loaded, dict) else None
            if isinstance(mcp_cfg, dict):
                data_enabled = any(
                    isinstance(server, dict)
                    and str(server.get("enabled", True)).strip().lower()
                    not in {"false", "0", "no", "off"}
                    and str(name).startswith(("one-trading-data", "ot-data-"))
                    for name, server in mcp_cfg.items()
                )
                enabled_mcp_servers = ("one-trading-data",) if data_enabled else ()
        except (OSError, yaml.YAMLError):
            enabled_mcp_servers = ()
        return cls(
            base_url=tenant.gateway_base_url,
            api_key=tenant.api_key,
            profile=tenant.profile,
            api_prefix=tenant.api_prefix,
            model=tenant.model,
            provider=tenant.provider,
            memory_provider="holographic",
            enabled_mcp_servers=enabled_mcp_servers,
            session_key=tenant.session_key,
        )


def load_connection_settings() -> HermesConnectionSettings:
    """Resolve the request principal to its one-to-one Profile assignment."""
    try:
        return HermesConnectionSettings.from_tenant(HermesTenantRegistry().current())
    except HermesTenantError as exc:
        raise HermesAgentError(str(exc), status_code=exc.status_code) from exc


class HermesAgentAdapter:
    """Hide Hermes auth, session resources, and SSE behind one small Interface."""

    def __init__(
        self,
        settings: HermesConnectionSettings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or load_connection_settings()
        self._client_override = client
        self._profile_verified = False

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
            "X-Hermes-Session-Key": self.settings.session_key,
        }

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client_override is not None:
            yield self._client_override
            return
        async with httpx.AsyncClient(
            base_url=self.settings.base_url,
            headers=self._headers,
            timeout=httpx.Timeout(300.0, connect=5.0),
            trust_env=False,
        ) as client:
            yield client

    def _path(self, path: str) -> str:
        return f"{self.settings.api_prefix}/{path.lstrip('/')}"

    async def _require_profile_route(self, client: httpx.AsyncClient) -> list[str]:
        """Fail closed if Hermes ignored the requested multiplex prefix."""
        response = await client.get(self._path("/v1/models"), headers=self._headers)
        if response.is_error:
            raise HermesAgentError(self._error_message(response))
        payload = response.json()
        model_ids = [
            str(item.get("id"))
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        ]
        if self.settings.profile not in model_ids:
            raise HermesAgentError(
                "Hermes 多 Profile 路由尚未生效, 已拒绝回退到其他用户 Profile",
                status_code=503,
            )
        self._profile_verified = True
        return model_ids

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])[:300]
            if isinstance(payload, dict) and payload.get("detail"):
                return str(payload["detail"])[:300]
        except (ValueError, TypeError):
            pass
        return f"Hermes 返回 HTTP {response.status_code}"

    async def status(self) -> dict[str, Any]:
        """Return a credential-free status payload for the user interface."""
        from app.services import user_context
        from app.services.ai_provider import CLOUD_SUBSCRIPTION_MODE, ai_access_status
        from app.services.hermes_runtime import local_gateway_capability

        capability = local_gateway_capability()
        capability["can_start_gateway"] = bool(
            capability.get("gateway_startable") and user_context.is_admin()
        )
        subscription = ai_access_status()
        cloud = subscription.get("mode") == CLOUD_SUBSCRIPTION_MODE
        provider = str(subscription.get("provider") or "")
        subscription_ready = bool(cloud and subscription.get("allowed"))
        spec_label = str(subscription.get("plan") or "AI")
        model_source = (
            "server_grok_subscription"
            if (not cloud or provider == "xai")
            else "server_subscription"
        )
        model_contract = {
            "model": str(subscription.get("model") or self.settings.model),
            "model_source": model_source,
            "model_plan": spec_label,
            "model_subscription_active": subscription_ready,
        }
        if not subscription_ready:
            if not cloud:
                unavailable = "服务器统一 Grok 订阅当前不可用"
            elif provider == "xai":
                unavailable = str(subscription.get("message") or "服务器统一 Grok 订阅当前不可用")
            else:
                unavailable = str(subscription.get("message") or "服务器统一 AI 订阅当前不可用")
            return {
                "connected": False,
                "profile": self.settings.profile,
                "isolation": "dedicated_profile",
                **model_contract,
                **capability,
                "message": unavailable,
                "detail": str(subscription.get("message") or "云订阅未就绪")[:240],
            }
        try:
            async with self._client() as client:
                health = await client.get(self._path("/health"), headers=self._headers)
                health.raise_for_status()
                model_ids = await self._require_profile_route(client)
                toolsets = await client.get(self._path("/v1/toolsets"), headers=self._headers)
                toolsets.raise_for_status()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            return {
                "connected": False,
                "profile": self.settings.profile,
                "isolation": "dedicated_profile",
                **model_contract,
                **capability,
                "message": "Hermes multiplex gateway 当前未运行",
                "detail": str(exc)[:240],
            }
        except (httpx.HTTPError, HermesAgentError) as exc:
            return {
                "connected": False,
                "profile": self.settings.profile,
                "isolation": "dedicated_profile",
                **model_contract,
                **capability,
                "message": "Hermes one-trading Profile 当前不可用",
                "detail": str(exc)[:240],
            }

        health_payload = health.json()
        tool_payload = toolsets.json()
        enabled_tools = [
            item.get("name")
            for item in tool_payload.get("data", [])
            if isinstance(item, dict) and item.get("enabled") and item.get("name")
        ]
        from app.services.user_console_data import visible_user_console_data_views

        data_tool_enabled = "one-trading-data" in self.settings.enabled_mcp_servers
        return {
            "connected": True,
            "profile": self.settings.profile,
            "isolation": "dedicated_profile",
            **model_contract,
            **capability,
            "api_model": model_ids[0] if model_ids else self.settings.profile,
            "version": health_payload.get("version"),
            "enabled_toolsets": enabled_tools,
            "memory_enabled": "memory" in enabled_tools,
            "memory_provider": self.settings.memory_provider or None,
            "enabled_mcp_servers": list(self.settings.enabled_mcp_servers),
            "data_tool_enabled": data_tool_enabled,
            "data_view_count": len(visible_user_console_data_views()) if data_tool_enabled else 0,
        }

    async def create_session(self, title: str = "") -> dict[str, Any]:
        body: dict[str, Any] = {
            "source": "one-trading",
            "model": self.settings.model,
            "provider": self.settings.provider,
            "require_model_lock": True,
        }
        requested_title = title.strip()[:120]
        if requested_title:
            body["title"] = requested_title
        async with self._client() as client:
            try:
                await self._require_profile_route(client)
                response = await client.post(
                    self._path("/api/sessions"),
                    headers=self._headers,
                    json=body,
                )
                # Hermes enforces globally unique session titles inside a Profile.
                # Prefer an untitled session over failing the first user message.
                if (
                    response.status_code == 400
                    and requested_title
                    and "already in use" in self._error_message(response).lower()
                ):
                    untitled = dict(body)
                    untitled.pop("title", None)
                    response = await client.post(
                        self._path("/api/sessions"),
                        headers=self._headers,
                        json=untitled,
                    )
            except httpx.HTTPError as exc:
                raise HermesAgentError("无法连接 one-trading Hermes Profile") from exc
        if response.is_error:
            raise HermesAgentError(self._error_message(response))
        payload = response.json()
        session = payload.get("session") if isinstance(payload, dict) else None
        if not isinstance(session, dict) or not session.get("id"):
            raise HermesAgentError("Hermes 没有返回有效的 Session")
        return session

    async def list_sessions(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent non-empty sessions for the one-trading history rail."""
        safe_limit = max(1, min(100, int(limit)))
        async with self._client() as client:
            try:
                await self._require_profile_route(client)
                response = await client.get(
                    self._path("/api/sessions"),
                    headers=self._headers,
                    params={"limit": safe_limit, "offset": 0},
                )
            except httpx.HTTPError as exc:
                raise HermesAgentError("无法读取 Hermes 历史对话") from exc
        if response.is_error:
            raise HermesAgentError(self._error_message(response))
        payload = response.json()
        sessions = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(sessions, list):
            return []
        return [
            session
            for session in sessions
            if isinstance(session, dict)
            and session.get("id")
            and int(session.get("message_count") or 0) > 0
        ]

    async def rename_session(self, session_id: str, title: str) -> dict[str, Any]:
        """Persist a user-visible session title through Hermes' native API."""
        safe_id = quote(session_id, safe="")
        normalized_title = title.strip()
        if not normalized_title or len(normalized_title) > 120:
            raise HermesAgentError("对话标题需要 1-120 个字符")
        async with self._client() as client:
            try:
                await self._require_profile_route(client)
                response = await client.patch(
                    self._path(f"/api/sessions/{safe_id}"),
                    headers=self._headers,
                    json={"title": normalized_title},
                )
            except httpx.HTTPError as exc:
                raise HermesAgentError("无法重命名 Hermes 对话") from exc
        if response.is_error:
            raise HermesAgentError(self._error_message(response))
        payload = response.json()
        session = payload.get("session") if isinstance(payload, dict) else None
        if not isinstance(session, dict) or not session.get("id"):
            raise HermesAgentError("Hermes 没有返回有效的 Session")
        return session

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        """Delete a Hermes session after the user-console confirmation step."""
        safe_id = quote(session_id, safe="")
        async with self._client() as client:
            try:
                await self._require_profile_route(client)
                response = await client.delete(
                    self._path(f"/api/sessions/{safe_id}"),
                    headers=self._headers,
                )
            except httpx.HTTPError as exc:
                raise HermesAgentError("无法删除 Hermes 对话") from exc
        if response.is_error:
            raise HermesAgentError(self._error_message(response))
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("deleted") is not True:
            raise HermesAgentError("Hermes 没有确认删除 Session")
        return payload

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        safe_id = quote(session_id, safe="")
        async with self._client() as client:
            try:
                await self._require_profile_route(client)
                response = await client.get(
                    self._path(f"/api/sessions/{safe_id}/messages"),
                    headers=self._headers,
                )
            except httpx.HTTPError as exc:
                raise HermesAgentError("无法读取 Hermes 对话历史") from exc
        if response.is_error:
            raise HermesAgentError(self._error_message(response))
        payload = response.json()
        messages = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(messages, list):
            return []
        return [message for message in messages if isinstance(message, dict)]

    async def stream_chat(
        self,
        session_id: str,
        message: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """Translate Hermes session SSE into one-trading's NDJSON event shape."""
        safe_id = quote(session_id, safe="")
        saw_delta = False
        completed_content = ""
        async with self._client() as client:
            try:
                await self._require_profile_route(client)
                async with client.stream(
                    "POST",
                    self._path(f"/api/sessions/{safe_id}/chat/stream"),
                    headers=self._headers,
                    json={"message": message},
                ) as response:
                    if response.is_error:
                        await response.aread()
                        raise HermesAgentError(self._error_message(response))
                    yield {"type": "meta", "session_id": session_id}
                    event_name = ""
                    async for line in response.aiter_lines():
                        if line.startswith("event:"):
                            event_name = line[6:].strip()
                            continue
                        if not line.startswith("data:"):
                            continue
                        try:
                            payload = json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            continue
                        if event_name == "assistant.delta":
                            delta = str(payload.get("delta") or "")
                            if delta:
                                saw_delta = True
                                yield {"type": "delta", "content": delta}
                        elif event_name in {"tool.started", "tool.completed", "tool.failed"}:
                            yield {
                                "type": "tool",
                                "status": event_name.removeprefix("tool."),
                                "name": payload.get("tool_name"),
                            }
                        elif event_name == "assistant.completed":
                            completed_content = str(payload.get("content") or "")
                        elif event_name == "error":
                            yield {
                                "type": "error",
                                "message": str(payload.get("message") or "Hermes 对话失败"),
                            }
                            return
                        elif event_name == "run.completed":
                            if completed_content and not saw_delta:
                                yield {"type": "delta", "content": completed_content}
                            yield {
                                "type": "done",
                                "session_id": str(payload.get("session_id") or session_id),
                                "usage": payload.get("usage") or {},
                                "runtime": payload.get("runtime") or {},
                            }
                            return
            except HermesAgentError:
                raise
            except httpx.HTTPError as exc:
                raise HermesAgentError("one-trading Hermes 对话连接已中断") from exc

        raise HermesAgentError("Hermes 对话流未正常结束")
