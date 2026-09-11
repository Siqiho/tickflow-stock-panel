from __future__ import annotations

import json
import time

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from app import secrets_store
from app.api.auth import LoginIn, login
from app.config import Settings, settings
from app.services import ai_reports, auth, preferences, user_context, watchlist
from app.services.authorization import require_request_access
from app.services.quote_service import QuoteService


@pytest.fixture
def tenant_runtime(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "auth_owner_username", "admin")
    monkeypatch.setattr(settings, "public_registration_enabled", True)
    monkeypatch.setattr(settings, "public_registration_invite_code", "")
    monkeypatch.setattr(settings, "user_ai_daily_quota", 2)
    monkeypatch.setattr(settings, "user_session_ttl_days", 30)
    monkeypatch.setattr(auth, "_initialized_path", None)
    yield tmp_path
    monkeypatch.setattr(auth, "_initialized_path", None)


def test_public_registration_is_enabled_by_default(monkeypatch: pytest.MonkeyPatch):
    """A fresh deployment exposes signup unless it explicitly opts out."""
    monkeypatch.delenv("PUBLIC_REGISTRATION_ENABLED", raising=False)

    fresh = Settings(_env_file=None)

    assert fresh.public_registration_enabled is True
    assert fresh.public_registration_invite_code == ""
    assert fresh.public_registration_daily_per_ip == 3
    assert fresh.public_max_users == 100


def test_legacy_owner_and_live_session_are_imported(tenant_runtime):
    salt, password_hash = auth._hash_password("owner-secret")
    legacy = tenant_runtime / "user_data" / "auth.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps(
            {
                "password_salt": salt,
                "password_hash": password_hash,
                "sessions": {"legacy-cookie": time.time() + 3600},
            }
        ),
        encoding="utf-8",
    )

    user = auth.authenticate_session("legacy-cookie")

    assert user == {
        "id": "owner",
        "username": "admin",
        "role": "admin",
        "status": "active",
        "legacy_home": True,
        "ai_daily_limit": None,
    }
    assert auth.verify_credentials("owner-secret", "admin")["id"] == "owner"


def test_watchlist_reports_and_secrets_are_isolated_per_user(tenant_runtime):
    auth.set_password("owner-secret")
    alice, _ = auth.register_user("alice", "alice-secret")
    bob, _ = auth.register_user("bob", "bob-secret")

    alice_token = user_context.bind(alice)
    try:
        watchlist.add("600519.SH", "alice")
        ai_reports.save_report({"symbol": "600519.SH", "content": "alice"})
        secrets_store.save({"ai_api_key": "alice-key"})
    finally:
        user_context.reset(alice_token)

    bob_token = user_context.bind(bob)
    try:
        assert watchlist.list_symbols() == []
        assert ai_reports.list_reports() == []
        assert secrets_store.get_ai_key() == ""
        watchlist.add("000001.SZ", "bob")
    finally:
        user_context.reset(bob_token)

    alice_token = user_context.bind(alice)
    try:
        assert [row["symbol"] for row in watchlist.list_symbols()] == ["600519.SH"]
        assert ai_reports.list_reports()[0]["content"] == "alice"
        assert secrets_store.get_ai_key() == "alice-key"
    finally:
        user_context.reset(alice_token)


def test_ai_quota_is_atomic_per_user_and_admin_is_exempt(tenant_runtime):
    auth.set_password("owner-secret")
    alice, _ = auth.register_user("alice", "alice-secret")

    assert auth.consume_quota(alice)["remaining"] == 1
    assert auth.consume_quota(alice)["remaining"] == 0
    with pytest.raises(PermissionError, match="额度"):
        auth.consume_quota(alice)

    owner = auth.verify_credentials("owner-secret", "admin")
    assert owner is not None
    assert auth.consume_quota(owner)["used"] == 0


