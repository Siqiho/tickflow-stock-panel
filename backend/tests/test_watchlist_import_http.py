"""Real-auth HTTP tests for watchlist paste/CSV parse (not mock 405, not 401-as-success)."""
from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.api import watchlist as watchlist_api
from app.api.auth import COOKIE_NAME
from app.config import settings
from app.services import auth, user_context, watchlist
from app.services.authorization import require_request_access

IAB_PASTE = "600000.SH\n000001.SZ\n600000.SH"


@pytest.fixture
def import_http(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "auth_owner_username", "admin")
    monkeypatch.setattr(settings, "public_registration_enabled", True)
    monkeypatch.setattr(settings, "public_registration_invite_code", "")
    monkeypatch.setattr(settings, "public_registration_daily_per_ip", 10)
    monkeypatch.setattr(settings, "public_max_users", 10)
    monkeypatch.setattr(auth, "_initialized_path", None)
    inst = tmp_path / "instruments"
    inst.mkdir()
    pl.DataFrame(
        {
            "symbol": ["600000.SH", "000001.SZ"],
            "name": ["浦发银行", "平安银行"],
        }
    ).write_parquet(inst / "part.parquet")

    auth.set_password("owner-secret")
    alice, alice_token = auth.register_user("alice", "alice-secret", registration_source="alice")
    bob, bob_token = auth.register_user("bob", "bob-secret", registration_source="bob")
    owner_token = auth.verify_and_create_session("owner-secret", "admin")
    assert owner_token

    app = FastAPI()
    app.include_router(auth_api.router)
    app.include_router(watchlist_api.router)
    app.state.repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        get_instruments=lambda: pl.DataFrame({"symbol": ["600000.SH"], "name": ["浦发银行"]}),
    )

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
    monkeypatch.setattr(auth, "_initialized_path", None)


def _as(client: TestClient, token: str) -> None:
    client.cookies.set(COOKIE_NAME, token)


def test_unauthenticated_import_codes_is_401_not_success(import_http):
    client = import_http["client"]
    client.cookies.clear()
    resp = client.post("/api/watchlist/import-codes", json={"text": IAB_PASTE})
    assert resp.status_code == 401
    assert resp.json()["detail"]


def test_import_codes_is_post_not_405_and_dedupes_iab_paste(import_http):
    client = import_http["client"]
    _as(client, import_http["alice_token"])
    resp = client.post("/api/watchlist/import-codes", json={"text": IAB_PASTE})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "codes"
    assert body["codes"] == ["600000", "000001"]
    assert body["matched_count"] == 2
    assert body["unmatched_count"] == 0
    assert "raw_text" not in body
    by_code = {c["code"]: c for c in body["candidates"]}
    assert by_code["600000"]["symbol"] == "600000.SH"
    assert by_code["000001"]["symbol"] == "000001.SZ"
    assert watchlist.list_symbols() == []


def test_import_codes_two_users_do_not_write_and_stay_isolated(import_http):
    client = import_http["client"]
    _as(client, import_http["alice_token"])
    alice = client.post("/api/watchlist/import-codes", json={"text": IAB_PASTE})
    assert alice.status_code == 200
    assert watchlist.list_symbols() == []

    _as(client, import_http["bob_token"])
    bob = client.post("/api/watchlist/import-codes", json={"text": IAB_PASTE})
    assert bob.status_code == 200
    assert watchlist.list_symbols() == []

    _as(client, import_http["owner_token"])
    listed = client.get("/api/watchlist")
    assert listed.status_code == 200
    assert listed.json()["symbols"] == []


def test_import_codes_empty_and_junk_are_400(import_http):
    client = import_http["client"]
    _as(client, import_http["alice_token"])
    empty = client.post("/api/watchlist/import-codes", json={"text": "   "})
    assert empty.status_code == 400
    assert "请输入" in empty.json()["detail"]
    junk = client.post("/api/watchlist/import-codes", json={"text": "hello world"})
    assert junk.status_code == 400
    assert "未识别" in junk.json()["detail"]


def test_import_csv_http_roundtrip_and_reject_xlsx(import_http):
    client = import_http["client"]
    _as(client, import_http["alice_token"])
    csv_ok = client.post(
        "/api/watchlist/import-csv",
        files={"file": ("wl.csv", "代码,名称\n600000,浦发银行\n000001,平安银行\n".encode(), "text/csv")},
    )
    assert csv_ok.status_code == 200, csv_ok.text
    assert csv_ok.json()["matched_count"] == 2
    assert "raw_text" not in csv_ok.json()
    assert watchlist.list_symbols() == []

    xlsx = client.post(
        "/api/watchlist/import-csv",
        files={
            "file": (
                "wl.xlsx",
                b"x",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert xlsx.status_code == 400
    assert "仅支持" in xlsx.json()["detail"]
