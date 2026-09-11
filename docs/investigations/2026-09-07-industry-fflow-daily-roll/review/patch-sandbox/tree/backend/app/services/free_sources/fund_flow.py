"""EastMoney public fund-flow fetchers (intelligence-only map; own parsers).

Primary board/concept ranking source (aligned with go-stock web money ranks):
  data.eastmoney.com/dataapi/bkzj/getbkzj
    industry secondary: code=m:90+s:4
    industry primary approx: code=m:90+s:2 / t:2 fallback
    concept: code=m:90+t:3
  change_pct enriched via key=f3 (scale-normalized to percent points)

Fallback ranking source:
  dean-stack/a-share-sector-flow-visualizer
    https://push2.eastmoney.com/api/qt/clist/get  (fs=m:90+t:2/3)

Daily history backfill map:
  shenjing023/flowlens
    https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get  (secid=90.BKxxxx)

Intraday minute series map:
  dean-stack/a-share-sector-flow-visualizer
    https://push2.eastmoney.com/api/qt/stock/fflow/kline/get  (klt=1, secid=90.BKxxxx)
"""
from __future__ import annotations

import fcntl
import os
import sqlite3
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

import polars as pl

from app.services.ext_data import ExtConfig, ExtConfigStore, ExtField, write_ext_parquet
from app.services.atomic_io import atomic_write_parquet
from app.services.free_sources.http_resilience import ResilientHttpClient, get_shared_client

_EM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.eastmoney.com/",
}

_EM_UT = "8dec03ba335b81bf4ebdf7b29ec27d15"
_EM_UT_FFLOW = "fa5fd1943c7b386f172d6893dbfba10b"
_EM_UT_DAY = "b2884a393a59ad64002292a3e90d46a5"

# dean-stack CATEGORY_MAP
_CATEGORY_FS = {
    "board": "m:90+t:2",      # 行业
    "industry": "m:90+t:2",
    "concept": "m:90+t:3",    # 概念
    "region": "m:90+t:1",     # 地域
}

_CLIST_FIELDS = "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124,f1,f13"


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


def _board_secid(code: str) -> str:
    c = str(code or "").strip().upper()
    if c.startswith("BK"):
        return f"90.{c}"
    if c.isdigit():
        return f"90.BK{c.zfill(4)}"
    return f"90.{c}"


def _symbol_from_sec_parts(code: str, market_hint: str | None = None) -> str:
    code = str(code).zfill(6)
    if market_hint == "1" or code.startswith(("5", "6", "9")):
        return f"{code}.SH"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def _fnum(v: Any) -> float | None:
    if v is None or v == "" or v == "-":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:  # NaN
        return None
    return x


def _as_of_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_bkzj_change_pct(v: Any) -> float | None:
    """Normalize eastmoney bkzj f3 into percent points for UI.

    bkzj key=f3 is always percent*100 (437 => +4.37%, -54 => -0.54%).
    clist fltt=2 already returns percent points and should not use this helper.
    """
    x = _fnum(v)
    if x is None:
        return None
    return x / 100.0


def _merge_change_pct(rows: list[dict], chg_rows: list[dict]) -> list[dict]:
    by_code: dict[str, float] = {}
    by_name: dict[str, float] = {}
    for item in chg_rows:
        code = str(item.get("code") or "").strip()
        name = str(item.get("name") or "").strip()
        pct = item.get("change_pct")
        if pct is None:
            continue
        if code:
            by_code[code] = float(pct)
        if name:
            by_name[name] = float(pct)
    for row in rows:
        if row.get("change_pct") is not None:
            continue
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or "").strip()
        if code and code in by_code:
            row["change_pct"] = by_code[code]
        elif name and name in by_name:
            row["change_pct"] = by_name[name]
    return rows


def _sort_rank_rows(rows: list[dict]) -> list[dict]:
    rows = [r for r in rows if isinstance(r, dict)]
    rows.sort(key=lambda r: (r.get("main_net") is None, -(r.get("main_net") or 0.0)))
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    return rows



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
    params = {
        "lmt": str(limit),
        "klt": "101",
        "secid": secid,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "ut": _EM_UT_DAY,
    }
    q = urlencode(params)
    hosts = [
        (
            "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
            "https://quote.eastmoney.com/",
        ),
        (
            "https://emdatah5.eastmoney.com/dc/ZJLX/getDBHistoryData",
            f"https://emdatah5.eastmoney.com/dc/zjlx/stock?fc={secid}",
        ),
        (
            "https://push2delay.eastmoney.com/api/qt/stock/fflow/daykline/get",
            "https://quote.eastmoney.com/",
        ),
        (
            "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get",
            "https://quote.eastmoney.com/",
        ),
    ]
    last_err: str | None = None
    for i, (host, referer) in enumerate(hosts):
        res = client.get_json(
            f"{host}?{q}",
            source_key=f"eastmoney_stock_fflow_{i}",
            headers={**_EM_HEADERS, "Referer": referer},
            timeout=5.0,
            cooldown_on_error=5.0,
        )
        if not res.ok:
            last_err = res.error or f"{host} failed"
            continue
        data = res.data or {}
        klines = (((data.get("data") or {}).get("klines")) if isinstance(data, dict) else None) or []
        if not klines:
            last_err = f"{host} returned empty klines"
            continue
        rows: list[dict] = []
        for line in klines:
            parts = str(line).split(",")
            if len(parts) < 6:
                continue
            rows.append(
                {
                    "symbol": symbol.upper() if "." in symbol else _symbol_from_sec_parts(symbol),
                    "date": parts[0],
                    "main_net": _fnum(parts[1]),
                    "small_net": _fnum(parts[2]),
                    "med_net": _fnum(parts[3]),
                    "large_net": _fnum(parts[4]),
                    "super_net": _fnum(parts[5]),
                    "main_net_pct": _fnum(parts[6]) if len(parts) > 6 else None,
                    "source": "eastmoney_fflow",
                    "unit_amount": "yuan",
                }
            )
        if rows:
            return rows
        last_err = f"{host} returned no valid rows"
    detail = f": {last_err}" if last_err else ""
    raise RuntimeError(f"东方财富个股资金流暂时不可用{detail}")


