"""Stdlib HTML extractors. Source HTML is parsed, never executed."""

from __future__ import annotations

import re
from datetime import date, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

FULL_DATE_RE = re.compile(
    r"(?:^|[^\d])(20\d{2})([-/.年])(\d{1,2})([-/.月])(\d{1,2})日?(?:$|[^\d])"
)
SHORT_DATE_RE = re.compile(r"(?:^|[^\d])(\d{1,2})[-/](\d{1,2})(?:$|[^\d])")
# Complete, consistently delimited path dates: /2026/09/09/ or /2026-09-09/.
BOUNDED_SEP_URL_DATE_RE = re.compile(r"(?<!\d)(20\d{2})([/\-.])(\d{1,2})\2(\d{1,2})(?!\d)")
# Year-month folder plus day folder: /2026-09/06/content.html. Not /YYYYMM/ + id.
BOUNDED_YEARMONTH_DAY_RE = re.compile(r"(?<!\d)(20\d{2})-(\d{2})/(\d{2})(?!\d)")
# Year folder plus MMDD folder: /2026/0907/27859.html. Four-digit day segment only.
BOUNDED_YEAR_MMDD_RE = re.compile(r"(?<!\d)(20\d{2})/(\d{2})(\d{2})(?!\d)")
# Complete YYYYMMDD with non-digit boundaries: t20260909_123.html. Never /YYYYMM/ + id.
BOUNDED_COMPACT_URL_DATE_RE = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)")
# Previous extractor; only used to detect cached splices, never to invent a date.
LEGACY_LOOSE_URL_DATE_RE = re.compile(r"(20\d{2})[-/]?(\d{2})[-/]?(\d{2})")
# True splice: /YYYYMM/ or /YYYY/MM/ joined to a longer numeric article id.
MONTH_DIR_LONG_ID_RE = re.compile(r"(?<!\d)(20\d{2})(\d{2})/(\d{2})\d")
YEAR_MONTH_LONG_ID_RE = re.compile(r"(?<!\d)(20\d{2})/(\d{1,2})/(\d{2})\d")
DATE_SOURCE_LIST = "list"
DATE_SOURCE_URL = "url"
DATE_SOURCE_PUBDATE = "pubdate"
DATE_SOURCES = frozenset({DATE_SOURCE_LIST, DATE_SOURCE_URL, DATE_SOURCE_PUBDATE})
DATE_SOURCE_RANK = {"": 0, DATE_SOURCE_URL: 1, DATE_SOURCE_PUBDATE: 2, DATE_SOURCE_LIST: 3}
PUBLISH_HINT_RE = re.compile(
    r"(发布时间|发布日期|成文日期|发稿时间)[^20]{0,24}(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?"
)
META_PUBDATE_RE = re.compile(
    r'<meta\b[^>]*\b(?:name|property)=["\'](?:PubDate|pubdate|publishdate|article:published_time)["\'][^>]*\bcontent=["\'](20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})',
    re.I,
)
META_PUBDATE_CONTENT_FIRST_RE = re.compile(
    r'<meta\b[^>]*\bcontent=["\'](20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})[^"\']*["\'][^>]*\b(?:name|property)=["\'](?:PubDate|pubdate|publishdate|article:published_time)["\']',
    re.I,
)
TRAILING_DATE_RE = re.compile(r"[\s\u00a0\u3000]*20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?[\s\u00a0\u3000]*$")
HTML_TAG_RE = re.compile(r"<[^>]+>")
LIST_ITEM_OPEN_RE = re.compile(r"<(?:li|tr|dd|dt)\b", re.I)
LIST_ITEM_BOUNDARY_RE = re.compile(r"</(?:li|tr|dd|dt)>|<(?:li|tr|dd|dt)\b", re.I)
NAV_WORDS = (
    "更多",
    "详情",
    "点击",
    "登录",
    "注册",
    "搜索",
    "首页",
    "上一页",
    "下一页",
    "关于我们",
    "联系方式",
    "网站地图",
    "无障碍",
    "收藏本站",
    "主办单位",
    "承办单位",
    "常见问题",
    "使用帮助",
    "相关链接",
    "友情链接",
    "网站标识",
    "政府网站",
    "智能问答",
)


def pad2(value: str) -> str:
    return value.zfill(2)


