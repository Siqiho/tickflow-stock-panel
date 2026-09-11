"""财务数据 API — 独立路由, Cap.FINANCIAL 门控。"""
from __future__ import annotations

import logging

import polars as pl
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services import ai_reports
from app.services.financial_analyzer import analyze_financials_stream
from app.services.financial_sync import get_financial_df
from app.tickflow.capabilities import Cap

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/financials", tags=["financials"])

def _public_fin() -> bool:
    try:
        from app.services import preferences
        return preferences.is_public_financial_provider()
    except Exception:
        return False


def _local_fin_ready(request: Request | None = None, data_dir=None) -> bool:
    try:
        from app.services.financial_normalize import local_financials_ready
        if data_dir is not None:
            return local_financials_ready(data_dir)
        if request is not None:
            repo = getattr(request.app.state, "repo", None)
            if repo is not None and getattr(repo, "store", None) is not None:
                return local_financials_ready(repo.store.data_dir)
        from app.config import settings
        return local_financials_ready(settings.data_dir)
    except Exception:
        return False


def _fin_available(capset, request: Request | None = None) -> bool:
    """Expert Cap, public provider, or non-empty local financials parquet."""
    if capset is not None and capset.has(Cap.FINANCIAL):
        return True
    if _public_fin():
        return True
    return _local_fin_ready(request)


def _require_fin(capset, request: Request | None = None) -> None:
    if _fin_available(capset, request):
        return
    try:
        capset.require(Cap.FINANCIAL)
    except Exception as e:
        raise HTTPException(status_code=403, detail=str(e)) from e



@router.get("/status")
def financial_status(request: Request):
    """返回各财务表的同步状态。无需 FINANCIAL 权限（前端根据 available 决定是否展示）。"""
    capset = request.app.state.capabilities
    if not _fin_available(capset, request):
        return {"available": False, "tables": {}, "provider": "none", "local_ready": False}

    data_dir = request.app.state.repo.store.data_dir
    tables = {}

    for table in ("metrics", "income", "balance_sheet", "cash_flow", "shares"):
        path = data_dir / "financials" / table / "part.parquet"
        if path.exists():
            try:
                df = pl.read_parquet(path, columns=["symbol"])
                tables[table] = {
                    "rows": len(df),
                    "symbols": df["symbol"].n_unique() if not df.is_empty() else 0,
                }
            except Exception:
                tables[table] = {"rows": 0, "symbols": 0}
        else:
            tables[table] = {"rows": 0, "symbols": 0}

    fs = getattr(request.app.state, "financial_scheduler", None)
    last_sync = fs.last_sync if fs else {}

    from app.services import preferences as _prefs
    if _public_fin() or capset.has(Cap.FINANCIAL):
        provider = _prefs.get_financial_provider()
    elif _local_fin_ready(request):
        provider = "local"
    else:
        provider = "none"
    # public detail coverage (expense/equity lines) for ops visibility
    detail_coverage: dict = {}
    try:
        inc_path = data_dir / "financials" / "income" / "part.parquet"
        bal_path = data_dir / "financials" / "balance_sheet" / "part.parquet"

        def _nn_syms(df: pl.DataFrame, col: str) -> int:
            if col not in df.columns:
                return 0
            return int(df.filter(pl.col(col).is_not_null())["symbol"].n_unique())

        if inc_path.exists():
            idf = pl.read_parquet(inc_path)
            detail_coverage["income"] = {
                "selling_expense": _nn_syms(idf, "selling_expense"),
                "admin_expense": _nn_syms(idf, "admin_expense"),
                "rd_expense": _nn_syms(idf, "rd_expense"),
                "financial_expense": _nn_syms(idf, "financial_expense"),
                "non_operating_income": _nn_syms(idf, "non_operating_income"),
                "interest_income": _nn_syms(idf, "interest_income"),
            }
        if bal_path.exists():
            bdf = pl.read_parquet(bal_path)
            detail_coverage["balance_sheet"] = {
                "retained_earnings": _nn_syms(bdf, "retained_earnings"),
                "share_capital": _nn_syms(bdf, "share_capital"),
                "intangible_assets": _nn_syms(bdf, "intangible_assets"),
            }
    except Exception as e:
        logger.debug("detail_coverage failed: %s", e)

    period_depth: dict = {}
    try:
        for tname in ("income", "balance_sheet", "cash_flow", "metrics"):
            path = data_dir / "financials" / tname / "part.parquet"
            if not path.exists():
                continue
            df = pl.read_parquet(path)
            if df.is_empty() or "symbol" not in df.columns:
                continue
            g = df.group_by("symbol").len().rename({"len": "n"})
            ns = g["n"]
            period_depth[tname] = {
                "symbols": int(g.height),
                "rows": int(df.height),
                "periods_min": int(ns.min()) if g.height else 0,
                "periods_median": float(ns.median()) if g.height else 0,
                "periods_max": int(ns.max()) if g.height else 0,
                "min_period": str(df["period_end"].min())[:10] if "period_end" in df.columns else None,
                "max_period": str(df["period_end"].max())[:10] if "period_end" in df.columns else None,
            }
    except Exception as e:
        logger.debug("period_depth failed: %s", e)

    return {
        "available": True,
        "provider": provider,
        "local_ready": _local_fin_ready(request),
        "tables": tables,
        "last_sync": last_sync,
        # 服务端是否正在同步(手动触发)——前端据此显示"同步中"并防重复点击,
        # 且刷新页面后仍能正确反映服务端状态。
        "syncing": bool(fs and fs.is_syncing),
        "detail_coverage": detail_coverage,
        "period_depth": period_depth,
        "notes": {
            "shares": "snapshot_from_instruments_not_timeseries",
            "expenses": "industrial_expense_lines; banks/insurers may only have interest/non-op lines",
            "periods": "statement body APIs are fetched in date chunks of 5 to honor financial_max_periods",
        },
    }



