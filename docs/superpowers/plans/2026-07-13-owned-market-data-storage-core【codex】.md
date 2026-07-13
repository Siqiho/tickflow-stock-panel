# one-trading 自主行情存储核心实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 one-trading 自主实现可恢复、跨进程安全的 Parquet 存储核心，并在不改变现有目录、文件名、DuckDB 视图和业务 API 的前提下，统一现有行情写入路径。

**Architecture:** `app.parquet` 负责兼容读取；`PartitionWriter` 负责单分区校验、锁、唯一临时文件、fsync 和原子替换；`ProviderTransaction` 在其上实现 preimage、write-ahead manifest、恢复、undo 和 write-event lineage。所有实现均属于 one-trading，不引入参考项目的存储框架或运行时。

**Tech Stack:** Python 3.11-3.13、Polars、DuckDB、portalocker 3.2.0、pytest、pytest-cov、multiprocessing

## Global Constraints

- one-trading 自主拥有存储协议、实现、测试和演进节奏；GitHub 参考项目只提供故障样本和接口经验。
- 本计划不接入任何新行情端点，不引入外部项目的服务层、数据库、缓存、调度器或插件系统。
- TickFlow 默认行为保持不变；`settings.data_dir`、既有 Parquet 目录、`part.parquet` / `all.parquet` 文件名、DuckDB 视图名和业务 API 保持不变。
- 日 K 新写入的物理列严格保持 `symbol,date,open,high,low,close,volume,amount`；来源信息写入 manifest / lineage，不写进既有行情行。
- 空结果、校验失败和 Provider 失败都不得创建 pending transaction，不得改动旧分区。
- 每个目标同时使用进程内 resolved-path lock 与 `portalocker==3.2.0` 跨进程锁；多目标按绝对路径排序加锁。
- 临时文件必须与目标同目录、名称唯一且不以 `.parquet` 结尾；写后 fsync 文件、`os.replace`，再走平台 durability adapter。POSIX fsync 父目录；Windows 尝试目录 handle flush，不支持时记录明确降级事件并依赖 manifest/checksum 恢复。
- 事务顺序固定为 preimage -> planned manifest -> replace -> applied manifest -> committed manifest -> lineage。
- 所有自动测试只使用 `tmp_path`；不得读写 `/Users/simon/Trading/one-trading/data`。
- 实施前在 `/Users/simon/备份/codex` 创建新的时间戳子目录，备份项目、当前 diff、未跟踪清单和 HEAD，并附 `README【codex】.md`，写明备份原因、原路径和时间。
- 当前工作树有用户改动；每次只暂存该任务列出的文件，不得覆盖或提交品牌、AI、打包、依赖及其他无关改动。
- 所有测试命令从 `backend/` 执行；所有 `git add` / `git commit` 命令先回到 `/Users/simon/Trading/one-trading`。若列出的文件在实施开始时已含用户改动，必须在隔离 worktree 完成并以精确补丁合入，不能把用户原有 hunks 一并提交。
- 每项生产代码严格遵循 RED -> GREEN -> refactor；旧有 19 个测试必须持续通过。

## File Map

**Create**

- `backend/app/parquet.py`: schema-compatible Parquet 读取。
- `backend/app/storage/__init__.py`: 存储公共导出。
- `backend/app/storage/models.py`: partition、mutation、manifest 和结果类型。
- `backend/app/storage/partition_writer.py`: 单分区安全写和多目标锁。
- `backend/app/storage/transactions.py`: pending / committed 两阶段事务。
- `backend/app/storage/recovery.py`: 启动恢复和显式 undo。
- `backend/app/storage/lineage.py`: write-event lineage。
- `backend/tests/storage/conftest.py`
- `backend/tests/storage/test_existing_storage_contract.py`
- `backend/tests/storage/test_parquet_schema_compat.py`
- `backend/tests/storage/test_partition_writer.py`
- `backend/tests/storage/test_partition_transaction.py`
- `backend/tests/storage/test_transaction_recovery.py`
- `backend/tests/storage/test_lineage.py`
- `backend/tests/storage/test_core_write_path_integration.py`
- `backend/tests/storage/test_datastore_recovery.py`

