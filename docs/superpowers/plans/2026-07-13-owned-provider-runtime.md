# one-trading 自主 ProviderRuntime 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 one-trading 内自主实现统一、不可变快照驱动的行情 ProviderRuntime，并先把现有 TickFlow 日 K、复权因子、1 分钟 K 和实时行情迁入，同时保持未配置其他数据源时的行为等价。

**Architecture:** one-trading 定义自己的 `ProviderRequest` / `ProviderResult`、canonical transport schema、descriptor、resolver 和 generation snapshot。`CapabilitySet` 继续是业务唯一门控对象，通过同一 runtime snapshot 完成 `dataset x asset_type x operation` 的能力判断与解析。第一阶段 runtime 只注册 TickFlow；外部 GitHub 项目不成为运行时依赖，custom HTTP、stock-sdk、a-stock-data 和 TDX 均留给独立 adapter 计划。

**Tech Stack:** Python 3.11-3.13、FastAPI、Polars、pytest、pytest-cov、httpx MockTransport、现有 TickFlow SDK

## Global Constraints

- Provider 协议、schema、runtime、resolver、日志、测试和版本策略全部归 one-trading 所有。
- 外部项目只提供数据源端点、字段语义、鉴权、限频和故障特征参考；不得复制其 loader、registry、缓存、数据库、调度器、设置系统或 UI。
- 第一阶段只注册 `tickflow`，不得接入 custom HTTP、stock-sdk、a-stock-data、finshare、adata、easy_tdx 或 go-stock 的实际运行时。
- 本计划依赖“自主行情存储核心实施计划”完成；所有持久化只经过 one-trading 的 `PartitionWriter` / transaction，不新增第二套存储。
- 现有 `/api/kline`、`/api/data` 等路径和主响应结构、Parquet 目录、DuckDB 视图及 Polars 缓存入口保持不变。
- `CapabilitySet.has/require/limits/to_dict` 的 TickFlow 语义保持不变；新增 dataset 方法，不让业务代码直接读 `tiers.yaml`、registry 或 preferences。
- 每次业务操作只读取一个 `ProviderRuntimeSnapshot`；不得先检查一代能力、再用另一代 factory。
- 业务代码只能从捕获的 `CapabilitySet` 取得 snapshot 和 resolution，不能绕过它读取 runtime 的当前 snapshot。
- 解析时可因配置无效受控回到 TickFlow；Provider 已开始执行后的异常或空结果不得静默切源，也不得覆盖旧 Parquet。
- index、ETF、financial、instruments、depth 和 WebSocket 第一阶段继续走现有 TickFlow 专用路径；只迁移 A 股 stock 的 daily、adj_factor、minute、realtime。
- minute 只有 `frequency="1m"` 才能声明、解析、返回和写盘；不得把 5m 数据混入现有分钟表。
- 自动测试只用 fake client、MockTransport 和 `tmp_path`，不访问真实 Provider 网络，不写真实 `data/`。
- 实施前按全局规则在 `/Users/simon/备份/codex/<新时间戳目录>/` 备份项目、diff、未跟踪清单和 HEAD，并附 `README.md`。
- 当前工作树存在用户改动；每个提交只暂存当前任务列出的文件，不覆盖或提交无关品牌、AI、打包和依赖改动。
- 所有测试命令从 `backend/` 执行；所有 `git add` / `git commit` 命令先回到 `/Users/simon/Trading/one-trading`。若目标文件已含用户改动，使用隔离 worktree 和精确补丁合入，不能把用户原有 hunks 一并提交。
- 每项生产代码执行 RED -> GREEN -> refactor；原有 19 个测试和存储核心测试必须持续通过。

## File Map

**Create**

