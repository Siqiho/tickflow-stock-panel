# 2026-09-09 Data platform structure continuation — current-state

- as_of：2026-09-09T10:20+08:00
- 主台：数据台
- 次台：用户台
- 本文件是独立核对产物，不是执行者自检，不是产品验收，也不是归档重审。
- 本轮唯一写入就是本报告。产品源码、正式数据、规则、开发日志、计划和其他三项只读。
- 未请求外网、未采集、未写数据、未安装、未构建、未跑产品测试、未操作浏览器、无 commit/push、未启动或重启任何服务。
- 历史交接卡只作导航。2026-09-07 归档独立复核已通过，本轮不重做归档审计。
- 本轮不是 GitHub 审阅，未更新三台十二份权威文件。

## 0. 总判断

2026-09-02 至 09-04 的减法三步、数据页故障修正、采集页去掉「采集状态」、以及补洞/重建/清除进默认折叠「维护」，在**当前 one-trading 工作树源码**里仍然成立。Catalog 仍是事后投影，查询仍由实际存储决定。`stock.db` 默认写入兜底在默认资金流写入口上仍关闭。

这只证明**源码仍在、目录投影可被只读打开、少量文件元数据与投影能对上**。它不证明页面已再验收，也不证明任一数据集 `accepted / production`。

**没有可证实际缺陷，因此不提出修复包。** 不为继续而造功能或重架构。`D-P0-01` 仍是 `ready`，不等于开工授权。

---

## 1. 已核实 / 未核实 / 阻塞

### 已核实（本轮独立取证）

| 项 | 证据层 | 结论 |
| --- | --- | --- |
| 主树坐标 | git | `main` @ `31216dda527cd4ec177b9cbf6fd1c524dbadbe82`（2026-08-12）。`origin/main` ahead 52 / behind 418。工作区脏，约 788 条。三步实现不在 HEAD，在脏工作树。 |
| 实际 `DATA_DIR` | 配置 + 进程打开文件 | `/Users/simon/Trading/one-trading/data`。`.env` 为 `DATA_DIR=./data`；`config.py` 相对路径按项目根解析。3018 打开的是该目录下的日志和 Parquet。 |
| 已有进程 | lsof / ps | 未启动、未重启。`3018`：uvicorn `--reload` 父进程 PID `3510`，worker PID `3545`，cwd=`one-trading/backend`，2026-09-09 05:20:24 起。`3011`：Vite PID `3528`（父 `3516` pnpm dev），cwd=`one-trading/frontend`，同时刻起。`3111` / `3118` 当前无监听。进程环境未见 `FUND_FLOW_HISTORY_PREFER_LOCAL`。 |
| 三步与页面分组源码 | 当前工作树 | 见第 3 节。关键文件 mtime 均早于上述进程启动，本轮未证明内存与磁盘不一致。 |
| Catalog 投影快照 | `catalog.sqlite3` `mode=ro&immutable=1` | `catalog_stale=false`，`catalog_refreshed_at=2026-09-09T02:11:24.635061Z`。38 healthy / 7 unknown / 0 degraded / 0 failed。中文存储分类标题已在快照里。 |
| 真实覆盖抽样 | 目录名 + 局部 Parquet 元数据 | 见第 4 节。目录 healthy ≠ 覆盖完整。 |
| 权威日志 / 计划 | 只读 | `5.6`–`5.12` / 用户台对应条仍写 `verified`，不是 `accepted`。`D-P0-01=ready`。`U-P0-04=candidate`。计划文件最近维护仍是 2026-09-03。 |
| 主树无 `data_sync` | 路径 | `backend/app/data_sync/` 不存在。 |

### 未核实

- 供应商 / HTTP 模型回执：与本轮无关，不伪报。
- 运行面页面：未打开浏览器，未登录 `/data`，未点扫描 / 同步 / 回补 / 维护按钮。
- 产品测试：未跑 pytest / vitest / 构建。测试文件只作源码对照。
- 3018 热重载后的内存映像：未打 `/health` 或 API。只能说关键文件 mtime < 进程启动，不能把「进程在听」写成「页面已验收」。
- 资金流 63 日窗口是否仍满窗、单板块 refresh 失败是否仍 502：未打实时接口。
- `go-stock/data/stock.db` 今日 10:13 仍在更新，未追溯是哪个进程写入；只确认 one-trading 默认写入口源码仍关闭。
- 9 月 7 日起市场看板 / 上游 `9a4bdcd` 正式晋升的全部交叉 diff：只把碰到数据页/偏好的交叉影响记为依赖，未做那些任务的验收。

