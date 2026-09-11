from __future__ import annotations

import json

import pytest

from app.services.news_sources.allowlist import UnsafeURLError, validate_http_url
from app.services.news_sources.cls import parse_cls_payload
from app.services.news_sources.foreign import parse_tradingview_items
from app.services.news_sources.html_extract import (
    extract_gov_departments,
    extract_policy_list_items,
    find_date_in_text,
    find_date_in_url,
    find_publish_hint_date,
    legacy_loose_url_date,
    month_dir_id_splice_date,
    parse_calendar_date,
    policy_sort_key,
    reconcile_cached_policy_date,
    sanitize_policy_date,
)
from app.services.free_sources import news_public as news_public_mod
from app.services.free_sources.news_public import fetch_department_policy
from app.services.news_sources.policy import parse_csrc_payload, parse_nfra_payload
from app.services.news_sources.sentiment import analyze_sentiment
from app.services.news_sources.sina import parse_sina_jsonp, parse_sina_payload


def test_cls_parser_maps_time_subjects_and_red_flag() -> None:
    items = parse_cls_payload(
        {
            "errno": 0,
            "data": {
                "roll_data": [
                    {
                        "id": 1,
                        "title": "央行加息",
                        "content": "利好消息推动大涨",
                        "ctime": 1757400000,
                        "level": "A",
                        "shareurl": "https://www.cls.cn/telegraph/1",
                        "subjects": [{"subject_name": "宏观"}],
                    },
                    {
                        "id": 2,
                        "title": "普通",
                        "content": "中性通报",
                        "ctime": 1757400060,
                        "level": "C",
                    },
                ]
            },
        }
    )
    assert items[0]["source"] == "财联社电报"
    assert items[0]["is_red"] is True
    assert items[0]["subjects"] == ["宏观"]
    assert items[0]["url"] == "https://www.cls.cn/telegraph/1"
    assert items[0]["time"].count(":") == 2
    assert items[1]["is_red"] is False


def test_sina_jsonp_is_stripped_without_executing_javascript() -> None:
    raw = 'try{callback({"result":{"data":{"feed":{"list":[{"id":9,"rich_text":"【焦点】大涨突破","create_time":"2026-09-09 10:01:02","tag":[{"name":"焦点"}]}]}}}});}catch(e){};'
    payload = parse_sina_jsonp(raw)
    items = parse_sina_payload(payload)
    assert items[0]["title"] == "焦点"
    assert items[0]["is_red"] is True
    assert items[0]["source"] == "新浪财经"
    assert items[0]["sentiment"] == "看涨"


def test_tradingview_parser_keeps_public_article_link() -> None:
    items = parse_tradingview_items(
        {"items": [{"id": "story:1", "title": "外媒标题足够长", "published": 1757400000}]},
    )
    assert items[0]["source"] == "外媒"
    assert items[0]["url"].startswith("https://cn.tradingview.com/news/")


def test_gov_department_catalog_filters_nav_and_gov_cn() -> None:
    html = """
    <a href="https://www.ndrc.gov.cn/">国家发展和改革委员会</a>
    <a href="https://www.pbc.gov.cn/">中国人民银行</a>
    <a href="https://www.gov.cn/home/">首页</a>
    <a href="https://beian.miit.gov.cn/">京ICP备123号</a>
    <a href="javascript:void(0)">商务部</a>
    """
    depts = extract_gov_departments(html)
    names = [item["name"] for item in depts]
    assert names == ["国家发展和改革委员会", "中国人民银行"]


def test_calendar_rejects_impossible_dates() -> None:
    assert parse_calendar_date("2026-09-04") is not None
    assert parse_calendar_date("2026-02-30") is None
    assert parse_calendar_date("2026-13-01") is None
    assert parse_calendar_date("2026-00-10") is None
    assert parse_calendar_date("2026-78-35") is None
    assert parse_calendar_date("2026-20-26") is None
    assert sanitize_policy_date("2026-78-35") == ""
    assert sanitize_policy_date("2026-09-04") == "2026-09-04"


def test_url_catalog_numbers_are_not_dates() -> None:
    today = "2026-09-09"
    assert find_date_in_url("/fbh/live/2026/78355/", today=today) == ""
    assert find_date_in_url("/jyb_xwfb/xw_zt/moe_357/2026/2026_zt09/", today=today) == ""
    assert find_date_in_url("/202609/t20260904_1.shtml", today=today) == "2026-09-04"
    assert find_date_in_url("/2026/09/04/content.html", today=today) == "2026-09-04"
    assert find_date_in_text("施行日期 2026-02-30 不是发布日", today=today) == ""


