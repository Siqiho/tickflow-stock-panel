from __future__ import annotations

import asyncio
import inspect
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI

from app import main
from app.data_providers.base import ProviderDatasetManifest
from app.services.pipeline_jobs import JobStore
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet


def _manifest(provider: str, operation: str) -> ProviderDatasetManifest:
    return ProviderDatasetManifest(
        provider=provider,
        dataset_id="stock_daily",
        asset_types=["stock"],
        operations=[operation],
        entitlement_required="unknown" if provider == "tickflow" else None,
        history_guarantee=None,
        verified_at=None,
    )


def test_runtime_entitlement_resolver_uses_explicit_capability_mapping_and_fails_closed() -> None:
    capset = CapabilitySet({Cap.KLINE_DAILY_BY_SYMBOL: CapabilityLimits()})
    resolver = main.build_catalog_entitlement_resolver(capset)

    assert resolver(_manifest("public", "unknown-operation")) is True
    assert resolver(_manifest("local", "unknown-operation")) is True
    assert resolver(_manifest("tickflow", "daily")) is True
    assert resolver(_manifest("tickflow", "minute")) is False
    assert resolver(_manifest("tickflow", "unknown-operation")) is False


def test_catalog_lifespan_injects_detected_capability_resolver(tmp_path) -> None:
    store = JobStore(store_dir=tmp_path / "jobs")
    app = FastAPI()
    capset = CapabilitySet({Cap.KLINE_DAILY_BY_SYMBOL: CapabilityLimits()})

    async def scenario() -> None:
        async with main.catalog_control_plane_lifespan(
            app,
            tmp_path / "data",
            job_store_instance=store,
            capability_set=capset,
        ):
            tickflow_daily = next(
                manifest
                for manifest in app.state.catalog_service.manifests
                if manifest.provider == "tickflow" and manifest.dataset_id == "stock_daily"
            )
            assert app.state.catalog_service.entitlement_resolver(tickflow_daily) is True

    asyncio.run(scenario())


def test_catalog_control_plane_is_entered_before_background_resources() -> None:
    source = inspect.getsource(main.lifespan)

    assert source.index("catalog_control_plane_lifespan") < source.index(
        "daily_pipeline.start_scheduler"
    )
    assert source.index("catalog_control_plane_lifespan") < source.index(
        "depth_service.start_polling"
    )
    assert source.index("catalog_control_plane_lifespan") < source.index("pull_scheduler.start")


def test_main_lifespan_closes_catalog_when_later_setup_fails(tmp_path, monkeypatch) -> None:
    events: list[str] = []

    class StubStore:
        data_dir = tmp_path / "data"

    class StubRepo:
        def __init__(self, store) -> None:
            self.store = store

        def refresh_cache(self) -> None:
            events.append("cache")

    class FailingQuoteService:
        def set_repo(self, repo) -> None:
            self.repo = repo

        def boot_check(self) -> None:
            raise RuntimeError("quote setup failed")

        def stop(self) -> None:
            events.append("quote-stop")

    @asynccontextmanager
    async def control_scope(*args, **kwargs):
        events.append("catalog-enter")
        try:
            yield
        finally:
            events.append("catalog-exit")

    monkeypatch.setattr(main, "DataStore", StubStore)
    monkeypatch.setattr(main, "KlineRepository", StubRepo)
    monkeypatch.setattr(main, "QuoteService", FailingQuoteService)
    monkeypatch.setattr(main, "detect_capabilities", CapabilitySet)
    monkeypatch.setattr(main, "catalog_control_plane_lifespan", control_scope)

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="quote setup failed"):
            async with main.lifespan(FastAPI()):
                raise AssertionError("startup failure must prevent yield")

    asyncio.run(scenario())

    assert events == ["cache", "catalog-enter", "quote-stop", "catalog-exit"]


def test_catalog_sink_is_cleared_when_later_startup_raises(tmp_path) -> None:
    store = JobStore(store_dir=tmp_path / "jobs")
    app = FastAPI()

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="later startup failed"):
            async with main.catalog_control_plane_lifespan(
                app, tmp_path / "data", job_store_instance=store
            ):
                raise RuntimeError("later startup failed")

    asyncio.run(scenario())

    assert store._control_plane_sink is None


def test_catalog_sink_is_cleared_when_lifespan_shutdown_raises(tmp_path) -> None:
    store = JobStore(store_dir=tmp_path / "jobs")
    app = FastAPI()

    @asynccontextmanager
    async def failing_shutdown_lifespan():
        async with main.catalog_control_plane_lifespan(
            app, tmp_path / "data", job_store_instance=store
        ):
            try:
                yield
            finally:
                raise RuntimeError("shutdown failed")

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="shutdown failed"):
            async with failing_shutdown_lifespan():
                assert store._control_plane_sink is not None

    asyncio.run(scenario())

    assert store._control_plane_sink is None


