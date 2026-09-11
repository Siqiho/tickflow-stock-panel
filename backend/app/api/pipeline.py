"""盘后管道 API — 异步触发 + 进度跟踪。"""
from __future__ import annotations

import asyncio
import concurrent.futures as _cf
import logging

from fastapi import APIRouter, HTTPException, Request

from app.jobs import daily_pipeline
from app.services.pipeline_jobs import (
    is_cancelled,
    job_store,
    release_run_slot,
    request_cancel,
    try_acquire_run_slot,
)
from app.api.data import invalidate_storage_cache
from app.tickflow.capabilities import CapabilitySet


def _http_capset(request: Request) -> CapabilitySet:
    """HTTP 缺 capabilities 时 fail-closed, 不把 None 传给管道当无门控。"""
    capset = getattr(getattr(request, "app", None), "state", None)
    capset = getattr(capset, "capabilities", None) if capset is not None else None
    if capset is None:
        return CapabilitySet()
    return capset

# 长时间任务专用线程池（隔离于 FastAPI 默认线程池，防止阻塞请求处理）
_long_task_executor = _cf.ThreadPoolExecutor(max_workers=2, thread_name_prefix="long-task")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/run")
async def run_now(request: Request) -> dict:
    """异步触发盘后管道,立即返回 job_id。客户端轮询 /jobs/{id} 拿进度。

    若已有任务在跑,**返回该任务 id 而不是开新任务**(防止并发拉数据撞限流)。
    卡死判定走 reap_stale（进度停滞 / 硬上限），不再用总时长一刀切。
    """
    repo = request.app.state.repo
    capset = _http_capset(request)

    # 进度停滞 / 硬上限自愈。不再用「总时长 10 分钟」一刀切。
    job_store.reap_stale()

    created = job_store.create(
        mirror={"dataset_id": "daily_pipeline", "operation": "daily_pipeline"}
    )
    job_id = str(created)
    if not created.is_new:
        return {"job_id": job_id, "reused": True}

    # 在 executor 里跑同步任务(pipeline 内部都是阻塞 IO + CPU)
    async def task() -> None:
        if is_cancelled(job_id):
            return
        if not try_acquire_run_slot(job_id):
            job_store.fail(job_id, "已有数据任务在运行(或上一次任务卡死未结束),请稍后再试")
            return
        try:
            job_store.start(job_id)
            loop = asyncio.get_event_loop()

            def progress(stage: str, pct: int, msg: str, stage_pct: int | None = None,
                         skip_log: bool = False) -> None:
                job_store.progress(job_id, stage, pct, msg, stage_pct=stage_pct, skip_log=skip_log)

            try:
                result = await loop.run_in_executor(
                    _long_task_executor,
                    lambda: daily_pipeline.run_now(repo, capset, on_progress=progress),
                )
                job_store.complete(job_id, result)
                invalidate_storage_cache()
                repo.refresh_cache()  # 刷新 Polars 缓存
            except Exception as e:  # noqa: BLE001
                logger.exception("pipeline failed")
                job_store.fail(job_id, str(e))
                invalidate_storage_cache()
        finally:
            release_run_slot(job_id)

    asyncio.create_task(task())
    return {"job_id": job_id, "reused": False}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job_store.reap_stale()
    j = job_store.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    return j


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    """手动取消一个 running 的 job。"""
    j = job_store.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    if j["status"] not in ("running", "pending"):
        raise HTTPException(status_code=400, detail=f"job status is {j['status']}, cannot cancel")
    request_cancel(job_id)
    daily_pipeline.request_industry_roll_cancel()
    job_store.fail(job_id, "用户手动取消")
    # 工作线程仍存活时不得放槽, 否则新请求会并发写。槽由执行体 finally 在真正结束后释放。
    return {"cancelled": job_id}


@router.get("/jobs")
def list_jobs(limit: int = 20) -> dict:
    return {
        "active_id": job_store.active_id(),
        "jobs": job_store.list_recent(limit=limit),
    }
