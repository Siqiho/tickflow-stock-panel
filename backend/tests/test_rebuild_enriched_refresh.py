from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.api import data as data_api
from app.api import kline as kline_api
from app.indicators import pipeline
from app.services import pipeline_jobs
from app.services.pipeline_jobs import JobStore


class _FakeDB:
    def execute(self, _sql: str) -> None:
        return None


class _FakeRepo:
    def __init__(self, data_dir: Path) -> None:
        self.store = SimpleNamespace(data_dir=data_dir)
        self.db = _FakeDB()
        self.refresh_count = 0

    def refresh_cache(self) -> None:
        self.refresh_count += 1


async def test_rebuild_enriched_refreshes_runtime_cache_before_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = _FakeRepo(tmp_path)
    store = JobStore(store_dir=tmp_path / "jobs")
    created_tasks: list[asyncio.Task] = []
    original_create_task = asyncio.create_task

    def capture_task(coro):
        task = original_create_task(coro)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(pipeline_jobs, "job_store", store)
    monkeypatch.setattr(pipeline, "run_pipeline", lambda **_kwargs: 7)
    monkeypatch.setattr(data_api, "invalidate_storage_cache", lambda: None)
    monkeypatch.setattr(asyncio, "create_task", capture_task)

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo)))
    response = await kline_api.rebuild_enriched(request)
    await created_tasks[0]

    job = store.get(response["job_id"])
    assert job is not None
    assert job["status"] == "succeeded"
    assert repo.refresh_count == 1
