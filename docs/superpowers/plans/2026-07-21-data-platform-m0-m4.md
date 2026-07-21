# one-trading Data Platform M0-M4 Implementation Plan

> **Execution mode:** use `superpowers:subagent-driven-development` task by task. Every feature and bug fix follows `superpowers:test-driven-development`; every task receives an independent spec-and-quality review before the next task starts.

**Goal:** Preserve the now-verified data-correctness work, then add a local SQLite-backed data catalog, explicit provider/unit contracts, and a stable `/data` workbench that separates local truth from provider/entitlement capability.

**Architecture:** Parquet remains the data plane. `data/control/catalog.sqlite3` becomes the small control plane for dataset state, runs, artifacts, source health, and cached storage facts. A catalog service merges immutable dataset definitions, provider manifests, local artifact facts, lineage, entitlement, and quality. Browser reads are local-only and use SQLite-backed APIs; only explicit sync actions may contact providers.

**Tech stack:** Python 3.13, FastAPI, Pydantic 2, stdlib SQLite, PyArrow/Polars, Pytest, React 18, TypeScript, TanStack Query, Vitest, React Testing Library, ESLint, pnpm/Vite.

## Execution checkpoint

- Isolated worktree: `/Users/simon/Trading/one-trading/.worktrees/data-platform-m0-m4-20260721`
- Branch: `codex/data-platform-m0-m4-20260721`
- Imported dirty-state baseline commit: `2dfe6ec36237ef449422e55fc504cfe3bc1f9c33`
- Source/data backup: `/Users/simon/备份/codex/20260721-152226-one-trading-data-platform-baseline`
- The user's dirty `main` checkout is not an implementation target and must remain untouched.

## M1 closure evidence already established

The existing correctness implementation is a precondition, not a rewrite task. On 2026-07-21 the isolated baseline passed:

- 23 focused tests covering public quote units, quote-snapshot isolation, realtime fallback, daily quality/degraded status, atomic I/O, provider semantics, and engineering closure.
- 116 complete backend tests (one pre-existing Polars sortedness warning).
- Frontend production build.
- No `.tmp-*` residue after focused atomic-publication tests.
- The baseline backup records current APIs, browser state, data bytes, data coverage, and restore instructions.

The final verification task repeats the complete suite after M2-M4, installs the missing frontend lint/test gate, and validates the real 3018/3011 runtime and browser surfaces. Repository-wide Ruff has 1,114 pre-existing diagnostics; the agreed gate is no new diagnostics in touched legacy files and zero diagnostics in new Python files, not an unrelated repository cleanup.

## Global constraints

- Scope is M0-M4 only. Do not add a new provider, buy/enable paid access, handle credentials, backfill history, migrate existing `job_store/*.json`, deploy, or begin M5-M8.
- Preserve all existing canonical Parquet paths, schemas, public APIs, and consumers unless this plan explicitly adds a compatible field or endpoint.
- SQLite stores control metadata only. It must never contain market rows.
- Catalog availability always keeps `provider_supported`, `entitled`, `local_materialized`, and `serving_ready` independent.
- Catalog hot reads and `/api/data/status` polling must use SQLite/in-memory scheduler state only; they must not rescan Parquet, run DuckDB aggregates, or make network calls.
- `POST /api/data/catalog/rescan` is the only catalog API that scans local files. It must never contact a remote provider. A dataset-specific rescan may touch only that dataset's owned paths and persisted artifact records.
- Every physical file contributes to storage totals at most once. Responses expose raw bytes as `managed_data_bytes`, `operational_bytes`, and `total_bytes`; the frontend formats but never reconstructs totals.
- Public sealed-limit L1 is `sealed_l1`, never `depth5`. `depth5` is visible only when the catalog explicitly reports `depth5_available=true`.
- A-share canonical units remain volume in lots, amount in CNY, ratio values in percentage points, daily dates in the market calendar, realtime time as UTC plus market timezone, and shares outstanding in shares.
- Unknown source volume/amount units are not publishable. Hong Kong/US assets must not inherit A-share lot/CNY rules.
- All formal lineage written by in-scope publication paths has a non-empty `unit_version`.
- New/changed behavior is test-first with recorded RED and GREEN evidence. New Python files must pass targeted Ruff. Changed legacy files must not add Ruff diagnostics.
- Frontend catalog code must pass Vitest, TypeScript/Vite build, and the new ESLint command. Avoid mass style cleanup outside touched files.
- Browser validation uses the Codex in-app browser only.