def test_shared_login_returns_the_authenticated_role_for_frontend_routing(tenant_runtime):
    auth.set_password("owner-secret")
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "headers": [],
            "client": ("127.0.0.1", 43120),
            "server": ("127.0.0.1", 3018),
            "scheme": "http",
            "query_string": b"",
        }
    )

    payload = login(LoginIn(username="admin", password="owner-secret"), request, Response())

    assert payload["authenticated"] is True
    assert payload["user"] == {"id": "owner", "username": "admin", "role": "admin"}


def test_registration_and_password_change_accept_six_characters(tenant_runtime):
    auth.set_password("owner6")

    with pytest.raises(ValueError, match="密码至少 6 位"):
        auth.register_user("short", "12345")

    alice, _ = auth.register_user("alice", "alice6")
    assert auth.verify_credentials("alice6", "alice") is not None

    with pytest.raises(ValueError, match="新密码至少 6 位"):
        auth.change_password(alice["id"], "alice6", "12345")

    auth.change_password(alice["id"], "alice6", "new123")
    assert auth.verify_credentials("alice6", "alice") is None
    assert auth.verify_credentials("new123", "alice") is not None


def test_regular_user_permissions_are_deny_by_default():
    user = {"id": "usr_1", "role": "user"}

    require_request_access(user, "GET", "/api/overview/market")
    require_request_access(user, "GET", "/api/overview/data-readiness")
    require_request_access(user, "GET", "/api/data/status")
    require_request_access(user, "GET", "/api/data/version")
    require_request_access(user, "GET", "/api/data/schema/daily")
    require_request_access(user, "GET", "/api/data/catalog")
    require_request_access(user, "GET", "/api/data/catalog/stock_daily")
    require_request_access(user, "GET", "/api/data/catalog/stock_daily/schema")
    require_request_access(user, "POST", "/api/watchlist")
    require_request_access(user, "POST", "/api/portfolio/holdings")
    require_request_access(user, "POST", "/api/strategies/build")
    require_request_access(user, "POST", "/api/strategies/ai/save")
    require_request_access(user, "DELETE", "/api/strategies/user/ai_alpha")
    require_request_access(user, "DELETE", "/api/backtest/strategy/history/abcdef1234")
    with pytest.raises(HTTPException) as credentials:
        require_request_access(user, "POST", "/api/settings/ai")
    with pytest.raises(HTTPException) as hosted_subscription:
        require_request_access(user, "POST", "/api/settings/ai/subscription")
    with pytest.raises(HTTPException) as hosted_subscription_test:
        require_request_access(user, "POST", "/api/settings/ai/subscription/test")
    with pytest.raises(HTTPException) as shared_oauth_start:
        require_request_access(user, "POST", "/api/settings/ai/xai/device/start")
    with pytest.raises(HTTPException) as shared_oauth_clear:
        require_request_access(user, "DELETE", "/api/settings/ai/xai/session")
    with pytest.raises(HTTPException) as admin_console:
        require_request_access(user, "GET", "/api/admin/users")
    with pytest.raises(HTTPException) as runtime_logs:
        require_request_access(user, "GET", "/api/runtime-logs")
    with pytest.raises(HTTPException) as data_control:
        require_request_access(user, "GET", "/api/data/control-summary")
    with pytest.raises(HTTPException) as data_runs:
        require_request_access(user, "GET", "/api/data/runs")
    with pytest.raises(HTTPException) as data_clear:
        require_request_access(user, "POST", "/api/data/clear")
    with pytest.raises(HTTPException) as data_rescan:
        require_request_access(user, "POST", "/api/data/catalog/rescan")
    with pytest.raises(HTTPException) as legacy_strategy_delete:
        require_request_access(user, "DELETE", "/api/strategies/legacy_python")
    with pytest.raises(HTTPException) as strategy_reload:
        require_request_access(user, "POST", "/api/strategies/reload")
    with pytest.raises(HTTPException) as hermes_gateway_start:
        require_request_access(user, "POST", "/api/hermes-agent/gateway/start")

    assert credentials.value.status_code == 403
    assert hosted_subscription.value.status_code == 403
    assert hosted_subscription_test.value.status_code == 403
    assert shared_oauth_start.value.status_code == 403
    assert shared_oauth_clear.value.status_code == 403
    assert admin_console.value.status_code == 403
    assert runtime_logs.value.status_code == 403
    assert data_control.value.status_code == 403
    assert data_runs.value.status_code == 403
    assert data_clear.value.status_code == 403
    assert data_rescan.value.status_code == 403
    assert legacy_strategy_delete.value.status_code == 403
    assert strategy_reload.value.status_code == 403
    assert hermes_gateway_start.value.status_code == 403


