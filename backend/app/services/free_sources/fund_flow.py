"""EastMoney public fund-flow fetchers (intelligence-only map; own parsers)."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.services.ext_data import ExtConfig, ExtConfigStore, ExtField, write_ext_parquet
from app.services.free_sources.http_resilience import ResilientHttpClient, get_shared_client

_EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; one-trading-free-sources/0.1)",
    "Referer": "https://data.eastmoney.com/",
}


def _secid(symbol: str) -> str:
    sym = symbol.strip().upper()
    if "." in sym:
        code, ex = sym.split(".", 1)
    else:
        code, ex = sym, ""
    code = code.zfill(6) if code.isdigit() else code
    market = "1" if ex == "SH" or code.startswith(("5", "6", "9")) else "0"
    if ex == "BJ":
        market = "0"
    return f"{market}.{code}"


def _symbol_from_sec_parts(code: str, market_hint: str | None = None) -> str:
    code = str(code).zfill(6)
    if market_hint == "1" or code.startswith(("5", "6", "9")):
        return f"{code}.SH"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def fetch_stock_fund_flow(
    symbol: str,
    client: ResilientHttpClient | None = None,
    *,
    limit: int = 0,
) -> list[dict]:
    """Fetch historical daily moneyflow for one stock.

    Endpoint map: push2his eastmoney fflow/daykline.
    """
    client = client or get_shared_client()
    secid = _secid(symbol)
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "lmt": str(limit),
        "klt": "101",
        "secid": secid,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
    }
    # build query manually for stable tests
    q = "&".join(f"{k}={v}" for k, v in params.items())
    full = f"{url}?{q}"
    res = client.get_json(full, source_key="eastmoney_fflow", headers={**_EM_HEADERS, "Referer": "https://quote.eastmoney.com/"})
    if not res.ok:
        raise RuntimeError(res.error or "fund flow fetch failed")
    data = res.data or {}
    klines = (((data.get("data") or {}).get("klines")) if isinstance(data, dict) else None) or []
    rows: list[dict] = []
    for line in klines:
        # date, main_net, small, med, large, super, ...
        parts = str(line).split(",")
        if len(parts) < 6:
            continue
        def f(i: int) -> float | None:
            try:
                return float(parts[i])
            except (IndexError, ValueError):
                return None
        rows.append(
            {
                "symbol": symbol.upper() if "." in symbol else _symbol_from_sec_parts(symbol),
                "date": parts[0],
                "main_net": f(1),
                "small_net": f(2),
                "med_net": f(3),
                "large_net": f(4),
                "super_net": f(5),
                "main_net_pct": f(6) if len(parts) > 6 else None,
                "source": "eastmoney_fflow",
                "unit_amount": "yuan",
            }
        )
    return rows


def _parse_bkzj_payload(data: Any, *, kind: str) -> list[dict]:
    rows: list[dict] = []
    # Response shapes vary; support list-of-dict and nested data
    payload = data
    if isinstance(data, dict):
        payload = data.get("data") or data.get("result") or data.get("list") or data
    if isinstance(payload, dict):
        # sometimes {diff: [...]} or {list: [...]}
        for key in ("diff", "list", "data", "items"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        return rows
    as_of = date.today().isoformat()
    for i, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        # common field names from go-stock/eastmoney
        code = item.get("code") or item.get("f12") or item.get("BOARD_CODE") or item.get("bk_code") or ""
        name = item.get("name") or item.get("f14") or item.get("BOARD_NAME") or item.get("bk_name") or ""
        main_net = item.get("main_net") or item.get("f62") or item.get("MAIN_NET_INFLOW") or item.get("net_amount")
        change_pct = item.get("change_pct") or item.get("f3") or item.get("CHANGE_RATE") or item.get("pct")
        try:
            main_net_f = float(main_net) if main_net is not None else None
        except (TypeError, ValueError):
            main_net_f = None
        try:
            change_pct_f = float(change_pct) if change_pct is not None else None
        except (TypeError, ValueError):
            change_pct_f = None
        rows.append(
            {
                "code": str(code),
                "name": str(name),
                "main_net": main_net_f,
                "change_pct": change_pct_f,
                "rank": i + 1,
                "as_of": as_of,
                "kind": kind,
                "source": "eastmoney_bkzj",
                "unit_amount": "yuan",
            }
        )
    return rows


def fetch_board_fund_flow_top(client: ResilientHttpClient | None = None) -> list[dict]:
    client = client or get_shared_client()
    url = "https://data.eastmoney.com/dataapi/bkzj/getbkzj?key=f62&code=m%3A90%2Bs%3A4"
    res = client.get_json(url, source_key="eastmoney_bkzj_board", headers=_EM_HEADERS)
    if not res.ok:
        raise RuntimeError(res.error or "board fund flow failed")
    return _parse_bkzj_payload(res.data, kind="board")


def fetch_concept_fund_flow_top(client: ResilientHttpClient | None = None) -> list[dict]:
    client = client or get_shared_client()
    url = "https://data.eastmoney.com/dataapi/bkzj/getbkzj?key=f62&code=m%3A90%2Bt%3A3"
    res = client.get_json(url, source_key="eastmoney_bkzj_concept", headers=_EM_HEADERS)
    if not res.ok:
        raise RuntimeError(res.error or "concept fund flow failed")
    return _parse_bkzj_payload(res.data, kind="concept")


def _ensure_stock_ff_config(store: ExtConfigStore) -> ExtConfig:
    cfg = store.get("ext_fund_flow_stock")
    if cfg:
        return cfg
    cfg = ExtConfig(
        id="ext_fund_flow_stock",
        label="个股资金流",
        mode="timeseries",
        fields=[
            ExtField("symbol", "string", "标的"),
            ExtField("date", "string", "日期"),
            ExtField("main_net", "float", "主力净流入"),
            ExtField("small_net", "float", "小单净流入"),
            ExtField("med_net", "float", "中单净流入"),
            ExtField("large_net", "float", "大单净流入"),
            ExtField("super_net", "float", "超大单净流入"),
            ExtField("main_net_pct", "float", "主力净占比"),
            ExtField("source", "string", "来源"),
            ExtField("unit_amount", "string", "金额单位"),
        ],
        description="东财公开个股历史资金流（on-demand 刷新，非 TickFlow）",
        symbol_map={"type": "mapped", "col": "symbol"},
    )
    store.upsert(cfg)
    return cfg


def _ensure_snapshot_config(store: ExtConfigStore, config_id: str, label: str) -> ExtConfig:
    cfg = store.get(config_id)
    if cfg:
        return cfg
    cfg = ExtConfig(
        id=config_id,
        label=label,
        mode="snapshot",
        fields=[
            ExtField("code", "string", "代码"),
            ExtField("name", "string", "名称"),
            ExtField("main_net", "float", "主力净流入"),
            ExtField("change_pct", "float", "涨跌幅"),
            ExtField("rank", "int", "排名"),
            ExtField("as_of", "string", "日期"),
            ExtField("kind", "string", "类型"),
            ExtField("source", "string", "来源"),
            ExtField("unit_amount", "string", "金额单位"),
        ],
        description=f"{label}（东财公开 bkzj，on-demand）",
    )
    store.upsert(cfg)
    return cfg


def persist_stock_fund_flow(data_dir: Path, symbol: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    store = ExtConfigStore(data_dir)
    cfg = _ensure_stock_ff_config(store)
    # group by date and write timeseries partitions
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        by_date.setdefault(str(r.get("date")), []).append(r)
    n = 0
    for d, group in by_date.items():
        df = pl.DataFrame(group)
        write_ext_parquet(df, cfg, data_dir, snapshot_date=date.fromisoformat(d) if len(d) == 10 else date.today())
        n += len(group)
    return n


def persist_board_snapshot(data_dir: Path, rows: list[dict]) -> int:
    store = ExtConfigStore(data_dir)
    cfg = _ensure_snapshot_config(store, "ext_fund_flow_bk", "行业板块资金流")
    if not rows:
        return 0
    write_ext_parquet(pl.DataFrame(rows), cfg, data_dir, snapshot_date=date.today())
    return len(rows)


def persist_concept_snapshot(data_dir: Path, rows: list[dict]) -> int:
    store = ExtConfigStore(data_dir)
    cfg = _ensure_snapshot_config(store, "ext_fund_flow_concept", "概念板块资金流")
    if not rows:
        return 0
    write_ext_parquet(pl.DataFrame(rows), cfg, data_dir, snapshot_date=date.today())
    return len(rows)


def load_stock_fund_flow(data_dir: Path, symbol: str, *, limit: int = 60) -> list[dict]:
    root = Path(data_dir) / "ext_data" / "ext_fund_flow_stock" / "timeseries"
    if not root.exists():
        return []
    files = sorted(root.rglob("*.parquet"))
    if not files:
        return []
    dfs = []
    for f in files:
        try:
            df = pl.read_parquet(f)
        except Exception:  # noqa: BLE001
            continue
        if "symbol" in df.columns:
            dfs.append(df.filter(pl.col("symbol") == symbol))
    if not dfs:
        return []
    out = pl.concat(dfs, how="diagonal_relaxed")
    if "date" in out.columns:
        out = out.sort("date")
    if limit > 0:
        out = out.tail(limit)
    return out.to_dicts()