## Canonical catalog response contracts

The Python and TypeScript models must agree on these shapes:

```text
CatalogResponse
  datasets: DatasetCatalogEntry[]
  storage: StorageBreakdown
  refreshed_at: ISO-8601 | null
  stale: boolean

DatasetCatalogEntry
  descriptor: DatasetDescriptor
  state: DatasetState
  provider: string | null
  coverage: MarketCoverage[]
  lineage: LineageSummary[]
  depth5_available: boolean

StorageBreakdown
  managed_data_bytes: integer
  operational_bytes: integer
  total_bytes: integer
  categories: { key, title, kind, bytes, files }[]
```

Required static dataset IDs are:

```text
stock_instruments, stock_daily, stock_enriched, stock_minute, stock_adj_factor,
etf_instruments, etf_daily, etf_enriched, etf_minute, etf_adj_factor,
index_instruments, index_daily, index_enriched,
quote_snapshot, sealed_l1, depth5, pools, ext_data,
financial_metrics, financial_income, financial_balance_sheet,
financial_cash_flow, financial_shares
```

`depth5` and `sealed_l1` may inspect the existing physical `depth5` directory, but the scanner must assign each file to exactly one semantic dataset based on its schema/lineage. Ambiguous files default to `sealed_l1`, never true depth5.

### Exact Python model contract

Use these fields and types; later tasks may add methods/validators but must not silently rename the public fields:

```python
from typing import Any, Literal

QualityStatus = Literal["unknown", "healthy", "degraded", "failed"]
RunStatus = Literal["pending", "running", "succeeded", "degraded", "failed"]

class DatasetAvailability(BaseModel):
    provider_supported: bool = False
    entitled: bool = False
    local_materialized: bool = False
    serving_ready: bool = False
    reason_code: str | None = None

class FieldContract(BaseModel):
    name: str
    dtype: str
    semantic: str
    unit: str | None = None
    scale: str | None = None
    currency: str | None = None
    timezone: str | None = None
    nullable: bool

class DatasetDescriptor(BaseModel):
    dataset_id: str
    title: str
    asset_types: list[str]
    grain: str
    primary_key: list[str]
    partition_keys: list[str]
    schema_version: str
    unit_version: str
    point_in_time: bool
    adjustment: str | None = None
    availability: DatasetAvailability
    fields: list[FieldContract]

class DatasetState(BaseModel):
    dataset_id: str
    schema_version: str
    unit_version: str
    quality_status: QualityStatus = "unknown"
    row_count: int = 0
    symbol_count: int = 0
    expected_symbol_count: int | None = None
    earliest_time: str | None = None
    latest_time: str | None = None
    managed_bytes: int = 0
    last_run_id: str | None = None
    updated_at: str
    payload: dict[str, Any] = Field(default_factory=dict)

class MarketCoverage(BaseModel):
    market: Literal["SH", "SZ", "BJ", "OTHER"]
    symbol_count: int = 0
    expected_symbol_count: int | None = None
    ratio: float | None = None  # 0.0..1.0, None when denominator is unknown

class ArtifactRecord(BaseModel):
    run_id: str
    dataset_id: str
    path: str
    sha256: str
    row_count: int = 0
    bytes: int = 0
    partition_value: str | None = None
    published_at: str

class SyncRun(BaseModel):
    run_id: str
    dataset_id: str
    provider: str | None = None
    operation: str
    started_at: str | None = None
    finished_at: str | None = None
    status: RunStatus
    rows_fetched: int = 0
    rows_published: int = 0
    quality_status: QualityStatus = "unknown"
    error_code: str | None = None
    error_message: str | None = None

class SourceHealth(BaseModel):
    provider: str
    operation: str
    last_success_at: str | None = None
    last_failure_at: str | None = None
    consecutive_failures: int = 0
    cooldown_until: str | None = None
    last_error_code: str | None = None

class LineageSummary(BaseModel):
    run_id: str | None = None
    source: str
    fetched_at: str | None = None
    unit_version: str
    quality_status: QualityStatus = "unknown"
    scope: str | None = None
    artifact_path: str | None = None
    row_count: int | None = None

class StorageCategory(BaseModel):
    key: str
    title: str
    kind: Literal["managed", "operational"]
    bytes: int = 0
    files: int = 0

class StorageBreakdown(BaseModel):
    managed_data_bytes: int = 0
    operational_bytes: int = 0
    total_bytes: int = 0
    categories: list[StorageCategory] = Field(default_factory=list)

class DatasetCatalogEntry(BaseModel):
    descriptor: DatasetDescriptor
    state: DatasetState
    provider: str | None = None
    coverage: list[MarketCoverage] = Field(default_factory=list)
    lineage: list[LineageSummary] = Field(default_factory=list)
    depth5_available: bool = False

class CatalogResponse(BaseModel):
    datasets: list[DatasetCatalogEntry]
    storage: StorageBreakdown
    refreshed_at: str | None = None
    stale: bool = False
```

