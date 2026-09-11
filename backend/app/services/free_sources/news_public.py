"""Allowlisted live fetchers for market news and official policy pages."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlparse

from app.services.news_sources.allowlist import decode_body, safe_get
from app.services.news_sources.cls import CLS_TELEGRAPH_LIST_URL, CLS_TELEGRAPH_URL, parse_cls_payload
from app.services.news_sources.foreign import TV_NEWS_URL, apply_story_detail, parse_tradingview_items, story_url
from app.services.news_sources.html_extract import DATE_SOURCE_PUBDATE, find_publish_hint_date, sanitize_policy_date
from app.services.news_sources.policy import (
    API_DEPARTMENTS,
    GOV_DEPT_LIST_URL,
    csrc_search_url,
    department_hosts,
    discover_list_pages,
    loads_json,
    parse_csrc_payload,
    parse_departments,
    parse_ndcpa_html,
    parse_nea_payload,
    parse_nfra_payload,
    parse_policy_html,
    target_url,
    today_shanghai,
)
from app.services.news_sources.sina import parse_sina_jsonp, parse_sina_payload, sina_feed_url

FetcherGet = Callable[..., Any]


class SourceFetchError(RuntimeError):
    def __init__(self, source: str, message: str) -> None:
        super().__init__(message)
        self.source = source
        self.message = message


def _get_text(url: str, extra_hosts: set[str] | None, timeout: float, getter: FetcherGet | None) -> tuple[str, str]:
    response = safe_get(url, extra_hosts=extra_hosts, timeout=timeout, client_get=getter)
    if response.status_code >= 400:
        raise SourceFetchError(url, f"HTTP {response.status_code}")
    return decode_body(response.content, response.headers.get("content-type")), url


def _get_json(url: str, extra_hosts: set[str] | None, timeout: float, getter: FetcherGet | None) -> dict[str, Any]:
    text, _ = _get_text(url, extra_hosts, timeout, getter)
    return loads_json(text)


def fetch_cls(getter: FetcherGet | None = None) -> list[dict[str, Any]]:
    try:
        payload = _get_json(CLS_TELEGRAPH_URL, None, 12.0, getter)
        items = parse_cls_payload(payload)
        if items:
            return items
    except Exception:  # noqa: BLE001
        payload = None
    payload = _get_json(CLS_TELEGRAPH_LIST_URL, None, 12.0, getter)
    items = parse_cls_payload(payload)
    if not items:
        raise SourceFetchError("cls", "财联社电报无可用条目")
    return items


def fetch_sina(getter: FetcherGet | None = None) -> list[dict[str, Any]]:
    url = sina_feed_url(int(time.time()))
    text, _ = _get_text(url, None, 12.0, getter)
    items = parse_sina_payload(parse_sina_jsonp(text))
    if not items:
        raise SourceFetchError("sina", "新浪财经无可用条目")
    return items


def fetch_foreign(getter: FetcherGet | None = None, *, detail_limit: int = 10) -> list[dict[str, Any]]:
    payload = _get_json(TV_NEWS_URL, None, 12.0, getter)
    items = parse_tradingview_items(payload, limit=20)
    if not items:
        raise SourceFetchError("foreign", "外媒无可用条目")
    detailed: list[dict[str, Any]] = []
    for item in items:
        story_id = str(item.get("story_id") or "")
        if story_id and len(detailed) < detail_limit:
            try:
                detail = _get_json(story_url(story_id), None, 8.0, getter)
                item = apply_story_detail(item, detail)
            except Exception:  # noqa: BLE001
                pass
        item.pop("story_id", None)
        detailed.append(item)
    return detailed


def fetch_departments(getter: FetcherGet | None = None) -> list[dict[str, str]]:
    text, _ = _get_text(GOV_DEPT_LIST_URL, None, 15.0, getter)
    departments = parse_departments(text)
    if not departments:
        raise SourceFetchError("departments", "未解析到官方部门目录")
    return departments


def _fetch_policy_api(department: str, limit: int, getter: FetcherGet | None) -> list[dict[str, str]]:
    if department == "国家金融监督管理总局":
        payload = _get_json(
            "https://www.nfra.gov.cn/cbircweb/DocInfo/SelectItemAndDocByItemPId?itemId=914&pageSize=20",
            None,
            15.0,
            getter,
        )
        return parse_nfra_payload(payload, limit=limit)
    if department == "中国证券监督管理委员会":
        items: list[dict[str, str]] = []
        channels = (
            "a1a078ee0bc54721ab6b148884c784a8",
            "8d1c236a98924e38a854bbb9f215efb9",
        )
        for channel in channels:
            try:
                payload = _get_json(csrc_search_url(channel, max(limit, 1)), None, 15.0, getter)
                items.extend(parse_csrc_payload(payload, limit=limit))
            except Exception:  # noqa: BLE001
                continue
        return items
    if department == "国家疾病预防控制局":
        text, _ = _get_text("https://www.ndcpa.gov.cn/jbkzzx/c100014/common/list.html", None, 15.0, getter)
        return parse_ndcpa_html(text, limit=limit)
    if department == "国家能源局":
        items: list[dict[str, str]] = []
        for url in (
            "https://www.nea.gov.cn/policy/ds_40d365c13659452aa06cdb7268d6192e.json",
            "https://www.nea.gov.cn/xwzx/ds_8839d76f7cb542ca8cbaab7122cc9b83.json",
        ):
            try:
                payload = _get_json(url, None, 15.0, getter)
                items.extend(parse_nea_payload(payload, url, limit=limit))
            except Exception:  # noqa: BLE001
                continue
        return items
    return []


def fetch_department_policy(
    department: str,
    home_url: str,
    *,
    limit: int,
    max_discover: int,
    extra_hosts: set[str],
    getter: FetcherGet | None = None,
) -> list[dict[str, str]]:
    if department in API_DEPARTMENTS:
        items = _fetch_policy_api(department, limit, getter)
        if items:
            return items[:limit]
    page = target_url(department, home_url)
    if not page:
        return []
    extra = set(extra_hosts)
    host = urlparse(page).hostname
    if host:
        extra.add(host.lower())
    html, _ = _get_text(page, extra, 15.0, getter)
    candidates = parse_policy_html(html, page, department, require_date=False)
    if max_discover > 0 and len([item for item in candidates if item.get("date")]) < 5 and home_url:
        for sub in discover_list_pages(html, page, limit=max_discover):
            try:
                sub_html, _ = _get_text(sub, extra, 15.0, getter)
                candidates.extend(parse_policy_html(sub_html, sub, department, require_date=False))
            except Exception:  # noqa: BLE001
                continue
            if len([item for item in candidates if item.get("date")]) >= limit:
                break
    items = [item for item in candidates if item.get("date")]
    seen = {str(item.get("url") or "") for item in items}
    today = today_shanghai()
    for cand in candidates:
        if len(items) >= limit:
            break
        url = str(cand.get("url") or "")
        if cand.get("date") or not url or url in seen:
            continue
        try:
            article_html, _ = _get_text(url, extra, 8.0, getter)
            pub = sanitize_policy_date(find_publish_hint_date(article_html, today=today))
        except Exception:  # noqa: BLE001
            continue
        if not pub:
            continue
        items.append({**cand, "date": pub, "date_source": DATE_SOURCE_PUBDATE})
        seen.add(url)
    return items[:limit]


def fetch_all_department_policy(
    departments: list[dict[str, str]],
    *,
    per_dept: int = 5,
    max_discover: int = 1,
    workers: int = 8,
    getter: FetcherGet | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    extra = department_hosts(departments)
    items: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="policy") as pool:
        futs = {
            pool.submit(
                fetch_department_policy,
                dept["name"],
                dept.get("url") or "",
                limit=per_dept,
                max_discover=max_discover,
                extra_hosts=extra,
                getter=getter,
            ): dept["name"]
            for dept in departments
            if dept.get("name")
        }
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                items.extend(fut.result())
            except Exception as exc:  # noqa: BLE001
                failures.append({"department": name, "error": str(exc)})
    return items, failures