### 阻塞

无。本调查可以收口。缺少的是另授的运行面复核或 `D-P0-01`，不是本轮修代码的门。

---

## 2. 主树、DATA_DIR、进程

| 项 | 值 |
| --- | --- |
| checkout | `/Users/simon/Trading/one-trading` |
| 分支 | `main`（当前 checkout） |
| HEAD | `31216dda527cd4ec177b9cbf6fd1c524dbadbe82` · `docs: track platform development logs` · 2026-08-12T21:21:33+08:00 |
| dirty | 是。三步相关文件相对 HEAD 为已改或未跟踪，见下表。 |
| 默认数据根 | `/Users/simon/Trading/one-trading/data` |
| 控制库 | `/Users/simon/Trading/one-trading/data/control/catalog.sqlite3`（无 WAL/SHM；mtime 2026-09-09 10:11） |
| 前端 | `127.0.0.1:3011` · PID 3528 · Vite |
| 后端 | `0.0.0.0:3018` · PID 3510 `--reload` + PID 3545 spawn worker |
| 隔离 fixture | `3111` / `3118` 当前未听 |

三步相关文件相对 HEAD 的 git 状态（HEAD 是 8 月 12 日，不能把 M/?? 当成 9 月 7 日后才引入）：

| 状态 | 路径 | 磁盘 mtime |
| --- | --- | --- |
| `??` | `backend/app/data_catalog/provenance_registry.py` | 2026-09-03 14:08 |
| `??` | `backend/app/data_catalog/provenance.py` | 2026-09-03 14:08 |
| `M` | `backend/app/data_catalog/definitions.py` | 2026-09-03 14:07 |
| `M` | `backend/app/data_catalog/scanner.py` | 2026-09-03 16:00 |
| `M` | `backend/app/data_catalog/service.py` | 2026-09-03 16:00 |
| `M` | `backend/app/services/free_sources/fund_flow.py` | 2026-09-03 12:12 |
| `M` | `backend/app/api/free_ext.py` | 2026-09-03 12:12 |
| `M` | `backend/app/services/preferences.py` | 2026-09-09 04:40 |
| `M` | `frontend/src/pages/Data.tsx` | 2026-09-09 01:11 |
| `??` | `frontend/src/components/data/DataSourceTracePanel.tsx` | 2026-09-03 16:00 |
| `M` | `frontend/src/components/data/DataCatalogSection.tsx` | 2026-09-03 15:20 |
| `M` | `frontend/src/components/data/StorageBreakdownCard.tsx` | 2026-09-03 15:19 |
| `??` | `frontend/src/components/data/DataPageCategoryNav.tsx` | 2026-09-03 16:37 |

交叉影响（依赖，不是本轮缺陷）：`preferences.py` / `Data.tsx` / `ControlPlaneSummary.tsx` 在 9 月 9 日被后续正式晋升或上游任务改过，但均早于 05:20 进程启动。读到的财务键顺序、采集页「维护」分组、来源追踪文案仍在。`Data.tsx` 另增「上游原版数据工具」页签，见 3.6。

权威日志 `5.97` 已记录同一对 PID `3510` / `3545` 使用该 `DATA_DIR`。本轮只确认进程仍在，不把 `5.97` 写成数据验收。

---

## 3. 三步与页面分组逐项

判定口径：`成立` = 当前工作树源码仍实现该行为。`成立` 不是运行面 verified，也不是 accepted。

### 3.1 第一步 — GitHub 只作 Adapter 对照，真实生产者负责数据

**状态：源码成立。运行面未核。数据验收未做。**

数据台：