def _parse_bkzj_payload(data: Any, *, kind: str) -> list[dict]:
    rows: list[dict] = []
    payload = data
    if isinstance(data, dict):
        payload = data.get("data") or data.get("result") or data.get("list") or data
    if isinstance(payload, dict):
        for key in ("diff", "list", "data", "items"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        return rows
    as_of = _as_of_now()
    for i, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        code = item.get("f12") or item.get("code") or item.get("BOARD_CODE") or item.get("bk_code")
        name = item.get("f14") or item.get("name") or item.get("BOARD_NAME") or item.get("bk_name")
        main_net = item.get("f62")
        if main_net is None:
            main_net = item.get("main_net") or item.get("NET_INFLOW") or item.get("net_inflow")
        change_pct = item.get("f3") if "f3" in item else item.get("change_pct")
        if change_pct is None:
            change_pct = item.get("CHANGE_RATE")
        main_net_f = _fnum(main_net)
        change_pct_f = _normalize_bkzj_change_pct(change_pct)
        rows.append(
            {
                "code": str(code) if code is not None else "",
                "name": str(name) if name is not None else "",
                "main_net": main_net_f,
                "change_pct": change_pct_f,
                "main_net_pct": _fnum(item.get("f184")),
                "price": _fnum(item.get("f2")),
                "rank": i + 1,
                "as_of": as_of,
                "kind": kind,
                "source": "eastmoney_bkzj",
                "unit_amount": "yuan",
            }
        )
    return _sort_rank_rows(rows)


def _parse_clist_payload(data: Any, *, kind: str) -> list[dict]:
    """Normalize dean-stack style push2 clist ranking payload."""
    rows: list[dict] = []
    payload = data
    if isinstance(data, dict):
        payload = data.get("data") or data
    items = None
    if isinstance(payload, dict):
        items = payload.get("diff")
    elif isinstance(payload, list):
        items = payload
    if not isinstance(items, list):
        return rows

    as_of = _as_of_now()
    scored: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = item.get("f12") or item.get("code")
        name = item.get("f14") or item.get("name")
        if not code and not name:
            continue
        scored.append(
            {
                "code": str(code or ""),
                "name": str(name or ""),
                "main_net": _fnum(item.get("f62") if "f62" in item else item.get("main_net")),
                "change_pct": _fnum(item.get("f3") if "f3" in item else item.get("change_pct")),
                "main_net_pct": _fnum(item.get("f184") if "f184" in item else item.get("main_net_pct")),
                "price": _fnum(item.get("f2") if "f2" in item else item.get("price")),
                "leader_name": str(item.get("f204") or item.get("leader_name") or "") or None,
                "leader_code": str(item.get("f205") or item.get("leader_code") or "") or None,
                "as_of": as_of,
                "kind": kind,
                "source": "eastmoney_clist",
                "unit_amount": "yuan",
            }
        )
    scored.sort(key=lambda r: (r.get("main_net") is None, -(r.get("main_net") or 0.0)))
    for i, row in enumerate(scored):
        row["rank"] = i + 1
        rows.append(row)
    return rows


def _fetch_bkzj_rows(
    *,
    kind: str,
    code: str,
    key: str,
    client: ResilientHttpClient,
    source_key: str,
) -> list[dict]:
    url = "https://data.eastmoney.com/dataapi/bkzj/getbkzj?" + urlencode({"key": key, "code": code})
    res = client.get_json(url, source_key=source_key, headers=_EM_HEADERS, timeout=15.0)
    if not res.ok or not res.data:
        return []
    rows = _parse_bkzj_payload(res.data, kind=kind)
    return rows


def fetch_board_fund_flow_top_legacy(client: ResilientHttpClient | None = None) -> list[dict]:
    """go-stock aligned industry ranking via dataapi (s:4 primary, t:2 fallback)."""
    client = client or get_shared_client()
    # Prefer secondary industry list used by go-stock market money ranks / local collector.
    rows = _fetch_bkzj_rows(
        kind="board",
        code="m:90+s:4",
        key="f62",
        client=client,
        source_key="eastmoney_bkzj_board_s4",
    )
    if not rows:
        rows = _fetch_bkzj_rows(
            kind="board",
            code="m:90+t:2",
            key="f62",
            client=client,
            source_key="eastmoney_bkzj_board_t2",
        )
    if not rows:
        raise RuntimeError("board fund flow failed")

    # Enrich change_pct from key=f3 (same code universe)
    chg = _fetch_bkzj_rows(
        kind="board",
        code="m:90+s:4",
        key="f3",
        client=client,
        source_key="eastmoney_bkzj_board_s4_chg",
    )
    if not chg:
        chg = _fetch_bkzj_rows(
            kind="board",
            code="m:90+t:2",
            key="f3",
            client=client,
            source_key="eastmoney_bkzj_board_t2_chg",
        )
    return _merge_change_pct(rows, chg)


def fetch_concept_fund_flow_top_legacy(client: ResilientHttpClient | None = None) -> list[dict]:
    """go-stock aligned concept ranking via dataapi t:3."""
    client = client or get_shared_client()
    rows = _fetch_bkzj_rows(
        kind="concept",
        code="m:90+t:3",
        key="f62",
        client=client,
        source_key="eastmoney_bkzj_concept",
    )
    if not rows:
        raise RuntimeError("concept fund flow failed")
    chg = _fetch_bkzj_rows(
        kind="concept",
        code="m:90+t:3",
        key="f3",
        client=client,
        source_key="eastmoney_bkzj_concept_chg",
    )
    return _merge_change_pct(rows, chg)


def fetch_board_ranking(
    kind: Literal["board", "concept", "industry", "region"] = "board",
    client: ResilientHttpClient | None = None,
    *,
    page_size: int = 2000,
) -> list[dict]:
    """Fetch industry/concept/region ranking.

    Priority aligned with go-stock web money ranks:
      1) data.eastmoney.com/dataapi/bkzj/getbkzj (+ f3 change enrichment)
      2) push2 clist fallback (dean-stack)
    """
    client = client or get_shared_client()
    kind_norm: str = "board" if kind in ("board", "industry") else kind

    # Primary: dataapi (works when push2 is blocked/slow)
    if kind_norm == "board":
        try:
            rows = fetch_board_fund_flow_top_legacy(client=client)
            if rows:
                return rows
        except Exception:
            pass
    elif kind_norm == "concept":
        try:
            rows = fetch_concept_fund_flow_top_legacy(client=client)
            if rows:
                return rows
        except Exception:
            pass

    # Fallback: dean-stack clist
    fs = _CATEGORY_FS.get(kind, _CATEGORY_FS["board"])
    params = {
        "pn": "1",
        "pz": str(max(20, min(int(page_size), 2000))),
        "po": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fid": "f62",
        "ut": _EM_UT,
        "fs": fs,
        "fields": _CLIST_FIELDS,
    }
    url = f"https://push2.eastmoney.com/api/qt/clist/get?{urlencode(params)}"
    res = client.get_json(
        url,
        source_key=f"eastmoney_clist_{kind_norm}",
        headers=_EM_HEADERS,
        timeout=15.0,
    )
    if res.ok:
        rows = _parse_clist_payload(res.data, kind=kind_norm)
        if rows:
            return rows
    return []


def fetch_board_fund_flow_top(client: ResilientHttpClient | None = None) -> list[dict]:
    return fetch_board_ranking("board", client=client)


def fetch_concept_fund_flow_top(client: ResilientHttpClient | None = None) -> list[dict]:
    return fetch_board_ranking("concept", client=client)


def fetch_board_intraday_flow(
    code: str,
    client: ResilientHttpClient | None = None,
) -> dict:
    """Fetch one board/concept minute main-net series (dean-stack kline map)."""
    client = client or get_shared_client()
    board = str(code or "").strip().upper()
    if not board:
        return {"code": "", "name": "", "trade_date": "", "points": []}
    params = {
        "lmt": "0",
        "klt": "1",
        "secid": _board_secid(board),
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56",
        "ut": _EM_UT_FFLOW,
    }
    url = f"https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?{urlencode(params)}"
    res = client.get_json(
        url,
        source_key="eastmoney_board_fflow_min",
        headers=_EM_HEADERS,
        timeout=15.0,
    )
    if not res.ok:
        raise RuntimeError(res.error or f"intraday fund flow failed for {board}")
    data = (res.data or {}).get("data") if isinstance(res.data, dict) else None
    data = data or {}
    name = str(data.get("name") or board)
    points: list[dict] = []
    for line in data.get("klines") or []:
        parts = str(line).split(",")
        if len(parts) < 2:
            continue
        ts = parts[0]
        points.append(
            {
                "code": board,
                "name": name,
                "timestamp": ts,
                "time": ts[11:16] if len(ts) >= 16 else ts,
                "date": ts[:10] if len(ts) >= 10 else "",
                "main_net": _fnum(parts[1]),
                "small_net": _fnum(parts[2]) if len(parts) > 2 else None,
                "med_net": _fnum(parts[3]) if len(parts) > 3 else None,
                "large_net": _fnum(parts[4]) if len(parts) > 4 else None,
                "super_net": _fnum(parts[5]) if len(parts) > 5 else None,
                "source": "eastmoney_fflow_min",
                "unit_amount": "yuan",
            }
        )
    trade_date = points[0]["date"] if points else date.today().isoformat()
    return {
        "code": board,
        "name": name,
        "trade_date": trade_date,
        "updated_time": points[-1]["time"] if points else "",
        "points": points,
        "count": len(points),
        "source": "eastmoney_fflow_min",
    }


def _go_stock_db_candidates() -> list[Path]:
    cands: list[Path] = []
    env_db = (os.environ.get("GO_STOCK_DB") or "").strip()
    if env_db:
        cands.append(Path(env_db).expanduser())
    env_dir = (os.environ.get("GO_STOCK_DATA_DIR") or "").strip()
    if env_dir:
        cands.append(Path(env_dir).expanduser() / "stock.db")
    # common sibling layout in this workspace
    here = Path(__file__).resolve()
    # fund_flow.py -> free_sources/services/app/backend/one-trading/Trading
    for idx in (5, 4, 3, 2):
        try:
            cands.append(here.parents[idx] / "go-stock" / "data" / "stock.db")
        except IndexError:
            pass
    cands.append(Path("/Users/simon/Trading/go-stock/data/stock.db"))
    out: list[Path] = []
    seen: set[str] = set()
    for p in cands:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        key = str(rp)
        if key in seen:
            continue
        seen.add(key)
        out.append(rp)
    return out


def _fetch_board_daily_history_from_go_stock(
    code: str,
    *,
    kind: Literal["board", "concept"] = "board",
    limit: int = 120,
) -> list[dict]:
    """Aggregate local go-stock minute/EOD snapshots into daily main_net points."""
    board = str(code or "").strip().upper()
    if not board:
        return []
    table = "concept_fund_flow" if kind == "concept" else "bk_fund_flow"
    db_path = next((p for p in _go_stock_db_candidates() if p.exists()), None)
    if db_path is None:
        return []
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        # one point per day: prefer 15:00 snapshot, else last snap of the day
        rows = cur.execute(
            f"""
            WITH daily AS (
              SELECT
                substr(snap_time, 1, 10) AS d,
                code,
                name,
                net_inflow,
                snap_time,
                CASE WHEN snap_time LIKE '% 15:00:%' THEN 1 ELSE 0 END AS is_eod
              FROM {table}
              WHERE code = ?
            ),
            ranked AS (
              SELECT *,
                     ROW_NUMBER() OVER (
                       PARTITION BY d
                       ORDER BY is_eod DESC, snap_time DESC
                     ) AS rn
              FROM daily
            )
            SELECT d, code, name, net_inflow, snap_time
            FROM ranked
            WHERE rn = 1
            ORDER BY d DESC
            LIMIT ?
            """,
            (board, max(1, min(int(limit), 500))),
        ).fetchall()
        con.close()
    except Exception:
        return []

    out: list[dict] = []
    for r in reversed(rows):  # ascending
        out.append(
            {
                "code": board,
                "name": str(r["name"] or board),
                "date": str(r["d"]),
                "main_net": _fnum(r["net_inflow"]),
                "small_net": None,
                "med_net": None,
                "large_net": None,
                "super_net": None,
                "main_net_pct": None,
                "source": "go_stock_local_snapshot",
                "unit_amount": "yuan",
                "snap_time": str(r["snap_time"] or ""),
            }
        )
    return out


def fetch_board_daily_history(
    code: str,
    client: ResilientHttpClient | None = None,
    *,
    limit: int = 120,
    kind: Literal["board", "concept"] = "board",
    allow_local_fallback: bool = False,
    prefer_h5: bool = False,
) -> list[dict]:
    """Fetch board/concept daily main-net history.

    Default is Eastmoney only. Local go-stock `stock.db` is opt-in via
    ``allow_local_fallback=True`` and must not be the refresh/empty-cache path.
    """
    client = client or get_shared_client()
    board = str(code or "").strip().upper()
    if not board:
        return []
    local = (
        _fetch_board_daily_history_from_go_stock(board, kind=kind, limit=limit)
        if allow_local_fallback
        else []
    )
    env_pref = (os.environ.get("FUND_FLOW_HISTORY_PREFER_LOCAL") or "").strip().lower()
    if env_pref in {"1", "true", "yes"}:
        prefer_local = True
    elif env_pref in {"0", "false", "no"}:
        prefer_local = False
    else:
        # auto: if local go-stock history exists for this code, use it first (current network often blocks EM daykline)
        prefer_local = bool(local)
    if allow_local_fallback and prefer_local and local:
        return local

    params = {
        "lmt": str(max(1, min(int(limit), 500))),
        "klt": "101",
        "secid": _board_secid(board),
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
        "ut": _EM_UT_DAY,
    }
    q = urlencode(params)
    secid = _board_secid(board)
    hosts = [
        (
            "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
            "https://data.eastmoney.com/",
        ),
        (
            "https://emdatah5.eastmoney.com/dc/ZJLX/getDBHistoryData",
            f"https://emdatah5.eastmoney.com/dc/zjlx/stock?fc={secid}",
        ),
        (
            "https://push2delay.eastmoney.com/api/qt/stock/fflow/daykline/get",
            "https://data.eastmoney.com/",
        ),
        (
            "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get",
            "https://data.eastmoney.com/",
        ),
    ]
    if prefer_h5:
        hosts = [hosts[1], hosts[0], hosts[2], hosts[3]]
    last_err: str | None = None
    for i, (host, referer) in enumerate(hosts):
        url = f"{host}?{q}"
        # separate cooldown keys so one dead host does not freeze the whole batch
        res = client.get_json(
            url,
            source_key=f"eastmoney_board_fflow_day_{i}",
            headers={**_EM_HEADERS, "Referer": referer},
            timeout=8.0,
            cooldown_on_error=5.0,
        )
        if not res.ok:
            last_err = res.error or f"{host} failed"
            continue
        data = (res.data or {}).get("data") if isinstance(res.data, dict) else None
        data = data or {}
        klines = data.get("klines") or []
        if not klines:
            last_err = f"{host} empty klines"
            continue
        name = str(data.get("name") or board)
        rows: list[dict] = []
        for line in klines:
            parts = str(line).split(",")
            if len(parts) < 2:
                continue
            rows.append(
                {
                    "code": board,
                    "name": name,
                    "date": parts[0][:10],
                    "main_net": _fnum(parts[1]),
                    "small_net": _fnum(parts[2]) if len(parts) > 2 else None,
                    "med_net": _fnum(parts[3]) if len(parts) > 3 else None,
                    "large_net": _fnum(parts[4]) if len(parts) > 4 else None,
                    "super_net": _fnum(parts[5]) if len(parts) > 5 else None,
                    "main_net_pct": _fnum(parts[6]) if len(parts) > 6 else None,
                    "source": "eastmoney_fflow_day",
                    "unit_amount": "yuan",
                }
            )
        if rows:
            rows.sort(key=lambda r: str(r.get("date") or ""))
            if int(limit) > 0:
                rows = rows[-int(limit):]
            return rows

    if allow_local_fallback and local:
        return local
    raise RuntimeError(last_err or f"daily fund flow history failed for {board}")


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
            ExtField("main_net_pct", "float", "主力净占比"),
            ExtField("price", "float", "最新价"),
            ExtField("leader_name", "string", "领涨股"),
            ExtField("leader_code", "string", "领涨股代码"),
            ExtField("rank", "int", "排名"),
            ExtField("as_of", "string", "快照时间"),
            ExtField("kind", "string", "类型"),
            ExtField("source", "string", "来源"),
            ExtField("unit_amount", "string", "金额单位"),
        ],
        description=f"{label}（东财 push2 clist / bkzj 兜底，on-demand）",
    )
    store.upsert(cfg)
    return cfg


