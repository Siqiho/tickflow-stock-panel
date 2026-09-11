from __future__ import annotations

import asyncio
import inspect
import os
import threading
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


def _force_normal_lifespan_mode(monkeypatch) -> None:
    """These nodes assert production startup fail-fast, not fixture skip."""
    monkeypatch.delenv("ONE_TRADING_DISABLE_BACKGROUND", raising=False)
    os.environ.pop("ONE_TRADING_DISABLE_BACKGROUND", None)


def test_main_lifespan_closes_catalog_when_later_setup_fails(tmp_path, monkeypatch) -> None:
    events: list[str] = []
    _force_normal_lifespan_mode(monkeypatch)

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

        def set_app_state(self, app_state) -> None:
            raise AssertionError("boot_check failure must run before set_app_state")

        def stop(self, *, persist: bool = True) -> None:
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


def test_fixture_mode_skips_boot_check_and_still_yields(tmp_path, monkeypatch) -> None:
    """DISABLE_BACKGROUND must not call boot_check (it can start polling)."""
    events: list[str] = []
    monkeypatch.setenv("ONE_TRADING_DISABLE_BACKGROUND", "1")
    os.environ["ONE_TRADING_DISABLE_BACKGROUND"] = "1"

    class PullScheduler:
        def start(self, data_dir) -> None:
            events.append("pull-start")

        def refresh(self, data_dir) -> None:
            events.append("pull-refresh")

        def stop(self) -> None:
            events.append("pull-stop")

    class FinancialScheduler:
        def start(self, data_dir, capset) -> None:
            events.append("financial-start")

        def stop(self) -> None:
            events.append("financial-stop")

    _stub_main_startup_through_scheduler_registration(
        tmp_path, monkeypatch, events, PullScheduler(), FinancialScheduler()
    )

    class FixtureQuoteService:
        def set_repo(self, repo) -> None:
            return None

        def boot_check(self) -> None:
            events.append("quote-boot")
            raise RuntimeError("fixture mode must not start realtime")

        def set_app_state(self, state) -> None:
            events.append("quote-state")

        def stop(self, *, persist: bool = True) -> None:
            events.append("quote-stop")

    monkeypatch.setattr(main, "QuoteService", FixtureQuoteService)

    async def scenario() -> None:
        async with main.lifespan(FastAPI()):
            events.append("yielded")

    asyncio.run(scenario())

    assert "quote-boot" not in events
    assert "pull-start" not in events
    assert "pull-refresh" not in events
    assert "financial-start" not in events
    assert "yielded" in events
    assert "quote-state" in events


def _stub_main_startup_through_scheduler_registration(
    tmp_path, monkeypatch, events, pull_scheduler, financial_scheduler
) -> None:
    from app.services import auth, depth_service, ext_presets, ext_pull, financial_sync
    from app.strategy import monitor

    class StubStore:
        def __init__(self) -> None:
            self.data_dir = tmp_path / "data"

    class StubRepo:
        def __init__(self, store) -> None:
            self.store = store

        def refresh_cache(self) -> None:
            return None

    class StubQuoteService:
        def set_repo(self, repo) -> None:
            return None

        def boot_check(self) -> None:
            return None

        def set_app_state(self, state) -> None:
            return None

        def stop(self) -> None:
            events.append("quote-stop")

    class StubDepthService:
        def set_repo(self, repo) -> None:
            return None

        def set_app_state(self, state) -> None:
            return None

        def boot_check(self) -> None:
            return None

        def start_polling(self) -> None:
            return None

        def stop_polling(self) -> None:
            events.append("depth-stop")

    class StubScheduler:
        def shutdown(self, *, wait) -> None:
            events.append("scheduler-stop")

    @asynccontextmanager
    async def control_scope(*args, **kwargs):
        events.append("catalog-enter")
        try:
            yield
        finally:
            events.append("catalog-exit")

    async def ensure_presets(data_dir) -> None:
        return None

    monkeypatch.setattr(auth, "bootstrap_from_env", lambda: None)
    monkeypatch.setattr(main, "DataStore", StubStore)
    monkeypatch.setattr(main, "KlineRepository", StubRepo)
    monkeypatch.setattr(main, "QuoteService", StubQuoteService)
    monkeypatch.setattr(main, "detect_capabilities", CapabilitySet)
    monkeypatch.setattr(main, "catalog_control_plane_lifespan", control_scope)
    monkeypatch.setattr(monitor, "StrategyMonitorService", object)
    monkeypatch.setattr(depth_service, "DepthService", StubDepthService)
    monkeypatch.setattr(main.daily_pipeline, "set_app_state", lambda state: None)
    monkeypatch.setattr(
        main.daily_pipeline, "start_scheduler", lambda repo, capset: StubScheduler()
    )
    monkeypatch.setattr(ext_pull, "pull_scheduler", pull_scheduler)
    monkeypatch.setattr(ext_presets, "ensure_builtin_presets", ensure_presets)
    monkeypatch.setattr(financial_sync, "financial_scheduler", financial_scheduler)