def test_url_dates_require_bounded_complete_forms() -> None:
    today = "2026-09-09"
    assert find_date_in_url("/seac/xwzx/202609/1194319.shtml", today=today) == ""
    assert find_date_in_url("/202607/1200abc.shtml", today=today) == ""
    assert find_date_in_url("/2026/09/1194319.shtml", today=today) == ""
    assert find_date_in_url("/202609/5ba25c81e0bb4614adf43f48a344dea5.shtml", today=today) == ""
    assert find_date_in_url("/t20260909_123.html", today=today) == "2026-09-09"
    assert find_date_in_url("/202609/t20260909_4224032.html", today=today) == "2026-09-09"
    assert find_date_in_url("/2026/09/09/", today=today) == "2026-09-09"
    assert find_date_in_url("/2026-09-09/content.html", today=today) == "2026-09-09"
    assert find_date_in_url("/html/xinwen/2026-09/06/content_294987.shtml", today=today) == "2026-09-06"
    assert find_date_in_url("/safe/2026/0907/27859.html", today=today) == "2026-09-07"
    assert find_date_in_url("/news/2026/0903/63100.shtml", today=today) == "2026-09-03"
    assert find_date_in_url("/2026090909080511735/index.html", today=today) == ""
    assert find_date_in_url("/2026/09/31/nope.html", today=today) == ""
    assert find_date_in_url("/2026/02/30/nope.html", today=today) == ""
    assert find_date_in_url("/2026/09/10/tomorrow.html", today=today) == "2026-09-10"
    assert find_date_in_url("/2026/09/11/day-after.html", today=today) == ""
    assert find_date_in_url("/2024/02/29/leap.html", today="2024-03-01") == "2024-02-29"
    assert find_date_in_url("/2025/02/29/not-leap.html", today="2025-03-01") == ""
    assert legacy_loose_url_date("/seac/xwzx/202609/1194319.shtml") == "2026-09-11"
    assert legacy_loose_url_date("/202607/1200abc.shtml", today=today) == "2026-07-12"


def test_cached_month_dir_id_dates_are_cleared_without_inventing() -> None:
    today = "2026-09-09"
    neac = "https://www.neac.gov.cn/seac/xwzx/202609/1194319.shtml"
    assert reconcile_cached_policy_date(neac, "2026-09-11", today=today) == ""
    assert reconcile_cached_policy_date(
        "https://www.example.gov.cn/202607/1200abc.shtml",
        "2026-07-12",
        today=today,
    ) == ""
    assert reconcile_cached_policy_date(
        "https://www.mot.gov.cn/202609/t20260909_4224032.html",
        "2026-09-09",
        today=today,
    ) == "2026-09-09"
    assert reconcile_cached_policy_date(
        "http://www.tobacco.gov.cn/gjyc/hyyw/202609/5ba25c81e0bb4614adf43f48a344dea5.shtml",
        "2026-09-09",
        today=today,
    ) == "2026-09-09"
    assert reconcile_cached_policy_date(neac, "2026-02-30", today=today) == ""
    pbc = "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/2026090909080511735/index.html"
    assert find_date_in_url("/2026090909080511735/index.html", today=today) == ""
    assert legacy_loose_url_date("/2026090909080511735/index.html", today=today) == "2026-09-09"
    assert month_dir_id_splice_date("/2026090909080511735/index.html", today=today) == ""
    assert month_dir_id_splice_date("/seac/xwzx/202609/1194319.shtml") == "2026-09-11"
    assert month_dir_id_splice_date("/202607/1200abc.shtml", today=today) == "2026-07-12"
    assert reconcile_cached_policy_date(pbc, "2026-09-09", today=today) == "2026-09-09"
    assert reconcile_cached_policy_date(pbc, "2026-09-09", today=today, date_source="list") == "2026-09-09"
    assert reconcile_cached_policy_date(pbc, "", today=today) == ""
    assert reconcile_cached_policy_date(pbc, "", today=today, date_source="list") == ""
    assert reconcile_cached_policy_date(neac, "2026-09-11", today=today, date_source="list") == ""
    assert find_publish_hint_date("发布时间：2026-09-08 10:00", today=today) == "2026-09-08"
    assert find_publish_hint_date("相关阅读 2026-09-01 不是本条", today=today) == ""
    assert (
        find_publish_hint_date(
            '<meta name="PubDate" content="2026-09-09 14:50:53"/>',
            today=today,
        )
        == "2026-09-09"
    )


