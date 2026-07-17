"""Tencent/Sina free watchlist quote fallback (no TickFlow key required)."""
from __future__ import annotations

from typing import Iterable

from app.services.free_sources.http_resilience import ResilientHttpClient, get_shared_client


def _to_tencent_code(symbol: str) -> str:
    s = symbol.strip().upper()
    if "." in s:
        code, ex = s.split(".", 1)
    else:
        code, ex = s, ""
    code = code.zfill(6) if code.isdigit() else code
    if ex == "SH" or code.startswith(("5", "6", "9")):
        return f"sh{code}"
    if ex == "BJ" or code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sz{code}"


def _from_tencent_code(code: str) -> str:
    c = code.lower()
    if c.startswith("sh"):
        return f"{c[2:]}.SH"
    if c.startswith("sz"):
        return f"{c[2:]}.SZ"
    if c.startswith("bj"):
        return f"{c[2:]}.BJ"
    return code.upper()


def fetch_tencent_quotes(symbols: Iterable[str], client: ResilientHttpClient | None = None) -> list[dict]:
    client = client or get_shared_client()
    codes = [_to_tencent_code(s) for s in symbols if s]
    if not codes:
        return []
    url = "https://qt.gtimg.cn/q=" + ",".join(codes)
    res = client.get_text(url, source_key="tencent_quote", headers={"Referer": "https://gu.qq.com/"})
    if not res.ok or not res.text:
        raise RuntimeError(res.error or "tencent quote failed")
    out: list[dict] = []
    for line in res.text.splitlines():
        # v_sz000001="1~平安银行~000001~11.20~..."
        if "=" not in line:
            continue
        left, right = line.split("=", 1)
        code = left.split("_")[-1]
        body = right.strip().strip(";").strip('"')
        parts = body.split("~")
        if len(parts) < 6:
            continue
        def f(i: int) -> float | None:
            try:
                return float(parts[i])
            except (IndexError, ValueError):
                return None
        last = f(3)
        prev = f(4)
        change_pct = None
        if last is not None and prev not in (None, 0):
            change_pct = (last - prev) / prev * 100
        out.append(
            {
                "symbol": _from_tencent_code(code),
                "name": parts[1] if len(parts) > 1 else None,
                "last": last,
                "prev_close": prev,
                "open": f(5),
                "high": f(33) if len(parts) > 33 else f(33) if False else (f(33) if len(parts) > 33 else None),
                "low": f(34) if len(parts) > 34 else None,
                "volume": f(6),
                "amount": f(37) if len(parts) > 37 else None,
                "change_pct": change_pct,
                "source": "tencent",
            }
        )
    # fix high/low indices carefully: Tencent format commonly uses 33 high / 34 low for A-shares
    return out


def fetch_sina_quotes(symbols: Iterable[str], client: ResilientHttpClient | None = None) -> list[dict]:
    client = client or get_shared_client()
    codes = [_to_tencent_code(s) for s in symbols if s]
    if not codes:
        return []
    url = "https://hq.sinajs.cn/list=" + ",".join(codes)
    res = client.get_text(
        url,
        source_key="sina_quote",
        headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"},
    )
    if not res.ok or not res.text:
        raise RuntimeError(res.error or "sina quote failed")
    out: list[dict] = []
    for line in res.text.splitlines():
        if "=" not in line:
            continue
        left, right = line.split("=", 1)
        code = left.split("_")[-1]
        body = right.strip().strip(";").strip('"')
        parts = body.split(",")
        if len(parts) < 10:
            continue
        def f(i: int) -> float | None:
            try:
                return float(parts[i])
            except (IndexError, ValueError):
                return None
        open_ = f(1)
        prev = f(2)
        last = f(3)
        high = f(4)
        low = f(5)
        volume = f(8)
        amount = f(9)
        change_pct = None
        if last is not None and prev not in (None, 0):
            change_pct = (last - prev) / prev * 100
        out.append(
            {
                "symbol": _from_tencent_code(code),
                "name": parts[0] or None,
                "last": last,
                "prev_close": prev,
                "open": open_,
                "high": high,
                "low": low,
                "volume": volume,
                "amount": amount,
                "change_pct": change_pct,
                "source": "sina",
            }
        )
    return out


def fetch_watchlist_quotes(symbols: list[str], client: ResilientHttpClient | None = None) -> list[dict]:
    client = client or get_shared_client()
    try:
        rows = fetch_tencent_quotes(symbols, client=client)
        if rows:
            return rows
    except Exception:  # noqa: BLE001
        pass
    return fetch_sina_quotes(symbols, client=client)
