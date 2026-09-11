"""Public index constituent pools (no TickFlow quote.pool).

Primary: CSI (中证) official constituent XLS
  https://oss-ch.csindex.com.cn/.../cons/{code}cons.xls

Fallback: Sina Market_Center nodes
  - CSI300: node=hs300 (paginated)
  - CSI500/SSE50: node=zhishu_{code} via getHQNodeDataSimple

Writes: data/pools/{CSI300|CSI500|SSE50}.parquet
Columns aligned with tickflow.pools cache: symbol, as_of [, name, weight, source]
"""
from __future__ import annotations

import io
import logging
import math
import time
from collections.abc import Callable, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.services.free_sources.http_resilience import ResilientHttpClient, get_shared_client
from app.services.atomic_io import atomic_write_parquet

logger = logging.getLogger(__name__)

# one-trading PoolId ↔ index codes
POOL_SPECS: dict[str, dict[str, str]] = {
    "CSI300": {"index_code": "000300", "name": "沪深300", "sina_node": "hs300"},
    "CSI500": {"index_code": "000905", "name": "中证500", "sina_node": "zhishu_000905"},
    "CSI800": {"index_code": "000906", "name": "中证800", "sina_node": "zhishu_000906"},
    "CSI1000": {"index_code": "000852", "name": "中证1000", "sina_node": "zhishu_000852"},
    "SSE50": {"index_code": "000016", "name": "上证50", "sina_node": "zhishu_000016"},
}

CSINDEX_CONS_URL = (
    "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/"
    "file/autofile/cons/{code}cons.xls"
)
CSINDEX_WEIGHT_URL = (
    "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/"
    "file/autofile/closeweight/{code}closeweight.xls"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}


def _exchange_to_suffix(ex: str | None, code: str) -> str:
    text = (ex or "").lower()
    if "shen" in text or "深圳" in (ex or "") or "szse" in text:
        return "SZ"
    if "shang" in text or "上海" in (ex or "") or "sse" in text:
        return "SH"
    if "bei" in text or "北京" in (ex or "") or "bse" in text:
        return "BJ"
    # code heuristic
    c = (code or "").zfill(6)
    if c.startswith(("5", "6", "9")):
        return "SH"
    if c.startswith(("4", "8")):
        return "BJ"
    return "SZ"


def _to_symbol(code: str, exchange: str | None = None) -> str | None:
    c = str(code or "").strip()
    if not c:
        return None
    # already prefixed sh/sz
    low = c.lower()
    if low.startswith("sh") and low[2:].isdigit():
        return f"{low[2:].zfill(6)}.SH"
    if low.startswith("sz") and low[2:].isdigit():
        return f"{low[2:].zfill(6)}.SZ"
    if low.startswith("bj") and low[2:].isdigit():
        return f"{low[2:].zfill(6)}.BJ"
    digits = "".join(ch for ch in c if ch.isdigit())
    if len(digits) < 6:
        digits = digits.zfill(6)
    if len(digits) != 6:
        return None
    suf = _exchange_to_suffix(exchange, digits)
    return f"{digits}.{suf}"


def _http_get_bytes(url: str, *, client: ResilientHttpClient, source_key: str, timeout: float = 30.0) -> bytes:
    import httpx

    if client.cooldown.is_cooling(source_key):
        raise RuntimeError(f"cooldown {client.cooldown.remaining(source_key):.1f}s")
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=timeout, follow_redirects=True)
        if resp.status_code >= 400:
            client.cooldown.trip(source_key, 20.0)
            raise RuntimeError(f"HTTP {resp.status_code}")
        return resp.content
    except Exception as exc:
        client.cooldown.trip(source_key, 20.0)
        raise RuntimeError(str(exc)) from exc


