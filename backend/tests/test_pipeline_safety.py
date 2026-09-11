"""有限阶段: pending 单飞、run slot 恢复、sector fail-closed、通知 ContextVar。

禁止把「两个 job」或「sector 等于全量」写成成功。不触网、不发真实消息。
"""
from __future__ import annotations

import threading
import time

import polars as pl
import pytest

from app.services import pipeline_jobs, user_context
from app.services.pipeline_jobs import JobStore
from app.services.quote_service import QuoteService
from app.strategy.monitor import SectorScopeError, apply_monitor_scope


@pytest.fixture(autouse=True)
def _reset_run_slot():
    pipeline_jobs.release_run_slot()
    pipeline_jobs._CANCEL_FLAGS.clear()
    yield
    pipeline_jobs.release_run_slot()
    pipeline_jobs._CANCEL_FLAGS.clear()


def _schedule_if_new(store: JobStore, **kwargs):
    created = store.create(timeout_s=60, **kwargs)
    if not created.is_new:
        return "reused", str(created)
    return "started", str(created)


def test_duplicate_create_schedules_only_one_job(tmp_path):
    store = JobStore(store_dir=tmp_path / "jobs")
    first_status, first_id = _schedule_if_new(store, work_key="pipeline.daily")
    second_status, second_id = _schedule_if_new(store, work_key="pipeline.daily")
    assert first_status == "started"
    assert second_status == "reused"
    assert first_id == second_id


def test_concurrent_duplicate_create_one_job(tmp_path):
    store = JobStore(store_dir=tmp_path / "jobs")
    ids: list[str] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        ids.append(str(store.create(timeout_s=60, work_key="same-work")))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(set(ids)) == 1


def test_different_work_keys_are_not_merged(tmp_path):
    store = JobStore(store_dir=tmp_path / "jobs")
    a = store.create(timeout_s=60, work_key="kline.sync_minute")
    b = store.create(timeout_s=60, work_key="kline.extend_history|month|12")
    c = store.create(timeout_s=60, work_key="kline.extend_history|year|5")
    assert len({str(a), str(b), str(c)}) == 3


def test_different_users_are_not_merged(tmp_path):
    store = JobStore(store_dir=tmp_path / "jobs")
    token_a = user_context.bind({"id": "alice", "username": "alice", "role": "user"})
    try:
        first = store.create(timeout_s=60, work_key="same-work")
    finally:
        user_context.reset(token_a)
    token_b = user_context.bind({"id": "bob", "username": "bob", "role": "user"})
    try:
        second = store.create(timeout_s=60, work_key="same-work")
    finally:
        user_context.reset(token_b)
    assert str(first) != str(second)


def test_terminal_then_new_request_creates_new_job(tmp_path):
    store = JobStore(store_dir=tmp_path / "jobs")
    first = store.create(timeout_s=60, work_key="pipeline.daily")
    store.start(str(first))
    store.fail(str(first), "cancelled")
    second = store.create(timeout_s=60, work_key="pipeline.daily")
    assert str(second) != str(first)
    assert second.is_new is True


def test_long_running_uses_long_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.preferences.get_data_source_long_job_timeout_s",
        lambda: 1800,
    )
    monkeypatch.setattr(
        "app.services.preferences.get_data_source_job_timeout_s",
        lambda: 300,
    )
    store = JobStore(store_dir=tmp_path / "jobs")
    created = store.create(long_running=True)
    assert store.get(str(created))["timeout_s"] == 1800


def test_run_slot_owner_guard_and_recover_after_exception():
    assert pipeline_jobs.try_acquire_run_slot("owner-a") is True
    assert pipeline_jobs.try_acquire_run_slot("owner-b") is False
    pipeline_jobs.release_run_slot("owner-b")
    assert pipeline_jobs.try_acquire_run_slot("owner-c") is False
    try:
        raise RuntimeError("worker crashed")
    except RuntimeError:
        pipeline_jobs.release_run_slot("owner-a")
    assert pipeline_jobs.try_acquire_run_slot("owner-retry") is True
    pipeline_jobs.release_run_slot("owner-retry")


