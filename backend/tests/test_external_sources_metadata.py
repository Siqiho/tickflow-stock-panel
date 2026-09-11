"""外置只读包元数据接口: 只 stat 配置根, 不接受路径, 不扫包。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import data
from app.services import user_context


def _client(role: str = "admin") -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def bind_user(request, call_next):
        token = user_context.bind(
            {"id": f"{role}-meta", "username": role, "role": role},
        )
        try:
            return await call_next(request)
        finally:
            user_context.reset(token)

    app.include_router(data.router)
    return TestClient(app)


def test_unconfigured_does_not_claim_package_ready(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "offline_quantdb_root", None)
    body = _client().get("/api/data/external-readonly-sources").json()
    assert body["status"] == "unconfigured"
    assert body["supported"] == [{"id": "margin_trading", "label": "两融"}]
    assert "不是全包已入库" in body["note"]
    assert "80" not in body["note"]
    assert body["root_path"] is None


def test_inaccessible_root_is_not_configured(tmp_path: Path, monkeypatch) -> None:
    from app.config import settings

    missing = tmp_path / "missing-quantdb"
    monkeypatch.setattr(settings, "offline_quantdb_root", missing)
    body = _client().get("/api/data/external-readonly-sources").json()
    assert body["status"] == "inaccessible"
    assert body["root_path"] == str(missing)
    assert body["supported"][0]["id"] == "margin_trading"


def test_configured_root_only_stats_directory(tmp_path: Path, monkeypatch) -> None:
    from app.config import settings

    root = tmp_path / "quantdb"
    root.mkdir()
    (root / "2_base_sector").mkdir()
    monkeypatch.setattr(settings, "offline_quantdb_root", root)
    body = _client().get("/api/data/external-readonly-sources").json()
    assert body["status"] == "configured"
    assert body["root_path"] == str(root)
    assert "80" not in body["note"]
    assert all(key not in body for key in ("bytes", "files", "capacity", "hashed"))


def test_file_root_is_inaccessible(tmp_path: Path, monkeypatch) -> None:
    from app.config import settings

    file_root = tmp_path / "not-a-dir"
    file_root.write_text("x", encoding="utf-8")
    monkeypatch.setattr(settings, "offline_quantdb_root", file_root)
    body = _client().get("/api/data/external-readonly-sources").json()
    assert body["status"] == "inaccessible"


def test_rejects_arbitrary_path_query(tmp_path: Path, monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "offline_quantdb_root", tmp_path)
    response = _client().get(
        "/api/data/external-readonly-sources",
        params={"path": str(tmp_path / "secret")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "external_readonly_path_not_accepted"

    response = _client().get(
        "/api/data/external-readonly-sources",
        params={"root": "/etc"},
    )
    assert response.status_code == 400


def test_non_admin_does_not_see_root_path(tmp_path: Path, monkeypatch) -> None:
    from app.config import settings

    root = tmp_path / "quantdb"
    root.mkdir()
    monkeypatch.setattr(settings, "offline_quantdb_root", root)
    body = _client("user").get("/api/data/external-readonly-sources").json()
    assert body["status"] == "configured"
    assert "root_path" not in body