def test_shared_market_preferences_use_owner_values_while_ui_preferences_stay_isolated(
    tenant_runtime,
):
    auth.set_password("owner-secret")
    alice, _ = auth.register_user("alice", "alice-secret")
    bob, _ = auth.register_user("bob", "bob-secret")

    preferences.save(
        {
            "realtime_data_provider": "tickflow",
            "pipeline_universe_scope": "CSI500",
            "pipeline_schedule": {"hour": 16, "minute": 5},
            "nav_order": ["/data", "/watchlist"],
            "feishu_webhook_secret": "owner-only-secret",
        }
    )

    alice_token = user_context.bind(alice)
    try:
        assert preferences.get_realtime_data_provider() == "tickflow"
        assert preferences.get_pipeline_universe_scope() == "CSI500"
        assert preferences.get_pipeline_schedule() == {"hour": 16, "minute": 5}
        assert preferences.get_nav_order() == []
        assert preferences.get_feishu_webhook_secret() == ""
        with pytest.raises(PermissionError, match="administrator-owned"):
            preferences.save_server({"pipeline_universe_scope": "ALL"})
        preferences.set_nav_order(["/watchlist", "/data"])
    finally:
        user_context.reset(alice_token)

    bob_token = user_context.bind(bob)
    try:
        assert preferences.get_realtime_data_provider() == "tickflow"
        assert preferences.get_pipeline_universe_scope() == "CSI500"
        assert preferences.get_pipeline_schedule() == {"hour": 16, "minute": 5}
        assert preferences.get_nav_order() == []
    finally:
        user_context.reset(bob_token)

    assert preferences.get_nav_order() == ["/data", "/watchlist"]
    assert preferences.get_feishu_webhook_secret() == "owner-only-secret"


def test_shared_quote_status_never_reads_request_users_private_watchlist(
    tenant_runtime,
    monkeypatch,
):
    auth.set_password("owner-secret")
    alice, _ = auth.register_user("alice", "alice-secret")
    bob, _ = auth.register_user("bob", "bob-secret")
    service = QuoteService()
    service._symbol_count = 3
    monkeypatch.setattr(service, "realtime_mode", lambda: "watchlist")

    alice_token = user_context.bind(alice)
    try:
        watchlist.add("600519.SH", "alice-only")
        alice_status = service.status()
    finally:
        user_context.reset(alice_token)

    bob_token = user_context.bind(bob)
    try:
        assert watchlist.list_symbols() == []
        bob_status = service.status()
    finally:
        user_context.reset(bob_token)

    assert alice_status == bob_status
    assert alice_status["watchlist_symbol_count"] == 3


def test_public_registration_has_per_source_and_global_caps(tenant_runtime, monkeypatch):
    monkeypatch.setattr(settings, "public_registration_daily_per_ip", 2)
    monkeypatch.setattr(settings, "public_max_users", 2)

    auth.register_user("alice", "alice-secret", registration_source="203.0.113.10")
    auth.register_user("bob", "bob-secret", registration_source="203.0.113.10")

    with pytest.raises(PermissionError, match="上限"):
        auth.register_user("carol", "carol-secret", registration_source="203.0.113.10")
