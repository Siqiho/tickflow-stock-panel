# one-trading 数据平台开发日志

最近维护：2026-08-12（最新版 Zeabur 共享市场数据同步与目录重扫）

适用项目：`/Users/simon/Trading/one-trading`

职责：只记录 one-trading 本地数据集的规划、实现、验证、验收和生产状态。

## 0. 权威边界

- 本文件是 one-trading 数据平台本地开发的持续维护入口。
- 数据台 GitHub 上游项目与采用判断见 `/Users/simon/Trading/数据台GitHub项目借鉴记录.md`。
- GitHub 数据来源、字段、分页、错误、更新和权利情报见 `/Users/simon/Trading/数据台GitHub项目数据能力目录.md`。
- 未来数据集顺序、开工门和验收门槛见 `/Users/simon/Trading/数据台下一步工程工作计划.md`。
- `docs/investigations/2026-07-29-data-platform-history-and-dashboard-audit-log.md` 是截至 2026-07-29 的历史审计与事故复盘，不再承担当前状态总览。
- 本文件中的 worktree、测试、canary、Parquet 或接口证据均不自动等于生产准入；生产状态必须由当前目标运行面和正式 `DATA_DIR` 证据单独证明。

## 1. 最终目标与执行顺序

最终目标：

> 在 one-trading 现有数据台基础上，以“一个上游来源、一个数据集、一个完整闭环”为单位，研究真实数据生产者、请求参数、字段、分页、错误语义和更新机制；然后在 one-trading 内实现自有 Provider/Adapter，接入现有同步服务，发布为可重复更新的 Parquet 数据集，并提供只读取本地数据的 API。每完成一个数据集就停止验收，确认数据质量和使用价值后，再进入下一个数据集。

验收顺序固定为：

1. `stock_daily`：第一个闭环验收对象。
2. `announcement_events`：只有 `stock_daily` 验收后才进入独立验收。
3. `stock_instruments`、`etf_instruments`、`index_instruments`、`trading_calendar`：已有隔离实现，但必须逐数据集验收，不因共同开发于 Task 7 而合并 promotion。
4. 其他数据集：只有前一个数据集被接受或明确 no-go 后才排期。

## 2. 本地状态词

- `planned`：已定义价值和边界，尚未固定生产者证据。
- `source-verified`：真实生产者、参数、字段、分页、错误和更新语义已有证据。
- `isolated`：one-trading 自有实现和自动检查已在隔离环境完成；未证明正式数据和运行面。
- `canary`：受控真实源/真实样本运行完成；仍未通过完整用户验收。
- `accepted`：数据质量、重复更新、local-only API 和使用价值均由用户验收。
- `production`：accepted 数据集已在正式 `DATA_DIR` 和目标运行面受控启用并验证。
- `blocked / no-go / superseded`：分别表示阻塞、明确不准入、被更高质量实现替代。

## 3. 当前开发坐标

### 3.1 当前用户运行面（只读观察，as_of 2026-08-04）

- 当前 checkout：`/Users/simon/Trading/one-trading`，分支基线 `main@56d481076c008efca9ff40db8f5c89139bb7f600`；该工作区同时存在用户和其他任务的未提交/未跟踪修改，运行结果不能仅按 HEAD 归因。
- 前端：`3011`，PID `17633`，启动于 `2026-08-03 13:48:49 +0800`，cwd=`/Users/simon/Trading/one-trading/frontend`，Vite 开发服务器。
- 后端：`3018`，PID `17623`，启动于 `2026-08-03 13:48:49 +0800`，cwd=`/Users/simon/Trading/one-trading/backend`，`uvicorn app.main:app --reload`。
- 当前物理数据根：`/Users/simon/Trading/one-trading/data`。本节只记录一次只读身份快照；PID、启动时间和未提交文件都可能变化，后续验收必须重新取证。

### 3.2 隔离候选实现

- 隔离开发 worktree：`/Users/simon/Trading/one-trading/.worktrees/data-platform-convergence-v1`。
- 分支：`codex/data-platform-convergence-v1`。
- HEAD：`7019d031ef81c00ca5e812f7910278d291d1f841`（`fix(data): close Task 7 repair and timezone gaps`）；2026-08-04 只读复核时 worktree clean。
- 该候选包含 `backend/app/data_sync/` 的深 Module、manifest/checkpoint 和 verified-local-query 设计，但没有进入上述 `main@56d4810` 用户运行面，也未获得切换、promotion 或正式数据写入授权。
- 本轮 `stock_instruments` 文档修复没有启动/重启服务、访问外部数据源、运行 RC、修改正式数据、切换 `3011/3018` 或执行 promotion。因此下列数据集的最高合法状态仍以各自条目为准；历史 canary 只绑定其固定提交和隔离坐标。

## 4. 数据集开发记录

### 4.1 `stock_daily`

#### 目标与来源

- 真实生产者：现有 TickFlow SDK。
- 固定调用语义：`kline.daily.batch`、`period=1d`、`adjust=none`、`as_dataframe=False`、`show_progress=False`。
- GitHub 情报：`shy3130/tickflow-stock-panel` 提供宿主和 TickFlow 工程背景；`simonlin1212/a-stock-data` 等只作字段与来源交叉情报，不是运行时依赖或 fallback。

#### one-trading 自有实现

- 首次深 Module：`1b776fb1d7e7836a05743ded1f0bb0164e2cb74c`。
- 原子 snapshot 修复：`94fc8e94a623161b9a70834beb314bc6d73240ed`。
- 当前相关 closeout：`7019d031ef81c00ca5e812f7910278d291d1f841`，补齐 repair window、上海业务日期和 job/cache 终态缺口。
- Adapter：`backend/app/data_sync/adapters/tickflow_stock_daily.py`。
- Module：`backend/app/data_sync/datasets/stock_daily.py`。
- 兼容入口：`backend/app/data_sync/sources/stock_daily.py`、`backend/app/services/kline_sync.py`、`backend/app/api/kline.py`、`backend/app/main.py`。
- canonical：`symbol,date,open,high,low,close,volume,amount`；价格为未复权 CNY，`volume=lot`，`amount=CNY`。
- 发布：多日分区先 stage/reopen/质量验证，再一次切换 immutable generation/current manifest 并推进 SQLite checkpoint。
- 查询：股票历史 GET 只读 verified manifest 的显式 artifact；普通读不得发起外部请求或写 managed data。

#### 已有证据与当前状态

- `94fc8e9` 阶段记录：focused/affected `89 passed`、DataSync `190 passed`、backend `1400 passed, 9 warnings`，以及相关 Ruff、compile、diff check 通过。
- 历史审计的 R07 固定记录：`7019d03` 完整 backend `1530 passed, 1 skipped`、`TZ=UTC` 47 passed、DataSync + Catalog 408 passed，worktree clean。本次文档职责迁移没有重新运行这些代码测试，因此这里只引用该固定证据，不把它写成新执行结果。
- 当前状态：`isolated / not-production`。

#### 验收缺口

- 在固定隔离 `DATA_DIR` 上运行真实 TickFlow canary，并记录 producer 参数、batch/rpm、429/Retry-After、partial 和 no-data 语义。
- 验证目标日期/沪深京覆盖、PK 唯一性、OHLC 关系、volume/amount 单位、异常行隔离、checkpoint 和同参数幂等。
- 验证真实 `/api/kline/daily` 消费 verified local manifest，读取期间零 egress、零 managed-data 写。
- 由用户确认数据质量和使用价值后，才能写为 `accepted`；production promotion 另行授权。

#### 2026-08-04 盘后范围与自选股并集修复