- `backend/app/data_providers/models.py`: dataset、operation、请求、结果、descriptor、snapshot 和 resolution 模型。
- `backend/app/data_providers/runtime.py`: 候选构建、原子发布、解析、fetch 和 generation 管理。
- `backend/app/data_providers/tickflow_mapping.py`: TickFlow `Cap` 到 dataset capability 的唯一映射。
- `backend/app/data_providers/projector.py`: transport frame 到既有物理 schema 的投影。
- `backend/app/services/tickflow_asset_sync.py`: index / ETF 暂不切源时的显式 TickFlow 兼容路径。
- `backend/tests/data_providers/conftest.py`
- `backend/tests/data_providers/test_existing_provider_contract.py`
- `backend/tests/data_providers/test_models_and_schemas.py`
- `backend/tests/data_providers/test_runtime_snapshot.py`
- `backend/tests/data_providers/test_capability_integration.py`
- `backend/tests/data_providers/test_tickflow_provider.py`
- `backend/tests/data_providers/test_runtime_publication.py`
- `backend/tests/data_providers/test_service_routing.py`
- `backend/tests/data_providers/test_realtime_routing.py`
- `backend/tests/qa/fake_tickflow.py`
- `backend/tests/qa_app.py`
- `.github/workflows/test.yml`: PR 测试门禁。

**Modify**

- `backend/app/data_providers/base.py`
- `backend/app/data_providers/schemas.py`
- `backend/app/data_providers/normalizer.py`
- `backend/app/data_providers/registry.py`
- `backend/app/data_providers/tickflow_provider.py`
- `backend/app/data_providers/__init__.py`
- `backend/app/tickflow/capabilities.py`
- `backend/app/tickflow/policy.py`
- `backend/app/services/kline_sync.py`
- `backend/app/services/quote_service.py`
- `backend/app/services/index_sync.py`
- `backend/app/jobs/daily_pipeline.py`
- `backend/app/api/kline.py`
- `backend/app/api/indices.py`
- `backend/app/api/routes.py`
- `backend/app/api/settings.py`
- `backend/app/main.py`

---

### Task 1: Characterize Current Provider and Capability Behavior

**Files:**
- Create: `backend/tests/data_providers/conftest.py`
- Create: `backend/tests/data_providers/test_existing_provider_contract.py`

- [ ] **Step 1: Reconfirm the full baseline**

```bash
cd /Users/simon/Trading/one-trading/backend
PYTHONDONTWRITEBYTECODE=1 uv run --frozen --no-sync \
  pytest -q -p no:cacheprovider -m "not qa and not external"
```

Expected: original 19 tests plus completed storage-core tests pass.

- [ ] **Step 2: Add characterization tests before refactoring**

Freeze:

- `CapabilitySet.has/require/limits/all/to_dict` behavior and serialized shape;
- none/free/starter/pro capability construction using existing local `tiers.yaml` fixtures;
- existing daily, adj-factor, minute and realtime TickFlow SDK calls, including parameters and return shapes;
- current API response roots for `/api/capabilities`, `/api/kline`, minute and realtime endpoints;
- A-stock versus index/ETF call sites;
- current preference keys and the fact that business services do not directly read `tiers.yaml`.

Add a source guard that lists every direct `get_client()`, `get_paid_realtime_client()` and TickFlow call in the production paths touched by this plan. Migrated stock functions leave the allowlist task by task; the final temporary allowlist is the named index / ETF compatibility module plus untouched financial, instruments, depth and WebSocket services.

- [ ] **Step 3: Run characterization only**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/data_providers/test_existing_provider_contract.py
```

Expected: PASS without production edits.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/data_providers/conftest.py \
  backend/tests/data_providers/test_existing_provider_contract.py
git commit -m "test(providers): characterize existing tickflow behavior"
```

---

### Task 2: Define one-trading Models and Canonical Schemas

**Files:**
- Create: `backend/app/data_providers/models.py`
- Create: `backend/app/data_providers/projector.py`
- Create: `backend/tests/data_providers/test_models_and_schemas.py`
- Modify: `backend/app/data_providers/base.py`
- Modify: `backend/app/data_providers/schemas.py`
- Modify: `backend/app/data_providers/normalizer.py`

**Interfaces:**

