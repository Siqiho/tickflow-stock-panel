from __future__ import annotations

import threading
from pathlib import Path

import pytest

from app.services import news as news_service
from app.services import user_context
from app.services.free_sources.news_public import SourceFetchError
from app.services.atomic_io import atomic_write_json


def _item(source: str, title: str, when: str) -> dict:
    return {
        "id": title,
        "source": source,
        "title": title,
        "content": title,
        "time": "10:00:00",
        "data_time": when,
        "url": "https://www.cls.cn/telegraph/1",
        "subjects": ["宏观"],
        "stocks": [],
        "is_red": True,
        "sentiment": "看涨",
    }


def test_get_market_never_calls_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("GET must not fetch")

    monkeypatch.setattr(news_service, "fetch_cls", boom)
    monkeypatch.setattr(news_service, "fetch_sina", boom)
    monkeypatch.setattr(news_service, "fetch_foreign", boom)
    payload = news_service.read_market(tmp_path)
    assert payload["sources"]["cls"]["items"] == []
    assert payload["sources"]["cls"]["from_cache"] is True


def test_failed_refresh_keeps_previous_items(tmp_path: Path) -> None:
    news_service.refresh_market_source(
        tmp_path,
        "cls",
        fetcher=lambda: [_item("财联社电报", "旧电报", "2026-09-09T10:00:00+08:00")],
    )
    failed = news_service.refresh_market_source(
        tmp_path,
        "cls",
        fetcher=lambda: (_ for _ in ()).throw(SourceFetchError("cls", "timeout")),
    )
    assert failed["preserved"] is True
    assert failed["ok"] is False
    assert failed["items"][0]["title"] == "旧电报"
    cached = news_service.read_market_source(tmp_path, "cls")
    assert cached["items"][0]["title"] == "旧电报"
    assert cached["error"]


def test_market_dedupes_title_or_content(tmp_path: Path) -> None:
    news_service.refresh_market_source(
        tmp_path,
        "sina",
        fetcher=lambda: [
            _item("新浪财经", "同一标题", "2026-09-09T10:00:00+08:00"),
            _item("新浪财经", "同一标题", "2026-09-09T10:01:00+08:00"),
        ],
    )
    assert len(news_service.read_market_source(tmp_path, "sina")["items"]) == 1


def test_policy_local_search_and_pagination(tmp_path: Path) -> None:
    news_service._write_policy_store(
        tmp_path,
        {
            "items": [
                {"title": "能源局发布新能源政策", "url": "https://www.nea.gov.cn/a", "date": "2026-09-08", "source": "国家能源局"},
                {"title": "央行公开市场操作", "url": "https://www.pbc.gov.cn/a", "date": "2026-09-07", "source": "中国人民银行"},
                {"title": "能源局另一份文件", "url": "https://www.nea.gov.cn/b", "date": "2026-09-06", "source": "国家能源局"},
            ],
            "updated_at": "2026-09-09T10:00:00+08:00",
            "last_refresh": {},
        },
    )
    searched = news_service.query_policy(tmp_path, department="能源", keyword="新能源", page=1, page_size=200)
    assert searched["search_mode"] is True
    assert [item["title"] for item in searched["items"]] == ["能源局发布新能源政策"]
    page1 = news_service.query_policy(tmp_path, page=1, page_size=2)
    assert page1["has_more"] is True
    page2 = news_service.query_policy(tmp_path, page=2, page_size=2)
    assert page2["has_more"] is False
    assert page2["total"] == 3


def test_failed_policy_refresh_does_not_drop_history(tmp_path: Path) -> None:
    news_service._write_policy_store(
        tmp_path,
        {
            "items": [
                {"title": "已入库政策标题足够长了", "url": "https://www.nea.gov.cn/old", "date": "2026-09-01", "source": "国家能源局"},
            ],
            "updated_at": "2026-09-01T10:00:00+08:00",
            "last_refresh": {},
        },
    )
    news_service._departments_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    from app.services.atomic_io import atomic_write_json

    atomic_write_json(
        {
            "departments": [{"name": "国家能源局", "url": "https://www.nea.gov.cn/"}],
            "ok": True,
            "error": None,
            "fetched_at": "2026-09-09T10:00:00+08:00",
        },
        news_service._departments_path(tmp_path),
        indent=2,
    )

    def boom(*_args, **_kwargs):
        raise SourceFetchError("policy", "site down")

    result = news_service.refresh_policy(tmp_path, department="国家能源局", fetcher=boom)
    assert result["preserved"] is True
    assert result["items"][0]["title"] == "已入库政策标题足够长了"