- 用户目标：保留当前 `CSI500` 管道范围，同时保证任何加入自选的股票都会进入盘后日 K 与 enriched 计算，不再因为不属于 CSI500 而长期显示“待数据”。
- 根因证据：`2026-08-03` 盘后任务 `universe_size=500`、日 K 500 行；8 只自选中只有 `301526.SZ` 属于该分区，其余 7 只的 `kline_daily` 和 `kline_daily_enriched` 最近日期均为 `2026-07-31`。
- 实现边界：`backend/app/jobs/daily_pipeline.py` 的标的解析改为“配置范围 + 自选股”的去重并集；不修改当前 `pipeline_universe_scope=CSI500` 偏好，不修改 Provider、schema、Parquet 或前端展示契约。
- 回归测试：`backend/tests/test_daily_pipeline_universe.py` 固定 CSI500 内外各一只自选，验证范围内股票不重复、范围外自选必须加入。
- 自动证据：新增测试 RED 后 GREEN；相关 universe/quality 测试共 10 项通过。真实当前配置只读预览得到 507 只（CSI500 500 只 + 7 只范围外自选），8 只自选缺失数为 0。
- 当前状态：`implemented`。本轮未触发 `/api/pipeline/run`，因此没有写入 8 月 4 日日 K/enriched，也不把页面“待数据 7”写成已消失。
- 后续验收：在用户另行授权实际同步后，确认任务标的数为 CSI500 与自选的去重并集、7 只股票生成目标交易日分区、`/api/watchlist/enriched` 不再返回空指标，并检查质量报告和回滚残留。

#### 2026-08-04 自选股实时快照接入

- 数据边界：`quote_snapshot` 是盘中行情快照，不是 `stock_daily` 或 `kline_daily_enriched` 的正式替代物；本轮只在自选查询时 overlay 实时同名字段，不覆盖正式 `close`、技术指标、manifest 或 checkpoint。
- 当前物理证据：`data/quote_snapshot/asset_type=stock/date=2026-08-04/part.parquet` 覆盖 8 只自选，生产者为 Tencent 公开行情，`fetched_at=2026-08-04T11:39:42.475124+08:00`。午间休市期间该时间不前进属于正常业务时段语义。
- API 契约：`backend/app/api/watchlist.py` 只读取最新快照；快照日期早于 enriched 日期时拒绝 overlay。`change_pct` 从生产者的百分点口径除以 100 后输出为前端比率口径，避免二次乘 100。
- 生命周期修复：`QuoteService.stop(persist=False)` 用于应用运行时清理，热重载/进程退出不再把 `realtime_quotes_enabled` 偏好写成 false；用户显式关闭仍沿用持久化关闭路径。
- 自动证据：实时 overlay、过期快照、快照持久化、公开源全市场和 lifespan 相关测试共 25 项通过；Python compile、目标 Ruff 与 diff check 通过。
- 当前运行面：`GET /api/watchlist/enriched` 返回 `realtime_count=8`、8 行均有 `rt_price/rt_pct/rt_change_amount`；QuoteService 当前 `enabled=true / running=true / mode=full_market`。本轮诊断期间曾显式调用一次 `/api/intraday/refresh` 生成上述实时快照，但没有运行盘后 pipeline，也没有写入正式日 K/enriched 分区。
- 当前状态：实时快照查询与生命周期修复为 `verified`；`stock_daily` 数据集整体仍为 `isolated / not-production`，盘后并集修复仍为 `implemented`，两者状态不得互相替代。
- 回滚：移除 watchlist 快照 overlay 和运行时 `persist=false` 调用即可；已有 quote snapshot 可安全保留或按独立授权清理，不涉及自选记录与正式行情数据回滚。

#### 2026-08-08 自选详情最新行情响应对齐

- 问题证据：`603261.SH` 的正式 enriched 日线截止 `2026-07-31 / close=45.39`，本地 `quote_snapshot` 已有 `2026-08-03..07` 五个后续交易日；自选接口读取最新快照为 `2026-08-07 / 49.11`，K 线详情此前没有消费这些已落盘资产。
- 查询契约：`GET /api/kline/daily` 只读扫描请求范围内、严格晚于最新 canonical 日线的股票快照，并在响应中按日期追加；同日 canonical 优先，历史 `end_date` 之后的快照不会泄漏进响应。
- 单位与来源：快照 `change_pct` 从百分点除以 100 后返回 K 线小数比例；`volume=lot / amount=CNY` 不变。追加行带 `is_quote_snapshot / quote_source / quote_fetched_at / quote_quality_status`，顶层带 `quote_overlay` 汇总，消费者可区分未封账快照与正式日线。
- 持久化边界：该路径零外部请求、零 `kline_daily / enriched` 写入、零 checkpoint/manifest 推进；不会把公开行情快照伪装成正式盘后日线。
- 自动与运行证据：相关后端 `16 passed`；正式 `3018` 返回 5 个追加交易日，最新行和自选接口同为 `2026-08-07 / 49.11 / -1.34 / -2.66% / tencent`。正式 `3011` 弹窗也显示同一最新行且控制台无 error。
- 当前状态：响应消费契约为 `verified / 待用户验收`；`stock_daily` 数据集整体仍保持此前 `isolated / not-production`，本轮不改变数据集 promotion 状态。
- 回滚：移除 `kline.py` 的只读快照合并与响应元数据即可；不需要删除或恢复任何 Parquet、lineage、manifest、checkpoint 或用户数据。

### 4.2 `announcement_events`

#### 目标与来源

- 真实生产者：巨潮资讯 CNINFO。
- 唯一 live transport：`POST https://www.cninfo.com.cn/new/hisAnnouncement/query`。
- 当前范围：沪深北、keyword-scoped、metadata-only；不下载 PDF、正文、附件，不做 OCR 或 lifecycle 派生事实。
- GitHub 情报：`tiantianlaolao/astock-data-toolkit@55b2004` 与 `simonlin1212/a-stock-data@9ed665c` 只提供数据价值、字段和工程情报。

#### one-trading 自有实现

- 深 Module commit：`70982a1465e208108e4d49c48e738c19497a8db9`。
- Adapter：`backend/app/data_sync/adapters/cninfo_announcements.py`。
- Module：`backend/app/data_sync/datasets/announcement_events.py`。
- local-only API：`GET /api/data/announcements`。
- canonical PK：`(source,doc_id)`；`announce_time=Asia/Shanghai_naive`，`fetched_at=UTC_naive`，内容边界为 `metadata_only`。
- 发布和恢复：Task 3 Publisher/ManifestStore、immutable generation/current manifest、SQLite checkpoint；合法空、源失败、同数据二跑、hash 冲突和 checkpoint 失败均保留 prior。

#### 已有证据与当前状态

- 历史 isolated live canary（commit `817f390`）：固定窗口 `2026-07-01..2026-07-30` 为 152 行，PK duplicates=0，URL 日期与上海时间一致，同参数二跑 published=0。
- `70982a1` 阶段记录：focused `72 passed`、DataSync `206 passed`、affected Data Lab/API/runtime `59 passed, 1 skipped`、backend `1417 passed`。
- 上述 live canary 不代表当前 CNINFO 仍返回 152 行，也不代表正式数据已发布。
- 当前状态：`isolated / not-production`。

#### 验收缺口

- 必须在 `stock_daily` 验收后重新固定 live window，验证真实全页分页、限流、动态 orgId 本地映射、北交所/退市覆盖和重复更新。
- 验证 Parquet/manifest、checkpoint、冲突 review 和 local-only API 的零 egress、零写入读取契约。
- 单独确认 CNINFO 数据使用权、SLA 和 metadata 保存边界。

### 4.3 `stock_instruments`

#### 目标、GitHub 情报与真实生产者

- 目标：形成可重复更新、失败保旧、可追溯且只由本地 verified manifest 消费的沪深京股票证券快照；不把当前静态表冒充历史 Universe、退市事实或 accepted 数据集。
- 直接服务来源：TickFlow SDK/API 的 `exchanges.get_instruments(exchange, instrument_type="stock")`。`shy3130/tickflow-stock-panel` 提供宿主和调用链；`handsomejustin/easy_tdx` 提供 TDX 协议/失败情报；AKShare 提供上交所、深交所、北交所官方列表端点与字段交叉核验。三个仓库都不是当前 Parquet 的数据权利方。
- 上游固定点和详细字段、分页、许可证与采用边界见 `/Users/simon/Trading/数据台GitHub项目借鉴记录.md#21-stock_instruments-相关固定审阅记录2026-08-04` 与 `/Users/simon/Trading/数据台GitHub项目数据能力目录.md#21-stock_instruments-当前来源对照as_of-2026-08-04`。

#### 当前用户运行面与物理快照（as_of 2026-08-04）

