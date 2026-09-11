"""TradingView Chinese news-flow JSON parser. Story details stay JSON-only."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from app.services.news_sources.sentiment import analyze_sentiment

SHANGHAI = ZoneInfo("Asia/Shanghai")
SOURCE_NAME = "外媒"
TV_NEWS_URL = (
    "https://news-mediator.tradingview.com/news-flow/v2/news"
    "?filter=lang%3Azh-Hans&client=screener&streaming=false"
)


def story_url(story_id: str) -> str:
    return f"https://news-headlines.tradingview.com/v3/story?id={quote(story_id, safe='')}&lang=zh-Hans"


def article_url(story_id: str) -> str:
    return f"https://cn.tradingview.com/news/{story_id}"


def parse_tradingview_items(payload: dict[str, Any], *, limit: int = 20) -> list[dict[str, Any]]:
    rows = payload.get("items")
    if not isinstance(rows, list):
        return []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        story_id = str(row.get("id") or "").strip()
        if not title or not story_id or title in seen:
            continue
        seen.add(title)
        published = row.get("published")
        try:
            when = datetime.fromtimestamp(int(published), tz=SHANGHAI)
        except (TypeError, ValueError, OSError):
            continue
        items.append(
            {
                "id": f"tv:{story_id}",
                "source": SOURCE_NAME,
                "title": title,
                "content": "",
                "time": when.strftime("%H:%M:%S"),
                "data_time": when.isoformat(),
                "url": article_url(story_id),
                "story_id": story_id,
                "subjects": [],
                "stocks": [],
                "is_red": False,
                "sentiment": "中性",
            }
        )
    return items


def apply_story_detail(item: dict[str, Any], detail: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(item)
    if not isinstance(detail, dict):
        return out
    description = str(detail.get("shortDescription") or detail.get("short_description") or "").strip()
    if description:
        out["content"] = description
        out["sentiment"] = analyze_sentiment(description)
    return out