def test_sector_explicit_members_filter():
    df = pl.DataFrame({
        "symbol": ["600000.SH", "000001.SZ", "600519.SH"],
        "close": [12.0, 15.0, 1600.0],
    })
    out = apply_monitor_scope(df, {
        "scope": "sector",
        "sector": "银行",
        "sector_targets": [{"name": "银行", "members": ["600000.SH"]}],
    })
    assert out.height == 1
    assert out.height != df.height
    assert out["symbol"].to_list() == ["600000.SH"]


def test_sector_empty_member_list_raises():
    df = pl.DataFrame({"symbol": ["600000.SH", "000001.SZ"], "close": [10.0, 20.0]})
    with pytest.raises(SectorScopeError):
        apply_monitor_scope(df, {
            "scope": "sector",
            "sector": "银行",
            "sector_targets": [{"name": "银行", "members": []}],
        })


def test_webhook_executor_preserves_bound_user(monkeypatch):
    seen: dict[str, str] = {}
    done = threading.Event()

    def fake_send(*_args):
        seen["id"] = str(user_context.current().get("id"))
        seen["thread"] = threading.current_thread().name
        done.set()

    monkeypatch.setattr("app.services.webhook_adapter.send_feishu", fake_send)
    monkeypatch.setattr("app.services.preferences.get_feishu_webhook_url", lambda: "https://example.invalid/feishu")
    monkeypatch.setattr("app.services.preferences.get_feishu_webhook_secret", lambda: "secret")
    monkeypatch.setattr("app.services.preferences.get_wecom_webhook_url", lambda: "")
    monkeypatch.setattr("app.services.preferences.get_custom_webhook_url", lambda: "")
    monkeypatch.setattr("app.services.preferences.get_email_smtp_config", lambda: {})
    monkeypatch.setattr("app.secrets_store.get_custom_webhook_secret", lambda: "")
    monkeypatch.setattr("app.secrets_store.get_email_smtp_password", lambda: "")

    engine = type("Engine", (), {
        "rules": {"r_ctx": {"webhook_channels": ["feishu"]}},
    })()
    token = user_context.bind({"id": "alice", "username": "alice", "role": "user"})
    try:
        QuoteService._maybe_send_webhook(
            object.__new__(QuoteService),
            [{
                "rule_id": "r_ctx",
                "source": "ladder",
                "symbol": "600000.SH",
                "name": "浦发银行",
                "message": "炸板预警",
            }],
            engine,
        )
    finally:
        user_context.reset(token)

    assert done.wait(2.0) is True
    assert seen["id"] == "alice"
    assert seen["thread"] != threading.current_thread().name
    time.sleep(0.05)


def _wait_event(event: threading.Event, timeout: float = 2.0) -> None:
    assert event.wait(timeout) is True


def test_tracked_scheduler_starts_work_once_on_duplicate(tmp_path, monkeypatch):
    """调度入口 _run_tracked: 并发重复请求只启动一次工作回调, 不是两次 enqueue。"""
    from app.jobs.daily_pipeline import _run_tracked

    store = JobStore(store_dir=tmp_path / "jobs")
    monkeypatch.setattr(pipeline_jobs, "job_store", store)

    calls: list[str] = []
    lock = threading.Lock()
    started = threading.Event()
    hold = threading.Event()
    barrier = threading.Barrier(2)

    def fake_work(on_progress=None):
        with lock:
            calls.append("work")
        started.set()
        _wait_event(hold)
        return {"quality": {"ok": True}}

    def worker() -> None:
        barrier.wait()
        _run_tracked(fake_work, "daily_pipeline")

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    _wait_event(started)
    time.sleep(0.05)
    assert calls == ["work"]
    hold.set()
    for thread in threads:
        thread.join(timeout=2)
        assert thread.is_alive() is False
    assert calls == ["work"]