- 运行代码：`main@56d4810` checkout 中的 `backend/app/services/instrument_sync.py`；工作日盘前任务和盘后管道都由 `backend/app/jobs/daily_pipeline.py` 调用它。
- 调用与发布：逐市场请求 SH/SZ/BJ，展平 SDK `ext` 字段后直接写 `/Users/simon/Trading/one-trading/data/instruments/instruments.parquet`；当前路径没有 stage、immutable generation、current manifest、checkpoint 或对应 lineage sidecar。
- 物理证据：文件修改时间 `2026-08-04 09:21:58 +0800`、大小 `180,596` bytes、共 `5,539` 行/`5,539` 个唯一 symbol；SH `2,310`、SZ `2,896`、BJ `333`，type 全为 `stock`，name/symbol 及当前 13 个字段均无空值。
- 时间与 schema：`as_of` 全部为 `2026-08-04`；物理 `listing_date` 为 `String`，而 Catalog descriptor 声明为 `date`，当前 Catalog `healthy` 不等于该语义已经完成严格验收。
- 只读 API 证据：`GET /api/data/catalog/stock_instruments` 报告 `quality_status=healthy`、`materialized=true`、`serving_ready=true`、`provider=tickflow`、`row_count=5539`；`GET /api/data/source-provenance` 的 `lineage_sources=[]`、`lifecycle=null`、`checkpoint_watermark=null`。
- 最近运行边界：来源追踪显示的最近记录是 `catalog_rescan`（`catalog-3ce4ae30a48e4e40b1dff736202923c7`），它证明目录扫描成功，不是 TickFlow 抓取运行、请求参数或三市场全部成功的 lineage 证据。
- 当前消费者：DuckDB/Polars `instruments` 视图、标的搜索、盘后 Universe 解析和策略/监控名称映射仍可读取该物理快照；“当前可服务”只证明这些现有消费者能读，不代表 verified-manifest 契约已接管。
- 现有风险：任一交易所异常只记录 warning；只要其他市场有数据，旧代码仍会覆盖完整文件，可能把部分市场结果写成新快照。直接 `write_parquet` 和盘后名称补全也会原位覆盖，缺少失败保旧、原子替换、hash、lineage 与幂等运行证据。

#### 2026-08-05 部分市场覆盖故障、门禁修复与正式目录恢复

- 用户可见故障：`2026-08-05` 盘前任务中 SH 返回 `2,310` 只、SZ 请求超时、BJ 返回 `333` 只；旧同步器仍把 `2,643` 行候选覆盖到正式 `data/instruments/instruments.parquet`，随后公开源全市场行情只请求到 SH/BJ 目录。8 只自选仍完整保留，但只有 `600756.SH` 属于沪市，页面一度显示“实时 1、待数据 7”。
- 日志证据：`2026-08-05 12:12:30 +0800` 记录 `get_instruments(SZ) failed: ... timed out`，随后 `12:12:33` 仍记录 `instruments synced: 2643 rows`，盘前 job 被标成成功。受损物理快照为 SH `2,310`、SZ `0`、BJ `333`，`as_of=2026-08-05`。
- 写入保护：`backend/app/services/instrument_sync.py` 新增逐市场成功/空结果/异常判定、symbol/code/exchange/PK 校验、首次或修复候选至少 `5,000` 行且 SH/SZ/BJ 非零、有健康 prior 时总量至少 `95%` 且各市场至少 `90%`。失败结果固定为 `kept_prior / failed_before_publish`，不得更新正式文件。
- 发布方式：通过 `backend/app/services/atomic_io.py::atomic_write_parquet` 在同目录临时文件完成后 `os.replace`；成功发布写入 `stock_instruments_v1` lineage。名称补全路径也改为原子写入，不再直接覆盖。
- 任务语义：`backend/app/jobs/daily_pipeline.py` 只在 `published` 时刷新 instruments view/cache；保留旧快照时返回 `quality.ok=false`、市场计数、失败交易所与 error code，JobStore/Catalog 记录为 `degraded`，不再显示伪成功。`backend/app/main.py` 会把结构化 `error_code/error_message` 镜像到同步运行记录。
- 实时兜底：`backend/app/services/quote_service.py` 在公开源全市场和范围 fallback 两条路径都调用 `resolve_symbols(..., include_watchlist=True)`；完整自选来自 `data/user_data/watchlist.parquet`，与本地全市场目录去重并集，不使用只取前 5 只的 Free/watchlist 指标函数。
- 回归测试：`backend/tests/test_instrument_sync_guard.py` 固定 SZ timeout、prior 覆盖率坍塌、受损 prior 由完整候选恢复、任务降级不刷新四条路径；`backend/tests/test_quote_service_watchlist_union.py` 固定 8 只完整自选必须进入公开源请求；Catalog writer fixture同步改为三市场完整候选。相关调用链 `44 passed`；新文件目标 Ruff、Python compile 与 `git diff --check` 通过。
- 后端广测：隔离空 `DATA_DIR` 全套为 `274 passed, 1 skipped`，仅两个明确依赖现有本地财务/股票数据的测试在空目录失败；这两个测试随后在只读正式数据上单独 `2 passed`，没有把空目录失败算成代码回归。
- 隔离真实 canary：`/tmp/one-trading-instruments-canary.BgyCda` 在 240 秒硬超时内通过 TickFlow 取得 `5,539` 行，SH `2,310`、SZ `2,896`、BJ `333`；symbol 全部唯一，必需字段齐全，symbol 后缀与交易所一致，无空名称，8 只自选全部存在。候选 SHA-256 为 `63cce8510fd47f33aa3b9c4b57371fc694d03aeaa5fe122d25f3883cc372a4c8`。
- 正式写入前备份：`/Users/simon/备份/codex/20260805_144158-one-trading-instruments-partial-overwrite-repair`；原目录 `/Users/simon/Trading/one-trading/data/instruments`。受损原文件和备份 SHA-256 均为 `c033af7448ea881073045d029cc363f1d7db270ebb1aaae948744535bd9372e8`，README 明确标注它是受损现场、不是健康快照。
- 正式恢复：门禁代码对正式 `DATA_DIR` 重新执行同一真实同步，结果 `published`、`5,539` 行、三市场计数同 canary；正式文件 SHA-256 与 canary 完全一致。lineage run 为 `instruments-bb082734467745f7a7b9a80b904fa903`，Catalog rescan 报告 `healthy / serving_ready / row_count=5539 / lineage=tickflow`。
- 目标运行面：后端热重载后的工作进程 PID `34613` 启动于 `2026-08-05 14:43:41 +0800`，启动日志确认 `instruments 缓存已加载: 5539 只`。修复前公开源请求为 `2,647` 只；仅消费兜底生效、目录尚未恢复时为 `2,654` 只并返回 `2,317` 只股票，精确补入 7 只深市自选；目录恢复后首轮请求 `5,543` 只（`5,539` 股票 + 4 核心指数），返回 `5,206` 只股票。
- Codex 内置浏览器：`/watchlist` 显示“自选股数量 8 只、实时 8”，8 行均有名称和实时价格；`/data -> 来源追踪 -> Stocks` 显示“质量健康、当前可服务、最新 2026-08-05、lineage：tickflow、证据链无告警”。控制台只有既有 React Router v7 future-flag warning，无本次错误。
- 当前状态：`canary / 待用户验收`。已完成代码、失败路径、隔离真实源、正式文件恢复、目标运行面和用户主路径验证；Catalog `lifecycle` 仍未登记，本条不声明 `accepted / production`。
- 剩余边界：下一次真实 SZ/SH/BJ 失败是否在工作日定时任务中显示 `degraded + kept_prior`，仍需后续自然调度观察；这不影响本轮已由确定性回归测试证明的失败保旧逻辑。首轮公开实时返回 `5,206` 只，恰为 SH+SZ 数量，BJ `333` 只仍没有获得该公开实时源返回；当前8只自选不含BJ，本轮没有把该既有来源边界写成已解决。不得通过降低 `95%/90%` 门槛来消除告警。

#### 隔离候选实现（未进入当前用户运行面）

