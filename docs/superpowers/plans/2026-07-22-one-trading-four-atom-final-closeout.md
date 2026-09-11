# one-trading 数据工作台“四原子”最终收尾实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal：** 在不破坏当前 3011/3018 工作台的前提下，将 recovery 成果整理成可审计、可重复启动、普通读取不访问外网、数据准入不误报、可备份和可回滚的本地生产版本。

**Architecture：** 保持现有 Parquet + DuckDB 数据面、SQLite 控制面和 React/FastAPI 接口；上游 GitHub 项目只提供数据源与工程机制情报，不成为运行时依赖。

**Tech Stack：** Python/FastAPI/Polars/DuckDB/SQLite、React/Vite/TypeScript、APFS clone、本地 RC 3118/3111。

**计划文件目标：** 执行新 session 首先把本计划保存为：

`/Users/simon/Trading/one-trading/docs/superpowers/plans/2026-07-22-one-trading-four-atom-final-closeout.md`

## 一、计划评估与最终调整

附件方案总体合理，四个原子任务仍是正确关键路径，但不能原样执行。最终版锁定以下修正：

- 当前静态源码约有 90 个 GET decorator，不沿用“101 个 GET”的固定数字；以 FastAPI 运行时路由清单为最终审计基准。
- 不把日线改成月度物理分区。继续保持既有 `date=YYYY-MM-DD/part.parquet` 协议，只按月份组织抓取批次，避免破坏仓库、扫描器和回测消费者。
- RC 分成两段：先建立最小 RC 运行器，再在其中执行 M5 数据 canary；M5 完成后再做最终 RC 认证。
- 长历史来源 NO-GO 只阻止相关数据集晋级，不阻止已经通过完整验证的 Phase、本地 GET 和 RC 代码切换。最终报告必须分别给出“平台运行状态”和“数据完整度状态”。
- 不直接整理当前主工作树，也不在 dirty recovery 上继续堆改动；从 recovery HEAD 新建干净收尾工作树，分批恢复已有 49 个修改。
- 生产数据晋级、3011/3018 切换和真实回滚均设置独立授权门，不因“执行本计划”而自动获得破坏性操作授权。

当前冻结参考值为：

- 主工作树：`56d4810`，3011/3018 正运行该版本，后端报告 `0.1.68`。
- recovery：`80473cc`，49 个 tracked 修改、5 个 untracked 项，尚不可称为 RC。
- 磁盘日线：1,395,155 行，至 2026-07-22；运行 API 仍返回 1,389,629 行、至 2026-07-21。
- 最新 2026-07-22 分区无 BJ 行，虽然 instruments 中有 328 个 BJ 标的。
- 32 个 catalog 数据集中仅 `trading_calendar` 有正式 dataset policy。
- 这些数字必须在执行开始时重新冻结，不能直接当作执行后的验收证据。

## 二、实施顺序

### S0：冻结、备份和 recovery 整理

- [ ] 读取 `/Users/simon/Trading/AGENTS.md`、旧 M5–M8 计划、全部当前 J/K 验收报告，明确旧 GO 只能作为历史证据。
- [ ] 记录两个工作树的 branch、HEAD、ahead/behind、dirty 状态，以及 3011/3018 的 PID、启动时间、cwd、命令和版本。
- [ ] 记录数据目录字节数、文件清单、关键 Parquet 行数/日期/市场覆盖、SQLite `integrity_check`、API status 与 catalog 摘要。
- [ ] 确认没有活动写入任务；如有任务运行，只等待其结束，不取消、不强停。
- [ ] 在 `/Users/simon/备份/codex/<时间>-one-trading-four-atom-closeout/` 建立新备份，包含 README、recovery binary diff、未跟踪源码/文档、Git 身份、SQLite online backup、生产 data APFS clone、Parquet 清单和运行身份。
- [ ] 备份前后比较受管 Parquet 清单；如期间发生变化，废弃该次快照并重新生成。
- [ ] 保留并登记主工作树现有 `data.k4-residual-*`、`output/` 和未跟踪旧计划，不删除、不覆盖。
- [ ] 从 `80473cc` 创建：
  - branch：`codex/four-atom-closeout`
  - worktree：`/Users/simon/Trading/one-trading/.worktrees/four-atom-closeout`
