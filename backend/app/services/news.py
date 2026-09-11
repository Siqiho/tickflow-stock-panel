"""Local news/policy cache. GET never leaves the machine; POST fetches allowlisted sources."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from app.services.atomic_io import atomic_write_json, write_lineage_record
from app.services.free_sources.news_public import (
    SourceFetchError,
    fetch_all_department_policy,
    fetch_cls,
    fetch_department_policy,
    fetch_departments,
    fetch_foreign,
    fetch_sina,
)
from app.services.news_sources.allowlist import public_http_url, validate_http_url
from app.services.news_sources.html_extract import (
    month_dir_id_splice_date,
    normalize_date_source,
    parse_calendar_date,
    policy_sort_key,
    reconcile_cached_policy_date,
    sanitize_policy_date,
)
from app.services.news_sources.policy import (
    DEFAULT_KEY_DEPARTMENTS,
    dedupe_and_sort,
    department_hosts,
    today_shanghai,
)
from app.services.user_context import user_path

logger = logging.getLogger(__name__)
SHANGHAI = ZoneInfo("Asia/Shanghai")
MARKET_SOURCES = {
    "cls": "财联社电报",
    "sina": "新浪财经",
    "foreign": "外媒",
}
UNIT_VERSION = "news_policy_v1"
_POLICY_STORE_LOCK = threading.RLock()
_MARKET_SOURCE_LOCKS = {source: threading.Lock() for source in MARKET_SOURCES}


def _now() -> str:
    return datetime.now(SHANGHAI).isoformat()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    import json

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _market_path(data_dir: Path, source: str) -> Path:
    return Path(data_dir) / "news" / "market" / f"{source}.json"


def _policy_items_path(data_dir: Path) -> Path:
    return Path(data_dir) / "news" / "policy" / "items.json"


def _departments_path(data_dir: Path) -> Path:
    return Path(data_dir) / "news" / "policy" / "departments.json"


def _key_departments_path(data_dir: Path | None = None) -> Path:
    return user_path("news", "key_departments.json", data_dir=data_dir)


def _public_url(url: str, extra_hosts: set[str] | None = None) -> str:
    text = (url or "").strip()
    if not text:
        return ""
    try:
        cleaned = public_http_url(text, resolve=False)
        if extra_hosts is not None:
            validate_http_url(cleaned, extra_hosts=extra_hosts, resolve=False)
        return cleaned
    except ValueError:
        return ""


def _sanitize_market_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        key = title or content
        if not key or key in seen:
            continue
        seen.add(key)
        url = _public_url(str(item.get("url") or ""))
        clean.append(
            {
                "id": str(item.get("id") or key),
                "source": str(item.get("source") or ""),
                "title": title,
                "content": content,
                "time": str(item.get("time") or ""),
                "data_time": str(item.get("data_time") or ""),
                "url": url,
                "subjects": [str(x) for x in (item.get("subjects") or []) if str(x).strip()],
                "stocks": [str(x) for x in (item.get("stocks") or []) if str(x).strip()],
                "is_red": bool(item.get("is_red")),
                "sentiment": str(item.get("sentiment") or "中性"),
            }
        )
    clean.sort(key=lambda row: row.get("data_time") or "", reverse=True)
    return clean


def empty_market_source(source: str) -> dict[str, Any]:
    return {
        "source": source,
        "label": MARKET_SOURCES[source],
        "ok": False,
        "error": None,
        "fetched_at": None,
        "producer": MARKET_SOURCES[source],
        "items": [],
        "from_cache": True,
    }


def read_market_source(data_dir: Path, source: str) -> dict[str, Any]:
    cached = _read_json(_market_path(data_dir, source)) or {}
    items = _sanitize_market_items(list(cached.get("items") or []))
    return {
        "source": source,
        "label": MARKET_SOURCES[source],
        "ok": bool(cached.get("ok")) if cached else False,
        "error": cached.get("error"),
        "fetched_at": cached.get("fetched_at"),
        "producer": cached.get("producer") or MARKET_SOURCES[source],
        "endpoint": cached.get("endpoint"),
        "items": items,
        "from_cache": True,
        "timezone": "Asia/Shanghai",
    }


def read_market(data_dir: Path) -> dict[str, Any]:
    sources = {source: read_market_source(data_dir, source) for source in MARKET_SOURCES}
    return {"timezone": "Asia/Shanghai", "sources": sources}


def _write_market(data_dir: Path, source: str, payload: dict[str, Any]) -> None:
    atomic_write_json(payload, _market_path(data_dir, source), indent=2)
    write_lineage_record(
        data_dir,
        f"news_market_{source}",
        {
            "date": datetime.now(SHANGHAI).date().isoformat(),
            "source": source,
            "producer": payload.get("producer"),
            "endpoint": payload.get("endpoint"),
            "unit_version": UNIT_VERSION,
            "row_count": len(payload.get("items") or []),
            "quality": "healthy" if payload.get("ok") else "failed",
            "target_artifact": f"news/market/{source}.json",
        },
    )


def refresh_market_source(data_dir: Path, source: str, *, fetcher=None) -> dict[str, Any]:
    if source not in MARKET_SOURCES:
        raise ValueError(f"unknown market source: {source}")
    previous = read_market_source(data_dir, source)
    fetchers = {
        "cls": fetch_cls,
        "sina": fetch_sina,
        "foreign": fetch_foreign,
    }
    try:
        raw_items = (fetcher or fetchers[source])()
        items = _sanitize_market_items(raw_items)
        if not items:
            raise SourceFetchError(source, "empty payload")
        payload = {
            "source": source,
            "label": MARKET_SOURCES[source],
            "ok": True,
            "error": None,
            "fetched_at": _now(),
            "producer": MARKET_SOURCES[source],
            "endpoint": {
                "cls": "https://www.cls.cn/api/cache",
                "sina": "https://zhibo.sina.com.cn/api/zhibo/feed",
                "foreign": "https://news-mediator.tradingview.com/news-flow/v2/news",
            }[source],
            "items": items,
            "timezone": "Asia/Shanghai",
        }
        with _MARKET_SOURCE_LOCKS[source]:
            _write_market(data_dir, source, payload)
        return {**payload, "from_cache": False, "preserved": False}
    except Exception as exc:  # noqa: BLE001
        logger.warning("market source %s refresh failed: %s", source, exc)
        with _MARKET_SOURCE_LOCKS[source]:
            current = read_market_source(data_dir, source)
            if (
                current.get("ok")
                and current.get("fetched_at")
                and current.get("fetched_at") != previous.get("fetched_at")
            ):
                return {
                    **current,
                    "ok": False,
                    "error": str(exc),
                    "from_cache": True,
                    "preserved": True,
                }
            failed = {
                "source": source,
                "label": MARKET_SOURCES[source],
                "ok": False,
                "error": str(exc),
                "fetched_at": current.get("fetched_at"),
                "producer": current.get("producer") or MARKET_SOURCES[source],
                "endpoint": current.get("endpoint"),
                "items": current.get("items") or [],
                "timezone": "Asia/Shanghai",
                "from_cache": True,
                "preserved": True,
            }
            _write_market(
                data_dir,
                source,
                {
                    **failed,
                    "items": current.get("items") or [],
                },
            )
        return failed


def refresh_market(data_dir: Path, source: str = "all") -> dict[str, Any]:
    chosen = list(MARKET_SOURCES) if source == "all" else [source]
    sources = {item: refresh_market_source(data_dir, item) for item in chosen}
    if source != "all":
        for item in MARKET_SOURCES:
            if item not in sources:
                sources[item] = read_market_source(data_dir, item)
    return {"timezone": "Asia/Shanghai", "sources": sources}


def read_departments(data_dir: Path) -> dict[str, Any]:
    cached = _read_json(_departments_path(data_dir)) or {}
    departments = []
    extra = department_hosts(list(cached.get("departments") or []))
    for item in cached.get("departments") or []:
        url = _public_url(str(item.get("url") or ""), extra_hosts=extra)
        name = str(item.get("name") or "").strip()
        if name and url:
            departments.append({"name": name, "url": url})
    return {
        "departments": departments,
        "count": len(departments),
        "ok": bool(cached.get("ok")) if cached else False,
        "error": cached.get("error"),
        "fetched_at": cached.get("fetched_at"),
        "from_cache": True,
        "producer": "www.gov.cn",
        "endpoint": "https://www.gov.cn/home/2023-03/29/content_5748953.htm",
    }


def refresh_departments(data_dir: Path, *, fetcher=None) -> dict[str, Any]:
    previous = read_departments(data_dir)
    try:
        departments = (fetcher or fetch_departments)()
        extra = department_hosts(departments)
        clean = []
        for item in departments:
            url = _public_url(str(item.get("url") or ""), extra_hosts=extra)
            name = str(item.get("name") or "").strip()
            if name and url:
                clean.append({"name": name, "url": url})
        if not clean:
            raise SourceFetchError("departments", "empty department catalog")
        payload = {
            "departments": clean,
            "ok": True,
            "error": None,
            "fetched_at": _now(),
            "producer": "www.gov.cn",
            "endpoint": "https://www.gov.cn/home/2023-03/29/content_5748953.htm",
        }
        atomic_write_json(payload, _departments_path(data_dir), indent=2)
        write_lineage_record(
            data_dir,
            "news_policy_departments",
            {
                "date": datetime.now(SHANGHAI).date().isoformat(),
                "source": "www.gov.cn",
                "producer": "www.gov.cn",
                "unit_version": UNIT_VERSION,
                "row_count": len(clean),
                "quality": "healthy",
                "target_artifact": "news/policy/departments.json",
            },
        )
        return {**read_departments(data_dir), "from_cache": False, "preserved": False}
    except Exception as exc:  # noqa: BLE001
        logger.warning("department catalog refresh failed: %s", exc)
        payload = {
            "departments": previous.get("departments") or [],
            "ok": False,
            "error": str(exc),
            "fetched_at": previous.get("fetched_at"),
            "producer": "www.gov.cn",
            "endpoint": previous.get("endpoint"),
        }
        atomic_write_json(payload, _departments_path(data_dir), indent=2)
        return {**read_departments(data_dir), "error": str(exc), "ok": False, "preserved": True}


def _policy_item_record(item: dict[str, Any], *, extra_hosts: set[str] | None, today: str) -> dict[str, str] | None:
    url = _public_url(str(item.get("url") or ""), extra_hosts=extra_hosts) or str(item.get("url") or "").strip()
    title = str(item.get("title") or "").strip()
    if not url or not title:
        return None
    date_source = normalize_date_source(item.get("date_source"))
    date = reconcile_cached_policy_date(
        url,
        str(item.get("date") or ""),
        today=today,
        date_source=date_source,
    )
    if not date:
        date_source = ""
    row = {
        "title": title,
        "url": url,
        "date": date,
        "source": str(item.get("source") or ""),
    }
    if date_source:
        row["date_source"] = date_source
    return row


def _read_policy_store(data_dir: Path) -> dict[str, Any]:
    cached = _read_json(_policy_items_path(data_dir)) or {}
    extra = department_hosts(read_departments(data_dir).get("departments") or [])
    today = today_shanghai()
    items = []
    for item in cached.get("items") or []:
        row = _policy_item_record(item, extra_hosts=extra, today=today)
        if row:
            items.append(row)
    return {
        "items": items,
        "updated_at": cached.get("updated_at"),
        "last_refresh": cached.get("last_refresh") or {},
    }


def _write_policy_store(data_dir: Path, store: dict[str, Any]) -> None:
    today = today_shanghai()
    extra = department_hosts(read_departments(data_dir).get("departments") or [])
    cleaned = []
    for item in store.get("items") or []:
        row = _policy_item_record(item, extra_hosts=extra, today=today)
        if row:
            cleaned.append(row)
    store = {**store, "items": cleaned}
    atomic_write_json(store, _policy_items_path(data_dir), indent=2)
    write_lineage_record(
        data_dir,
        "news_policy_items",
        {
            "date": datetime.now(SHANGHAI).date().isoformat(),
            "source": "gov_departments",
            "producer": "official_department_sites",
            "unit_version": UNIT_VERSION,
            "row_count": len(store.get("items") or []),
            "quality": "healthy",
            "target_artifact": "news/policy/items.json",
        },
    )


def _date_clear_reason(url: str, raw: str, *, today: str, date_source: str = "") -> str | None:
    calendar = sanitize_policy_date(raw)
    proven = reconcile_cached_policy_date(url, raw, today=today, date_source=date_source)
    if not raw.strip():
        return None
    if not calendar:
        return "invalid_calendar"
    if proven:
        return None
    if month_dir_id_splice_date(urlparse(url).path, today=today) == calendar:
        return "month_dir_id_splice"
    parsed = parse_calendar_date(calendar)
    today_date = parse_calendar_date(today)
    if parsed is not None and today_date is not None and parsed > today_date + timedelta(days=1):
        return "beyond_tomorrow"
    return "unproven"


def scrub_invalid_policy_dates(data_dir: Path) -> dict[str, Any]:
    """Rewrite local policy cache so invalid calendar dates become empty, not newest."""
    return scrub_unproven_policy_dates(data_dir)


def scrub_unproven_policy_dates(data_dir: Path, *, today: str | None = None) -> dict[str, Any]:
    """Persist empty dates for invalid, future, or month-folder+id splices. GET does not call this."""
    today_text = today or today_shanghai()
    with _POLICY_STORE_LOCK:
        store = _read_json(_policy_items_path(data_dir)) or {}
        items = list(store.get("items") or [])
        extra = department_hosts(read_departments(data_dir).get("departments") or [])
        cleared = 0
        cleaned = []
        changes: list[dict[str, str]] = []
        for item in items:
            raw = str(item.get("date") or "")
            url = _public_url(str(item.get("url") or ""), extra_hosts=extra) or str(item.get("url") or "")
            date_source = normalize_date_source(item.get("date_source"))
            date = reconcile_cached_policy_date(url, raw, today=today_text, date_source=date_source)
            reason = _date_clear_reason(url, raw, today=today_text, date_source=date_source)
            if reason:
                cleared += 1
                changes.append(
                    {
                        "title": str(item.get("title") or ""),
                        "url": url,
                        "source": str(item.get("source") or ""),
                        "before": raw,
                        "after": date,
                        "reason": reason,
                        "path": urlparse(url).path,
                    }
                )
            row = {**item, "url": url or str(item.get("url") or ""), "date": date}
            if date and date_source:
                row["date_source"] = date_source
            elif "date_source" in row and (not date or reason):
                row.pop("date_source", None)
            cleaned.append(row)
        payload = {
            "items": cleaned,
            "updated_at": store.get("updated_at"),
            "last_refresh": store.get("last_refresh") or {},
            "date_scrub": {
                "cleared": cleared,
                "total": len(cleaned),
                "kind": "unproven_or_invalid",
            },
        }
        _write_policy_store(data_dir, payload)
    return {
        "cleared": cleared,
        "total": len(cleaned),
        "path": str(_policy_items_path(data_dir)),
        "today": today_text,
        "changes": changes,
    }


def query_policy(
    data_dir: Path,
    *,
    department: str = "",
    keyword: str = "",
    page: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    store = _read_policy_store(data_dir)
    items = list(store.get("items") or [])
    dept = department.strip()
    kw = keyword.strip()
    if dept:
        items = [item for item in items if dept in str(item.get("source") or "")]
    if kw:
        items = [item for item in items if kw in str(item.get("title") or "")]
    items.sort(key=policy_sort_key, reverse=True)
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 100), 200))
    start = (page - 1) * page_size
    sliced = items[start : start + page_size]
    return {
        "items": sliced,
        "total": len(items),
        "page": page,
        "page_size": page_size,
        "has_more": start + page_size < len(items),
        "search_mode": bool(kw),
        "department": dept,
        "keyword": kw,
        "from_cache": True,
        "updated_at": store.get("updated_at"),
        "last_refresh": store.get("last_refresh") or {},
        "note": "本地已入库历史；上游政策页无真正可见分页，仅有 100/200 抓取限额。加载更多只翻本地缓存。",
    }


def refresh_policy(
    data_dir: Path,
    *,
    department: str = "",
    fetcher=None,
) -> dict[str, Any]:
    catalog = read_departments(data_dir)
    if not catalog.get("departments"):
        catalog = refresh_departments(data_dir)
    departments = list(catalog.get("departments") or [])
    extra = department_hosts(departments)
    snapshot_lr = (_read_json(_policy_items_path(data_dir)) or {}).get("last_refresh") or {}
    snapshot_lr_at = snapshot_lr.get("fetched_at")
    failures: list[dict[str, str]] = []
    incoming: list[dict[str, str]] = []
    scope = "all"
    limit = 100
    try:
        if department.strip():
            scope = "department"
            limit = 30
            match = next((item for item in departments if item["name"] == department.strip()), None)
            if match is None:
                raise SourceFetchError("policy", f"部门不在官方目录中: {department}")
            incoming = (fetcher or fetch_department_policy)(
                match["name"],
                match.get("url") or "",
                limit=limit,
                max_discover=5,
                extra_hosts=extra,
            )
        else:
            incoming, failures = (fetcher or fetch_all_department_policy)(
                departments,
                per_dept=5,
                max_discover=1,
            )
            incoming = dedupe_and_sort(incoming, 0)
            if not incoming and failures:
                raise SourceFetchError("policy", f"全部部门刷新失败（{len(failures)} 个）")
        with _POLICY_STORE_LOCK:
            store = _read_policy_store(data_dir)
            previous_items = list(store.get("items") or [])
            merged = dedupe_and_sort([*incoming, *previous_items], 0)
            last_refresh = {
                "scope": scope,
                "department": department.strip(),
                "ok": True,
                "error": None,
                "added": max(0, len(merged) - len(previous_items)),
                "fetched": len(incoming),
                "failures": failures,
                "fetched_at": _now(),
            }
            _write_policy_store(
                data_dir,
                {
                    "items": merged,
                    "updated_at": _now(),
                    "last_refresh": last_refresh,
                },
            )
        result = query_policy(data_dir, department=department, page=1, page_size=100 if scope == "all" else 30)
        result["from_cache"] = False
        result["last_refresh"] = last_refresh
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("policy refresh failed: %s", exc)
        last_refresh = {
            "scope": scope,
            "department": department.strip(),
            "ok": False,
            "error": str(exc),
            "added": 0,
            "fetched": 0,
            "failures": failures,
            "fetched_at": _now(),
        }
        with _POLICY_STORE_LOCK:
            store = _read_policy_store(data_dir)
            current_lr = store.get("last_refresh") or {}
            if current_lr.get("ok") and current_lr.get("fetched_at") and current_lr.get("fetched_at") != snapshot_lr_at:
                result = query_policy(data_dir, department=department, page=1, page_size=100)
                result["last_refresh"] = last_refresh
                result["preserved"] = True
                return result
            _write_policy_store(
                data_dir,
                {
                    "items": list(store.get("items") or []),
                    "updated_at": store.get("updated_at"),
                    "last_refresh": last_refresh,
                },
            )
        result = query_policy(data_dir, department=department, page=1, page_size=100)
        result["last_refresh"] = last_refresh
        result["preserved"] = True
        return result


def read_key_departments(data_dir: Path | None = None) -> dict[str, Any]:
    cached = _read_json(_key_departments_path(data_dir)) or {}
    departments = [str(item).strip() for item in cached.get("departments") or [] if str(item).strip()]
    is_default = not departments
    if is_default:
        departments = list(DEFAULT_KEY_DEPARTMENTS)
    return {
        "departments": departments,
        "is_default": is_default,
        "defaults": list(DEFAULT_KEY_DEPARTMENTS),
    }


def save_key_departments(departments: list[str], data_dir: Path | None = None) -> dict[str, Any]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in departments or []:
        name = str(item).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        cleaned.append(name)
    path = _key_departments_path(data_dir)
    if not cleaned:
        if path.exists():
            path.unlink()
        return read_key_departments(data_dir)
    atomic_write_json({"departments": cleaned}, path, indent=2)
    return read_key_departments(data_dir)
