"""运行日志 API — 查询 / 上报 / 状态 / 清空。"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services import runtime_logging as rl

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/runtime-logs", tags=["runtime-logs"])


class ClientEventIn(BaseModel):
    ts: str | None = None
    level: str = "INFO"
    category: str = "ui"
    message: str
    path: str | None = None
    method: str | None = None
    status: int | None = None
    duration_ms: float | None = None
    session_id: str | None = None
    detail: dict[str, Any] | None = None
    change: dict[str, Any] | None = None


class ClientEventsBatch(BaseModel):
    session_id: str | None = None
    events: list[ClientEventIn] = Field(default_factory=list)


@router.get("/status")
def logs_status() -> dict:
    return rl.get_status()


@router.get("")
def list_logs(
    source: str | None = Query(None, description="ui | backend | access"),
    level: str | None = Query(None, description="最低级别, 如 INFO/WARNING/ERROR"),
    category: str | None = Query(None),
    q: str | None = Query(None, description="全文搜索"),
    limit: int = Query(200, ge=1, le=1000),
    after_id: str | None = Query(None, description="只返回比该 id 更新的事件"),
) -> dict:
    events = rl.query_events(
        source=source,
        level=level,
        category=category,
        q=q,
        limit=limit,
        after_id=after_id,
    )
    status = rl.get_status()
    return {
        "events": events,
        "count": len(events),
        "process_id": status.get("process_id"),
        "log_dir": status.get("log_dir"),
        "latest_ts": status.get("latest_ts"),
    }


@router.post("/client")
def ingest_client_logs(body: ClientEventsBatch) -> dict:
    if not body.events:
        return {"ok": True, "accepted": 0}
    if len(body.events) > 200:
        raise HTTPException(status_code=400, detail="单次最多 200 条事件")
    accepted = rl.ingest_client_events(
        (e.model_dump(exclude_none=True) for e in body.events),
        default_session=body.session_id,
    )
    return {"ok": True, "accepted": accepted}


@router.delete("")
def clear_logs(keep_files: bool = Query(False, description="仅清内存, 保留磁盘文件")) -> dict:
    return rl.clear_logs(keep_files=keep_files)
