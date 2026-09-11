"""同花顺官方特色数据的本地查询与显式同步 API。"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import polars as pl
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services.free_sources.hithink_finance import (
    AUCTION_UNIT,
    DRAGON_TIGER_UNIT,
    LIMIT_POOL_UNIT,
    PRODUCER,
    VALUATION_UNIT,
    HiThinkFinanceError,
    HiThinkQualityError,
    query_auction_snapshot,
    query_dragon_tiger,
    query_limit_pool,
    query_valuation_snapshot,
    shanghai_today,
    sync_hithink_special_data,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hithink", tags=["hithink"])
SHANGHAI = ZoneInfo("Asia/Shanghai")
DATASET_IDS = (
    "hithink_limit_pool",
    "hithink_dragon_tiger",
    "hithink_auction_snapshot",
    "hithink_valuation_snapshot",
)
IncludeTarget = Literal["limit_pool", "dragon_tiger", "auction", "valuation"]


class HiThinkSyncRequest(BaseModel):
    trade_date: date | None = None
    include: list[IncludeTarget] | None = None
    symbols: list[str] | None = None


def _data_dir(request: Request):
    return request.app.state.repo.store.data_dir


def _json_rows(frame: pl.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in frame.to_dicts():
        for key, value in list(row.items()):
            if isinstance(value, datetime):
                row[key] = value.isoformat(timespec="seconds")
            elif isinstance(value, date):
                row[key] = value.isoformat()
        rows.append(row)
    return rows


def _local_payload(
    *,
    dataset_id: str,
    unit_version: str,
    requested_date: date | None,
    resolved_date: date | None,
    frame: pl.DataFrame,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "available": not frame.is_empty(),
        "dataset_id": dataset_id,
        "requested_date": requested_date.isoformat() if requested_date else None,
        "resolved_date": resolved_date.isoformat() if resolved_date else None,
        "rows": _json_rows(frame),
        "row_count": frame.height,
        "source": "local",
        "producer": PRODUCER,
        "unit_version": unit_version,
    }
    if extra:
        payload.update(extra)
    return payload


def _bounded_http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _map_sync_error(error: Exception) -> HTTPException:
    if isinstance(error, HiThinkQualityError):
        text = str(error)
        if "missing HITHINK" in text or "requires at least one symbol" in text or "unsupported" in text or "future" in text:
            return _bounded_http_error(400, "hithink_invalid_request", "同花顺官方特色数据请求无效")
        return _bounded_http_error(502, "hithink_upstream_invalid", "同花顺官方特色数据返回了不完整或无法解释的数据")
    if isinstance(error, HiThinkFinanceError):
        if error.code in {401, 403} or "authentication" in str(error):
            return _bounded_http_error(502, "hithink_auth_failed", "同花顺官方特色数据认证失败")
        if "missing HITHINK_FINANCE_API_KEY" in str(error):
            return _bounded_http_error(400, "hithink_key_missing", "未配置同花顺官方 API Key")
        return _bounded_http_error(502, "hithink_upstream_failed", "同花顺官方特色数据暂时不可用")
    return _bounded_http_error(502, "hithink_upstream_failed", "同花顺官方特色数据暂时不可用")


@router.get("/limit-pool")
def get_limit_pool(
    request: Request,
    trade_date: date | None = None,
    pool_kind: str | None = None,
    symbol: str | None = None,
    limit: int = 500,
) -> dict:
    """只读查询本地官方涨跌停池; 不会在查询时访问外部端点。"""
    try:
        resolved, frame = query_limit_pool(
            _data_dir(request),
            trade_date=trade_date,
            pool_kind=pool_kind,
            symbol=symbol,
            limit=limit,
        )
    except HiThinkQualityError:
        logger.exception("local hithink limit pool quality validation failed")
        raise _bounded_http_error(500, "hithink_local_invalid", "本地官方涨跌停池未通过质量校验") from None
    return _local_payload(
        dataset_id="hithink_limit_pool",
        unit_version=LIMIT_POOL_UNIT,
        requested_date=trade_date,
        resolved_date=resolved,
        frame=frame,
    )


@router.get("/dragon-tiger")
def get_dragon_tiger(
    request: Request,
    trade_date: date | None = None,
    symbol: str | None = None,
    limit: int = 500,
) -> dict:
    """只读查询本地官方龙虎榜; 不会在查询时访问外部端点。"""
    try:
        resolved, frame = query_dragon_tiger(
            _data_dir(request),
            trade_date=trade_date,
            symbol=symbol,
            limit=limit,
        )
    except HiThinkQualityError:
        logger.exception("local hithink dragon tiger quality validation failed")
        raise _bounded_http_error(500, "hithink_local_invalid", "本地官方龙虎榜未通过质量校验") from None
    return _local_payload(
        dataset_id="hithink_dragon_tiger",
        unit_version=DRAGON_TIGER_UNIT,
        requested_date=trade_date,
        resolved_date=resolved,
        frame=frame,
    )


@router.get("/auction-snapshot")
def get_auction_snapshot(
    request: Request,
    trade_date: date | None = None,
    symbol: str | None = None,
    limit: int = 500,
) -> dict:
    """只读查询本地官方集合竞价快照; 不会在查询时访问外部端点。"""
    try:
        resolved, frame = query_auction_snapshot(
            _data_dir(request),
            trade_date=trade_date,
            symbol=symbol,
            limit=limit,
        )
    except HiThinkQualityError:
        logger.exception("local hithink auction snapshot quality validation failed")
        raise _bounded_http_error(500, "hithink_local_invalid", "本地官方集合竞价快照未通过质量校验") from None
    return _local_payload(
        dataset_id="hithink_auction_snapshot",
        unit_version=AUCTION_UNIT,
        requested_date=trade_date,
        resolved_date=resolved,
        frame=frame,
        extra={"volume_unit": "lot", "amount_unit": "CNY"},
    )


@router.get("/valuation-snapshot")
def get_valuation_snapshot(
    request: Request,
    as_of: date | None = None,
    symbol: str | None = None,
    limit: int = 500,
) -> dict:
    """只读查询本地官方最新估值快照; 不会在查询时访问外部端点。"""
    try:
        resolved, frame = query_valuation_snapshot(
            _data_dir(request),
            as_of=as_of,
            symbol=symbol,
            limit=limit,
        )
    except HiThinkQualityError:
        logger.exception("local hithink valuation snapshot quality validation failed")
        raise _bounded_http_error(500, "hithink_local_invalid", "本地官方最新估值快照未通过质量校验") from None
    return _local_payload(
        dataset_id="hithink_valuation_snapshot",
        unit_version=VALUATION_UNIT,
        requested_date=as_of,
        resolved_date=resolved,
        frame=frame,
        extra={"history_guarantee": "latest_snapshot_only"},
    )


@router.post("/sync")
def sync_hithink_endpoint(request: Request, body: HiThinkSyncRequest) -> dict:
    """显式采集同花顺官方特色数据, 成功发布后刷新本地目录。"""
    requested_date = body.trade_date or shanghai_today()
    if requested_date > datetime.now(SHANGHAI).date():
        raise _bounded_http_error(400, "hithink_invalid_request", "不能同步未来日期的同花顺官方特色数据")
    include = tuple(body.include) if body.include else ("limit_pool", "dragon_tiger", "auction", "valuation")
    try:
        result = sync_hithink_special_data(
            requested_date,
            _data_dir(request),
            include=include,
            symbols=body.symbols,
        )
    except (HiThinkQualityError, HiThinkFinanceError, RuntimeError) as error:
        logger.exception("hithink official special-data sync failed")
        raise _map_sync_error(error) from None

    catalog_refreshed: list[str] = []
    catalog = getattr(request.app.state, "catalog_service", None)
    if catalog is not None:
        for dataset_id in DATASET_IDS:
            if dataset_id not in {item.dataset_id for item in result.datasets}:
                continue
            try:
                catalog.refresh_after_mutation(dataset_id)
                catalog_refreshed.append(dataset_id)
            except Exception:
                logger.exception("catalog refresh failed after hithink publish for %s", dataset_id)
    payload = result.as_dict()
    payload["catalog_refreshed"] = catalog_refreshed
    payload["source"] = "hithink_fuyao"
    return payload
