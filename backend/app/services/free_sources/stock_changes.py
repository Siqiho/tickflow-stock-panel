"""EastMoney stock changes (盘口异动) on-demand."""
from __future__ import annotations

from datetime import date

from app.services.free_sources.http_resilience import ResilientHttpClient, get_shared_client


def fetch_stock_changes(
    client: ResilientHttpClient | None = None,
    *,
    date_str: str | None = None,
) -> list[dict]:
    client = client or get_shared_client()
    # Common public endpoint used by community tools; fields may vary.
    d = date_str or date.today().strftime("%Y%m%d")
    url = (
        "https://push2ex.eastmoney.com/getAllStockChanges"
        f"?type=8201,8202,8193,4,32,64,16&ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wzchanges&pageindex=0&pagesize=100&day={d}"
    )
    res = client.get_json(
        url,
        source_key="eastmoney_changes",
        headers={"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"},
    )
    if not res.ok:
        raise RuntimeError(res.error or "stock changes failed")
    data = res.data or {}
    items = []
    if isinstance(data, dict):
        payload = data.get("data") or {}
        if isinstance(payload, dict):
            items = payload.get("allstock") or payload.get("diff") or payload.get("list") or []
        elif isinstance(payload, list):
            items = payload
    out: list[dict] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        code = str(it.get("c") or it.get("code") or it.get("f12") or "")
        name = it.get("n") or it.get("name") or it.get("f14")
        tm = it.get("tm") or it.get("time")
        info = it.get("i") or it.get("info") or it.get("t")
        out.append(
            {
                "code": code,
                "name": name,
                "time": tm,
                "info": info,
                "raw": {k: it[k] for k in list(it)[:12]},
                "source": "eastmoney_changes",
                "date": d,
            }
        )
    return out
