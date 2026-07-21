from __future__ import annotations

from app.services.pipeline_jobs import JobStore, _normalize_legacy_quality_status, terminal_status


def test_pipeline_result_with_failed_quality_is_degraded(tmp_path):
    result = {"quality": {"ok": False, "issues": [{"code": "low_coverage"}]}}

    assert terminal_status(result) == "degraded"

    store = JobStore(store_dir=tmp_path)
    job_id = store.create()
    store.start(job_id)
    store.complete(job_id, result)

    saved = store.get(job_id)
    assert saved is not None
    assert saved["status"] == "degraded"
    assert saved["result"] == result


def test_pipeline_result_with_passing_quality_succeeds(tmp_path):
    result = {"quality": {"ok": True, "issues": []}}

    assert terminal_status(result) == "succeeded"

    store = JobStore(store_dir=tmp_path)
    job_id = store.create()
    store.start(job_id)
    store.complete(job_id, result)

    assert store.get(job_id)["status"] == "succeeded"


def test_missing_quality_result_is_degraded(tmp_path):
    assert terminal_status({"quality": None}) == "degraded"


def test_legacy_succeeded_job_with_failed_quality_is_presented_as_degraded():
    legacy = {"status": "succeeded", "result": {"quality": {"ok": False}}}

    normalized = _normalize_legacy_quality_status(legacy)

    assert normalized["status"] == "degraded"
    assert legacy["status"] == "succeeded"


def test_daily_pipeline_transitions_are_mirrored_without_progress_ticks(tmp_path):
    mirrored = []
    store = JobStore(store_dir=tmp_path)
    store.set_control_plane_sink(mirrored.append)

    job_id = store.create(mirror={"dataset_id": "daily_pipeline", "operation": "daily_pipeline"})
    store.start(job_id)
    store.progress(job_id, "sync_daily", 50, "halfway")
    store.complete(job_id, {"quality": {"ok": True}})

    assert [job["status"] for job in mirrored] == ["pending", "running", "succeeded"]
    assert {job["_catalog_mirror"]["dataset_id"] for job in mirrored} == {"daily_pipeline"}


def test_instruments_and_failed_pipeline_are_mirrored_with_distinct_terminal_statuses(tmp_path):
    mirrored = []
    store = JobStore(store_dir=tmp_path)
    store.set_control_plane_sink(mirrored.append)

    instruments = store.create(mirror={"dataset_id": "daily_pipeline", "operation": "instruments"})
    store.start(instruments)
    store.degrade(instruments, {"quality": {"ok": False}})
    failed = store.create(mirror={"dataset_id": "daily_pipeline", "operation": "daily_pipeline"})
    store.start(failed)
    store.fail(failed, "provider unavailable")

    assert [(job["_catalog_mirror"]["operation"], job["status"]) for job in mirrored] == [
        ("instruments", "pending"),
        ("instruments", "running"),
        ("instruments", "degraded"),
        ("daily_pipeline", "pending"),
        ("daily_pipeline", "running"),
        ("daily_pipeline", "failed"),
    ]


def test_control_plane_sink_failure_does_not_change_legacy_job_result(tmp_path):
    store = JobStore(store_dir=tmp_path)

    def failing_sink(_job):
        raise RuntimeError("sqlite unavailable")

    store.set_control_plane_sink(failing_sink)
    job_id = store.create(mirror={"dataset_id": "daily_pipeline", "operation": "daily_pipeline"})
    store.start(job_id)
    store.complete(job_id, {"quality": {"ok": True}})

    saved = store.get(job_id)
    assert saved is not None
    assert saved["status"] == "succeeded"
