"""Real-auth HTTP tests for minute TickFlow fallback gating.

Goes through product ACL + cookie auth + the real kline router.
Does not call real external endpoints. TickFlow is mocked and counted.
"""
from __future__ import annotations

from datetime import datetime
from threading import Lock
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.api import kline as kline_api
from app.api.auth import COOKIE_NAME
from app.config import settings
from app.services import auth, user_context
from app.services.authorization import require_request_access
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet


class _EmptyMinuteRepo:
    def __init__(self, data_dir):
        self.store = SimpleNamespace(data_dir=data_dir)
        self._write_lock = Lock()

    def get_etf_symbol_set(self):
        return set()

    def get_minute_batch(self, _symbols, _trade_date, asset_type="stock"):
        return pl.DataFrame()


@pytest.fixture
def minute_http(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "auth_owner_username", "admin")
    monkeypatch.setattr(settings, "public_registration_enabled", True)
    monkeypatch.setattr(settings, "public_registration_invite_code", "")
    monkeypatch.setattr(settings, "public_registration_daily_per_ip", 10)
    monkeypatch.setattr(settings, "public_max_users", 10)
    monkeypatch.setattr(auth, "_initialized_path", None)
    monkeypatch.setattr("app.services.preferences.get_minute_batch_compress", lambda: False)
    auth.set_password("owner-secret")
    alice, alice_token = auth.register_user("alice", "alice-secret", registration_source="alice")
    owner_token = auth.verify_and_create_session("owner-secret", "admin")
    assert owner_token

    app = FastAPI()
    app.include_router(auth_api.router)
    app.include_router(kline_api.router)
    app.state.repo = _EmptyMinuteRepo(tmp_path)
    app.state.capabilities = None
    app.state.quote_service = None

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
        "app": app,
        "client": client,
        "alice": alice,
        "alice_token": alice_token,
        "owner_token": owner_token,
    }
    monkeypatch.setattr(auth, "_initialized_path", None)


def _as(client: TestClient, token: str) -> None:
    client.cookies.set(COOKIE_NAME, token)


def _setup_failing_custom(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    provider = MagicMock()
    provider.get_minute.side_effect = RuntimeError("custom source unavailable")
    monkeypatch.setattr(
        "app.services.preferences.get_minute_data_provider",
        lambda: "mock_src",
    )
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, ds: True,
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda name: provider)
    return provider


def _setup_ok_custom(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    provider = MagicMock()
    provider.get_minute.return_value = pl.DataFrame(
        {
            "symbol": ["600519.SH"],
            "datetime": [datetime(2026, 1, 15, 9, 35, 0)],
            "open": [100.0],
            "high": [101.0],
            "low": [99.5],
            "close": [100.5],
            "volume": [1000.0],
            "amount": [100500.0],
        }
    )
    monkeypatch.setattr(
        "app.services.preferences.get_minute_data_provider",
        lambda: "mock_src",
    )
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, ds: True,
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda name: provider)
    return provider


def test_unauthenticated_minute_batch_is_401(minute_http):
    client = minute_http["client"]
    client.cookies.clear()
    resp = client.post(
        "/api/kline/minute-batch",
        json={"symbols": ["600519.SH"], "date": "2026-01-15"},
    )
    assert resp.status_code == 401


def test_regular_user_minute_batch_post_is_403(minute_http):
    client = minute_http["client"]
    _as(client, minute_http["alice_token"])
    resp = client.post(
        "/api/kline/minute-batch",
        json={"symbols": ["600519.SH"], "date": "2026-01-15"},
    )
    assert resp.status_code == 403


def test_auth_custom_fail_missing_capset_tickflow_count_zero(minute_http, monkeypatch):
    provider = _setup_failing_custom(monkeypatch)
    tickflow = MagicMock()
    get_client = MagicMock(return_value=tickflow)
    monkeypatch.setattr("app.services.kline_sync.get_client", get_client)
    minute_http["app"].state.capabilities = None

    client = minute_http["client"]
    _as(client, minute_http["owner_token"])
    resp = client.post(
        "/api/kline/minute-batch",
        json={"symbols": ["600519.SH"], "date": "2026-01-15"},
    )
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json().get("data"), dict)
    provider.get_minute.assert_called()
    get_client.assert_not_called()
    tickflow.klines.batch.assert_not_called()


def test_auth_custom_fail_explicit_no_entitlement_tickflow_count_zero(minute_http, monkeypatch):
    provider = _setup_failing_custom(monkeypatch)
    tickflow = MagicMock()
    get_client = MagicMock(return_value=tickflow)
    monkeypatch.setattr("app.services.kline_sync.get_client", get_client)
    minute_http["app"].state.capabilities = CapabilitySet()

    client = minute_http["client"]
    _as(client, minute_http["owner_token"])
    resp = client.post(
        "/api/kline/minute-batch",
        json={"symbols": ["600519.SH"], "date": "2026-01-15"},
    )
    assert resp.status_code == 200, resp.text
    provider.get_minute.assert_called()
    get_client.assert_not_called()
    tickflow.klines.batch.assert_not_called()


def test_auth_custom_success_without_tickflow_capability(minute_http, monkeypatch):
    provider = _setup_ok_custom(monkeypatch)
    get_client = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr("app.services.kline_sync.get_client", get_client)
    minute_http["app"].state.capabilities = CapabilitySet()

    client = minute_http["client"]
    _as(client, minute_http["owner_token"])
    resp = client.post(
        "/api/kline/minute-batch",
        json={"symbols": ["600519.SH"], "date": "2026-01-15"},
    )
    assert resp.status_code == 200, resp.text
    assert "600519.SH" in resp.json()["data"]
    provider.get_minute.assert_called()
    get_client.assert_not_called()


def test_auth_entitled_custom_fail_stays_fail_closed(minute_http, monkeypatch):
    _setup_failing_custom(monkeypatch)
    tickflow = MagicMock()
    tickflow.klines.batch.return_value = {}
    get_client = MagicMock(return_value=tickflow)
    monkeypatch.setattr("app.services.kline_sync.get_client", get_client)
    minute_http["app"].state.capabilities = CapabilitySet(
        {Cap.KLINE_MINUTE_BATCH: CapabilityLimits()}
    )

    client = minute_http["client"]
    _as(client, minute_http["owner_token"])
    resp = client.post(
        "/api/kline/minute-batch",
        json={"symbols": ["600519.SH"], "date": "2026-01-15"},
    )
    assert resp.status_code == 200, resp.text
    get_client.assert_not_called()
    tickflow.klines.batch.assert_not_called()