- [ ] 不 pull/merge 主工作树，不修改原 dirty recovery。

将 recovery diff 恢复成四个提交：

1. `fix(recovery): restore runtime and frontend contracts`
   - preferences、pipeline、前端 API 合并、Layout、MiniIntraday、相关测试和可解释的 lockfile 更新。
2. `fix(recovery): preserve BJ and provider corrections`
   - symbol normalization、BJ 路由、quote/depth/public source、kline sync 及对应测试。
3. `fix(recovery): preserve M5 semantic corrections`
   - catalog scanner、CNINFO/lifecycle、corporate actions、financial PIT 及对应测试。
4. `docs(audit): invalidate superseded J and K evidence`
   - 旧验收正文保留，但明确标记失效；生成新的 recovery 基线报告。

Gate S0：

- 新工作树能重现 recovery 功能且 Git diff 可解释。
- `output/` 不进入 Git。
- `pnpm-lock.yaml` 必须能由当前 `package.json` 解释并通过 frozen install。
- 后端、前端基线测试通过。
- 3011/3018 和生产数据完全未变。

### 原子 1：Phase 和生产准入 fail-closed

主要位置：

- `backend/app/data_catalog/admission.py`
- `backend/app/data_catalog/service.py`
- `backend/app/data_sync/tools/readmit.py`
- `backend/app/services/data_query.py`
- catalog API/model 与数据工作台展示组件

- [ ] 新增 `PhaseResolution`、`resolve_phase()`、`validate_promotion_evidence()`。
- [ ] API 新增 `policy_phase`、`effective_phase`、`agent_readable`、`phase_reason_codes`；原 `phase` 暂时保留为 `effective_phase` 的兼容别名。
- [ ] 固定解析规则：
  - 无 policy、无文件：`unavailable`
  - 无 policy、有文件：`lab`
  - 非法 policy：`lab + phase_policy_invalid`
  - canary policy 且质量可用：`canary`
  - production policy、质量 healthy、证据完整：`production`
  - production 证据缺失：降为 `canary + promotion_evidence_missing`
  - production 质量失败：降为 `lab + quality_failed`
- [ ] `serving_ready` 仅允许 materialized、非 failed、effective phase 为 canary/production；`agent_readable` 只允许 healthy production。
- [ ] `readmit`、backfill、空增量成功最多晋级 canary，不得自动 production。
- [ ] 显式晋级只通过 operator CLI `python -m app.data_sync.tools.admit`，第一版不在 UI 添加“晋级生产”按钮。
- [ ] 晋级证据写入现有 `dataset_policies.source_policy_json.admission`，至少包含 run ID、相对证据路径及 hash、来源权利状态、质量/覆盖报告、父数据集、算法版本、时间和操作人。
- [ ] 提供只读 dry-run 和 apply 两种模式；apply 前校验证据文件真实存在。
- [ ] 为现有 32 个数据集生成 policy migration：
  - calendar 保持 production；
  - 已物化且可读的数据最高设为 canary；
  - Lab 数据保持 lab；
  - 空或不支持的数据设为 unavailable；
  - 不因迁移产生新的 production。
- [ ] Agent 默认拒绝 canary；显式 operator/lab 工具与普通 Agent 接口分离。

重点测试：

- 健康文件无 policy 不能 production。
- 非法 phase 不会自动修正为 production。
- 无新增分区的 backfill 不会 production。
- production + failed quality 时普通服务与 Agent 都 fail-closed。
- canary 可供本地 UI 使用，但 Agent 返回明确拒绝原因。
- 重启、catalog rescan 后解析结果不变。
- 不重写任何 Parquet。

提交：

`fix(catalog): make dataset admission explicit and fail closed`

### 原子 2：普通 GET 本地化与数据源网络边界

主要位置：

- `backend/app/services/egress_policy.py`
- `backend/app/services/free_sources/http_resilience.py`
- `backend/app/api/kline.py`
- `backend/app/api/indices.py`
- `backend/app/api/free_ext.py`
- `frontend/src/lib/api.ts`

- [ ] 从 `app.routes` 生成 GET 路由清单，逐项标记 pure-local、cached-local、operator-diagnostic；清单成为测试契约。
- [ ] 禁止 API handler 直接调用 `httpx/requests/urllib`；市场数据 transport 必须收到显式 `EgressPermit`。
- [ ] permit 只允许：
  - `sync`
  - `operator_probe`
  - `explicit_live_refresh`
