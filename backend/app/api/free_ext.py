"""Free no-subscription extension APIs for the data desk."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from app.services.daily_quality import run_daily_quality_check
from app.services.free_sources.chip_distribution import chips_for_symbol
from app.services.free_sources.f10_snapshot import fetch_f10_summary
from app.services.free_sources.fund_flow import (
    fetch_board_fund_flow_top,
    fetch_concept_fund_flow_top,
    fetch_stock_fund_flow,
    load_stock_fund_flow,
    persist_board_snapshot,
    persist_concept_snapshot,
    persist_stock_fund_flow,
)
from app.services.free_sources.intraday_public import fetch_public_intraday
from app.services.free_sources.quote_fallback import fetch_watchlist_quotes
from app.services.free_sources.stock_changes import fetch_stock_changes

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/free", tags=["free-ext"])


def _data_dir(request: Request) -> Path:
    repo = getattr(request.app.state, "repo", None)
    if repo is not None and getattr(repo, "store", None) is not None:
        return Path(repo.store.data_dir)
    # fallback relative
    return Path(__file__).resolve().parents[3] / "data"


@router.get("/chips/{symbol}")
def get_chips(
    symbol: str,
    request: Request,
    days: int = Query(120, ge=5, le=500),
    bins: int = Query(80, ge=10, le=300),
) -> dict:
    try:
        result = chips_for_symbol(_data_dir(request), symbol.upper(), days=days, bins=bins)
        return {"ok": True, "data": result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("chips failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/fund-flow/stock/{symbol}/refresh")
def refresh_stock_fund_flow(symbol: str, request: Request) -> dict:
    try:
        rows = fetch_stock_fund_flow(symbol.upper())
        n = persist_stock_fund_flow(_data_dir(request), symbol.upper(), rows)
        return {"ok": True, "symbol": symbol.upper(), "rows": n, "source": "eastmoney_fflow"}
    except Exception as e:  # noqa: BLE001
        logger.warning("stock fund flow refresh failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/fund-flow/stock/{symbol}")
def get_stock_fund_flow(symbol: str, request: Request, limit: int = Query(60, ge=1, le=500)) -> dict:
    rows = load_stock_fund_flow(_data_dir(request), symbol.upper(), limit=limit)
    return {"ok": True, "symbol": symbol.upper(), "rows": rows, "count": len(rows), "cached": True}


@router.post("/fund-flow/boards/refresh")
def refresh_boards(request: Request) -> dict:
    try:
        rows = fetch_board_fund_flow_top()
        n = persist_board_snapshot(_data_dir(request), rows)
        return {"ok": True, "rows": n, "items": rows[:50], "source": "eastmoney_bkzj"}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/fund-flow/boards")
def get_boards(request: Request, top: int = Query(20, ge=1, le=200)) -> dict:
    path = _data_dir(request) / "ext_data" / "ext_fund_flow_bk" / "part.parquet"
    if not path.exists():
        return {"ok": True, "items": [], "count": 0, "cached": True}
    import polars as pl

    df = pl.read_parquet(path)
    if top:
        df = df.head(top)
    items = df.to_dicts()
    return {"ok": True, "items": items, "count": len(items), "cached": True}


@router.post("/fund-flow/concepts/refresh")
def refresh_concepts(request: Request) -> dict:
    try:
        rows = fetch_concept_fund_flow_top()
        n = persist_concept_snapshot(_data_dir(request), rows)
        return {"ok": True, "rows": n, "items": rows[:50], "source": "eastmoney_bkzj"}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/fund-flow/concepts")
def get_concepts(request: Request, top: int = Query(20, ge=1, le=200)) -> dict:
    path = _data_dir(request) / "ext_data" / "ext_fund_flow_concept" / "part.parquet"
    if not path.exists():
        return {"ok": True, "items": [], "count": 0, "cached": True}
    import polars as pl

    df = pl.read_parquet(path)
    if top:
        df = df.head(top)
    items = df.to_dicts()
    return {"ok": True, "items": items, "count": len(items), "cached": True}


@router.get("/quality/latest")
def quality_latest(request: Request) -> dict:
    path = _data_dir(request) / "user_data" / "daily_quality_latest.json"
    if not path.exists():
        return {"ok": True, "report": None}
    return {"ok": True, "report": json.loads(path.read_text(encoding="utf-8"))}


@router.post("/quality/run")
def quality_run(request: Request, date: str | None = None) -> dict:
    report = run_daily_quality_check(_data_dir(request), date=date)
    return {"ok": True, "report": report}


@router.get("/quotes")
def free_quotes(symbols: str = Query(..., description="comma-separated symbols")) -> dict:
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    try:
        rows = fetch_watchlist_quotes(syms)
        return {"ok": True, "items": rows, "count": len(rows)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/intraday/{symbol}")
def free_intraday(symbol: str) -> dict:
    try:
        data = fetch_public_intraday(symbol.upper())
        return {"ok": True, "data": data}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/changes")
def free_changes(date: str | None = None) -> dict:
    try:
        items = fetch_stock_changes(date_str=date)
        return {"ok": True, "items": items, "count": len(items)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/f10/{symbol}")
def free_f10(symbol: str) -> dict:
    try:
        data = fetch_f10_summary(symbol.upper())
        return {"ok": True, "data": data}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/ths/refresh")
async def ths_refresh(request: Request) -> dict:
    """Manually refresh THS concept/industry presets without enabling auto pull."""
    from app.services.ext_presets import fetch_preset, get_preset

    data_dir = _data_dir(request)
    results = {}
    for cid in ("ext_gn_ths", "ext_hy_ths"):
        if get_preset(cid) is None:
            results[cid] = {"ok": False, "error": "preset missing"}
            continue
        try:
            n = await fetch_preset(cid, data_dir)
            results[cid] = {"ok": True, "rows": n}
        except Exception as e:  # noqa: BLE001
            logger.warning("ths refresh %s failed: %s", cid, e)
            results[cid] = {"ok": False, "error": str(e)}
    return {"ok": all(v.get("ok") for v in results.values()), "results": results}
