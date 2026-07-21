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