- [ ] permit 必须包含 run ID、dataset/source、purpose；普通 GET 无法自行创建 permit。
- [ ] 将以下 GET 改为只读本地缓存或本地空结果：
  - 股票/指数 daily、minute
  - quotes、intraday、changes、F10
  - adj factor、financials
  - pools 与板块历史/分时
- [ ] 废弃 GET `refresh=1`；返回 `refresh_requires_post` 和对应 POST 路径，不产生外网请求。
- [ ] 复用已有 refresh POST，并补充缺少的 quotes、intraday、changes、F10、单票因子/财务、pool refresh。
- [ ] refresh POST 统一返回 HTTP 202、`job_id/run_id/status=queued`；前端轮询本地任务状态。
- [ ] 本地空结果返回 200 和 `rows/items=[]`，同时给出 `stale`、`data_timestamp`、`refresh_available`、`reason_code`，不把“本地没有缓存”伪装成上游 502。
- [ ] 前端普通页面刷新只执行 GET；只有明确的“刷新实时数据/同步”操作才执行 POST。
- [ ] 默认关闭进入页面即自动访问外网；实时页面读取 5–15 秒本地缓存，显式实时模式通过 POST 启动有限时 refresh session。

网络韧性同时单独提交：

- 复用进程级 `httpx.Client` 连接池，并在 lifespan shutdown 关闭。
- cooldown key 固定为 hostname + operation，东财三个 trends host 不共享单一 key。
- 只有所有镜像均失败才记录 provider-level cooldown。
- connect/read timeout、TLS EOF、502/503/504 最多重试两次并加 jitter。
- 403 不重试；429 解析 `Retry-After` 后排入后续任务，不在请求线程长时间等待。
- 空响应、解析失败、403、429、5xx、TLS 分别记录。
- 网络失败不得用空数据覆盖 last-known-good。

测试：

- 新增 `backend/tests/test_market_get_local_only.py`。
- 所有 market GET 在网络 client 被设为“调用即 AssertionError”时仍返回本地结果或本地空结果。
- GET 前后数据目录和 SQLite 的受管文件 hash/mtime 不变。
- provider outbound counter 增量为零。
- POST 无 permit 失败；有合法 permit 才可调用 transport。
- 三个东财 host 中一个失败不会冷却另外两个。
- 403/429/TLS EOF/空响应和 last-known-good 路径全部覆盖。

提交：

- `fix(api): keep ordinary market-data GET requests local only`
- `fix(http): require explicit egress and isolate host cooldowns`

### 原子 4A：提前建立最小可重复 RC 运行器

主要位置：

- `scripts/rc/local_rc.py`
- `frontend/vite.iso-3111.config.ts`
- `/health` 运行身份扩展
- `backend/tests/rc/`

- [ ] 提供 `start/status/verify/stop`。
- [ ] candidate 默认使用 3118/3111，端口占用时安全失败，绝不自动 kill。
- [ ] 后端不使用 `--reload`；前端先 `pnpm build`，再使用配置了 preview proxy 的 Vite production preview。
- [ ] 数据使用 `output/rc/<run_id>/data` APFS clone，绝不直接使用生产 data。
- [ ] 使用独立 process group；停止时核对 PID、启动时间、cwd、commit 和命令，不执行宽泛端口 kill。
- [ ] `identity.json` 记录 commit、branch、dirty、版本、dist hash、数据绝对路径、data fingerprint、SQLite user_version、PID、端口、环境版本和日志路径。
- [ ] data fingerprint 基于 SQLite artifact hash 清单、catalog generation 和关键受管文件清单生成。
- [ ] `/health` 增加可选的 build ID、commit、dirty、data fingerprint；普通 dev 环境允许为空，RC 必须与 manifest 一致。
- [ ] `start` 要求 Git clean；`status/verify/stop` 可幂等重复运行。

Gate RC-A：

- 一条命令启动、一条命令验证、一条命令安全停止。
- stop/start 两次身份一致。
- 3111/3118 无残留孤儿进程。
- 3011/3018 未受影响。

提交：

