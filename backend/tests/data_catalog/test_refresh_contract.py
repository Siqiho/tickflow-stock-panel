from __future__ import annotations

import asyncio
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import FastAPI

from app import main
from app.api import data as data_api
from app.api import indices as index_api
from app.services.pipeline_jobs import JobStore
from app.tickflow import policy
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


def test_real_index_instrument_sync_defaults_to_persisting_index_and_etf(
    monkeypatch,
) -> None:
    writes: list[str] = []

    class Repo:
        def save_index_instruments(self, frame) -> None:
            assert frame["asset_type"].to_list() == ["index"]
            writes.append("index_instruments")

        def save_etf_instruments(self, frame) -> None:
            assert frame["asset_type"].to_list() == ["etf"]
            writes.append("etf_instruments")

        def refresh_index_views(self) -> None:
            writes.append("views")

    def fetch(instrument_type, asset_type_label):
        return pl.DataFrame(
            {
                "symbol": ["000001.SH" if instrument_type == "index" else "510300.SH"],
                "name": [instrument_type],
                "code": ["000001" if instrument_type == "index" else "510300"],
                "asset_type": [asset_type_label],
            }
        )

    monkeypatch.setattr(index_api.index_sync, "_fetch_instruments_by_type", fetch)
    monkeypatch.setattr(policy, "detect_capabilities", lambda force=False: CapabilitySet({}))

    assert index_api.index_sync.sync_index_instruments(Repo()) == 2
    assert writes == ["index_instruments", "etf_instruments", "views"]


def test_index_sync_refreshes_only_its_written_catalog_datasets(monkeypatch) -> None:
    scans: list[str | None] = []
    written_datasets: list[str] = []
    catalog = SimpleNamespace(
        refresh_after_mutation=lambda dataset_id=None: scans.append(dataset_id)
    )

    class Repo:
        def save_index_instruments(self, frame) -> None:
            written_datasets.append("index_instruments")

        def save_etf_instruments(self, frame) -> None:
            written_datasets.append("etf_instruments")

        def refresh_index_views(self) -> None:
            return None

    repo = Repo()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                repo=repo,
                catalog_service=catalog,
                capabilities=CapabilitySet({Cap.KLINE_DAILY_BATCH: CapabilityLimits()}),
            )
        )
    )

    def fetch(instrument_type, asset_type_label):
        return pl.DataFrame(
            {
                "symbol": ["000001.SH" if instrument_type == "index" else "510300.SH"],
                "name": [instrument_type],
                "code": ["000001" if instrument_type == "index" else "510300"],
                "asset_type": [asset_type_label],
            }
        )

    def sync_daily(*args, **kwargs):
        written_datasets.extend(["index_daily", "index_enriched"])
        return 20

    monkeypatch.setattr(index_api.index_sync, "_fetch_instruments_by_type", fetch)
    monkeypatch.setattr(policy, "detect_capabilities", lambda force=False: CapabilitySet({}))
    monkeypatch.setattr(
        index_api.index_sync,
        "sync_and_persist_index_daily",
        sync_daily,
    )

    assert index_api.sync_index_instruments(request) == {"status": "ok", "count": 2}
    assert scans == written_datasets == ["index_instruments", "etf_instruments"]
    scans.clear()
    written_datasets.clear()

    assert index_api.sync_index_daily(request, days=30) == {
        "status": "ok",
        "index_count": 2,
        "rows_written": 20,
    }
    assert scans == written_datasets == [
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
    f10_artifact = tmp_path / "f10" / "stock_margin_trading" / "part.parquet"
    f10_artifact.parent.mkdir(parents=True)
    f10_artifact.write_bytes(b"old-f10")

    class Catalog:
        serving_ready = True

        def refresh_after_mutation(self, dataset_id=None):
            assert dataset_id is None
            assert not artifact.exists()
            assert not f10_artifact.exists()
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

    assert data_api.clear_data(request) == {"deleted_files": 2}
    assert catalog.serving_ready is False
