from __future__ import annotations

import json

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import hermes_model_proxy as model_proxy_api
from app.config import settings
from app.services import xai_oauth
from app.services.hermes_model_proxy import (
    HermesModelProxyError,
    HermesUserConsoleModelAdapter,
    UserConsoleModelRuntime,
    load_server_grok_subscription_runtime,
)


def _server_subscription(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    *,
    api_key: str = "server-grok-secret",
) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "ai_access_mode", "cloud_subscription")
    monkeypatch.setattr(settings, "ai_subscription_enabled", True)
    monkeypatch.setattr(settings, "ai_subscription_plan", "Grok 云订阅")
    monkeypatch.setattr(settings, "ai_provider", "xai")
    monkeypatch.setattr(settings, "ai_model", "grok-4.5")
    monkeypatch.setattr(settings, "ai_api_key", api_key)
    monkeypatch.setattr(xai_oauth, "has_oauth", lambda: False)
    monkeypatch.setattr(xai_oauth, "get_valid_access_token", lambda: None)


async def test_local_server_probe_returns_404_instead_of_spa_html(monkeypatch):
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/hermes-xai/v1/profiles/ot-alice/api/v1/models",
            "headers": [],
            "client": ("127.0.0.1", 43120),
            "server": ("127.0.0.1", 3018),
            "scheme": "http",
            "query_string": b"",
        }
    )
    monkeypatch.setattr(model_proxy_api, "_principal", lambda *_args: {"id": "usr_alice"})

    response = await model_proxy_api.reject_local_model_server_probe(
        "ot-alice",
        request,
        "Bearer profile-bridge-key",
    )

    assert response.status_code == 404


async def test_subscription_failure_does_not_consume_user_quota(monkeypatch):
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/hermes-xai/v1/profiles/ot-alice/responses",
            "headers": [],
            "client": ("127.0.0.1", 43120),
            "server": ("127.0.0.1", 3018),
            "scheme": "http",
            "query_string": b"",
        }
    )
    quota_calls: list[str] = []

    class UnavailableAdapter:
        def require_ready(self) -> None:
            raise HermesModelProxyError("服务器统一 Grok 订阅当前不可用", status_code=503)

    monkeypatch.setattr(model_proxy_api, "_principal", lambda *_args: {"id": "usr_alice"})
    monkeypatch.setattr(model_proxy_api, "HermesUserConsoleModelAdapter", UnavailableAdapter)
    monkeypatch.setattr(
        model_proxy_api,
        "_consume_quota",
        lambda user: quota_calls.append(str(user["id"])),
    )

    with pytest.raises(HTTPException) as exc_info:
        await model_proxy_api.responses("ot-alice", request, "Bearer internal-profile-token")

    assert exc_info.value.status_code == 503
    assert quota_calls == []


def test_local_bearer_auth_uses_constant_interface_without_exposing_key():
    adapter = HermesUserConsoleModelAdapter(
        local_api_key="local-hermes-secret",
        runtime_loader=lambda: UserConsoleModelRuntime(
            provider="xai",
            model="grok-4.5",
            access_token="upstream-token",
        ),
    )

    assert adapter.authorization_is_valid("Bearer local-hermes-secret") is True
    assert adapter.authorization_is_valid("Bearer wrong") is False
    assert adapter.authorization_is_valid(None) is False


def test_runtime_loader_rejects_user_managed_ai_configuration(monkeypatch):
    monkeypatch.setattr(settings, "ai_access_mode", "self_hosted")

    with pytest.raises(HermesModelProxyError, match="服务器统一 Grok 订阅") as exc_info:
        load_server_grok_subscription_runtime()

    assert exc_info.value.status_code == 503


def test_runtime_loader_uses_the_server_subscription_api_key(tmp_path, monkeypatch):
    _server_subscription(monkeypatch, tmp_path)

    runtime = load_server_grok_subscription_runtime()

    assert runtime == UserConsoleModelRuntime(
        provider="xai",
        model="grok-4.5",
        access_token="server-grok-secret",
        base_url="https://api.x.ai/v1",
    )


def test_runtime_loader_uses_server_oauth_for_every_profile(tmp_path, monkeypatch):
    _server_subscription(monkeypatch, tmp_path, api_key="")
    monkeypatch.setattr(xai_oauth, "has_oauth", lambda: True)
    monkeypatch.setattr(xai_oauth, "get_valid_access_token", lambda: "one-server-oauth-token")

    alice_runtime = load_server_grok_subscription_runtime()
    bob_runtime = load_server_grok_subscription_runtime()

    assert alice_runtime.access_token == "one-server-oauth-token"
    assert bob_runtime == alice_runtime


async def test_responses_proxy_locks_model_and_keeps_credentials_on_the_server():
    captured: dict = {}

    class EventStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"type":"response.completed"}\n\n'

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={
                "Content-Type": "text/event-stream",
                "X-Request-Id": "req-test",
                "X-Ignored": "not-forwarded",
            },
            stream=EventStream(),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = HermesUserConsoleModelAdapter(
        local_api_key="local-hermes-secret",
        runtime_loader=lambda: UserConsoleModelRuntime(
            provider="xai",
            model="grok-4.5",
            access_token="upstream-oauth-token",
        ),
        client=client,
    )

    upstream = await adapter.open_responses(
        json.dumps({"model": "stale-model", "stream": True}).encode()
    )
    chunks = [chunk async for chunk in upstream.body]
    await client.aclose()

    assert captured["authorization"] == "Bearer upstream-oauth-token"
    assert captured["payload"]["model"] == "grok-4.5"
    assert captured["payload"]["stream"] is True
    assert b"response.completed" in b"".join(chunks)
    assert upstream.status_code == 200
    assert upstream.headers["content-type"] == "text/event-stream"
    assert upstream.headers["x-request-id"] == "req-test"
    assert "x-ignored" not in upstream.headers


async def test_chat_completions_proxy_uses_hermes_compatible_upstream_path():
    captured: dict = {}

    class EventStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=EventStream(),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = HermesUserConsoleModelAdapter(
        local_api_key="local-hermes-secret",
        runtime_loader=lambda: UserConsoleModelRuntime(
            provider="xai",
            model="grok-4.5",
            access_token="upstream-oauth-token",
        ),
        client=client,
    )

    upstream = await adapter.open_chat_completions(
        json.dumps({"model": "stale-model", "messages": [], "stream": True}).encode()
    )
    chunks = [chunk async for chunk in upstream.body]
    await client.aclose()

    assert captured["path"] == "/v1/chat/completions"
    assert captured["payload"]["model"] == "grok-4.5"
    assert b'"content":"ok"' in b"".join(chunks)