- `provenance_registry.py:664-707`：`SUBJECT_REFERENCES` 注释写明「不是数据集父母」。`stock_daily` 对照 `tickflow-stock-panel` + `go-stock`；7 个固定扩展目录项在该表里是空元组，资金流 GitHub 名单由 `references_for_subject` 另补。
- `provenance_registry.py:475-487`：`go-stock` 默认 roles 是 `endpoint_intelligence` / `field_semantics`，不再带 `local_fallback`。文案写明仓库不是生产者、行业/概念日线主路径不用 `stock.db`。
- `provenance_registry.py:818-829`：`references_for_subject()` 只组装 Adapter 对照；`ext_fund_flow*` 追加 `FUND_FLOW_REFERENCE_IDS`。
- `provenance_registry.py:899-901`：`ext_fund_flow*` 的申报生产者固定 `eastmoney`。
- `provenance.py:274-287`：`true_producers` 先看 lineage 观测；没有观测才用申报表。`go_stock_snapshot` 只在 lineage 源里出现 `go_stock` 时进入故障链。
- `provenance.py:221-224`、`307-311`：`missing_github_mapping` 仍是 `info`，「不是数据缺失，也不表示生产者未知」。
- `provenance.py:257-258`、`483-484`：资金流摘要写「GitHub 只作 Adapter 对照，真实生产者是东财。go-stock stock.db 不在主路径」。
- `provenance.py:423-433`：已是 Catalog 目录项的 `ext_data/{id}` 不再重复列为 extension。

用户台：

- `DataSourceTracePanel.tsx:85`、`248`、`264`、`275-281`、`366-377`：故障链标题是「真实生产者」；GitHub 在「Adapter 对照（GitHub）」；页首写明 GitHub 不当数据集父母。

### 3.2 第二步 — 资金流日线默认关掉 `stock.db` 写入兜底

**状态：默认写入口源码成立。运行面未核。已有残片未当作本轮新缺陷。**

- `fund_flow.py:640-652`：`fetch_board_daily_history(..., allow_local_fallback: bool = False)`。注释写明默认只走东财；`stock.db` 必须显式 opt-in。
- `fund_flow.py:658-672`、`751-752`：只有 `allow_local_fallback` 为真时才读/返回本地库。`FUND_FLOW_HISTORY_PREFER_LOCAL` 不能单独打开默认路径。
- `fund_flow.py:1237-1258`：行业/概念窗口回补把 `force_local` 强制 `False`，并显式 `allow_local_fallback=False`、`prefer_h5=True`。
- `free_ext.py:241-242`：`GET /fund-flow/board/{code}/history` 在 refresh 或空缓存时显式 `allow_local_fallback=False`。
- `free_ext.py:255-267`：东财失败且已有缓存则返回旧行、不 persist；无缓存 502。
- 全树 `allow_local_fallback=True` 的产品调用：只出现在测试 `backend/tests/free_sources/test_fund_flow.py` 和注释。产品默认路径没有 True。
- `go-stock/data/stock.db` 仍在（982,376,448 bytes，mtime 2026-09-09 10:13）。文件存在 ≠ 默认写入口打开。
- 局部抽样：`ext_data/ext_fund_flow_bk_daily/timeseries` 最早 `date=2026-03-02` 与最晚 `date=2026-08-31` 两个分区的 `source` 均为 `eastmoney_fflow_day`。这不是全历史去残证明。权威日志 `5.7` 仍记录旧残片 `go_stock_local_snapshot`；本轮未全盘扫描，不宣称残片已消失。

### 3.3 第三步 — `ext_data` 拆项；Catalog 事后投影；查询由实际存储决定

**状态：源码成立。运行面未核。**

目录定义与扫描：

- `definitions.py:34-40`、`1370-1467`：固定项 `ext_fund_flow_bk` / `_bk_daily` / `_concept` / `_concept_daily` / `_stock`、`ext_gn_ths` / `ext_hy_ths`；`ext_data` 标题是「扩展数据余项」。
- `definitions.py:610-625`：固定项扫描根 `ext_data/{dataset_id}`。
- `definitions.py:1780-1802`：允许余项与 `ext_data/{id}` 父子重叠。
- `scanner.py:245-267`：按最长前缀归属，同一文件只属于一个目录项。
- 磁盘：`data/ext_data/` 现有 8 个子目录，正好是 7 个固定项 + 余项 `ext_fund_flow_concept_minute`。