def test_query_policy_clears_month_dir_id_and_keeps_unknown_last(tmp_path: Path) -> None:
    news_service._write_policy_store(
        tmp_path,
        {
            "items": [
                {
                    "title": "民委月份目录加编号被拼成未来日",
                    "url": "https://www.nea.gov.cn/seac/xwzx/202609/1194319.shtml",
                    "date": "2026-09-11",
                    "source": "国家民族事务委员会",
                },
                {
                    "title": "另一月份目录加编号被拼成日期",
                    "url": "https://www.nea.gov.cn/202607/1200abc.shtml",
                    "date": "2026-07-12",
                    "source": "国家民族事务委员会",
                },
                {
                    "title": "紧凑URL日期政策标题足够长",
                    "url": "https://www.nea.gov.cn/202609/t20260909_1.html",
                    "date": "2026-09-09",
                    "source": "国家能源局",
                },
                {
                    "title": "列表来源日期不是URL拼出来的",
                    "url": "https://www.nea.gov.cn/202609/5ba25c81e0bb4614adf43f48a344dea5.shtml",
                    "date": "2026-09-08",
                    "source": "国家烟草专卖局",
                },
                {
                    "title": "没有可靠日期的政策标题足够长",
                    "url": "https://www.nea.gov.cn/unknown",
                    "date": "",
                    "source": "教育部",
                },
            ],
            "updated_at": "2026-09-09T10:00:00+08:00",
            "last_refresh": {},
        },
    )
    page = news_service.query_policy(tmp_path, page=1, page_size=100)
    by_title = {item["title"]: item["date"] for item in page["items"]}
    assert by_title["民委月份目录加编号被拼成未来日"] == ""
    assert by_title["另一月份目录加编号被拼成日期"] == ""
    assert by_title["紧凑URL日期政策标题足够长"] == "2026-09-09"
    assert by_title["列表来源日期不是URL拼出来的"] == "2026-09-08"
    assert by_title["没有可靠日期的政策标题足够长"] == ""
    assert page["items"][0]["title"] == "紧凑URL日期政策标题足够长"
    assert page["items"][-1]["date"] == ""


def test_scrub_unproven_policy_dates_persists_empty_splices(tmp_path: Path) -> None:
    from app.services.atomic_io import atomic_write_json

    atomic_write_json(
        {
            "items": [
                {
                    "title": "民委错误日期",
                    "url": "https://www.nea.gov.cn/seac/xwzx/202609/1194319.shtml",
                    "date": "2026-09-11",
                    "source": "国家民族事务委员会",
                },
                {
                    "title": "真实紧凑日期",
                    "url": "https://www.nea.gov.cn/t20260909_1.html",
                    "date": "2026-09-09",
                    "source": "国家能源局",
                },
            ],
            "updated_at": "2026-09-09T10:00:00+08:00",
            "last_refresh": {},
        },
        news_service._policy_items_path(tmp_path),
        indent=2,
    )
    result = news_service.scrub_unproven_policy_dates(tmp_path, today="2026-09-09")
    assert result["cleared"] == 1
    stored = news_service._read_json(news_service._policy_items_path(tmp_path))
    by_title = {item["title"]: item["date"] for item in stored["items"]}
    assert by_title["民委错误日期"] == ""
    assert by_title["真实紧凑日期"] == "2026-09-09"


