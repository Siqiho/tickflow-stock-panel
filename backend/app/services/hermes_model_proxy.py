"""Local-only model bridge from Hermes to the user console's active Grok runtime."""

from __future__ import annotations

import json
import secrets
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import ClassVar

import httpx

from app.services.ai_provider import (
    XAI_API_BASE,
    resolve_server_grok_subscription,
)


class HermesModelProxyError(RuntimeError):
    """A credential-free failure at the Hermes-to-server-subscription seam."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class UserConsoleModelRuntime:
    provider: str
    model: str
    access_token: str
    base_url: str = XAI_API_BASE


@dataclass(frozen=True)
class ModelProxyStream:
    status_code: int
    headers: dict[str, str]
    body: AsyncIterator[bytes]


def load_server_grok_subscription_runtime() -> UserConsoleModelRuntime:
    """Resolve the deployment-owned Grok subscription, never a user's AI settings."""
    try:
        runtime = resolve_server_grok_subscription()
    except RuntimeError as exc:
        raise HermesModelProxyError(str(exc), status_code=503) from exc
    return UserConsoleModelRuntime(
        provider=runtime.provider,
        model=runtime.model,
        access_token=runtime.bearer_token,
        base_url=runtime.base_url,
    )


# Compatibility name for code that imported the first local prototype.
load_user_console_model_runtime = load_server_grok_subscription_runtime


class HermesUserConsoleModelAdapter:
    """Bridge every Profile to one server Grok subscription without exposing it."""

    _FORWARDED_RESPONSE_HEADERS: ClassVar[set[str]] = {
        "cache-control",
        "content-type",
        "openai-processing-ms",
        "retry-after",
        "x-request-id",
    }

    def __init__(
        self,
        *,
        runtime_loader: Callable[[], UserConsoleModelRuntime] = load_server_grok_subscription_runtime,
        local_api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._runtime_loader = runtime_loader
        self._runtime: UserConsoleModelRuntime | None = None
        self._local_api_key = local_api_key
        self._client_override = client

    @property
    def model(self) -> str:
        return self._load_runtime().model

    def _load_runtime(self) -> UserConsoleModelRuntime:
        if self._runtime is None:
            self._runtime = self._runtime_loader()
        return self._runtime

    def require_ready(self) -> None:
        """Validate and cache the shared server subscription before quota use."""
        self._load_runtime()

    def authorization_is_valid(self, authorization: str | None) -> bool:
        expected = self._local_api_key
        scheme, _, supplied = (authorization or "").partition(" ")
        return bool(
            expected
            and scheme.lower() == "bearer"
            and supplied
            and secrets.compare_digest(supplied.strip(), expected)
        )

    async def open_responses(self, raw_body: bytes) -> ModelProxyStream:
        """Open a transparent Responses stream locked to the server Grok model."""
        return await self._open_upstream(raw_body, endpoint="responses")

    async def open_chat_completions(self, raw_body: bytes) -> ModelProxyStream:
        """Open the OpenAI-compatible chat stream used by Hermes API routes."""
        return await self._open_upstream(raw_body, endpoint="chat/completions")

    async def _open_upstream(self, raw_body: bytes, *, endpoint: str) -> ModelProxyStream:
        try:
            payload = json.loads(raw_body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HermesModelProxyError("Hermes 模型请求不是有效 JSON", status_code=400) from exc
        if not isinstance(payload, dict):
            raise HermesModelProxyError("Hermes 模型请求必须是 JSON 对象", status_code=400)

        runtime = self._load_runtime()
        payload["model"] = runtime.model
        upstream_url = f"{runtime.base_url.rstrip('/')}/{endpoint}"
        request_headers = {
            "Authorization": f"Bearer {runtime.access_token}",
            "Accept": "text/event-stream, application/json",
            "Content-Type": "application/json",
            "User-Agent": "one-trading-hermes-model-bridge/1.0",
        }

        owns_client = self._client_override is None
        client = self._client_override or httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=10.0),
            trust_env=False,
        )
        try:
            request = client.build_request(
                "POST",
                upstream_url,
                headers=request_headers,
                json=payload,
            )
            response = await client.send(request, stream=True)
        except httpx.HTTPError as exc:
            if owns_client:
                await client.aclose()
            raise HermesModelProxyError("无法连接服务器统一 AI 订阅") from exc

        response_headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() in self._FORWARDED_RESPONSE_HEADERS
            or key.lower().startswith("x-ratelimit-")
        }

        async def body() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_raw():
                    if chunk:
                        yield chunk
            finally:
                await response.aclose()
                if owns_client:
                    await client.aclose()

        return ModelProxyStream(
            status_code=response.status_code,
            headers=response_headers,
            body=body(),
        )