**Modify**

- `backend/pyproject.toml`
- `backend/uv.lock`
- `backend/app/tickflow/repository.py`
- `backend/app/services/kline_sync.py`
- `backend/app/services/quote_service.py`
- `backend/app/services/depth_service.py`
- `backend/app/services/financial_sync.py`
- `backend/app/services/instrument_sync.py`
- `backend/app/indicators/pipeline.py`
- `backend/app/api/kline.py`
- `backend/app/api/data.py`
- `backend/app/jobs/daily_pipeline.py`
- `backend/scripts/cleanup_halt_days.py`
- `backend/app/main.py`

---

### Task 1: Freeze Existing Storage Contracts

**Files:**
- Create: `backend/tests/storage/conftest.py`
- Create: `backend/tests/storage/test_existing_storage_contract.py`

- [ ] **Step 1: Record the baseline**

```bash
cd /Users/simon/Trading/one-trading/backend
PYTHONDONTWRITEBYTECODE=1 uv run --frozen --no-sync \
  pytest -q -p no:cacheprovider
```

Expected: `19 passed` before production changes.

- [ ] **Step 2: Add characterization fixtures and tests**

Freeze these contracts with temporary data:

- daily path `kline_daily/date=YYYY-MM-DD/part.parquet`, exact eight-column schema, key `(symbol, date)` and current last-write-wins behavior;
- minute path `kline_minute/date=YYYY-MM-DD/part.parquet`, key `(symbol, datetime)`;
- `adj_factor/all.parquet`, key `(symbol, trade_date)`;
- four `financials/<table>/part.parquet` targets and three instruments targets;
- existing DuckDB view names;
- realtime replace and merge semantics;
- empty financial response preserves the old file;
- repository public method signatures and existing API response roots.

- [ ] **Step 3: Verify the characterization suite is GREEN without production edits**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/storage/test_existing_storage_contract.py
```

- [ ] **Step 4: Commit only the characterization files**

```bash
git add backend/tests/storage/conftest.py \
  backend/tests/storage/test_existing_storage_contract.py
git commit -m "test(storage): characterize existing parquet contracts"
```

---

### Task 2: Add Schema-Compatible Reads

**Files:**
- Create: `backend/app/parquet.py`
- Create: `backend/tests/storage/test_parquet_schema_compat.py`

**Interfaces:**

```python
def scan_parquet_compat(
    source: str | Path | Sequence[str | Path],
    *,
    schema: Mapping[str, pl.DataType] | None = None,
    **kwargs: object,
) -> pl.LazyFrame: ...

def read_partition_compat(
    path: Path,
    *,
    schema: Mapping[str, pl.DataType] | None = None,
) -> pl.DataFrame: ...

def scan_daily_parquet(source: object, **kwargs: object) -> pl.LazyFrame: ...
def scan_enriched_parquet(source: object, **kwargs: object) -> pl.LazyFrame: ...
```

- [ ] **Step 1: Write failing compatibility tests**

Cover old integer volume versus new float volume, a legacy partition missing `amount`, an enriched partition with additional indicator columns, deterministic canonical column order, and rejection of an unsafe incompatible type.

- [ ] **Step 2: Verify RED**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/storage/test_parquet_schema_compat.py
```

Expected: import failure for `app.parquet`.

- [ ] **Step 3: Implement compatible scanning**

Use Polars structured scan options (`missing_columns="insert"`, explicit cast policy and canonical schema). Compatibility is read-only tolerance: every new daily write must still contain exactly the canonical eight columns.