def test_pull_scheduler_is_stopped_when_refresh_raises_during_startup(
    tmp_path, monkeypatch
) -> None:
    events: list[str] = []
    _force_normal_lifespan_mode(monkeypatch)

    class PullScheduler:
        def start(self, data_dir) -> None:
            events.append("pull-start")

        def refresh(self, data_dir) -> None:
            events.append("pull-refresh")
            raise RuntimeError("pull refresh failed")

        def stop(self) -> None:
            events.append("pull-stop")

    class FinancialScheduler:
        def start(self, data_dir, capset) -> None:
            raise AssertionError("financial startup must not be reached")

        def stop(self) -> None:
            events.append("financial-stop")

    _stub_main_startup_through_scheduler_registration(
        tmp_path, monkeypatch, events, PullScheduler(), FinancialScheduler()
    )

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="pull refresh failed"):
            async with main.lifespan(FastAPI()):
                raise AssertionError("startup failure must prevent yield")

    asyncio.run(scenario())

    assert events.count("pull-stop") == 1
    assert events.index("pull-refresh") < events.index("pull-stop") < events.index("catalog-exit")


def test_financial_scheduler_is_stopped_when_start_raises(tmp_path, monkeypatch) -> None:
    events: list[str] = []
    _force_normal_lifespan_mode(monkeypatch)

    class PullScheduler:
        def start(self, data_dir) -> None:
            return None

        def refresh(self, data_dir) -> None:
            return None

        def stop(self) -> None:
            events.append("pull-stop")

    class FinancialScheduler:
        def start(self, data_dir, capset) -> None:
            events.append("financial-start")
            raise RuntimeError("financial start failed")

        def stop(self) -> None:
            events.append("financial-stop")

    _stub_main_startup_through_scheduler_registration(
        tmp_path, monkeypatch, events, PullScheduler(), FinancialScheduler()
    )

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="financial start failed"):
            async with main.lifespan(FastAPI()):
                raise AssertionError("startup failure must prevent yield")

    asyncio.run(scenario())

    assert events.count("financial-stop") == 1
    assert events.index("financial-start") < events.index("financial-stop")
    assert events.index("financial-stop") < events.index("catalog-exit")


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


def _assert_terminal_owner_race_is_absorbed(tmp_path, terminal_method, iteration) -> None:
    store = JobStore(store_dir=tmp_path / f"jobs-{terminal_method}-{iteration}")
    mirrored_statuses: list[str] = []

    def capture_status(payload) -> None:
        mirrored_statuses.append(payload["status"])

    token = store.set_control_plane_sink(capture_status)
    job_id = store.create(mirror={"dataset_id": "daily_pipeline", "operation": "daily"})
    store.start(job_id)

    terminal_ready = threading.Barrier(2)
    allow_terminal_notify = threading.Event()
    original_notify = store._notify_control_plane

    def paused_notify(job, mirror, owner_token, *, lock_held=False):
        if job["status"] in {"succeeded", "degraded", "failed"}:
            terminal_ready.wait(timeout=2)
            assert allow_terminal_notify.wait(timeout=2)
        if lock_held:
            return original_notify(job, mirror, owner_token, lock_held=True)
        return original_notify(job, mirror, owner_token)

    store._notify_control_plane = paused_notify  # type: ignore[method-assign]

    def finish_terminal() -> None:
        if terminal_method == "succeed":
            store.succeed(job_id, {"quality": {"ok": True}})
        elif terminal_method == "degrade":
            store.degrade(job_id, {"quality": {"ok": False}})
        else:
            store.fail(job_id, "worker failed")

    terminal = threading.Thread(target=finish_terminal)
    terminal.start()
    terminal_ready.wait(timeout=2)

    clear_started = threading.Event()
    clear_done = threading.Event()

    def clear_owner() -> None:
        clear_started.set()
        store.clear_control_plane_sink(token)
        clear_done.set()

    clearer = threading.Thread(target=clear_owner)
    clearer.start()
    assert clear_started.wait(timeout=1)
    assert not clear_done.wait(timeout=0.05)
    allow_terminal_notify.set()
    terminal.join(timeout=2)
    clearer.join(timeout=2)

    assert not terminal.is_alive()
    assert not clearer.is_alive()
    expected_status = {
        "succeed": "succeeded",
        "degrade": "degraded",
        "fail": "failed",
    }[terminal_method]
    assert mirrored_statuses[-1] == expected_status


@pytest.mark.parametrize("terminal_method", ["succeed", "degrade", "fail"])
def test_terminal_and_owner_shutdown_race_always_emits_a_terminal_callback(
    tmp_path, terminal_method
) -> None:
    for iteration in range(10):
        _assert_terminal_owner_race_is_absorbed(tmp_path, terminal_method, iteration)
