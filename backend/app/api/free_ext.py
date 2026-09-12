"""Free no-subscription extension APIs for the data desk."""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.services.daily_quality import run_daily_quality_check
from app.services.free_sources.adj_factor_public import (
    fetch_adj_factors_symbol,
    sync_adj_factor_public,
)
from app.services.free_sources.chip_distribution import chips_for_symbol
from app.services.free_sources.f10_snapshot import fetch_f10_summary
from app.services.free_sources.financials_public import (
    fetch_financials_symbol,
    sync_financials_public,
)
from app.services.free_sources.fund_flow import (
    aggregate_board_window,
    fetch_board_daily_history,
    fetch_board_fund_flow_top,
    fetch_board_intraday_flow,
    fetch_concept_fund_flow_top,
    fetch_stock_fund_flow,
    load_board_daily_history,
    load_board_intraday,
    load_stock_fund_flow,
    persist_board_daily_history,
    persist_board_intraday,
    persist_board_snapshot,
    persist_concept_snapshot,
    persist_stock_fund_flow,
    refresh_top_boards_daily_history,
)
from app.services.free_sources.intraday_public import fetch_public_intraday
from app.services.free_sources.pools_public import (
    POOL_SPECS,
    fetch_pool_constituents,
    load_pool_symbols,
    sync_pools_public,
)
from app.services.free_sources.quote_fallback import fetch_watchlist_quotes
from app.services.free_sources.stock_changes import fetch_stock_changes

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/free", tags=["free-ext"])


def _require_lab_public_surface(route: str, label: str) -> None:
    """Lab public fetch/write only for an explicit public route.

    Leftover TickFlow used to share this surface with ``public``. That mixed
    sina / public Lab writes onto leftover TickFlow adj / financial / pool
    routes. Custom / unresolved stay refused.
    """
    token = (route or "").strip().lower()
    if token == "public":
        return
    raise HTTPException(
        status_code=409,
        detail={
            "code": "lab_public_refused",
            "message": f"{label} route {token or 'unresolved'} refuses public Lab",
            "dataset": label,
            "route": token or "unresolved",
        },
    )


def _data_dir(request: Request) -> Path:
    repo = getattr(request.app.state, "repo", None)
    if repo is not None and getattr(repo, "store", None) is not None:
        return Path(repo.store.data_dir)
    # fallback relative
    return Path(__file__).resolve().parents[3] / "data"



