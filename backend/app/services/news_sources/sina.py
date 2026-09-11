"""Sina finance live JSONP parser. The wrapper is stripped; JS is never executed."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.services.news_sources.sentiment import analyze_sentiment

SHANGHAI = ZoneInfo("Asia/Shanghai")
SOURCE_NAME = "新浪财经"
SINA_FEED_PREFIX = "https://zhibo.sina.com.cn/api/zhibo/feed"
JSONP_RE = re.compile(r"^[^{\[]*([{\[].*[}\]])[\s);]*$", re.S)
TITLE_RE = re.compile(r"【([^】]+)】")


def sina_feed_url(now_ts: int) -> str:
    return (
        "https://zhibo.sina.com.cn/api/zhibo/feed"
        "?callback=callback&page=1&page_size=20&zhibo_id=152&tag_id=0"
        f"&dire=f&dpc=1&pagesize=20&id=4161089&type=0&_={now_ts}"
    )


def parse_sina_jsonp(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    text = text.replace("try{callback(", "").replace(");}catch(e){};", "")
    text = re.sub(r"^callback\(", "", text)
    text = text.rstrip(";")
    if text.endswith(")"):
        text = text[:-1]
    match = JSONP_RE.match(text)
    if match:
        text = match.group(1)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("sina jsonp is not an object")
    return payload


def parse_sina_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    data = result.get("data") if isinstance(result, dict) else None
    feed = data.get("feed") if isinstance(data, dict) else None
    rows = feed.get("list") if isinstance(feed, dict) else None
    if not isinstance(rows, list):
        return []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        content = str(row.get("rich_text") or row.get("content") or "").strip()
        if not content:
            continue
        title_match = TITLE_RE.search(content)
        title = title_match.group(1).strip() if title_match else ""
        created = str(row.get("create_time") or "").strip()
        try:
            when = datetime.strptime(created, "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI)
        except ValueError:
            continue
        subjects: list[str] = []
        tags = row.get("tag")
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, dict):
                    name = str(tag.get("name") or "").strip()
                    if name:
                        subjects.append(name)
        key = title or content
        if key in seen:
            continue
        seen.add(key)
        url = str(row.get("url") or row.get("docurl") or "").strip()
        items.append(
            {
                "id": f"sina:{row.get('id') or key}",
                "source": SOURCE_NAME,
                "title": title,
                "content": content,
                "time": when.strftime("%H:%M:%S"),
                "data_time": when.isoformat(),
                "url": url,
                "subjects": subjects,
                "stocks": [],
                "is_red": "焦点" in subjects,
                "sentiment": analyze_sentiment(content),
            }
        )
    return items
