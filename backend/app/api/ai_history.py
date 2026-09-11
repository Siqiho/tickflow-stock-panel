"""Read-only cross-feature AI history for the authenticated account."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from app.services.analysis_history import (
    AnalysisHistoryKind,
    get_analysis_history_report,
    list_analysis_history,
)

router = APIRouter(prefix="/api/ai-history", tags=["ai-history"])


@router.get("/reports")
def reports(
    kind: Annotated[AnalysisHistoryKind | None, Query()] = None,
    symbol: Annotated[str, Query(max_length=32)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    """List saved report metadata without returning every report body."""
    return list_analysis_history(kind=kind or "", symbol=symbol, limit=limit)


@router.get("/reports/{kind}/{report_id}")
def report(
    kind: AnalysisHistoryKind,
    report_id: Annotated[str, Path(min_length=1, max_length=200)],
) -> dict:
    """Read one saved report body from the authenticated account."""
    result = get_analysis_history_report(kind, report_id)
    if result is None:
        raise HTTPException(status_code=404, detail="分析历史报告不存在")
    return result
