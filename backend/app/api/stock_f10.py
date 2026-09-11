"""本地股票 F10 补充数据查询与显式同步入口。"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.services.free_sources.margin_trading_public import (
    MarginTradingQualityError,
    MarginTradingQueryError,
    query_margin_trading_result,
    sync_margin_trading,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/f10", tags=["stock-f10"])


class MarginTradingSyncRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1, max_length=50)
    rows_per_symbol: int = Field(250, ge=10, le=1_000)


def _data_dir(request: Request):
    return request.app.state.repo.store.data_dir


@router.get("/margin-trading")
def get_margin_trading(
    request: Request,
    symbol: str | None = Query(None, description="A股代码, 例如 600519.SH"),
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(250, ge=1, le=5_000),
    source: str = Query("local", description="local 或 offline_quantdb，禁止传文件路径"),
) -> dict:
    """只读查询融资融券日数据; 默认本地自有库，offline_quantdb 只读原包 by_symbol。"""
    try:
        result = query_margin_trading_result(
            _data_dir(request),
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            source=source,
            offline_root=settings.offline_quantdb_root,
        )
    except MarginTradingQueryError as error:
        raise HTTPException(
            status_code=error.http_status,
            detail={"code": error.code, "message": str(error)},
        ) from None
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail={"code": "margin_trading_invalid_request", "message": str(error)},
        ) from None
    payload = {
        "data": result.frame.to_dicts(),
        "count": result.frame.height,
        "source": result.source,
        "unit_version": result.unit_version,
        "as_of": result.as_of,
        "status": result.status,
        "missing_fields": list(result.missing_fields),
    }
    if result.note:
        payload["note"] = result.note
    return payload


@router.post("/margin-trading/sync")
def sync_margin_trading_endpoint(request: Request, body: MarginTradingSyncRequest) -> dict:
    """显式采集东方财富单源融资融券数据, 成功发布后刷新本地目录。"""
    try:
        result = sync_margin_trading(
            body.symbols,
            _data_dir(request),
            max_rows=body.rows_per_symbol,
        )
    except MarginTradingQualityError:
        logger.exception("margin trading sync quality validation failed")
        raise HTTPException(
            status_code=502,
            detail={
                "code": "margin_trading_upstream_failed",
                "message": "融资融券数据源返回了不完整数据",
            },
        ) from None
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail={"code": "margin_trading_invalid_request", "message": str(error)},
        ) from None
    except RuntimeError:
        logger.exception("margin trading sync failed")
        raise HTTPException(
            status_code=502,
            detail={
                "code": "margin_trading_upstream_failed",
                "message": "融资融券数据源暂时不可用",
            },
        ) from None

    catalog_refreshed = False
    catalog = getattr(request.app.state, "catalog_service", None)
    if catalog is not None:
        try:
            catalog.refresh_after_mutation("stock_margin_trading")
            catalog_refreshed = True
        except Exception:
            logger.exception("catalog refresh failed after margin trading publish")
    return {**result.as_dict(), "catalog_refreshed": catalog_refreshed}