```python
class Dataset(StrEnum):
    DAILY = "daily"
    ADJ_FACTOR = "adj_factor"
    MINUTE = "minute"
    REALTIME = "realtime"

class DatasetOperation(StrEnum):
    BY_SYMBOL = "by_symbol"
    BATCH = "batch"
    UNIVERSE = "universe"

@dataclass(frozen=True)
class DatasetKey:
    dataset: Dataset
    asset_type: AssetType

@dataclass(frozen=True)
class DatasetOperationKey:
    dataset: Dataset
    asset_type: AssetType
    operation: DatasetOperation

@dataclass(frozen=True)
class ProviderRequest:
    dataset: Dataset
    asset_type: AssetType
    operation: DatasetOperation
    symbols: tuple[str, ...] = ()
    universes: tuple[str, ...] = ()
    start_time: datetime | None = None
    end_time: datetime | None = None
    frequency: Literal["1m"] | None = None
    request_id: str = field(default_factory=new_request_id)
    on_progress: Callable[[int, int], None] | None = field(
        default=None, repr=False, compare=False
    )

@dataclass(frozen=True)
class ProviderResult:
    frame: pl.DataFrame
    provider: str
    dataset: Dataset
    asset_type: AssetType
    operation: DatasetOperation
    frequency: Literal["1m"] | None
    request_id: str

class MarketDataProvider(Protocol):
    def fetch(self, request: ProviderRequest) -> ProviderResult: ...
    def close(self) -> None: ...
```

- [ ] **Step 1: Write RED schema and request-validation tests**

Cover invalid symbol/universe combinations, invalid operations, non-1m minute frequency, required and optional columns, duplicate primary keys, types, date/time bounds, empty-result behavior, realtime always returning a DataFrame, and transport-to-physical projection.

- [ ] **Step 2: Verify RED**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/data_providers/test_models_and_schemas.py
```

- [ ] **Step 3: Establish one schema truth source**

Move canonical definitions to `schemas.py`:

- daily transport required: `symbol,date,open,high,low,close,volume,amount`;
- adj factor: `symbol,trade_date,ex_factor`;
- minute: `symbol,datetime,open,high,low,close,volume,amount`, result frequency exactly `1m`;
- realtime: `symbol,last_price,prev_close,open,high,low,volume`, optional `amount,quote_ts,name,change_pct`.

Delete duplicate constants from normalizer and later from `kline_sync.py`. `StorageProjector` removes transport-only optional fields and produces the existing physical schemas; provider/source metadata stays in `ProviderResult` and transaction context.

- [ ] **Step 4: Verify GREEN**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/data_providers/test_models_and_schemas.py \
  tests/data_providers/test_existing_provider_contract.py
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/data_providers/models.py \
  backend/app/data_providers/projector.py backend/app/data_providers/base.py \
  backend/app/data_providers/schemas.py backend/app/data_providers/normalizer.py \
  backend/tests/data_providers/test_models_and_schemas.py
git commit -m "feat(providers): define owned request and schema contracts"
```

---

### Task 3: Implement the Immutable ProviderRuntime

**Files:**
- Create: `backend/app/data_providers/runtime.py`
- Create: `backend/tests/data_providers/test_runtime_snapshot.py`
- Modify: `backend/app/data_providers/registry.py`
- Modify: `backend/app/data_providers/__init__.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class ProviderLimits:
    rpm: int | None = None
    batch: int | None = None

@dataclass(frozen=True)
class ProviderDescriptor:
    name: str
    display_name: str
    kind: Literal["builtin", "adapter"]
    supports: frozenset[DatasetOperationKey]
    limits: Mapping[DatasetOperationKey, ProviderLimits]
    enabled: bool
    available: bool
    error: str | None = None

@dataclass(frozen=True)
class OperationCapability:
    available: bool
    provider: str
    limits: ProviderLimits
    reason: str

@dataclass(frozen=True)
class DatasetCapability:
    operations: Mapping[DatasetOperation, OperationCapability]

ProviderFactory = Callable[[], MarketDataProvider]

@dataclass(frozen=True)
class ProviderRuntimeSnapshot:
    generation: int
    descriptors: Mapping[str, ProviderDescriptor]
    factories: Mapping[str, ProviderFactory]
    selections: Mapping[DatasetOperationKey, str]
    effective_datasets: Mapping[DatasetKey, DatasetCapability]

@dataclass(frozen=True)
class ProviderResolution:
    snapshot: ProviderRuntimeSnapshot
    key: DatasetOperationKey
    provider: str
    factory: ProviderFactory
    limits: ProviderLimits
    reason: str

class ProviderRuntime:
    def snapshot(self) -> ProviderRuntimeSnapshot: ...
    def build_candidate(...) -> ProviderRuntimeSnapshot: ...
    def publish(self, candidate: ProviderRuntimeSnapshot) -> ProviderRuntimeSnapshot: ...
    def resolve(self, key: DatasetOperationKey, *, snapshot: ProviderRuntimeSnapshot | None = None) -> ProviderResolution: ...
    def fetch(self, resolution: ProviderResolution, request: ProviderRequest) -> ProviderResult: ...
```