def test_query_policy_does_not_write_cache(tmp_path: Path) -> None:
    path = news_service._policy_items_path(tmp_path)
    news_service._write_policy_store(
        tmp_path,
        {
            "items": [
                {
                    "title": "民委错误日期标题足够长了",
                    "url": "https://www.nea.gov.cn/seac/xwzx/202609/1194319.shtml",
                    "date": "2026-09-11",
                    "source": "国家民族事务委员会",
                }
            ],
            "updated_at": "2026-09-09T10:00:00+08:00",
            "last_refresh": {},
        },
    )
    before = path.read_bytes()
    mtime = path.stat().st_mtime_ns
    page = news_service.query_policy(tmp_path)
    assert page["items"][0]["date"] == ""
    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == mtime


def test_query_policy_does_not_rank_invalid_dates_first(tmp_path: Path) -> None:
    news_service._write_policy_store(
        tmp_path,
        {
            "items": [
                {"title": "教育部栏目编号被误读", "url": "https://www.nea.gov.cn/fbh/live/2026/78355/", "date": "2026-78-35", "source": "教育部"},
                {"title": "能源局真实日期政策标题足够长", "url": "https://www.nea.gov.cn/real", "date": "2026-09-04", "source": "国家能源局"},
                {"title": "专题页没有可靠日期标题足够长", "url": "https://www.nea.gov.cn/2026/2026_zt09/", "date": "2026-20-26", "source": "教育部"},
            ],
            "updated_at": "2026-09-09T10:00:00+08:00",
            "last_refresh": {},
        },
    )
    page = news_service.query_policy(tmp_path, page=1, page_size=100)
    assert page["items"][0]["title"] == "能源局真实日期政策标题足够长"
    assert page["items"][0]["date"] == "2026-09-04"
    assert all(item["date"] != "2026-78-35" for item in page["items"])
    assert all(item["date"] != "2026-20-26" for item in page["items"])
    moe = [item for item in page["items"] if item["source"] == "教育部"]
    assert moe and all(item["date"] == "" for item in moe)


def test_all_department_refresh_keeps_more_than_display_page(tmp_path: Path) -> None:
    news_service._departments_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    from app.services.atomic_io import atomic_write_json

    atomic_write_json(
        {
            "departments": [{"name": "国家能源局", "url": "https://www.nea.gov.cn/"}],
            "ok": True,
            "error": None,
            "fetched_at": "2026-09-09T10:00:00+08:00",
        },
        news_service._departments_path(tmp_path),
        indent=2,
    )
    incoming = [
        {
            "title": f"政策标题足够长{index:03d}",
            "url": f"https://www.nea.gov.cn/{index}",
            "date": "2026-09-08",
            "source": "国家能源局",
        }
        for index in range(130)
    ]

    def fake_all(*_args, **_kwargs):
        return incoming, []

    result = news_service.refresh_policy(tmp_path, department="", fetcher=fake_all)
    assert result["total"] == 130
    assert result["has_more"] is True
    assert len(result["items"]) == 100
    stored = news_service.query_policy(tmp_path, page=2, page_size=100)
    assert stored["total"] == 130
    assert len(stored["items"]) == 30


def test_key_departments_are_isolated_by_user(tmp_path: Path) -> None:
    token_a = user_context.bind({"id": "alice", "username": "alice", "role": "user"})
    try:
        news_service.save_key_departments(["国家能源局"], tmp_path)
        assert news_service.read_key_departments(tmp_path)["departments"] == ["国家能源局"]
        assert news_service.read_key_departments(tmp_path)["is_default"] is False
    finally:
        user_context.reset(token_a)

    token_b = user_context.bind({"id": "bob", "username": "bob", "role": "user"})
    try:
        saved = news_service.read_key_departments(tmp_path)
        assert saved["is_default"] is True
        assert "中国人民银行" in saved["departments"]
        news_service.save_key_departments([], tmp_path)
        assert news_service.read_key_departments(tmp_path)["is_default"] is True
    finally:
        user_context.reset(token_b)

    token_a2 = user_context.bind({"id": "alice", "username": "alice", "role": "user"})
    try:
        assert news_service.read_key_departments(tmp_path)["departments"] == ["国家能源局"]
    finally:
        user_context.reset(token_a2)