- [ ] **Step 4: Verify GREEN and old tests**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/storage/test_parquet_schema_compat.py \
  tests/storage/test_existing_storage_contract.py
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/parquet.py backend/tests/storage/test_parquet_schema_compat.py
git commit -m "feat(storage): add schema-compatible parquet reads"
```

---

### Task 3: Implement the Atomic PartitionWriter

**Files:**
- Create: `backend/app/storage/__init__.py`
- Create: `backend/app/storage/models.py`
- Create: `backend/app/storage/partition_writer.py`
- Create: `backend/tests/storage/test_partition_writer.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`

**Interfaces:**

```python
@dataclass(frozen=True)
class PartitionSpec:
    dataset: str
    required_schema: Mapping[str, pl.DataType]
    primary_key: tuple[str, ...]
    sort_by: tuple[str, ...]
    max_rows: int
    symbol_column: str | None = "symbol"
    date_column: str | None = None
    expected_frequency: str | None = None

@dataclass(frozen=True)
class WriteResult:
    target: Path
    rows: int
    checksum: str | None
    previous_checksum: str | None

@dataclass(frozen=True)
class StagedPartition:
    target: Path
    temp_path: Path | None
    mode: Literal["replace", "delete"]
    rows: int
    expected_checksum: str | None

class PartitionWriter:
    def lock_targets(self, targets: Iterable[Path]) -> ContextManager[TargetLockSet]: ...
    def stage_locked(
        self,
        locks: TargetLockSet,
        target: Path,
        frame: pl.DataFrame | None,
        *,
        spec: PartitionSpec,
        mode: Literal["replace", "upsert", "delete"],
    ) -> StagedPartition: ...
    def apply_staged_locked(
        self,
        locks: TargetLockSet,
        staged: StagedPartition,
    ) -> WriteResult: ...
    def replace(self, target: Path, frame: pl.DataFrame, *, spec: PartitionSpec) -> WriteResult: ...
    def upsert(self, target: Path, frame: pl.DataFrame, *, spec: PartitionSpec) -> WriteResult: ...
    def delete(self, target: Path, *, expected_checksum: str | None = None) -> WriteResult: ...
```

- [ ] **Step 1: Write RED tests**

Required cases:

- `test_replace_failure_leaves_old_partition_intact`
- `test_temp_names_are_unique_and_not_matched_by_parquet_glob`
- `test_upsert_rejects_duplicate_incoming_primary_keys`
- `test_upsert_keeps_existing_rows_and_replaces_matching_keys`
- `test_two_process_upserts_do_not_lose_rows`
- `test_different_targets_can_write_concurrently`
- `test_locked_primitives_require_token_and_do_not_reacquire_lock`
- `test_minute_writer_rejects_non_1m_frequency`
- `test_target_outside_data_root_is_rejected`

The failure test monkeypatches `os.replace` and proves the original checksum is unchanged.

- [ ] **Step 2: Verify RED**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/storage/test_partition_writer.py
```

- [ ] **Step 3: Pin only required tooling**

Add `portalocker==3.2.0` to runtime dependencies and `pytest-cov` to the dev extra. Regenerate with the project toolchain:

```bash
uv lock
uv sync --frozen --extra dev
```

- [ ] **Step 4: Implement validation, locks and atomic replace**

Implementation requirements:

- validate resolved target containment below `data_dir`;
- validate schema, primary-key uniqueness, symbol shape, partition date, maximum rows and minute frequency;
- hold the same target lock across read, concat, dedupe and replacement during upsert;
- make public `replace/upsert/delete` thin single-target wrappers around one `lock_targets()` scope plus `stage_locked()` / `apply_staged_locked()`;
- require a matching `TargetLockSet` token for the locked primitives and never reacquire a file lock inside them;
- create `.<target>.<pid>.<uuid>.tmp`, fsync it, checksum it, replace atomically and fsync the directory;
- delete only under lock and honor an optional expected checksum;
- always remove orphan temporary files created by the failed call.
- expose a platform durability result; tests assert POSIX directory fsync ordering and Windows atomic replace/recovery behavior without claiming unsupported power-loss guarantees.