- [ ] **Step 1: Write RED snapshot tests**

Require generation monotonicity, `MappingProxyType` and nested `frozenset` immutability, lock-free reads after publication, failed candidate retaining old generation, factory cleanup, one snapshot per request, operation-specific selections, invalid selection resolving to TickFlow with a reason, and runtime fetch failures never silently resolving again.

- [ ] **Step 2: Verify RED**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/data_providers/test_runtime_snapshot.py
```

- [ ] **Step 3: Implement candidate-build then pointer publication**

Build and validate descriptors, factories, operation-specific selections and effective capabilities outside the publication lock. A dataset-level user preference is expanded and validated separately for each supported operation, so `by_symbol` and `batch` may report different providers/reasons. Deep-freeze every nested collection. On success, acquire a short lock, assign the next generation and swap one snapshot reference. Do not store long-lived HTTP/SDK clients; each factory returns an independent provider and runtime closes it in `finally`.

`registry.get_provider()` may remain as a temporary compatibility wrapper, but it must resolve through the runtime and must not keep its own `_PROVIDERS` truth source.

- [ ] **Step 4: Add structured fetch telemetry**

Emit `provider_fetch_started`, `provider_fetch_completed` and `provider_fetch_failed` with `run_id`, `request_id`, generation, provider, dataset, asset type, operation, symbol count, rows, elapsed milliseconds and resolution reason. Never log tokens, raw headers or complete sensitive query strings.

- [ ] **Step 5: Verify GREEN and thread contention**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/data_providers/test_runtime_snapshot.py
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/data_providers/runtime.py \
  backend/app/data_providers/registry.py backend/app/data_providers/__init__.py \
  backend/tests/data_providers/test_runtime_snapshot.py
git commit -m "feat(providers): add immutable provider runtime"
```

---

### Task 4: Integrate Runtime Capabilities Without a Second Truth Source

**Files:**
- Create: `backend/app/data_providers/tickflow_mapping.py`
- Create: `backend/tests/data_providers/test_capability_integration.py`
- Modify: `backend/app/tickflow/capabilities.py`
- Modify: `backend/app/tickflow/policy.py`

**Interfaces:**

```python
class CapabilitySet:
    def with_provider_runtime(
        self,
        runtime: ProviderRuntime,
        snapshot: ProviderRuntimeSnapshot,
    ) -> CapabilitySet: ...
    def provider_snapshot(self) -> ProviderRuntimeSnapshot: ...
    def has_dataset(self, dataset: Dataset, asset_type: AssetType,
                    operation: DatasetOperation) -> bool: ...
    def limits_for_dataset(self, dataset: Dataset, asset_type: AssetType,
                           operation: DatasetOperation) -> ProviderLimits | None: ...
    def resolve_dataset(self, dataset: Dataset, asset_type: AssetType,
                        operation: DatasetOperation,
                        *, snapshot: ProviderRuntimeSnapshot | None = None) -> ProviderResolution: ...
    def effective_datasets_to_dict(self) -> dict[str, object]: ...
```

- [ ] **Step 1: Write RED mapping tests**

Map exact legacy capabilities, without broad inference:

- `KLINE_DAILY_BY_SYMBOL` -> daily/by_symbol;
- `KLINE_DAILY_BATCH` -> daily/batch;
- `KLINE_MINUTE_BY_SYMBOL` -> minute/by_symbol;
- `KLINE_MINUTE_BATCH` -> minute/batch;
- `QUOTE_BY_SYMBOL` -> realtime/by_symbol;
- `QUOTE_BATCH` -> realtime/batch;
- `QUOTE_POOL` -> realtime/universe;
- `ADJ_FACTOR` -> adj_factor/by_symbol and adj_factor/batch, preserving existing limits.