def _table_payload(request: Request, table: str, symbol: str | None) -> dict:
    from app.services.financial_normalize import normalize_financial_rows
    capset = request.app.state.capabilities
    _require_fin(capset, request)
    df = get_financial_df(request.app.state.repo.store.data_dir, table)
    if df.is_empty():
        return {"data": []}
    if symbol:
        df = df.filter(pl.col("symbol") == symbol.upper())
    rows = normalize_financial_rows(table, df.to_dicts())
    # newest first for UI
    rows.sort(key=lambda r: str(r.get("period_end") or ""), reverse=True)
    return {"data": rows}

@router.get("/metrics")
def get_metrics(request: Request, symbol: str | None = None):
    """查询核心财务指标。"""
    return _table_payload(request, "metrics", symbol)



@router.get("/income")
def get_income(request: Request, symbol: str | None = None):
    """查询利润表。"""
    return _table_payload(request, "income", symbol)


@router.get("/balance-sheet")
def get_balance_sheet(request: Request, symbol: str | None = None):
    """查询资产负债表。"""
    return _table_payload(request, "balance_sheet", symbol)


@router.get("/cash-flow")
def get_cash_flow(request: Request, symbol: str | None = None):
    """查询现金流量表。"""
    return _table_payload(request, "cash_flow", symbol)


@router.get("/shares")
def get_shares(request: Request, symbol: str | None = None):
    """查询股本（public: instruments 截面快照；TickFlow: financials.shares）。"""
    return _table_payload(request, "shares", symbol)


@router.post("/sync/{table}")
def sync_table(request: Request, table: str):
    """手动触发同步(立即返回,后台异步执行)。

    table: metrics / income / balance_sheet / cash_flow / all
    同步在后台线程执行,全量同步需数分钟。本接口立即返回 started 状态,
    前端通过轮询 GET /status 的 syncing 字段观察进度。
    """
    capset = request.app.state.capabilities
    _require_fin(capset, request)

    valid_tables = {"metrics", "income", "balance_sheet", "cash_flow", "shares", "all"}
    if table not in valid_tables:
        raise HTTPException(400, f"invalid table: {table}, expected one of {valid_tables}")

    fs = getattr(request.app.state, "financial_scheduler", None)
    if not fs:
        return {"status": "error", "message": "FinancialScheduler not available"}

    target = None if table == "all" else table
    result = fs.trigger(target)

    return {"status": "ok", "synced": result}


class AnalyzeRequest(BaseModel):
    """AI 财务分析请求。"""
    symbol: str
    focus: str = ""  # 可选:用户追加的分析关注点


@router.post("/analyze")
async def analyze_financials(request: Request, req: AnalyzeRequest):
    """AI 财务分析 — SSE 流式返回。

    后端读取该标的 4 张财务表 → 注入 CFA 分析师级提示词 → 流式调用 LLM →
    逐 chunk 以 SSE 形式推给前端(JSON per line, 非 text/event-stream,
    以便前端用 ReadableStream 逐行解析,更简单可靠)。
    """
    capset = request.app.state.capabilities
    _require_fin(capset, request)

    if not req.symbol:
        raise HTTPException(400, "symbol 不能为空")
    from app.api.ai_guard import require_ai_http_access
    require_ai_http_access()

    data_dir = request.app.state.repo.store.data_dir

    async def stream_gen():
        async for chunk in analyze_financials_stream(data_dir, req.symbol, req.focus):
            yield chunk + "\n"

    return StreamingResponse(
        stream_gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ================================================================
# AI 报告 CRUD(历史报告持久化)
# ================================================================

class SaveReportRequest(BaseModel):
    """保存一条 AI 财务分析报告。"""
    symbol: str
    name: str = ""
    focus: str = ""
    content: str
    periods: int | None = None
    summary: str = ""


@router.get("/reports")
def list_reports(request: Request):
    """获取全部历史报告(按时间降序,后端已裁剪到上限)。无需 FINANCIAL 能力读取列表元信息。"""
    capset = request.app.state.capabilities
    if not _fin_available(capset, request):
        return {"reports": []}
    return {"reports": ai_reports.list_reports()}


@router.post("/reports")
def save_report(request: Request, req: SaveReportRequest):
    """保存一条报告。"""
    capset = request.app.state.capabilities
    _require_fin(capset, request)
    report = ai_reports.save_report({
        "symbol": req.symbol,
        "name": req.name,
        "focus": req.focus,
        "content": req.content,
        "periods": req.periods,
        "summary": req.summary,
    })
    return {"ok": True, "report": report}


@router.delete("/reports/{report_id}")
def delete_report(request: Request, report_id: str):
    """删除一条报告。"""
    capset = request.app.state.capabilities
    _require_fin(capset, request)
    ok = ai_reports.delete_report(report_id)
    return {"ok": ok}
