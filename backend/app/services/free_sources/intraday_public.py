"""Single-symbol public intraday (Tencent). Does not write full-market kline_minute."""
from __future__ import annotations

from app.services.free_sources.http_resilience import ResilientHttpClient, get_shared_client
from app.services.free_sources.quote_fallback import _to_tencent_code


def fetch_public_intraday(symbol: str, client: ResilientHttpClient | None = None) -> dict:
    client = client or get_shared_client()
    code = _to_tencent_code(symbol)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={code}"
    res = client.get_json(url, source_key="tencent_intraday", headers={"Referer": "https://gu.qq.com/"})
    if not res.ok:
        raise RuntimeError(res.error or "intraday fetch failed")
    data = res.data or {}
    # data.data.{code}.data.data -> list of "HH:MM price volume"
    node = ((data.get("data") or {}).get(code) or {}).get("data") or {}
    points_raw = node.get("data") or []
    points = []
    for item in points_raw:
        parts = str(item).split()
        if len(parts) >= 2:
            try:
                price = float(parts[1])
            except ValueError:
                continue
            vol = None
            if len(parts) >= 3:
                try:
                    vol = float(parts[2])
                except ValueError:
                    vol = None
            points.append({"time": parts[0], "price": price, "volume": vol})
    return {
        "symbol": symbol.upper() if "." in symbol else symbol,
        "code": code,
        "points": points,
        "count": len(points),
        "source": "tencent_minute",
        "persisted": False,
    }