def fetch_csindex_constituents(
    index_code: str,
    *,
    client: ResilientHttpClient | None = None,
    with_weight: bool = False,
) -> pl.DataFrame:
    """Fetch CSI official constituent list for one index code (e.g. 000300)."""
    client = client or get_shared_client()
    code = str(index_code).zfill(6)
    raw = _http_get_bytes(
        CSINDEX_CONS_URL.format(code=code),
        client=client,
        source_key="csindex_cons",
        timeout=35.0,
    )
    if len(raw) < 100:
        raise RuntimeError(f"csindex cons empty for {code}")

    df = pl.read_excel(io.BytesIO(raw))
    # Flexible column match (Chinese / bilingual headers)
    def pick(*cands: str) -> str | None:
        for cand in cands:
            for c in df.columns:
                if cand.lower() in str(c).lower().replace(" ", ""):
                    return c
                if cand in str(c):
                    return c
        return None

    col_code = pick("成份券代码", "ConstituentCode", "成分券代码")
    col_name = pick("成份券名称", "ConstituentName", "成分券名称")
    col_ex = pick("交易所Exchange", "交易所", "Exchange")
    col_date = pick("日期Date", "日期", "Date")
    if not col_code:
        # fallback positional: known layout
        if df.width >= 5:
            col_code = df.columns[4]
            col_name = df.columns[5] if df.width > 5 else None
            col_ex = df.columns[7] if df.width > 7 else None
            col_date = df.columns[0]
        else:
            raise RuntimeError(f"unexpected csindex columns: {df.columns}")

    as_of = date.today()
    if col_date:
        try:
            sample = str(df[col_date][0])
            if len(sample) >= 8 and sample[:8].isdigit():
                as_of = date(int(sample[0:4]), int(sample[4:6]), int(sample[6:8]))
        except Exception:
            pass

    rows: list[dict[str, Any]] = []
    for rec in df.to_dicts():
        code_raw = rec.get(col_code)
        ex_raw = rec.get(col_ex) if col_ex else None
        sym = _to_symbol(code_raw, str(ex_raw) if ex_raw is not None else None)
        if not sym:
            continue
        rows.append(
            {
                "symbol": sym,
                "name": str(rec.get(col_name) or "") if col_name else None,
                "as_of": as_of,
                "index_code": code,
                "source": "csindex",
            }
        )

    out = pl.DataFrame(rows) if rows else pl.DataFrame()
    if out.is_empty():
        return out

    if with_weight:
        try:
            wraw = _http_get_bytes(
                CSINDEX_WEIGHT_URL.format(code=code),
                client=client,
                source_key="csindex_weight",
                timeout=35.0,
            )
            wdf = pl.read_excel(io.BytesIO(wraw))
            w_code = None
            w_weight = None
            for c in wdf.columns:
                cs = str(c)
                if "成份券代码" in cs or "Constituent Code" in cs or "成分券代码" in cs:
                    w_code = c
                if "权重" in cs or "Weight" in cs.lower():
                    w_weight = c
            if w_code and w_weight:
                wr: list[dict[str, Any]] = []
                for rec in wdf.to_dicts():
                    # weight file may not include exchange; use code heuristic
                    sym = _to_symbol(rec.get(w_code), None)
                    if not sym:
                        continue
                    try:
                        w = float(rec.get(w_weight))
                    except (TypeError, ValueError):
                        w = None
                    wr.append({"symbol": sym, "weight": w})
                if wr:
                    out = out.join(pl.DataFrame(wr), on="symbol", how="left")
        except Exception as e:
            logger.debug("csindex weight skipped for %s: %s", code, e)

    return out.unique(subset=["symbol"], keep="first").sort("symbol")


def fetch_sina_constituents(
    pool_id: str,
    *,
    client: ResilientHttpClient | None = None,
) -> pl.DataFrame:
    """Sina fallback for index constituents."""
    if pool_id not in POOL_SPECS:
        raise ValueError(pool_id)
    client = client or get_shared_client()
    spec = POOL_SPECS[pool_id]
    node = spec["sina_node"]

    import httpx

    headers = {
        **_HEADERS,
        "Referer": "https://vip.stock.finance.sina.com.cn/",
    }
    rows: list[dict[str, Any]] = []

    if node == "hs300":
        # count + paginate 80
        count_url = (
            "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "Market_Center.getHQNodeStockCountSimple"
        )
        r = httpx.get(count_url, params={"node": "hs300"}, headers=headers, timeout=15.0)
        r.raise_for_status()
        try:
            total = int(str(r.text).strip().strip('"'))
        except ValueError:
            total = 300
        pages = max(1, math.ceil(total / 80))
        url = (
            "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "Market_Center.getHQNodeData"
        )
        for page in range(1, pages + 1):
            rr = httpx.get(
                url,
                params={
                    "page": str(page),
                    "num": "80",
                    "sort": "symbol",
                    "asc": "1",
                    "node": "hs300",
                    "symbol": "",
                    "_s_r_a": "init",
                },
                headers=headers,
                timeout=15.0,
            )
            rr.raise_for_status()
            data = rr.json()
            if not isinstance(data, list):
                break
            for item in data:
                sym = _to_symbol(item.get("symbol") or item.get("code"))
                if not sym:
                    continue
                rows.append(
                    {
                        "symbol": sym,
                        "name": item.get("name"),
                        "as_of": date.today(),
                        "index_code": spec["index_code"],
                        "source": "sina",
                    }
                )
    else:
        url = (
            "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "Market_Center.getHQNodeDataSimple"
        )
        rr = httpx.get(
            url,
            params={
                "page": "1",
                "num": "3000",
                "sort": "symbol",
                "asc": "1",
                "node": node,
                "_s_r_a": "setlen",
            },
            headers=headers,
            timeout=20.0,
        )
        rr.raise_for_status()
        data = rr.json()
        if isinstance(data, list):
            for item in data:
                sym = _to_symbol(item.get("symbol") or item.get("code"))
                if not sym:
                    continue
                rows.append(
                    {
                        "symbol": sym,
                        "name": item.get("name"),
                        "as_of": date.today(),
                        "index_code": spec["index_code"],
                        "source": "sina",
                    }
                )

    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).unique(subset=["symbol"], keep="first").sort("symbol")


