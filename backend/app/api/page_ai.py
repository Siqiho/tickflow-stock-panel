"""Saved page-embedded Hermes analyses."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import page_ai_reports

router = APIRouter(prefix="/api/page-ai", tags=["page-ai"])


class SavePageAiReportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    route: str = Field(default="", max_length=120)
    as_of: str | None = None
    focus: str = ""
    summary: str = ""
    content: str = Field(min_length=1, max_length=80_000)
    session_id: str = ""


@router.get("/reports")
def list_reports() -> dict:
    return {"reports": page_ai_reports.list_reports()}


@router.get("/reports/{report_id}")
def get_report(report_id: str) -> dict:
    report = page_ai_reports.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="页面分析记录不存在")
    return {"report": report}


@router.post("/reports")
def save_report(req: SavePageAiReportRequest) -> dict:
    report = page_ai_reports.save_report({
        "title": req.title.strip(),
        "route": req.route.strip(),
        "as_of": (req.as_of or "").strip() or None,
        "focus": req.focus.strip(),
        "summary": req.summary.strip(),
        "content": req.content,
        "session_id": req.session_id.strip(),
    })
    return {"ok": True, "report": report}


@router.delete("/reports/{report_id}")
def delete_report(report_id: str) -> dict:
    return {"ok": page_ai_reports.delete_report(report_id)}
