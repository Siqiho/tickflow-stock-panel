"""指数 API。本地保留全量列表/搜索; 核心四只只约束展示层, 不撤搜索面。"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import polars as pl
from fastapi import APIRouter, HTTPException, Query, Request

from app.indicators.pipeline import compute_enriched
from app.services import index_sync, kline_sync
from app.tickflow.capabilities import Cap, CapabilitySet

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/index", tags=["index"])


def _refresh_catalog(request: Request, *dataset_ids: str) -> None:
    """Best-effort writer refresh without changing the legacy sync response."""
    service = getattr(request.app.state, "catalog_service", None)
    if service is None:
        return
    for dataset_id in dataset_ids:
        try:
            service.refresh_after_mutation(dataset_id)
        except Exception:
            logger.exception("catalog refresh failed after index sync: dataset_id=%s", dataset_id)


def _index_info(repo, symbol: str) -> dict:
    df = repo.get_index_instruments()
    if df.is_empty() or "symbol" not in df.columns:
        return {}
    hit = df.filter(pl.col("symbol") == symbol).head(1)
    if hit.is_empty():
        return {}
    return hit.to_dicts()[0]


@router.get("/list")
def list_indices(request: Request):
    """返回已缓存的 CN_Index 指数列表。"""
    repo = request.app.state.repo
    df = repo.get_index_instruments()
    if df.is_empty():
        return {"results": [], "count": 0}
    cols = [c for c in ["symbol", "name", "code", "asset_type"] if c in df.columns]
    rows = df.select(cols).sort("symbol").to_dicts()
    return {"results": rows, "count": len(rows)}


@router.get("/search")
def search_indices(
    request: Request,
    q: str = Query("", min_length=0, max_length=50, description="搜索关键词"),
    limit: int = Query(20, ge=1, le=100),
):
    """模糊搜索指数。"""
    repo = request.app.state.repo
    df = repo.get_index_instruments()
    if df.is_empty():
        return {"results": []}
    if not q.strip():
        rows = df.head(limit).to_dicts()
        return {"results": rows}

    keyword = q.strip().upper()
    masks = []
    if "code" in df.columns:
        masks.append(pl.col("code").cast(pl.Utf8).str.contains(keyword, literal=True))
    masks.append(pl.col("symbol").cast(pl.Utf8).str.to_uppercase().str.contains(keyword, literal=True))
    if "name" in df.columns:
        masks.append(pl.col("name").cast(pl.Utf8).str.contains(q.strip(), literal=True))

    mask = masks[0]
    for m in masks[1:]:
        mask = mask | m
    rows = df.filter(mask).head(limit).to_dicts()
    return {"results": rows}


@router.get("/daily")
def get_index_daily(
    request: Request,
    symbol: str = Query(..., description="指数代码, 如 000001.SH"),
    days: int = Query(120, ge=10, le=2000),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD, 优先于 days"),
    end_date: Optional[str] = Query(None, description="截止日期 YYYY-MM-DD, 默认今天"),
):
    """读取指数日 K。指数数据使用独立 kline_index_* parquet。"""
    repo = request.app.state.repo
    end = date.fromisoformat(end_date) if end_date else date.today()
    start = date.fromisoformat(start_date) if start_date else end - timedelta(days=days)
    info = _index_info(repo, symbol)

    df = repo.get_index_daily(symbol, start, end)
    if not df.is_empty():
        return {"symbol": symbol, "name": info.get("name"), "index_info": info, "rows": df.to_dicts(), "source": "index_enriched"}

    capset = request.app.state.capabilities
    if capset is None:
        capset = CapabilitySet()
    if not capset.has(Cap.KLINE_DAILY_BATCH) and not kline_sync.daily_provider_is_custom():
        return {"symbol": symbol, "name": info.get("name"), "index_info": info, "rows": [], "source": "none"}

    try:
        raw = kline_sync.fetch_routed_daily(
            [symbol],
            start_time=datetime.combine(start, datetime.min.time()),
            end_time=datetime.combine(end, datetime.max.time().replace(microsecond=0)),
            asset_type="index",
            capset=capset,
            count=days + 150,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"daily fetch failed: {e}") from e
    if raw.is_empty():
        return {"symbol": symbol, "name": info.get("name"), "index_info": info, "rows": [], "source": "none"}

    enriched = compute_enriched(raw, factors=None, instruments=None)
    rows = enriched.filter((pl.col("date") >= start) & (pl.col("date") <= end)).to_dicts()
    return {"symbol": symbol, "name": info.get("name"), "index_info": info, "rows": rows, "source": "live"}


@router.get("/minute")
def get_index_minute(
    request: Request,
    symbol: str = Query(..., description="指数代码, 如 000001.SH"),
    trade_date: date | None = Query(None, alias="date", description="交易日期, 默认今天"),
):
    """实时读取指数分钟 K。不写入股票分钟 parquet。"""
    repo = request.app.state.repo
    capset = getattr(request.app.state, "capabilities", None)
    if capset is None:
        capset = CapabilitySet()
    info = _index_info(repo, symbol)
    day = trade_date or date.today()
    df = kline_sync.fetch_minute_single(symbol, day, asset_type="index", capset=capset)
    return {
        "symbol": symbol,
        "name": info.get("name"),
        "index_info": info,
        "date": str(day),
        "rows": df.to_dicts(),
        "source": "live" if not df.is_empty() else "none",
    }


@router.post("/sync_instruments")
def sync_index_instruments(request: Request):
    """同步 CN_Index 指数标的列表。"""
    repo = request.app.state.repo
    count = index_sync.sync_index_instruments(repo)
    _refresh_catalog(request, "index_instruments", "etf_instruments")
    return {"status": "ok", "count": count}


@router.post("/sync_daily")
def sync_index_daily(
    request: Request,
    days: int = Query(365, ge=30, le=5000),
):
    """同步指数日K到独立 parquet。"""
    repo = request.app.state.repo
    capset = request.app.state.capabilities
    if capset is None:
        capset = CapabilitySet()
    if not capset.has(Cap.KLINE_DAILY_BATCH) and not kline_sync.daily_provider_is_custom():
        raise HTTPException(status_code=403, detail="需要日K批量能力或已配置的自定义日K源")
    end = datetime.now()
    start = end - timedelta(days=days)
    count = index_sync.sync_index_instruments(repo)
    rows = index_sync.sync_and_persist_index_daily(repo, capset, start_date=start, end_date=end)
    _refresh_catalog(
        request,
        "index_instruments",
        "etf_instruments",
        "index_daily",
        "index_enriched",
    )
    return {"status": "ok", "index_count": count, "rows_written": rows}