Non-negative counters/bytes are validated. Coverage ratios, when present, are within `[0, 1]`. `StorageBreakdown` validates `total_bytes == managed_data_bytes + operational_bytes` and the category byte total equals `total_bytes`.

### Exact internal definition contract

`DatasetDefinition` is a frozen dataclass with these fields:

```python
@dataclass(frozen=True)
class DatasetDefinition:
    descriptor: DatasetDescriptor          # availability is the all-false placeholder
    roots: tuple[str, ...]                  # paths relative to data_dir
    provider: str | None
    operation: str | None
    storage_category: str
    symbol_column: str | None = "symbol"
    time_column: str | None = None
    partition_key: str | None = None
    lineage_ids: tuple[str, ...] = ()
    semantic_classifier: Literal["default", "depth"] = "default"
    shared_root_group: str | None = None
```

All roots are exclusive. The only allowed duplicate root is `depth5`, shared by `sealed_l1` and `depth5` with `shared_root_group="depth_semantics"` and `semantic_classifier="depth"`. Root mapping is the existing canonical directory name: `instruments`, `kline_daily`, `kline_daily_enriched`, `kline_minute`, `adj_factor`; ETF equivalents use `instruments_etf`, `kline_etf_daily`, `kline_etf_enriched`, `kline_etf_minute`, `adj_factor_etf`; index equivalents use `instruments_index`, `kline_index_daily`, `kline_index_enriched`; then `quote_snapshot`, `depth5`, `pools`, `ext_data`, and `financials/{metrics,income,balance_sheet,cash_flow,shares}`.

Static registry validation requires: non-empty/unique dataset IDs; non-empty title, asset types, grain, schema/unit versions, primary key, and fields; unique field names inside each descriptor; valid roots; and no disallowed root overlap. Keep schema/unit versions at `"1"` / `"cn_market_v1"` for market datasets and use a truthful dataset-specific unit version for non-market reference/control data.

Definitions must contain the current canonical columns relevant to each dataset. At minimum: instrument identifiers/metadata; OHLCV/amount/change for bars; factor value for adjustment data; snapshot/depth price and volume semantics; pool constituent identity; and each financial table's identifying dates plus its representative monetary/share fields. Reuse helpers to avoid duplicating common field contracts. Stock/index/ETF enriched helpers may share technical field names, but their `semantic` text must explicitly name the correct asset class. `limit_up` and `limit_down` are nullable CNY price fields with no percentage scale.

---

## Task 1: Define catalog models and the static dataset registry

**Files:**

- Create: `backend/app/data_catalog/__init__.py`
- Create: `backend/app/data_catalog/models.py`
- Create: `backend/app/data_catalog/definitions.py`
- Create: `backend/tests/data_catalog/__init__.py`
- Create: `backend/tests/data_catalog/test_models.py`

**Interfaces:**