查询仍走存储，不走 Catalog SQLite：

- `fund_flow.py:1127-1157`：`load_board_daily_history` 直接读 `ext_data/{id}/timeseries/*.parquet`。
- `fund_flow.py:873-957`：persist 仍用 `ExtConfigStore` + `write_ext_parquet` / 快照原子替换。
- `tickflow/repository.py:948-961`：`get_daily` 扫描日 K Parquet，不读 Catalog。
- 主树没有 `backend/app/data_sync/`。

存储桶仍是一个磁盘桶，目录项已拆开：

- `scanner.py:40-52`、`service.py:34-52`、`276-285`：分类中文标题；`list_catalog()` 回写 title。
- `StorageBreakdownCard.tsx:4-15`、`28-39`：「扩展数据」按钮进 Catalog `group=ext`，不把整桶当成余项 `ext_data`。
- 当前投影：`ext_data` 桶 404 files / 4,742,236 bytes。余项目录项 `ext_data` 仍是 357 行（分时余项），与 7 张固定卡分开。

用户台目录分组：

- `DataCatalogSection.tsx:27-56`：`isExtCatalogDataset` 把 `ext_data` 与 `ext_*` 放进「扩展数据」。

### 3.4 数据页目录扫描故障处理

**状态：源码成立。当前投影 stale=false，但这是目录健康，不是数据验收。**

- `scanner.py:30-31`、`412-478`：`file changed during scan` 最多重试 3 次，读到完整新版本；连续失败仍 fail-closed。
- `service.py:234-257`：全量扫描提交成功项；失败且先前可服务的项保留旧状态，不再因一项失败丢弃整页。`catalog_stale` 在有保留失败时可为 true，但成功项仍提交。
- `DatasetCatalogCard.tsx:70-74`：只有真正存在控制库 policy 才显示准入芯片。
- `ControlPlaneSummary.tsx:50-58`：空策略文案「未使用控制库准入」；可服务文案「已落库并可服务」。
- `DataSourceTracePanel.tsx:73`：同源空策略文案。
- 控制库仍只有 `trading_calendar` 一条 policy。
- `data/lineage/financial_shares/unpartitioned/legacy-dffd14cfaaaa21ca8a1d9cab.json` 仍在：`row_count=41784`，`source=legacy_local_artifact`。`financial_shares` 投影 41,784 行 healthy。

当前投影：`catalog_stale=false`。38 healthy / 7 unknown。7 个 unknown 是空数据集（`announcement_events` / `depth5` / `etf_adj_factor` / `etf_minute` / `index_weights` / `instrument_status_history` / `listing_delisting_events`），不是整页冻在 8 月。今日 10:11 的刷新把 `market_pulse`、`stock_instruments` 的 `updated_at` 推到 09-09；多数项仍停在 `2026-09-08T07:31:56Z`。这符合「按数据集提交，不当成一次全市场质量验收」。

### 3.5 采集页：旧「采集状态」移除；财务偏好一致；维护默认折叠

**状态：源码成立。运行面未核。**

- `Data.tsx` 无 `DataCollectionControlPanel`、无「采集状态」字符串。组件文件在 frontend 中不存在。
- `DataPageCategoryNav.tsx:28-35`：采集页签是「采集与同步」，没有 `extensionCount`。数字只给「数据目录」。
- `Data.tsx:588-627`：主位是盘后主链、立即同步、数据范围、自动调度；五个补洞/重建/清除按钮在 `<AdvancedDisclosure label="维护">`。
- `AdvancedDisclosure.tsx:13`：`useState(false)`，默认收起。
- `Data.test.tsx:196`、`271`、`397`、`425`：测试仍断言无「采集状态」标题，并要点「维护」才打开。
- `preferences.py:259-270`：`get_financial_provider()` 仍是 `financial_provider` 优先，然后才是 `financial_data_provider`。
- `settings.py:791`、`1915-1916`、`1979-1981`：setter / v0.2 data-providers / 删除自定义源仍双写两键。
- 磁盘 `data/user_data/preferences.json` 仍分叉：`financial_provider=public`，`financial_data_provider=tickflow`。与 `5.12` 一致。runtime getter 源码会解析为 `public`；本轮未执行 getter。