def _write_two_departments(tmp_path: Path) -> None:
    news_service._departments_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        {
            "departments": [
                {"name": "国家能源局", "url": "https://www.nea.gov.cn/"},
                {"name": "中国人民银行", "url": "http://www.pbc.gov.cn/"},
            ],
            "ok": True,
            "error": None,
            "fetched_at": "2026-09-09T10:00:00+08:00",
        },
        news_service._departments_path(tmp_path),
        indent=2,
    )


def test_query_keeps_long_id_list_date_and_unknown_empty(tmp_path: Path) -> None:
    path = news_service._policy_items_path(tmp_path)
    news_service._write_policy_store(
        tmp_path,
        {
            "items": [
                {
                    "title": "央行副行长出席国际清算银行行长例会标题足够长",
                    "url": "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/2026090909080511735/index.html",
                    "date": "2026-09-09",
                    "date_source": "list",
                    "source": "中国人民银行",
                },
                {
                    "title": "另一条央行长编号没有日期标题足够长了",
                    "url": "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/2026082118245286995/index.html",
                    "date": "",
                    "source": "中国人民银行",
                },
                {
                    "title": "民委月份目录加编号被拼成未来日",
                    "url": "https://www.nea.gov.cn/seac/xwzx/202609/1194319.shtml",
                    "date": "2026-09-11",
                    "source": "国家民族事务委员会",
                },
            ],
            "updated_at": "2026-09-09T10:00:00+08:00",
            "last_refresh": {},
        },
    )
    before = path.read_bytes()
    mtime = path.stat().st_mtime_ns
    page = news_service.query_policy(tmp_path)
    by_title = {item["title"]: item for item in page["items"]}
    assert by_title["央行副行长出席国际清算银行行长例会标题足够长"]["date"] == "2026-09-09"
    assert by_title["央行副行长出席国际清算银行行长例会标题足够长"]["date_source"] == "list"
    assert by_title["另一条央行长编号没有日期标题足够长了"]["date"] == ""
    assert by_title["民委月份目录加编号被拼成未来日"]["date"] == ""
    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == mtime


def test_legacy_long_id_list_date_without_date_source_is_kept(tmp_path: Path) -> None:
    news_service._write_policy_store(
        tmp_path,
        {
            "items": [
                {
                    "title": "央行长编号与真实列表日碰撞标题足够长",
                    "url": "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/2026090909080511735/index.html",
                    "date": "2026-09-09",
                    "source": "中国人民银行",
                }
            ],
            "updated_at": "2026-09-09T10:00:00+08:00",
            "last_refresh": {},
        },
    )
    page = news_service.query_policy(tmp_path)
    assert page["items"][0]["date"] == "2026-09-09"


def test_policy_merge_keeps_same_title_from_other_department(tmp_path: Path) -> None:
    _write_two_departments(tmp_path)
    news_service._write_policy_store(
        tmp_path,
        {
            "items": [
                {
                    "title": "中国人民银行 国家外汇管理局发布联合通知标题足够长了",
                    "url": "https://www.safe.gov.cn/safe/2026/0814/27784.html",
                    "date": "2026-08-14",
                    "source": "国家外汇管理局",
                }
            ],
            "updated_at": "2026-09-01T10:00:00+08:00",
            "last_refresh": {},
        },
    )
    news_service.refresh_policy(
        tmp_path,
        department="中国人民银行",
        fetcher=lambda *_args, **_kwargs: [
            {
                "title": "中国人民银行 国家外汇管理局发布联合通知标题足够长了",
                "url": "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/2026081410142217598/index.html",
                "date": "2026-08-14",
                "date_source": "list",
                "source": "中国人民银行",
            }
        ],
    )
    stored = news_service.query_policy(tmp_path)
    urls = {item["url"] for item in stored["items"]}
    sources = {item["source"] for item in stored["items"]}
    assert "https://www.safe.gov.cn/safe/2026/0814/27784.html" in urls
    assert "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/2026081410142217598/index.html" in urls
    assert "国家外汇管理局" in sources
    assert "中国人民银行" in sources


