"""东方财富 F10 股本结构历史 -> 严格 PIT 股本行。

真实生产者: 东方财富 `datacenter.eastmoney.com` 的 `RPT_F10_EH_EQUITY` 报表
(HSF10 股本结构, 按 SECUCODE 逐股查询)。每行是一次股本变动:
`END_DATE`=变动日(作 effective_date), `NOTICE_DATE`=真实公告日(作 announce_date),
`TOTAL_SHARES`=总股本(股), `LISTED_A_SHARES`=流通 A 股(股)。

带真实公告日的行经 `financial_pit.ensure_pit_columns` 判定为 PIT 安全
(source 不含 snapshot/instruments/fetch), 从而让 valuation_daily 的市值可派生;
无公告日的行保留但标记 pit_unsafe, 不会进入严格 as_of 查询。

显式入口: scripts/sync-share-capital.py; 不加入自动调度。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl

from app.services.financial_pit import (
    merge_financial_pit,
    staging_atomic_replace_financial_table,
)
from app.services.free_sources.http_resilience import (
    ResilientHttpClient,
    get_shared_client,
)

logger = logging.getLogger(__name__)

SHARE_CAPITAL_SOURCE = "eastmoney_f10_equity"

_ENDPOINT = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
_HEADERS = {
    "Referer": "https://emweb.securities.eastmoney.com/",
    "User-Agent": "Mozilla/5.0",
}


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def fetch_share_capital_history(
    symbol: str,
    *,
    client: ResilientHttpClient | None = None,
    page_size: int = 200,
) -> list[dict[str, Any]]:
    """按 SECUCODE 全页拉取一只股票的股本变动历史原始行。"""
    client = client or get_shared_client()
    secucode = symbol.upper()
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        url = (
            f"{_ENDPOINT}?reportName=RPT_F10_EH_EQUITY&columns=ALL"
            f"&filter=(SECUCODE%3D%22{secucode}%22)"
            f"&pageNumber={page}&pageSize={page_size}&source=HSF10&client=PC"
        )
        res = client.get_json(
            url,
            source_key="eastmoney_f10_equity",
            headers=_HEADERS,
            timeout=15.0,
        )
        if not res.ok:
            raise RuntimeError(res.error or f"share capital fetch failed: {secucode}")
        payload = res.data if isinstance(res.data, dict) else {}
        result = payload.get("result") or {}
        data = result.get("data") or []
        if not isinstance(data, list):
            raise RuntimeError(f"share capital payload malformed: {secucode}")
        rows.extend(item for item in data if isinstance(item, dict))
        pages = int(result.get("pages") or 1)
        if page >= pages:
            break
        page += 1
    return rows


def normalize_share_capital(symbol: str, rows: Sequence[dict[str, Any]]) -> pl.DataFrame:
    """原始行 -> canonical 股本历史行(单位: 股)。

    保留无公告日的行(将被 PIT 规则标记 pit_unsafe), 丢弃无变动日或无总股本的行。
    """
    sym = symbol.upper()
    out: list[dict[str, Any]] = []
    for row in rows or []:
        effective = _as_date(row.get("END_DATE"))
        total = row.get("TOTAL_SHARES")
        if effective is None or total is None:
            continue
        try:
            total_f = float(total)
        except (TypeError, ValueError):
            continue
        listed_a = row.get("LISTED_A_SHARES")
        try:
            float_f = float(listed_a) if listed_a is not None else None
        except (TypeError, ValueError):
            float_f = None
        out.append(
            {
                "symbol": sym,
                "period_end": effective,
                "effective_date": effective,
                "announce_date": _as_date(row.get("NOTICE_DATE")),
                "total_shares": total_f,
                "float_shares": float_f,
                "name": row.get("SECURITY_NAME_ABBR"),
                "change_reason": row.get("CHANGE_REASON"),
                "source": SHARE_CAPITAL_SOURCE,
                "table": "shares",
            }
        )
    if not out:
        return pl.DataFrame()
    return (
        pl.DataFrame(out)
        .unique(subset=["symbol", "effective_date", "announce_date"], keep="last")
        .sort(["symbol", "effective_date"])
    )


def sync_share_capital_public(
    symbols: Sequence[str],
    data_dir: Path,
    *,
    client: ResilientHttpClient | None = None,
    sleep_s: float = 0.15,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """逐股拉取股本历史并整批合并进 financials/shares(保留 restatement)。

    单股失败只记录并继续; 全部失败则不写表。写入使用 staging 原子替换,
    既有 instruments_snapshot 行保留(仍为 pit_unsafe), 新增权威行与其共存。
    """
    data_dir = Path(data_dir)
    try:
        from app.services.financial_sync import (
            _tag_financial_route,
            financial_cache_usable,
            financial_write_route,
        )

        route = financial_write_route()
    except Exception:  # noqa: BLE001
        route = "unresolved"
        _tag_financial_route = None
        financial_cache_usable = None

    stats: dict[str, Any] = {
        "requested": len([str(s).upper().strip() for s in symbols if str(s).strip()]),
        "ok": 0,
        "empty": 0,
        "failed": 0,
        "failed_symbols": [],
        "rows_fetched": 0,
    }
    if route not in {"public", "tickflow"}:
        stats["published"] = False
        stats["skipped"] = True
        stats["error"] = f"financial route {route} must not write public share capital"
        logger.info("sync_share_capital_public skipped for route=%s", route)
        return stats

    client = client or get_shared_client()
    syms = [str(s).upper().strip() for s in symbols if str(s).strip()]
    stats["requested"] = len(syms)
    frames: list[pl.DataFrame] = []
    total = len(syms)
    for index, sym in enumerate(syms, 1):
        try:
            raw = fetch_share_capital_history(sym, client=client)
            frame = normalize_share_capital(sym, raw)
        except Exception as exc:
            stats["failed"] += 1
            stats["failed_symbols"].append(sym)
            logger.warning("share capital fetch failed for %s: %s", sym, exc)
            frame = pl.DataFrame()
        if frame.is_empty():
            if sym not in stats["failed_symbols"]:
                stats["empty"] += 1
        else:
            stats["ok"] += 1
            stats["rows_fetched"] += int(frame.height)
            frames.append(frame)
        if on_progress:
            on_progress(index, total, sym)
        if sleep_s > 0 and index < total:
            time.sleep(sleep_s)

    if not frames:
        stats["published"] = False
        stats["error"] = "no_rows_fetched"
        return stats

    new_rows = pl.concat(frames, how="diagonal_relaxed")
    shares_path = data_dir / "financials" / "shares" / "part.parquet"
    existing = pl.read_parquet(shares_path) if shares_path.exists() else None
    if (
        existing is not None
        and financial_cache_usable is not None
        and not financial_cache_usable(existing, route)
    ):
        logger.info("sync_share_capital_public: drop stale shares for route=%s", route)
        existing = None
    stats["rows_before"] = int(existing.height) if existing is not None else 0
    merged = merge_financial_pit(existing, new_rows, table="shares")
    if _tag_financial_route is not None and merged is not None and not merged.is_empty():
        merged = _tag_financial_route(merged)
    info = staging_atomic_replace_financial_table(data_dir, "shares", merged)
    stats["published"] = True
    stats["rows_after"] = info["rows"]
    stats["symbols_after"] = info["symbols"]
    stats["path"] = info["path"]
    stats["lineage_path"] = info["lineage_path"]
    pit_safe = merged.filter(
        (pl.col("pit_unsafe") == False)  # noqa: E712
        & pl.col("available_at").is_not_null()
    )
    stats["pit_safe_rows_after"] = int(pit_safe.height)
    stats["pit_safe_symbols_after"] = (
        int(pit_safe.get_column("symbol").n_unique()) if pit_safe.height else 0
    )
    return stats
