"""Official department catalog and department-site policy parsers."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from app.services.news_sources.html_extract import (
    DATE_SOURCE_LIST,
    DATE_SOURCE_RANK,
    discover_gov_list_pages,
    extract_gov_departments,
    extract_policy_list_items,
    is_policy_title,
    normalize_date_source,
    normalize_policy_title,
    policy_sort_key,
    sanitize_policy_date,
    strip_html,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
GOV_DEPT_LIST_URL = "https://www.gov.cn/home/2023-03/29/content_5748953.htm"

POLICY_PAGE_OVERRIDES = {
    "国家发展和改革委员会": "https://www.ndrc.gov.cn/",
    "中国人民银行": "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html",
    "中国证券监督管理委员会": "http://www.csrc.gov.cn/csrc/c100028/common_xq_list.shtml",
    "财政部": "https://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/",
    "国家统计局": "https://www.stats.gov.cn/sj/zxfb/",
    "国家外汇管理局": "https://www.safe.gov.cn/safe/whxw/index.html",
    "海关总署": "http://www.customs.gov.cn/customs/xwfb34/index.html",
    "公安部": "https://www.mps.gov.cn/n2253534/n2253535/index.html",
    "人力资源和社会保障部": "https://www.mohrss.gov.cn/SYrlzyhshbzb/dongtaixinwen/buneiyaowen/",
    "国家卫生健康委员会": "https://www.nhc.gov.cn/wjw/wnsj/list.shtml",
    "国家航天局": "https://www.cnsa.gov.cn/n6758823/n6758838/index.html",
    "国家原子能机构": "https://www.caea.gov.cn/n6760338/n6760342/index.html",
    "国家国际发展合作署": "http://www.cidca.gov.cn/hzdt2.htm",
    "国家国防科技工业局": "http://www.sastind.gov.cn/n10086200/n10086319/index.html",
    "国家矿山安全监察局": "https://www.chinamine-safety.gov.cn/zfxxgk/fdzdgknr/tzgg/",
    "全国人大": "http://www.npc.gov.cn/c2/c10134/",
    "全国政协": "http://www.cppcc.gov.cn/zxxw/yw/",
    "中国气象局": "https://www.cma.gov.cn/2011xwzx/2011xqxxw/2011xqxyw/",
    "中国社会科学院": "http://www.cass.cn/yaowen/",
    "国家疾病预防控制局": "https://www.ndcpa.gov.cn/jbkzzx/c100014/common/list.html",
    "国家数据局": "https://www.nda.gov.cn/sjj/swdt/list/index_pc_1.html",
    "国家能源局": "https://www.nea.gov.cn/policy/zxwj.htm",
}

API_DEPARTMENTS = frozenset(
    {
        "国家金融监督管理总局",
        "中国证券监督管理委员会",
        "国家疾病预防控制局",
        "国家能源局",
    }
)

DEFAULT_KEY_DEPARTMENTS = [
    "国家发展和改革委员会",
    "中国人民银行",
    "中国证券监督管理委员会",
    "财政部",
    "国家统计局",
    "国家外汇管理局",
    "商务部",
    "工业和信息化部",
    "住房和城乡建设部",
    "交通运输部",
    "国家数据局",
    "国家能源局",
]

NDCPA_TITLE_RE = re.compile(r'"aT":"((?:[^"\\]|\\.)*)"')
NDCPA_DATE_RE = re.compile(r'"aPd":"(\d{4}-\d{2}-\d{2})[ ]?[\d:]*"')
NDCPA_URL_RE = re.compile(r'"aU":"\{\\"common\\":\\"([^"\\]+)')
ATTACHMENT_RE = re.compile(r"\.(xlsx?|docx?|pdf|zip|rar|wps)($|\?)", re.I)


def today_shanghai() -> str:
    return datetime.now(SHANGHAI).date().isoformat()


def department_hosts(departments: list[dict[str, str]]) -> set[str]:
    hosts: set[str] = set()
    for item in departments:
        host = urlparse(str(item.get("url") or "")).hostname
        if host:
            hosts.add(host.lower())
    for url in POLICY_PAGE_OVERRIDES.values():
        host = urlparse(url).hostname
        if host:
            hosts.add(host.lower())
    return hosts


def parse_departments(html: str) -> list[dict[str, str]]:
    return extract_gov_departments(html)


def parse_policy_html(
    html: str,
    page_url: str,
    department: str,
    *,
    today: str | None = None,
    require_date: bool = True,
) -> list[dict[str, str]]:
    items = extract_policy_list_items(
        html,
        page_url,
        today=today or today_shanghai(),
        require_date=require_date,
    )
    for item in items:
        item["source"] = department
    return items


def discover_list_pages(html: str, page_url: str, limit: int) -> list[str]:
    return discover_gov_list_pages(html, page_url, limit=limit)


def target_url(department: str, home_url: str) -> str:
    return POLICY_PAGE_OVERRIDES.get(department) or home_url


def parse_nfra_payload(payload: dict[str, Any], *, limit: int) -> list[dict[str, str]]:
    if int(payload.get("rptCode") or 0) != 200:
        return []
    items: list[dict[str, str]] = []
    for group in payload.get("data") or []:
        if not isinstance(group, dict):
            continue
        item_id = group.get("itemId")
        for doc in group.get("docInfoVOList") or []:
            if not isinstance(doc, dict):
                continue
            title = str(doc.get("docTitle") or "").strip()
            if not title or (doc.get("isTitleLink") == "1" and doc.get("titleLink")):
                continue
            published = str(doc.get("publishDate") or "")
            date = published[:10] if len(published) >= 10 else ""
            items.append(
                _policy_row(
                    {
                        "title": title,
                        "url": f"https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId={doc.get('docId')}&itemId={item_id}",
                        "date": date,
                        "date_source": DATE_SOURCE_LIST,
                        "source": "国家金融监督管理总局",
                    }
                )
            )
    return dedupe_and_sort(items, limit)


def parse_csrc_payload(payload: dict[str, Any], *, limit: int) -> list[dict[str, str]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    items: list[dict[str, str]] = []
    for row in data.get("results") or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        link = str(row.get("url") or "").strip()
        if not title or not link:
            continue
        if link.startswith("//"):
            link = "https:" + link
        if ATTACHMENT_RE.search(link):
            continue
        published = row.get("publishedTime")
        date = ""
        try:
            date = datetime.fromtimestamp(int(published) / 1000, tz=SHANGHAI).date().isoformat()
        except (TypeError, ValueError, OSError):
            date = ""
        items.append(
            _policy_row(
                {
                    "title": title,
                    "url": link,
                    "date": date,
                    "date_source": DATE_SOURCE_LIST,
                    "source": "中国证券监督管理委员会",
                }
            )
        )
    return dedupe_and_sort(items, limit)


def parse_ndcpa_html(html: str, *, limit: int) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    matches = list(NDCPA_TITLE_RE.finditer(html or ""))
    for index, match in enumerate(matches):
        title = match.group(1).replace(r"\"", '"')
        if not is_policy_title(title):
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(html)
        block = html[match.start() : end]
        date_match = NDCPA_DATE_RE.search(block)
        url_match = NDCPA_URL_RE.search(block)
        if not date_match or not url_match:
            continue
        items.append(
            _policy_row(
                {
                    "title": title,
                    "url": "https://www.ndcpa.gov.cn" + url_match.group(1),
                    "date": date_match.group(1),
                    "date_source": DATE_SOURCE_LIST,
                    "source": "国家疾病预防控制局",
                }
            )
        )
    return dedupe_and_sort(items, limit)


def parse_nea_payload(payload: dict[str, Any], json_url: str, *, limit: int) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for doc in payload.get("datasource") or []:
        if not isinstance(doc, dict):
            continue
        title = strip_html(str(doc.get("title") or "")) or strip_html(str(doc.get("showTitle") or ""))
        if not is_policy_title(title):
            continue
        link = str(doc.get("publishUrl") or "").strip()
        if not link:
            continue
        if not link.startswith("http"):
            link = urljoin(json_url, link)
        if "nea.gov.cn" not in link:
            continue
        published = str(doc.get("publishTime") or "")
        items.append(
            _policy_row(
                {
                    "title": title,
                    "url": link,
                    "date": published[:10] if len(published) >= 10 else "",
                    "date_source": DATE_SOURCE_LIST,
                    "source": "国家能源局",
                }
            )
        )
    return dedupe_and_sort(items, limit)


def csrc_search_url(channel_id: str, limit: int) -> str:
    return (
        f"https://www.csrc.gov.cn/searchList/{channel_id}"
        f"?_isAgg=true&_isJson=true&_pageSize={limit}&_template=index"
        "&_rangeTimeGte=&_channelName=&page=1"
    )


def _policy_row(item: dict[str, str]) -> dict[str, str]:
    date = sanitize_policy_date(str(item.get("date") or ""))
    date_source = normalize_date_source(item.get("date_source")) if date else ""
    row = {
        "title": str(item.get("title") or "").strip(),
        "url": str(item.get("url") or "").strip(),
        "date": date,
        "source": str(item.get("source") or ""),
    }
    if date_source:
        row["date_source"] = date_source
    return row


def _row_better(candidate: dict[str, str], existing: dict[str, str]) -> bool:
    cand_date = candidate.get("date") or ""
    exist_date = existing.get("date") or ""
    cand_rank = DATE_SOURCE_RANK.get(candidate.get("date_source") or "", 0)
    exist_rank = DATE_SOURCE_RANK.get(existing.get("date_source") or "", 0)
    if cand_date and not exist_date:
        return True
    if exist_date and not cand_date:
        return False
    return cand_rank > exist_rank


def dedupe_and_sort(items: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    seen_url: dict[str, int] = {}
    seen_title_source: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for item in items:
        row = _policy_row(item)
        url = row["url"]
        title = row["title"]
        if not url:
            continue
        normalized = normalize_policy_title(title)
        source = row["source"]
        existing_idx = seen_url.get(url)
        if existing_idx is not None:
            if _row_better(row, result[existing_idx]):
                result[existing_idx] = row
            continue
        title_key = (normalized, source)
        if normalized and title_key in seen_title_source:
            continue
        seen_url[url] = len(result)
        if normalized:
            seen_title_source.add(title_key)
        result.append(row)
    result.sort(key=policy_sort_key, reverse=True)
    if limit > 0:
        return result[:limit]
    return result


def loads_json(text: str) -> dict[str, Any]:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("expected json object")
    return payload
