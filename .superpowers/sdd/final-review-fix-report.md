# Final review fix report

Date: 2026-07-21
Baseline: `cdc99c0`
Scope: final-review findings A-G only; no provider expansion, live-data mutation, deployment, or cutover.

## Outcome

All three Critical and four Important findings are closed in the isolated M0-M4 worktree.

- A — Refresh/invalidation: pipeline terminal states refresh the full catalog; the instruments operation refreshes only `stock_instruments`; index writers refresh only `index_instruments`, `index_daily`, and `index_enriched`; destructive clear performs a serialized post-delete full refresh before returning. Frontend pipeline/clear invalidates the `data-catalog` prefix, while index sync invalidates only the three related dataset detail/schema/run keys plus catalog root/status/global runs.
- B — Schema admission: every fixed dataset has an explicit required writer schema; `ext_data` is explicitly `opaque_dynamic`; descriptors expose persisted semantic columns rather than invented wide schemas. Stock enriched has its three stock-only fields, while ETF/index enriched expose only their actual 11-column persisted shape.
- C — Stable scans/concurrency: Parquet metadata, selected values, and SHA-256 are read through one open file descriptor. Device/inode/size/mtime are checked before and after reading and against the final path. A non-blocking public rescan mutex yields stable HTTP 409 detail; writer-triggered refreshes serialize and cannot be silently lost behind a manual rescan.
- D — Runtime entitlements: catalog entitlement is derived from the detected `CapabilitySet` through explicit operation-to-capability mappings. Public/local manifests are allowed; unknown providers and unknown TickFlow operations fail closed.
- E — Unit/lineage/depth truth: lineage is admitted only when its canonical target matches a materialized artifact. Missing lineage stays `unknown`; mismatched unit versions fail admission. Sealed seven-column summaries always persist under `sealed_l1` with `sealed_l1_v1`; only true level-5 shapes can set `depth5_available`.
- F — Lifespan ordering/cleanup: catalog initialization is the startup gate before schedulers/pollers. Its outer `try/finally` immediately covers all later setup; partial startup performs independent best-effort resource cleanup and always exits the catalog scope.
- G — Run monotonicity/ownership: SQLite run transitions are monotonic (`pending -> running -> terminal`) and terminal states absorb late callbacks. Exiting an owner synthesizes `failed/control_plane_owner_shutdown` for its in-flight control-plane runs without changing the legacy JSON job, and late legacy completion cannot reopen or redirect that run.

Catalog refreshes do not recursively trigger the pipeline sink: catalog rescans write directly to `CatalogControlDB`; only `JobStore` lifecycle callbacks invoke the sink. Pipeline legacy terminal JSON is persisted before the refresh callback, and refresh exceptions are caught and tested not to change either the legacy terminal or the already-written pipeline terminal run.

## Schema evidence used

The admission contracts were matched against the read-only M0 backup under `/Users/simon/备份/codex/20260721-152226-one-trading-data-platform-baseline/data` and current writers. Key shapes include canonical daily 8 columns, stock enriched 14, ETF/index enriched 11, stock instruments 13, ETF/index instruments 4, adjustment factors 3 with coverage sidecars excluded, sealed L1 7, pools 6, dynamic external tables, and the five financial table conventions (`notice_date` or shares `announce_date`, `total_revenue`, `netcash_operate`). The scan did not modify the backup.

## TDD evidence

RED was observed before each implementation group:

- B/C/E: 7 focused failures (missing schema contracts, descriptor drift, real-writer rejection, corrupt-schema false healthy, unscoped lineage, replace race, sealed summary written as depth5).
- Scan publication/retention: 2 failures and 1 pass before retaining the previous good snapshot and adding the rescan mutex.
- Rescan API: concurrent rescan exception escaped before stable HTTP 409 mapping.
- D/F: 2 capability failures; catalog ordering failed before it became the startup gate. A later-setup failure regression was added to prove cleanup reaches catalog exit.
- G: 2 failures before terminal absorption and owner-exit abortion.
- A backend: 6 failures before pipeline/index/clear refresh hooks.
- A frontend: 3 failures before full-prefix versus index-scoped invalidation.
- Descriptor scope: 1 failure before removing stock-only persisted fields from ETF/index descriptors.

GREEN commands/results:

- `backend/.venv/bin/pytest -q backend/tests/data_catalog backend/tests/test_depth_catalog_contract.py` — **87 passed**.
- `backend/.venv/bin/ruff check backend/app/data_catalog backend/tests/data_catalog backend/tests/test_depth_catalog_contract.py` — **all checks passed**.
- `pnpm run test:run` — **38 passed**.
- `pnpm run lint` — **0 errors**, 36 pre-existing repository warnings outside touched Data files.
- `pnpm run build` — **passed**; existing Vite chunk/dynamic-import warnings remain.
- `git diff --check` — **passed**.

Full backend result: `backend/.venv/bin/pytest -q` produced **216 passed, 2 failed**. Both failures are pre-existing data-dependent tests in this isolated worktree, which has no local sample financial/instrument dataset: `test_financial_normalize.py::test_local_ready_and_rows` and `test_financial_p1.py::test_shares_snapshot_from_instruments`. Neither failure touches the final-review code paths; the complete focused catalog/depth suite is green.

Targeted Ruff is green for all new/catalog files. The five touched legacy modules (`api/data.py`, `api/indices.py`, `main.py`, `services/depth_service.py`, `services/pipeline_jobs.py`) retain their pre-existing file-level Ruff baseline (97 diagnostics in the combined invocation); no diagnostic points to a line added by this fix.

## Files and risk boundary

Implementation is limited to catalog definitions/scanner/service/control DB/API, runtime lifespan/job mirroring, the existing data/index/depth writer hooks, and Data-page query invalidation plus focused tests. No live runtime was started, no user data was changed, no backup was created, and no upstream/provider/deployment scope was added.
