"""SSRF-safe fetch limited to static verified hosts and official department catalog."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urljoin, urlparse

import httpx

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

STATIC_ALLOWED_HOSTS = frozenset(
    {
        "www.cls.cn",
        "zhibo.sina.com.cn",
        "news-mediator.tradingview.com",
        "news-headlines.tradingview.com",
        "www.gov.cn",
        "www.nfra.gov.cn",
        "www.csrc.gov.cn",
        "www.ndcpa.gov.cn",
        "www.nea.gov.cn",
    }
)

STATIC_ALLOWED_URLS = frozenset(
    {
        "https://www.cls.cn/api/cache?app=CailianpressWeb&name=telegraph&os=web&sv=8.7.9",
        "https://www.cls.cn/api/cache?app=CailianpressWeb&name=telegraphList&os=web&sv=8.7.9",
        "https://www.gov.cn/home/2023-03/29/content_5748953.htm",
        "https://www.nfra.gov.cn/cbircweb/DocInfo/SelectItemAndDocByItemPId?itemId=914&pageSize=20",
        "https://www.ndcpa.gov.cn/jbkzzx/c100014/common/list.html",
        "https://www.nea.gov.cn/policy/ds_40d365c13659452aa06cdb7268d6192e.json",
        "https://www.nea.gov.cn/xwzx/ds_8839d76f7cb542ca8cbaab7122cc9b83.json",
        "https://news-mediator.tradingview.com/news-flow/v2/news?filter=lang%3Azh-Hans&client=screener&streaming=false",
    }
)

_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata.google.internal",
    }
)


class UnsafeURLError(ValueError):
    """Rejected because the URL is not an allowlisted public http(s) source."""


def _normalize_host(host: str) -> str:
    return host.lower().strip().strip("[]")


def host_is_blocked(host: str) -> bool:
    name = _normalize_host(host)
    if not name or name in _BLOCKED_HOSTS:
        return True
    if name.endswith(".local") or name.endswith(".internal"):
        return True
    try:
        ip = ipaddress.ip_address(name)
    except ValueError:
        return False
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def resolve_public(host: str) -> list[str]:
    name = _normalize_host(host)
    if host_is_blocked(name):
        raise UnsafeURLError(f"blocked host: {host}")
    try:
        infos = socket.getaddrinfo(name, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeURLError(f"dns failed: {host}") from exc
    addrs: list[str] = []
    for info in infos:
        raw = info[4][0]
        ip = ipaddress.ip_address(raw)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UnsafeURLError(f"resolved to private address: {host}")
        addrs.append(str(ip))
    if not addrs:
        raise UnsafeURLError(f"no public address: {host}")
    return addrs


def allowed_hosts(extra_hosts: Iterable[str] | None = None) -> set[str]:
    hosts = set(STATIC_ALLOWED_HOSTS)
    for host in extra_hosts or ():
        name = _normalize_host(host)
        if name and not host_is_blocked(name):
            hosts.add(name)
    return hosts


def public_http_url(raw: str, *, resolve: bool = False) -> str:
    """Accept http(s) public URLs for display. Does not authorize a fetch."""
    if not isinstance(raw, str) or not raw.strip():
        raise UnsafeURLError("empty url")
    parsed = urlparse(raw.strip())
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURLError("only http(s) is allowed")
    if parsed.username or parsed.password:
        raise UnsafeURLError("userinfo is not allowed")
    host = _normalize_host(parsed.hostname or "")
    if not host or host_is_blocked(host):
        raise UnsafeURLError("host is not allowed")
    if resolve:
        resolve_public(host)
    return raw.strip()


def validate_http_url(raw: str, *, extra_hosts: Iterable[str] | None = None, resolve: bool = True) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise UnsafeURLError("empty url")
    text = raw.strip()
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURLError("only http(s) is allowed")
    if parsed.username or parsed.password:
        raise UnsafeURLError("userinfo is not allowed")
    host = _normalize_host(parsed.hostname or "")
    if not host or host_is_blocked(host):
        raise UnsafeURLError("host is not allowed")
    if host not in allowed_hosts(extra_hosts):
        raise UnsafeURLError("host is outside the verified catalog")
    if resolve:
        resolve_public(host)
    return text


def decode_body(payload: bytes, content_type: str | None = None) -> str:
    header = (content_type or "").lower()
    for encoding in ("utf-8", "gb18030", "gbk"):
        if encoding in header:
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                break
    for encoding in ("utf-8", "gb18030"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


HttpGet = Callable[..., httpx.Response]


def safe_get(
    url: str,
    *,
    extra_hosts: Iterable[str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    max_redirects: int = 5,
    client_get: HttpGet | None = None,
) -> httpx.Response:
    """GET an allowlisted URL. Redirects are re-validated; private hops are rejected."""
    current = validate_http_url(url, extra_hosts=extra_hosts, resolve=True)
    getter = client_get or httpx.get
    merged = dict(BROWSER_HEADERS)
    if headers:
        merged.update(headers)
    for _ in range(max_redirects + 1):
        response = getter(current, headers=merged, timeout=timeout, follow_redirects=False)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("location")
        if not location:
            raise UnsafeURLError("redirect without location")
        current = validate_http_url(urljoin(current, location), extra_hosts=extra_hosts, resolve=True)
    raise UnsafeURLError("too many redirects")