### 3.6 交叉影响（只作依赖，不覆盖历史基线）

1. **脏主树。** HEAD 停在 8 月 12 日。9 月 2–4 日三步和 9 月 7–9 日上游/看板/正式晋升都在同一工作区未提交。后续任何写入必须按文件授权，不能假定「历史基线文件 = 当前磁盘」。
2. **数据页新增「上游工具」。** `DataPageCategoryNav.tsx:5,34` 与 `Data.tsx:685-697` 增加独立页签「上游原版数据工具」（`RepairDailyPanel` / `RegimeConfigCard`）。采集主位分组没有被它拆掉。这是后来的加项，不是三步回退。
3. **9 月 9 日偏好 / 设置文件被后续任务改过。** `preferences.py` mtime 04:40、`settings.py` 03:51。当前 getter 顺序和双写仍在。不把 F1/F2 晋升写成采集页或资金流已验收。
4. **`docs/investigations/2026-09-07-industry-fflow-daily-roll/`** 里有 `fund_flow.py` overlay。官方 `backend/app/services/free_sources/fund_flow.py` mtime 仍是 2026-09-03 12:12，默认兜底仍关。本轮不审那次行业窗口滚动。
5. **正式晋升 `5.97` / 工作台 `5.30`。** 改了 `kline_sync` / `kline` API 等分钟 fallback，并留下今日 3011/3018。不是减法工单，也不开工 `D-P0-01`。

---

## 4. 目录健康 ≠ 真实覆盖 / 质量

Catalog 当前：`stale=false`，38 healthy / 7 unknown。存储分类标题已是中文。这只证明控制库投影能读，并且最近一次提交没有把整页标失败。

| 对象 | Catalog 投影 | 文件/元数据抽样 | 含义 |
| --- | --- | --- | --- |
| `stock_daily` | healthy · 8,209,018 行 · 最新 2026-09-08 | `kline_daily` 1743 个 `date=` 分区；`date=2026-09-08/part.parquet` 5207 行 | 投影与最新分区存在。不是 `D-P0-01` accepted，也不是全 A 验收。 |
| `stock_minute` | healthy · 2,160 行 · 5 标的 · 最新 2026-09-08 | 仅 9 个日期分区；`date=2026-09-08` 480 行、标的 `002916.SZ` / `300204.SZ` | **healthy 仍是按需薄覆盖。** 不能当成分时主链完成。 |
| `stock_adj_factor` | healthy · 56,861 行 · 最新 2026-07-23 | `adj_factor/all.parquet` 56,861 行，`trade_date` max `2026-07-23` | 文件与投影一致，**覆盖停在 7 月 23 日。** |
| `trading_calendar` | healthy · 1,824 行 · 最新 2026-08-31 | `reference/trading_calendar/calendar.parquet` `trade_date` max `2026-08-31` | 文件与投影一致，**日历没有走到 9 月。** |
| `quote_snapshot` | healthy · 183,513 行 · 最新 2026-09-08 | 已有 `quote_snapshot/asset_type=stock/date=2026-09-09/part.parquet` 5207 行 | **目录最新日落后于磁盘今日分区。** 正是 Catalog 事后投影，不是查询真相。 |
| `financial_shares` | healthy · 41,784 行 · 最新 2026-08-31 | lineage sidecar `row_count=41784` | 5.11 补的 sidecar 还在。不是财务数据集验收。 |
| `ext_fund_flow_bk_daily` | healthy · 16,033 行 · 128 标的 · 2026-03-02..2026-08-31 | 128 个日期分区，末分区 128 行且 `source=eastmoney_fflow_day` | 窗口文件还停在 8-31。目录健康 ≠ 9 月已滚动。 |
| `ext_fund_flow_concept_daily` | healthy · 59,010 行 · 504 标的 · 至 2026-08-31 | 123 个日期分区 | 同上。 |
| `ext_data` 余项 | healthy · 357 行 | `ext_fund_flow_concept_minute` 2 个分区（08-19、08-21） | 余项仍是分时，不是糊回 7 张固定卡。 |
| 空数据集 | unknown / 0 行 | `depth5` / `etf_minute` / `etf_adj_factor` 等无行 | unknown 是空，不是全台故障。 |