`chore(rc): add deterministic local release-candidate runner`

### 原子 3：M5 数据与语义闭环

#### M5.1 来源准入

- [ ] 第一优先仅验证当前 TickFlow 长历史 batch 权限，做不落盘 canary。
- [ ] canary 固定覆盖 SH 主板、科创、SZ 主板、创业板、BJ、退市/暂停上市、长期停牌、公司行动、ETF 和指数。
- [ ] 只有来源权利、数据单位、复权语义、北交所、退市历史、限频和完整性均通过，才可成为生产来源。
- [ ] 若 TickFlow 不通过，不自动切换到公开网页源；其他来源只能进入 Lab，等待用户提供明确授权。
- [ ] 无来源通过时生成正式 `M5_LONG_HISTORY_NO_GO`，但继续完成代码 RC 和后续运行切换。

GitHub 项目使用边界固定为：

- `a-share-kline-puller`：checkpoint、lease、无数据审核队列。
- `astock-data-toolkit`：公司行动、日频估值和公告字段情报。
- `a-stock-data`、AKShare、myhhub/stock：来源地图和字段交叉核验。
- `free-stockdb`：manifest、checksum、离线恢复机制。
- `A-share-replay`：历史回放和按日存储参考，不作为日线权利方。
- `china_stock_data`、Sequoia-X：异常吞空和覆盖旧数据的反例。
- ChipDistribution：不重复建设现有筹码算法。
- 不 clone、不 vendor、不把上游项目放入生产运行时。

#### M5.2 长历史日线与 BJ

- [ ] 保持既有按日物理分区；按“月份 × 20–50 标的”组织任务。
- [ ] 股票目标为最近十年；ETF 为成立以来；指数为来源支持的完整历史。
- [ ] 现有 2025-07 以后分区全部 compare-only；冲突进入 quarantine。
- [ ] missing partition 才能正常写；替换健康分区必须 repair + backup ID。
- [ ] 每批写 checkpoint、sync run、artifact、lineage、source rights 和 hash。
- [ ] 先修复当前最新日 BJ=0，再开始向前回填。
- [ ] SH/SZ/BJ 分别计算 expected/actual/ratio：
  - 任一市场为零：failed
  - ≥99.5%：healthy
  - 97%–99.5%：degraded/canary
  - <97%：failed
- [ ] lifecycle 未生产准入时，覆盖分母标记 provisional、`survivorship_safe=false`，数据最高 canary。
- [ ] 继续使用现有 30/36/40GB 容量门禁；预计峰值必须包含 staging、发布副本和 10% 余量。
- [ ] 不加入全市场分钟、逐笔或盘口数据。

#### M5.3 真实公司行动

- [ ] 将 EastMoney bonus/F10 接到 Lab fetcher；CNINFO/交易所公告只作为来源证据和交叉核验。
- [ ] 公司行动升级为 schema/unit v2，增加 source record ID、source URL、方案状态、原始单位、history guarantee 和 verification。
- [ ] `adj_factor_derived` 移出正式事件事实，只作为 verification signal。
- [ ] 真实事件与复权因子双向核验；无法解释的差异进入 quarantine。
- [ ] 只有来源明确返回“无事件”才能写 `verified_no_event`；网络失败和空响应只能写 `source_failed/unverified`。
- [ ] 生产晋级要求真实来源可追溯、BJ 独立覆盖、幂等、稳定 action ID、非 unknown 成为主要语义。

提交：

`feat(data): publish sourced corporate-action facts`

#### M5.4 严格 PIT 财务

- [ ] 财务 schema/unit 升级为 v2，增加 `available_at`、`pit_unsafe`、`history_guarantee`。
- [ ] 禁止 `announce_date <- report_date`。
- [ ] `available_at` 只接受权威公告日期，或经过来源语义验证的 update date。
- [ ] 现有可疑回填行保守标记 `pit_unsafe=true`，不得反向猜测其公开日期。
- [ ] strict Agent/回测查询只消费 `pit_unsafe=false` 且 `available_at <= as_of` 的记录。
- [ ] 普通财务页面可以展示 unsafe 记录，但必须有非 PIT 警告。
- [ ] restatement 追加保存，不覆盖旧版；当前来源声明 `as_collected`，不能声明完整历史重述。
- [ ] shares 只有真实 effective date 才能用于历史估值；抓取日快照不得倒灌历史。

