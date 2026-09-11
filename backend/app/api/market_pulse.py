"""市场脉搏的本地查询与显式同步 API。"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services.free_sources.market_pulse_public import (
    BENCHMARK_NAME,
    BENCHMARK_SYMBOL,
    MarketPulseQualityError,
    query_market_pulse,
    sync_market_pulse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/market-pulse", tags=["market-pulse"])
SHANGHAI = ZoneInfo("Asia/Shanghai")


class MarketPulseSyncRequest(BaseModel):
    trade_date: date | None = None


def _data_dir(request: Request):
    return request.app.state.repo.store.data_dir


def _json_rows(frame: pl.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in frame.to_dicts():
        event_time = row.get("event_time")
        if isinstance(event_time, datetime):
            row["event_time"] = event_time.isoformat(timespec="seconds")
        trade_date = row.get("trade_date")
        if isinstance(trade_date, date):
            row["trade_date"] = trade_date.isoformat()
        rows.append(row)
    return rows


@router.get("")
def get_market_pulse(request: Request, trade_date: date | None = None) -> dict:
    """只读查询本地市场脉搏; 不会在查询时访问外部端点。"""
    try:
        resolved_date, frame, updated_at, skipped_dates = query_market_pulse(
            _data_dir(request), requested_date=trade_date
        )
    except MarketPulseQualityError:
        logger.exception("local market pulse quality validation failed")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "market_pulse_local_invalid",
                "message": "本地市场脉搏数据未通过质量校验",
            },
        ) from None

    minute_rows = frame.filter(pl.col("record_type") == "minute")
    event_rows = frame.filter(pl.col("record_type") == "sector_event")
    return {
        "available": not minute_rows.is_empty(),
        "requested_date": trade_date.isoformat() if trade_date else None,
        "resolved_date": resolved_date.isoformat() if resolved_date else None,
        "skipped_invalid_dates": [item.isoformat() for item in skipped_dates],
        "updated_at": updated_at.isoformat(timespec="seconds") if updated_at else None,
        "benchmark": {"symbol": BENCHMARK_SYMBOL, "name": BENCHMARK_NAME},
        "points": _json_rows(minute_rows),
        "events": _json_rows(event_rows),
        "minute_rows": minute_rows.height,
        "event_rows": event_rows.height,
        "source": "local",
        "producer": "cls",
        "unit_version": "market_pulse_v1",
    }


@router.post("/sync")
def sync_market_pulse_endpoint(request: Request, body: MarketPulseSyncRequest) -> dict:
    """显式采集财联社市场脉搏, 成功发布后刷新本地目录。"""
    requested_date = body.trade_date or datetime.now(SHANGHAI).date()
    if requested_date > datetime.now(SHANGHAI).date():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "market_pulse_invalid_request",
                "message": "不能同步未来日期的市场脉搏",
            },
        )
    try:
        result = sync_market_pulse(requested_date, _data_dir(request))
    except MarketPulseQualityError:
        logger.exception("market pulse sync quality validation failed")
        raise HTTPException(
            status_code=502,
            detail={
                "code": "market_pulse_upstream_invalid",
                "message": "财联社市场脉搏返回了不完整或错日数据",
            },
        ) from None
    except RuntimeError:
        logger.exception("market pulse sync failed")
        raise HTTPException(
            status_code=502,
            detail={
                "code": "market_pulse_upstream_failed",
                "message": "财联社市场脉搏暂时不可用",
            },
        ) from None

    catalog_refreshed = False
    catalog = getattr(request.app.state, "catalog_service", None)
    if catalog is not None:
        try:
            catalog.refresh_after_mutation("market_pulse")
            catalog_refreshed = True
        except Exception:
            logger.exception("catalog refresh failed after market pulse publish")
    return {**result.as_dict(), "catalog_refreshed": catalog_refreshed}