- worktree/commit：`/Users/simon/Trading/one-trading/.worktrees/data-platform-convergence-v1@7019d031ef81c00ca5e812f7910278d291d1f841`。
- 自有 Adapter：`backend/app/data_sync/adapters/tickflow_instruments.py`；Module：`backend/app/data_sync/datasets/instruments.py`；统一支持 `stock_instruments`、`etf_instruments`、`index_instruments`，但按 dataset 使用独立 manifest/current/checkpoint。
- Adapter 会把任一市场失败或非法行归类为 `partial/failed/unavailable/rate_limited`；Module 对非 `ok` fail-closed，并保留 prior。canonical 要求 symbol/name/source_id 非空、market 与 symbol 后缀一致、无跨资产行和 PK 重复。
- 发布门槛：首次候选至少 `5,000`，SH/SZ/BJ 均非零；有 prior 时总量至少 prior `95%`、各市场至少 prior `90%`；通过 Publisher 写 immutable generation/current manifest 并在同一受控事务推进 checkpoint。
- 历史提交：`b4bc1e6` 建立 reference universe Module，`c1ab883` 完成 manifest consumer 迁移，后续修复直到 `7019d03`。历史宽测试记录见本日志其他条目；本次文档修复没有重新运行 instruments 专项测试或真实源 canary。
- 当前状态：`isolated / not-production`。候选代码存在不等于当前 5,539 行已经由该 Module 发布，也不等于用户运行面已切换。

#### 验收缺口与下一步边界

- 按 `/Users/simon/Trading/数据台下一步工程工作计划.md#d-p2-01-stock_instruments-独立验收` 保持 `parked`；在前序数据集结束前不访问真实源、不写正式 `DATA_DIR`、不启动 promotion。
- 开始前先确定目标分支/commit/worktree/隔离 `DATA_DIR` 和运行身份，并明确把 `7019d03` 候选集成到目标运行面还是重新实现；不得把旧物理文件直接登记为 verified manifest。
- canary 必须证明 SH/SZ/BJ 三市场同次完整成功、北交所与退市/状态边界、PK/schema/字段类型、总量和分市场 prior 比例、失败保旧、同参数幂等、checkpoint 与 lineage 对准实际 artifact。
- 修正或显式迁移 `listing_date` 到 canonical `date`；确认总/流通股本、最小价差和涨跌停价格的单位、空值及业务日期语义。
- 验证真实产品消费者只读 verified manifest，读取期零 egress、零 managed-data 写；再由用户确认数据质量和使用价值后才能写为 `accepted`。`production` 仍需另行授权和目标运行面验证。

### 4.4 `etf_instruments`

- 真实生产者：TickFlow `exchanges.get_instruments(exchange, instrument_type=etf)`。
- 与股票分表、独立 manifest/current/checkpoint；PK 为 `symbol`，候选要求完整 source snapshot、非空、asset/schema/PK 合法。
- 当前状态：`isolated / not-production`。
- 不得因 `stock_instruments` 通过而自动 promotion；必须独立验收 SH/SZ 资产路由和本地消费。

### 4.5 `index_instruments`

- 真实生产者：TickFlow `exchanges.get_instruments(exchange, instrument_type=index)`。
- 与股票/ETF 分表、独立 manifest/current/checkpoint；PK 为 `symbol`，候选要求完整 source snapshot、非空、asset/schema/PK 合法。
- 当前状态：`isolated / not-production`。
- 必须独立验证指数代码路由、搜索/API structured unavailable 语义和本地消费价值。

### 4.6 `trading_calendar`

- 真实生产者：深交所官方 monthList HTTPS endpoint。
- canonical PK：`(exchange,trade_date)`；字段为 `exchange,trade_date,is_open,session_type,open_time,close_time,source,as_of`。
- SH/SZ/BJ 行均明确记录为从同一 SZSE 现金市场日历假设扩展，不冒充各交易所独立 official facts。
- 自有 Adapter/Module：`backend/app/data_sync/adapters/szse_calendar.py`、`backend/app/data_sync/datasets/trading_calendar.py`。
- Task 7 时间线：
  - `b4bc1e6`：reference universe 初始收敛。
  - `c1ab883`：manifest consumer 完整性。
  - `a45a8a8`：calendar unavailable fail-closed。
  - `d253752`：verified calendar pipeline preflight。
  - `d49c57d`：end-to-end calendar authorization。
  - `49a31b2`：Shanghai date 与 skipped cache gate。
  - `7019d03`：repair pipeline 与 timezone closeout；它取代“49a31b2 是最终修复”的旧文档表述。
- `49a31b2` 记录为 DataSync + Catalog `406 passed`、backend `1521 passed, 1 skipped, 9 warnings`；后续历史审计 R07 对 `7019d03` 记录为 backend `1530 passed, 1 skipped`、`TZ=UTC` 47 passed、DataSync + Catalog 408 passed。本文档迁移没有重新运行代码测试。
- 当前状态：`isolated / not-production`。
- 验收必须覆盖真实 SZSE endpoint、历史/未来窗口、临时休市与修订、沪深京同日历假设、license/SLA、fail-closed pipeline 和正式消费者。

### 4.7 `ext_fund_flow_stock`

#### 目标、生产者与数据契约

- 用户目标：修复“个股分析 -> 资金分析”点击“获取资金流”后出现 `Server disconnected without sending a response.`，并确认页面数据的真实来源。
- 真实生产者：东方财富公开个股资金流；不是 TickFlow、GitHub 仓库或交易所官方资金流。
- 主请求：`https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get`；安全同源备用请求依次包含东方财富 H5 `https://emdatah5.eastmoney.com/dc/ZJLX/getDBHistoryData`、`push2delay` 与 `push2` HTTPS host。所有请求继续使用相同 `secid`、`lmt`、`klt=101` 和字段契约，不降级到明文 HTTP。
- canonical：`symbol,date,main_net,small_net,med_net,large_net,super_net,main_net_pct,source,unit_amount`；金额单位固定为元，`source=eastmoney_fflow`。
- 外部刷新仅由用户点击 POST 触发；普通 GET 只读本地缓存，不在浏览页面时自动访问外部源。

#### one-trading 自有实现与本地缓存

- Provider：`backend/app/services/free_sources/fund_flow.py::fetch_stock_fund_flow`。
- API：`POST /api/free/fund-flow/stock/{symbol}/refresh` 获取并保存；`GET /api/free/fund-flow/stock/{symbol}` 只读缓存。
- 本地资产：`data/ext_data/ext_fund_flow_stock/timeseries/date=YYYY-MM-DD/part.parquet`。
- 根因：原实现只访问 `push2his.eastmoney.com`；对端 HTTPS 连接被提前关闭、握手超时或返回 502 时，请求直接失败，前端只是如实显示后端 502 detail。
- 修复：为各 HTTPS host 使用独立 resilience key、5 秒超时和短冷却；连接、HTTP、空 payload 或无有效行时继续同生产者备用 host；全部失败时返回中文、来源明确的可恢复错误，既有缓存仍可读取。
- 回归测试：`backend/tests/free_sources/test_fund_flow.py` 新增主 host 断连后切换 H5 host、全部 host 失败错误语义两项覆盖。

#### 2026-08-04 正式运行面 canary 与数据核对

- 自动检查：资金流 focused suite `13 passed`；测试文件 Ruff 与 Provider `B023` 检查通过；`git diff --check` 通过。
- 真实源：`000636.SZ` 在主 host 不稳定时由东方财富 H5 HTTPS 接口取得 120 个交易日；首日 `2026-02-02`，最新日 `2026-08-03`。
- 正式 API：运行中的 3018 POST 返回 `200`、`rows=120`；3011 前端代理 GET 返回最近 60 行且 `cached=true`。
- 写入前备份：`/Users/simon/备份/codex/20260804-113105-fund-flow-stock-before-live-refresh`，原始目录为 `/Users/simon/Trading/one-trading/data/ext_data/ext_fund_flow_stock`。
- 写后校验：目标股票 120 行、120 个唯一日期，来源仅 `eastmoney_fflow`、单位仅 `yuan`；备份前已有的其他股票 120 行与刷新后逐字段一致，未发生非目标数据变化。新增 `2026-08-03` 分区使 timeseries 文件数从 120 变为 121。
- Codex 内置浏览器：`/stock-analysis?symbol=000636.SZ&name=风华高科` 正常显示最新 `08-03`、主力净流入 `+3.54亿`、主力净占比 `+3.85%` 和“东财公开资金流 · 单位元”；再次点击“更新”成功，控制台无本次错误。
- 当前状态：`canary / 待用户验收`。已证明当前正式本地运行面和目标股票主路径恢复，但不把一次个股 canary 扩大为全市场 SLA 或 `accepted / production`。
- 剩余风险：若东方财富全部 HTTPS 个股资金流入口同时不可用，本轮不会伪造或清空数据；接口会返回中文来源错误，页面仍可保留并展示既有缓存。