def _ensure_board_daily_config(store: ExtConfigStore, kind: str) -> ExtConfig:
    config_id = "ext_fund_flow_bk_daily" if kind == "board" else "ext_fund_flow_concept_daily"
    label = "行业板块资金流日线" if kind == "board" else "概念板块资金流日线"
    cfg = store.get(config_id)
    if cfg:
        return cfg
    cfg = ExtConfig(
        id=config_id,
        label=label,
        mode="timeseries",
        fields=[
            ExtField("code", "string", "板块代码"),
            ExtField("name", "string", "板块名称"),
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
        description=f"{label}（东财 daykline 历史回补，on-demand）",
        symbol_map={"type": "mapped", "col": "code"},
    )
    store.upsert(cfg)
    return cfg


def _ensure_board_minute_config(store: ExtConfigStore, kind: str) -> ExtConfig:
    config_id = "ext_fund_flow_bk_minute" if kind == "board" else "ext_fund_flow_concept_minute"
    label = "行业板块资金流分时" if kind == "board" else "概念板块资金流分时"
    cfg = store.get(config_id)
    if cfg:
        return cfg
    cfg = ExtConfig(
        id=config_id,
        label=label,
        mode="timeseries",
        fields=[
            ExtField("code", "string", "板块代码"),
            ExtField("name", "string", "板块名称"),
            ExtField("date", "string", "日期"),
            ExtField("timestamp", "string", "时间戳"),
            ExtField("time", "string", "时刻"),
            ExtField("main_net", "float", "主力净流入"),
            ExtField("small_net", "float", "小单净流入"),
            ExtField("med_net", "float", "中单净流入"),
            ExtField("large_net", "float", "大单净流入"),
            ExtField("super_net", "float", "超大单净流入"),
            ExtField("source", "string", "来源"),
            ExtField("unit_amount", "string", "金额单位"),
        ],
        description=f"{label}（东财分钟 kline，交易日 on-demand/定时沉淀）",
        symbol_map={"type": "mapped", "col": "code"},
    )
    store.upsert(cfg)
    return cfg


def persist_stock_fund_flow(data_dir: Path, symbol: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    store = ExtConfigStore(data_dir)
    cfg = _ensure_stock_ff_config(store)
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        by_date.setdefault(str(r.get("date")), []).append(r)
    n = 0
    for d, group in by_date.items():
        df = pl.DataFrame(group)
        write_ext_parquet(
            df,
            cfg,
            data_dir,
            snapshot_date=date.fromisoformat(d) if len(d) == 10 else date.today(),
        )
        n += len(group)
    return n


def _overwrite_snapshot_parquet(data_dir: Path, config_id: str, rows: list[dict]) -> int:
    """Full replace snapshot parquet.

    write_ext_parquet merges by first key and would keep stale board codes from an
    older universe (e.g. t:2 primary mixed into s:4 secondary). Ranking snapshots
    must be atomic replace to stay consistent with go-stock money ranks.
    """
    if not rows:
        return 0
    out_dir = Path(data_dir) / "ext_data" / config_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "part.parquet"
    df = pl.DataFrame(rows)
    # stable column order for UI/debug
    preferred = [
        "code", "name", "main_net", "change_pct", "main_net_pct", "price",
        "rank", "as_of", "kind", "source", "unit_amount",
    ]
    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    df = df.select(cols)
    atomic_write_parquet(df, out_path)
    return len(rows)


def persist_board_snapshot(data_dir: Path, rows: list[dict]) -> int:
    store = ExtConfigStore(data_dir)
    _ensure_snapshot_config(store, "ext_fund_flow_bk", "行业板块资金流")
    return _overwrite_snapshot_parquet(data_dir, "ext_fund_flow_bk", rows)


def persist_concept_snapshot(data_dir: Path, rows: list[dict]) -> int:
    store = ExtConfigStore(data_dir)
    _ensure_snapshot_config(store, "ext_fund_flow_concept", "概念板块资金流")
    return _overwrite_snapshot_parquet(data_dir, "ext_fund_flow_concept", rows)


def persist_board_daily_history(
    data_dir: Path,
    code: str,
    rows: list[dict],
    *,
    kind: Literal["board", "concept"] = "board",
) -> int:
    """Merge daily rows by date+code. Never replace a date partition wholesale."""
    if not rows:
        return 0
    _ = str(code or "").strip()
    store = ExtConfigStore(data_dir)
    cfg = _ensure_board_daily_config(store, kind)
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        d = str(r.get("date") or "")[:10]
        if not d:
            continue
        by_date.setdefault(d, []).append(r)
    n = 0
    for d, group in by_date.items():
        write_ext_parquet(
            pl.DataFrame(group),
            cfg,
            data_dir,
            snapshot_date=date.fromisoformat(d),
        )
        n += len(group)
    return n


def load_board_snapshot_items(
    data_dir: Path,
    *,
    kind: Literal["board", "concept"] = "board",
) -> list[dict]:
    snapshot_id = "ext_fund_flow_bk" if kind == "board" else "ext_fund_flow_concept"
    path = Path(data_dir) / "ext_data" / snapshot_id / "part.parquet"
    if not path.exists():
        return []
    try:
        return pl.read_parquet(path).to_dicts()
    except Exception:  # noqa: BLE001
        return []


def backfill_industry_daily_from_h5(
    data_dir: Path,
    *,
    client: ResilientHttpClient | None = None,
    codes: list[str] | None = None,
    limit: int = 120,
    batch_size: int = 8,
    pause_s: float = 0.35,
    pause_code_s: float = 0.0,
    min_days: int = 63,
    kind: Literal["board", "concept"] = "board",
) -> dict:
    """Backfill current industry or concept snapshot from Eastmoney H5 only.

    Writes `ext_fund_flow_bk_daily` / `ext_fund_flow_concept_daily` by date+code
    merge. Does not refresh the ranking snapshot, and does not persist
    go-stock / TickFlow / stockdb rows.
    """
    client = client or get_shared_client()
    kind = "concept" if kind == "concept" else "board"
    snapshot = load_board_snapshot_items(data_dir, kind=kind)
    names = {
        str(row.get("code") or "").upper(): row.get("name")
        for row in snapshot
        if str(row.get("code") or "").strip()
    }
    if codes:
        selected = [str(c).strip().upper() for c in codes if str(c).strip()]
    else:
        selected = [str(row.get("code") or "").upper() for row in snapshot if str(row.get("code") or "").strip()]
    seen: set[str] = set()
    universe: list[str] = []
    for code in selected:
        if not code or code in seen:
            continue
        seen.add(code)
        universe.append(code)

    ok_codes: list[str] = []
    short_codes: list[dict] = []
    failed: list[dict] = []
    total_points = 0
    date_min: str | None = None
    date_max: str | None = None
    step = max(1, int(batch_size))
    for i in range(0, len(universe), step):
        batch = universe[i : i + step]
        batch_rows: list[dict] = []
        for code in batch:
            try:
                hist = fetch_board_daily_history(
                    code,
                    client=client,
                    limit=limit,
                    kind=kind,
                    allow_local_fallback=False,
                    prefer_h5=True,
                )
            except Exception as e:  # noqa: BLE001
                failed.append({"code": code, "error": str(e)})
                continue
            hist = [row for row in hist if str(row.get("source")) == "eastmoney_fflow_day"]
            for row in hist:
                if not row.get("name"):
                    row["name"] = names.get(code) or code
            if not hist:
                failed.append({"code": code, "error": "empty eastmoney history"})
                continue
            dates = [str(row.get("date") or "")[:10] for row in hist if row.get("date")]
            if dates:
                lo, hi = min(dates), max(dates)
                date_min = lo if date_min is None else min(date_min, lo)
                date_max = hi if date_max is None else max(date_max, hi)
            if len(hist) < int(min_days):
                short_codes.append({"code": code, "days": len(hist), "start": dates[0] if dates else None, "end": dates[-1] if dates else None})
            batch_rows.extend(hist)
            ok_codes.append(code)
            if pause_code_s > 0:
                time.sleep(float(pause_code_s))
        if batch_rows:
            total_points += persist_board_daily_history(data_dir, batch[0], batch_rows, kind=kind)
        if pause_s > 0 and i + step < len(universe):
            time.sleep(float(pause_s))

    return {
        "ok": bool(ok_codes) and not failed,
        "kind": kind,
        "selected": len(universe),
        "history_codes": ok_codes,
        "history_points": total_points,
        "short": short_codes,
        "failed": failed,
        "source": "eastmoney_fflow_day",
        "limit": int(limit),
        "min_days": int(min_days),
        "start": date_min,
        "end": date_max,
        "note": (
            "东财 H5/daykline 概念日线回补，按 date+code 合并，不写 go-stock"
            if kind == "concept"
            else "东财 H5/daykline 行业日线回补，按 date+code 合并，不写 go-stock"
        ),
    }


_INDUSTRY_ROLL_THREAD_LOCK = threading.Lock()
_INDUSTRY_ROLL_LOCK_NAME = ".industry_daily_roll.lock"


def _as_iso_day(value: object) -> str | None:
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            text = str(iso())
        except Exception:
            return None
        return text[:10] if len(text) >= 10 else None
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else None


def _is_open_flag(value: object) -> bool:
    if value is True or value == 1:
        return True
    if value is False or value == 0 or value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes"}


def _load_local_trading_calendar(data_dir: Path) -> pl.DataFrame | None:
    path = Path(data_dir) / "reference" / "trading_calendar" / "calendar.parquet"
    if not path.exists():
        return None
    try:
        frame = pl.read_parquet(path)
    except Exception:
        return None
    if frame.is_empty():
        return None
    return frame


def assess_industry_window_freshness(
    data_dir: Path,
    *,
    data_as_of: str | None,
    as_of_today: date | None = None,
) -> dict[str, Any]:
    """Judge industry window freshness from the local trading calendar only.

    Window completeness is a separate field. Missing calendar coverage is
    unknown; kline dates are never used as a legal calendar.
    """
    today = as_of_today or date.today()
    today_s = today.isoformat()
    payload = {
        "data_as_of": data_as_of,
        "freshness_status": "unknown",
        "freshness_note": "无法确定",
        "expected_trading_day": None,
        "calendar_covers": False,
    }
    calendar = _load_local_trading_calendar(data_dir)
    if calendar is None:
        payload["freshness_note"] = "无法确定（交易日历缺失或无法读取）"
        return payload
    date_col = "trade_date" if "trade_date" in calendar.columns else (
        "date" if "date" in calendar.columns else None
    )
    if date_col is None:
        payload["freshness_note"] = "无法确定（交易日历缺少日期列）"
        return payload
    all_days: list[str] = []
    open_days: list[str] = []
    for row in calendar.to_dicts():
        day = _as_iso_day(row.get(date_col))
        if not day:
            continue
        all_days.append(day)
        if _is_open_flag(row.get("is_open")):
            open_days.append(day)
    if not all_days:
        payload["freshness_note"] = "无法确定（交易日历无日期）"
        return payload
    if max(all_days) < today_s:
        payload["freshness_note"] = "无法确定（交易日历未覆盖到当日）"
        return payload
    payload["calendar_covers"] = True
    expected = max((day for day in open_days if day <= today_s), default=None)
    payload["expected_trading_day"] = expected
    if not data_as_of or not expected:
        payload["freshness_note"] = "无法确定"
        return payload
    if data_as_of == expected:
        payload["freshness_status"] = "fresh"
        payload["freshness_note"] = "足够新"
        return payload
    if data_as_of < expected:
        payload["freshness_status"] = "stale"
        payload["freshness_note"] = "已陈旧"
        return payload
    payload["freshness_note"] = "无法确定（数据截止日超出日历可判定范围）"
    return payload


def _attach_industry_freshness(
    payload: dict[str, Any],
    data_dir: Path,
    *,
    as_of_today: date | None = None,
) -> dict[str, Any]:
    if payload.get("kind") != "board":
        return payload
    payload.update(
        assess_industry_window_freshness(
            data_dir,
            data_as_of=payload.get("end"),
            as_of_today=as_of_today,
        )
    )
    return payload


def _industry_h5_latest_coverage(
    data_dir: Path,
    snapshot_codes: list[str],
) -> tuple[str | None, bool, int]:
    daily_root = Path(data_dir) / "ext_data" / "ext_fund_flow_bk_daily" / "timeseries"
    wanted = {str(code).strip().upper() for code in snapshot_codes if str(code).strip()}
    if not daily_root.exists() or not wanted:
        return None, False, 0
    frames: list[pl.DataFrame] = []
    for path in daily_root.rglob("*.parquet"):
        try:
            frames.append(pl.read_parquet(path))
        except Exception:
            continue
    if not frames:
        return None, False, 0
    daily = pl.concat(frames, how="diagonal_relaxed")
    if daily.is_empty() or "date" not in daily.columns or "code" not in daily.columns:
        return None, False, 0
    daily = daily.with_columns(
        pl.col("code").cast(pl.Utf8).str.to_uppercase().alias("code"),
        pl.col("date").cast(pl.Utf8).str.slice(0, 10).alias("date"),
    )
    if "source" in daily.columns:
        daily = daily.filter(pl.col("source") == "eastmoney_fflow_day")
    if daily.is_empty():
        return None, False, 0
    latest = max(str(value) for value in daily["date"].to_list() if value)
    have = {
        str(value)
        for value in daily.filter(pl.col("date") == latest)["code"].to_list()
        if value
    }
    covered = len(wanted & have)
    return latest, bool(wanted) and wanted <= have, covered


def _acquire_industry_roll_lock(data_dir: Path):
    lock_dir = Path(data_dir) / "ext_data" / "ext_fund_flow_bk_daily"
    lock_dir.mkdir(parents=True, exist_ok=True)
    handle = open(lock_dir / _INDUSTRY_ROLL_LOCK_NAME, "a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def _release_industry_roll_lock(handle) -> None:
    if handle is None:
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _industry_roll_busy_result() -> dict[str, Any]:
    return {
        "ok": False,
        "kind": "board",
        "status": "busy",
        "skipped_lock": True,
        "selected": 0,
        "history_codes": [],
        "failed": [],
        "latest_data_date": None,
        "latest_day_complete": False,
        "source": "eastmoney_fflow_day",
        "note": "已有行业日线续更在进行，跳过本次",
    }


def _roll_industry_daily_from_h5_unlocked(
    data_dir: Path,
    *,
    client: ResilientHttpClient | None,
    limit: int,
    batch_size: int,
    pause_s: float,
    pause_code_s: float,
) -> dict[str, Any]:
    snapshot = load_board_snapshot_items(data_dir, kind="board")
    names = {
        str(row.get("code") or "").upper(): row.get("name")
        for row in snapshot
        if str(row.get("code") or "").strip()
    }
    universe: list[str] = []
    seen: set[str] = set()
    for row in snapshot:
        code = str(row.get("code") or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        universe.append(code)
    if not universe:
        return {
            "ok": False,
            "kind": "board",
            "status": "no_snapshot",
            "selected": 0,
            "history_codes": [],
            "failed": [],
            "latest_data_date": None,
            "latest_day_complete": False,
            "source": "eastmoney_fflow_day",
            "note": "本地行业快照为空，未联网补目录",
        }

    client = client or get_shared_client()
    ok_codes: list[str] = []
    failed: list[dict] = []
    total_points = 0
    date_min: str | None = None
    date_max: str | None = None
    step = max(1, int(batch_size))
    for i in range(0, len(universe), step):
        batch = universe[i : i + step]
        batch_rows: list[dict] = []
        for code in batch:
            try:
                hist = fetch_board_daily_history(
                    code,
                    client=client,
                    limit=limit,
                    kind="board",
                    allow_local_fallback=False,
                    prefer_h5=True,
                )
            except Exception as e:  # noqa: BLE001
                failed.append({"code": code, "error": str(e)})
                continue
            hist = [row for row in hist if str(row.get("source")) == "eastmoney_fflow_day"]
            for row in hist:
                if not row.get("name"):
                    row["name"] = names.get(code) or code
            if not hist:
                failed.append({"code": code, "error": "empty eastmoney history"})
                continue
            dates = [str(row.get("date") or "")[:10] for row in hist if row.get("date")]
            if dates:
                lo, hi = min(dates), max(dates)
                date_min = lo if date_min is None else min(date_min, lo)
                date_max = hi if date_max is None else max(date_max, hi)
            batch_rows.extend(hist)
            ok_codes.append(code)
            if pause_code_s > 0:
                time.sleep(float(pause_code_s))
        if batch_rows:
            total_points += persist_board_daily_history(data_dir, batch[0], batch_rows, kind="board")
        if pause_s > 0 and i + step < len(universe):
            time.sleep(float(pause_s))

    latest_data_date, latest_day_complete, latest_day_covered = _industry_h5_latest_coverage(
        data_dir,
        universe,
    )
    status = "ok"
    if failed and ok_codes:
        status = "partial"
    elif failed:
        status = "failed"
    elif not latest_day_complete:
        status = "incomplete_latest_day"
    return {
        "ok": bool(ok_codes) and not failed and latest_day_complete,
        "kind": "board",
        "status": status,
        "selected": len(universe),
        "history_codes": ok_codes,
        "history_points": total_points,
        "failed": failed,
        "latest_data_date": latest_data_date,
        "latest_day_complete": latest_day_complete,
        "latest_day_covered": latest_day_covered,
        "source": "eastmoney_fflow_day",
        "limit": int(limit),
        "start": date_min,
        "end": date_max,
        "note": "东财 H5 行业日线续更，按本地快照全集、date+code 合并，不写 go-stock",
    }


def roll_industry_daily_from_h5(
    data_dir: Path,
    *,
    client: ResilientHttpClient | None = None,
    limit: int = 120,
    batch_size: int = 8,
    pause_s: float = 0.35,
    pause_code_s: float = 0.0,
) -> dict:
    """Continue industry daily history for the local snapshot universe.

    Uses Eastmoney H5 only. Does not refresh the ranking snapshot, does not
    call the Top20 history helper, and does not persist stock.db rows.
    """
    if not _INDUSTRY_ROLL_THREAD_LOCK.acquire(blocking=False):
        return _industry_roll_busy_result()
    handle = None
    try:
        handle = _acquire_industry_roll_lock(data_dir)
        if handle is None:
            return _industry_roll_busy_result()
        return _roll_industry_daily_from_h5_unlocked(
            data_dir,
            client=client,
            limit=limit,
            batch_size=batch_size,
            pause_s=pause_s,
            pause_code_s=pause_code_s,
        )
    finally:
        _release_industry_roll_lock(handle)
        _INDUSTRY_ROLL_THREAD_LOCK.release()


def persist_board_intraday(
    data_dir: Path,
    payload: dict,
    *,
    kind: Literal["board", "concept"] = "board",
) -> int:
    points = list(payload.get("points") or [])
    if not points:
        return 0
    store = ExtConfigStore(data_dir)
    cfg = _ensure_board_minute_config(store, kind)
    trade_date = str(payload.get("trade_date") or points[0].get("date") or date.today().isoformat())[:10]
    write_ext_parquet(
        pl.DataFrame(points),
        cfg,
        data_dir,
        snapshot_date=date.fromisoformat(trade_date),
    )
    return len(points)


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


def load_board_daily_history(
    data_dir: Path,
    code: str,
    *,
    kind: Literal["board", "concept"] = "board",
    limit: int = 120,
) -> list[dict]:
    config_id = "ext_fund_flow_bk_daily" if kind == "board" else "ext_fund_flow_concept_daily"
    root = Path(data_dir) / "ext_data" / config_id / "timeseries"
    if not root.exists():
        return []
    files = sorted(root.rglob("*.parquet"))
    if not files:
        return []
    dfs = []
    code_u = str(code).upper()
    for f in files:
        try:
            df = pl.read_parquet(f)
        except Exception:  # noqa: BLE001
            continue
        if "code" in df.columns:
            dfs.append(df.filter(pl.col("code").cast(pl.Utf8).str.to_uppercase() == code_u))
    if not dfs:
        return []
    out = pl.concat(dfs, how="diagonal_relaxed")
    if "date" in out.columns:
        out = out.sort("date")
    if limit > 0:
        out = out.tail(limit)
    return out.to_dicts()


def load_board_intraday(
    data_dir: Path,
    code: str,
    *,
    kind: Literal["board", "concept"] = "board",
    trade_date: str | None = None,
) -> list[dict]:
    config_id = "ext_fund_flow_bk_minute" if kind == "board" else "ext_fund_flow_concept_minute"
    root = Path(data_dir) / "ext_data" / config_id / "timeseries"
    if not root.exists():
        return []
    code_u = str(code).upper()
    files = sorted(root.rglob("*.parquet"))
    if trade_date:
        td = trade_date[:10]
        files = [f for f in files if f"date={td}" in str(f)]
    if not files:
        return []
    dfs = []
    for f in files:
        try:
            df = pl.read_parquet(f)
        except Exception:  # noqa: BLE001
            continue
        if "code" in df.columns:
            dfs.append(df.filter(pl.col("code").cast(pl.Utf8).str.to_uppercase() == code_u))
    if not dfs:
        return []
    out = pl.concat(dfs, how="diagonal_relaxed")
    sort_cols = [c for c in ("timestamp", "time", "date") if c in out.columns]
    if sort_cols:
        out = out.sort(sort_cols)
    return out.to_dicts()


def refresh_top_boards_daily_history(
    data_dir: Path,
    *,
    kind: Literal["board", "concept"] = "board",
    top_n: int = 20,
    limit: int = 60,
    client: ResilientHttpClient | None = None,
) -> dict:
    """Refresh ranking snapshot + daily history for selected boards.

    Industry window ranking needs the current snapshot universe, not just today's
    inflow/outflow TOP20. Concept callers can keep the older TOP-N path.
    """
    client = client or get_shared_client()
    ranking = fetch_board_ranking("board" if kind == "board" else "concept", client=client)
    if kind == "board":
        persist_board_snapshot(data_dir, ranking)
    else:
        persist_concept_snapshot(data_dir, ranking)

    selected: list[dict] = []
    seen: set[str] = set()
    if kind == "board" and int(top_n) >= 100:
        source_rows = ranking
    else:
        inflow = [r for r in ranking if (r.get("main_net") or 0) > 0][: max(1, top_n)]
        outflow = sorted(
            [r for r in ranking if (r.get("main_net") or 0) < 0],
            key=lambda r: r.get("main_net") or 0,
        )[: max(1, top_n)]
        source_rows = inflow + outflow
    for r in source_rows:
        c = str(r.get("code") or "").upper()
        if not c or c in seen:
            continue
        seen.add(c)
        selected.append(r)

    ok_codes: list[str] = []
    failed: list[dict] = []
    total_points = 0
    sources: set[str] = set()
    env_pref = (os.environ.get("FUND_FLOW_HISTORY_PREFER_LOCAL") or "").strip().lower()
    if env_pref in {"1", "true", "yes"}:
        force_local = True
    elif env_pref in {"0", "false", "no"}:
        force_local = False
    else:
        # auto-enable local batch mode when go-stock db is present
        force_local = any(p.exists() for p in _go_stock_db_candidates())
    if kind in {"board", "concept"}:
        # Window ranks stay on Eastmoney daily bars only.
        force_local = False
    for item in selected:
        code = str(item.get("code") or "").upper()
        try:
            if kind in {"board", "concept"}:
                hist = fetch_board_daily_history(
                    code,
                    client=client,
                    limit=limit,
                    kind=kind,
                    allow_local_fallback=False,
                    prefer_h5=True,
                )
            elif force_local:
                hist = _fetch_board_daily_history_from_go_stock(code, kind=kind, limit=limit)
                if not hist:
                    # still try remote once if local empty for this code
                    hist = fetch_board_daily_history(code, client=client, limit=limit, kind=kind)
            else:
                hist = fetch_board_daily_history(code, client=client, limit=limit, kind=kind)
            # keep name from ranking if history name blank
            for row in hist:
                if not row.get("name"):
                    row["name"] = item.get("name")
                if row.get("source"):
                    sources.add(str(row.get("source")))
            if not hist:
                failed.append({"code": code, "error": "empty history"})
                continue
            if kind in {"board", "concept"}:
                hist = [row for row in hist if str(row.get("source")) == "eastmoney_fflow_day"]
                if not hist:
                    failed.append({"code": code, "error": "refused non-eastmoney daily"})
                    continue
            n = persist_board_daily_history(data_dir, code, hist, kind=kind)
            total_points += n
            ok_codes.append(code)
        except Exception as e:  # noqa: BLE001
            err = str(e)
            failed.append({"code": code, "error": err})
            if kind not in {"board", "concept"} and any(x in err for x in ("SSL", "EOF", "timeout", "Timeout", "cooldown")):
                force_local = True

    source = "+".join(sorted(sources)) if sources else "eastmoney_daykline|go_stock_local"
    return {
        "ok": len(failed) == 0 or total_points > 0,
        "kind": kind,
        "ranking_count": len(ranking),
        "selected": len(selected),
        "history_codes": ok_codes,
        "history_points": total_points,
        "failed": failed,
        "source": source,
        "note": (
            "东财 daykline 不可用时自动回退 go-stock 本地板块/概念资金快照（按日聚合）"
            if "go_stock_local_snapshot" in sources
            else ""
        ),
    }


def _window_rank_items(items: list[dict], top: int) -> list[dict]:
    """Keep both ranking heads for the two-column panel.

    ``top`` is the column length, not a high-side-only slice. A quarter window
    may have fewer than ``top`` positive sums; the inflow column still needs
    the next-highest cumulative names.
    """
    if not items:
        return []
    if not top or int(top) <= 0:
        return items
    n = max(1, int(top))

    def _net(row: dict) -> float:
        value = row.get("main_net")
        return float(value) if isinstance(value, (int, float)) else 0.0

    ranked = [row for row in items if str(row.get("code") or "").strip()]
    high = sorted(ranked, key=_net, reverse=True)[:n]
    high_codes = {str(row.get("code") or "").upper() for row in high}
    low = [row for row in sorted(ranked, key=_net) if str(row.get("code") or "").upper() not in high_codes][:n]
    seen: set[str] = set()
    out: list[dict] = []
    for row in high + low:
        code = str(row.get("code") or "").upper()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(row)
    return out


def aggregate_board_window(
    data_dir: Path,
    *,
    kind: Literal["board", "concept"] = "board",
    days: int = 63,
    top: int = 8,
    as_of_today: date | None = None,
) -> dict[str, Any]:
    """Rank boards by summed main_net over the latest ``days`` trading dates.

    Missing daily history is returned as coverage, never silently treated as 0.
    """
    snapshot_id = "ext_fund_flow_bk" if kind == "board" else "ext_fund_flow_concept"
    daily_id = "ext_fund_flow_bk_daily" if kind == "board" else "ext_fund_flow_concept_daily"
    snap_path = Path(data_dir) / "ext_data" / snapshot_id / "part.parquet"
    daily_root = Path(data_dir) / "ext_data" / daily_id / "timeseries"
    snapshot_rows = 0
    snapshot_items: list[dict] = []
    if snap_path.exists():
        snap = pl.read_parquet(snap_path)
        snapshot_rows = snap.height
        snapshot_items = snap.to_dicts()
    files = sorted(daily_root.rglob("*.parquet")) if daily_root.exists() else []
    daily = pl.DataFrame()
    if files:
        frames = []
        for path in files:
            try:
                frames.append(pl.read_parquet(path))
            except Exception:
                continue
        if frames:
            daily = pl.concat(frames, how="diagonal_relaxed")
    if daily.is_empty() or "date" not in daily.columns or "code" not in daily.columns:
        missing = [
            {
                "code": str(row.get("code") or "").upper(),
                "name": row.get("name"),
                "days": 0,
            }
            for row in snapshot_items
            if str(row.get("code") or "").strip()
        ]
        empty = {
            "ok": True,
            "kind": kind,
            "window_days": int(days),
            "requested_days": int(days),
            "window_complete": False,
            "window_label": f"近{int(days)}个交易日累计",
            "trading_days": 0,
            "start": None,
            "end": None,
            "prior_start": None,
            "prior_end": None,
            "snapshot_count": snapshot_rows,
            "covered_count": 0,
            "full_count": 0,
            "missing_count": len(missing),
            "coverage_pct": 0.0,
            "items": [],
            "missing": missing,
            "short": missing,
            "prior_available": False,
            "prior_note": "窗口外数据不足",
            "window_note": "窗口数据不足",
            "source": daily_id,
        }
        return _attach_industry_freshness(empty, data_dir, as_of_today=as_of_today)
    daily = daily.with_columns(
        pl.col("code").cast(pl.Utf8).str.to_uppercase().alias("code"),
        pl.col("date").cast(pl.Utf8).str.slice(0, 10).alias("date"),
    )
    dates = sorted({str(v) for v in daily["date"].to_list() if v})
    ranked = daily
    if "source" in daily.columns:
        em_dates = sorted({
            str(v) for v in daily.filter(pl.col("source") == "eastmoney_fflow_day")["date"].to_list() if v
        })
        if em_dates:
            # Latest completed Eastmoney bar is the window end. Count only H5
            # trading days so go-stock weekend leftovers cannot steal a slot.
            dates = em_dates
            ranked = daily.filter(pl.col("source") == "eastmoney_fflow_day")
    window_dates = dates[-max(1, int(days)):]
    window = ranked.filter(pl.col("date").is_in(window_dates))
    names = {}
    if "name" in daily.columns:
        for row in daily.select(["code", "name"]).unique(subset=["code"], keep="last").to_dicts():
            names[str(row.get("code") or "").upper()] = row.get("name")
    for row in snapshot_items:
        code = str(row.get("code") or "").upper()
        if code and code not in names:
            names[code] = row.get("name")
    grouped = (
        window.group_by("code")
        .agg(
            pl.col("main_net").sum().alias("main_net"),
            pl.col("date").n_unique().alias("days"),
            pl.col("date").max().alias("as_of"),
        )
        .sort("main_net", descending=True, nulls_last=True)
    )
    items = []
    covered_codes = set()
    for row in grouped.to_dicts():
        code = str(row.get("code") or "").upper()
        if not code:
            continue
        covered_codes.add(code)
        items.append(
            {
                "code": code,
                "name": names.get(code) or code,
                "main_net": row.get("main_net"),
                "days": int(row.get("days") or 0),
                "window_days": len(window_dates),
                "coverage_pct": round(100.0 * int(row.get("days") or 0) / max(1, len(window_dates)), 1),
                "as_of": row.get("as_of"),
                "kind": kind,
                "source": daily_id,
                "unit_amount": "yuan",
            }
        )
    missing = []
    snapshot_codes: list[str] = []
    for row in snapshot_items:
        code = str(row.get("code") or "").upper()
        if not code:
            continue
        snapshot_codes.append(code)
        if code not in covered_codes:
            missing.append({"code": code, "name": row.get("name"), "days": 0})
    days_by_code = {str(item.get("code") or "").upper(): int(item.get("days") or 0) for item in items}
    short = []
    seen_short: set[str] = set()
    for row in snapshot_items:
        code = str(row.get("code") or "").upper()
        if not code:
            continue
        have = days_by_code.get(code, 0)
        if have < int(days) and code not in seen_short:
            seen_short.add(code)
            short.append({"code": code, "name": names.get(code) or row.get("name"), "days": have})
    if not snapshot_codes:
        for item in items:
            code = str(item.get("code") or "").upper()
            have = int(item.get("days") or 0)
            if code and have < int(days) and code not in seen_short:
                seen_short.add(code)
                short.append({"code": code, "name": item.get("name"), "days": have})
    full_count = sum(1 for code in snapshot_codes if days_by_code.get(code, 0) >= int(days))
    if snapshot_codes:
        if kind == "concept":
            # New or sparse themes cannot fill a longer window. Rank only full
            # codes; open the window when they cover at least 90% of the snapshot.
            items = [item for item in items if int(item.get("days") or 0) >= int(days)]
            window_complete = (
                len(window_dates) >= int(days)
                and full_count >= max(20, int(0.9 * len(snapshot_codes)))
                and full_count == len(items)
            )
        else:
            window_complete = len(window_dates) >= int(days) and full_count == len(snapshot_codes)
    else:
        window_complete = bool(items) and len(window_dates) >= int(days) and all(
            int(item.get("days") or 0) >= int(days) for item in items
        )
    prior_dates = dates[: max(0, len(dates) - len(window_dates))]
    prior_available = len(prior_dates) >= max(5, int(days) // 2) and grouped.height >= max(20, snapshot_rows // 2)
    payload = {
        "ok": True,
        "kind": kind,
        "window_days": len(window_dates),
        "requested_days": int(days),
        "window_complete": window_complete,
        "window_label": f"近{len(window_dates)}个交易日累计",
        "trading_days": len(window_dates),
        "start": window_dates[0] if window_dates else None,
        "end": window_dates[-1] if window_dates else None,
        "prior_start": prior_dates[0] if prior_dates else None,
        "prior_end": prior_dates[-1] if prior_dates else None,
        "snapshot_count": snapshot_rows,
        "covered_count": len(covered_codes),
        "full_count": full_count,
        "missing_count": len(missing),
        "coverage_pct": round(100.0 * len(covered_codes) / max(1, snapshot_rows), 1),
        "items": _window_rank_items(items, top),
        "missing": missing,
        "short": short,
        "prior_available": prior_available,
        "prior_note": None if prior_available else "窗口外数据不足",
        "window_note": None if window_complete else "窗口数据不足",
        "source": daily_id,
    }
    return _attach_industry_freshness(payload, data_dir, as_of_today=as_of_today)