- [ ] **Step 5: Verify GREEN, including multiprocessing**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/storage/test_partition_writer.py
```

- [ ] **Step 6: Commit only scoped files**

```bash
git add backend/pyproject.toml backend/uv.lock \
  backend/app/storage/__init__.py backend/app/storage/models.py \
  backend/app/storage/partition_writer.py \
  backend/tests/storage/test_partition_writer.py
git commit -m "feat(storage): add locked atomic partition writer"
```

---

### Task 4: Add Transaction Manifests and Lineage

**Files:**
- Create: `backend/app/storage/transactions.py`
- Create: `backend/app/storage/lineage.py`
- Create: `backend/tests/storage/test_partition_transaction.py`
- Create: `backend/tests/storage/test_lineage.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class PartitionMutation:
    target: Path
    frame: pl.DataFrame | None
    spec: PartitionSpec
    mode: Literal["replace", "upsert", "delete"]
    frequency: str | None = None

@dataclass(frozen=True)
class TransactionContext:
    run_id: str
    request_id: str
    provider: str
    dataset: str
    asset_type: str

class ProviderTransaction:
    @classmethod
    def begin(cls, data_dir: Path, writer: PartitionWriter, context: TransactionContext) -> Self: ...
    def apply(self, mutations: Sequence[PartitionMutation]) -> tuple[WriteResult, ...]: ...
    def commit(self) -> Path: ...
    def rollback(self) -> RecoverySummary: ...
```

- [ ] **Step 1: Write RED tests for write-ahead ordering**

Cover invalid mutation creating no pending state, manifest fsync before first replace, per-target planned-to-applied transitions, immutable committed manifest before lineage, preimage hardlink/copy behavior, sorted multi-target locks, no nested lock reacquisition, committed-plus-pending crash state and write-event rather than row-level lineage.

- [ ] **Step 2: Verify RED**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/storage/test_partition_transaction.py tests/storage/test_lineage.py
```

- [ ] **Step 3: Implement the lifecycle**

`apply()` validates all mutations in memory, acquires one sorted `TargetLockSet`, calls `stage_locked()` for every postimage, captures preimages, atomically persists `pending.json`, calls `apply_staged_locked()` for each target and persists its applied state. It must not call the public self-locking `replace/upsert/delete` wrappers. `commit()` rechecks every postcondition/checksum (`None` means the target must be absent after delete), writes immutable `committed.json`, appends idempotent lineage, fsyncs both, then deletes `pending.json` and fsyncs the transaction directory. Every manifest uses unique temp JSON, file fsync, `os.replace` and parent fsync.

If a crash leaves both files, `committed.json` wins: recovery verifies post-checksums, rebuilds missing lineage, then removes pending. A directory is active only when pending exists without committed.

- [ ] **Step 4: Verify GREEN**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/storage/test_partition_transaction.py tests/storage/test_lineage.py
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/storage/transactions.py backend/app/storage/lineage.py \
  backend/tests/storage/test_partition_transaction.py \
  backend/tests/storage/test_lineage.py
git commit -m "feat(storage): add transaction manifests and lineage"
```

---

### Task 5: Add Crash Recovery and Undo

**Files:**
- Create: `backend/app/storage/recovery.py`
- Create: `backend/tests/storage/test_transaction_recovery.py`

**Interfaces:**

```python
def recover_provider_transactions(data_dir: Path, writer: PartitionWriter) -> RecoverySummary: ...
def undo_provider_transaction(data_dir: Path, writer: PartitionWriter, run_id: str) -> RecoverySummary: ...
```

- [ ] **Step 1: Encode the recovery matrix as RED tests**

Test planned/pre-checksum cleanup, planned/post-checksum rollback, applied/post-checksum rollback, removal of newly created targets, unknown-checksum quarantine, lineage reconstruction for committed transactions, committed-plus-pending cleanup, committed conflicts and checksum-guarded undo.

- [ ] **Step 2: Verify RED**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/storage/test_transaction_recovery.py
```