### 4.8 `stock_margin_trading`

#### 目标、来源情报与边界

- 用户目标：按照 go-stock 本轮 F10 情报，先补一个价值高、日期粒度和单位较清楚的数据集，并在数据分栏中加入对应业务；本轮只实施融资融券，不连带展开大宗交易、股东户数、龙虎榜、机构预测、基金、新闻或市场情绪。
- 真实生产者：东方财富 `RPT_RZRQ_STOCKS_DETAIL`；运行时为单源，没有伪造 fallback。go-stock 只提供请求参数、字段名称和展示语义情报，不是生产者、运行时依赖或本地快照兜底。
- 当前状态：`canary / 待用户验收`。正式 `DATA_DIR` 已有受控自选股样本和真实运行面，但没有获得 `accepted / production` 用户验收，也未加入自动调度或全市场采集。

#### one-trading 自有闭环

- Adapter：`backend/app/services/free_sources/margin_trading_public.py`；显式分页、A 股 symbol 规范化、整批先取后写、失败保旧、原子 Parquet 替换与 lineage 均由 one-trading 持有。
- canonical PK：`symbol + trade_date`；金额字段统一为人民币元，融券数量统一为股，`unit_version=stock_margin_trading_v1`。`point_in_time=false`，因此不把当前公开端点历史返回冒充严格 PIT 数据。
- 字段：融资余额、融资买入额、融资偿还额、融资净买入额、融券余额、融券卖出量、融券偿还量、融券余量与两融余额。
- 物理产物：`data/f10/stock_margin_trading/part.parquet`；lineage 位于 `data/lineage/stock_margin_trading/`。当前为单文件原子 upsert，没有另建 manifest/checkpoint；重复同步按主键保留最后值且不增加重复行。
- API：`GET /api/f10/margin-trading` 只读本地 Parquet、查询时零外部请求；`POST /api/f10/margin-trading/sync` 是显式外部采集入口，成功发布后只刷新该数据集目录，错误响应不泄露上游 body。
- Catalog/来源披露：新增 `stock_margin_trading` schema、`f10` 存储分类、EastMoney 真生产者、go-stock 数据集级接口情报说明，以及清除本地数据时的 `f10` 管理范围。

#### 质量、canary 与正式数据

- 隔离真实 canary：`/tmp/one-trading-margin-canary-i3pug5l_`，标的 `600519.SH / 300502.SZ`，共 200 行；PK 唯一、关键键无空值、最新日期 `2026-08-04`、Catalog `healthy`、lineage source=`eastmoney`。
- 恒等式：`两融余额 = 融资余额 + 融券余额` 的最大绝对误差约 `0.0000018` 元；`融资净买入 = 融资买入 - 融资偿还` 最大绝对误差为 `0` 元。
- canary 揭示 `300502.SZ` 在 `2026-06-11` 的 `LOAN_REPAY_VOL=-74,524`。相邻日满足 `212,760 + 13,000 - (-74,524) = 300,284`，证明该列是允许负值的有符号调整量；修复只放宽这一列，余额、卖出量、余量和金额字段仍保留非负与恒等式质量门，并用真实边界回归测试锁定。
- 正式发布范围：当前 8 只自选股，`1,886` 行、8 个唯一 symbol，覆盖 `2025-07-24..2026-08-04`，PK 唯一，source 仅 `eastmoney_rzrq`，unit version 仅 `stock_margin_trading_v1`。
- 正式 lineage：`lineage/stock_margin_trading/date=2026-08-04/margin-3755161f56f04b30b1a795aa7ba5b0e5.json`；浏览器再次同步 `600756.SH` 后仍为 `1,886` 行，证明当前主路径幂等。
- 发布前备份：`/Users/simon/备份/codex/20260805-161926-one-trading-stock-margin-trading-before-publish`；原控制目录 `/Users/simon/Trading/one-trading/data/control`。发布前 F10 数据与对应 lineage 目录不存在，README 已明确记录首次新增边界。

#### 自动检查与目标运行面

- 后端全量：`287 passed, 1 skipped`；本轮相关后端复检 `79 passed`，新增/相关文件 Ruff 通过，`git diff --check` 通过。跳过项与两条警告为既有 integration mark/Polars sortedness 提示。
- 前端全量：20 个测试文件、82 项通过；ESLint 无 error，生产构建通过。保留项目既有 Hook、React Router future flag、混合动静态导入和 bundle 大小提示。
- 真实后端：`127.0.0.1:3118`，重启后进程 PID `52877`，启动日志于 `2026-08-05 16:28:45 +0800` 报告 application startup complete；`GET /api/f10/margin-trading?symbol=300502.SZ&limit=2` 返回 200 和本地行。
- Catalog：数据集数从 24 增至 25；`stock_margin_trading` 报告 `healthy / local_materialized / serving_ready / 1,886 rows / 8 symbols / latest=2026-08-04`，存储分类 `Stock F10` 为 1 个文件约 68 KiB。
- Codex 内置浏览器：`http://127.0.0.1:3111/data` 实测独立“股票 F10”分组、个股融资融券目录卡、采集同步卡、幂等同步成功提示和来源追踪；真实生产者为 EastMoney public endpoints，go-stock 详情没有“本地快照兜底”角色。页面无本轮 error，仅有既有 React Router v7 future flag warning。

#### 剩余风险、回滚与下一步

- 东方财富公开端点仍有频率、字段漂移、访问权利和 SLA 风险；当前门禁会失败保旧，但不把单次自选股 canary 扩大成全市场稳定性结论。
- 当前只覆盖用户明确触发的股票；在用户确认数据价值、频率和保留年限前，不加入盘前/盘后自动调度，也不启动全市场 5,539 只采集。
- 回滚：停止使用新增 API/界面入口，移除 `data/f10/stock_margin_trading` 与对应新增 lineage，再用上述备份恢复 `data/control`；不会影响自选记录、日 K、财务表或实时行情。
- 下一步必须由用户在本数据集验收后再选择；本轮不自动进入大宗交易、股东户数、龙虎榜或机构预测。

### 4.9 `kline_historical_date_alignment`

#### 目标、接口契约与失败语义

- 用户目标：自选股详情点击某一天 K 线后，日 K、筹码分布和分钟数据必须使用同一个交易日；不得把公开源提供的最新分时冒充历史日分时。
- `GET /api/free/chips/{symbol}` 新增可选 `as_of=YYYY-MM-DD`；本地 `kline_daily_enriched / kline_daily` 先过滤 `date <= as_of`，再取最近 `days` 根进行既有换手衰减推算。响应新增实际最后交易日 `as_of`，`current` 来自该日收盘价。
- `GET /api/kline/minute` 在公开源转换、单股 Provider 返回和 API 出口三处执行交易日门禁。行日期与请求日期不同就丢弃并返回 `source=none / rows=[]`，前端显示“该日暂无分钟数据（数据源未提供）”。
- 该契约不新增历史分钟数据；无分钟权限或无本地历史数据时保持诚实空态。筹码仍为 `local_daily_derived / approx_turnover_decay_vwap_kernel`，不是交易所官方筹码峰。

#### 自动检查、真实接口与运行面