def test_policy_list_uses_nearby_publish_date_not_url_id() -> None:
    html = """
    <ul>
      <li><a href="/fbh/live/2026/78355/">新闻发布会：介绍教师队伍建设有关情况和第42个教师节宣传庆祝活动</a><span>2026-09-05</span></li>
      <li><a href="/jyb_xwfb/xw_zt/moe_357/2026/2026_zt09/">全国基础教育工作会议专题标题足够长了</a></li>
      <li><a href="/202609/t20260904_1.shtml">关于进一步支持科技创新的若干政策措施</a></li>
    </ul>
    """
    items = extract_policy_list_items(html, "http://www.moe.gov.cn/jyb_xwfb/", today="2026-09-09")
    by_title = {item["title"]: item["date"] for item in items}
    assert by_title["新闻发布会：介绍教师队伍建设有关情况和第42个教师节宣传庆祝活动"] == "2026-09-05"
    assert "全国基础教育工作会议专题标题足够长了" not in by_title
    assert by_title["关于进一步支持科技创新的若干政策措施"] == "2026-09-04"


def test_policy_list_does_not_steal_neighbor_or_month_dir_id() -> None:
    html = """
    <ul>
      <li><a href="/seac/xwzx/202609/1194319.shtml">国新办举行开局起步系列主题新闻发布会介绍发展社会主义民主</a></li>
      <li><a href="/seac/xwzx/202608/1193820.shtml">第二条政策标题足够长了足够长了</a><span>2026-09-08</span></li>
      <li><a href="/202607/1200abc.shtml">第三条政策标题足够长了足够长了</a></li>
      <li><a href="/t20260909_123.html">第四条政策标题足够长了足够长了</a></li>
      <li><a href="/2026/09/09/bounded.html">第五条政策标题足够长了足够长了</a></li>
      <li><a href="/seac/xwzx/202609/1194001.shtml">本条带列表日期的政策标题足够长了</a><span>2026-09-08</span></li>
    </ul>
    """
    items = extract_policy_list_items(html, "https://www.neac.gov.cn/seac/xwzx/", today="2026-09-09")
    by_title = {item["title"]: item["date"] for item in items}
    assert "国新办举行开局起步系列主题新闻发布会介绍发展社会主义民主" not in by_title
    assert "第三条政策标题足够长了足够长了" not in by_title
    assert by_title["第二条政策标题足够长了足够长了"] == "2026-09-08"
    assert by_title["第四条政策标题足够长了足够长了"] == "2026-09-09"
    assert by_title["第五条政策标题足够长了足够长了"] == "2026-09-09"
    assert by_title["本条带列表日期的政策标题足够长了"] == "2026-09-08"


def test_unknown_dates_never_sort_as_newest() -> None:
    items = [
        {"title": "无日期", "date": ""},
        {"title": "假日期", "date": "2026-78-35"},
        {"title": "真日期", "date": "2026-09-04"},
    ]
    ordered = sorted(items, key=policy_sort_key, reverse=True)
    assert ordered[0]["title"] == "真日期"
    assert ordered[0]["date"] == "2026-09-04"
    assert {item["title"] for item in ordered[1:]} == {"无日期", "假日期"}


def test_policy_list_keeps_same_host_dated_titles() -> None:
    html = """
    <ul>
      <li><a href="/202609/t20260904_1.shtml" title="关于进一步支持科技创新的若干政策措施">关于进一步支持科技创新的若干政策措施</a><span>2026-09-04</span></li>
      <li><a href="https://www.gov.cn/zhengce/1.htm">国务院转载新闻标题足够长了</a><span>2026-09-04</span></li>
      <li><a href="/more.shtml">更多</a></li>
    </ul>
    """
    items = extract_policy_list_items(html, "https://www.nea.gov.cn/policy/zxwj.htm", today="2026-09-09")
    assert len(items) == 1
    assert items[0]["date"] == "2026-09-04"
    assert "nea.gov.cn" in items[0]["url"]