提交：

`feat(data): make financial PIT guarantees explicit`

#### M5.5 统一准入报告

每个数据集必须给出：

- 数据来源和权利状态
- SH/SZ/BJ 覆盖
- 历史深度
- schema/unit/history guarantee
- PIT 和生存者偏差状态
- phase/promotion evidence
- 消费者验证
- production、canary、lab 或证据化 No-Go

`listing_delisting_events`、`instrument_status_history` 在没有交易所历史来源前继续明确 Lab/No-Go，不得用影子样本晋级。

### 原子 4B：最终 RC 认证

- [ ] 在最终 clean commit 上重新创建 RC data clone。
- [ ] 应用所有获准 M5/M6 candidate 数据，不直接写生产目录。
- [ ] 运行全量后端测试、前端测试、lint、build、SQLite integrity、Parquet reopen、catalog full rescan。
- [ ] 验证 production phase 全部可反查 evidence。
- [ ] 验证 Agent 只读取 healthy production。
- [ ] 验证普通浏览器主路径 provider outbound=0。
- [ ] 注入同步失败，确认 last-known-good 可继续读取。
- [ ] 重启 RC 后身份、catalog、data fingerprint 和页面行为一致。
- [ ] 使用 Codex 内置浏览器检查首页、数据台、股票详情、指数、财务、设置和关键控制台错误。

Gate RC-B：

- Git clean、commit 唯一、manifest 与 `/health` 一致。
- 全量自动检查通过。
- 真实浏览器主路径通过。
- 失败恢复和安全停止通过。
- 不以历史测试数量代替本次结果。

## 三、M6 重做和最终切换

### M6 数据集重建

- [ ] `valuation_daily`：只使用同日 raw daily 和 PIT-safe shares；无真实历史 PE/PB 来源时保持 null，核心字段覆盖不达标则不得 production。
- [ ] `limit_up_events`：使用未复权 raw daily；分别覆盖主板、科创、创业、BJ、ST 规则，修复跌停误判；没有历史 ST 状态时限定 history guarantee。
- [ ] `index_membership_history`：当前 pools 只能作为 `snapshot_seed/as_collected`，没有修订史时保持 canary。
- [ ] `corporate_actions`：只消费新的 sourced v2 事实。
- [ ] 以下八项继续 No-Go，除非另有真实来源和独立准入：
  - index_weights
  - dragon_tiger
  - seats
  - block_trades
  - ownership
  - governance
  - etf_nav
  - etf_holdings
- [ ] 输出新的 dataset-by-dataset M6 admission matrix，不复用旧 F/K 报告。

### K1：隔离候选

- [ ] 使用最终 clean commit、最终 RC runner 和新的生产 data clone。
- [ ] 核对 health、commit、build hash、data fingerprint、SQLite schema。
- [ ] 完成 API 成功/失败矩阵和 Codex 内置浏览器验证。
- [ ] 整个普通浏览过程 provider outbound 增量必须为零。

### K2：切换前备份

- [ ] 在 `/Users/simon/备份/codex/<时间>-one-trading-final-cutover/` 创建独立完整备份。
- [ ] 包含旧源码身份、生产 data、SQLite、RC commit/build、PID/端口、数据清单、回滚命令和 README。
- [ ] 验证备份能重新打开、hash 匹配，并生成 K2 报告。

### K3：代码与获准数据切换

这是独立授权门。执行者必须在 K2 报告完成后向用户明确申请：

- 停止当前 3011/3018；
- 更新生产 SQLite policy；
- 发布获准的数据增量；
- 使用新 RC commit 启动正式运行面。

获准后按固定顺序：

1. 记录旧 PID、cwd、版本和 data fingerprint。
2. 只停止身份匹配的旧进程。
3. 通过带 production profile 的 RC runner 启动 3018/3011，不使用 dev `--reload`。
4. 数据增量按 manifest 发布，禁止用候选 data 目录整体覆盖生产 data。
5. 检查 SQLite、Parquet、catalog、health 和 phase。
6. 运行 API 矩阵、浏览器主路径和 outbound=0 验证。
7. 如需外网验证，只运行一个显式获准的低量 POST sync。
8. 任一关键门禁失败立即进入 K4 回滚。