def test_older_catalog_lifespan_cannot_clear_newer_sink(tmp_path) -> None:
    store = JobStore(store_dir=tmp_path / "jobs")
    first = main.catalog_control_plane_lifespan(
        FastAPI(), tmp_path / "first", job_store_instance=store
    )
    second = main.catalog_control_plane_lifespan(
        FastAPI(), tmp_path / "second", job_store_instance=store
    )

    async def scenario() -> None:
        await first.__aenter__()
        first_sink = store._control_plane_sink
        await second.__aenter__()
        second_sink = store._control_plane_sink
        assert first_sink is not second_sink

        await first.__aexit__(None, None, None)
        assert store._control_plane_sink is second_sink

        await second.__aexit__(None, None, None)

    asyncio.run(scenario())

    assert store._control_plane_sink is None


def test_newest_exit_restores_older_catalog_owner_for_new_pipeline_runs(tmp_path) -> None:
    store = JobStore(store_dir=tmp_path / "jobs")
    first_app = FastAPI()
    second_app = FastAPI()
    first = main.catalog_control_plane_lifespan(
        first_app, tmp_path / "first", job_store_instance=store
    )
    second = main.catalog_control_plane_lifespan(
        second_app, tmp_path / "second", job_store_instance=store
    )

    async def scenario() -> None:
        await first.__aenter__()
        await second.__aenter__()
        await second.__aexit__(None, None, None)

        job_id = store.create(
            mirror={"dataset_id": "daily_pipeline", "operation": "daily_pipeline"}
        )
        store.start(job_id)
        store.complete(job_id, {"quality": {"ok": True}})

        assert [
            run.status
            for run in first_app.state.catalog_control_db.list_sync_runs("daily_pipeline")
        ] == ["succeeded"]
        assert second_app.state.catalog_control_db.list_sync_runs("daily_pipeline") == []

        await first.__aexit__(None, None, None)

    asyncio.run(scenario())

    assert store._control_plane_sink is None


def test_inflight_job_stays_bound_to_its_creation_owner_after_newer_owner_enters(tmp_path) -> None:
    store = JobStore(store_dir=tmp_path / "jobs")
    first_app = FastAPI()
    second_app = FastAPI()
    first = main.catalog_control_plane_lifespan(
        first_app, tmp_path / "first", job_store_instance=store
    )
    second = main.catalog_control_plane_lifespan(
        second_app, tmp_path / "second", job_store_instance=store
    )

    async def scenario() -> None:
        await first.__aenter__()
        job_id = store.create(
            mirror={"dataset_id": "daily_pipeline", "operation": "daily_pipeline"}
        )
        store.start(job_id)
        await second.__aenter__()
        store.complete(job_id, {"quality": {"ok": True}})

        assert [
            run.status
            for run in first_app.state.catalog_control_db.list_sync_runs("daily_pipeline")
        ] == ["succeeded"]
        assert second_app.state.catalog_control_db.list_sync_runs("daily_pipeline") == []

        await second.__aexit__(None, None, None)
        await first.__aexit__(None, None, None)

    asyncio.run(scenario())


def test_inflight_job_is_aborted_in_its_control_plane_when_owner_exits(tmp_path) -> None:
    store = JobStore(store_dir=tmp_path / "jobs")
    first_app = FastAPI()
    second_app = FastAPI()
    first = main.catalog_control_plane_lifespan(
        first_app, tmp_path / "first", job_store_instance=store
    )
    second = main.catalog_control_plane_lifespan(
        second_app, tmp_path / "second", job_store_instance=store
    )

    async def scenario() -> None:
        await first.__aenter__()
        job_id = store.create(
            mirror={"dataset_id": "daily_pipeline", "operation": "daily_pipeline"}
        )
        store.start(job_id)
        await second.__aenter__()
        await first.__aexit__(None, None, None)
        run = first_app.state.catalog_control_db.list_sync_runs("daily_pipeline")[0]
        assert run.status == "failed"
        assert run.finished_at is not None
        assert run.error_code == "control_plane_owner_shutdown"
        assert run.error_message == "control-plane owner shutdown"
        assert second_app.state.catalog_control_db.list_sync_runs("daily_pipeline") == []

        # The legacy job remains owned by its worker and may still finish normally;
        # its late callback must not redirect or reopen the absorbed SQLite run.
        store.complete(job_id, {"quality": {"ok": True}})
        assert (
            first_app.state.catalog_control_db.list_sync_runs("daily_pipeline")[0].status
            == "failed"
        )

        await second.__aexit__(None, None, None)

    asyncio.run(scenario())