- Implement the required `DatasetAvailability`, `FieldContract`, and `DatasetDescriptor` Pydantic models exactly as specified by the total plan.
- Add typed models for persisted `DatasetState`, `MarketCoverage`, `ArtifactRecord`, `SyncRun`, `SourceHealth`, `LineageSummary`, `StorageCategory`, `StorageBreakdown`, `DatasetCatalogEntry`, and `CatalogResponse`.
- Keep storage-path ownership and scan metadata in an internal frozen `DatasetDefinition`, separate from the public descriptor.
- `definitions.py` exposes `DATASET_DEFINITIONS`, `get_dataset_definition(dataset_id)`, and a validation function that rejects duplicate IDs or overlapping exclusive roots.
- Define all required dataset IDs, including the five separate financial tables. Stock/index/ETF enriched definitions must use their own field descriptions instead of sharing misleading stock-only semantics.
- `limit_up` and `limit_down` field contracts use price/CNY semantics, never percentage semantics.

- [ ] Write failing tests for independent availability states, model validation, dataset ID uniqueness/completeness, five financial definitions including shares, limit price semantics, and distinct enriched descriptions.
- [ ] Run `pytest -q backend/tests/data_catalog/test_models.py` and capture the expected RED caused by the missing package/models.
- [ ] Implement the smallest models and registry that satisfy the tests.
- [ ] Run the focused test GREEN, targeted Ruff on all new files, then the complete backend suite once.
- [ ] Commit only Task 1 files.

---

## Task 2: Build the WAL SQLite control plane and migrations

**Files:**

- Create: `backend/app/data_catalog/control_db.py`
- Create: `backend/app/data_catalog/migrations/001_init.sql`
- Create: `backend/tests/data_catalog/test_control_db.py`

**Interfaces:**

- Database path is `<data_dir>/control/catalog.sqlite3`.
- Every connection enables `journal_mode=WAL`, `foreign_keys=ON`, and `busy_timeout=5000`.
- Migrations use `PRAGMA user_version`, execute transactionally, and make a timestamped pre-migration copy when an existing non-empty database will change. A brand-new empty database needs no meaningless backup.
- Implement transaction-safe repository operations for all four required tables: `dataset_state`, `sync_runs`, `artifacts`, and `source_health`.
- Dataset state and source health use deterministic upserts. Sync runs preserve start/terminal timestamps and error details. Artifact replacement for one dataset/run is atomic.
- Connections are short-lived and safe for FastAPI threadpool use; the class must not share one mutable cursor across threads.

- [ ] Write failing tests for schema/migration, PRAGMAs, state upsert/read, run lifecycle, artifacts, source health, pre-migration backup, rollback on invalid writes, and concurrent readers during a writer transaction.
- [ ] Verify RED before implementation.
- [ ] Implement migration loading, connection/transaction helpers, and repositories.
- [ ] Verify focused GREEN and confirm the concurrent read test completes without lock errors or a five-second stall.
- [ ] Run targeted Ruff and the complete backend suite once, then commit Task 2.

---

## Task 3: Add provider manifests and enforce unit contracts at provider boundaries

**Files:**

- Create: `backend/app/data_providers/unit_contracts.py`
- Modify: `backend/app/data_providers/base.py`
- Modify: `backend/app/data_providers/normalizer.py`
- Modify: `backend/app/data_providers/public_provider.py`
- Modify: `backend/app/data_providers/tickflow_provider.py`
- Modify: `backend/app/data_providers/registry.py`
- Modify as required for lineage enforcement: `backend/app/services/atomic_io.py`, current `write_lineage_record` call sites, and their focused tests
- Create: `backend/tests/test_unit_contracts.py`
- Modify: `backend/tests/test_provider_registry.py`
- Modify: `backend/tests/test_atomic_io.py`

**Interfaces:**

- Define the exact literals `VolumeUnit`, `AmountUnit`, `RatioScale`, and `TimestampUnit` from M3.
- Define an A-share canonical contract (`lot`, `CNY`, `percentage_point`, market date, UTC realtime plus `Asia/Shanghai`, shares in `share`) without applying it to non-CN markets.
- Add Pydantic `ProviderDatasetManifest` while retaining `ProviderCapabilities` unchanged for current consumers.
- Each provider exposes manifests per dataset/operation. Undocumented TickFlow/DigiPool source units are `unknown`; do not infer them from names or current values.
- Provider-boundary normalization converts TickFlow ratio fractions so `0.01` becomes `1.0` percentage point when and only when the manifest says `fraction -> percentage_point`.
- Publishing validation rejects unknown volume/amount units, and rejects non-CN assets that attempt to use the A-share canonical lot/CNY contract.
- Sealed L1 and true depth5 manifests describe their volume units independently. Financial monetary fields expose both currency and scale.
- `write_lineage_record` rejects/does not emit a formal record without `unit_version`; update all existing in-scope call sites and tests to provide it.
- No paid sample call is made. Fixture tests are the admission evidence for this batch.

