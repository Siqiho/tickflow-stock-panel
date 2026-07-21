from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI

from app import main
from app.services.pipeline_jobs import JobStore


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