- 后端相关 4 个测试文件、9 项通过，覆盖筹码 `as_of` 截断、实际截止日、公开分时错日拒绝和 API 最终门禁；Python 编译与本轮新增代码检查通过。历史大文件仍保留既有 Ruff 格式债务，本轮未批量改写。
- 正式 `3018` 接口复验 `301526.SZ / 2026-07-20`：筹码返回 `as_of=2026-07-20 / current=26.70 / source=local_daily_derived`；分钟返回 `date=2026-07-20 / source=none / rows=0`。
- 正式 `3011` 页面点击同日蜡烛后，日 K、筹码截至日期与诚实分钟空态一致；截图位于 `/Users/simon/.codex/visualizations/2026/08/05/019fd0f2-2d5f-7250-ab6e-546203a0daf2/10-historical-date-alignment-fixed.png`。控制台无本轮 error，仅有既有 React Router future flag warning。
- 当前状态：`canary / 待用户验收`。本轮修改查询语义但没有写入、迁移、删除或重算任何正式 Parquet、缓存与控制库。

#### 回滚与剩余风险

- 回滚：移除筹码 `as_of` 参数和日线截止过滤，恢复分钟公开回退旧语义，并同步移除前端日期参数；不涉及数据文件恢复。
- 当前免费公开分时只稳定提供当日或最近交易日；若用户需要任意历史日真实分钟曲线，仍需独立补齐合法、可持续的历史分钟数据源与本地落库，不应放宽本轮错日门禁。

### 4.10 `stock_minute` watchlist on demand

#### 目标、边界与 GitHub 固定情报

- 用户目标：不预采全市场分钟数据；只在用户点击自选股某个历史交易日 K 线时读取该 `symbol + trade_date`，质量通过后保存到数据台，后续点击只读本地。
- 主台 GitHub 记录：`/Users/simon/Trading/数据台GitHub项目借鉴记录.md#handsomejustineasy_tdx数据台完整记录2026-08-06-增补-stock_minute-canary`；固定上游点 `handsomejustin/easy_tdx main@513ee15c83ca14b81de1b2890c2369b6456bc864 / 1.20.6`。
- 真实生产者是公开 TDX 行情服务器池；easy_tdx 是 TCP 协议客户端，不是数据权利方。当前不声明 SLA、商业数据权利、北京市场或全市场历史覆盖。
- 非目标：不改全市场 `/sync_minute`，不做 5,539 只预采，不做后台自动调度，不把价格曲线冒充真实分钟 OHLC，不改变筹码分布推算。

#### 本地运行坐标、Module、schema 与存储

- 运行坐标：`main@56d481076c008efca9ff40db8f5c89139bb7f600`，worktree `/Users/simon/Trading/one-trading`，正式 `DATA_DIR=/Users/simon/Trading/one-trading/data`；后端 reload 主进程 PID `68616`，实际 worker PID `86214`，端口 `3018`。
- 依赖：`backend/pyproject.toml` 与 `uv.lock` 固定 `easy-tdx==1.20.6`。
- Provider Adapter：`backend/app/services/free_sources/tdx_history_minute.py`；只接受 `.SH/.SZ`，按 YYYYMMDD 获取 `datetime/price/vol`。
- 数据集 Module：`backend/app/services/kline_sync.py::validate_historical_minute / persist_historical_minute`；API seam 为 `GET /api/kline/minute?symbol=...&date=...`。只有本地自选股且日期早于今天才进入按需写路径，非自选股和今天保持即时读、不落历史缓存。
- canonical：`symbol,datetime,open,high,low,close,volume,amount`；上游为分钟价格曲线，OHLC 同值。TDX volume 单位为手，amount 为 `price * volume * 100` 的估算值，并在 lineage 明确 `amount_semantics=estimated_price_times_volume_lots_times_100`。
- 正式产物：`data/kline_minute/date=2026-06-29/part.parquet`；lineage 为 `data/lineage/kline_minute/date=2026-06-29/a2da3d89ac424b7a8d4651cf8d00f49c.json`，`source=tdx_public / adapter=easy_tdx_1.20.6 / unit_version=canonical_minute_v1 / scope=watchlist_on_demand`。

#### 质量门、canary、失败语义与幂等

- 发布前必须满足：请求日完全一致；canonical 非空；216..242 点；时间唯一且只在 A 股交易时段；价格为正、成交量非负；本地同日日 K 存在。
- 日线对账：最后分钟价相对原始日收盘误差不超过 `0.5%`，分钟量合计相对日量误差不超过 `1%`，分钟估算成交额相对日成交额误差不超过 `5%`；任一失败都不创建或覆盖正式 Parquet。
- 真实 canary `301526.SZ / 2026-06-29`：240 点，`09:30..14:59`；末价 `47.82 = raw_close 47.82`；量合计 `2,245,847 = 日量 2,245,847`；估算额 `10,814,650,451` 元对日额 `10,823,434,410` 元，误差约 `0.081%`。
- 首次正式接口约 `8.74s`，返回 `source=local / provider=easy_tdx_1.20.6 / persisted=true / rows=240`；第二次约 `0.015s`，只返回本地 240 行，Parquet SHA、mtime 与 lineage 数量均未变化。
- 写入使用进程内分区锁、按 `symbol+datetime` upsert 与原子替换；相同数据二跑 `rows_added=0`。日期错配、收盘/量/额不一致和 TDX/兜底异常均返回诚实空态，不写坏数据。

#### Catalog、自动检查、目标运行面与清理

- `stock_minute` 已标记 `coverage_policy=on_demand`，不再拿全市场 5,539 只作为覆盖目标。最终目录为 `healthy / local_materialized / serving_ready / provider=public / 240 rows / 1 symbol / 1 day / expected_symbol_count=null / scan_errors=[]`。
- 后端相关与目录/来源回归共 `44 passed`；新增文件目标 Ruff `E/F/I` 通过。前端 `pnpm build` 通过，保留既有混合动静态导入和大 bundle 提醒。
- Codex 内置浏览器正式 `http://127.0.0.1:3011/watchlist`：点击 `2026-06-29` 后左右标题均为同日；右侧呈下跌曲线，末点 `47.82`，不再出现 Pro+ 全市场分钟同步错误。控制台无业务 error，仅有既有 React Router v7 future flag warning。
- 写入前备份：`/Users/simon/备份/codex/20260806-003524-one-trading-watchlist-minute-canary`，原路径为 `data/kline_minute` 与 `data/control/catalog.sqlite3`。浏览器定位时产生的 `2026-06-30 / 2026-08-05` 验证缓存及 lineage 已移出正式目录并保存在该备份的 `verification-residue/`；正式目录最终只保留目标日。

#### 当前状态、回滚与下一步

- 数据集状态：`canary / 待用户验收`；尚未提升为 `accepted` 或 `production`，也未加入自动调度。
- 回滚：停止使用按需 Adapter，恢复 API 只读/即时回退；将目标 Parquet 与 lineage 移出正式目录并用上述备份恢复 Catalog。自选列表、日 K、筹码和其他数据集不受影响。
- 下一步只在用户验收后决定：继续维持点击即取，或补充更多自选股/历史日期 canary；不得自动扩成全市场分钟库。

### 4.11 `market_pulse`

#### 目标、真实生产者与来源情报

- 用户目标：为看板提供“指数分时 + 分钟成交额 + 板块异动”的同日时间轴，并支持本地复盘；一次只实现这一个数据集，不把 go-stock 整套系统搬入主项目。
- 真实生产者：财联社公开市场端点。`https://x-quote.cls.cn/quote/index/tline` 以 `date=YYYYMMDD` 返回上证指数分钟点；`https://www.cls.cn/v3/transaction/anchor` 以 `cdate=YYYY-MM-DD` 返回板块事件。go-stock 只提供端点、字段、单位和交互情报，不是生产者、数据权利方、fallback 或运行时依赖。
- 上游代码情报见 `/Users/simon/Trading/用户台GitHub项目借鉴记录.md#2026-08-10-市场脉搏产品形态采用`；数据字段、权利和风险短卡见 `/Users/simon/Trading/数据台GitHub项目数据能力目录.md#market_pulse-数据集级短卡2026-08-10`。

#### one-trading 自有 Provider、schema、存储与查询

