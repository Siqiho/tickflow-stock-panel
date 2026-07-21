# Task 5 report: catalog API and pipeline control-plane mirroring

## Status

`DONE_WITH_CONCERNS`

The FastAPI catalog endpoints, catalog-backed compatibility status, lifespan control-plane setup, and opt-in daily/instruments pipeline run mirroring are implemented and committed. The complete backend suite has two known fixture-dependent failures because this isolated linked worktree intentionally has no local financial/instruments data fixture; no live data, provider, network endpoint, or development port was accessed.

## TDD record

### RED

Command (from `backend/`):

```sh
.venv/bin/pytest -q tests/data_catalog/test_api.py tests/test_pipeline_quality_status.py
```

Exit code: `2`.

Expected failure: collection stopped with `ModuleNotFoundError: No module named 'app.data_catalog.api'`. This showed the new catalog HTTP surface did not yet exist. A preliminary bare `pytest` command was unavailable on `PATH`; the project-local `.venv/bin/pytest` was then used for the recorded RED run.

### GREEN and focused regression

```sh
.venv/bin/pytest -q tests/data_catalog/test_api.py tests/test_pipeline_quality_status.py
# exit 0: 12 passed in 0.38s

.venv/bin/pytest -q tests/data_catalog/test_api.py tests/data_catalog/test_service.py tests/test_pipeline_quality_status.py
# exit 0: 21 passed in 0.39s

.venv/bin/pytest -q tests/data_catalog tests/test_pipeline_quality_status.py
# exit 0: 64 passed in 0.57s
```

Coverage includes catalog list/detail/schema/runs, stable catalog-unavailable and unknown-dataset errors, failed rescan retention with `stale=true`, old status top-level shape, succeeded/degraded/failed transitions, no progress-tick mirroring, and sink-failure isolation.

## Static and diff checks

```sh
.venv/bin/ruff check app/data_catalog/api.py app/data_catalog/service.py tests/data_catalog/test_api.py
# exit 0: All checks passed

.venv/bin/python -m compileall -q app/data_catalog/api.py app/api/data.py app/api/pipeline.py app/jobs/daily_pipeline.py app/main.py app/services/pipeline_jobs.py
# exit 0

git diff --check
# exit 0
```

An initial diagnostic Ruff pass over every touched legacy module exited `1` with 129 findings, predominantly existing whole-file Unicode/comment/style violations in `app/api/data.py`, `app/jobs/daily_pipeline.py`, and `app/main.py`; it is not a Task 5 behavior failure. Task 5's new API/test modules pass targeted Ruff. Import-order violations introduced at the `main.py` import block were fixed.

## Complete backend suite

```sh
.venv/bin/pytest -q
```

Exit code: `1`; `188 passed`, `2 failed`, `1 warning` in `6.81s`.

Failures:

- `tests/test_financial_normalize.py::test_local_ready_and_rows`: `local_financials_ready(settings.data_dir)` is false because the linked worktree data directory has no financial fixture.
- `tests/test_financial_p1.py::test_shares_snapshot_from_instruments`: the derived shares frame has zero rows because the linked worktree has no instruments fixture.

The warning is a pre-existing Polars sortedness warning in `tests/free_sources/test_adj_factor_public.py::test_pipeline_formula_matches_cumulative`.

## Changed files

- `backend/app/data_catalog/api.py`
- `backend/app/data_catalog/service.py`
- `backend/app/services/pipeline_jobs.py`
- `backend/app/main.py`
- `backend/app/api/data.py`
- `backend/app/api/pipeline.py`
- `backend/app/jobs/daily_pipeline.py`
- `backend/tests/data_catalog/test_api.py`
- `backend/tests/test_pipeline_quality_status.py`

## Commit

Task 5 implementation commit: `87be2442b55f52d6868030209e10ef56a6e2cdbe` (`feat(data-catalog): expose control plane and mirror pipeline runs`).

## Self-review

- Catalog GET handlers use only `CatalogService` hot methods and reply `503` when that service is absent; they do not fall back to filesystem/DuckDB status scans.
- Rescan failure persists a failed run, retains the last SQLite snapshot, and explicitly returns it as stale.
- Status retains its existing top-level key set, overlays APScheduler next-run values, and reads last pipeline/instruments completion only from mirrored SQLite runs.
- `JobStore` keeps old JSON behavior, only mirrors jobs explicitly marked by the manual daily pipeline and scheduled daily/instruments callers, and catches/logs sink errors after legacy state has been updated.
- Lifespan initializes the control plane after the store/capabilities, scans only if no dataset state exists, and clears the global sink at shutdown.

## Concerns

- Full-suite completion remains blocked only by intentionally absent local financial/instruments fixtures; no fixture was copied from a real data directory because Task 5 forbids that scope.
- Broader legacy-file Ruff cleanliness is outside this narrow Task 5 change. The new catalog API and its tests pass targeted Ruff.