def parse_calendar_date(text: str) -> date | None:
    """Accept only real Gregorian YYYY-MM-DD values. Topic/catalog numbers fail."""
    raw = (text or "").strip()
    if not raw:
        return None
    parts = raw.split("-")
    if len(parts) != 3:
        return None
    try:
        year, month, day = (int(part) for part in parts)
        return date(year, month, day)
    except ValueError:
        return None


def sanitize_policy_date(text: str) -> str:
    parsed = parse_calendar_date(text)
    return parsed.isoformat() if parsed else ""


def normalize_date_source(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in DATE_SOURCES else ""


def policy_sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
    """Valid dates sort newest-first; unknown/invalid dates never rank as latest."""
    parsed = parse_calendar_date(str(item.get("date") or ""))
    if parsed is None:
        return (0, "", str(item.get("title") or ""))
    return (1, parsed.isoformat(), str(item.get("title") or ""))


def strip_html(value: str) -> str:
    return " ".join(HTML_TAG_RE.sub("", value or "").split())


def normalize_host(host: str) -> str:
    return (host or "").lower().strip().removeprefix("www.")


def trim_trailing_date(title: str) -> str:
    return TRAILING_DATE_RE.sub("", title).strip()


def is_policy_title(title: str) -> bool:
    text = (title or "").strip()
    chars = list(text)
    if len(chars) < 8 or len(chars) > 80:
        return False
    if sum(1 for ch in chars if "\u4e00" <= ch <= "\u9fff") < 4:
        return False
    return not any(word in text for word in NAV_WORDS)


def find_date_in_text(text: str, *, today: str) -> str:
    today_date = parse_calendar_date(today)
    if today_date is None:
        return ""
    tomorrow = today_date + timedelta(days=1)
    for match in FULL_DATE_RE.finditer(text or ""):
        parsed = parse_calendar_date(f"{match.group(1)}-{pad2(match.group(3))}-{pad2(match.group(5))}")
        if parsed is None or parsed > tomorrow:
            continue
        return parsed.isoformat()
    for match in SHORT_DATE_RE.finditer(text or ""):
        parsed = parse_calendar_date(f"{today_date.year}-{pad2(match.group(1))}-{pad2(match.group(2))}")
        if parsed is None:
            continue
        if parsed > today_date:
            parsed = parse_calendar_date(f"{today_date.year - 1}-{pad2(match.group(1))}-{pad2(match.group(2))}")
            if parsed is None:
                continue
        return parsed.isoformat()
    return ""


def _url_date_window(today: str) -> tuple[date, date] | None:
    today_date = parse_calendar_date(today)
    if today_date is None:
        return None
    try:
        oldest = date(today_date.year - 2, today_date.month, today_date.day)
    except ValueError:
        oldest = date(today_date.year - 2, 3, 1)
    return oldest, today_date + timedelta(days=1)


def _first_in_window(candidates: list[tuple[int, date]], *, today: str) -> str:
    window = _url_date_window(today)
    if window is None:
        return ""
    oldest, tomorrow = window
    for _, parsed in sorted(candidates, key=lambda row: row[0]):
        if oldest <= parsed <= tomorrow:
            return parsed.isoformat()
    return ""


def find_date_in_url(path: str, *, today: str) -> str:
    """Accept only complete, consistently bounded URL dates. Do not join a month folder to an id."""
    text = path or ""
    candidates: list[tuple[int, date]] = []
    for match in BOUNDED_SEP_URL_DATE_RE.finditer(text):
        parsed = parse_calendar_date(f"{match.group(1)}-{pad2(match.group(3))}-{pad2(match.group(4))}")
        if parsed is not None:
            candidates.append((match.start(), parsed))
    for match in BOUNDED_YEARMONTH_DAY_RE.finditer(text):
        parsed = parse_calendar_date(f"{match.group(1)}-{pad2(match.group(2))}-{pad2(match.group(3))}")
        if parsed is not None:
            candidates.append((match.start(), parsed))
    for match in BOUNDED_YEAR_MMDD_RE.finditer(text):
        parsed = parse_calendar_date(f"{match.group(1)}-{pad2(match.group(2))}-{pad2(match.group(3))}")
        if parsed is not None:
            candidates.append((match.start(), parsed))
    for match in BOUNDED_COMPACT_URL_DATE_RE.finditer(text):
        parsed = parse_calendar_date(f"{match.group(1)}-{pad2(match.group(2))}-{pad2(match.group(3))}")
        if parsed is not None:
            candidates.append((match.start(), parsed))
    return _first_in_window(candidates, today=today)


def legacy_loose_url_date(path: str, *, today: str | None = None) -> str:
    """Reproduce the old unsliced YYYYMM + id matcher for cache provenance checks."""
    candidates: list[tuple[int, date]] = []
    for match in LEGACY_LOOSE_URL_DATE_RE.finditer(path or ""):
        parsed = parse_calendar_date(f"{match.group(1)}-{pad2(match.group(2))}-{pad2(match.group(3))}")
        if parsed is not None:
            candidates.append((match.start(), parsed))
    if not candidates:
        return ""
    if today is None:
        return sorted(candidates, key=lambda row: row[0])[0][1].isoformat()
    return _first_in_window(candidates, today=today)


def month_dir_id_splice_date(path: str, *, today: str | None = None) -> str:
    """Date invented by joining /YYYYMM/ or /YYYY/MM/ to the start of a longer article id.

    A long continuous digit id such as /2026090909080511735/ is not a splice.
    """
    text = path or ""
    candidates: list[tuple[int, date]] = []
    for match in MONTH_DIR_LONG_ID_RE.finditer(text):
        parsed = parse_calendar_date(f"{match.group(1)}-{pad2(match.group(2))}-{pad2(match.group(3))}")
        if parsed is not None:
            candidates.append((match.start(), parsed))
    for match in YEAR_MONTH_LONG_ID_RE.finditer(text):
        parsed = parse_calendar_date(f"{match.group(1)}-{pad2(match.group(2))}-{pad2(match.group(3))}")
        if parsed is not None:
            candidates.append((match.start(), parsed))
    if not candidates:
        return ""
    if today is None:
        return sorted(candidates, key=lambda row: row[0])[0][1].isoformat()
    return _first_in_window(candidates, today=today)


def reconcile_cached_policy_date(
    url: str,
    stored: str,
    *,
    today: str,
    date_source: str = "",
) -> str:
    """Keep a stored date only when it is a real calendar day with independent evidence.

    list/pubdate metadata from this item wins over URL heuristics. Legacy rows without
    date_source keep a stored day unless it is a month-folder + article-id splice or after
    tomorrow. Long article ids are never used to invent or clear a real list date.
    Neighbor items are never used here.
    """
    date_text = sanitize_policy_date(stored)
    if not date_text:
        return ""
    parsed = parse_calendar_date(date_text)
    today_date = parse_calendar_date(today)
    if parsed is None or today_date is None:
        return ""
    if parsed > today_date + timedelta(days=1):
        return ""
    path = urlparse(url).path
    proven = find_date_in_url(path, today=today)
    if proven == date_text:
        return date_text
    source = normalize_date_source(date_source)
    if source in {DATE_SOURCE_LIST, DATE_SOURCE_PUBDATE}:
        return date_text
    if source == DATE_SOURCE_URL:
        return proven
    if month_dir_id_splice_date(path, today=today) == date_text:
        return ""
    return date_text


def find_publish_hint_date(text: str, *, today: str) -> str:
    """Use an explicit publish-date label on this page only. Do not take a neighboring story."""
    today_date = parse_calendar_date(today)
    if today_date is None:
        return ""
    tomorrow = today_date + timedelta(days=1)
    raw = text or ""
    match = PUBLISH_HINT_RE.search(raw)
    if match is not None:
        parsed = parse_calendar_date(f"{match.group(2)}-{pad2(match.group(3))}-{pad2(match.group(4))}")
        if parsed is not None and parsed <= tomorrow:
            return parsed.isoformat()
    for meta in (META_PUBDATE_RE.search(raw), META_PUBDATE_CONTENT_FIRST_RE.search(raw)):
        if meta is None:
            continue
        parsed = parse_calendar_date(f"{meta.group(1)}-{pad2(meta.group(2))}-{pad2(meta.group(3))}")
        if parsed is not None and parsed <= tomorrow:
            return parsed.isoformat()
    return ""


def list_item_text_for_href(raw: str, href: str, search_from: int = 0) -> tuple[str, int]:
    """Return visible text of the same list row as this href, never the next row."""
    idx = raw.find(href, search_from)
    if idx < 0:
        idx = raw.find(href)
    if idx < 0:
        return "", search_from
    lookback = raw[max(0, idx - 800) : idx]
    opens = list(LIST_ITEM_OPEN_RE.finditer(lookback))
    item_start = (max(0, idx - 800) + opens[-1].start()) if opens else idx
    after = raw[idx : idx + 800]
    boundary = LIST_ITEM_BOUNDARY_RE.search(after)
    if boundary:
        item_end = idx + boundary.start()
    elif opens:
        item_end = idx + min(len(after), 400)
    else:
        item_end = idx + min(len(after), 160)
    return strip_html(raw[item_start:item_end]), idx + max(len(href), 1)


def normalize_policy_title(title: str) -> str:
    puncts = " \t\n\r《》〈〉“”‘’【】[]（()），,。．.、：:！!？?—-－·"
    return "".join(ch for ch in title if ch not in puncts)


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._chunks: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        mapping = {key: (value or "") for key, value in attrs}
        href = mapping.get("href", "").strip()
        if self._current is None:
            self._current = {"href": href, "title_attr": mapping.get("title", "").strip()}
            self._chunks = []
            self._depth = 1
        else:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._current is None:
            return
        self._depth -= 1
        if self._depth > 0:
            return
        text = "".join(self._chunks).strip()
        self.anchors.append({**self._current, "text": text})
        self._current = None
        self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._chunks.append(data)


def extract_anchors(html: str) -> list[dict[str, str]]:
    parser = _AnchorParser()
    parser.feed(html or "")
    parser.close()
    return parser.anchors


def extract_gov_departments(html: str) -> list[dict[str, str]]:
    seen: set[str] = set()
    departments: list[dict[str, str]] = []
    for anchor in extract_anchors(html):
        name = " ".join((anchor.get("text") or "").split())
        href = (anchor.get("href") or "").strip()
        if not name or not href or href.lower().startswith("javascript"):
            continue
        if not (3 <= len(list(name)) <= 20):
            continue
        if any(token in name for token in ("ICP", "备案", "公网安备", "标识码", "无障碍", "手机版")):
            continue
        parsed = urlparse(href)
        if not parsed.scheme or not parsed.netloc:
            continue
        host = parsed.netloc.lower()
        if "www.gov.cn" in host or "beian." in host:
            continue
        if host in seen:
            continue
        seen.add(host)
        departments.append({"name": name, "url": parsed.geturl()})
    return departments


def extract_policy_list_items(
    html: str,
    base_url: str,
    *,
    today: str,
    require_date: bool = True,
) -> list[dict[str, str]]:
    base = urlparse(base_url)
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    raw = html or ""
    search_from = 0
    for anchor in extract_anchors(raw):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript", "mailto:")):
            continue
        title = (anchor.get("text") or "").strip()
        title_attr = (anchor.get("title_attr") or "").strip()
        if title_attr:
            if len(list(title)) > 80 or len(list(title_attr)) > len(list(title)):
                title = title_attr
        title = trim_trailing_date(title)
        if not is_policy_title(title):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if not parsed.netloc:
            continue
        if normalize_host(parsed.netloc) != normalize_host(base.netloc):
            continue
        if absolute in seen:
            continue
        nearby, search_from = list_item_text_for_href(raw, href, search_from)
        list_date = sanitize_policy_date(find_date_in_text(nearby or title, today=today))
        hint_date = sanitize_policy_date(find_publish_hint_date(nearby or "", today=today))
        url_date = sanitize_policy_date(find_date_in_url(parsed.path, today=today))
        if list_date:
            date, date_source = list_date, DATE_SOURCE_LIST
        elif hint_date:
            date, date_source = hint_date, DATE_SOURCE_PUBDATE
        elif url_date:
            date, date_source = url_date, DATE_SOURCE_URL
        else:
            date, date_source = "", ""
            if require_date:
                continue
        seen.add(absolute)
        item = {"title": title, "url": absolute, "date": date}
        if date_source:
            item["date_source"] = date_source
        items.append(item)
    return items


def discover_gov_list_pages(html: str, base_url: str, limit: int = 5) -> list[str]:
    keywords = ("新闻", "要闻", "政策", "公告", "发布", "文件", "动态")
    urls: list[str] = []
    seen: set[str] = set()
    base_host = normalize_host(urlparse(base_url).netloc)
    for anchor in extract_anchors(html):
        name = (anchor.get("text") or "").strip()
        href = (anchor.get("href") or "").strip()
        if not name or len(list(name)) > 12 or not href:
            continue
        if href.startswith(("#", "javascript")):
            continue
        if not any(keyword in name for keyword in keywords):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if normalize_host(parsed.netloc) != base_host:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        urls.append(absolute)
        if len(urls) >= limit:
            break
    return urls