- Adapter/Module：`backend/app/services/free_sources/market_pulse_public.py`；公共 Provider manifest 与类型化操作位于 `backend/app/data_providers/public_provider.py`；API 为 `backend/app/api/market_pulse.py`。
- canonical PK：`trade_date + record_type + event_id`。一分钟点或一条板块事件占一行；字段包括基准指数、点位、逐分钟变化小数比例、昨收/开盘、成交量/额和板块代码/名称/方向/article_id。`event_time=Asia/Shanghai`，`last_price/preclose/open=指数点`，`change_ratio=ratio`，`volume=股`，`amount=CNY`，`unit_version=market_pulse_v1`。
- 正式产物：`data/market/pulse/date=2026-08-10/part.parquet`；lineage 为 `data/lineage/market_pulse/date=2026-08-10/market-pulse-47ba27b7f69d420e84e3d37b6667ac77.json`。
- `GET /api/market-pulse?trade_date=...` 只读本地 Parquet；不存在时返回诚实空态。`POST /api/market-pulse/sync` 是唯一外部采集/写入口；成功原子发布后只刷新 `market_pulse` 目录。
- Catalog/来源追踪：dataset/provider/operation=`market_pulse/public/market_pulse`，存储分类为 indices；来源链明确显示财联社为真实生产者、go-stock 为 `reference_only_no_gpl_runtime`。

#### 质量、失败语义、隔离 canary 与正式数据

- 质量门：两个 payload 必须等于请求日期；PK 和分钟唯一；历史分钟数 216..242；时间只在 A 股交易时段；价格正、量额非负；事件方向只允许 `up/down` 且板块代码/名称非空。空、错日、字段不完整、未来日期或上游失败均不发布，不做最近交易日静默回退。
- 隔离 canary 位于系统临时目录 `market-pulse-canary-vdxavfry`；对 `2026-08-10` 连续同步两次均为 241 个分钟点、22 条事件、263 个唯一 PK，Parquet hash 稳定，重新打开并经 local-only query 复核通过。隔离 canary 未修改正式 `DATA_DIR`。
- 正式显式同步同日得到 263 行，只有一个交易日和 `market_pulse_v1`，PK 263/263 唯一；产物 16,607 bytes，SHA-256 `7c6916a86b70ce3e66aa63ce09c79e9538918848056bddf86a6d84dec6e78754`。
- 正式 GET 返回 241 points / 22 events；Catalog 为 `provider_supported / entitled / local_materialized / serving_ready=true`、`quality=healthy`、`row_count=263`、lineage source=`cls`。正式路径此前不存在，因此这是新增资产，没有可备份的旧 market_pulse 数据；没有覆盖其他数据集。
- 用户台切换深证即时指数后再次核验，正式 Parquet mtime、大小和 hash 完全不变，证明即时比较不会回写 owned 数据集。

#### 自动检查与真实运行面

- 后端目录/来源/Adapter/API 相关套件 68 项通过；修正 manifest 后全量 313 项通过。新增覆盖 normalization、错日/质量门、原子发布、local-only GET、显式 POST、目录 refresh 和 provider 单位/历史保证。
- 前端全量 27 个测试文件、106 项通过，TypeScript/Vite 生产构建通过；详细界面行为见工作台日志 `market_pulse_workbench`。
- 正式后端 `127.0.0.1:3018` 的 GET/POST 与 Catalog/来源追踪均复核；正式前端 `127.0.0.1:3011` 在桌面与 375px 运行面完成图表、事件、回放、即时比较、数据页和复盘链路验证，控制台无业务 error。

#### 当前状态、回滚与下一步

- 数据集状态：`canary / 待用户验收`。真实生产者、正式资产、重复同步、local-only API、目录/来源和实际用户台消费均已验证，但没有把 Codex 自验写成用户 `accepted`，也没有加入自动调度或 production promotion。
- 回滚：停止使用新增 API/组件，移出 `data/market/pulse`、对应 `data/lineage/market_pulse` 和新增 Catalog 状态；这是全新目录，不需要恢复旧 market_pulse 资产，也不得删除其他 indices、行情或控制数据。
- 剩余风险：财联社公开端点没有承诺 SLA/商业数据权利，且 tline 当前只证明上证基准。若端点限流、字段漂移或空返回，系统失败保旧；即时比较指数仍是用户显式查询、不写入 owned dataset。
- 下一步仅在用户使用确认后决定是否接受当前数据集；本轮不自动扩展历史批量回补、第二生产者、自动轮询或更多事件域。

### 4.12 `market_snapshot` 全市场行业分析服务视图

#### 目标、契约与边界

- 用户目标：先修复行业分析的数据覆盖，再让热力图消费同一份可信行情；页面不能再把 `CSI500 + 自选股` 的增强日线冒充“全市场行情”。
- 保留 `pipeline_universe_scope=CSI500`，没有修改日线流水线配置、`public_data_scope`、Provider 或调度范围。修复点位于服务视图：`backend/app/services/market_snapshot.py` 以最新持久化 `quote_snapshot` 为主，只在同一交易日用 `stock_enriched` 补充派生指标；两个来源日期不一致时只选更新者，不混日。
- API seam 仍为 `GET /api/screener/market-snapshot`；新增 `as_of/source/fetched_at/scope/quality_status/coverage`，显式返回全市场、分交易所覆盖率和缺口，不再以隐含行数代替完整性说明。

#### 正式数据、质量与完整性

- `2026-08-10` 正式服务视图为 `quote_snapshot+enriched`，返回 5,207 只有价格和涨跌幅的股票；股票基础维表 5,540 只，总覆盖 `93.99%`。
- 分市场：沪市 `2,311/2,311`、深市 `2,896/2,896`，均为 `100%`；北交所 `0/333`。因此当前已经满足沪深全市场行业分析，但不能声称全 A 100% 完整，北交所缺口由 API 和页面覆盖徽标如实展示。
- `change_pct` 从行情快照的百分数转换为页面小数比例；成交量沿用 `cn_quote_v1` 的手，换手率按 `volume * 100 * 100 / float_shares` 生成百分数，市值按价格与股本派生，5 日量比只读取更早的行情快照分区。
- 行业分类 `ext_hy_ths` 在写前从 4,635 行刷新为 5,539 个唯一标的，必填列零空值；层级为 31 个一级、90 个二级、257 个三级行业。与当前股票维表匹配 `5,521/5,540`（`99.66%`），仍有 19 只基础股票未分类、18 条行业源记录不在当前维表。
- 行业与行情交集为 5,193 只，90/90 个二级行业均有可着色行情；热力图行业着色覆盖 `5,193/5,539`（`93.75%`）。未报价标的不按平盘计入行业均值、涨跌家数或龙头。

#### 写入保护、幂等与自动检查

- 写前备份：`/Users/simon/备份/codex/20260810_2112_industry-heatmap-data-fix`；原路径为 `data/ext_data/ext_hy_ths/part.parquet` 和 `data/ext_data/ext_hy_ths/config.json`，README 记录原因、绝对原路径、时间和 SHA-256。没有覆盖其他数据集或配置。
- 只执行 `ext_hy_ths` 单数据集刷新；重复拉取后按排序后的逻辑内容比较完全相等，5,539 行语义幂等。`config.json` SHA-256 保持 `cbc52bd3...` 不变。
- 新增 2 项服务测试覆盖同日宽行情优先、单位换算/派生指标/覆盖率，以及旧行情不得污染较新增强日线。市场快照、K 线行情覆盖、自选增强、单位契约和快照持久化相关 25 项后端测试通过；新增文件 Ruff 通过。
- 正式 `127.0.0.1:3018` 健康检查与快照 API 复核通过；当前快照质量状态为 `intraday_partial`。用户台 `3011` 实际显示 90 个行业、5,539 只标的、行情 `5,207/5,540`、行业着色 `5,193/5,539` 和“盘中快照”。

#### 当前状态、回滚与剩余风险

- 数据集/服务视图状态：`canary / 待用户验收`。沪深行情与全部二级行业已进入真实用户台验证；北交所 333 只行情和 19 只行业映射缺口尚未补齐，因此未写成全 A `accepted` 或 `production`。
- 回滚代码时恢复旧 `/market-snapshot` 实现；回滚行业分类时先移出现有 `ext_hy_ths`，再用上述备份恢复 Parquet 与 config。两者必须独立回滚，不能顺带改动 `stock_daily`、`stock_enriched` 或流水线 scope。
- 下一步如要达到全 A 100%，应单独补北交所行情 Provider/快照和剩余行业映射质量门；本轮不扩大日线流水线、不伪造北交所价格，也不把缺失记录当平盘。

