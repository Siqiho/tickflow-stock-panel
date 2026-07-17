"""Lightweight F10 summary via EastMoney push2 clist/quote fields (on-demand)."""
from __future__ import annotations

from app.services.free_sources.fund_flow import _secid
from app.services.free_sources.http_resilience import ResilientHttpClient, get_shared_client


def fetch_f10_summary(symbol: str, client: ResilientHttpClient | None = None) -> dict:
    """Return a small valuation/size snapshot — not full financial statements."""
    client = client or get_shared_client()
    secid = _secid(symbol)
    # utoken-less public quote endpoint with valuation fields
    url = (
        "https://push2.eastmoney.com/api/qt/stock/get"
        f"?secid={secid}&fields=f57,f58,f43,f46,f44,f45,f47,f48,f60,f170,f162,f167,f116,f117,f127,f173,f188"
    )
    res = client.get_json(
        url,
        source_key="eastmoney_f10",
        headers={"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"},
    )
    if not res.ok:
        raise RuntimeError(res.error or "f10 fetch failed")
    data = (res.data or {}).get("data") if isinstance(res.data, dict) else None
    data = data or {}

    def scaled(v, div=100.0):
        if v is None:
            return None
        try:
            return float(v) / div
        except (TypeError, ValueError):
            return None

    return {
        "symbol": symbol,
        "code": data.get("f57"),
        "name": data.get("f58"),
        "last": scaled(data.get("f43")),
        "open": scaled(data.get("f46")),
        "high": scaled(data.get("f44")),
        "low": scaled(data.get("f45")),
        "volume": data.get("f47"),
        "amount": data.get("f48"),
        "prev_close": scaled(data.get("f60")),
        "change_pct": scaled(data.get("f170")),
        "pe_ttm": scaled(data.get("f162"), 100.0),
        "pb": scaled(data.get("f167"), 100.0),
        "total_mv": data.get("f116"),
        "float_mv": data.get("f117"),
        "industry": data.get("f127"),
        "roe": scaled(data.get("f173"), 100.0) if data.get("f173") is not None else None,
        "source": "eastmoney_push2_quote_fields",
        "note": "Summary snapshot only; not full financial statements",
    }