Run the mapping over the characterized none/free/starter/pro fixtures. Prove that free by-symbol realtime does not imply universe realtime, and use a synthetic descriptor to prove by-symbol and batch can expose different provider/reason objects under one dataset. Prove `to_dict()` is byte-for-byte unchanged.

- [ ] **Step 2: Verify RED**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/data_providers/test_capability_integration.py
```

- [ ] **Step 3: Implement one composed capability object**

`CapabilitySet` holds a stable runtime executor plus the immutable snapshot captured when that capset was constructed. Dataset methods always pass that snapshot to `resolve()`; they never read a newer generation mid-operation. Existing TickFlow-specific methods keep their signatures and behavior.

- [ ] **Step 4: Verify GREEN and characterization**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/data_providers/test_capability_integration.py \
  tests/data_providers/test_existing_provider_contract.py
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/data_providers/tickflow_mapping.py \
  backend/app/tickflow/capabilities.py backend/app/tickflow/policy.py \
  backend/tests/data_providers/test_capability_integration.py
git commit -m "feat(capabilities): compose provider dataset capabilities"
```

---

### Task 5: Make TickFlow a Conforming Provider

**Files:**
- Create: `backend/tests/data_providers/test_tickflow_provider.py`
- Modify: `backend/app/data_providers/tickflow_provider.py`
- Modify: `backend/app/data_providers/normalizer.py`

- [ ] **Step 1: Write RED adapter tests with a fake SDK**

Cover daily by-symbol/batch, adj-factor, minute by-symbol/batch with explicit `period="1m"`, realtime by-symbol/batch/universe, empty results, malformed rows, SDK exception propagation, progress callbacks, client close behavior and request/result metadata.

Prove `get_minute()` no longer returns a hard-coded empty frame and realtime no longer leaks list/dict return-shape variants.

- [ ] **Step 2: Verify RED**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/data_providers/test_tickflow_provider.py
```

- [ ] **Step 3: Implement `TickFlowProvider.fetch()`**

Inject a client factory for tests. Dispatch strictly on `DatasetOperationKey`, pass existing SDK parameters, normalize with one-trading schemas, validate result metadata and return `ProviderResult`. Do not catch SDK errors into empty frames; runtime owns structured failure logging and callers preserve old data.

- [ ] **Step 4: Add descriptor conformance**

Generate the TickFlow descriptor from the mapped runtime capabilities. A descriptor may only advertise operations backed by a tested branch. Financial and instruments remain on their old explicit services and are not advertised through this fetch protocol yet.

- [ ] **Step 5: Verify GREEN**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/data_providers/test_tickflow_provider.py \
  tests/data_providers/test_models_and_schemas.py
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/data_providers/tickflow_provider.py \
  backend/app/data_providers/normalizer.py \
  backend/tests/data_providers/test_tickflow_provider.py
git commit -m "refactor(providers): conform tickflow to owned protocol"
```

---

### Task 6: Publish Runtime at Startup and Redetection

**Files:**
- Create: `backend/tests/data_providers/test_runtime_publication.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/routes.py`
- Modify: `backend/app/api/settings.py`

- [ ] **Step 1: Write RED lifecycle and API tests**

Require startup generation 1, a stable `app.state.provider_runtime`, `app.state.capabilities` containing the published snapshot, failed redetection preserving old state, and requests in flight retaining the old snapshot after a newer generation is published.

Freeze the additive capability response:

```json
{
  "label": "Free",
  "capabilities": {},
  "provider_generation": 1,
  "effective_datasets": {
    "stock": {
      "daily": {
        "operations": {
          "by_symbol": {
            "available": true,
            "provider": "tickflow",
            "limits": {},
            "reason": "selected"
          },
          "batch": {
            "available": false,
            "provider": "tickflow",
            "limits": {},
            "reason": "capability_unavailable"
          }
        }
      }
    }
  }
}
```

Existing `label` and `capabilities` must remain unchanged.

