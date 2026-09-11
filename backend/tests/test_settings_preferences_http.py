"""Real-auth HTTP tests for /api/settings/preferences.

Goes through product ACL + cookie auth + the real settings router.
Does not mock the preferences JSON response. Does not treat 401 as success.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.api import settings as settings_api
from app.api.auth import COOKIE_NAME
from app.config import settings
from app.services import auth, preferences, user_context
from app.services.authorization import require_request_access


@pytest.fixture
def prefs_http(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "auth_owner_username", "admin")
    monkeypatch.setattr(settings, "public_registration_enabled", True)
    monkeypatch.setattr(settings, "public_registration_invite_code", "")
    monkeypatch.setattr(settings, "public_registration_daily_per_ip", 10)
    monkeypatch.setattr(settings, "public_max_users", 10)
    monkeypatch.setattr(auth, "_initialized_path", None)
    preferences._invalidate_cache()
    auth.set_password("owner-secret")
    alice, alice_token = auth.register_user("alice", "alice-secret", registration_source="alice")
    bob, bob_token = auth.register_user("bob", "bob-secret", registration_source="bob")
    owner_token = auth.verify_and_create_session("owner-secret", "admin")
    assert owner_token

    app = FastAPI()
    app.include_router(auth_api.router)
    app.include_router(settings_api.router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    app.state.quote_service = None
    app.state.monitor_engine = None
    app.state.strategy_engine = None

    @app.middleware("http")
    async def _product_acl(request, call_next):
        path = request.url.path
        if path.startswith("/api/auth/"):
            return await call_next(request)
        token = request.cookies.get(COOKIE_NAME)
        user = auth.authenticate_session(token or "")
        if not user:
            return JSONResponse(status_code=401, content={"detail": "未登录或会话已过期"})
        try:
            require_request_access(user, request.method, path)
        except Exception as exc:
            from fastapi import HTTPException
            if isinstance(exc, HTTPException):
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            raise
        request.state.user = user
        ctx = user_context.bind(user)
        try:
            return await call_next(request)
        finally:
            user_context.reset(ctx)

    client = TestClient(app)
    yield {
        "client": client,
        "tmp_path": tmp_path,
        "alice": alice,
        "bob": bob,
        "alice_token": alice_token,
        "bob_token": bob_token,
        "owner_token": owner_token,
    }
    preferences._invalidate_cache()
    monkeypatch.setattr(auth, "_initialized_path", None)


def _as(client: TestClient, token: str) -> None:
    client.cookies.set(COOKIE_NAME, token)


def _assert_preferences_payload(body: dict) -> None:
    assert "sidebar_index_symbols" in body
    assert isinstance(body["sidebar_index_symbols"], list)
    assert "pipeline_index_symbols" in body
    assert "indices_nav_pinned" in body
    assert "nav_order" in body
    assert "realtime_quotes_enabled" in body
    assert "screener_auto_run" in body
    for symbol in body["sidebar_index_symbols"]:
        assert symbol in preferences.SIDEBAR_INDEX_SYMBOLS_DEFAULT


def test_unauthenticated_preferences_get_is_401_not_success(prefs_http):
    client = prefs_http["client"]
    client.cookies.clear()
    resp = client.get("/api/settings/preferences")
    assert resp.status_code == 401
    assert resp.json()["detail"]


def test_admin_and_regular_user_get_preferences_json(prefs_http):
    client = prefs_http["client"]
    _as(client, prefs_http["owner_token"])
    admin = client.get("/api/settings/preferences")
    assert admin.status_code == 200, admin.text
    admin_body = admin.json()
    _assert_preferences_payload(admin_body)
    assert admin_body["sidebar_index_symbols"] == preferences.SIDEBAR_INDEX_SYMBOLS_DEFAULT

    _as(client, prefs_http["alice_token"])
    user = client.get("/api/settings/preferences")
    assert user.status_code == 200, user.text
    user_body = user.json()
    _assert_preferences_payload(user_body)
    assert user_body["sidebar_index_symbols"] == preferences.SIDEBAR_INDEX_SYMBOLS_DEFAULT


def test_own_sidebar_roundtrip_does_not_alias_pipeline_index(prefs_http):
    client = prefs_http["client"]
    _as(client, prefs_http["owner_token"])
    pipeline = client.put(
        "/api/settings/preferences/pipeline-index-symbols",
        json={"symbols": "000300.SH,000905.SH"},
    )
    assert pipeline.status_code == 200, pipeline.text
    assert pipeline.json()["pipeline_index_symbols"] == "000300.SH,000905.SH"

    saved = client.put(
        "/api/settings/preferences/realtime-monitor",
        json={"sidebar_index_symbols": ["000001.SH", "399006.SZ", "999999.SH"]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["sidebar_index_symbols"] == ["000001.SH", "399006.SZ"]
    assert "pipeline_index_symbols" not in saved.json()

    got = client.get("/api/settings/preferences")
    assert got.status_code == 200
    body = got.json()
    assert body["sidebar_index_symbols"] == ["000001.SH", "399006.SZ"]
    assert body["pipeline_index_symbols"] == "000300.SH,000905.SH"


def test_regular_user_sidebar_roundtrip_and_two_user_isolation(prefs_http):
    client = prefs_http["client"]
    _as(client, prefs_http["alice_token"])
    alice_put = client.put(
        "/api/settings/preferences/realtime-monitor",
        json={"sidebar_index_symbols": ["000001.SH"]},
    )
    assert alice_put.status_code == 200, alice_put.text
    assert alice_put.json()["sidebar_index_symbols"] == ["000001.SH"]

    _as(client, prefs_http["bob_token"])
    bob_put = client.put(
        "/api/settings/preferences/realtime-monitor",
        json={"sidebar_index_symbols": ["399001.SZ", "399006.SZ"]},
    )
    assert bob_put.status_code == 200, bob_put.text
    assert bob_put.json()["sidebar_index_symbols"] == ["399001.SZ", "399006.SZ"]

    _as(client, prefs_http["alice_token"])
    alice_get = client.get("/api/settings/preferences")
    assert alice_get.status_code == 200
    assert alice_get.json()["sidebar_index_symbols"] == ["000001.SH"]

    _as(client, prefs_http["bob_token"])
    bob_get = client.get("/api/settings/preferences")
    assert bob_get.status_code == 200
    assert bob_get.json()["sidebar_index_symbols"] == ["399001.SZ", "399006.SZ"]

    _as(client, prefs_http["owner_token"])
    owner_get = client.get("/api/settings/preferences")
    assert owner_get.status_code == 200
    assert owner_get.json()["sidebar_index_symbols"] == preferences.SIDEBAR_INDEX_SYMBOLS_DEFAULT


def test_two_users_same_mtime_ns_same_size_http_do_not_cross(prefs_http):
    client = prefs_http["client"]
    tmp_path = prefs_http["tmp_path"]
    alice = prefs_http["alice"]
    bob = prefs_http["bob"]

    _as(client, prefs_http["alice_token"])
    alice_put = client.put(
        "/api/settings/preferences/realtime-monitor",
        json={"sidebar_index_symbols": ["000001.SH"]},
    )
    assert alice_put.status_code == 200, alice_put.text

    _as(client, prefs_http["bob_token"])
    bob_put = client.put(
        "/api/settings/preferences/realtime-monitor",
        json={"sidebar_index_symbols": ["399001.SZ"]},
    )
    assert bob_put.status_code == 200, bob_put.text

    alice_path = tmp_path / "tenants" / alice["id"] / "user_data" / "preferences.json"
    bob_path = tmp_path / "tenants" / bob["id"] / "user_data" / "preferences.json"
    assert alice_path.is_file() and bob_path.is_file()
    assert alice_path.stat().st_size == bob_path.stat().st_size
    stamp_ns = 1_725_000_000_123_456_789
    os.utime(alice_path, ns=(stamp_ns, stamp_ns))
    os.utime(bob_path, ns=(stamp_ns, stamp_ns))
    assert alice_path.stat().st_mtime_ns == bob_path.stat().st_mtime_ns == stamp_ns
    preferences._invalidate_cache()

    _as(client, prefs_http["alice_token"])
    alice_get = client.get("/api/settings/preferences")
    assert alice_get.status_code == 200
    assert alice_get.json()["sidebar_index_symbols"] == ["000001.SH"]

    _as(client, prefs_http["bob_token"])
    bob_get = client.get("/api/settings/preferences")
    assert bob_get.status_code == 200
    assert bob_get.json()["sidebar_index_symbols"] == ["399001.SZ"]

    _as(client, prefs_http["alice_token"])
    alice_save = client.put(
        "/api/settings/preferences/realtime-monitor",
        json={"sidebar_index_symbols": ["000001.SH", "399006.SZ"]},
    )
    assert alice_save.status_code == 200
    assert alice_save.json()["sidebar_index_symbols"] == ["000001.SH", "399006.SZ"]

    _as(client, prefs_http["bob_token"])
    bob_after = client.get("/api/settings/preferences")
    assert bob_after.status_code == 200
    assert bob_after.json()["sidebar_index_symbols"] == ["399001.SZ"]
    assert "sidebar_index_symbols" not in json.loads(bob_path.read_text(encoding="utf-8")) or (
        json.loads(bob_path.read_text(encoding="utf-8"))["sidebar_index_symbols"] == ["399001.SZ"]
    )
    assert json.loads(alice_path.read_text(encoding="utf-8"))["sidebar_index_symbols"] == [
        "000001.SH",
        "399006.SZ",
    ]


def test_regular_user_cannot_write_server_index_or_shared_settings(prefs_http):
    client = prefs_http["client"]
    _as(client, prefs_http["alice_token"])
    pipeline = client.put(
        "/api/settings/preferences/pipeline-index-symbols",
        json={"symbols": "000001.SH"},
    )
    assert pipeline.status_code == 403
    assert "无权" in pipeline.json()["detail"] or "管理员" in pipeline.json()["detail"]

    quotes = client.put(
        "/api/settings/preferences/realtime-quotes",
        json={"realtime_quotes_enabled": True},
    )
    assert quotes.status_code == 403

    wecom = client.put(
        "/api/settings/preferences/wecom-webhook",
        json={"url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=12345678-1234-1234-1234-1234567890ab"},
    )
    assert wecom.status_code == 403

    _as(client, prefs_http["owner_token"])
    server = client.get("/api/settings/preferences")
    assert server.status_code == 200
    assert server.json()["pipeline_index_symbols"] == ""
    assert server.json()["realtime_quotes_enabled"] is False