- [ ] Write failing manifest/unit tests first: fraction conversion, unknown-unit rejection, non-CN rejection, independent L1/depth units, finance currency/scale, and missing lineage unit version.
- [ ] Verify RED.
- [ ] Implement unit contracts, manifests, registry access, guarded normalization, and lineage enforcement.
- [ ] Run provider, quote, depth, finance-normalization, atomic-I/O, and new unit tests GREEN.
- [ ] Run targeted Ruff and the complete backend suite once, then commit Task 3.

---

## Task 4: Implement the local scanner and SQLite-backed catalog service

**Files:**

- Create: `backend/app/data_catalog/scanner.py`
- Create: `backend/app/data_catalog/service.py`
- Create: `backend/tests/data_catalog/test_scanner.py`
- Create: `backend/tests/data_catalog/test_service.py`

**Interfaces:**

- Full rescan walks local `data_dir` once, assigns every regular file to one storage category, persists artifact/state facts, and verifies `total_bytes == sum(stat().st_size for every regular file)`.
- Storage kinds are `managed` and `operational`; categories include stocks, ETFs, indices, quote snapshot, sealed L1, true depth5, pools, financials, ext data, lineage, job store, logs, user data, and SQLite control files.
- Scanner stores raw bytes and file counts. It may use Parquet metadata/lazy column scans only during rescan to obtain rows, symbols, dates, schema, and SH/SZ/BJ coverage.
- Dataset-specific rescan reads only its owned roots, replaces only its artifact/state records, and leaves unrelated dataset facts unchanged.
- Files under the physical `depth5` path are classified as true depth5 only when schema/lineage proves bid/ask levels 1-5; otherwise they belong to `sealed_l1`.
- Service merges definitions, provider manifests/entitlement, local state, quality, and lineage. `local_materialized=true` does not imply `serving_ready=true`; failed/degraded quality preserves that distinction with a reason code.
- Hot methods (`list_catalog`, `get_dataset`, `get_schema`, `list_runs`, `compatibility_status`) read SQLite only. They do not call `Path.rglob`, PyArrow/Polars, DuckDB, or a network client.
- `compatibility_status` preserves the existing `/api/data/status` top-level and nested storage keys while sourcing values from cached states.

- [ ] Write failing scanner tests using small real Parquet fixtures: exact byte totals/no duplicates, stock/index/ETF separation, shares table, L1-vs-depth schema, coverage, and dataset-specific refresh isolation.
- [ ] Write failing service tests for the four independent availability flags, local-but-quality-failed behavior, hot-read no-filesystem guarantee, and unchanged legacy status key shape.
- [ ] Verify RED before implementation.
- [ ] Implement scanner and service with no network path.
- [ ] Run focused GREEN; assert a warmed catalog query is under 200ms in the fixture test without a brittle machine-wide benchmark.
- [ ] Run targeted Ruff and the complete backend suite once, then commit Task 4.

---

## Task 5: Expose catalog APIs, initialize the control plane, and mirror new pipeline runs

**Files:**

- Create: `backend/app/data_catalog/api.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/data.py`
- Modify: `backend/app/services/pipeline_jobs.py`
- Create: `backend/tests/data_catalog/test_api.py`
- Modify: `backend/tests/test_pipeline_quality_status.py`

**Interfaces:**

- Add local-only endpoints:
  - `GET /api/data/catalog`
  - `GET /api/data/catalog/{dataset_id}`
  - `GET /api/data/catalog/{dataset_id}/schema`
  - `GET /api/data/runs?dataset_id=...`
  - `POST /api/data/catalog/rescan` with optional `dataset_id`