- [ ] **Step 3: Implement deterministic recovery**

Lock each target before comparing checksums. Restore or delete only when the current checksum equals a recorded preimage or expected postimage. Move unknown states to `provider_transactions/quarantine/<run_id>/` and never overwrite the live target. Make every recovery action idempotent.

- [ ] **Step 4: Verify GREEN and repeatability**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/storage/test_transaction_recovery.py
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/storage/recovery.py \
  backend/tests/storage/test_transaction_recovery.py
git commit -m "feat(storage): recover and undo interrupted writes"
```

---

### Task 6: Migrate Core Market Write Paths

**Files:**
- Modify: `backend/app/tickflow/repository.py`
- Modify: `backend/app/services/kline_sync.py`
- Modify: `backend/app/services/quote_service.py`
- Modify: `backend/app/api/kline.py`
- Create: `backend/tests/storage/test_core_write_path_integration.py`

- [ ] **Step 1: Write delegation and AST guard tests**

Assert writer delegation from daily partition writes, live daily/enriched merge and flush, adj-factor sync, minute sync and minute-history API. Add an AST guard that forbids direct `.write_parquet()` calls in these production files.

- [ ] **Step 2: Verify RED against current direct writes**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/storage/test_core_write_path_integration.py
```

- [ ] **Step 3: Inject one shared writer**

Create `DataStore.partition_writer`, expose it through `KlineRepository`, and preserve every existing public method signature. Use `upsert` for append/merge and `replace` for current flush semantics. Refresh memory caches and DuckDB views only after successful disk commit.

- [ ] **Step 4: Centralize minute and adj-factor persistence**

Add one `persist_minute_partitions()` function to `kline_sync.py`; make both service and API paths call it. Enforce `frequency="1m"`. Remove duplicated Parquet read-modify-write from `api/kline.py`.

- [ ] **Step 5: Verify GREEN and characterization compatibility**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/storage/test_core_write_path_integration.py \
  tests/storage/test_existing_storage_contract.py
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/tickflow/repository.py \
  backend/app/services/kline_sync.py backend/app/services/quote_service.py \
  backend/app/api/kline.py backend/tests/storage/test_core_write_path_integration.py
git commit -m "refactor(storage): route market writes through partition writer"
```

---

### Task 7: Migrate Derived, Depth, Financial, Instruments and Maintenance Writes

**Files:**
- Modify: `backend/app/indicators/pipeline.py`
- Modify: `backend/app/services/depth_service.py`
- Modify: `backend/app/services/financial_sync.py`
- Modify: `backend/app/services/instrument_sync.py`
- Modify: `backend/app/jobs/daily_pipeline.py`
- Modify: `backend/app/api/data.py`
- Modify: `backend/scripts/cleanup_halt_days.py`
- Modify: `backend/tests/storage/test_core_write_path_integration.py`

- [ ] **Step 1: Expand RED guards and failure tests**

Require zero direct `.write_parquet()` in these paths. Prove that a failed full enriched rebuild preserves all old partitions, four-table financial sync rolls back earlier targets, concurrent instrument enrichment loses no rows, a depth snapshot is replaced through the shared writer, clear rejects active pending transactions, and halt cleanup uses the writer.

- [ ] **Step 2: Verify RED**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/storage/test_core_write_path_integration.py
```

- [ ] **Step 3: Replace destructive rebuilds with mutations**

Compute all enriched outputs before mutation. Submit sorted replace/delete mutations in one transaction. Never call `shutil.rmtree` on the enriched root.

- [ ] **Step 4: Transact financial and instrument writes**

Use one transaction for the four financial outputs and one-target transactions for depth and individual reference refreshes. Record `provider="tickflow"` in transaction context without changing physical schemas.

- [ ] **Step 5: Guard clear and cleanup**