根据用户选择，即使长历史来源仍为 No-Go，只要代码、兼容性、现有数据读取和回滚门禁全部通过，也允许完成代码切换；相关数据集继续保持 canary/No-Go。

### K4：真实回滚演练

- [ ] 停止新版正式面。
- [ ] 从 K2 备份恢复旧源码身份、data 和 SQLite。
- [ ] 启动旧版本并验证 health、preferences、catalog 和浏览器主路径。
- [ ] 记录回滚耗时、文件清单和残留。
- [ ] 再恢复 K3 后快照并重新启动新版。
- [ ] 验证新版 data fingerprint、SQLite integrity、API 和 UI。
- [ ] 保留全部备份和候选数据，不自动清理。

只有 K4 完整走通，才能宣布“生产运行改造收尾”。

## 四、接口、测试和文档契约

重要接口变化：

| 接口 | 最终契约 |
|---|---|
| Catalog entry | 增加 policy/effective phase、agent readable 和 reason codes；旧 phase 为兼容别名 |
| 普通 market GET | 只读本地缓存，不访问外网、不写数据 |
| Refresh POST | HTTP 202，返回 job/run ID，由前端轮询 |
| Agent data | 只允许 healthy production；canary 默认拒绝 |
| `/health` | RC/production 增加 commit、build ID、dirty 和 data fingerprint |
| Operator admission | CLI dry-run/apply；production 必须有可验证证据 |

全量最终检查：

```text
cd backend
uv run pytest -q -p no:cacheprovider tests

cd ../frontend
pnpm test:run
pnpm lint
pnpm build

git diff --check
git status --porcelain
```

还必须覆盖：

- Phase 正反例及重启一致性。
- GET egress=0、GET 无写入。
- POST permit、限频、403/429/TLS/空响应。
- checkpoint 中断恢复和幂等重跑。
- compare-only 与冲突 quarantine。
- PIT 未来信息泄漏。
- 公司行动/复权双向核验。
- RC 端口占用、安全 stop、孤儿进程、身份不匹配。
- SQLite integrity、Parquet reopen、catalog full reload。
- 生产浏览器主路径和真实回滚。

每个原子任务结束时同步更新：

- `/Users/simon/Trading/GitHub项目借鉴记录.md`
- `/Users/simon/Trading/数据台GitHub项目数据能力目录.md`
- 对应 acceptance 报告

记录必须写清固定上游 commit、借鉴机制、one-trading 落点、自动检查、真实运行验证和 production/canary/Lab/No-Go 状态。

## 五、完成标准与新 session 执行入口

最终结果必须分三项报告，禁止合并成模糊的“全部完成”：

1. **Platform/Code Status**
   - Phase、local GET、egress、RC、测试和 UI 是否完成。
2. **Dataset Admission Status**
   - 每个 M5/M6 数据集的 production/canary/Lab/No-Go。
3. **Production Runtime Status**
   - K3/K4 是否完成，3011/3018 当前实际运行哪个 commit 和哪一代数据。

允许的最终结论：

- `PLATFORM_GO + DATA_COMPLETE_GO + RUNTIME_GO`
- `PLATFORM_GO + DATA_PARTIAL_NO_GO + RUNTIME_GO`
- `PLATFORM_GO + DATA_PARTIAL_NO_GO + CUTOVER_NOT_AUTHORIZED`
- 任一核心代码、备份或回滚门禁失败时为 `NO_GO`

预计工作量：

- S0 与 recovery 整理：1–2 天
- Phase：1–2 天
- GET/egress/HTTP：3–4 天
- RC 运行器与认证：2–4 天
- M5 数据与语义：5–10 天，另加来源审批和实际回填时间
- M6 与 K1–K4：3–5 天

新 session 的执行指令：

> 在 `/Users/simon/Trading/one-trading` 执行“四原子最终收尾计划”。先读取 AGENTS.md 和本计划，使用 `superpowers:executing-plans`。严格从 S0 开始，不修改当前 3011/3018，不直接写生产 data，不 pull/merge/push。第一阶段先完成 S0、recovery 分批整理、原子 1、原子 2 和 RC-A；通过阶段 Gate 后再进入 M5。K3 前必须单独向我申请正式切换授权。