def test_nfra_and_csrc_json_parsers() -> None:
    nfra = parse_nfra_payload(
        {
            "rptCode": 200,
            "data": [
                {
                    "itemId": 10,
                    "docInfoVOList": [
                        {
                            "docId": 88,
                            "docTitle": "金融监管总局发布风险提示",
                            "publishDate": "2026-09-01 12:00:00",
                            "isTitleLink": "0",
                        }
                    ],
                }
            ],
        },
        limit=10,
    )
    assert nfra[0]["source"] == "国家金融监督管理总局"
    csrc = parse_csrc_payload(
        {
            "data": {
                "results": [
                    {
                        "title": "证监会发布监管工作动态",
                        "url": "//www.csrc.gov.cn/csrc/c100028/a.html",
                        "publishedTime": 1757400000000,
                    },
                    {"title": "附件", "url": "https://www.csrc.gov.cn/a.pdf"},
                ]
            }
        },
        limit=10,
    )
    assert len(csrc) == 1
    assert csrc[0]["url"].startswith("https://")


def test_ssrf_rejects_private_and_non_http() -> None:
    with pytest.raises(UnsafeURLError):
        validate_http_url("file:///etc/passwd", resolve=False)
    with pytest.raises(UnsafeURLError):
        validate_http_url("https://127.0.0.1/secret", resolve=False)
    with pytest.raises(UnsafeURLError):
        validate_http_url("https://example.com/news", resolve=False)
    assert validate_http_url(
        "https://www.gov.cn/home/2023-03/29/content_5748953.htm",
        resolve=False,
    ).startswith("https://www.gov.cn/")


def test_long_id_list_date_is_not_cleared_or_invented() -> None:
    today = "2026-09-09"
    html = """
    <ul>
      <li><a href="/goutongjiaoliu/113456/113469/2026090909080511735/index.html">中国人民银行副行长宣昌能出席国际清算银行行长例会</a><span>2026-09-09</span></li>
      <li><a href="/seac/xwzx/202609/1194319.shtml">月份目录加文章编号的政策标题足够长了</a></li>
      <li><a href="/202609/t20260909_1.html">紧凑URL日期政策标题足够长了足够长了</a></li>
    </ul>
    """
    items = extract_policy_list_items(html, "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/", today=today)
    by_title = {item["title"]: item for item in items}
    pbc = by_title["中国人民银行副行长宣昌能出席国际清算银行行长例会"]
    assert pbc["date"] == "2026-09-09"
    assert pbc["date_source"] == "list"
    assert "月份目录加文章编号的政策标题足够长了" not in by_title
    assert by_title["紧凑URL日期政策标题足够长了足够长了"]["date"] == "2026-09-09"
    assert by_title["紧凑URL日期政策标题足够长了足够长了"]["date_source"] == "url"


def test_fetch_uses_article_pubdate_when_list_has_no_date(monkeypatch: pytest.MonkeyPatch) -> None:
    list_html = """
    <ul>
      <li><a href="/article.html">央行发布公开市场业务操作通知标题足够长了</a></li>
    </ul>
    """
    article_html = '<meta name="PubDate" content="2026-09-09 09:08:05"/>'

    class _Resp:
        def __init__(self, body: str) -> None:
            self.status_code = 200
            self.content = body.encode("utf-8")
            self.headers = {"content-type": "text/html; charset=utf-8"}

    def fake_safe_get(url, extra_hosts=None, timeout=15.0, client_get=None, **_kwargs):
        if str(url).endswith("/article.html"):
            return _Resp(article_html)
        return _Resp(list_html)

    monkeypatch.setattr(news_public_mod, "safe_get", fake_safe_get)
    items = fetch_department_policy(
        "中国人民银行",
        "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html",
        limit=5,
        max_discover=0,
        extra_hosts={"www.pbc.gov.cn", "pbc.gov.cn"},
    )
    assert len(items) == 1
    assert items[0]["date"] == "2026-09-09"
    assert items[0]["date_source"] == "pubdate"


def test_rule_sentiment_labels() -> None:
    assert analyze_sentiment("利好消息推动股价大涨创新高") == "看涨"
    assert analyze_sentiment("突发利空暴跌跌停") == "看跌"
    assert analyze_sentiment("今日召开例行发布会") == "中性"
