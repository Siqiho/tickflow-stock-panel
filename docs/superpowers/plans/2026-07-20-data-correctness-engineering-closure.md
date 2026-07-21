# Data Correctness and Engineering Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove public realtime unit corruption, make failed quality gates visible and blocking, restore a trustworthy 2026-07-20 partition, and then close the provider, durability, lineage, adjustment-factor, and financial retry gaps without adding new data sources.

**Architecture:** Public realtime data is normalized at the source boundary and persisted only as a lineage-rich quote snapshot; canonical end-of-day K-line partitions remain owned by the daily pipeline. Quality reports produce an explicit `succeeded` / `degraded` / `failed` terminal outcome. Shared atomic writers protect Parquet and JSON artifacts. Public sources are then exposed through typed provider capabilities rather than synthetic legacy keys.

**Tech Stack:** Python 3.13, FastAPI, Polars, DuckDB, Pytest, React 18, TypeScript, TanStack Query, pnpm/Vite.

## Global Constraints

- Primary project: `/Users/simon/Trading/one-trading`.
- Cross-layer scope: data platform is primary; frontend changes are limited to capability and job-state presentation.
- Do not add or evaluate new upstream data sources.
- Preserve existing canonical daily Parquet schema and page/API contracts unless a versioned replacement is introduced.
- Do not call a public L1 sealed snapshot `depth5` and do not call a public quote snapshot a TickFlow pool capability.
- Work in the current explicitly authorized dirty `main` worktree because the target implementation is itself uncommitted; do not commit unrelated user changes.
- Backup created before implementation: `/Users/simon/备份/codex/20260720-142525-one-trading-data-correctness-closure`.

---

### Task 1: Public quote unit contract

**Files:**
- Modify: `backend/app/services/free_sources/quote_fallback.py`
- Test: `backend/tests/free_sources/test_public_market_quotes.py`

**Interfaces:**
- Produces: every public quote row contains canonical `volume` in lots, `amount` in CNY, `source`, `source_volume_unit`, `source_amount_unit`, and `unit_version="cn_quote_v1"`.
- Consumes: Tencent field 6 and field 37 plus the market/code prefix.

- [ ] **Step 1: Write failing Tencent unit tests**

```python
def test_tencent_sz_quote_normalizes_lots_and_cny():
    # field 6 is lots; field 37 is ten-thousand CNY
    row = fetch_tencent_quotes(["000001.SZ"], client=fake_client("sz", volume=1256397, amount=137273))[0]
    assert row["volume"] == 1_256_397
    assert row["amount"] == 1_372_730_000
    assert row["unit_version"] == "cn_quote_v1"

def test_tencent_star_quote_normalizes_shares_to_lots():
    # Tencent STAR field 6 is shares; canonical storage is lots.
    row = fetch_tencent_quotes(["688549.SH"], client=fake_client("sh", volume=107491870, amount=258234))[0]
    assert row["volume"] == 1_074_918.7
    assert row["amount"] == 2_582_340_000
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `backend/.venv/bin/pytest -q backend/tests/free_sources/test_public_market_quotes.py`

Expected: amount remains `137273` and STAR volume remains `107491870`.

- [ ] **Step 3: Implement source-boundary conversion**

```python
def _tencent_volume_to_lots(code: str, volume: float | None) -> tuple[float | None, str]:
    if volume is None:
        return None, "unknown"
    raw_code = code.lower().removeprefix("sh").removeprefix("sz").removeprefix("bj")
    if code.lower().startswith("sh") and raw_code.startswith("68"):
        return volume / 100.0, "shares"
    return volume, "lots"

canonical_amount = raw_amount * 10_000.0 if raw_amount is not None else None
```

- [ ] **Step 4: Verify GREEN and run quote/depth consumers**

Run: `backend/.venv/bin/pytest -q backend/tests/free_sources/test_public_market_quotes.py backend/tests/free_sources/test_quote_fallback.py backend/tests/test_realtime_public_full_market.py`

---

### Task 2: Isolate public realtime snapshots from canonical daily data

**Files:**
- Modify: `backend/app/services/quote_service.py`
- Modify: `backend/app/tickflow/repository.py`
- Create: `backend/app/services/atomic_io.py`
- Test: `backend/tests/test_realtime_public_full_market.py`
- Test: `backend/tests/test_quote_snapshot_persistence.py`

**Interfaces:**
- Produces: `KlineRepository.write_quote_snapshot_asset(asset_type, df, metadata)` and `KlineRepository.publish_live_enriched_asset(asset_type, df)`.
- Snapshot path: `data/quote_snapshot/asset_type=<type>/date=<YYYY-MM-DD>/part.parquet`.
- Canonical `kline_*_daily` and `kline_*_enriched` remain untouched by public realtime refreshes.

- [ ] **Step 1: Write failing persistence-isolation tests**

```python
def test_public_refresh_writes_snapshot_not_daily(tmp_path):
    service = build_public_quote_service(tmp_path)
    service._fetch_full_market_quotes()
    assert list((tmp_path / "quote_snapshot").rglob("*.parquet"))
    assert not list((tmp_path / "kline_daily").rglob("*.parquet"))
    live, live_date = service.get_enriched_today()
    assert live_date is not None and live.height > 0
