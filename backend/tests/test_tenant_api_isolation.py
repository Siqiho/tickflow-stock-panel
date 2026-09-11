"""Two-user real-API isolation: factors/monitor/settings keep product ACL."""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.api import factors as factors_api
from app.api import monitor_rules as monitor_api
from app.api import settings as settings_api
from app.api.auth import COOKIE_NAME
from app.config import settings
from app.factors.registry import get_factor, unregister_factor
from app.services import auth, user_context
from app.services.authorization import require_request_access
from app.strategy.monitor import MonitorRuleEngine


class _FakeEngine:
    def __init__(self) -> None:
        rows = []
        end = date.today()
        for index in range(40):
            day = end - timedelta(days=39 - index)
            for symbol_id, daily_return in (("A", 0.01), ("B", 0.02), ("C", 0.03)):
                rows.append({
                    "symbol": symbol_id,
                    "date": day,
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.0,
                    "close": (1.0 + daily_return) ** index * 10.0 * (ord(symbol_id) - ord("A") + 1),
                    "volume": 1000.0,
                    "amount": 10000.0,
                    "turnover_rate": 0.02,
                })
        self.panel = pl.DataFrame(rows).sort(["symbol", "date"])

    def load_panel(self, symbols, start, end, *, columns=None, asset_type="stock", **_kwargs):
        frame = self.panel
        if columns is not None:
            for column in columns:
                if column not in frame.columns:
                    frame = frame.with_columns(pl.lit(None).cast(pl.Float64).alias(column))
            frame = frame.select(columns)
        return frame.filter((pl.col("date") >= start) & (pl.col("date") <= end))


@pytest.fixture
def tenant_api(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "auth_owner_username", "admin")
    monkeypatch.setattr(settings, "public_registration_enabled", True)
    monkeypatch.setattr(settings, "public_registration_invite_code", "")
    monkeypatch.setattr(settings, "public_registration_daily_per_ip", 10)
    monkeypatch.setattr(settings, "public_max_users", 10)
    monkeypatch.setattr(auth, "_initialized_path", None)
    auth.set_password("owner-secret")
    alice, alice_token = auth.register_user("alice", "alice-secret", registration_source="alice")
    bob, bob_token = auth.register_user("bob", "bob-secret", registration_source="bob")
    owner_token = auth.verify_and_create_session("owner-secret", "admin")
    assert owner_token

    app = FastAPI()
    app.include_router(auth_api.router)
    app.include_router(factors_api.router)
    app.include_router(monitor_api.router)
    app.include_router(settings_api.router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    app.state.backtest_engine = _FakeEngine()
    app.state.monitor_engine = MonitorRuleEngine()

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
        "engine": app.state.monitor_engine,
    }
    for fid in ("uf_owner_iso",):
        token = user_context.bind({
            "id": "owner", "username": "admin", "role": "admin", "legacy_home": True,
        })
        try:
            try:
                unregister_factor(fid)
            except Exception:
                pass
        finally:
            user_context.reset(token)
    monkeypatch.setattr(auth, "_initialized_path", None)


def _as(client: TestClient, token: str) -> None:
    client.cookies.set(COOKIE_NAME, token)


def test_regular_users_keep_admin_only_acl(tenant_api):
    client = tenant_api["client"]
    _as(client, tenant_api["alice_token"])
    listed = client.get("/api/factors")
    assert listed.status_code == 200
    detail = client.get("/api/factors/rsi_14")
    assert detail.status_code == 200
    assert detail.json()["factor"]["id"] == "rsi_14"
    assert client.post("/api/factors/custom", json={
        "label": "alice", "formula": "close + 1",
    }).status_code == 403
    assert client.post("/api/monitor-rules", json={
        "id": "alice_rule",
        "name": "alice",
        "type": "price",
        "symbols": ["600519.SH"],
        "conditions": [{"field": "close", "op": ">", "value": 1}],
    }).status_code == 403
    assert client.put("/api/settings/preferences/wecom-webhook", json={
        "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=12345678-1234-1234-1234-1234567890ab",
    }).status_code == 403


def test_owner_factor_save_publish_compute_is_isolated_from_alice(tenant_api):
    client = tenant_api["client"]
    _as(client, tenant_api["owner_token"])
    created = client.post("/api/factors/custom", json={
        "id": "uf_owner_iso",
        "label": "owner iso",
        "formula": "close + 1",
    })
    assert created.status_code == 200, created.text
    detail = client.get("/api/factors/uf_owner_iso")
    assert detail.status_code == 200
    published = client.post("/api/factors/custom/uf_owner_iso/status", json={"status": "active"})
    assert published.status_code == 200
    trial = client.post("/api/factors/trial", json={"formula": "close + 1"})
    assert trial.status_code == 200
    owner_ids = {item["id"] for item in client.get("/api/factors").json()["factors"]}
    assert "uf_owner_iso" in owner_ids

    _as(client, tenant_api["alice_token"])
    alice_ids = {item["id"] for item in client.get("/api/factors").json()["factors"]}
    assert "uf_owner_iso" not in alice_ids
    assert client.get("/api/factors/uf_owner_iso").status_code == 404
    token = user_context.bind(tenant_api["alice"])
    try:
        assert get_factor("uf_owner_iso") is None
    finally:
        user_context.reset(token)


def test_monitor_engine_does_not_overwrite_other_user_slice(tenant_api):
    client = tenant_api["client"]
    engine = tenant_api["engine"]
    _as(client, tenant_api["owner_token"])
    saved = client.post("/api/monitor-rules", json={
        "id": "owner_rule",
        "name": "owner price",
        "type": "price",
        "scope": "symbols",
        "symbols": ["600519.SH"],
        "conditions": [{"field": "close", "op": ">", "value": 1}],
    })
    assert saved.status_code == 200, saved.text
    assert engine.get_rule("owner_rule", "owner") is not None
    engine.set_rules_for_user(tenant_api["alice"]["id"], [])
    assert engine.get_rule("owner_rule", "owner") is not None
    _as(client, tenant_api["alice_token"])
    assert client.get("/api/monitor-rules").status_code == 403
    listed = client.get("/api/factors")
    assert listed.status_code == 200