async def test_pipeline_run_api_starts_work_once_on_duplicate(tmp_path, monkeypatch):
    """真实 /api/pipeline/run 入口: 运行中再请求只复用, 工作回调仍是一次。"""
    import asyncio
    from types import SimpleNamespace

    from app.api import pipeline as pipeline_api
    from app.jobs import daily_pipeline

    store = JobStore(store_dir=tmp_path / "jobs")
    monkeypatch.setattr(pipeline_jobs, "job_store", store)
    monkeypatch.setattr(pipeline_api, "job_store", store)
    monkeypatch.setattr(pipeline_api, "invalidate_storage_cache", lambda: None)

    calls: list[str] = []
    started = threading.Event()
    hold = threading.Event()
    created_tasks: list[asyncio.Task] = []
    original_create_task = asyncio.create_task

    def capture_task(coro):
        task = original_create_task(coro)
        created_tasks.append(task)
        return task

    def fake_run_now(repo, capset, on_progress=None):
        calls.append("run_now")
        started.set()
        _wait_event(hold)
        return {"quality": {"ok": True}}

    monkeypatch.setattr(daily_pipeline, "run_now", fake_run_now)
    monkeypatch.setattr(asyncio, "create_task", capture_task)

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                repo=SimpleNamespace(refresh_cache=lambda: None),
                capabilities=object(),
            )
        )
    )
    first = await pipeline_api.run_now(request)
    assert first["reused"] is False
    started_ok = await asyncio.get_running_loop().run_in_executor(
        None, lambda: started.wait(2.0)
    )
    assert started_ok is True
    second = await pipeline_api.run_now(request)
    assert second["reused"] is True
    assert second["job_id"] == first["job_id"]
    assert calls == ["run_now"]
    assert len(created_tasks) == 1
    hold.set()
    await created_tasks[0]
    job = store.get(first["job_id"])
    assert job is not None
    assert job["status"] in {"succeeded", "degraded"}
    assert calls == ["run_now"]


def test_cancel_while_worker_alive_does_not_start_second_write(tmp_path, monkeypatch):
    """取消时工作线程仍活着: 不得放槽让新任务并发写; 真正结束后可恢复。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import pipeline as pipeline_api
    from app.jobs.daily_pipeline import _run_tracked

    store = JobStore(store_dir=tmp_path / "jobs")
    monkeypatch.setattr(pipeline_jobs, "job_store", store)
    monkeypatch.setattr(pipeline_api, "job_store", store)

    calls: list[str] = []
    started = threading.Event()
    hold = threading.Event()

    def fake_work(on_progress=None):
        calls.append("work")
        started.set()
        _wait_event(hold)
        return {"quality": {"ok": True}}

    worker = threading.Thread(target=lambda: _run_tracked(fake_work, "daily_pipeline"))
    worker.start()
    _wait_event(started)
    job_id = store.active_id()
    assert job_id
    assert calls == ["work"]

    app = FastAPI()
    app.include_router(pipeline_api.router)
    client = TestClient(app)
    resp = client.post(f"/api/pipeline/jobs/{job_id}/cancel")
    assert resp.status_code == 200
    assert store.get(job_id)["status"] == "failed"
    assert pipeline_jobs.try_acquire_run_slot("intruder") is False

    _run_tracked(fake_work, "daily_pipeline")
    assert calls == ["work"]

    hold.set()
    worker.join(timeout=2)
    assert worker.is_alive() is False
    assert pipeline_jobs.try_acquire_run_slot("after") is True
    pipeline_jobs.release_run_slot("after")

    recovered: list[str] = []

    def recovered_work(on_progress=None):
        recovered.append("work")
        return {"quality": {"ok": True}}

    _run_tracked(recovered_work, "daily_pipeline")
    assert recovered == ["work"]


def test_tracked_exception_releases_slot_for_retry(tmp_path, monkeypatch):
    from app.jobs.daily_pipeline import _run_tracked

    store = JobStore(store_dir=tmp_path / "jobs")
    monkeypatch.setattr(pipeline_jobs, "job_store", store)

    def boom(on_progress=None):
        raise RuntimeError("fixture boom")

    _run_tracked(boom, "daily_pipeline")
    assert pipeline_jobs.try_acquire_run_slot("probe") is True
    pipeline_jobs.release_run_slot("probe")

    calls: list[str] = []

    def ok(on_progress=None):
        calls.append("ok")
        return {"quality": {"ok": True}}

    _run_tracked(ok, "daily_pipeline")
    assert calls == ["ok"]