```

- [ ] **Step 2: Verify RED**

Run: `backend/.venv/bin/pytest -q backend/tests/test_quote_snapshot_persistence.py`

- [ ] **Step 3: Implement atomic snapshot persistence and memory-only publication**

```python
def atomic_write_parquet(df: pl.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp-{uuid.uuid4().hex}")
    try:
        df.write_parquet(tmp)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
```

Public refresh branches call `write_quote_snapshot_asset` and publish the computed enriched frame only to the repository cache. TickFlow paid branches retain their canonical persistence behavior.

- [ ] **Step 4: Verify snapshot and existing realtime tests**

Run: `backend/.venv/bin/pytest -q backend/tests/test_quote_snapshot_persistence.py backend/tests/test_realtime_public_full_market.py backend/tests/free_sources/test_public_market_quotes.py`

---

### Task 3: Make the quality gate authoritative

**Files:**
- Modify: `backend/app/services/free_sources/daily_quality.py`
- Modify: `backend/app/jobs/daily_pipeline.py`
- Modify: `backend/app/api/pipeline.py`
- Modify: `backend/app/services/pipeline_jobs.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/Data.tsx`
- Test: `backend/tests/test_daily_quality.py`
- Test: `backend/tests/test_pipeline_quality_status.py`

**Interfaces:**
- Produces terminal status `degraded` for completed pipelines whose quality report has `ok=false`.
- Unit checks emit `amount_unit_mismatch` and `turnover_unit_mismatch` with measurable ratios.

- [ ] **Step 1: Write failing unit-quality and job-outcome tests**

```python
def test_daily_quality_rejects_ten_thousand_cny_amount(tmp_path):
    seed_daily(tmp_path, amount=126_608, volume=1_158_719, close=10.94)
    report = run_daily_quality_check(tmp_path)
    assert "amount_unit_mismatch" in {i["code"] for i in report["issues"]}

def test_pipeline_result_with_failed_quality_is_degraded():
    assert terminal_status({"quality": {"ok": False}}) == "degraded"
```

- [ ] **Step 2: Verify RED**

Run: `backend/.venv/bin/pytest -q backend/tests/test_daily_quality.py backend/tests/test_pipeline_quality_status.py`

- [ ] **Step 3: Implement hard status semantics**

```python
JobStatus = Literal["pending", "running", "succeeded", "degraded", "failed"]

def terminal_status(result: dict) -> str:
    quality = result.get("quality") or {}
    return "succeeded" if quality.get("ok") is True else "degraded"
```

Move the final `done` progress event after quality evaluation. Data.tsx renders degraded in amber, includes issue count and does not show a success checkmark.

- [ ] **Step 4: Verify backend tests and frontend build**

Run: `backend/.venv/bin/pytest -q backend/tests/test_daily_quality.py backend/tests/test_pipeline_quality_status.py`

Run: `pnpm run build` from `frontend/`.

---

### Task 4: Repair and verify the 2026-07-20 canonical partitions

**Files:**
- Data: `data/kline_daily/date=2026-07-20/part.parquet`
- Data: `data/kline_daily_enriched/date=2026-07-20/part.parquet`
- Data: current-day index/ETF partitions if present
- Report: `data/user_data/daily_quality_latest.json`

**Interfaces:**
- Consumes the existing end-of-day daily provider only; no public quote snapshot is promoted directly.
- Produces an end-of-day partition whose median `amount / (volume * 100 * close)` is within `[0.5, 2.0]` and whose coverage gate is explicit.

- [ ] **Step 1: Dry-run provider output into a temporary DATA_DIR**
- [ ] **Step 2: Validate rows, uniqueness, OHLC, amount/volume ratio, and coverage**
- [ ] **Step 3: Stop writers and atomically replace only the validated 2026-07-20 partitions**
- [ ] **Step 4: Reopen Parquet, rerun quality, refresh repository cache, and verify dashboard totals**

---

### Task 5: Close build, incremental indicator, finance JSON, and test-isolation defects

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/data/MinuteSyncConfig.tsx`
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `backend/app/indicators/pipeline.py`
- Modify: `backend/app/services/financial_analyzer.py`
- Modify: affected tests/fixtures that mutate global settings

**Interfaces:**
- `CapabilitiesResponse` includes `depth`, `quote`, `websocket`, `view_available`, and marker metadata.
- `_load_recent_history` constructs its own `ScanCastOptions`.
- Finance JSON serialization uses `default=str` for date-compatible output.

- [ ] **Step 1: Add failing tests for recent-history loading and finance date serialization**
- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Implement minimal fixes and restore global settings in fixtures**
- [ ] **Step 4: Run full backend tests and frontend build**

---

### Task 6: Adopt atomic persistence and lineage sidecars

**Files:**
- Modify: `backend/app/services/atomic_io.py`
- Modify: `backend/app/tickflow/repository.py`
- Modify: `backend/app/services/free_sources/adj_factor_public.py`
- Modify: `backend/app/services/free_sources/financials_public.py`
- Modify: `backend/app/services/free_sources/fund_flow.py`
- Modify: `backend/app/services/pipeline_jobs.py`
- Test: `backend/tests/test_atomic_io.py`
- Test: `backend/tests/test_lineage.py`

**Interfaces:**
- `atomic_write_parquet`, `atomic_write_json`, and `write_lineage_record`.
- Sidecar path: `data/lineage/<dataset>/date=<date>/<run_id>.json` with source, fetched_at, unit_version, row_count, scope, quality, and target artifact.

- [ ] **Step 1: Write interruption and lineage tests**
- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Replace direct writes in in-scope public and canonical persistence paths**
- [ ] **Step 4: Verify no temporary artifacts remain after success/failure**

---

### Task 7: Integrate public capabilities into ProviderRuntime

**Files:**
- Modify: `backend/app/data_providers/base.py`
- Modify: `backend/app/data_providers/registry.py`
- Create: `backend/app/data_providers/public_provider.py`
- Modify: `backend/app/api/routes.py`
- Modify: `backend/app/tickflow/capabilities.py`
- Test: `backend/tests/test_provider_registry.py`
- Test: `backend/tests/test_capabilities_features.py`

**Interfaces:**
- Typed operations: `quote_snapshot`, `sealed_l1`, `adj_factor`, `financial`, `pools`.
- `depth5` remains false for public L1.
- Remove synthetic `depth5.batch`, `quote.batch`, and `quote.pool` capability entries; consumers use `features.*`.

- [ ] **Step 1: Write failing registry and semantic-capability tests**
- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Implement the public provider and route production calls through typed operations**
- [ ] **Step 4: Run capability, quote, depth, financial, and pool suites**

---

### Task 8: Quarantine adjustment outliers and retry financial failures

**Files:**
- Modify: `backend/app/services/free_sources/adj_factor_public.py`
- Modify: `backend/app/services/free_sources/financials_public.py`
- Test: `backend/tests/test_adj_public_no_event.py`
- Test: `backend/tests/free_sources/test_financials_public.py`

**Interfaces:**
- Per-symbol factor replacement validates event count/density and quarantines suspicious output without preserving stale rows.
- Failed financial symbols are retried with bounded attempts and remain visibly failed if exhausted.

- [ ] **Step 1: Add a failing 689009-style dense-micro-event test and bounded retry test**
- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Implement quarantine and retry behavior**
- [ ] **Step 4: Rebuild CSI800 coverage reports and verify the two known failures**

---

### Task 9: Full verification and handoff

**Files:**
- Verify only; no new implementation.

- [ ] **Step 1: Inspect final diff and non-target changes**
- [ ] **Step 2: Run full backend test suite and targeted static checks**
- [ ] **Step 3: Run frontend production build**
- [ ] **Step 4: Restart the actual 3018/3011 targets and confirm PID/start time/version**
- [ ] **Step 5: Verify `/health`, capabilities, data status, pipeline degraded behavior, and runtime logs**
- [ ] **Step 6: Use Codex in-app browser to verify Dashboard, Data, Financials, minute fallback, and sealed-L1 wording**
- [ ] **Step 7: Confirm backup, rollback procedure, target state, and no temporary artifacts**

## Self-Review

- Spec coverage: all quoted P0/P1 items map to Tasks 1-8; no new source acquisition is included.
- Type consistency: quote snapshot, quality status, atomic I/O, lineage, and provider feature names are defined before downstream use.
- Safety: canonical data repair is isolated to Task 4 after backup, dry-run, validation, writer stop, and atomic replacement.
- Dirty-worktree handling: no blanket reset, checkout, mass staging, or commit is planned.