Return HTTP 409 when an uncommitted pending transaction exists or a write job is active. A crash residue containing both committed and pending is recovered/cleaned first and is not treated as active. Delete discovered data targets through checksum-aware writer operations; clear caches and refresh views only after all mutations commit.

- [ ] **Step 6: Verify GREEN**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/storage/test_core_write_path_integration.py \
  tests/storage/test_partition_transaction.py
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/indicators/pipeline.py \
  backend/app/services/depth_service.py backend/app/services/financial_sync.py \
  backend/app/services/instrument_sync.py \
  backend/app/jobs/daily_pipeline.py backend/app/api/data.py \
  backend/scripts/cleanup_halt_days.py \
  backend/tests/storage/test_core_write_path_integration.py
git commit -m "refactor(storage): transact derived and reference data writes"
```

---

### Task 8: Recover Before DuckDB Views and Close Verification

**Files:**
- Modify: `backend/app/tickflow/repository.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/storage/test_datastore_recovery.py`

- [ ] **Step 1: Write startup-order RED tests**

Assert the order is directory creation -> legacy migration -> writer creation -> transaction recovery -> DuckDB connection -> view registration. Add an interrupted-transaction fixture and prove the restored partition is readable through the view.

- [ ] **Step 2: Verify RED**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/storage/test_datastore_recovery.py
```

- [ ] **Step 3: Hook recovery and telemetry**

Expose `DataStore.recovery_summary` and `app.state.storage_recovery`. Log recovered, rolled-back, lineage-rebuilt and quarantined counts with `run_id`; never log frames, tokens or credentials.

- [ ] **Step 4: Run storage and full backend suites**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider tests/storage
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  -m "not qa and not external"
```

- [ ] **Step 5: Run targeted quality gates**

```bash
uv run --frozen --no-sync ruff check \
  app/parquet.py app/storage tests/storage
uv run --frozen --no-sync ruff check --select E9,F63,F7,F82 app tests
uv run --frozen --no-sync mypy --strict --ignore-missing-imports \
  app/parquet.py app/storage
uv run --frozen --no-sync pytest -q tests/storage \
  --cov=app.storage --cov-branch --cov-report=term-missing \
  --cov-fail-under=90
```

The repository currently has broad pre-existing Ruff debt; only changed/new core files and fatal-code checks are gates.

- [ ] **Step 6: Run temporary-data main and failure paths**

Use `/tmp/one-trading-storage-qa-<run_id>` only. Record real data Parquet checksums before and after. Exercise daily, adj factor, minute, realtime, depth, financial and instruments writes; inject a crash after replace but before `state=applied`; recreate `DataStore`; verify rollback, readable Parquet, no residual pending state, committed checksum and lineage agreement, and quarantine on unknown checksum.

- [ ] **Step 7: Read and analyze the generated logs**

Inspect all INFO/WARNING/ERROR/Traceback lines. Confirm ordering, row counts, elapsed time, recovery reason, no credentials, no unexplained warnings, no performance regression signal and no missing event fields. Compare real-data checksums byte-for-byte.

- [ ] **Step 8: Commit**

```bash
git add backend/app/tickflow/repository.py backend/app/main.py \
  backend/tests/storage/test_datastore_recovery.py
git commit -m "feat(storage): recover transactions before startup views"
```

## Completion Gate

This plan is complete only when:

- all old and new automated tests pass on Python 3.11, 3.12 and 3.13;
- lock/recovery tests pass on Linux, macOS and Windows CI;
- targeted Ruff, mypy and branch coverage gates pass;
- the temporary-data main path and injected failure path pass;
- generated telemetry has been read and analyzed;
- the real `/Users/simon/Trading/one-trading/data` checksum list is unchanged;
- no unrelated dirty-worktree file has been staged or overwritten.

Custom HTTP, stock-sdk, a-stock-data, TDX and resilience routing are explicitly outside this plan and require separate adapter plans after this core is accepted.
