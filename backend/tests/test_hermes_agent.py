from __future__ import annotations

import json

import httpx
import pytest

from app.config import settings
from app.services import xai_oauth
from app.services.hermes_agent import (
    HermesAgentAdapter,
    HermesAgentError,
    HermesConnectionSettings,
    load_connection_settings,
)


def test_load_connection_settings_never_falls_back_to_a_shared_profile(monkeypatch):
    monkeypatch.setattr(settings, "hermes_multiuser_enabled", False)

    with pytest.raises(HermesAgentError, match="多用户 Hermes Agent 尚未启用"):
        load_connection_settings()


async def test_adapter_status_session_history_and_streaming_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "ai_access_mode", "cloud_subscription")
    monkeypatch.setattr(settings, "ai_subscription_enabled", True)
    monkeypatch.setattr(settings, "ai_subscription_plan", "Grok 云订阅")
    monkeypatch.setattr(settings, "ai_provider", "xai")
    monkeypatch.setattr(settings, "ai_model", "grok-4.5")
    monkeypatch.setattr(settings, "ai_api_key", "server-grok-secret")
    monkeypatch.setattr(xai_oauth, "has_oauth", lambda: False)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        if request.url.path == "/p/ot-test/health":
            return httpx.Response(200, json={"status": "ok", "version": "0.20.0"})
        if request.url.path == "/p/ot-test/v1/models":
            return httpx.Response(200, json={"data": [{"id": "ot-test"}]})
        if request.url.path == "/p/ot-test/v1/toolsets":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"name": "memory", "enabled": True},
                        {"name": "skills", "enabled": True},
                        {"name": "terminal", "enabled": False},
                    ]
                },
            )
        if request.url.path == "/p/ot-test/api/sessions" and request.method == "POST":
            assert json.loads(request.content) == {
                "source": "one-trading",
                "model": "grok-4.5",
                "provider": "custom",
                "require_model_lock": True,
            }
            return httpx.Response(
                201,
                json={"session": {"id": "api_test", "title": "one-trading 对话"}},
            )
        if request.url.path == "/p/ot-test/api/sessions" and request.method == "GET":
            assert dict(request.url.params) == {"limit": "50", "offset": "0"}
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "api_test",
                            "title": "one-trading 对话",
                            "preview": "你好",
                            "message_count": 2,
                            "last_active": 1786367567.0,
                        },
                        {"id": "empty", "message_count": 0},
                    ]
                },
            )
        if request.url.path == "/p/ot-test/api/sessions/api_test" and request.method == "PATCH":
            assert json.loads(request.content) == {"title": "收盘复盘"}
            return httpx.Response(
                200,
                json={"session": {"id": "api_test", "title": "收盘复盘"}},
            )
        if request.url.path == "/p/ot-test/api/sessions/api_test" and request.method == "DELETE":
            return httpx.Response(
                200,
                json={"object": "hermes.session.deleted", "id": "api_test", "deleted": True},
            )
        if request.url.path == "/p/ot-test/api/sessions/api_test/messages":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"role": "user", "content": "你好"},
                        {"role": "assistant", "content": "你好, 我是你的助理。"},
                    ]
                },
            )
        if request.url.path == "/p/ot-test/api/sessions/api_test/chat/stream":
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                text=(
                    'event: assistant.delta\ndata: {"delta":"第一段"}\n\n'
                    'event: assistant.delta\ndata: {"delta":"第二段"}\n\n'
                    'event: run.completed\ndata: {"session_id":"api_test","usage":{"output_tokens":2}}\n\n'
                    "event: done\ndata: {}\n\n"
                ),
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(
        base_url="http://hermes.test",
        transport=httpx.MockTransport(handler),
    )
    adapter = HermesAgentAdapter(
        HermesConnectionSettings(
            base_url="http://hermes.test",
            api_key="test-key",
            profile="ot-test",
            api_prefix="/p/ot-test",
            model="grok-4.5",
            provider="custom",
            memory_provider="holographic",
            enabled_mcp_servers=("one-trading-data",),
        ),
        client=client,
    )

    status = await adapter.status()
    session = await adapter.create_session()
    sessions = await adapter.list_sessions()
    renamed_session = await adapter.rename_session(session["id"], "  收盘复盘  ")
    messages = await adapter.get_messages(session["id"])
    events = [event async for event in adapter.stream_chat(session["id"], "继续")]
    deleted_session = await adapter.delete_session(session["id"])
    await client.aclose()

    assert status["connected"] is True
    assert status["profile"] == "ot-test"
    assert status["isolation"] == "dedicated_profile"
    assert status["model"] == "grok-4.5"
    assert status["model_source"] == "server_grok_subscription"
    assert status["model_plan"] == "Grok 云订阅"
    assert status["model_subscription_active"] is True
    assert status["api_model"] == "ot-test"
    assert status["version"] == "0.20.0"
    assert status["enabled_toolsets"] == ["memory", "skills"]
    assert status["memory_enabled"] is True
    assert status["memory_provider"] == "holographic"
    assert status["enabled_mcp_servers"] == ["one-trading-data"]
    assert status["data_tool_enabled"] is True
    assert status["data_view_count"] > 0
    assert messages[1]["content"] == "你好, 我是你的助理。"
    assert [item["id"] for item in sessions] == ["api_test"]
    assert renamed_session["title"] == "收盘复盘"
    assert deleted_session == {
        "object": "hermes.session.deleted",
        "id": "api_test",
        "deleted": True,
    }
    assert [event["type"] for event in events] == ["meta", "delta", "delta", "done"]
    assert events[-1]["usage"]["output_tokens"] == 2