- Missing dataset IDs return 404 with a stable error detail. Rescan errors do not destroy the last successful catalog snapshot.
- Lifespan creates/migrates `CatalogControlDB`, constructs `CatalogService`, performs an initial local rescan only when no dataset state exists, and stores it on `app.state`. Shutdown closes no long-lived shared connection.
- Existing `GET /api/data/status` delegates to `CatalogService.compatibility_status`; scheduler next-run values may come from in-memory APScheduler, never a Parquet scan.
- Preserve `GET /api/data/schema/{table}` and all current `/api/data/status` response keys.
- Extend `JobStore` with an optional control-plane sink configured at startup. New pipeline job create/start/complete/degrade/fail transitions are mirrored to `sync_runs` under `dataset_id="daily_pipeline"`, while legacy JSON persistence/list/detail behavior stays compatible. Do not migrate old JSON files.
- Sink failures are logged and cannot make the legacy pipeline job fail.

- [ ] Write failing API tests for list/detail/schema/runs, 404, local-only rescan, rescan failure retaining prior state, catalog query without scan, and old status shape.
- [ ] Write failing job-mirror tests for succeeded/degraded/failed transitions and sink-failure isolation.
- [ ] Verify RED.
- [ ] Implement router, lifespan initialization, status delegation, and optional run sink.
- [ ] Run focused API/job tests GREEN, targeted Ruff, and the complete backend suite once.
- [ ] Commit Task 5.

---

## Task 6: Install the frontend quality gate and typed catalog client

**Files:**