def fetch_pool_constituents(
    pool_id: str,
    *,
    client: ResilientHttpClient | None = None,
    prefer: str = "csindex",
) -> pl.DataFrame:
    """Fetch one pool; try csindex then sina."""
    if pool_id not in POOL_SPECS:
        raise ValueError(f"unsupported pool_id: {pool_id}")
    client = client or get_shared_client()
    spec = POOL_SPECS[pool_id]
    errors: list[str] = []

    order = ["csindex", "sina"] if prefer == "csindex" else ["sina", "csindex"]
    for src in order:
        try:
            if src == "csindex":
                df = fetch_csindex_constituents(spec["index_code"], client=client, with_weight=False)
            else:
                df = fetch_sina_constituents(pool_id, client=client)
            if df is not None and not df.is_empty():
                return df.with_columns(pl.lit(pool_id).alias("pool_id"))
            errors.append(f"{src}:empty")
        except Exception as e:
            errors.append(f"{src}:{e}")
            logger.warning("pool %s via %s failed: %s", pool_id, src, e)
    raise RuntimeError(f"fetch pool {pool_id} failed: {'; '.join(errors)}")


def write_pool_parquet(df: pl.DataFrame, data_dir: Path, pool_id: str) -> Path:
    """Write cache compatible with tickflow.pools.get_pool (symbol + as_of)."""
    if df is None or df.is_empty():
        raise ValueError("empty pool frame")
    if "symbol" not in df.columns:
        raise ValueError("pool frame requires symbol")
    out_dir = Path(data_dir) / "pools"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{pool_id}.parquet"

    as_of = date.today()
    if "as_of" in df.columns:
        try:
            v = df["as_of"][0]
            if isinstance(v, datetime):
                as_of = v.date()
            elif isinstance(v, date):
                as_of = v
        except Exception:
            pass

    # Keep extended cols but ensure required ones exist
    base = df.with_columns(
        pl.col("symbol").cast(pl.Utf8),
        pl.lit(as_of).alias("as_of"),
    ).unique(subset=["symbol"], keep="first").sort("symbol")
    atomic_write_parquet(base, out)
    logger.info("pool %s wrote %d symbols -> %s", pool_id, base.height, out)
    return out


def sync_pools_public(
    data_dir: Path,
    *,
    pool_ids: Sequence[str] | None = None,
    client: ResilientHttpClient | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Sync CSI300/CSI500/SSE50 constituent caches."""
    client = client or get_shared_client()
    ids = list(pool_ids) if pool_ids else list(POOL_SPECS.keys())
    ids = [p for p in ids if p in POOL_SPECS]
    t0 = time.perf_counter()
    results: dict[str, Any] = {}
    ok = []
    fail = []
    total = len(ids)
    for i, pid in enumerate(ids, 1):
        try:
            df = fetch_pool_constituents(pid, client=client)
            path = write_pool_parquet(df, data_dir, pid)
            results[pid] = {
                "ok": True,
                "count": int(df.height),
                "source": df["source"][0] if "source" in df.columns and df.height else None,
                "path": str(path),
                "as_of": str(df["as_of"][0]) if "as_of" in df.columns and df.height else None,
            }
            ok.append(pid)
        except Exception as e:
            logger.warning("sync pool %s failed: %s", pid, e)
            results[pid] = {"ok": False, "error": str(e)}
            fail.append(pid)
        if on_progress:
            on_progress(i, total, pid)
    return {
        "ok": len(fail) == 0,
        "source": "csindex/sina",
        "pools": results,
        "ok_pools": ok,
        "fail_pools": fail,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "path": str(Path(data_dir) / "pools"),
    }


def load_pool_symbols(data_dir: Path, pool_id: str) -> list[str]:
    path = Path(data_dir) / "pools" / f"{pool_id}.parquet"
    if not path.exists():
        return []
    df = pl.read_parquet(path)
    if df.is_empty() or "symbol" not in df.columns:
        return []
    return df["symbol"].to_list()