def test_concurrent_department_refreshes_retain_both(tmp_path: Path) -> None:
    _write_two_departments(tmp_path)
    ready = threading.Barrier(2)
    errors: list[BaseException] = []

    def run(department: str, item: dict) -> None:
        def fetcher(*_args, **_kwargs):
            ready.wait(timeout=5)
            return [item]

        try:
            news_service.refresh_policy(tmp_path, department=department, fetcher=fetcher)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    item_a = {
        "title": "能源局并发刷新政策标题足够长了",
        "url": "https://www.nea.gov.cn/concurrent-a",
        "date": "2026-09-08",
        "date_source": "list",
        "source": "国家能源局",
    }
    item_b = {
        "title": "央行并发刷新政策标题足够长了足够长",
        "url": "http://www.pbc.gov.cn/concurrent-b",
        "date": "2026-09-09",
        "date_source": "list",
        "source": "中国人民银行",
    }
    threads = [
        threading.Thread(target=run, args=("国家能源局", item_a)),
        threading.Thread(target=run, args=("中国人民银行", item_b)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert errors == []
    titles = {item["title"] for item in news_service.query_policy(tmp_path)["items"]}
    assert item_a["title"] in titles
    assert item_b["title"] in titles


def test_policy_failure_does_not_rollback_concurrent_success(tmp_path: Path) -> None:
    _write_two_departments(tmp_path)
    news_service._write_policy_store(
        tmp_path,
        {
            "items": [
                {
                    "title": "已入库旧政策标题足够长了足够长",
                    "url": "https://www.nea.gov.cn/old",
                    "date": "2026-09-01",
                    "source": "国家能源局",
                }
            ],
            "updated_at": "2026-09-01T10:00:00+08:00",
            "last_refresh": {},
        },
    )
    success_done = threading.Event()
    results: dict[str, dict] = {}

    def success_fetcher(*_args, **_kwargs):
        return [
            {
                "title": "并发成功新政策标题足够长了足够长",
                "url": "https://www.nea.gov.cn/new",
                "date": "2026-09-08",
                "date_source": "list",
                "source": "国家能源局",
            }
        ]

    def fail_fetcher(*_args, **_kwargs):
        if not success_done.wait(timeout=5):
            raise AssertionError("success refresh did not finish")
        raise SourceFetchError("policy", "site down")

    def run_success() -> None:
        results["success"] = news_service.refresh_policy(
            tmp_path, department="国家能源局", fetcher=success_fetcher
        )
        success_done.set()

    def run_fail() -> None:
        results["fail"] = news_service.refresh_policy(
            tmp_path, department="中国人民银行", fetcher=fail_fetcher
        )

    threads = [threading.Thread(target=run_success), threading.Thread(target=run_fail)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert results["fail"]["preserved"] is True
    titles = {item["title"] for item in news_service.query_policy(tmp_path)["items"]}
    assert "并发成功新政策标题足够长了足够长" in titles
    assert "已入库旧政策标题足够长了足够长" in titles


def test_market_failure_does_not_rollback_concurrent_success(tmp_path: Path) -> None:
    success_done = threading.Event()
    results: dict[str, dict] = {}

    def success_fetcher():
        return [_item("财联社电报", "并发成功电报", "2026-09-09T11:00:00+08:00")]

    def fail_fetcher():
        if not success_done.wait(timeout=5):
            raise AssertionError("success refresh did not finish")
        raise SourceFetchError("cls", "timeout")

    def run_success() -> None:
        results["success"] = news_service.refresh_market_source(
            tmp_path, "cls", fetcher=success_fetcher
        )
        success_done.set()

    def run_fail() -> None:
        results["fail"] = news_service.refresh_market_source(tmp_path, "cls", fetcher=fail_fetcher)

    threads = [threading.Thread(target=run_success), threading.Thread(target=run_fail)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    cached = news_service.read_market_source(tmp_path, "cls")
    assert cached["items"][0]["title"] == "并发成功电报"
    assert cached["ok"] is True
    assert results["fail"]["preserved"] is True
    assert results["fail"]["items"][0]["title"] == "并发成功电报"
