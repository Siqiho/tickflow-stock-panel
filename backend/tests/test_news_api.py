from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import news as news_api
from app.services import news as news_service
from app.services import user_context
from app.services.atomic_io import atomic_write_json


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    app.include_router(news_api.router)
    return TestClient(app)


def test_get_endpoints_are_local_only(tmp_path: Path, monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("GET must not fetch")

    monkeypatch.setattr(news_service, "fetch_cls", boom)
    monkeypatch.setattr(news_service, "refresh_departments", boom)
    client = _client(tmp_path)
    market = client.get("/api/news/market")
    policy = client.get("/api/news/policy")
    depts = client.get("/api/news/policy/departments")
    keys = client.get("/api/news/policy/key-departments")
    assert market.status_code == 200
    assert market.json()["sources"]["cls"]["items"] == []
    assert policy.json()["from_cache"] is True
    assert depts.json()["departments"] == []
    assert keys.json()["is_default"] is True


def test_refresh_and_local_search_roundtrip(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path)
    monkeypatch.setattr(
        news_service,
        "refresh_market_source",
        lambda data_dir, source, fetcher=None: {
            "source": source,
            "label": "财联社电报",
            "ok": True,
            "error": None,
            "items": [{"title": "电报", "content": "正文", "url": "https://www.cls.cn/telegraph/1"}],
            "from_cache": False,
        },
    )
    refreshed = client.post("/api/news/market/refresh", json={"source": "cls"})
    assert refreshed.status_code == 200
    assert refreshed.json()["sources"]["cls"]["ok"] is True

    atomic_write_json(
        {
            "items": [
                {"title": "能源局发布新能源政策", "url": "https://www.nea.gov.cn/a", "date": "2026-09-08", "source": "国家能源局"},
            ],
            "updated_at": "2026-09-09T10:00:00+08:00",
            "last_refresh": {},
        },
        news_service._policy_items_path(tmp_path),
        indent=2,
    )
    searched = client.get("/api/news/policy", params={"keyword": "新能源", "department": "能源", "page_size": 200})
    assert searched.status_code == 200
    assert searched.json()["search_mode"] is True
    assert searched.json()["items"][0]["title"] == "能源局发布新能源政策"


def test_get_policy_clears_spliced_dates_without_writing(tmp_path: Path, monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("GET must not fetch")

    monkeypatch.setattr(news_service, "fetch_cls", boom)
    monkeypatch.setattr(news_service, "refresh_departments", boom)
    monkeypatch.setattr(news_service, "fetch_department_policy", boom)
    path = news_service._policy_items_path(tmp_path)
    atomic_write_json(
        {
            "items": [
                {
                    "title": "民委月份目录加编号",
                    "url": "https://www.nea.gov.cn/seac/xwzx/202609/1194319.shtml",
                    "date": "2026-09-11",
                    "source": "国家民族事务委员会",
                },
                {
                    "title": "紧凑日期政策标题足够长",
                    "url": "https://www.nea.gov.cn/t20260909_1.html",
                    "date": "2026-09-09",
                    "source": "国家能源局",
                },
            ],
            "updated_at": "2026-09-09T10:00:00+08:00",
            "last_refresh": {},
        },
        path,
        indent=2,
    )
    before = path.read_bytes()
    mtime = path.stat().st_mtime_ns
    time.sleep(0.01)
    client = _client(tmp_path)
    payload = client.get("/api/news/policy")
    assert payload.status_code == 200
    items = payload.json()["items"]
    by_title = {item["title"]: item["date"] for item in items}
    assert by_title["民委月份目录加编号"] == ""
    assert by_title["紧凑日期政策标题足够长"] == "2026-09-09"
    assert payload.json()["from_cache"] is True
    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == mtime


def test_get_keeps_long_id_list_date_without_writing(tmp_path: Path, monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("GET must not fetch")

    monkeypatch.setattr(news_service, "fetch_cls", boom)
    monkeypatch.setattr(news_service, "refresh_departments", boom)
    monkeypatch.setattr(news_service, "fetch_department_policy", boom)
    path = news_service._policy_items_path(tmp_path)
    atomic_write_json(
        {
            "items": [
                {
                    "title": "央行长编号真实列表日标题足够长了",
                    "url": "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/2026090909080511735/index.html",
                    "date": "2026-09-09",
                    "date_source": "list",
                    "source": "中国人民银行",
                },
                {
                    "title": "民委月份目录加编号",
                    "url": "https://www.nea.gov.cn/seac/xwzx/202609/1194319.shtml",
                    "date": "2026-09-11",
                    "source": "国家民族事务委员会",
                },
            ],
            "updated_at": "2026-09-09T10:00:00+08:00",
            "last_refresh": {},
        },
        path,
        indent=2,
    )
    before = path.read_bytes()
    mtime = path.stat().st_mtime_ns
    time.sleep(0.01)
    client = _client(tmp_path)
    payload = client.get("/api/news/policy")
    assert payload.status_code == 200
    items = payload.json()["items"]
    by_title = {item["title"]: item for item in items}
    assert by_title["央行长编号真实列表日标题足够长了"]["date"] == "2026-09-09"
    assert by_title["民委月份目录加编号"]["date"] == ""
    assert payload.json()["from_cache"] is True
    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == mtime


def test_key_departments_api_uses_current_user(tmp_path: Path) -> None:
    client = _client(tmp_path)
    token = user_context.bind({"id": "carol", "username": "carol", "role": "user"})
    try:
        saved = client.post("/api/news/policy/key-departments", json={"departments": ["财政部"]})
        assert saved.status_code == 200
        assert saved.json()["departments"] == ["财政部"]
        assert saved.json()["is_default"] is False
        reset = client.post("/api/news/policy/key-departments", json={"departments": []})
        assert reset.json()["is_default"] is True
    finally:
        user_context.reset(token)
