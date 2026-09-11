"""Local-only GET surfaces for newly published reference datasets."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from app.services.reference_query import query_reference_dataset

router = APIRouter(prefix="/api/reference", tags=["reference-data"])


def _data_dir(request: Request):
    return request.app.state.repo.store.data_dir


def _query(
    request: Request,
    dataset_id: str,
    *,
    symbol: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    pool_id: str | None = None,
    index_code: str | None = None,
    limit: int = 100,
) -> dict:
    try:
        return query_reference_dataset(
            _data_dir(request),
            dataset_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            pool_id=pool_id,
            index_code=index_code,
            limit=limit,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail={"code": "reference_invalid_request", "message": str(error)},
        ) from None


@router.get("/valuation-daily")
def get_valuation_daily(
    request: Request,
    symbol: str | None = Query(None, description="A股代码, 例如 600756.SH"),
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """只读查询本地估值日数据; 查询时不访问外部端点。"""
    return _query(
        request,
        "valuation_daily",
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@router.get("/limit-up-events")
def get_limit_up_events(
    request: Request,
    symbol: str | None = Query(None, description="A股代码, 例如 600756.SH"),
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """只读查询本地涨跌停事件; 查询时不访问外部端点。"""
    return _query(
        request,
        "limit_up_events",
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@router.get("/index-membership")
def get_index_membership(
    request: Request,
    symbol: str | None = Query(None, description="成分股代码, 例如 000001.SZ"),
    pool_id: str | None = Query(None, description="本地股票池, 例如 CSI300"),
    index_code: str | None = Query(None, description="指数代码, 例如 000300"),
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """只读查询本地指数/股票池成分观察历史。"""
    return _query(
        request,
        "index_membership_history",
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        pool_id=pool_id,
        index_code=index_code,
        limit=limit,
    )


@router.get("/corporate-actions")
def get_corporate_actions(
    request: Request,
    symbol: str | None = Query(None, description="A股代码, 例如 600519.SH"),
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """只读查询本地公司行动; 查询时不访问外部端点。"""
    return _query(
        request,
        "corporate_actions",
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