def _load_fund_flow_snapshot(data_dir: Path, config_id: str, top: int) -> list[dict]:
    from app.services.ext_data import usable_ext_snapshot_files
    import polars as pl

    files = usable_ext_snapshot_files(data_dir, config_id)
    if not files:
        return []
    df = pl.read_parquet(files)
    if df.is_empty():
        return []
    if "main_net" in df.columns:
        df = df.sort("main_net", descending=True, nulls_last=True)
    if not top or top >= df.height:
        return df.to_dicts()
    # 同时覆盖净流入与净流出两端
    head_n = max(1, top // 2)
    tail_n = max(1, top - head_n)
    head_df = df.head(head_n)
    tail_df = df.tail(tail_n)
    # 去重后按 main_net 降序
    merged = pl.concat([head_df, tail_df]).unique(subset=[c for c in ("code", "name") if c in df.columns] or None, keep="first")
    if "main_net" in merged.columns:
        merged = merged.sort("main_net", descending=True, nulls_last=True)
    return merged.head(top).to_dicts()

@router.get("/chips/{symbol}")
def get_chips(
    symbol: str,
    request: Request,
    days: int = Query(120, ge=5, le=500),
    bins: int = Query(80, ge=10, le=300),
    as_of: Annotated[
        date | None,
        Query(description="筹码计算截止交易日, 默认最新"),
    ] = None,
) -> dict:
    try:
        result = chips_for_symbol(
            _data_dir(request),
            symbol.upper(),
            days=days,
            bins=bins,
            as_of=as_of,
        )
        return {"ok": True, "data": result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("chips failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/fund-flow/stock/{symbol}/refresh")
def refresh_stock_fund_flow(symbol: str, request: Request) -> dict:
    try:
        rows = fetch_stock_fund_flow(symbol.upper())
        n = persist_stock_fund_flow(_data_dir(request), symbol.upper(), rows)
        return {"ok": True, "symbol": symbol.upper(), "rows": n, "source": "eastmoney_fflow"}
    except Exception as e:
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
        source = (rows[0].get("source") if rows else None) or "eastmoney_clist"
        return {"ok": True, "rows": n, "source": source}
    except Exception as e:
        logger.warning("board fund flow refresh failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/fund-flow/boards")
def get_boards(request: Request, top: int = Query(20, ge=1, le=500)) -> dict:
    items = _load_fund_flow_snapshot(_data_dir(request), "ext_fund_flow_bk", top)
    return {"ok": True, "items": items, "count": len(items), "cached": True}


@router.post("/fund-flow/concepts/refresh")
def refresh_concepts(request: Request) -> dict:
    try:
        rows = fetch_concept_fund_flow_top()
        n = persist_concept_snapshot(_data_dir(request), rows)
        source = (rows[0].get("source") if rows else None) or "eastmoney_clist"
        return {"ok": True, "rows": n, "source": source}
    except Exception as e:
        logger.warning("concept fund flow refresh failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/fund-flow/concepts")
def get_concepts(request: Request, top: int = Query(20, ge=1, le=500)) -> dict:
    items = _load_fund_flow_snapshot(_data_dir(request), "ext_fund_flow_concept", top)
    return {"ok": True, "items": items, "count": len(items), "cached": True}


@router.get("/fund-flow/boards/window")
def get_boards_window(
    request: Request,
    days: int = Query(63, ge=1, le=250),
    top: int = Query(8, ge=1, le=200),
) -> dict:
    """Industry fund-flow ranking by summed daily main_net over a trading-day window."""
    return aggregate_board_window(_data_dir(request), kind="board", days=days, top=top)


@router.get("/fund-flow/concepts/window")
def get_concepts_window(
    request: Request,
    days: int = Query(63, ge=1, le=250),
    top: int = Query(8, ge=1, le=200),
) -> dict:
    """Concept fund-flow ranking by summed daily main_net over a trading-day window."""
    return aggregate_board_window(_data_dir(request), kind="concept", days=days, top=top)


@router.post("/fund-flow/boards/history/refresh")
def refresh_boards_history(
    request: Request,
    top_n: int = Query(20, ge=1, le=200),
    limit: int = Query(60, ge=5, le=500),
) -> dict:
    """Refresh industry daily history. top_n>=100 backfills the current snapshot universe."""
    try:
        result = refresh_top_boards_daily_history(
            _data_dir(request), kind="board", top_n=top_n, limit=limit
        )
        return result
    except Exception as e:
        logger.warning("board history refresh failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/fund-flow/concepts/history/refresh")
def refresh_concepts_history(
    request: Request,
    top_n: int = Query(20, ge=1, le=50),
    limit: int = Query(60, ge=5, le=500),
) -> dict:
    """Refresh concept ranking + daily history for top inflow/outflow concepts."""
    try:
        result = refresh_top_boards_daily_history(
            _data_dir(request), kind="concept", top_n=top_n, limit=limit
        )
        return result
    except Exception as e:
        logger.warning("concept history refresh failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/fund-flow/board/{code}/history")
def get_board_history(
    code: str,
    request: Request,
    kind: str = Query("board"),
    limit: int = Query(120, ge=1, le=500),
    refresh: bool = Query(False),
) -> dict:
    data_dir = _data_dir(request)
    if kind not in ("board", "concept"):
        raise HTTPException(status_code=400, detail="kind must be board or concept")
    k = "board" if kind == "board" else "concept"
    rows = load_board_daily_history(data_dir, code.upper(), kind=k, limit=limit)
    if refresh or not rows:
        try:
            fetched = fetch_board_daily_history(
                code.upper(), limit=limit, kind=k, allow_local_fallback=False
            )
            persist_board_daily_history(data_dir, code.upper(), fetched, kind=k)
            rows = load_board_daily_history(data_dir, code.upper(), kind=k, limit=limit) or fetched
            return {
                "ok": True,
                "code": code.upper(),
                "kind": k,
                "rows": rows,
                "count": len(rows),
                "cached": False,
                "source": "eastmoney_fflow_day",
            }
        except Exception as e:
            if rows:
                return {
                    "ok": True,
                    "code": code.upper(),
                    "kind": k,
                    "rows": rows,
                    "count": len(rows),
                    "cached": True,
                    "warning": str(e),
                }
            logger.warning("board history fetch failed: %s", e)
            raise HTTPException(status_code=502, detail=str(e)) from e
    return {
        "ok": True,
        "code": code.upper(),
        "kind": k,
        "rows": rows,
        "count": len(rows),
        "cached": True,
    }


@router.get("/fund-flow/board/{code}/intraday")
def get_board_intraday(
    code: str,
    request: Request,
    kind: str = Query("board"),
    refresh: bool = Query(False),
    trade_date: str | None = Query(None),
) -> dict:
    data_dir = _data_dir(request)
    if kind not in ("board", "concept"):
        raise HTTPException(status_code=400, detail="kind must be board or concept")
    k = "board" if kind == "board" else "concept"
    points = load_board_intraday(data_dir, code.upper(), kind=k, trade_date=trade_date)
    if refresh or not points:
        try:
            payload = fetch_board_intraday_flow(code.upper())
            persist_board_intraday(data_dir, payload, kind=k)
            points = payload.get("points") or []
            return {
                "ok": True,
                "code": code.upper(),
                "kind": k,
                "name": payload.get("name"),
                "trade_date": payload.get("trade_date"),
                "updated_time": payload.get("updated_time"),
                "points": points,
                "count": len(points),
                "cached": False,
                "source": payload.get("source") or "eastmoney_fflow_min",
            }
        except Exception as e:
            if points:
                return {
                    "ok": True,
                    "code": code.upper(),
                    "kind": k,
                    "points": points,
                    "count": len(points),
                    "cached": True,
                    "warning": str(e),
                }
            logger.warning("board intraday fetch failed: %s", e)
            raise HTTPException(status_code=502, detail=str(e)) from e
    return {
        "ok": True,
        "code": code.upper(),
        "kind": k,
        "points": points,
        "count": len(points),
        "cached": True,
    }


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
    from app.services import preferences

    try:
        realtime = (preferences.get_realtime_data_provider() or "").strip().lower()
    except Exception:  # noqa: BLE001
        realtime = "unresolved"
    _require_lab_public_surface(realtime, "realtime")
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    try:
        rows = fetch_watchlist_quotes(syms)
        return {"ok": True, "items": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/intraday/{symbol}")
def free_intraday(symbol: str) -> dict:
    from app.services.kline_sync import minute_route

    _require_lab_public_surface(minute_route(), "minute")
    try:
        data = fetch_public_intraday(symbol.upper())
        return {"ok": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/changes")
def free_changes(date: str | None = None) -> dict:
    try:
        items = fetch_stock_changes(date_str=date)
        return {"ok": True, "items": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/f10/{symbol}")
def free_f10(symbol: str) -> dict:
    try:
        data = fetch_f10_summary(symbol.upper())
        return {"ok": True, "data": data}
    except Exception as e:
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
        except Exception as e:
            logger.warning("ths refresh %s failed: %s", cid, e)
            results[cid] = {"ok": False, "error": str(e)}
    return {"ok": all(v.get("ok") for v in results.values()), "results": results}


@router.get("/adj-factor/{symbol}")
def free_adj_factor_symbol(symbol: str) -> dict:
    """On-demand public (Sina qfq) event-level adj factors for one symbol. Does not write disk."""
    from app.services.kline_sync import adj_route

    _require_lab_public_surface(adj_route(), "adj")
    try:
        df = fetch_adj_factors_symbol(symbol.upper())
        items = df.to_dicts() if df is not None and not df.is_empty() else []
        # serialize dates
        for it in items:
            d = it.get("trade_date")
            if d is not None and hasattr(d, "isoformat"):
                it["trade_date"] = d.isoformat()
        return {"ok": True, "source": "sina_qfq", "symbol": symbol.upper(), "items": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/adj-factor/sync")
def free_adj_factor_sync(
    request: Request,
    symbols: str = Query("", description="comma-separated symbols; empty = use scope"),
    scope: str = Query("", description="ALL|CSI300|CSI500|SSE50|WATCHLIST; default public_data_scope"),
    limit: int = Query(0, ge=0, le=20000, description="0=no limit"),
    asset_type: str = Query("stock", description="stock|etf"),
) -> dict:
    """Pull public adj factors and merge-write into data/adj_factor[/etf]/all.parquet."""
    from app.services import preferences
    from app.services.universe_scope import resolve_symbols

    data_dir = _data_dir(request)
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    used_scope = None
    if not sym_list:
        used_scope = scope.strip() or preferences.get_public_data_scope()
        sym_list = resolve_symbols(
            used_scope, data_dir=data_dir, default="CSI300", refresh_pools_if_missing=True
        )
        if not sym_list:
            raise HTTPException(status_code=400, detail=f"no symbols for scope={used_scope}")
    if limit and limit > 0:
        sym_list = sym_list[:limit]
    at = "etf" if asset_type.lower() == "etf" else "stock"
    from app.services.kline_sync import adj_route

    _require_lab_public_surface(adj_route(), "adj")
    try:
        result = sync_adj_factor_public(sym_list, data_dir, asset_type=at)
        if used_scope:
            result = {**result, "scope": used_scope}
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/financials/{symbol}")
def free_financials_symbol(
    symbol: str,
    max_periods: int = Query(0, ge=0, le=40, description="0=use preferences.financial_max_periods"),
) -> dict:
    """On-demand public financials (East Money HSF10). Does not write disk."""
    from app.services.financial_sync import financial_write_route

    _require_lab_public_surface(financial_write_route(), "financial")
    try:
        got = fetch_financials_symbol(symbol.upper(), max_periods=max_periods)
        out = {}
        for table, df in got.items():
            items = df.to_dicts() if df is not None and not df.is_empty() else []
            for it in items:
                for k, v in list(it.items()):
                    if hasattr(v, "isoformat"):
                        it[k] = v.isoformat()
            out[table] = items
        return {"ok": True, "source": "eastmoney_hsf10", "symbol": symbol.upper(), "tables": out}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/financials/sync")
def free_financials_sync(
    request: Request,
    symbols: str = Query("", description="comma-separated; empty = use scope"),
    scope: str = Query("", description="ALL|CSI300|CSI500|SSE50|WATCHLIST; default public_data_scope"),
    limit: int = Query(0, ge=0, le=5000, description="0=no limit"),
    max_periods: int = Query(0, ge=0, le=40, description="0=use preferences.financial_max_periods"),
) -> dict:
    """Pull public financials and merge-write into data/financials/*/part.parquet."""
    from app.services import preferences
    from app.services.universe_scope import resolve_symbols

    data_dir = _data_dir(request)
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    used_scope = None
    if not sym_list:
        used_scope = scope.strip() or preferences.get_public_data_scope()
        sym_list = resolve_symbols(
            used_scope, data_dir=data_dir, default="CSI300", refresh_pools_if_missing=True
        )
        if not sym_list:
            raise HTTPException(status_code=400, detail=f"no symbols for scope={used_scope}")
    if limit and limit > 0:
        sym_list = sym_list[:limit]
    from app.services.financial_sync import financial_write_route

    _require_lab_public_surface(financial_write_route(), "financial")
    try:
        from app.services import preferences as _prefs
        mp = max_periods if max_periods and max_periods > 0 else _prefs.get_financial_max_periods()
        result = sync_financials_public(sym_list, data_dir, max_periods=mp)
        if used_scope:
            result = {**result, "scope": used_scope, "max_periods": mp}
        else:
            result = {**result, "max_periods": mp}
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/pools")
def free_pools_list(request: Request) -> dict:
    """List cached public index pools under data/pools/."""
    data_dir = _data_dir(request)
    items = []
    for pid, spec in POOL_SPECS.items():
        path = data_dir / "pools" / f"{pid}.parquet"
        syms = load_pool_symbols(data_dir, pid) if path.exists() else []
        items.append({
            "pool_id": pid,
            "name": spec.get("name"),
            "index_code": spec.get("index_code"),
            "count": len(syms),
            "cached": path.exists(),
            "path": str(path) if path.exists() else None,
        })
    return {"ok": True, "items": items}


@router.get("/pools/{pool_id}")
def free_pool_get(pool_id: str, request: Request, refresh: bool = Query(False)) -> dict:
    """Get constituent symbols for CSI300/CSI500/SSE50. refresh=1 forces re-fetch."""
    pid = pool_id.strip().upper()
    if pid not in POOL_SPECS:
        raise HTTPException(status_code=400, detail=f"unsupported pool_id: {pool_id}")
    data_dir = _data_dir(request)
    from app.tickflow.pools import pool_route

    _require_lab_public_surface(pool_route(), "pool")
    try:
        if refresh:
            from app.services.free_sources.pools_public import write_pool_parquet
            df = fetch_pool_constituents(pid)
            write_pool_parquet(df, data_dir, pid)
            syms = df["symbol"].to_list()
            source = df["source"][0] if "source" in df.columns and df.height else None
        else:
            syms = load_pool_symbols(data_dir, pid)
            source = None
            if not syms:
                from app.services.free_sources.pools_public import write_pool_parquet
                df = fetch_pool_constituents(pid)
                write_pool_parquet(df, data_dir, pid)
                syms = df["symbol"].to_list()
                source = df["source"][0] if "source" in df.columns and df.height else None
        return {
            "ok": True,
            "pool_id": pid,
            "count": len(syms),
            "symbols": syms,
            "source": source,
            "name": POOL_SPECS[pid]["name"],
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/pools/sync")
def free_pools_sync(
    request: Request,
    pools: str = Query("CSI300,CSI500,SSE50", description="comma-separated pool ids"),
) -> dict:
    """Refresh public index constituent caches into data/pools/*.parquet."""
    data_dir = _data_dir(request)
    ids = [p.strip().upper() for p in pools.split(",") if p.strip()]
    from app.tickflow.pools import pool_route

    _require_lab_public_surface(pool_route(), "pool")
    try:
        return sync_pools_public(data_dir, pool_ids=ids or None)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
