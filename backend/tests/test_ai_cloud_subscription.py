from __future__ import annotations

import stat

import pytest
from fastapi import HTTPException

from app.api.ai_guard import require_ai_http_access
from app.api.settings import AiSettingsIn, _require_server_ai_login_request, save_ai_settings
from app.config import settings
from app.services import ai_provider, user_context, xai_oauth


def _cloud_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    *,
    enabled: bool,
    api_key: str = "server-secret",
    mock_oauth: bool = True,
) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "ai_access_mode", "cloud_subscription")
    monkeypatch.setattr(settings, "ai_subscription_enabled", enabled)
    monkeypatch.setattr(settings, "ai_subscription_plan", "AI Pro")
    monkeypatch.setattr(settings, "ai_provider", "xai")
    monkeypatch.setattr(settings, "ai_base_url", "https://should-not-be-used.example/v1")
    monkeypatch.setattr(settings, "ai_api_key", api_key)
    monkeypatch.setattr(settings, "ai_model", "grok-4.5")
    monkeypatch.setattr(settings, "ai_86gamestore_api_key", "")
    monkeypatch.setattr(settings, "ai_subrouter_api_key", "")
    if mock_oauth:
        monkeypatch.setattr(xai_oauth, "has_oauth", lambda: False)


def test_cloud_subscription_uses_only_server_managed_xai_credentials(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _cloud_mode(monkeypatch, tmp_path, enabled=True)
    monkeypatch.setattr(
        ai_provider.secrets_store,
        "get_ai_config",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cloud mode read secrets.json")),
    )

    status = ai_provider.ai_access_status()

    assert status == {
        "mode": "cloud_subscription",
        "state": "active",
        "allowed": True,
        "entitled": True,
        "configured": True,
        "provider": "xai",
        "model": "grok-4.5",
        "plan": "AI Pro",
        "message": "云端 Grok 已连接",
        "credential_source": "api_key",
    }
    assert ai_provider._resolve_openai_credentials() == ("server-secret", ai_provider.XAI_API_BASE)
    runtime = ai_provider.resolve_server_grok_subscription()
    assert runtime.provider == "xai"
    assert runtime.model == "grok-4.5"
    assert runtime.bearer_token == "server-secret"
    assert runtime.plan == "AI Pro"


def test_cloud_subscription_fails_closed_without_entitlement(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _cloud_mode(monkeypatch, tmp_path, enabled=False)

    with pytest.raises(HTTPException) as exc_info:
        require_ai_http_access()

    assert exc_info.value.status_code == 402
    assert exc_info.value.detail == {
        "code": "subscription_required",
        "message": "AI 订阅尚未开通",
    }
    with pytest.raises(RuntimeError, match="AI 订阅尚未开通"):
        ai_provider.resolve_server_grok_subscription()


def test_cloud_subscription_fails_closed_without_server_key(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _cloud_mode(monkeypatch, tmp_path, enabled=True, api_key="")

    with pytest.raises(HTTPException) as exc_info:
        require_ai_http_access()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "service_unavailable"


def test_cloud_subscription_accepts_server_oauth_without_api_key(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _cloud_mode(monkeypatch, tmp_path, enabled=True, api_key="")
    monkeypatch.setattr(xai_oauth, "has_oauth", lambda: True)
    monkeypatch.setattr(xai_oauth, "get_valid_access_token", lambda: "server-oauth-token")

    status = ai_provider.ai_access_status()

    assert status["allowed"] is True
    assert status["credential_source"] == "server_oauth"
    assert ai_provider._resolve_openai_credentials() == ("server-oauth-token", ai_provider.XAI_API_BASE)


def test_apk_cannot_replace_cloud_managed_ai_credentials(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _cloud_mode(monkeypatch, tmp_path, enabled=True)

    with pytest.raises(HTTPException) as exc_info:
        save_ai_settings(AiSettingsIn(provider="openai_compat", api_key="client-secret"))

    assert exc_info.value.status_code == 403
    assert "服务器统一管理" in str(exc_info.value.detail)


def test_android_apk_cannot_start_server_oauth(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from starlette.requests import Request

    _cloud_mode(monkeypatch, tmp_path, enabled=True, api_key="")
    request = Request({
        "type": "http",
        "headers": [(b"user-agent", b"Mozilla/5.0 one-trading-android/0.1.68")],
    })

    with pytest.raises(HTTPException) as exc_info:
        _require_server_ai_login_request(request)

    assert exc_info.value.status_code == 403


def test_server_browser_can_start_server_oauth(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from starlette.requests import Request

    _cloud_mode(monkeypatch, tmp_path, enabled=True, api_key="")
    request = Request({
        "type": "http",
        "headers": [(b"user-agent", b"Mozilla/5.0 Chrome/131.0")],
    })

    _require_server_ai_login_request(request)


def test_cloud_oauth_is_shared_by_all_users_and_clear_does_not_resurrect_legacy(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _cloud_mode(monkeypatch, tmp_path, enabled=True, api_key="", mock_oauth=False)
    owner = {"id": "owner", "username": "admin", "role": "admin", "legacy_home": True}
    alice = {"id": "usr_alice", "username": "alice", "role": "user", "legacy_home": False}
    bob = {"id": "usr_bob", "username": "bob", "role": "user", "legacy_home": False}

    # Seed the pre-multi-user owner location, then switch back to hosted mode.
    monkeypatch.setattr(settings, "ai_access_mode", "self_hosted")
    owner_token = user_context.bind(owner)
    try:
        xai_oauth.save_oauth_tokens(
            {
                "access_token": "one-server-oauth-token",
                "refresh_token": "one-server-refresh-token",
                "expires_in": 3600,
            }
        )
    finally:
        user_context.reset(owner_token)
    monkeypatch.setattr(settings, "ai_access_mode", "cloud_subscription")

    for user in (alice, bob):
        token = user_context.bind(user)
        try:
            assert xai_oauth.has_oauth() is True
            assert xai_oauth.get_valid_access_token() == "one-server-oauth-token"
        finally:
            user_context.reset(token)

    bob_token = user_context.bind(bob)
    try:
        xai_oauth.clear_oauth_tokens()
        assert xai_oauth.has_oauth() is False
    finally:
        user_context.reset(bob_token)

    deployment_path = settings.data_dir / "control" / "deployment-secrets.json"
    assert deployment_path.is_file()
    assert stat.S_IMODE(deployment_path.stat().st_mode) == 0o600
    assert "one-server-oauth-token" in (
        settings.data_dir / "user_data" / "secrets.json"
    ).read_text(encoding="utf-8")


def test_cloud_catalog_includes_86game_and_subrouter_without_replacing_grok(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _cloud_mode(monkeypatch, tmp_path, enabled=True)
    monkeypatch.setattr(settings, "ai_86gamestore_api_key", "86game-secret")
    monkeypatch.setattr(settings, "ai_subrouter_api_key", "subrouter-secret")

    catalog = {item["provider"]: item for item in ai_provider.list_server_subscriptions()}

    assert catalog["xai"]["active"] is True
    assert catalog["xai"]["ready"] is True
    assert catalog["86gamestore"]["ready"] is True
    assert catalog["86gamestore"]["models"] == list(ai_provider.GAMESTORE_MODELS)
    assert catalog["subrouter"]["ready"] is True
    assert catalog["subrouter"]["models"] == ["gpt-5.6-sol"]
    assert ai_provider.ai_access_status()["provider"] == "xai"
    assert ai_provider._resolve_openai_credentials() == ("server-secret", ai_provider.XAI_API_BASE)


def test_cloud_can_switch_to_86game_and_subrouter_without_exposing_keys(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _cloud_mode(monkeypatch, tmp_path, enabled=True)
    monkeypatch.setattr(settings, "ai_86gamestore_api_key", "86game-secret")
    monkeypatch.setattr(settings, "ai_subrouter_api_key", "subrouter-secret")

    gamestore = ai_provider.select_server_subscription("86gamestore", "gpt-5.6-terra")
    assert gamestore["provider"] == "86gamestore"
    assert gamestore["model"] == "gpt-5.6-terra"
    assert gamestore["plan"] == "86game"
    assert gamestore["message"] == "云端 86game 已连接"
    assert ai_provider._resolve_openai_credentials() == (
        "86game-secret",
        ai_provider.GAMESTORE_API_BASE,
    )
    runtime = ai_provider.resolve_server_grok_subscription()
    assert runtime.provider == "86gamestore"
    assert runtime.model == "gpt-5.6-terra"
    assert runtime.bearer_token == "86game-secret"

    subrouter = ai_provider.select_server_subscription("subrouter")
    assert subrouter["provider"] == "subrouter"
    assert subrouter["model"] == "gpt-5.6-sol"
    assert subrouter["plan"] == "Subrouter"
    assert ai_provider._resolve_openai_credentials() == (
        "subrouter-secret",
        ai_provider.SUBROUTER_API_BASE,
    )


def test_apk_cannot_switch_hosted_subscription(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from starlette.requests import Request

    from app.api.settings import AiSubscriptionIn, save_ai_subscription

    _cloud_mode(monkeypatch, tmp_path, enabled=True)
    monkeypatch.setattr(settings, "ai_86gamestore_api_key", "86game-secret")
    request = Request({
        "type": "http",
        "headers": [(b"user-agent", b"Mozilla/5.0 one-trading-android/0.1.68")],
    })

    with pytest.raises(HTTPException) as exc_info:
        save_ai_subscription(AiSubscriptionIn(provider="86gamestore"), request)

    assert exc_info.value.status_code == 403
    assert ai_provider.current_ai_provider() == "xai"


def test_admin_can_override_hosted_source_url_and_key(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _cloud_mode(monkeypatch, tmp_path, enabled=True)
    monkeypatch.setattr(settings, "ai_subrouter_api_key", "env-stale-key")

    saved = ai_provider.save_server_subscription_source(
        "subrouter",
        base_url="https://subrouter.ai/v1/",
        api_key="fresh-subrouter-key",
    )

    assert saved["ok"] is True
    assert saved["base_url"] == "https://subrouter.ai/v1"
    assert saved["has_api_key"] is True
    assert ai_provider._cloud_key("subrouter") == "fresh-subrouter-key"
    assert ai_provider._cloud_base_url("subrouter") == "https://subrouter.ai/v1"
    catalog = {item["provider"]: item for item in ai_provider.list_server_subscriptions(include_secrets=True)}
    assert catalog["subrouter"]["api_key_masked"].startswith("fres")
    assert "fresh-subrouter-key" not in str(catalog["subrouter"]["api_key_masked"])


@pytest.mark.asyncio
async def test_probe_server_subscription_does_not_switch_active_source(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _cloud_mode(monkeypatch, tmp_path, enabled=True)
    monkeypatch.setattr(settings, "ai_86gamestore_api_key", "86game-secret")

    class _Message:
        content = "OK"

    class _Choice:
        message = _Message()

    class _Response:
        choices = [_Choice()]

    class _Completions:
        async def create(self, **kwargs):
            assert kwargs["model"] == "gpt-5.6-terra"
            return _Response()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(ai_provider, "_openai_client", lambda *_args, **_kwargs: _Client())

    result = await ai_provider.probe_server_subscription("86gamestore", "gpt-5.6-terra")

    assert result["ok"] is True
    assert result["provider"] == "86gamestore"
    assert result["model"] == "gpt-5.6-terra"
    assert ai_provider.current_ai_provider() == "xai"
    assert ai_provider.current_ai_model() == "grok-4.5"


@pytest.mark.asyncio
async def test_regular_user_cannot_test_hosted_subscription(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from starlette.requests import Request

    from app.api.settings import AiSubscriptionIn, test_ai_subscription

    _cloud_mode(monkeypatch, tmp_path, enabled=True)
    monkeypatch.setattr(settings, "ai_86gamestore_api_key", "86game-secret")
    request = Request({
        "type": "http",
        "headers": [(b"user-agent", b"Mozilla/5.0 Chrome/131.0")],
    })
    token = user_context.bind({
        "id": "usr_regular",
        "username": "alice",
        "role": "user",
    })
    try:
        with pytest.raises(HTTPException) as exc_info:
            await test_ai_subscription(AiSubscriptionIn(provider="86gamestore"), request)
        assert exc_info.value.status_code == 403
    finally:
        user_context.reset(token)


def test_regular_user_cannot_switch_hosted_subscription(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from starlette.requests import Request

    from app.api.settings import AiSubscriptionIn, save_ai_subscription

    _cloud_mode(monkeypatch, tmp_path, enabled=True)
    monkeypatch.setattr(settings, "ai_86gamestore_api_key", "86game-secret")
    request = Request({
        "type": "http",
        "headers": [(b"user-agent", b"Mozilla/5.0 Chrome/131.0")],
    })
    token = user_context.bind({
        "id": "usr_regular",
        "username": "alice",
        "role": "user",
    })
    try:
        with pytest.raises(HTTPException) as exc_info:
            save_ai_subscription(AiSubscriptionIn(provider="86gamestore"), request)
        assert exc_info.value.status_code == 403
        assert "管理员" in str(exc_info.value.detail)
        assert ai_provider.current_ai_provider() == "xai"
    finally:
        user_context.reset(token)