结论：目录扫描故障处理仍在源码里，当前投影也没有回到「整页冻在 8 月」。**healthy 不能写成数据质量已过关。**

---

## 5. 权威日志与计划（最新对应状态）

| 文件 | 状态词 | 本轮读法 |
| --- | --- | --- |
| 数据台开发日志 `5.6` / `5.7` / `5.8` / `5.9` | 展示或写入口或目录 `verified`；总账关闭 | 历史条目。本轮源码复核对得上，**不重新标记 verified，也不升 accepted**。 |
| 数据台 `5.10` / `5.11` / `5.12` | 展示 remap / 目录投影 / 财务键 `verified` | 源码仍在。`5.11` 里 2026-09-03 的行数/最新日已过时，以第 4 节当前抽样为准。 |
| 数据台 `5.97`（2026-09-09） | 正式 API/F2 `verified`；**没有**新数据集 `canary/accepted/production` | 交叉依赖。不是减法工单。 |
| 工作台 `source_trace_*` / `fund_flow_*` / `catalog_*` / `collection_*` | 各条 `verified`，不是 accepted | 用户台历史。本轮未做浏览器。 |
| 工作台 `5.30` | scoped engineering verified；入口 3011 | 正式晋升交叉依赖。 |
| `数据台下一步工程工作计划.md` | 最近维护 2026-09-03；减法三条关闭；**`D-P0-01` = `ready`** | `ready` ≠ 开工。进入 `active` 必须另授真实源访问，并在开发日志登记本次 commit / `DATA_DIR` / 运行面。 |
| `用户台下一步工程工作计划.md` | 最近维护 2026-09-03；**`U-P0-04` = `candidate`** | 不把三步写成用户验收完成。 |

计划禁区仍有效：不统一 TickFlow/东财/腾讯 Provider；不恢复 `data_sync` / `current.json`；不把质量门改成「不过就不能切正式文件」；不再开第 4 步减法工单。

---

## 6. 后续工作包

**无。**

未发现可证实际缺陷。三步与页面分组的源码还在，扫描提交/重试还在，默认 `stock.db` 写入口还关着。不为「接续」发明功能、重架构或把 `D-P0-01` 伪装成本轮修复包。

若 Astra 另授下一阶段，只应在这些既有门里选，而不是本报告新开包：

1. 独立运行面复核（另授；浏览器 / 已登录 `/data`；仍不写盘）。
2. `D-P0-01` `stock_daily` 主链质量与验收（计划已是 `ready`，必须单独授权才可 `active`）。
3. 已落地 canary 的用户验收（分钟线、同花顺四表等），按开发日志各自条目，不插入减法。

非目标（沿用计划，不是新工单）：不统一 Provider；不恢复 `data_sync`；不把 Catalog healthy 写成 accepted；不点资金流回补或维护写盘，除非另授。

---

## 7. 证据分层（禁止混写）

| 层 | 本轮 | 不能写成 |
| --- | --- | --- |
| 源码存在 | 已核，见第 3 节路径行号 | 产品已完整验收 |
| 运行面验证 | 只核进程身份与监听；未开页面 | `/data` 已核对、热重载健康、窗口满窗 |
| 数据验收 | 只做投影快照 + 局部文件元数据 | `accepted` / `production` / 全市场覆盖 |

`D-P0-01 ready` ≠ 开工授权。Catalog `healthy` ≠ 数据集 accepted。

---

## 8. 本轮工具与限制

只读：Read / Grep / Glob / Shell（git、lsof、ps、sqlite `immutable=1`、venv 内 pyarrow 读少量文件元数据）。写：仅本报告。未 fork、未改被审文件、未改日志/计划。

限制：未跑测试；未打 HTTP；未开浏览器；未全盘扫描 Parquet；`stock.db` 今日更新者未归属；脏工作树使「HEAD commit」不能代表实现。
