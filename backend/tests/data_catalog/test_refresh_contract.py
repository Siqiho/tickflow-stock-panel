from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from app import main
from app.api import data as data_api
from app.api import indices as index_api
from app.services.pipeline_jobs import JobStore
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet


@pytest.mark.parametrize("terminal", ["succeeded", "degraded", "failed"])
def test_pipeline_terminal_refreshes_the_full_local_catalog(
    tmp_path, monkeypatch, terminal
) -> None:
    scans: list[str | None] = []

    def record_rescan(self, dataset_id=None):
        scans.append(dataset_id)
        return self.list_catalog()

    monkeypatch.setattr(main.CatalogService, "refresh_after_mutation", record_rescan)
    store = JobStore(store_dir=tmp_path / "jobs")
    app = FastAPI()

    async def scenario() -> None:
        async with main.catalog_control_plane_lifespan(
            app, tmp_path / "data", job_store_instance=store
        ):
            job_id = store.create(
                mirror={"dataset_id": "daily_pipeline", "operation": "daily_pipeline"}
            )
            store.start(job_id)
            if terminal == "succeeded":
                store.succeed(job_id, {"quality": {"ok": True}})
            elif terminal == "degraded":
                store.degrade(job_id, {"quality": {"ok": False}})
            else:
                store.fail(job_id, "partial writer failure")
            assert scans == [None]

    asyncio.run(scenario())


def test_instruments_pipeline_terminal_refreshes_only_stock_instruments(
    tmp_path, monkeypatch
) -> None:
    scans: list[str | None] = []

    def record_rescan(self, dataset_id=None):
        scans.append(dataset_id)
        return self.list_catalog()

    monkeypatch.setattr(main.CatalogService, "refresh_after_mutation", record_rescan)
    store = JobStore(store_dir=tmp_path / "jobs")

    async def scenario() -> None:
        async with main.catalog_control_plane_lifespan(
            FastAPI(), tmp_path / "data", job_store_instance=store
        ):
            job_id = store.create(
                mirror={"dataset_id": "daily_pipeline", "operation": "instruments"}
            )
            store.start(job_id)
            store.succeed(job_id, {"instruments_rows": 1})
            assert scans == ["stock_instruments"]

    asyncio.run(scenario())


def test_pipeline_refresh_failure_cannot_change_the_persisted_legacy_terminal(
    tmp_path, monkeypatch
) -> None:
    def fail_refresh(self, dataset_id=None):
        raise RuntimeError("catalog unavailable")

    monkeypatch.setattr(main.CatalogService, "refresh_after_mutation", fail_refresh)
    store = JobStore(store_dir=tmp_path / "jobs")
    app = FastAPI()

    async def scenario() -> None:
        async with main.catalog_control_plane_lifespan(
            app, tmp_path / "data", job_store_instance=store
        ):
            job_id = store.create(
                mirror={"dataset_id": "daily_pipeline", "operation": "daily_pipeline"}
            )
            store.start(job_id)
            store.succeed(job_id, {"quality": {"ok": True}})

            assert store.get(job_id)["status"] == "succeeded"
            assert (
                app.state.catalog_control_db.get_sync_run(f"pipeline-{job_id}").status
                == "succeeded"
            )

    asyncio.run(scenario())


def test_index_sync_refreshes_only_its_written_catalog_datasets(monkeypatch) -> None:
    scans: list[str | None] = []
    instrument_calls: list[tuple[bool, bool]] = []
    catalog = SimpleNamespace(
        refresh_after_mutation=lambda dataset_id=None: scans.append(dataset_id)
    )
    repo = SimpleNamespace(etf_instruments_written=False)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                repo=repo,
                catalog_service=catalog,
                capabilities=CapabilitySet({Cap.KLINE_DAILY_BATCH: CapabilityLimits()}),
            )
        )
    )

    def sync_instruments(value, pull_index=True, pull_etf=True):
        instrument_calls.append((pull_index, pull_etf))
        value.etf_instruments_written = pull_etf
        return 2

    monkeypatch.setattr(index_api.index_sync, "sync_index_instruments", sync_instruments)
    monkeypatch.setattr(
        index_api.index_sync,
        "sync_and_persist_index_daily",
        lambda *args, **kwargs: 20,
    )

    assert index_api.sync_index_instruments(request) == {"status": "ok", "count": 2}
    assert instrument_calls == [(True, True)]
    assert repo.etf_instruments_written is True
    assert scans == ["index_instruments", "etf_instruments"]
    scans.clear()

    assert index_api.sync_index_daily(request, days=30) == {
        "status": "ok",
        "index_count": 2,
        "rows_written": 20,
    }
    assert instrument_calls == [(True, True), (True, True)]
    assert scans == [
        "index_instruments",
        "etf_instruments",
        "index_daily",
        "index_enriched",
    ]


def test_clear_rescans_after_deletion_so_old_serving_state_is_not_returned(
    tmp_path, monkeypatch
) -> None:
    artifact = tmp_path / "kline_daily" / "date=2026-07-21" / "part.parquet"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"old")

    class Catalog:
        serving_ready = True

        def refresh_after_mutation(self, dataset_id=None):
            assert dataset_id is None
            assert not artifact.exists()
            self.serving_ready = False

    class DB:
        def execute(self, *args, **kwargs) -> None:
            return None

    class Repo:
        store = SimpleNamespace(data_dir=tmp_path)
        db = DB()

        def clear_cache(self) -> None:
            return None

        def refresh_cache(self) -> None:
            return None

    from app.api import overview
    from app.services import alert_store, pipeline_jobs
    from app.services.screener import ScreenerService

    monkeypatch.setattr(pipeline_jobs.job_store, "clear", lambda: None)
    monkeypatch.setattr(alert_store, "clear", lambda data_dir: None)
    monkeypatch.setattr(ScreenerService, "clear_history_cache", lambda: None)
    monkeypatch.setattr(overview, "invalidate_overview_cache", lambda: None)
    catalog = Catalog()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(repo=Repo(), catalog_service=catalog, quote_service=None)
        )
    )

    assert data_api.clear_data(request) == {"deleted_files": 1}
    assert catalog.serving_ready is False