- [ ] **Step 2: Verify RED**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/data_providers/test_runtime_publication.py
```

- [ ] **Step 3: Publish one runtime/capability generation**

Startup detects TickFlow caps, builds a TickFlow-only candidate, publishes it, constructs a new `CapabilitySet(runtime, published_snapshot)` and assigns that capset once to app state. The runtime object itself remains stable. `/api/capabilities` reads the captured capset rather than independently detecting caps or reading runtime current state. Redetect/settings first build and validate; after publication they replace `app.state.capabilities` with one reference assignment. In-flight code keeps the old capset/snapshot and remains valid.

- [ ] **Step 4: Update long-running consumers**

Schedulers and quote loops capture the current app-state `CapabilitySet` once at the beginning of a job/refresh cycle and use its snapshot throughout. Do not retain a capset forever after settings redetection; fetch it at job start or accept an accessor.

- [ ] **Step 5: Verify GREEN**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/data_providers/test_runtime_publication.py \
  tests/data_providers/test_capability_integration.py
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/app/api/routes.py backend/app/api/settings.py \
  backend/tests/data_providers/test_runtime_publication.py
git commit -m "feat(providers): publish runtime generations at app lifecycle"
```

---

### Task 7: Route A-Stock Daily, Adj-Factor and Minute Services

**Files:**
- Create: `backend/tests/data_providers/test_service_routing.py`
- Create: `backend/app/services/tickflow_asset_sync.py`
- Modify: `backend/app/services/kline_sync.py`
- Modify: `backend/app/services/index_sync.py`
- Modify: `backend/app/jobs/daily_pipeline.py`
- Modify: `backend/app/api/kline.py`
- Modify: `backend/app/api/indices.py`

- [ ] **Step 1: Write RED routing tests**

Cover:

- daily batch resolves once and respects resolved batch/rpm limits;
- single daily and adj factor use by-symbol operations;
- minute single/batch request and result frequency are `1m`;
- empty/exception leaves old Parquet checksum unchanged;
- provider metadata enters transaction context and lineage, not physical rows;
- index and ETF endpoints still call the existing TickFlow-only path;
- the direct-client guard only covers migrated stock functions, while `tickflow_asset_sync.py` is the sole temporary allowlist for index / ETF;
- one scheduled job uses one snapshot generation from start to finish;
- `sync_daily_by_quotes` is allowed only when daily/batch selection and realtime/universe resolution name the same provider, and that provider explicitly supports both operations.

- [ ] **Step 2: Verify RED**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/data_providers/test_service_routing.py
```

- [ ] **Step 3: Replace direct stock fetches with resolution**

Build `ProviderRequest` from service inputs, resolve through `CapabilitySet.resolve_dataset()`, call `ProviderRuntime.fetch()`, project to the existing physical schema and persist through the storage-core transaction. Remove duplicated daily/minute normalization and migrated direct client calls.

- [ ] **Step 4: Keep explicit asset boundaries**

Move the old direct daily/adj helpers needed by index and ETF into `tickflow_asset_sync.py`, update `index_sync.py` and `api/indices.py` to call that named compatibility path, and reject external selection for index/ETF in the resolver. Financial, instruments, depth and WebSocket remain on their existing TickFlow-specific fetch paths. No generic fallback is introduced.

- [ ] **Step 5: Verify GREEN and storage integration**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/data_providers/test_service_routing.py \
  tests/storage/test_core_write_path_integration.py \
  tests/storage/test_existing_storage_contract.py
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/tickflow_asset_sync.py \
  backend/app/services/kline_sync.py backend/app/services/index_sync.py \
  backend/app/jobs/daily_pipeline.py backend/app/api/kline.py \
  backend/app/api/indices.py backend/tests/data_providers/test_service_routing.py
git commit -m "refactor(providers): route stock kline services through runtime"
```

---

### Task 8: Route Realtime and Complete the Verification Loop

**Files:**
- Create: `backend/tests/data_providers/test_realtime_routing.py`
- Create: `backend/tests/qa/fake_tickflow.py`
- Create: `backend/tests/qa_app.py`
- Create: `.github/workflows/test.yml`
- Modify: `backend/app/services/quote_service.py`

