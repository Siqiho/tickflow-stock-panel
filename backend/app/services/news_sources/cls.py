"""Cailianpress telegraph JSON parser. Does not execute HTML or scripts."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.services.news_sources.sentiment import analyze_sentiment

SHANGHAI = ZoneInfo("Asia/Shanghai")
CLS_TELEGRAPH_URL = "https://www.cls.cn/api/cache?app=CailianpressWeb&name=telegraph&os=web&sv=8.7.9"
CLS_TELEGRAPH_LIST_URL = "https://www.cls.cn/api/cache?app=CailianpressWeb&name=telegraphList&os=web&sv=8.7.9"
SOURCE_NAME = "财联社电报"


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_cls_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if _as_int(payload.get("errno")) not in {0, None}:
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    rows = data.get("roll_data")
    if not isinstance(rows, list):
        return []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        ctime = _as_int(row.get("ctime"))
        if ctime is None:
            continue
        when = datetime.fromtimestamp(ctime, tz=SHANGHAI)
        title = str(row.get("title") or "").strip()
        content = str(row.get("content") or "").strip()
        if not title and not content:
            continue
        share = str(row.get("shareurl") or "").strip()
        if not share and row.get("id") is not None:
            share = f"https://www.cls.cn/telegraph/{row['id']}"
        subjects: list[str] = []
        stocks: list[str] = []
        raw_subjects = row.get("subjects")
        if isinstance(raw_subjects, list):
            for subject in raw_subjects:
                if not isinstance(subject, dict):
                    continue
                name = str(subject.get("subject_name") or "").strip()
                if name:
                    subjects.append(name)
        raw_stocks = row.get("stock_list") or row.get("stocks")
        if isinstance(raw_stocks, list):
            for stock in raw_stocks:
                if isinstance(stock, dict):
                    name = str(stock.get("name") or stock.get("secu_name") or "").strip()
                    if name:
                        stocks.append(name)
                elif isinstance(stock, str) and stock.strip():
                    stocks.append(stock.strip())
        key = title or content
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "id": f"cls:{row.get('id') or key}",
                "source": SOURCE_NAME,
                "title": title,
                "content": content,
                "time": when.strftime("%H:%M:%S"),
                "data_time": when.isoformat(),
                "url": share,
                "subjects": subjects,
                "stocks": stocks,
                "is_red": str(row.get("level") or "") != "C",
                "sentiment": analyze_sentiment(content or title),
            }
        )
    return items