- Modify: `frontend/package.json`
- Modify: `frontend/pnpm-lock.yaml`
- Create: `frontend/eslint.config.js`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/queryKeys.ts`
- Modify: `frontend/src/lib/useSharedQueries.ts`
- Create: `frontend/src/lib/__tests__/dataCatalog.test.tsx`

**Interfaces:**

- Add the minimal compatible dev dependencies for ESLint, TypeScript ESLint parsing, React hooks, Vitest, jsdom, React Testing Library, and jest-dom. Add `test`/`test:run` scripts without changing pnpm major version.
- ESLint covers `src/**/*.{ts,tsx}` and must pass the existing source tree without disabling parsing or all rules globally. Do not mass-reformat unrelated source.
- TypeScript types mirror the canonical catalog response contracts and run/detail/schema payloads.
- Add API methods for all catalog endpoints; `rescan` accepts optional `dataset_id` and is an explicit mutation.
- Add query keys for catalog list, detail, schema, and dataset/all runs.
- Add `useDataCatalog` using `placeholderData: keepPreviousData`, local polling, and a derived stale flag when a refetch fails while prior data exists. An initial error remains an inline error state, not an exception that blanks the route.

- [ ] Install dependencies and create the test harness/configuration.
- [ ] Write a failing hook/client test showing the last successful catalog remains visible with a stale flag after a later API failure.
- [ ] Verify RED, then implement the typed client, keys, and hook.
- [ ] Run `pnpm test --run`, `pnpm run lint`, and `pnpm run build` GREEN.
- [ ] Commit Task 6.

---

## Task 7: Build the catalog, availability, storage, lineage, and history components

**Files:**

- Create: `frontend/src/components/data/AvailabilityBadge.tsx`
- Create: `frontend/src/components/data/CoverageBar.tsx`
- Create: `frontend/src/components/data/DatasetCatalogCard.tsx`
- Create: `frontend/src/components/data/DatasetDetailDrawer.tsx`
- Create: `frontend/src/components/data/DataCatalogSection.tsx`
- Create: `frontend/src/components/data/StorageBreakdownCard.tsx`
- Create: `frontend/src/components/data/QualityLineagePanel.tsx`
- Create: `frontend/src/components/data/DatasetRunHistory.tsx`
- Create focused tests under: `frontend/src/components/data/__tests__/`

**Interfaces:**

- Components consume typed local catalog props; they perform no direct remote or provider request.
- Every dataset card shows title, asset/grain, the four independent availability states, rows, symbols, SH/SZ/BJ coverage, earliest/latest, updated time, quality, and raw-byte-formatted local size.
- Data catalog groups the five financial dataset entries visibly; `financial_shares` cannot be omitted.
- `quote_snapshot`, `sealed_l1`, and `pools` are first-class cards. `sealed_l1` is labeled `封板 L1`. A `depth5` card is rendered only when `depth5_available === true`.
- Detail drawer shows fields, dtype, semantic, unit, scale, currency, timezone, adjustment, primary key, point-in-time flag, provider, lineage, recent runs, and reason code.
- Storage card displays backend-provided managed/operational/total byte values. It never sums category bytes to invent the total.
- Stale/error handling preserves provided old data, shows `状态可能过期`, and never throws a render-time exception.
- Responsive layout has deliberate 375px single-column, 768px two-column where space permits, and 1280px multi-column behavior.

- [ ] Write failing RTL tests for the four availability badges, ETF/financial visibility, sealed-L1 wording and depth5 hiding, backend total-byte use, stale marker, all five finance tables, and unit/scale/currency/timezone rendering.
- [ ] Verify RED.
- [ ] Implement the focused components with accessible names/roles and existing design tokens.
- [ ] Run focused and full frontend tests, lint, and build GREEN.
- [ ] Commit Task 7.

---

## Task 8: Recompose `/data` into four explicit workbench regions

**Files:**

- Modify: `frontend/src/pages/Data.tsx`
- Modify: `frontend/src/components/data/PageSettingsModal.tsx`
- Modify focused frontend tests as needed

**Interfaces:**

- The rendered page has four explicit top-level regions in order:
  1. `数据系统状态`
  2. `数据集目录`
  3. `同步和维护操作`
  4. `同步历史与质量问题`
- Replace the old local-data capability inference cards with `DataCatalogSection`; preserve existing explicit sync/settings/clear operations in the maintenance region.
- ETF is visible by default in both catalog and any retained legacy visibility preference. Resetting page visibility settings must not hide ETF by default.
- System status uses `StorageBreakdownCard` and exposes managed, operational, total, control refresh time, and stale/error state.
- Catalog/detail/history use local catalog APIs only. Page entry/refetch never invokes an external source. Rescan is a clearly labeled manual local action.
- Sync completion invalidates only catalog/status/run keys relevant to the completed operation; do not clear the whole React Query cache. Card visibility affects rendering only.
- Existing public L1 copy says `封板 L1`; no package/tier label substitutes for local state. True depth wording follows catalog `depth5_available` only.
- API failures produce inline degraded/stale states; the rest of the Data route remains usable.

- [ ] Write or update failing integration tests for the four region headings, ETF default/reset behavior, stale old catalog on error, and no depth5 wording for sealed L1.
- [ ] Verify RED.
- [ ] Integrate components and reorganize the page without changing unrelated routes.
- [ ] Run all frontend tests, lint, and production build GREEN.
- [ ] Run targeted backend catalog/API tests once to catch cross-layer contract drift.
- [ ] Commit Task 8.

---

## Final verification and handoff (controller-owned)

- [ ] Inspect `git diff 2dfe6ec..HEAD`, commit list, status, and changed-path ownership; confirm the dirty main checkout remains unchanged.
- [ ] Run all backend tests. Run targeted Ruff for every changed/new Python file and compare touched legacy diagnostics with the agreed baseline; report the repository-wide 1,114 baseline separately.
- [ ] Run all frontend tests, ESLint, and production build.
- [ ] Copy the backed-up data into an isolated runtime `DATA_DIR`; never point destructive tests or rescan at the user's live data while developing.
- [ ] Initialize/rescan the isolated catalog twice; verify idempotence, database integrity, WAL/foreign-key/busy-timeout settings, exact byte accounting, no `.tmp-*`, and no unexpected data mutations.
- [ ] Start the actual branch runtime on isolated ports first; confirm PID, start time, source checkout, version, and bundle identity. Then use the agreed 3018/3011 target only when it can be switched safely.
- [ ] Verify `/health`, catalog list/detail/schema/runs/rescan, legacy status compatibility, warmed query latency, and runtime logs.
- [ ] In the Codex in-app browser verify Dashboard, Data, Financials, public minute fallback, sealed-L1 wording, degraded/failed history, stale catalog behavior, and 375/768/1280 widths.
- [ ] Confirm data bytes/row counts are unchanged except for the isolated SQLite control database and its WAL/SHM files.
- [ ] Record rollback: branch commits can be omitted; live data restore uses the M0 backup README and manifest.

## Deferred by design

- M5 history/data growth, M6 event/relationship datasets, M7 Agent query APIs, and M8 long-run storage/scheduling policy.
- Paid DigiPool/TickFlow live-sample admission until a valid entitled account is explicitly provided.
- Migration of existing `job_store/*.json` into SQLite.
- Deployment or production cutover.