- [ ] **Step 1: Write RED realtime tests**

Cover watchlist by-symbol/batch, full-market universe, empty watchlist, capability denial, malformed quote rows, failure preserving current caches and disk partitions, index/ETF staying on TickFlow, and one snapshot per polling cycle. Verify free by-symbol capability never unlocks full-market universe mode.

- [ ] **Step 2: Verify RED**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  tests/data_providers/test_realtime_routing.py
```

- [ ] **Step 3: Route stock realtime through ProviderRuntime**

Resolve the exact operation from watchlist/full-market mode, fetch a canonical DataFrame, split stock/index/ETF only after normalization, and publish caches only after validation. Keep the current downstream enrichment, monitoring and SSE behavior. A failed or empty fetch leaves old caches and Parquet untouched and emits a controlled failure event.

- [ ] **Step 4: Run all automated gates**

```bash
uv run --frozen --no-sync pytest -q -p no:cacheprovider \
  -m "not qa and not external"
uv run --frozen --no-sync ruff check \
  app/data_providers tests/data_providers
uv run --frozen --no-sync ruff check --select E9,F63,F7,F82 app tests
uv run --frozen --no-sync mypy --strict --ignore-missing-imports \
  app/data_providers
uv run --frozen --no-sync pytest -q \
  tests/data_providers tests/storage \
  --cov=app.data_providers --cov=app.storage --cov-branch \
  --cov-report=term-missing --cov-fail-under=90
```

- [ ] **Step 5: Add CI compatibility gates**

Add:

- backend matrix on Ubuntu with Python 3.11, 3.12 and 3.13;
- storage lock/recovery subset on Ubuntu, macOS and Windows with Python 3.12;
- targeted Ruff, mypy and 90% core branch coverage;
- frontend compatibility on Node 20 and pnpm 9.10.0 using frozen install, `tsc --noEmit` and Vite build.

Do not make real Provider network tests part of default CI.

- [ ] **Step 6: Run temporary-data manual QA in the Codex browser**

Use unique loopback ports and `/tmp/one-trading-provider-qa-<run_id>`. Record real data checksums before startup. Start `tests.qa_app:app` with the fake TickFlow bridge and a temporary `DATA_DIR`; if the existing UI is used, start Vite on `127.0.0.1` with pnpm 9.10.0. Confirm all listeners are loopback-only.

In the Codex in-app browser:

1. open `/api/capabilities` and verify generation plus stock daily/minute/realtime operation distinctions;
2. run a fake daily/minute sync and confirm existing read APIs, physical schema, transaction and lineage;
3. run watchlist realtime and universe realtime under distinct capabilities;
4. switch the fake bridge to failure mode and retry;
5. confirm controlled error, no silent fallback, old API data still readable and partition checksums unchanged.

- [ ] **Step 7: Read and analyze telemetry**

Read backend, fake bridge, frontend, browser console and network logs. Check every provider operation has matching start/completed or start/failed events, the same request ID and generation, correct row counts/timing, explicit resolution reason, no unexplained WARNING/ERROR/Traceback, no credential canary, no pending transaction and no real-data checksum change.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/quote_service.py \
  backend/tests/data_providers/test_realtime_routing.py \
  backend/tests/qa/fake_tickflow.py backend/tests/qa_app.py \
  .github/workflows/test.yml
git commit -m "refactor(providers): route realtime and add runtime gates"
```

## Completion Gate

This plan is complete only when:

- TickFlow-only behavior remains compatible for all characterized APIs and Cap methods;
- the four stock datasets resolve by exact operation from one immutable generation;
- index, ETF, financial, instruments, depth and WebSocket remain on explicit TickFlow paths;
- no migrated service directly calls the TickFlow client;
- all tests, compatibility matrices, targeted quality and coverage gates pass;
- the Codex in-app browser main path and failure path pass;
- generated logs and traces have been read and analyzed;
- real data checksums are unchanged and no unrelated worktree change was staged.

Custom HTTP, stock-sdk, a-stock-data, finshare/adata resilience, TDX host routing and go-stock-derived source adapters are separate future plans. They may implement one-trading's protocol, but they do not bring their source projects' data systems into this runtime.