## 5. 平台与事故边界

### 5.1 `shared_market_multiuser_boundary`

- 目标：所有账户只读消费同一套服务器市场数据；用户自选、持仓、策略、报告、偏好、告警和回测历史进入 `DATA_DIR/tenants/<user_id>/user_data`，不得复制或分叉市场 Parquet。
- Interface：`backend/app/services/user_context.py` 绑定请求主体，`authorization.py` 区分管理员写操作、共享市场只读接口和个人写入接口；普通用户的数据目录响应移除路径、运行存储和扫描错误等内部信息。
- as_of 2026-08-12，基底 HEAD `56d481076c008efca9ff40db8f5c89139bb7f600` 加本轮未提交移植：后端全量 393 项通过、1 项跳过；隔离运行面 `127.0.0.1:38118` 中 Alice/Bob 的 `market_pulse` JSON SHA-256 相同，均为 241 分钟/19 事件，而 Alice 的自选和持仓未出现在 Bob 目录。
- 普通用户对 `/api/admin/users`、`POST /api/data/clear`、`POST /api/market-pulse/sync` 均为 403；`/api/data/catalog` 只暴露 managed/shared storage，`operational_bytes=0`。
- 本轮没有迁移或改写正式 `DATA_DIR`，没有同步外部数据，没有部署；临时验收目录已清理。现有市场脉搏、quote snapshot、K 线 overlay 和行业分析数据契约均保留。
- 当前为平台访问边界 `verified`，不改变各数据集原有 lifecycle 状态；真实身份库/PVC 迁移和线上启用需另行备份、部署与验收。

- K4、guard、journal、recovery、inode alias 和生产进程恢复保留在各自事故/审计文档中，不再作为本日志的数据集完成条件。
- 若平台问题阻塞数据集，只记录：阻塞代码、证据链接、是否影响 source/sync/publish/query/acceptance，以及解除阻塞所需的独立授权。
- `PLATFORM_GO`、RC 通过或浏览器打开不能代替任一数据集的 `accepted`。

### 5.2 `zeabur_latest_shared_market_sync_20260812`

#### 目标、运行坐标与隔离边界

- 用户授权把 `/Users/simon/Trading/one-trading` 当前开发版同步到既有 Zeabur `one-trading` service，并明确要求把本地市场数据完整同步，同时保留多用户隔离和每账户独立 Hermes Agent 体系。
- 发布仍从独立 release 树 `/Users/simon/Trading/one-trading-release` 执行；没有把开发 `DATA_DIR`、本地身份库、Session、用户目录、Hermes Runtime、Secret、日志或工作区打进镜像。
- 当前线上 Deployment 为 `6a7c57c70d41a78958bb46a2`，service `6a7618adec01e16bfb324c30`，build `local-sync-20260812-5379302b4970d31a`；公网 `/health` 返回 `200 / status=ok / version=0.1.68 / release_channel=private`。
- 共享市场数据只覆盖明确 allowlist；线上 `control/identity.sqlite3`、`tenants/`、`user_data/`、`hermes/` 与其他运行控制目录原地保留。同步和重启前后身份库均为 `integrity_check=ok / users=1 / sessions=7 / admins=1 / hermes_profiles=1`。

#### 备份、迁移与回滚

- 总备份目录：`/Users/simon/备份/codex/20260812-164436-one-trading-zeabur-latest-sync`；README 记录原因、原始绝对路径、时间、内容与回滚边界。
- 完整停机态线上 PVC 备份：`online-pvc/pre-sync-complete-pvc.tar.zst`，SHA-256 `6db8d221623cded9b4e396ad3077ee30241973c091f5edea40c31d5081358307`，47,379 个成员，zstd 校验通过。完整市场迁移包 SHA-256 为 `175ad8357cf4cab5acab4d0c9ffe6afc80727bfc3c83e0550113208d8a294044`。
- 本地先修复 9 行股票 raw/enriched 缺口；修复后股票 raw/enriched 各 8,064,651 行、1,724 分区，ETF 各 364,882 行、260 分区，三组均为零重复、零 raw/enriched 差集。
- 停服务后向真实 PVC 叠加 37,314 个 allowlist 市场文件，逐文件 SHA 零差异；保留线上已有而本地不存在的 12 个指数分区，没有执行镜像式删除。完整 PVC 与远端 staging 均保留，回滚不依赖重新抓取外部数据。

#### Catalog、lineage 与最终物理事实

- 首次全量重扫主动保留旧快照并标记 `stale=true`，暴露出稳定路径替换后的旧 lineage、QA Parquet、历史无生产者凭据和扫描期间 quote 写入问题；没有把失败扫描伪装成成功。
- `CatalogScanner` 现在只用与当前 artifact 行数匹配的最新 lineage 做 unit admission，同时保留全部历史 lineage 供审计；`coverage.parquet / verification.parquet` 明确是复权 QA 文件而非 material artifact，`financial_shares` 正式契约为 `financial_cn_v2`。
- `scripts/reconcile-legacy-market-lineage.py` 复用 26 个数据集定义与扫描器 ownership/schema/artifact 契约，只为当前文件版本缺少可匹配 lineage 的 artifact 新增 `legacy_local_artifact / degraded` 记录；遇到 schema、竞态或其他非 lineage 错误立即停止。线上 scanner-derived dry-run 固定为 637 条，实际写入分布为 stock 251、ETF 191+191、balance/shares/sealed-L1/adj-factor 各 1；重复 dry-run 为 0。
- 637 条记录在 service 重启后的新 Pod 中仍存在，证明写入 Zeabur PVC；7 个受影响数据集重启后快速扫描均无错误并明确为 `degraded`。
- 2026-08-12 19:53 CST 最终 26 数据集原子重扫完成：19 个 run `succeeded`、7 个 `degraded`、0 个 `failed`，Catalog `stale=false`。质量汇总为 16 healthy、7 degraded、3 个无物理数据的可解释 unknown。
- 最终线上核心事实：stock daily/enriched 各 8,064,651 行、1,724 分区、2019-07-05..2026-08-12；ETF 各 364,882 行、260 分区、2025-07-17..2026-08-11；index 各 238,680 行、400 分区、2024-12-17..2026-08-11；market pulse 1,258 行；quote snapshot 84,353 行、37 文件；lineage 64,838 文件。
- Catalog 报告托管数据 672,637,423 bytes、运行数据 264,824,736 bytes、总量 937,462,159 bytes。Codex 内置浏览器显示 26 项、托管 641 MiB、运行 253 MiB、总量 894 MiB，与 API 字节值一致。

#### 自动检查、真实运行面与状态

- release 树后端全量 `406 passed / 2 skipped`，ruff、`git diff --check`、开发/release 关键文件一致性和 Docker 构建通过；候选容器健康、注册策略和目录修复源码身份均单独验证。
- 真实公网数据 API 在管理员会话下返回 26 项且 `stale=false`，未登录 `/api/data/catalog` 返回 401。Codex 内置浏览器数据总览和数据目录显示上述 stock/ETF/index 行数、刷新时间及 degraded 标签，控制台错误为 0。
- 实时行情在两次全量扫描前保存原值并暂停，最终已恢复 `realtime_quotes_enabled=true`；重启后页面开关为选中，非交易时段等待下一交易窗口。
- 本条记录的是共享市场数据迁移和线上目录的 `production deployment verified`，不会越权把原有各数据集生命周期统一提升为 `accepted / production`；各数据集仍以自己的条目和用户逐项验收为准。

## 6. 后续条目模板

```md
## dataset_name

### 目标与使用价值
### GitHub 情报引用与固定上游点
### 真实生产者、参数、字段、分页、错误和更新
### 本地分支、commit、worktree、DATA_DIR
### Provider/Adapter、schema、sync、manifest/checkpoint、Parquet
### local-only API 与实际消费者
### 数据质量、失败恢复和幂等
### 自动检查与真实运行面
### 当前状态与验收结论
### 阻塞、剩余风险和下一步
```

维护时只追加稳定事实。版本、行数、测试数量、端口、PID 和数据覆盖必须附 `as_of`、commit 和运行坐标；旧记录保留为历史证据，不覆盖成当前事实。