async def test_create_session_retries_without_title_on_hermes_title_conflict(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "ai_access_mode", "cloud_subscription")
    monkeypatch.setattr(settings, "ai_subscription_enabled", True)
    monkeypatch.setattr(settings, "ai_subscription_plan", "Grok")
    monkeypatch.setattr(settings, "ai_provider", "xai")
    monkeypatch.setattr(settings, "ai_model", "grok-4.5")
    monkeypatch.setattr(settings, "ai_api_key", "server-grok-secret")
    monkeypatch.setattr(xai_oauth, "has_oauth", lambda: False)

    posts: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/p/ot-test/v1/models":
            return httpx.Response(200, json={"data": [{"id": "ot-test"}]})
        if request.url.path == "/p/ot-test/api/sessions" and request.method == "POST":
            body = json.loads(request.content)
            posts.append(body)
            if body.get("title") == "你好":
                return httpx.Response(
                    400,
                    json={
                        "error": {
                            "message": "Title already in use by session api_old",
                            "code": "invalid_title",
                        }
                    },
                )
            assert "title" not in body
            return httpx.Response(
                201,
                json={"session": {"id": "api_new", "title": None}},
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(
        base_url="http://hermes.test",
        transport=httpx.MockTransport(handler),
    )
    adapter = HermesAgentAdapter(
        HermesConnectionSettings(
            base_url="http://hermes.test",
            api_key="test-key",
            profile="ot-test",
            api_prefix="/p/ot-test",
            model="grok-4.5",
            provider="custom",
        ),
        client=client,
    )
    session = await adapter.create_session("你好")
    await client.aclose()

    assert session["id"] == "api_new"
    assert len(posts) == 2
    assert posts[0]["title"] == "你好"
    assert "title" not in posts[1]


async def test_adapter_status_reports_gateway_down_separately_from_profile_errors(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "ai_access_mode", "cloud_subscription")
    monkeypatch.setattr(settings, "ai_subscription_enabled", True)
    monkeypatch.setattr(settings, "ai_subscription_plan", "Grok")
    monkeypatch.setattr(settings, "ai_provider", "xai")
    monkeypatch.setattr(settings, "ai_model", "grok-4.5")
    monkeypatch.setattr(settings, "ai_api_key", "server-grok-secret")
    monkeypatch.setattr(xai_oauth, "has_oauth", lambda: False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("All connection attempts failed")

    client = httpx.AsyncClient(
        base_url="http://127.0.0.1:8651",
        transport=httpx.MockTransport(handler),
    )
    adapter = HermesAgentAdapter(
        HermesConnectionSettings(
            base_url="http://127.0.0.1:8651",
            api_key="test-key",
            profile="ot-owner",
            api_prefix="/p/ot-owner",
            model="grok-4.5",
            provider="custom",
        ),
        client=client,
    )

    status = await adapter.status()
    await client.aclose()

    assert status["connected"] is False
    assert status["profile"] == "ot-owner"
    assert status["model_subscription_active"] is True
    assert status["message"] == "Hermes multiplex gateway 当前未运行"
    assert "All connection attempts failed" in status["detail"]


async def test_adapter_status_exposes_admin_start_capability_when_gateway_is_down(
    tmp_path, monkeypatch
):
    from app.services import user_context

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "ai_access_mode", "cloud_subscription")
    monkeypatch.setattr(settings, "ai_subscription_enabled", True)
    monkeypatch.setattr(settings, "ai_subscription_plan", "Grok")
    monkeypatch.setattr(settings, "ai_provider", "xai")
    monkeypatch.setattr(settings, "ai_model", "grok-4.5")
    monkeypatch.setattr(settings, "ai_api_key", "server-grok-secret")
    monkeypatch.setattr(xai_oauth, "has_oauth", lambda: False)
    monkeypatch.setattr(
        "app.services.hermes_runtime.local_gateway_capability",
        lambda: {
            "gateway_kind": "managed_local",
            "gateway_running": False,
            "gateway_startable": True,
            "can_start_gateway": False,
            "base_url": "http://127.0.0.1:8651",
        },
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("All connection attempts failed")

    client = httpx.AsyncClient(
        base_url="http://127.0.0.1:8651",
        transport=httpx.MockTransport(handler),
    )
    adapter = HermesAgentAdapter(
        HermesConnectionSettings(
            base_url="http://127.0.0.1:8651",
            api_key="test-key",
            profile="ot-owner",
            api_prefix="/p/ot-owner",
            model="grok-4.5",
            provider="custom",
        ),
        client=client,
    )

    token = user_context.bind({"id": "owner", "username": "admin", "role": "admin"})
    try:
        status = await adapter.status()
    finally:
        user_context.reset(token)
        await client.aclose()

    assert status["connected"] is False
    assert status["gateway_kind"] == "managed_local"
    assert status["gateway_startable"] is True
    assert status["can_start_gateway"] is True
    assert status["message"] == "Hermes multiplex gateway 当前未运行"
