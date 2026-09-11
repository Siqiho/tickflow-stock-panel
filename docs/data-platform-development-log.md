# one-trading 数据平台开发日志

最近维护：2026-09-12（当前入口改为 2026-09-10T00:19:35+08:00 融合完成基线导航，见 `/Users/simon/Trading/one-trading/docs/development-baseline.md`。`restore_pre_cursor_20260911` 的「回退 9/9 05:12 之前」已是 superseded 历史范围。保留 9/12 新授权增量，不伪报验收。）

最近追加：2026-09-12 文档/记忆对齐。现行新授权条目仍是 `fund_flow_window_chain_restore_20260912` 与 `4.23` 的 9/12 估值恢复段；旧 9/11 历史正文不改数字。

适用项目：`/Users/simon/Trading/one-trading`

职责：只记录 one-trading 本地数据集的规划、实现、验证、验收和生产状态。

## 0. 权威边界

- 本文件是 one-trading 数据平台本地开发的持续维护入口。
- 数据台 GitHub 上游项目与采用判断见 `/Users/simon/Trading/数据台GitHub项目借鉴记录.md`。
- GitHub 数据来源、字段、分页、错误、更新和权利情报见 `/Users/simon/Trading/数据台GitHub项目数据能力目录.md`。
- 未来数据集顺序、开工门和验收门槛见 `/Users/simon/Trading/数据台下一步工程工作计划.md`。
- `docs/investigations/2026-07-29-data-platform-history-and-dashboard-audit-log.md` 是截至 2026-07-29 的历史审计与事故复盘，不再承担当前状态总览。
- 本文件中的 worktree、测试、canary、Parquet 或接口证据均不自动等于生产准入；生产状态必须由当前目标运行面和正式 `DATA_DIR` 证据单独证明。
- 开发基线导航：`/Users/simon/Trading/one-trading/docs/development-baseline.md`。旧会话/PID/「已完成」不能覆盖现行条目。

## 1. 最终目标与执行顺序

最终目标：

> 在 one-trading 现有数据台基础上，以“一个上游来源、一个数据集、一个完整闭环”为单位，研究真实数据生产者、请求参数、字段、分页、错误语义和更新机制；然后在 one-trading 内实现自有 Provider/Adapter，接入现有同步服务，发布为可重复更新的 Parquet 数据集，并提供只读取本地数据的 API。每完成一个数据集就停止验收，确认数据质量和使用价值后，再进入下一个数据集。

验收顺序固定为：

1. `stock_daily`：第一个闭环验收对象。
2. `announcement_events`：只有 `stock_daily` 验收后才进入独立验收。
3. `stock_instruments`、`etf_instruments`、`index_instruments`、`trading_calendar`：必须逐数据集按主链短链验收。隔离候选里的深 Module 不是主树实现，也不因共同开发于 Task 7 而合并 promotion。
4. 其他数据集：只有前一个数据集被接受或明确 no-go 后才排期。

## 2. 本地状态词

- `planned`：已定义价值和边界，尚未固定生产者证据。
- `source-verified`：真实生产者、参数、字段、分页、错误和更新语义已有证据。
- `isolated`：one-trading 自有实现和自动检查已在隔离环境完成；未证明正式数据和运行面。
- `canary`：受控真实源/真实样本运行完成；仍未通过完整用户验收。
- `accepted`：数据质量、重复更新、local-only API 和使用价值均由用户验收。
- `production`：accepted 数据集已在正式 `DATA_DIR` 和目标运行面受控启用并验证。
- `blocked / no-go / superseded`：分别表示阻塞、明确不准入、被更高质量实现替代。

<a id="restore_pre_cursor_20260911"></a>
### restore_pre_cursor_20260911（**superseded 历史范围**；不是当前入口）

- 历史范围注：本条记录 2026-09-11 把运行代码撤回到 9/9 05:12 晋升前。该操作范围已被 `restore_whole_20260910_0019`（2026-09-12T00:55:46+08:00 起，完成约 01:10）取代。当前入口是 00:19 融合完成基线 + 其后新授权增量，见 `development-baseline.md`。本条数字/备份不改，也不再表示当前运行代码。
- 用户授权恢复到 2026-09-09 05:12 晋升前旧版。数据台 `backend/app` / `backend/tests` 已回到 A 旧源；新增资讯/因子等后写源码已移 trash。
- 正式 `DATA_DIR=/Users/simon/Trading/one-trading/data` 未整树覆盖。Parquet 5770 身份与写前备份一致；`identity.sqlite3` / `catalog.sqlite3` integrity_check=ok。`.env` 未改。
- 当前 3018 PID 5762 用非产品验证 wrapper 关掉后台拉取/调度，**不是**日常 `uvicorn app.main:app`。未跑真实回填。不插入 `D-P0-01`。
- 证据：`/Users/simon/Trading/one-trading/docs/cursor-handoffs/restore-pre-cursor-20260911/restore-report.md`。后写实现已从运行代码撤回；本日志历史条目保留。


- 收尾（restore-docs-wording-20260911-close）：SOURCE 1533/1533；206 还原 / 176 trash / 40 从 9/8 补全；`.env`/现有数据保留。前端 tsc/build 通过。后端 46 passed / 12 errors 为旧版 `preferences_cache` 缺 `_invalidate_cache`，不修旧版。3011/3018 wrapper 后台暂停，不是日常全功能验收。
- Codex IAB（转录，非本执行端观察）：`/data` 展示 8,214,828 条日线，Stock daily bars 详情打开成功；后续数据仍保留。看板侧 5468 股票 / 241 分钟脉搏 / 行业资金流 128/128 见用户台同名条。
- 独立只读 review `aca6de45-3dcf-4aa3-8b86-12c80cef1590`，session `b09672e5-80b9-4d25-b8ee-eefdedf1f63c`，success/pass：无恢复阻断、384 extras 仅 docs、176 已 trash、12 errors 旧版固有。Grok 4.6 Extra High 配置 ack 有，实际模型/effort 未核验。实现任务传输超时，不写 workflow 成功。


<a id="restore_whole_20260910_0019"></a>
### restore_whole_20260910_0019（运行面恢复到融合完成，不是数据集验收）

- 时点：2026-09-12T00:55:46+08:00。正式数据台源码回到 2026-09-10 00:19 融合完成/瘦身前。正式 `DATA_DIR=/Users/simon/Trading/one-trading/data` 未整树覆盖、未回滚。
- identity/catalog sha 与写前一致；sqlite integrity ok。`.env` 未改。Parquet 只做身份记录。
- 当前 3018 PID 31588 用 audit 目录验证 wrapper + `ONE_TRADING_DISABLE_BACKGROUND=1`，**不是**日常 `uvicorn app.main:app`。未采集/同步/外网回填。不插入 `D-P0-01`。
- Polars 正式 venv realpath **1.44.1**。证据：`/Users/simon/Trading/docs/audits/restore-whole-20260910-0019/restore-report.md`。

<a id="fund_flow_window_chain_restore_20260912"></a>
### fund_flow_window_chain_restore_20260912（源码续接恢复，不是数据集验收）

新授权任务：`01a09187-8f63-7193-9645-b38acbf9803a`（核对市场看板数据 (2)）。禁后台/联网补数。

#### 目标与边界

- 在 2026-09-10 00:19 数据合集版本边界上，只补回缺失的概念 H5 日线续更代码和 `run_now` 接线。正式 `ext_fund_flow_concept_daily` 只读核验，不回填、不跑真实 roll/管道。
- 日历覆盖与时效语义已在当前源码/正式日历中成立，本轮不改日历文件。行业 180s 钉死；概念独立锁 / 720s / 稳定码 `ok`。
- 不是 cron 观察，不是 `accepted` / `production`。9/10 15:30 历史证据未复验。

#### 盘点（改前源码 vs 保留数据）

- 已在当前源：行业 `roll_industry_daily_from_h5`、`aggregate_board_window` 概念 90% 满窗、行业日历 freshness、正式概念/行业 Parquet 可读。
- 缺失：`roll_concept_daily_from_h5`、概念锁/取消/720s、`run_now` 行业后接概念。前端门槛仍是双方 63。
- 保留正式盘：行业 H5 max `2026-09-10` 128/128；概念 H5 max `2026-09-10` 504/504；日历 2007 行 `2025-01-01`～`2026-10-31`，覆盖 2026-09-12。

#### 代码 / 测试 / 保留数据核验 / 待 IAB

- 代码：`fund_flow.py` 最小 kind 贯穿；`daily_pipeline.run_now` 行业后立即概念，失败隔离。未改调度注册、日K 阶段、`pipeline.py` API。`request_industry_roll_cancel` 同时置概念取消事件，以覆盖现有 `cancel_job` 只调行业入口。
- 测试：`tests/free_sources/test_fund_flow_window_restore.py`；既有 `test_fund_flow.py` 未改。monkeypatch + tmp `DATA_DIR`，无真实 H5/网络。
- 保留数据核验：独立 `verify_parquet_windows.py` 对行业 5/63/126、概念 5/63 与 `aggregate_board_window` 精确相等，`all_match=true`。未写 `data/`。
- 待 IAB（实现当时）：目标页/已登录 HTTP/调度是否再打概念针。本执行端未开浏览器、未启停服务、未 enable scheduler。Codex 总工只读验收已记入下方「Codex 最终只读验收」与 `docs/investigations/2026-09-12-fund-flow-window-chain-restore/chief-acceptance.md`。

#### Codex 最终只读验收

以下为 **Codex 总工观察，不是 Cursor / 本执行端观察**。完整数字与 HTTP digest 见 `docs/investigations/2026-09-12-fund-flow-window-chain-restore/chief-acceptance.md` 与 `evidence/chief-iab.json`。

- 保留数据只读加总 / 已登录 HTTP / 用户台行业 126 + 概念 63 主路径已核对：实际 HTTP == `parquet-vs-service.json` service == 独立 Parquet 重算（行业 5/63/126、概念 5/63）。
- 概念续更实现仍停在 `isolated`：未执行真实 H5 roll，未执行正式 `run_now`。scheduler 启用/开火未验证。真实续更未验证。
- 未联网、未回填、未写正式数据、未 enable/开火调度、未跑真实行业/概念 roll、未跑正式 `run_now`；2026-09-10 历史 15:30 未复验。
- 当前状态：保留数据读/API/UI 链已核。概念续更实现仍为 isolated。不是 `canary`，不是 `accepted`，不是 `production`。
- 写前备份（实现）：`/Users/simon/备份/codex/20260912-015545-fund-flow-window-chain-restore-before`
- 收尾写前备份：`/Users/simon/备份/codex/20260912-025119-fund-flow-window-chain-restore-closeout-before`

#### 坐标

- 备份：`/Users/simon/备份/codex/20260912-015545-fund-flow-window-chain-restore-before`
- 收尾备份：`/Users/simon/备份/codex/20260912-025119-fund-flow-window-chain-restore-closeout-before`
- 证据：`docs/investigations/2026-09-12-fund-flow-window-chain-restore/`
- 当前状态：源码续接 + 自动检查 + 只读加总 + Codex 只读验收。概念续更实现仍 isolated。不是 `canary` 真实续更，不是 `accepted` / `production`。

## 3. 当前开发坐标

L3 当前入口（2026-09-12）：固定代码基线是 `2026-09-10T00:19:35+08:00` 数据合集/融合完成版，恢复证据见 `restore_whole_20260910_0019` 与 `/Users/simon/Trading/docs/audits/restore-whole-20260910-0019/restore-report.md`。其后现行新授权增量是 `fund_flow_window_chain_restore_20260912`（禁后台/联网补数）和 `4.23` 的 9/12 估值 CLI 恢复（不接 API/UI）。3.1 的 2026-08-04 PID 只是历史快照，不是当前运行面事实。

### 3.1 历史用户运行面快照（只读观察，as_of 2026-08-04；不是当前 PID）

- 当前 checkout：`/Users/simon/Trading/one-trading`，分支基线 `main@56d481076c008efca9ff40db8f5c89139bb7f600`；该工作区同时存在用户和其他任务的未提交/未跟踪修改，运行结果不能仅按 HEAD 归因。
- 前端：`3011`，PID `17633`，启动于 `2026-08-03 13:48:49 +0800`，cwd=`/Users/simon/Trading/one-trading/frontend`，Vite 开发服务器。
- 后端：`3018`，PID `17623`，启动于 `2026-08-03 13:48:49 +0800`，cwd=`/Users/simon/Trading/one-trading/backend`，`uvicorn app.main:app --reload`。
- 当前物理数据根：`/Users/simon/Trading/one-trading/data`。本节只记录一次只读身份快照；PID、启动时间和未提交文件都可能变化，后续验收必须重新取证。

### 3.2 隔离候选实现（停在实验室，不是主链）

- 隔离开发 worktree：`/Users/simon/Trading/one-trading/.worktrees/data-platform-convergence-v1`（2026-08-13 已删；分支仍在）。
- 分支：`codex/data-platform-convergence-v1`。
- HEAD：`7019d031ef81c00ca5e812f7910278d291d1f841`（`fix(data): close Task 7 repair and timezone gaps`）；2026-08-04 只读复核时 worktree clean。
- 该候选包含 `backend/app/data_sync/` 的深 Module、manifest/checkpoint、`current.json` 和 verified-local-query 设计。2026-09-02 结构核对后，这套统一发布协议停在实验室 / 隔离分支，不得抬成全台标准，也不得作为 `D-P0-01` 开工门。
- 主树实际短链：情报 → Provider/Adapter → 尽量归一 → `atomic_write_parquet` + `write_lineage_record` → Catalog 事后投影 → `repo.get_daily` 等直接读 Parquet。主树没有 `backend/app/data_sync/`。
- 只有“必须保留旧文件、新旧不能原地覆盖”的数据集才继续用 staging 再切正式文件：当前是 `corporate_actions` 与日历实验室。不推广到日 K、资金流、财务、同花顺特色表。
- 下列数据集的最高合法状态仍以各自条目为准；隔离历史 canary 只绑定其固定提交和隔离坐标，不能替代主链验收。

## 4. 数据集开发记录

<a id="stockdb-offline-export"></a>
### 4.18 `stockdb_offline_export`（独立离线包，不是生产 Provider）

- 目标/权限：用户授权本轮全量导出；明确允许暂停 StockDB、固定离线快照后恢复。保留原库和 QuantDB 包，不写正式 DATA_DIR，不触发网络镜像更新，不接行情 UI/API。
- 上游情报：/Users/simon/Trading/数据台GitHub项目借鉴记录.md#stockdb-source-review；真实行情生产者/数据权利仍待核，不能标记为 production 源。
- 坐标：/Users/simon/Trading/one-trading，main@31216dda527cd4ec177b9cbf6fd1c524dbadbe82；已有大量用户/其他任务未提交修改，保留。正式 DATA_DIR=/Users/simon/Trading/one-trading/data；本次产物=/Users/simon/Trading/下载数据/stockdb_parquet。
- 源与备份：原库 /Users/simon/Trading/下载数据/股票数据/stockdb 的 data/data1/mydb；暂停 PID 58166 后 APFS COW 快照到 /Users/simon/备份/codex/20260905-stockdb-export-source-snapshot。已有文档改动前备份到 /Users/simon/备份/codex/20260905-200350-stockdb-review-docs，两处均有 README。
- 当前阶段：canary；隔离离线包的全量转换与完整性验证已完成，不能升级成正式数据集 accepted/production。只读转换器 scripts/stockdb_offline_export.py 已实现；原始 CURRENT/MANIFEST 有效文件、WAL、内部序号/删除标记、Zstd/MessagePack、CRC、源/输出 SHA-256、分区 checkpoint 与原子发布；源始终 rb 打开，不加载原生引擎。闭环范围为离线包转换，不含 Provider/Catalog/API promotion。
- Canonical/原值：英文分表、代码字符串、原始数值字段；source_db/source_file/source_sequence/physical_key/logical_key/payload_raw 保留。仅同库取最新版本、应用 tombstone、排除 kidx 二级索引；跨库冲突不擅自覆盖，未知字段/辅助记录不丢弃。原值与可读字段共存，不统一平移分钟标签、不强改价格/估值/零量 bar。
- 自动验证：scripts/test_stockdb_offline_export.py 的 11 项测试通过，覆盖 CRC、范围、MANIFEST 删除、WAL 分片/残尾/损坏、版本/tombstone/冲突、索引安全跳过、原值与未知字段保留、Parquet 重开、checkpoint 幂等与篡改拒绝、独立逐记录 digest 验证。真实单文件 canary 151335 行，Parquet 原值样本逐字段一致且复跑跳过。
- 全量与验收：406 区间结束；661480720 个业务版本去掉 2886 个旧/重复版本后，保留 661477834 条。8 张原始表，包括 641759114 分钟、19658020 日线、58490 复权；约 21.9 GB。validation.json 逐页重开、每文件 hash、全部原值流 hash、同库唯一性和分区范围通过，30401 条分层可读字段样本一致；恢复前原库/快照 692 个有效输入文件 hash 一致。mydb 无有效业务记录。原值保全不等于行情质量合格。
- 质量与异常：134228 条源 MessagePack 截断（日线 3722、分钟 130506）原值保留并单列 unreadable_native_records；原生查询的两条代表样本同样返回 null。分钟另有可解码但缺字段记录；OHLC 顺序异常日线 37、分钟 2666；旧日 pre_close 算术不一致 14067401 条，市值/股本也有警报。完整数字见 quality_profile.json / quarantine_report.json，不补造价格/量额/PIT，不直接用于回测。跨分库分钟 600 个重叠键、2 个原始值差异，见 overlap_report.json，不擅自覆盖。
- 真实消费/恢复：read.sql 在独立 DuckDB 内存连接执行，日线查询及异常证券/日期查询成功；derived 提供板块成分、证券、退市和异常原值。2026-09-05 21:19:52 恢复查询服务 PID 20849/127.0.0.1:7899，清掉旧 PID 58166 的大扫描请求；7 个精确日/分钟/复权键对账通过。服务恢复证据 service_restore.json；one-trading PID 15035/83220/83232 未变化，未作前端/UI/API 接入或桌面控制台按钮验收。
- 实际失败/恢复验证：全库 HTTP 小 num 仍展开的请求被暂停并清掉；质量扫描曾因全市场 key GROUP BY 触及 2 GiB 内存上限而停止，原值和已导出文件无影响，改为只在跨库交叠日期窗口分组后成功。异常不被写成空成功，已完成 checkpoint 经 hash 可复用，未完成临时文件拒绝静默覆盖。
- 回滚：原库不被转换器改写，快照保留；导出产物在隔离目录，不触及线上数据。恢复原服务仅操作 StockDB，不操作 one-trading 的 3011/3018 服务。
- 后续边界：逐数据集生产准入需要另行授权与完整验收；下一步工程计划未更新，D-P0-01 不因此开工。

<a id="stockdb-native-sdk-check"></a>
#### 2026-09-05 22:20 官方 Mac 同内容重装与 SDK 导出核验

- 用户本轮授权：下载并安装最新版 Mac 包，遵守上游访问规则，再看本地数据是否能导出；不自动联网同步、修改源业务值或增加生产 Provider。上游固定发行物、44 文件一致性与规则主记录：/Users/simon/Trading/数据台GitHub项目借鉴记录.md#stockdb-source-review。当前 one-trading 坐标与原 canary 状态不变，未做 promotion。
- 真实安装目标：/Users/simon/Trading/下载数据/股票数据/stockdb/stockdb.app 与同目录 数据更新.app。从 GitHub 下载 ZIP 校验 SHA-256 后仅切换两个 bundle；其余 44 非数据文件比较中 SDK/配置/示例已一致，不重复覆盖。官方包与旧包完全同内容，本轮不是获得新修复代码。未执行递归 xattr/chmod/重签/同时启动两 App 的附带脚本。
- 停止/备份/恢复：核对并正常停止旧 GUI 58164、服务 20849，只操作 StockDB。备份目录 /Users/simon/备份/codex/20260905-stockdb-macos-install.pu1Tfc，含应用、配置、文档以及停服务后的 data/data1/mydb COW 快照；旧应用原件另在 bundles_before_switch，可恢复，未删除。源 SST 文件名/大小/mtime 与新快照一致（661/22/0），这是元数据核查而非本轮全库重哈希；引擎正常启动会更新控制文件。
- 真实桌面/服务：新 GUI PID 33497（2026-09-05 22:14:48）、子服务 PID 33505（22:14:49）；Codex CUA 核验 stockdb 服务状态窗口显示“正在运行（已启用监听）”，版本 0.3.1-stockdb、127.0.0.1:7899、PID 33505，与进程/监听者一致。两个新 bundle codesign --verify --deep --strict 通过；不声称 Apple 公证。数据更新器未启动；one-trading 原 PID 15035/83220/83232 不变。
- 本轮实现/产物：独立 /Users/simon/Trading/下载数据/stockdb_native_export_check_20260905，含一次性 check_export.py、local-only.sb、README、native_sample.parquet/json 与 validation.json。使用官方 SDK rd.get(table,code,date).do()，warm=False，3 秒 socket timeout；macOS sandbox 限制导出客户端只连接 localhost:7899、只向小样目录写入。非本地连接及输出目录外写入探针均得到 EPERM，本地查询成功；无远程行情、全库枚举、自动重试、设备身份变更或正式数据写入。
- 真实主路径：成功核验轮固定 9 次查询，7 可读、2 native_null；全部 9 个查询键和状态保留。Parquet 重开/页 checksum、JSON 对照、文件 SHA-256 通过，7 条可读值与旧归档中相同 key 的原始 MessagePack 值一致。小样 hash=e3441c12b7183525cd69bcbef298b918c9d725cc4da0c52805c9847fdad97172。再次执行在导入 SDK 前拒绝覆盖旧结果，不发送请求，验证幂等保护。
- 真实失败/修复边界：安装前后 `日k:000008:20000926` 与 `分钟k:000001:20260130132500` 都不可读；没有把 null 丢弃或补零。两冲突分钟键仍返回 data 的旧值，旧日 pre_close 问题未消失。一轮初步小样在第 5 个复权键因核验器错误要求返回字典含 code/date 而停止，未发布输出；已将该身份断言限定到日/分钟表，再成功导出。共 6 次前置本地 SDK 精确读取 + 9 次成功轮读取，没有远程重试。第一次 sandbox 地址写法在编译阶段被系统拒绝，改为系统支持的 localhost:7899 后才运行 SDK，没有临时放开网络。
- 结论：正常本地数据可以用最新版官方 SDK 导出，已取得真实独立小样；不是“新版修好了全量异常”。既有约 21.9 GB 全量归档不变、未重扫；异常表 hash 仍为 b1f7eebc0ba46cc65de9e70b2d89d84c7b49d01d612e917f311a9600eb2743f8。数据没有联网更新，末端仍按原覆盖清单到 2026-08-25。后续修复/新镜像核验必须单独确定范围，不能把本次同内容重装当作新数据或 accepted/production。

<a id="stockdb-isolated-repair"></a>
#### 4.18.b 隔离异常字段恢复与前收盘候选（2026-09-05）

- 目标/权限：用户明确要求修复异常，并通过 `codex exec --model xai/grok-4.6` 独立进程分工，根代理负责回传与最终复核。属于数据台既有 StockDB 离线包后处理；不接 UI/Provider/API，不改原库/旧归档/正式 DATA_DIR，不启动更新器或请求远程行情。外部 CLI 协作不是 one-trading Agent Runtime 已实现。
- 坐标：仍为 /Users/simon/Trading/one-trading，main@31216dda527cd4ec177b9cbf6fd1c524dbadbe82；保留全部已有脏工作区修改。输入 /Users/simon/Trading/下载数据/stockdb_parquet；独立结果 /Users/simon/Trading/下载数据/stockdb_repair_20260905。备份 /Users/simon/备份/codex/20260905-stockdb-repair.vA5Xg4，保存原异常表/质量报告及本轮更新文档，完整原始路径和原因见 README；原库既有完整快照继续保留。
- 当前状态：canary，已完成隔离字段恢复与候选计算，不是 accepted/production。实现 scripts/repair_stockdb_records.py、repair_stockdb_preclose.py、verify_stockdb_repairs.py、verify_stockdb_preclose.py、audit_grok_cli_tasks.py；读取说明和回滚见独立包 README / 本项目 runbook。输出表含原字节/来源/缺失清单或 original_pre_close/候选/前记录证据；成功标记与 SHA-256 独立保留，不覆盖历史证据。
- 截断全量结果：134228 条原值逐对恢复，代码/日期/OHLC 全部可读；C 扩展与纯 Python 两套 MessagePack 实现逐条一致，全部原字节/源文件/序号对账一致。日线 3268 条核心字段完整；仍缺量额的日线 454、分钟 130506，共 130960 条在 unresolved_core 中。完整核心日线另有 2626 条 amount/volume 超出 OHLC 的原生口径警报；没有把“恢复可读”写成“数据真值已修好”。
- 前收盘全量结果：覆盖全部 19658020 条日线，生成 8125359 条 internally_consistent_candidate；保留原 pre_close，分析视图另给 pre_close_for_analysis。必须当前/前记录身份和 OHLC 有效、唯一、日历严格相邻、无本地已知事件，原收益率误差 >0.2pp 而候选误差 <=0.005pp。5900774 条因缺日历/前日日历拒绝；其他事件/间隔/字段等分类见 preclose_full_v1/validation.json。300750/20260810 原 386.67 保持，不被 388.07 覆盖。来源价格/未记录事件/权利/PIT 仍未独立验收。
- Grok 协作与实际回传：两个 CLI session 为 01a07203-2059-7563-88a2-54eb682bf7fb（coverage）、01a07203-2431-7d81-bab5-d882d120a1b4（semantics）。初轮约 20 分钟后由根代理中断收束，再通过同模型 CLI resume 完成交付；最终均 exit 0、turn.completed、非空 final_result。27/39 条 task-scoped 路由记录 requestedModel=xai/grok-4.6、实际 provider=xai/resolvedModel=grok-4.6，没有其他模型 fallback；原生 spawn_agent 未使用。完整无敏感字段审计在 grok_cli_audit.json；CLI 自带后台 marketplace 刷新超时留在 stderr，不是行情访问或 Skill 调用。
- 根代理独立复核：重新运行 coverage probe，与其 9 条坏分钟/239 个共同完整分钟小样结果一致，未批准跨源量额补值；这是有限样本的拒绝，不外推为全库绝无匹配。重新执行 Grok 前收盘小样并核对其输出 6827 条，实际拒绝 000001/600519 在 20160104 缺前日日历的两条；加固空 OHLC、前记录重复/无效、事件重复、保留小误差原值等后，小样 6825 条，再全量运行。未原样采用子任务 overlay；证据 root_agent_review.json。
- 自动检查与目标消费：字段恢复 12 项、前收盘边界 8 项、旧导出器 11 项，共 31 项测试通过。全量候选唯一性/误差/相邻日期逐行检查通过；另用独立验证器将全部 8125359 条分别对回当日原记录、前一日原记录及重新计算日历/收益率，三组均全量通过，已知事件漏入 0 条（preclose_independent_verification.json）。验证器首轮因 DuckDB CREATE VIEW 不支持参数占位失败，改为转义的已验路径后成功重跑，没有改候选数据。消费前后所有日线/因子/日历/恢复输入 hash 一致。新 Parquet 重开、输出 hash、4 个字段恢复查询和3个前收盘主/边界样本通过。真实“不可读分钟变成可读 OHLC”、正常日线不变、前日日历缺口不应用、除权原值不改都已验证；重复运行拒绝覆盖，旧异常表 hash 仍 b1f7eebc...eb2743f8。
- 剩余边界/回滚：130960 条量额缺口、2 个分钟冲突仍明确未解决；两冲突继续保留4个原始版本行，没有 data1 自动优先。其他原生缺字段/OHLC/量价口径问题不因本轮消失。停止读取独立叠加视图即可回滚，不需恢复原库；未删除数据，正式服务无本轮重启。下一步工程计划未更新，不自动启动联网补数或生产接入。

### stock_daily_full_a_aug17_24_dashboard_universe

#### 目标与边界

- 用户目标：看板「趋势强度 / 实用监控」从 CSI1800∪自选（约 1804 只）扩到全 A，使站上均线、60 日新高低、炸板、跌停、高换手按全市场口径重算。
- 只扩官方 `kline_daily` / `kline_daily_enriched` 的 `2026-08-17..2026-08-24` 六个交易日，并把日常 `pipeline_universe_scope` 改为 `ALL`。不改 `public_data_scope=CSI800`，不扩财务五表/复权，不重拉 2019 年以来长历史，不部署。

#### 真实生产者与写入

- 历史窗口日 K：TickFlow 免费档 `https://free-api.tickflow.org`，`kline.daily.batch` 每批 100 只。脚本 [`scripts/backfill-full-a-aug17-24.py`](/Users/simon/Trading/one-trading/scripts/backfill-full-a-aug17-24.py)。
- 写入走 `repo.append_daily` merge-upsert，保留原 CSI1800 行。enriched 只对这 6 天窗口重算后 merge，不整表覆盖。
- 今天 `2026-08-24` 免费历史日 K 不含当日；用已有 `quote_snapshot/asset_type=stock/date=2026-08-24`（5213 只、无北交所）合成当日官方日 K。

#### 物理结果（正式 DATA_DIR）

- 扩面前备份：`/Users/simon/备份/codex/20260824-161629-one-trading-full-a-before-dashboard-universe`。
- 日 K / enriched：8-17 5539、8-18 5540、8-19 5541、8-20 5541、8-21 5543、8-24 5213。8-14 对照仍是 5540。茅台/宁德/平安/罗曼股份仍在。
- 科创板 300 只第一轮空返回，重试后补回；8-17..8-21 相对证券表 5551 仍缺 8–12 只（含上次 TickFlow 也没有完整日 K 的 `300176.SZ` / `301655.SZ` / `600984.SH` 等）。
- 8-24 缺 338 只，全部 `.BJ` / `920*`。当日公开快照没有北交所，腾讯/新浪公开行情合成也是 0 行，未把 CSI1800 行覆盖掉。
- `pipeline_universe_scope`: `CSI1800` → `ALL`。`public_data_scope` 仍是 `CSI800`。

#### 看板口径变化

- 本地复算 `GET /api/overview/market`（`data_mode=official`，as_of=2026-08-24，股票池 5207 只有效行）：站上 MA5/20/60 约 27%/42%/37%，60 日新高/新低 91/110，炸板 34，跌停 14，高换手 787，放量占比 5.8%。这是口径变化，不是把原 1804 只的 29%/26%/30% 按比例放大。
- 运行中 uvicorn 已 reload，enriched 缓存 `1105973 rows, 2025-10-28 ~ 2026-08-24`。刷新 `http://127.0.0.1:3011/` 后看板应吃到新范围。

#### 当前状态

- 当前状态：`canary / 待用户验收`。未把 `stock_daily` 升为 accepted/production。明天 15:30 盘后管道会按 ALL 写全 A 日 K；财务/复权仍只跟 CSI800。

#### 回滚

- 用备份覆盖这 6 天 `kline_daily` / `kline_daily_enriched` 分区和 `data/user_data/preferences.json`（把 `pipeline_universe_scope` 改回 `CSI1800`），再重启或 reload 后端。不要删 2019 年以来日 K。


### ext_fund_flow_bk_daily_h5_63d_128

#### 目标与边界

- 只补行业 1 个季度：当前快照 128 只，目标每只至少 63 个交易日，写入现有 `ext_fund_flow_bk_daily`。
- 生产者只许东财 H5 / daykline。不写 go-stock，不混 TickFlow、同花顺官方 API、20G stockdb。
- 不补概念，不打开半年/1 年，不改 `pipeline_universe_scope`，不动个股 K 线 / 财务 / 分钟线 / Catalog。

#### 真实生产者与写入

- 东财 H5 `https://emdatah5.eastmoney.com/dc/ZJLX/getDBHistoryData`，`limit=120`（H5 `lmt` 仍可能返回约 120 根，落盘前截断）。
- 代码：`backend/app/services/free_sources/fund_flow.py::backfill_industry_daily_from_h5`；脚本 `scripts/backfill_industry_fund_flow_h5_63d.py`。
- 强制远程：`FUND_FLOW_HISTORY_PREFER_LOCAL=0`，`allow_local_fallback=False`，`prefer_h5=True`。
- 分批 8 只，按 `date+code` 合并。`write_ext_parquet` 时序合并失败改为拒绝整日覆盖。
- 窗口完整条件改为：最近 N 个日期分区存在，且快照里每只 `days>=N`。只数日期分区不再算过关。

#### 物理结果（正式 DATA_DIR）

- 回补前备份：`/Users/simon/备份/codex/20260827-130029-ext-fund-flow-bk-daily-before-h5-63d`（123 个交易日）。
- 金丝雀 BK1258/BK1254：各 120 根，`2026-03-05` 至 `2026-08-26`；`2026-08-21` 仍是 128 只。
- 全量：128/128 成功，失败 0，短窗 0，`history_points=15360`，`source=eastmoney_fflow_day`。
- 分区 `2026-03-02` 至 `2026-08-26`（125 日）。`2026-08-24/25/26` 均为 128 只 H5。
- 全历史覆盖：min/p50/max=122/122/125，`ge63=128`，`ge120=128`，`ge126=0`，`ge250=0`。
- 2026-08-27 收盘后只读探测：H5 已有当日栏（半导体 `2026-03-05`～`2026-08-27`，121 根），本轮未写入，见 `ext_fund_flow_bk_daily_h5_126_250_blocked`。
- `aggregate_board_window(days=63)`：`2026-06-02` 至 `2026-08-26`，`window_complete=True`，`full_count=128`，每只 `days=63`。5/10/21 日窗口同样满窗。
- 63 日累计净流入为正的只有贵金属约 18.41 亿、焦炭Ⅱ约 0.41 亿；其余 126 只季度净流出。这是满窗求和结果，不是残缺拼接。

#### 自动检查

- `backend/.venv/bin/python -m pytest tests/free_sources/test_fund_flow.py tests/test_ext_parquet_merge.py -q`：23 passed。
- 前端 `SectorFundFlowPanel.history.test.tsx`：5 passed。

#### 当前状态

- 当前状态：`canary`。磁盘门已过，可打开行业「1 个季度」窗口累计。未标记 accepted/production。
- 使 `ext_fund_flow_bk_daily_63d_backfill_blocked` 与 `ext_fund_flow_bk_daily_eastmoney_probe_failed` 变为 `superseded`。
- 概念季度已另开 `ext_fund_flow_concept_daily_h5_63d_504`。行业半年/1 年仍不够。

#### 回滚

- 用 `/Users/simon/备份/codex/20260827-130029-ext-fund-flow-bk-daily-before-h5-63d` 覆盖 `data/ext_data/ext_fund_flow_bk_daily/`，界面会因 `window_complete=false` 自动退回当日快照。


### ext_fund_flow_concept_daily_h5_63d_504

#### 目标与边界

- 用户要核对概念「1 个季度」是否等于行业季度榜；若需要同步，按同一东财 H5 方法补概念日线并打开窗口累计。
- 只写现有 `ext_fund_flow_concept_daily`。不写 go-stock，不混 TickFlow、同花顺、20G stockdb。
- 不改行业已验收的 63 日窗口（仍是 `2026-06-02`～`2026-08-26`，贵金属 +18.41 亿 / 半导体 -3408.71 亿）。

#### 真实生产者与写入

- 东财 H5 `getDBHistoryData`，`prefer_h5=True`，`allow_local_fallback=False`，只落 `eastmoney_fflow_day`。
- 代码：`backfill_industry_daily_from_h5(..., kind="concept")`；脚本 `--kind concept --batch-size 4 --pause-s 2.0 --pause-code-s 1.5`。
- 回补前备份：`/Users/simon/备份/codex/20260831-111350-ext-fund-flow-concept-daily-before-h5-63d`（45 个旧 go-stock 分区）。
- 金丝雀 BK1009 / BK0596 各 120 根，`2026-03-09`～`2026-08-28`；`2026-08-21` 仍保留其他 go-stock 同行。

#### 物理结果（正式 DATA_DIR）

- 504/504 成功，失败 0，`history_points=58234`，区间 `2026-03-09`～`2026-08-28`。
- H5 满 63 天 483 只、满 120 天 448 只；21 只是 7 月后新主题（低市净率、2026 中报预减等），H5 本身只有 23～59 根。
- `历史新高` BK1675 有 90 根但窗口内缺 6 日，属稀疏主题。
- 概念窗口日期去掉 H5 开始后的 go-stock 空洞（`2026-07-19`、`2026-08-02`）和 8/31 未收盘残片，不改行业日期算法。
- `aggregate_board_window(kind=concept, days=63)`：`2026-06-02`～`2026-08-28`，`full_count=482/504`，`window_complete=True`（满窗只占快照 ≥90%，新主题不进累计榜）。
- 5 日窗口同样满窗：`2026-08-24`～`2026-08-28`，`503/504`。
- 季度累计流入 TOP：CAR-T细胞疗法 +11.17 亿、粮食概念 +7.94 亿、钛白粉概念 +5.80 亿。流出 TOP：融资融券 -20424 亿、富时罗素 -14041 亿、MSCI中国 -13641 亿。与当日快照（元宇宙 / 融资融券）不是同一张榜。

#### 自动检查

- `tests/free_sources/test_fund_flow.py`：27 passed。
- 前端 `SectorFundFlowPanel.history.test.tsx`：7 passed。

#### 当前状态

- 当前状态：`canary`。概念「1 天～1 个季度」可走窗口累计。半年/1 年仍不够。未标记 accepted/production。
- 与行业季度榜名称、代码、金额均无交集；只同步了方法，没有也不应做成同一张表。
- 2026-08-31 已登录看板 `http://127.0.0.1:3011/`：概念 63 日窗口接口 200，页面满窗 482/504；行业 63 日窗口未改。

#### 回滚

- 用 `/Users/simon/备份/codex/20260831-111350-ext-fund-flow-concept-daily-before-h5-63d` 覆盖 `data/ext_data/ext_fund_flow_concept_daily/`。


### ext_fund_flow_bk_daily_h5_roll_20260831

#### 目标与边界

- 用户要求窗口从当前最新已收盘日往前数 5 个交易日 / 1 周 / 1 个季度，不再停在 8/26。
- 只写现有 `ext_fund_flow_bk_daily`。只许东财 H5。不混 go-stock / TickFlow / 同花顺 / stockdb。
- 窗口日期轴改为只数 `eastmoney_fflow_day`，周末 go-stock 残片不再占交易日。

#### 真实生产者与写入

- 同一 H5 `getDBHistoryData`，`prefer_h5=True`，`allow_local_fallback=False`。
- 脚本 `--kind board --batch-size 4 --pause-s 2.0 --pause-code-s 1.0 --skip-gate`。
- 回补前备份：`/Users/simon/备份/codex/20260901-105254-ext-fund-flow-bk-daily-before-h5-roll`。

#### 物理结果（正式 DATA_DIR）

- 128/128 成功，失败 0，`history_points=15360`，H5 `2026-03-10`～`2026-08-31`。
- 5 日 / 1 周：`2026-08-25`～`2026-08-31`，满窗 128/128。流入元件 +142.07 亿；流出电池 -48.46 亿。
- 63 日：`2026-06-03`～`2026-08-31`，满窗 128/128。流入种植业 +2.41 亿；流出半导体 -3180.95 亿。旧的 `2026-06-02`～`2026-08-26` / 贵金属 +18.41 亿不再是当前窗口。
- 今天 9/1 盘中未进窗。半年/1 年仍不够。

#### 自动检查

- `tests/free_sources/test_fund_flow.py`：28 passed。

#### 当前状态

- 当前状态：`canary`。未标记 accepted/production。

#### 回滚

- 用 `/Users/simon/备份/codex/20260901-105254-ext-fund-flow-bk-daily-before-h5-roll` 覆盖 `data/ext_data/ext_fund_flow_bk_daily/`。


<a id="ext_fund_flow_bk_daily_industry_roll_phase_b_20260907"></a>
### ext_fund_flow_bk_daily_industry_roll_phase_b_20260907

#### 目标与边界

- 阶段 B：让已有盘后 `run_now` 能调用行业日线续更；只改行业 `ext_fund_flow_bk_daily`。
- 沿现有东财 H5 读取与 `persist_board_daily_history` / `write_ext_parquet` 合并链。不新建全台发布层。
- 使用本地行业快照代码全集，不联网补目录，不调用默认 Top20 `refresh_top_boards_daily_history`。
- 只认 `eastmoney_fflow_day`，`allow_local_fallback=False`，不混 `stock.db`。
- 概念、半年、一年、交易日历扩修、正式 `DATA_DIR` 回补、真实外连均不在本轮。
- 优先级按 P1 数据时效处理；日历缺口时时效为 unknown，不用日K假充法定日历。

#### GitHub 情报

- 无新 GitHub 审阅。沿用既有东财 H5 / `ext_fund_flow_bk_daily` 记录。

#### 坐标

- 主树 `/Users/simon/Trading/one-trading` `main@31216dda527cd4ec177b9cbf6fd1c524dbadbe82`；既有未提交改动保留，未 reset/stash。
- 实施目录（不在 `--reload` 监视下）：`/Users/simon/Trading/one-trading/docs/investigations/2026-09-07-industry-fflow-daily-roll/`
- 正式 DATA_DIR 仍为 `/Users/simon/Trading/one-trading/data`；本轮未写入。
- 备份：`/Users/simon/备份/codex/20260907-154837-industry-fflow-daily-roll`

#### Provider / Adapter / schema

- 新函数 `roll_industry_daily_from_h5`：本地 `ext_fund_flow_bk` 快照全集 → `fetch_board_daily_history(prefer_h5=True, allow_local_fallback=False)` → 只落 `eastmoney_fflow_day` → 按 date+code 合并。
- 线程锁 + `ext_fund_flow_bk_daily/.industry_daily_roll.lock` 防重入。
- `ok` 要求全部成功且最新 H5 日对快照全集到齐；非空响应不等于最新日到齐。
- `aggregate_board_window(kind=board)` 增加 `data_as_of` / `freshness_status` / `freshness_note` / `expected_trading_day` / `calendar_covers`。日历未覆盖到当日 → `unknown`。概念返回不加这些字段。
- `daily_pipeline.run_now` 在日K质量门已决定后附加 `industry_fund_flow_daily`；失败不改 `quality` / `daily_days`。

#### 自动检查

- 隔离 pytest 12 passed：`docs/investigations/2026-09-07-industry-fflow-daily-roll/results/pytest.txt`
- 覆盖：128 只全选、5/63 窗前移与独立金额、上游失败保旧、不完整批次、非空≠到齐、幂等/并发防重、120 窗外长历史保留、陈旧/未知时效、概念 90% 与 Top6/5=1 周、行业失败不拖垮日K。
- 未连外网；`PYTHONDONTWRITEBYTECODE=1`；临时 data 仅 pytest `basetemp`。

#### 当前状态

- 当前状态：`isolated`。代码与隔离自动检查已完成。
- 不是 `source-verified` 的新源（沿用已有 H5 链），也不是 `canary` / `accepted` / `production`。未跑真实源，未写正式 DATA_DIR，未验证 HTTP API。
- 下一步工程计划未更新。

#### 回滚

- 主树源码本轮未改。隔离 overlay 可用 `baseline/` 覆盖。
- 若之后应用补丁：用备份目录 `files/` 覆盖四个绝对路径。

#### 2026-09-07 18:47 独立复查返工（只追加，不整份回退）

- 独立复查：`docs/investigations/2026-09-07-industry-fflow-daily-roll/review/independent-review.md`。本条相对 15:50 备份的漂移包含 Phase B 本条追加，回滚不得用该备份覆盖本文件。
- 调度：`run_now` 进程内闸，第二次触发 `busy` 且不重跑日K；`/api/pipeline/run` 600s 仅在不在飞时 fail；行业默认 180s 墙钟 + `cancel_event`，`done` 只在续更返回后发出。
- 落盘：行业 persist 走 `write_ext_parquet(..., atomic=True)`；默认 `atomic=False` 不变。
- 日期：latest 只在本次快照全集 ∩ `eastmoney_fflow_day`；时效 Asia/Shanghai + 日历 `close_time`。
- 读取：行业专用 `h5_only=True`，失败保旧，不改其他调用默认。
- 自动检查：原 12 + 返工 13 = 25 passed（`results/pytest.txt`）。未重跑无关大套。未改 `review/` 旧用例。
- 当前状态仍为 `isolated`。未跑真实东财 / HTTP API / 盘后真实调度 / 正式 DATA_DIR。
- 应用/回滚只打或只撤 `patches/phase-b-industry-fflow-daily-roll.diff`；禁止整文件 copy 与旧备份覆盖源码或本日志。


<a id="ext_fund_flow_bk_daily_industry_roll_live_20260909"></a>
### ext_fund_flow_bk_daily_industry_roll_live_20260909

#### 目标与边界

- 把 9/7 已审查的行业 H5 日线续更迁入现行主树，并对正式 `DATA_DIR` 做真实续更与回读。
- 只写行业 `ext_fund_flow_bk_daily`。概念、日历扩修、长周期混源、全日 K 重跑不在本轮。
- 保留现行 job slot / `reap_stale` 与现有调度逻辑，不退回 9/7 overlay 的第二套进程闸。配置默认 15:30（`preferences.get_pipeline_schedule`），`daily_pipeline.py` 注释写 15:35，二者不一致；未观察真实自然触发。不改偏好、源码注释或运行调度。

#### GitHub 情报

- 无新 GitHub 审阅。沿用既有东财 H5 / `ext_fund_flow_bk_daily` 记录。9/7 overlay 见 `docs/investigations/2026-09-07-industry-fflow-daily-roll/`。

#### 坐标

- 主树 `/Users/simon/Trading/one-trading` `main@31216dda527cd4ec177b9cbf6fd1c524dbadbe82` dirty。未 reset/stash。
- `DATA_DIR=/Users/simon/Trading/one-trading/data`。
- 备份：脏树起点 `/Users/simon/备份/codex/20260909-131435-industry-fflow-live`；文档P2改前 `/Users/simon/备份/codex/20260909-142907-industry-fflow-docs-p2`
- 实施目录：`/Users/simon/Trading/one-trading/docs/investigations/2026-09-09-industry-fflow-live/`
- 运行面：uvicorn `--reload` 父 PID `3510`（05:20:24）；本轮改码后 worker PID `91841`（13:17:10）。未启新常驻服务。

#### Provider / Adapter / schema

- `roll_industry_daily_from_h5`：本地行业快照 128 只 → `h5_only=True` → 只落 `eastmoney_fflow_day` → date+code 合并 + `write_ext_parquet(..., atomic=True)`。
- 超时后续跑：已有最新 H5 日的码跳过，缺日码优先，避免 180s 反复从头。
- `run_now` 在质量门之后、`done` 之前调用；失败不改 `quality` / `daily_days`。
- 行业窗 `aggregate_board_window(kind=board)` 带 `data_as_of` / `freshness_*`。日历未覆盖当日 → `unknown`。

#### 真实源与正式日线

- 隔离 canary 5 码（元件/电池/种植业/半导体/航运港口）真实 H5：`2026-03-18`～`2026-09-08`，`source=eastmoney_fflow_day`，`unit=yuan`。
- 正式 128/128：PASS1 42.8s，`latest=2026-09-08` 到齐，失败 0。新分区 `2026-09-01..04`、`09-07`、`09-08`。
- 5 日窗 `2026-09-02`～`2026-09-08` 满窗；63 日窗 `2026-06-11`～`2026-09-08` 满窗。
- `2026-03-02` 长历史与 `go_stock_local_snapshot` 256 行保留。概念日线仍止 `2026-08-31`。
- 受控路径是 `roll_industry_daily_from_h5`，不是全日 K，也不是已观察的未来 cron。

#### 自动检查

- 原日志：`docs/investigations/2026-09-09-industry-fflow-live/tests` 14 passed（`evidence/pytest.txt`，4.88s）。主树模块，不是 overlay。无单独 vitest 日志，不冒充实测。
- 控制器 `ecf15990-52f4-48f8-ba7f-1d949aba4285` `checks.log`：`14 passed in 4.20s`，exit 0。独立 review 未重跑，不是漏测。
- 代表码独立加总见 `evidence/independent-sums-full.json`（5 代表码）。独立复核另做正式 Parquet 全窗 12+12 与总工 HTTP200 精确相等。

#### 当前状态

- 当前状态：`accepted`（仅上述当前范围：受控 `roll_industry_daily_from_h5` 正式行业续更 + 5/63 窗 local-only API/页面技术验收）。不是 `production`。自然盘后调度仍待观察。概念、日历扩修、长周期不在本条。
- 总工 IAB 2026-09-09 05:26:04 UTC 已登录浏览器看到 5/63 满窗前移；总工已登录 HTTP 05:37:04 UTC 同端点 200、5/63 均为 128/128。执行端未登录 HTTP 401 是未登录事实。日历不足故时效 `unknown`。
- 独立技术复核 task `9cd3cd22-b5e1-4262-950d-29300d799fed` / session `75c6b767-3e2c-422d-ab3b-fcba37faf477`：产品 P1 无；正式 134 分区 `2026-03-02`～`2026-09-08`；9/8、5 日、63 日各 128/128；date+code 重复 0；`go_stock` 256 行（7/19、8/2）、3/2 长历史、snapshot/calendar/config 与改前备份 SHA 匹配；独立直接 Parquet 逐日求和与总工 HTTP200 12+12 项 `main_net` 全部精确相等；6/19 属日历休市；worker 91841@13:17:10 晚于源码。P2 仅权威日志（本阶段修正）。
- 文档P2本阶段修正待独立定点复查。计划 `D-R-05` 只更新剩余依赖，不改调度。
- 完整记录：`docs/investigations/2026-09-09-industry-fflow-live/implementation.md`
- 2026-09-10 WP3 只读 126 加总指针：`industry_window_126_sum_20260910`。不把行业半年开门写成数据台实现。

#### 回滚

- 源码：以本轮相对脏树起点 `evidence/diffs/*.diff` 生成反向补丁，先 dry-run；冲突或当前哈希已不等于本轮交付版本则停止。不要用备份 `files/` 整文件覆盖六源码（会覆盖后续任务写入）。不要整文件覆盖源码或 `data/`。
- 数据：行业分区只逆本轮增量（`data/ext_data/ext_fund_flow_bk_daily/`）；先校验当前哈希仍等于本轮交付版本。存在后续有效写入则停。不要整份覆盖 `data/`。


<a id="dashboard_data_acceptance_20260911"></a>
### dashboard_data_acceptance_20260911

#### 目标与边界

- 只核对市场看板四包当前正式盘与源码契约：概念 H5 日线、日历 4.6 覆盖补丁、行业半年窗、9/10 15:30 自然管道。不是新数据集，不改调度，不写正式 `DATA_DIR`。
- 工程已查 / 自动通过。目标页 IAB 由 Codex 完成（见下）。独立 audit 已 PASS。不是 `accepted` / `production`。

#### 2026-09-11 只读结果

- 正式行业/概念 H5 max 仍 `2026-09-10`（128 / 504）。日 K 仍 `2026-09-09`，`daily_days=0` 与 job `f7864b8bdd` 一致。日历仍 2007 行、`2025-01-01`～`2026-10-31`。
- 独立 Parquet 加总与 `aggregate_board_window` 对行业 5/63/126、概念 5/63 Top6 精确相等。概念半年/年档与行业年档仍是不请求长窗的当日快照契约，不能称已有长窗。
- 列明测试 46 + 前端 14 + tsc 通过。Codex 对照原 impl `883367d3`：共同源码/测试/API hash 全同，仅两日志变动。
- 证据：`docs/investigations/2026-09-11-dashboard-data-acceptance/`。总工归档：`chief-acceptance.md`。

#### WP1 总工归档（本包顺带落地，无新封装阶段）

- 旧 wf `352f625c-50d1-457d-965c-6a0be438e523` blocked 预算；旧 review `d273` 取消保留。
- 新独立 audit `01bbde76-e057-4fea-b74f-b959962184e5` PASS / session `23a8f1fd-d292-4062-8941-ef29bd90d793` / candidate `fe4b29b9d34201819d1dbda3854b2f42591ab3353618e5a335865f3eeb5d92a4`。
- Codex IAB ~15:00 隔离 3011：行业 5/63/126=128/128；概念 5=504/504、63=490/504；至 9/10；主要金额与 `window-sums.json` 相同。概念 126 与双方 250 明确窗口不足 / 9/2 快照日期 / 不能当完整累计。15:05:57 行业 126「已陈旧」是日内 freshness 门随时间变化，不能把早前「足够新」当一直 fresh。全负 TOP 是 8/27 两端 Top6 规则。日 K 9/9 未解决。观察来自 Codex，本执行端未亲测。`window-sums.json` freshness=null 旧原始值未改。
- 状态：工程验收通过。目标页/用户 accepted / production：否。

<a id="overview_scope_fix_20260911"></a>
### overview_scope_fix_20260911

#### 目标与边界

- 恢复总览 coverage 契约：scope / sample_count / as_of / availability。5 条旧 quote 样本不得冒充当日全 A。可信全市场才全市场合计；缺元信息按未知/不完整。合计缺数不可伪零。
- 不重开 WP1。不改 TickFlow none/free=`none` 与 public=`full_market`。不采集、不写正式 `DATA_DIR`、不重启 runtime。

#### 坐标

- 备份：`/Users/simon/备份/codex/20260911-170040-overview-scope-fix-before`
- lineage P2 改前备份：`/Users/simon/备份/codex/20260911-175435-overview-scope-lineage-p2-before`
- 实现说明：`docs/investigations/2026-09-11-overview-scope-fix/implementation.md`
- 隔离 fixture：同目录 `fixtures/`（TEST-ONLY，默认 `/tmp/ot-overview-scope-repro`）

#### 当前状态

- 续接失败任务 `dce105e3-ad1e-40eb-907e-d0fc68971e79`（HTTP/2 CANCEL，session `30ba043c-25f8-4d8a-b212-a9125293ec46`，candidate `010200b5bfcdc050ea221e2032f0c870ce5e53869b73bc299318859bb3c849f7`，零 controller 检查）。旧 wf `69099e44-2698-4bba-bb68-4375ac0aa05e` blocked 仍保留。
- 独立 review `f4889223-1dcd-4362-9dd1-97e8ff9c5455` 虽 PASS，但总工将该审查的 lineage 残余 P2（同日 ETF/index `full_market` lineage 可能抬升无 scope 的股票快照）提升为本包必修。
- `_latest_quote_lineage` 现 fail-closed：只认 `asset_type=stock`，或旧记录 `target_artifact` 明确指向 `quote_snapshot/asset_type=stock/date=目标日`。非 stock / 路径不匹配 / 缺乏身份均不授予 `full_market`。不按行数猜；显式 stock parquet scope 优先与混合 scope unknown 未改。
- 本执行端看见：`tests/test_overview_scope.py` **12 passed**；controller 同组五文件 **30 passed**（原 27 + 本轮 3）。未写 shared `DATA_DIR`，未重启 3011/3018。前端无 diff，复用 `0238cce4` 的 43 / tsc / vite。
- IAB 仍待 Codex 在 runtime owner `01a07a79-1c8e-73e0-af8f-85939177bb8b` 刷新 3018 之后。不是 `accepted` / `production`。
- 基线分类（2026-09-12）：**基线不含；仅历史未重新授权**。12 passed / 30 passed 等原数字保留，不当作当前已重做。

<a id="industry_window_126_sum_20260910"></a>
### industry_window_126_sum_20260910

#### 目标与边界

- 只记录正式盘行业 126 窗独立 Parquet 加总与已登录 HTTP 对照。不是数据集生命周期条目，不把门开写成数据台实现。
- 用户台半年开门见工作台日志 `industry_half_year_window_open_20260910`。

#### 加总证据

- 算法与 5/63 相同：最近 126 个 `eastmoney_fflow_day`，逐码 `main_net`。
- 2026-09-10 已登录 `GET /api/free/fund-flow/boards/window?days=126`：`2026-03-11`～`2026-09-09`，128/128，`window_complete=true`，`calendar_covers=true`，时效 `fresh`。未登录 401。
- 独立 Parquet 128/128 与 HTTP `main_net` 全部精确相等。见 `docs/investigations/2026-09-10-industry-half-year-open/evidence/http-126-resum.json`；WP2 切日历后首次对照见 `docs/investigations/2026-09-10-calendar-extend/evidence/http-boards-window.json` 的 `126`。
- 当前状态：证据指针。不提升行业日线或日历生命周期。不是 `accepted` / `production`。
- 2026-09-11 核对：正式 126 已滚到 `2026-03-12`～`2026-09-10`，128/128，农业综合Ⅱ -2.36 亿 / 半导体 -5683.45 亿。见 `dashboard_data_acceptance_20260911`。目标页待 Codex。
- 基线分类（2026-09-12）：00:19 树已有加总算法；用户台 126 开门门槛与概念续更代码属锚后内容，**恢复后新授权重做**见 `fund_flow_window_chain_restore_20260912`。本条 9/10–9/11 数字保留。旧 15:30 批写不是当前授权。

<a id="daily_pipeline_natural_1530_observe_20260910"></a>
### daily_pipeline_natural_1530_observe_20260910

#### 目标与边界

- 只观察现有 `pipeline@15:30`。不新写 cron，不改默认 15:30，不用 `PUT pipeline-schedule` 或 `POST /api/pipeline/run` 冒充。
- job `degraded` ≠ 行业未续更；`succeeded` ≠ 行业已到齐。

#### 2026-09-09 已有行业准点（文档此前冻在 15:30 之前故写「未观察」）

- `data/job_store/f0125e68cf.json`：`_work_key=owner|daily_pipeline|daily_pipeline`，`started_at=2026-09-09T07:30:01Z`（15:30:01 CST），`finished_at=2026-09-09T07:35:01Z`，`status=degraded`。
- 质量门 `ok=false`：`low_coverage` / `turnover_unit_mismatch`。不是行业失败。
- `result.industry_fund_flow_daily.ok=true`，`latest_data_date=2026-09-09`，128/128。该路径**没有** `concept_fund_flow_daily`。
- 摘要：`docs/investigations/2026-09-10-pipeline-1530-observe/evidence/f0125e68cf-summary.json`。

#### 2026-09-10 WP1 后再看概念是否跟同一根针

- 观察前基线（14:44:22 CST，后端已在跑）：`next_pipeline_run=2026-09-10T15:30:00+08:00`；行业/概念 H5 max 均为 `2026-09-09`（128 / 504）。见 `docs/investigations/2026-09-10-pipeline-1530-observe/evidence/pre-1530-baseline.json`。
- 三件证据缺一则该次未观察：新 job 准点起步、行业+概念子结果、正式 parquet H5 max 相对基线。
- 既有 watcher `watch_1530.py`（PID 10879）在 15:29:00 写下 `watch-start.json`，15:35:00 因磁盘尚无新文件写成 `today-observe.json` `observed=false` / `no_new_daily_pipeline_job_by_15:35`。这是假阴性：`job_store` 只在终态落盘，本轮文件 15:35:31 CST 才出现。未另起第二条 watcher，也未 `POST /api/pipeline/run`。
- **准点**：`data/job_store/f7864b8bdd.json`，`_work_key=owner|daily_pipeline|daily_pipeline`，`started_at=2026-09-10T07:30:00Z`（15:30:00 CST，对齐预录 `next_pipeline_run`），`finished_at=2026-09-10T07:35:31Z`，`status=succeeded`，`duration_s=331`。uvicorn 日志 `2026-09-10 15:30:00,041` APScheduler cron `15:30` mon-fri。不是 misfire，不是无 job。
- **子结果**：`industry_fund_flow_daily.ok=true` / `status=ok` / `latest_data_date=2026-09-10` / 128/128 / `latest_day_complete=true`。`concept_fund_flow_daily.ok=true` / `status=ok` / `latest_data_date=2026-09-10` / 504/504 / `latest_day_complete=true`。概念已跟同一根针。
- **正式 parquet H5**：观察前行业/概念 max 均为 `2026-09-09`（128 / 504）；观察后均为 `2026-09-10`（128 / 504，`source=eastmoney_fflow_day`）。
- `succeeded` ≠ 日 K 已到 9/10：质量门 `ok=true` 仍核 `2026-09-09`（TickFlow 跳过 public 合成）。15:30 后日 K 仍停在 9/9 是观察，不是改点到 15:35 的授权。job `succeeded` ≠ 把本条写成 `production`。
- 摘要：`docs/investigations/2026-09-10-pipeline-1530-observe/evidence/f7864b8bdd-summary.json`。watcher 假阴性原件保留为 `evidence/today-observe.json`。
- 当前状态：9/9 与 9/10 准点均已归档。本条是观察，不是 `production`。WP1/WP2/WP3 不因此升 `accepted`/`production`。
- 2026-09-11 核对：原 job `f7864b8bdd` 未变。日 K 仍无 `date=2026-09-10`。根因是 TickFlow batch 15:30 新增 0 分区，且 `realtime_data_provider=tickflow` 跳过 public 合成；质量门核最新已有日 9/9。不改 15:30。诊断见 `docs/investigations/2026-09-11-dashboard-data-acceptance/evidence/daily-k-diagnosis.json`。

<a id="ext_fund_flow_concept_daily_h5_roll_live_20260910"></a>
### ext_fund_flow_concept_daily_h5_roll_live_20260910

#### 目标与边界

- 把 `ext_fund_flow_concept_daily` 从 `2026-08-31` 续到行业已有的最新东财已收盘日，并挂进 `run_now`（行业 roll 之后）。
- 用 `kind=` 贯穿现有 roll；独立概念锁 / 默认 720s / 按批心跳。不要走 `backfill_industry_daily_from_h5`。行业默认 180s 源码钉不动。
- 概念 `ok` = 上一本地末日已有稳定码都出现在新的 H5 末日。窗口排名仍 90% + 新主题不进累计榜。Universe = 当前快照行。
- 前端不改。`BOARD_WINDOW_MAX_DAYS` 仍 63。不加概念时效行，不自动开 126。不是 cron 观察，不是 `production`。

#### GitHub 情报

- 无新 GitHub 审阅。沿用既有东财 H5 / `ext_fund_flow_concept_daily` 记录。

#### 坐标

- 主树 `/Users/simon/Trading/one-trading` `main@31216dda527cd4ec177b9cbf6fd1c524dbadbe82` dirty。
- `DATA_DIR=/Users/simon/Trading/one-trading/data`。
- 隔离 canary DATA_DIR：`docs/investigations/2026-09-10-concept-fflow-live/canary-data`。
- 正式写入前备份：`/Users/simon/备份/codex/20260910-140918-ext-fund-flow-concept-daily-before-wp1`。
- 证据：`docs/investigations/2026-09-10-concept-fflow-live/evidence/`。
- 运行面：2026-09-10 14:17 重启 uvicorn `--reload` 父 PID `82981`，worker PID `83019`（14:17:27），端口 3018；Vite 3011 PID `3528`。旧 80814 父进程占 LISTEN 不 accept，已替换。调度仍是 `pipeline@15:30`。

#### Provider / Adapter / schema

- `roll_concept_daily_from_h5`：`kind=concept` 穿进 `_industry_local_h5_dates` / `_industry_h5_latest_coverage` / `_acquire_industry_roll_lock`。
- 锁：`ext_fund_flow_concept_daily/.concept_daily_roll.lock`，与行业锁互不 `busy`。
- 取数：`fetch_board_daily_history(..., kind="concept", h5_only=True, allow_local_fallback=False)`，只落 `eastmoney_fflow_day`。
- 管道暂停：`batch_size=8, pause_s=0.35, pause_code_s=0`；按批 `emit` 心跳，不调大 `data_source_job_timeout_s`。
- `run_now`：行业之后接概念；行业失败/超时不跳过概念；任一 roll 失败不改 `quality` / `daily_days`。
- `cancel_job` 同时取消概念。`atomic=True` 合并；`snap_time` / go-stock 残片保留。

#### 真实源与正式日线

- 隔离 canary 5 码（BK1749/BK1750/BK1723/BK0743/BK0596）：`latest=2026-09-09`，5/5，`date=2026-07-19` 仍 142 行带 `snap_time`。
- 正式 504/504：170s，`latest_data_date=2026-09-09`，`ok=true`，失败 0，`history_points=58636`。H5 max 9/9。
- date+code 重复 0。`go_stock_local_snapshot` 272 行（`2026-07-19`、`2026-08-02`）保留。7/19 分区仍 142 行且 `snap_time` 无空。

#### 自动检查与 local-only API

- 概念 roll 测试 + 行业 live + `test_fund_flow.py`：53 passed（本轮实现会话）。
- 独立 Parquet 加总 vs `aggregate_board_window`：5/63 Top6 十二项 `code`/`main_net` 精确相等。见 `evidence/window-sums.json`。
- 未登录 `GET /api/free/fund-flow/concepts/window` = 401。已登录同端点 5/63 HTTP 200，12+12 与 Parquet 精确相等；概念无 `freshness_status`。见 `evidence/http-window.json`。
- 5 日窗 `2026-09-03`～`2026-09-09` 满窗 504/504。63 日窗 `2026-06-12`～`2026-09-09` 满窗 490/504。

#### 当前状态

- 当前状态：`canary`（受控 `roll_concept_daily_from_h5` 正式续更 + 5/63 local-only API/已登录页）。独立 Cursor 复查未做，故不标 `accepted`。不是 `production`。不是 cron 已观察。
- 2026-09-11 核对：正式概念 H5 仍止于 `2026-09-10`，5 日 `2026-09-04`～`2026-09-10` 504/504，63 日满窗 490/504。来源/单位/锁/取消/atomic/90% 源码仍在。目标页待 Codex。见 `dashboard_data_acceptance_20260911`。
- 已登录 Cursor 内置浏览器 `http://127.0.0.1:3011/`：概念 5 日已离开 `2026-08-25`～`2026-08-31`，为 `2026-09-03`～`2026-09-09`，504/504，5G概念 +253.70 亿；「1 个季度」`2026-06-12`～`2026-09-09`，CAR-T +42.23 亿；「半年」仍当日快照。概念无时效行。见 `evidence/browser-wp1.json`。
- 计划旁路：`D-R-07`。不扩大 `D-R-05`。

#### 回滚

- 源码反向 diff。概念分区只逆本轮增量。哈希漂移则停。禁止整份覆盖 `data/`。


### ext_fund_flow_concept_daily_h5_roll_20260831

#### 目标与边界

- 与行业同一终点：最新 H5 已收盘日往前数。只写 `ext_fund_flow_concept_daily`。

#### 真实生产者与写入

- 同一东财 H5 路径。脚本 `--kind concept --batch-size 4 --pause-s 2.0 --pause-code-s 1.5 --skip-gate`。
- 回补前备份：`/Users/simon/备份/codex/20260901-105254-ext-fund-flow-concept-daily-before-h5-roll`。

#### 物理结果（正式 DATA_DIR）

- 回补后 H5 收到 `2026-08-31`。5 日 / 1 周：`2026-08-25`～`2026-08-31`，满窗 503/504。
- 63 日：`2026-06-03`～`2026-08-31`，满窗 482/504。流入钛白粉概念 +5.09 亿；流出融资融券约 -2.05 万亿。
- 旧窗口 `2026-06-02`～`2026-08-28` 已被这次滚动取代。

#### 自动检查

- 与行业同一次 `test_fund_flow.py` 28 passed。

#### 当前状态

- 当前状态：`canary`。未标记 accepted/production。

#### 回滚

- 用 `/Users/simon/备份/codex/20260901-105254-ext-fund-flow-concept-daily-before-h5-roll` 覆盖 `data/ext_data/ext_fund_flow_concept_daily/`。


### ext_fund_flow_bk_daily_h5_126_250_blocked

#### 目标与边界

- 用户授权：用同一东财 H5 方法、分批回补行业半年（126 日）和 1 年（250 日），再打开对应窗口。
- 只评估并尝试现有 `ext_fund_flow_bk_daily`。不写 go-stock，不混 TickFlow、同花顺官方 API、20G stockdb、Tushare、新浪。
- 不补概念。H5 若吐不出满窗，不得打开「半年 / 1 年」，不得把残缺窗口写成完整累计榜。

#### 真实生产者与探测

- 同一生产者：H5 `https://emdatah5.eastmoney.com/dc/ZJLX/getDBHistoryData`，以及 `push2his` `fflow/daykline/get`。
- 2026-08-27 15:41 后对 `BK1036` 半导体只读探测（`prefer_h5` 路径，约 1.6s 间隔）：`lmt=120/250/500/0/1000` 都是 121 根，`2026-03-05`～`2026-08-27`。`beg/end/lmt0/type/fc` 不能往更早翻页。
- 2026-08-28 10:46 盘中复测（H5 `lmt=0`，间隔 2s）：行业 6 只（半导体/贵金属/焦炭Ⅱ/种植业/金属新材料/航空机场）、概念融资融券、个股茅台、上证指数全部 120 根，`2026-03-06`～`2026-08-27`。与本地交易日历该区间开市日数一致。未收盘的 8/28 不在序列里。
- 官方行业页 `data.eastmoney.com/bkzj/BK1036.html` 的「行业历史资金流」也走同一条 `quotehisurl + api/qt/stock/fflow/daykline/get`，`lmt=0`。
- `push2his` 在 8/27 连续探测后断连，8/28 对半导体再打一次仍断连；公开可读主机以 H5 为准。
- datacenter-web 几个 `RPT_*FUND*` 猜测无可用结果。Tushare `moneyflow_ind_dc` 是积分接口，不是本闭环生产者。

#### 物理结果（正式 DATA_DIR，只读）

- 磁盘仍是 125 个日期，`2026-03-02`～`2026-08-26`；128 只 min/p50/max=122/122/125。
- `aggregate_board_window(days=126|250)`：`window_complete=False`，`full_count=0`。
- 即使把今天 8/27 写入，H5 窗口仍从 `2026-03-05` 起，多数行业最多约 123 日，过不了 `ge126=128`，更过不了 250。
- 本轮未备份、未写 Parquet、未改 `BOARD_WINDOW_MAX_DAYS`。

#### 当前状态

- 当前状态：`blocked`。单次请求极限是**滚动 120 个已收盘交易日**，不是可无限拉长的档案库。8/27 收盘后短暂看到 121 根（含 3/5），次日窗口左端已切到 3/6。
- 同一生产者若只靠每日追加，半年还缺每只至少约 4～5 个更早交易日（H5 已不再返回 3/2～3/5），一年还要再攒约 130 个交易日。
- 本地开发日志：未开始实现。用户台「半年 / 1 年」继续回退当日快照。

#### 回滚

- 无写入，无需回滚。


### ext_fund_flow_bk_daily_h5_21d_128

#### 目标与边界

- 按时间刻度、不按行业一次多天：当前快照 128 只行业，只落近 21 个交易日，补齐「1 个月」窗口累计榜。
- 写入现有 `ext_fund_flow_bk_daily`。不打开季度开关，不补概念，不动个股 K 线 / 财务 / 分钟线 / Catalog。

#### 同步方式

- 东财 H5 `getDBHistoryData` 的 `lmt=21` 仍返回约 120 根，不能当成服务端已截断。
- `fetch_board_daily_history` 在落盘前按日期排序后只保留最近 `limit` 根。回归：`test_fetch_board_daily_history_trims_h5_rows_to_limit`。
- 128 只全部 `ok`，每只 21 根，日期 `2026-07-24` 至 `2026-08-21`，`source=eastmoney_fflow_day`。失败 0。

#### 验收

- `2026-08-21`：128/128，全部 H5。`2026-08-24` 当日快照分区未改，仍是 go-stock 128 只。
- 近 21 个交易日覆盖 128/128，缺 0；`aggregate_board_window(days=21)` 为 `window_complete=True`。
- 1 个月累计 TOP 与当日快照不同：窗口最大净流入贵金属约 63.27 亿，快照仍是工业金属约 7.5 亿。
- 当前窗口接口取盘上最近 21 个日期分区，含 `2026-08-24` 快照日，区间显示为 `2026-07-28` 至 `2026-08-24`。H5 短窗本身止于 `2026-08-21`。
- 未改 `useWindowRanking = days <= 21`。

#### 当前状态

- 当前状态：`canary`。「1 个月」短窗已可按 128 只累计。季度 / 半年 / 1 年仍不够，继续回退当日快照。

### ext_fund_flow_bk_daily_h5_batch0_canary

#### 目标与边界

- 只做 H5 `getDBHistoryData` 第一批实验：确认当前行业快照 128 只能否分批读取，并只落第一批约 10 只到现有 `ext_fund_flow_bk_daily`。
- 不打开「1 个季度」窗口累计开关，不补概念，不改 `pipeline_universe_scope`，不动个股 K 线 / 财务 / 分钟线 / Catalog 全量重扫。

#### 真实生产者

- 主请求仍先打 `push2his` daykline；本轮实测行业历史由东方财富 H5 `https://emdatah5.eastmoney.com/dc/ZJLX/getDBHistoryData` 返回。
- 代码：`backend/app/services/free_sources/fund_flow.py::fetch_board_daily_history` 已把 H5 插入 daykline 多 host 顺序。
- 强制远程：`FUND_FLOW_HISTORY_PREFER_LOCAL=0`。

#### 事故与恢复

- 第一批首次落盘时，旧 go-stock 分区多 `snap_time` 列，`write_ext_parquet` 默认 concat 失败后整日覆盖，导致 2026-07-02 至 08-21 多数分区从约 128 只写成 10 只。
- 已从 `/Users/simon/备份/codex/20260824-134553-ext-fund-flow-bk-daily-before-h5-batch0` 恢复 64 个交易日。
- 覆盖前现场另存：`/Users/simon/备份/codex/20260824-135341-ext-fund-flow-bk-daily-before-restore-from-h5-batch0`。
- 修复：`write_ext_parquet` 改为 `pl.concat(..., how="diagonal_relaxed")`。回归：`tests/test_ext_parquet_merge.py`。

#### 第一批实验证据

- 读取：快照 128/128 只全部 `ok`，每只 120 根，`source=eastmoney_fflow_day`，日期 `2026-03-02` 至 `2026-08-21`。失败 0。
- 落盘：金丝雀 BK1287 + 第一批 10 只（BK0420/BK0421/BK0422/BK0424/BK0428/BK0440/BK0448/BK0450/BK0451/BK0454）。
- 2026-08-21 仍是 128 只；其中 11 只已换成 H5，其余 117 只仍是 `go_stock_local_snapshot`。2026-08-24 当日快照分区未改，仍 128 只 go-stock。
- 当前覆盖：128 只都至少 21 天；`ge63=14`，`ge120=11`，中位数仍约 28 天。不够开季度累计。
- 自动检查：`tests/test_ext_parquet_merge.py` 与 `tests/free_sources/test_fund_flow.py` 共 17 passed。

#### 当前状态

- 当前状态：`canary`。H5 读取路径已验证到 128 只行业；完整 63/63 尚未达到。界面「1 个季度」继续回退当日快照。

### ext_fund_flow_bk_daily_eastmoney_probe_failed

#### 目标与边界

- 第 0 期只读探活东财 daykline，强制远程，不改界面，不批量写。
- 样本：电力 BK0428、保险Ⅱ BK0474。通过门：source=eastmoney_fflow_day 且 klines≥63。

#### 探活结果

- `FUND_FLOW_HISTORY_PREFER_LOCAL=0 fetch_board_daily_history` 仍返回 `go_stock_local_snapshot`（电力 64 天，保险Ⅱ 28 天），因为远程失败后函数会本地兜底。
- 直打东财：push2his 断开无响应；push2delay 200 但空 klines；push2 HTTP 502。
- 未安装 akshare/efinance。未改 `useWindowRanking`，未分批落盘。

#### 当前状态

- 当前状态：`superseded`。已被 `ext_fund_flow_bk_daily_h5_63d_128` 用东财 H5 路径替代。

### ext_fund_flow_bk_daily_63d_backfill_blocked

#### 目标与边界

- 按指令先补行业快照 128 只约 63 个交易日，再决定是否打开「1 个季度」累计榜。
- 不改用户台门槛，不补概念，不补半年/1 年，不新建数据集。

#### 执行

- `refresh_top_boards_daily_history(..., top_n=200, limit=63)`。
- 东财 daykline 仍不可用，回退 go-stock `bk_fund_flow`。selected=128，failed=0，history_points=3805。

#### 日线验收（未过关）

- 回补前：min/p50/max=21/26.5/64，ge63=2。
- 回补后：min/p50/max=28/28/64，codes=128，ge63=5（电力、厨卫电器、其他家电Ⅱ等），99 只停在约 28 天。
- 本地 go-stock `bk_fund_flow` 自身也只有 163 个行业、64 个交易日，ge63 仅 5 只、中位数 28 天。现有来源补不出完整季度。
- 因此不打开 `days<=21` 到 63 的开关，避免把电力约 247 亿的残缺拼接榜当成完整季度。

#### 当前状态

- 当前状态：`superseded`。go-stock 本地库补不出季度；后续由 `ext_fund_flow_bk_daily_h5_63d_128` 用东财 H5 完成 128/128。

### ext_fund_flow_bk_daily_21d_backfill

#### 目标与边界

- 只补行业资金流日线：当前快照 128 只，近 21 个交易日，写入现有 `ext_fund_flow_bk_daily`。
- 不新建数据集，不改 kline_daily、财务、分钟线，不做 Catalog 全量重扫，不补概念窗口。

#### 真实生产者与本地实现

- 调用：`refresh_top_boards_daily_history(..., kind=board, top_n=200, limit=21)`。
- 东财 daykline 不可用，回退 go-stock 本地 `bk_fund_flow` 按日聚合。
- 结果：selected=128，history_codes=128，failed=0，history_points=2688，source=`go_stock_local_snapshot`。

#### 验收证据

- 回补前 1 个月窗口：覆盖 64/128，缺 64 只，窗口 2026-07-24 ~ 2026-08-21。
- 回补后：覆盖 128/128，缺 0 只，窗口 2026-07-27 ~ 2026-08-24；21/21 齐全 128 只。
- 1 个月累计榜第一变为元件约 115.66 亿，不再是当日快照通信设备。下载云当日快照仍独立。

#### 当前状态

- 当前状态：`canary`。本地磁盘已更新；页面需刷新后才显示 128/128。未标记 accepted/production。

### ext_fund_flow_bk_daily_window_rank

#### 目标与边界

- 行业资金流按交易日窗口对 `ext_fund_flow_bk_daily.main_net` 求和后排名。
- 回补范围从当日 TOP20 流入/流出扩大到当前行业快照全部约 128 只；窗口默认 63 个交易日。
- 不新建数据集，不改 kline_daily、财务、分钟线，不做 Catalog 全量重扫，不改 pipeline_universe_scope。

#### GitHub 情报链接

- 沿用已有东财 daykline / go-stock `bk_fund_flow` 回退，不新增上游审阅。

#### 真实生产者与本地实现

- 查询：`backend/app/services/free_sources/fund_flow.py` `aggregate_board_window()`。
- 接口：`GET /api/free/fund-flow/boards/window`。
- 回补：`refresh_top_boards_daily_history(..., top_n>=100)` 使用当前快照全部行业。
- 写入仍是 `ext_fund_flow_bk_daily/timeseries/date=*/part.parquet`。

#### 自动测试与当前证据

- `tests/free_sources/test_fund_flow.py::test_aggregate_board_window_does_not_treat_missing_days_as_zero` 通过。
- 当前磁盘：快照 128 只，日线 72 只 / 63 个交易日（2026-04-01 到 2026-08-21）。窗口累计第一为电力，不是当日通信设备 75.49 亿。缺 56 只可见。窗口外样本不足，返回「窗口外数据不足」。

#### 当前状态

- 当前状态：`isolated`。完整 128 只回补和目标运行面验收未完成，不能写成 accepted/production。


### 4.1 `stock_daily`

#### 目标与来源

- 真实生产者：现有 TickFlow SDK。
- 固定调用语义：`kline.daily.batch`、`period=1d`、`adjust=none`、`as_dataframe=False`、`show_progress=False`。
- GitHub 情报：`shy3130/tickflow-stock-panel` 提供宿主和 TickFlow 工程背景；`simonlin1212/a-stock-data` 等只作字段与来源交叉情报，不是运行时依赖或 fallback。

#### one-trading 自有实现

- 主树运行路径（2026-09-02 结构核对后的验收对象）：`backend/app/services/kline_sync.py` → `KlineRepository.append_daily` / `atomic_write_parquet` + lineage → `repo.get_daily` 读 `data/kline_daily`。`GET /api/kline/daily` 本地为空时仍会现场拉 TickFlow，这是现有查询兜底，不是质量门缺陷。
- 隔离候选路径（停在实验室，不作为主链开工门）：`backend/app/data_sync/adapters/tickflow_stock_daily.py`、`backend/app/data_sync/datasets/stock_daily.py`；首次深 Module `1b776fb`，原子 snapshot `94fc8e9`，closeout `7019d03`。这些文件不在当前用户运行面。
- canonical：`symbol,date,open,high,low,close,volume,amount`；价格为未复权 CNY，`volume=lot`，`amount=CNY`。
- 主链发布：按日分区原子写 Parquet，并写 lineage sidecar。Catalog 事后扫描投影，不参与查询。
- 隔离发布（仅历史记录）：多日分区先 stage/reopen/质量验证，再切换 immutable generation/current manifest。不再作为 `stock_daily` 验收门槛。

#### 已有证据与当前状态

- `94fc8e9` 阶段记录：focused/affected `89 passed`、DataSync `190 passed`、backend `1400 passed, 9 warnings`，以及相关 Ruff、compile、diff check 通过。
- 历史审计的 R07 固定记录：`7019d03` 完整 backend `1530 passed, 1 skipped`、`TZ=UTC` 47 passed、DataSync + Catalog 408 passed，worktree clean。本次文档职责迁移没有重新运行这些代码测试，因此这里只引用该固定证据，不把它写成新执行结果。
- 当前状态：`isolated / not-production`。

#### 2026-08-31 自选股当日 enriched 覆盖缺口补齐

- 不是新数据集，也不把 `stock_daily` / `kline_daily_enriched` 升到 `accepted` 或 `production`。
- 用户目标：自选表振幅、换手、量比、RSI14、信号不再对深市 000/002/300 显示 `—`。
- 根因：`new_dates_only` 只要看到 `date=2026-08-31` 分区存在就跳过；当日官方分区先按不完整日 K 写成 2948 行（沪+北+部分创业板），后来日 K 补到 4946 行也不再重算。价格列来自 `quote_snapshot`，指标列来自最新 enriched，所以半行有数。
- 物理写入（正式 `DATA_DIR=/Users/simon/Trading/one-trading/data`）：
  - 备份：`/Users/simon/备份/codex/20260831-214700-watchlist-enriched-gapfill-before`
  - `000636.SZ` 当天日 K 缺失，用已有 `quote_snapshot` 合成 1 行后 `kline_daily/date=2026-08-31` = 4947。
  - `fill_enriched_coverage_gap` 按当日日 K 差集重算并 merge，新增 1999 行；enriched 现 4947，与日 K 对齐，自选 14 只全部在分区内。
- 代码：`backend/app/indicators/pipeline.py` 的 `fill_enriched_coverage_gap`；增量无新日期和盘后 skip 分支会再跑一次覆盖检查。测试：`tests/test_enriched_full_rebuild.py` 新增覆盖缺口用例，相关 12 项通过。
- 查询验证：同进程重载 `get_enriched_latest` + `watchlist_enriched` 得到 `as_of=2026-08-31`、14 行、振幅/换手/量比/RSI14 均非空。抽查 `002916.SZ` 振幅 5.98%、换手 1.23%、量比 0.98、RSI14 51.1；`002815.SZ` 振幅 4.36%、换手 5.04%、RSI14 58.9。运行中 uvicorn 已换 worker；未在 Cursor 浏览器完成登录后的点击验收。
- 当前状态：`canary`。刷新自选页应看到数字；用户确认前不写 `accepted`。
- 回滚：用上述备份覆盖 `kline_daily/date=2026-08-31` 与 `kline_daily_enriched/date=2026-08-31`，再重启或 reload 后端。不要删其他日期分区。

#### 2026-08-31 挖掘指纹只读钩子

#### 验收缺口

- 2026-09-02 起，缺口改为主链质量与用户验收，不再要求先建 `data_sync` 或 verified manifest。
- 需要补齐的是现有 TickFlow → `kline_sync` → Parquet → `/api/kline/daily`：producer 参数、覆盖、PK/OHLC/单位、lineage，以及已有分区时的 local-only 读。本地为空时的现场 TickFlow 兜底必须写明，不得假装已经 local-only。
- 由用户确认数据质量和使用价值后，才能写为 `accepted`；production promotion 另行授权。
- 隔离候选上的四项复审（休市日 `force`、复权业务日期、repair/cache 终态、日历默认时钟）只绑定 `7019d03`，不再阻塞主链验收。

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

#### 2026-08-17 盘后日 K 扩到 CSI1800 并回补 8 月缺口

- 用户目标：只把盘后正式日 K / enriched 从 `CSI500 + 自选` 扩到 `CSI1800 + 自选`，把茅台、宁德这类大票接回当前管道；不要改成 3800 / 全 A，也不要重拉 2019 年以来的长历史。
- 范围定义：`CSI1800 = 官方中证800(000906) ∪ 官方中证1000(000852)`。当前磁盘成分 `CSI800.parquet` / `CSI1000.parquet` 均为 `as_of=2026-08-14`、`source=csindex`，去重后 1800 只；再叠加当前 11 只自选（其中 4 只不在 1800 内：`300204.SZ` / `600756.SH` / `603261.SH` / `605289.SH`），解析结果 1804 只。`public_data_scope` 仍为 `CSI800`，财务五表/复权自动范围未扩。
- 实现边界：`pools_public.py` 新增官方池；`universe_scope.py` 让 `CSI800` 走官方 000906，不再用 300∪500 近似，并新增 `CSI1800` 并集；preferences / settings / `PipelineScopeConfig` 可保存并选择 `CSI800` / `CSI1000` / `CSI1800`。当前 `pipeline_universe_scope=CSI1800`。未改 Hermes 视图、分析桥、日 K schema、用户表，也未部署。
- 回补：`scripts/backfill-csi1800-august.py --apply` 只补已有 8 月分区 `2026-08-03..2026-08-14` 共 10 个交易日（15/16 为周末；17 日当天尚未收盘，本轮不预写今日）。公开 EOD 写入后与原 CSI500 行合并，未用 `quote_snapshot` 冒充正式日 K，也未改写 `2019-07-05..2026-07-31`。
- 物理验收（正式 `DATA_DIR=/Users/simon/Trading/one-trading/data`）：上述 10 个 `kline_daily` / `kline_daily_enriched` 分区均为 1804 行，且恰好等于当前 CSI1800∪自选，无范围外泄漏。抽查 `300750.SZ` / `600519.SH` / `000001.SZ` 正式日 K 与 enriched 均为 `first=2019-07-05 last=2026-08-14 n=1726`。CSI500 样本 `000009.SZ` 等历史起点仍是 `2019-07-05`。范围外对照 `000006.SZ` 仍停在 `2026-07-31`。财务五表目录无 2026-08-17 全量同步痕迹。
- 自动检查：`tests/test_universe_scope_csi1800.py`、`test_universe_scope_csi800.py`、`test_daily_pipeline_universe.py`、`test_universe_scope.py` 共 7 passed。
- 当前状态：管道范围与 8 月缺口回补为 `canary / 待用户验收`。`stock_daily` 数据集整体仍为 `isolated / not-production`，本轮不提升 promotion。3800 / 全 A / 中证2000 仍需另行授权。
- 回滚：把 `pipeline_universe_scope` 改回 `CSI500`；新池文件可留着。不要删除 2019 年以来的日 K。

#### 2026-08-17 来源追踪 degraded 扫描空错误详情

- 用户可见故障：数据页来源追踪黄条写 `最近一次本地目录扫描降级: 未记录错误详情` / `latest_run_degraded`。
- 根因：`catalog_rescan` 只在 `failed` 时把 `scan_errors` 写入 `error_message`；`stock_daily` 在补完 legacy lineage 后改为 `degraded`，run 的 `error_code/error_message` 为空，页面只能走兜底文案。本轮重扫还暴露 8 月 CSI1800 合并分区（1804 行）没有匹配当前行数的 lineage，旧记录仍是 500/1297 行。
- 修复：降级扫描现在写入 `catalog_quality_degraded` 和 lineage 质量摘要；来源追踪在旧空 run 上也会回退到当前 lineage 说明。仅为 `stock_daily` 的 10 个 8 月分区补了 `legacy_local_artifact` 记录，未改 Parquet、未动财务。
- 验收：相关 catalog 测试 7 passed。正式目录 `stock_daily` 重扫 `catalog-f430736b…`，`degraded / 8,078,626 行 / latest=2026-08-14`，黄条改为说明 legacy lineage 降级，不再写“未记录错误详情”。这不把 `stock_daily` 提升为 accepted。
- 回滚：恢复 `service.py` / `provenance.py` 的空错误字段逻辑即可；新增 10 条 lineage sidecar 可单独删除，不影响日 K。

#### 2026-08-17 stock_daily 当前证据链收口

- 用户目标：不是关黄卡，而是让 `stock_daily` 的当前文件、当前 lineage、当前扫描三者对齐后自己变成 healthy。
- 当前事实：`2026-08-03..2026-08-14` 十个分区已经是 1804 行，且等于当时 CSI1800∪自选，含 `300750.SZ` / `600519.SH` / `000001.SZ`。旧 lineage 仍是 500/510 或 1294/1297 行；此前补的 `legacy_local_artifact` 虽然 row_count=1804，但质量是 degraded。扫描器选当前记录必须 `row_count == 当前文件行数`，对不上就等于没有当前证据。更老分区的 `pending_gate` 会被收成 unknown，历史 legacy 也会把整表拖成 degraded。
- 第一层：为这 10 个分区新增当前整文件 lineage，source=`public_quote_eod_merged`，`row_count=1804`，`scope=CSI1800`，`unit_version=canonical_daily_v1`。旧的 500/1297 记录和 legacy sidecar 都留着当历史，未改、未删。未改 Parquet，未改 `pipeline_universe_scope`。
- 第二层：扫描质量只看 `_current_artifact_lineage()` 的当前选用记录。当前文件对得上、schema/unit 正确、没有 scan_errors 时，`pending_gate` 和仅用于旧分区补录的 `legacy_local_artifact` 不再一票否决整表。当前文件没有匹配 lineage、缺列、unit 冲突、扫描中文件被改，仍失败。
- 验收：只重扫 `stock_daily`。最近一次 run `catalog-3e534b9f…` 为 `succeeded` / `healthy`，`error_code/error_message` 为空，`scan_errors=[]`。8 月 10 个分区当前选用记录均为 `public_quote_eod_merged` / 1804 行。来源追踪 `stock_daily` 的 `issues=[]`。三只大票正式日 K 仍是 `2019-07-05..2026-08-14`。相关 catalog 测试 46 passed。
- 当前状态：`stock_daily` 目录扫描证据链收口为 `canary / 待用户验收`。数据集整体仍不提升为 accepted。刷新数据页后，“证据缺口与本地问题”不应再因这次扫描出现。
- 回滚：删除本次新增的 10 条 `public_quote_eod_merged` 当前 lineage，恢复扫描质量规则，再只扫一次 `stock_daily`。不要删 Parquet，不要改管道范围。

#### 2026-08-17 TickFlow 免费档分批回补 8 月全 A 日 K

- 用户目标：既然 TickFlow 免费档能覆盖大约 5500 只历史日 K，就把 7 月 31 日后停更的范围外股票补到 8 月；必须按每批最多 100 只记录，并记下完整一轮耗时。不把日常 `pipeline_universe_scope` 改成 ALL。
- 档位：本机 `TICKFLOW_API_KEY` 为空，`mode=none`，`https://free-api.tickflow.org`。`kline.daily.batch` = 60 次/分钟、每批 100 只。只补历史日 K + 对应 enriched；不拉实时、分钟、深度。
- 窗口：`2026-08-03..2026-08-14` 共 10 个已有交易日。脚本 [`scripts/sync-tickflow-fullmarket-august.py`](/Users/simon/Trading/one-trading/scripts/sync-tickflow-fullmarket-august.py)。日志：`data/logs/tickflow-fullmarket-august-batch1.jsonl`、`...-full.jsonl`、`...-retry.jsonl`。
- 分批与耗时（Asia/Shanghai）：
  - 试跑第 1 批：15:59:22 开始，100 只 / 1000 行 / 拉数 2.044s / 含 enriched 8.707s；8-14 从 1812 到 1912。
  - 主轮剩余 37 批：15:59:36 开始，16:01:11 结束，墙钟 94.722s。其中拉数合计 67.834s，enriched 26.881s。35 批成功，2 批科创板空返回（第 30/32 批，各约 7.5–7.7s）。主轮后 8-14 = 5340。
  - 空批重试 3 批：16:02:15 起，墙钟 3.895s，补回 203 只 / 2017 行，8-14 = 5540。
  - 最后 4 只单独再拉：`300176.SZ` / `301655.SZ` / `600984.SH` / `603221.SH`；TickFlow 没有完整 8-14 日 K，8-14 仍为 5540。对应 enriched 补 200 只，6.433s。
  - 完整一轮（试跑 + 主轮 + 重试 + 收尾 enrich）大约 **15:59:22 到 16:02:25，约 3 分 3 秒**。若只算主轮 37 批，是 **1 分 35 秒**。
- 物理结果：`kline_daily` / `kline_daily_enriched` 的 8-03 为 5330，8-14 为 5540。CSI1800∪自选 1804 只仍在。抽查 `300750.SZ` / `600519.SH` / `000001.SZ` / `000006.SZ` 8-14 都在。证券表 5544 只里，8-14 缺 4 只。`pipeline_universe_scope` 仍是 `CSI1800`，`public_data_scope` 仍是 `CSI800`。
- 旁注：当天 15:31 盘后公开快照另写了 `date=2026-08-17`、1804 行、`source=public_quote_eod`，不是本轮 TickFlow 回补。
- 当前状态：一次性 8 月全 A 日 K 回补为 `canary / 待用户验收`。不是每天自动更新 5500 只，也不提升 `stock_daily` accepted。
- 回滚：不要删 2019 年以来日 K。若只要回到 CSI1800 日常范围，保持 `pipeline_universe_scope=CSI1800` 即可；新补的 8 月范围外行可留着。

#### 2026-08-18 市场看板默认选日收口

- 用户目标：用户没指定日期时，按查询时刻显示最新可用大盘；不要把公开快照写成正式日 K。
- 实现边界：`build_market_overview(..., default_to_live=True)` 只给首页 `/api/overview/market` 未带 `as_of` 的请求使用。选日顺序是：内存 live enriched 已是今天 → 今天磁盘 `quote_snapshot` → 正式 `kline_daily_enriched` 最新日。复盘等调用方仍 `default_to_live=False`，只认正式 enriched。
- 装配：今天只有快照、没有正式 enriched 时，用快照重算涨跌家数和成交额，响应带 `data_mode=intraday_snapshot`；均线 / 涨停梯队先留空。用户点回历史日只读那天正式账，不把今天快照混进昨天。
- 未做：不写 `kline_daily` / `kline_daily_enriched`，不改 `pipeline_universe_scope`，不改 15:30 盘后管道、财务、复权、分钟线、Hermes，不改午休停全市场轮询，不部署。
- 自动检查：`tests/test_market_overview_as_of.py` 与既有 `test_market_snapshot_service.py` 共 5 passed；前端 Dashboard / Review 相关 2 passed。
- 物理核对：正式日仍停在 `2026-08-17`、1804 行，含 `300750.SZ` / `600519.SH`；今天只有 `quote_snapshot/date=2026-08-18` 5209 行。没有新增 18 日正式分区。
- 当前状态：看板默认选日收口为 `implemented / 待用户验收`。不是全 A 扩容，也不取消“快照不能冒充正式日”。
- 回滚：恢复 overview 只认正式 enriched 最新日；不要删 Parquet，不要改管道范围。

#### 2026-08-18 盘中活跃换手现算

- 用户目标：首页「活跃换手」在盘中不要空着。数据台已有换手所需原料：正式 `kline_daily_enriched.turnover_rate`，以及今天 `quote_snapshot` 的成交量 + `instruments.float_shares`。
- 根因：今天看板走 `intraday_snapshot` 后，公开快照本身没有 `turnover_rate`，装配又没按行业分析同一公式现算，于是 `active_leaders` 为空。
- 实现：`_snapshot_rows_for_date()` 用 `volume * 10000 / float_shares` 现算百分点换手，不写回正式日 K / enriched。
- 自动检查：`tests/test_market_overview_as_of.py` 4 passed，覆盖盘中榜排序且不新增 18 日正式分区。
- 当前状态：`implemented / 待用户验收`。不是新数据集，也不改管道范围。
- 回滚：恢复快照行不派生 `turnover_rate` 即可。

#### 2026-08-26 盘中近似指标装配

- 用户目标：首页盘中不要把趋势强度、涨停梯队、炸板、量比显示成 0 / 1.00。
- 实现边界：只改 `build_market_overview` 盘中装配。量比复用行业分析已有的近 5 日 `quote_snapshot` 均量；涨跌停/炸板按昨收 + 板块/ST 规则现算，不用维表旧涨跌停价；趋势用昨日正式日均线/60 日高低对照今日快照现价；连板 = 昨日高度 + 今日是否仍封。
- 响应新增 `indicators_source=intraday_approx` / `indicators_approx=true`。`data_mode` 仍是 `intraday_snapshot`。不写 `kline_daily` / `kline_daily_enriched`，不拉 HiThink，不灌桌面 20G。
- 2026-08-26 空态/雷达降级：`vol_ratio` 未就绪时为 `null`，不再默认 `1`；雷达每轴带 `ready`；情绪分只平均已就绪轴，并返回 `emotion.partial` / `emotion.note`（盘中部分维度不可用）。`limit.ready` / `trend.ready` / `trend.extremes_ready` / `activity.vol_ready` 供用户台空态。涨停数仍是真实 0 或近似计数，只有未装配时才 `ready=false`。
- 自动检查：`tests/test_intraday_overview.py` + `tests/test_market_overview_as_of.py` 共 10 passed。
- 物理核对（2026-08-26 本地正式 `DATA_DIR`，未写今日正式分区）：涨停 54 / 炸板 49 / 最高 5 连板；站上 MA5/20/60 约 63%/56%/49%；量比均值约 0.83、放量约 6.8%；装配约 0.32s。
- 当前状态：服务视图 `implemented / 待用户验收`。不是新数据集，也不把近似写成正式收盘口径。
- 回滚：恢复盘中 `indicators_ready=false` 时清零均线/涨停/量比，以及量比默认 `1` 进雷达即可。

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

#### 4.6 覆盖补丁 2026-09-10（不是 D-P2-04）

- 目标：正式 `calendar.parquet` 从 `2026-08-31` 扩到至少今日 + 2026-10，让行业窗时效能离开「交易日历未覆盖到当日」。
- 主树只用 `calendar_probe.fetch_szse_calendar_range` / `build_trading_calendar_from_szse` + `publish_dataset`。新增 `extend_trading_calendar_from_szse`：候选 = prior ∪ 新月，空月失败保旧。`allow_status_flip=False`，`cleanup_staging_on_success=False`。
- 不把日历挂进 `daily_pipeline`。不用日 K / 腾讯补洞。SH/SZ/BJ 仍是深交所开闭旗展开。
- 备份：`/Users/simon/备份/codex/20260910-142649-trading-calendar-before-wp2`。隔离 dry-run 2007 行、`2025-01-01`～`2026-10-31`、August 重叠通过后再切正式文件。
- 正式切后：1824 → 2007 行，`min` 仍 `2025-01-01`，`max=2026-10-31`，`source=szse_month_list`，三所同日 `is_open` 一致。10 月深交所已发布（31 日 / 17 开市）。
- 自动检查：`tests/data_lab/test_calendar_extend.py` + probe/publish 共 18 passed。
- 已登录 HTTP 5/63：`calendar_covers=true`，时效 `fresh`（盘中期望 9/9），金额与加总仍精确相等。见 `docs/investigations/2026-09-10-calendar-extend/evidence/`。
- 当前状态：本补丁 `canary`。`trading_calendar` 生命周期仍是 `isolated / not-production`。`D-P2-04` 保持 `parked`。
- 2026-09-11 核对：正式日历仍 2007 行、`max=2026-10-31`、`source=szse_month_list`，sha `dfd9f647…`。空月失败保旧 / prior union 源码未改。行业窗 `calendar_covers=true`。未再 publish。

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

#### 2026-08-13 盘中部分分区过夜失效修复

- 用户可见故障：前端整页 `Unexpected Application Error!`（React "Objects are not valid as a React child {code, message}"）。
- 根因链：`date=2026-08-12` 分区是 8-12 盘中约 14:10 同步的当日部分数据（199 分钟点，当日语义合法）；次日它成为历史日期，`GET /api/market-pulse` 自动解析到该最新分区后按历史标准（216..242 分钟）校验失败返回 500，错误 detail 为 `{code, message}` 对象；前端 `api.ts` 把该对象原样送入全局 toast，`ToastContainer` 渲染对象导致整棵路由树崩溃。
- 数据修复：显式重同步 `2026-08-12`（现为完整收盘会话），241 分钟 + 21 事件共 262 行，lineage `market-pulse-b963384e...`；Catalog `market_pulse` 重扫 `healthy / 1,302 行`。
- 读取契约修复：`query_market_pulse` 自动解析（未显式指定日期）时跳过未通过校验的分区并回退到最近有效分区，被跳过日期通过响应字段 `skipped_invalid_dates` 披露，不静默；显式指定日期仍严格抛错。回归测试 `test_query_auto_resolve_skips_stale_partial_partition`。
- 前端加固：`api.ts` 四处错误 detail 提取统一经 `errorDetailToText` 归一化为字符串（对象取 `message`）；`Toast` 增加非字符串运行时护栏。任何后端结构化错误 detail 不再可能击穿路由树。
- 自动检查：market pulse 后端 8 项通过、目标 Ruff 通过；前端全量 137 项通过。运行面 `3018`（--reload 已热载）与 `3011` 无需重启。
- 边界：盘中同步当日部分数据仍为合法行为（当日语义）；本修复不改变同步质量门，不加自动调度。

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

### 4.13 `reference_derived_recovery`（valuation_daily / limit_up_events / index_membership_history）

#### 目标、授权与来源

- 用户于 2026-08-13 02:25 +0800 单独授权：从分支提交 `7019d031ef81c00ca5e812f7910278d291d1f841` 移植 `price_limits.py`、`financial_pit.py` 和 M6 派生逻辑，在主树把三个数据集恢复生产并回填到 2026-08-12；同时授权 pools 的一次显式同步作为 membership 原料。`corporate_actions` 明确不在本包。
- 数据来源为全本地派生：`kline_daily`（价格与前收盘）、`kline_daily_enriched`（连板高度）、`sealed_l1`（同日封单）、`instruments`（当前名称快照判 ST）、`financials/shares`（严格 PIT 股本）、`pools`（成分快照）。除 pools 显式同步外，构建过程零外部请求。
- pools 真实生产者：中证指数公司公开 CSV 端点（`csindex`），Adapter 为主树既有 `backend/app/services/free_sources/pools_public.py`；本轮一次显式拉取 CSI300 300 / CSI500 500 / SSE50 50，`as_of=2026-08-12`，全部成功。

#### one-trading 自有实现

- 移植基础件：`backend/app/price_limits.py`（板块/ST/北交所涨跌停规则与整分 half-up 取整）、`backend/app/services/financial_pit.py`（PIT 列规范化、restatement 保留、严格 as_of 过滤）。
- 派生 Module：`backend/app/services/reference_derived.py`；与 7019d03 原实现的三处差异均已在模块 docstring 披露：sealed_l1 封单只取同日分区（原实现会把任意日期封单套到所有交易日）、membership 支持以既有 members.parquet 为基线做快照差分（持续成员保留原 effective_from、移出成员写 effective_to、新成员标 `snapshot_diff`）、lineage 增加覆盖披露字段。
- canonical：三数据集沿用 v2 契约（`valuation_daily_v2` / `limit_up_events_v2` / `index_membership_history_v2`），字段与 7 月物理文件一致；估值 PE/PB/PS/PCF 在无权威历史估值源时保持 null，市值只在严格 PIT 股本存在时派生。
- catalog 注册：三数据集加入 `DATASET_DEFINITIONS`（reference 家族、`unit_policy=reference`、`coverage_policy=on_demand`），`tests/data_catalog/test_models.py` 的必备清单同步更新，目录数据集数 26 -> 29。
- 显式入口：`scripts/rebuild-reference-derived.py`；默认 dry-run，`--apply` 才写；构建 valuation/limit 时强制 `--start/--end` 防止无界历史回填；apply 后按数据集触发目录重扫并以真实 `sync_run` 状态判定成败（修复过一次"读 dataset_state 保留旧值误报 healthy"的脚本缺陷）。未加入任何自动调度。

#### 运行坐标、备份与正式数据

- 运行坐标：主树 `main@31216dd` + 未提交改动，正式 `DATA_DIR=/Users/simon/Trading/one-trading/data`，后端服务未运行（单写者）。主运行 `refderived-20260812194343`（窗口 2026-07-22..2026-08-12），补充运行 `refderived-20260812194648`（重建 2026-07-21 老 schema 分区）。
- 写前备份：`/Users/simon/备份/codex/20260813-025300-one-trading-m6-reference-recovery`（三数据集原目录 + pools 原目录 + README/回滚说明）。
- 正式产物（as_of 2026-08-13 03:47 +0800）：
  - `valuation_daily`：17 个分区（2026-07-21..2026-08-12），53,364 行、5,535 个 symbol，Catalog `healthy`。当前 `financials/shares` 全部来自 `instruments_snapshot`、严格 PIT 可用行为 0，因此全部行 `shares_pit_safe=false`、市值列诚实为 null（价格壳）；待财务 PIT 工作包补齐权威股本后市值自动可派生。
  - `limit_up_events`：17 个分区（同窗口），1,799 行、1,016 个 symbol，Catalog `healthy`；2026-07-21 全市场日 444 条事件，规则推价与交易所整分取整一致（如 37.46 x 1.1 = 41.21）。
  - `index_membership_history`：850 行、800 个 symbol，`healthy`；2026-07-17 种子与 2026-08-12 快照差分无成员变动，全部行保留原 `effective_from=2026-07-17`，无 `snapshot_diff` 行。
  - `pools`：850 行，`as_of=2026-08-12`，`healthy`。
- 覆盖披露（lineage 逐分区记录 `coverage_scope / source_daily_rows / source_daily_symbols / scope_note`）：2026-07-21..2026-07-31 分区为 `full_market_daily`（每日 5,197..5,528 只）；2026-08-03..2026-08-12 分区为 `pipeline_scope_daily`（每日 507..509 只，即 CSI500+自选并集），如实反映当前日线管道范围，未用 quote_snapshot 补近期日期。
- 老 schema 修复：`date=2026-07-21` 两个分区为 7 月早期 M6 代码写的 v1 schema（缺 `unit_version` 等列），首轮重扫如实 `catalog_quality_failed`；补充运行用 v2 重建后三数据集重扫全部 `succeeded`。

#### 自动检查与状态

- 新增/移植回归：`tests/test_reference_derived.py`（含 PIT 股本门、板块规则、封单同日门、快照差分、orchestrator 端到端与 lineage 披露）、`tests/test_price_limits.py`、`tests/test_financial_pit_e6.py`、`tests/test_financial_pit_v2.py`，共 24 项通过；后端全量 `431 passed, 2 skipped`；目标文件 Ruff 通过。未提交 commit。
- 当前状态：三数据集均为 `canary / 待用户验收`。Catalog `healthy`、回填完成和测试通过不等于 `accepted`；`production` 与是否加入任何调度另行授权。
- 回滚：用上述备份恢复四个目录，删除两个 run_id 前缀的新增 lineage，重扫目录即可；不影响 kline、财务、instruments 等其他数据集。
- 下一步（待用户决定）：验收当前三数据集；财务 PIT 迁移（让估值市值非空）与 `corporate_actions` 外部生产者接入均为独立候选，不自动开工。

### 4.14 `share_capital_pit`（financial_shares PIT 升级 + valuation_daily 市值）

#### 目标、授权与真实生产者

- 用户于 2026-08-13 03:51 +0800 授权"财务 PIT 迁移（让估值市值非空）"。
- 真实生产者：东方财富 `datacenter.eastmoney.com` `RPT_F10_EH_EQUITY`（HSF10 股本结构，逐股全页拉取）。live 核查（2026-08-13）：`NOTICE_DATE` 为真实公告日、`END_DATE` 为变动日、`TOTAL_SHARES`/`LISTED_A_SHARES` 单位为股；600000.SH 全历史 69 条。
- 单位与语义：`total_shares`/`float_shares` 单位股，`float_shares=LISTED_A_SHARES`（流通 A 股）；`effective_date=END_DATE`、`announce_date=NOTICE_DATE`；带真实公告日的行经 `financial_pit` 严格 PIT 门（`pit_unsafe=false`），无公告日的行保留但不进入严格 as_of 查询。

#### one-trading 自有实现与运行

- Adapter：`backend/app/services/free_sources/share_capital_public.py`（逐股全页、单股失败继续、整批 `merge_financial_pit` 合并 + staging 原子替换；既有 `instruments_snapshot` 行共存保留）。显式入口 `scripts/sync-share-capital.py`（默认 dry-run，`--universe pipeline`=CSI500+自选并集）。未加入自动调度。
- 正式运行（2026-08-13 04:03..04:11 +0800，`refderived` 主树，服务未运行）：509/509 只全部成功、0 失败，拉取 19,282 条股本变动历史；`financials/shares` 从 20,133 行升至 32,215 行，其中严格 PIT 可用 19,282 行 / 509 只。lineage `financial-pit-shares-c5a0a24c...`（financial_cn_v2）。
- 估值重建：`rebuild-reference-derived.py --datasets valuation_daily`（窗口 2026-07-21..2026-08-12）17 个分区重建。范围分区（8-03..8-12）市值覆盖 100%（509/509）；全市场分区（7-21..7-31）市值覆盖为已同步的 509 只（约 9.2%），由 lineage 与 `shares_pit_safe` 列如实披露。抽查 `600756.SH` 8-12：`total_mv = close 16.37 x total_share 349,628,753` 逐位一致，`shares_source=eastmoney_f10_equity`。
- Catalog：`financial_shares` 重扫 `succeeded`，`healthy / 32,215 行`（此前 degraded/20,133）；`valuation_daily` 重扫 `succeeded / healthy`。
- 写前备份：`/Users/simon/备份/codex/20260813-040000-one-trading-pit-shares-and-corporate-actions`（financials/shares、reference/corporate_actions、adj_factor 三目录 + SHA-256 + 回滚说明）。

#### 自动检查、状态与边界

- 回归：`tests/free_sources/test_share_capital_public.py` 3 项（PIT 门、快照行共存、部分失败继续、幂等、估值市值端到端）；后端全量 `443 passed, 2 skipped`；目标文件 Ruff 通过。未提交 commit。
- 当前状态：`canary / 待用户验收`。全市场 5,539 只股本扩容（约 5.5k 请求）与自动更新节奏需另行授权。
- 回滚：用上述备份恢复 `financials/shares`，重跑估值重建（窗口同上）即回到无市值版本；删除本次 lineage。

### 4.15 `corporate_actions`（外部生产者接入）

#### 目标、授权与真实生产者

- 用户于 2026-08-13 03:51 +0800 授权"corporate_actions 外部生产者接入"。
- 真实生产者：东方财富 `datacenter-web.eastmoney.com` `RPT_SHAREBONUS_DET`（全市场分红送转明细，分页批量）。live 核查（2026-08-13）：56,411 行全历史，含 `PLAN_NOTICE_DATE`/`NOTICE_DATE`/`EQUITY_RECORD_DATE`/`EX_DIVIDEND_DATE`、送股/转增/派息结构化数值与实施进度。
- 单位与语义：`cash_per_share=PRETAX_BONUS_RMB/10`（税前元/股）、`stock_ratio=(送+转)/10`；`announce_date` 优先预案公告日；无除权除息日的预案行跳过；`point_in_time=false`、`history_guarantee=as_collected`。

#### one-trading 自有实现与运行

- Module：`backend/app/services/corporate_actions_sync.py`，自 `7019d03` 的 M5.3 corporate_actions 模块移植并适配：正式事实抓取改为批量报表（新 source `eastmoney_sharebonus_det` 加入 FORMAL 集合；逐股 F10 解析器保留为备选）；分支 egress_policy 未移植，外部访问边界由显式入口承担；prior 行按 append-only 原样保留，本轮 crosscheck 只给新增行盖章（当前逐股核对状态由 `adj_factor/verification.parquet` 承载），修复了旧行状态翻转触发 overlap 门的问题。
- schema/catalog：`data_lab/schemas_reference.py` 移植 corporate_actions schema（unit_version 对齐 `corporate_actions_v2`）；`DATASET_DEFINITIONS` 注册 corporate_actions（第 30 个数据集，reference 家族 / on_demand）。
- 显式入口：`scripts/sync-corporate-actions.py`（默认零网络 dry-run）。首次 apply 被 overlap 门如实拦截（`plan_status=4449` 旧行翻转、kept_prior），修正合并顺序后二跑发布成功——失败保旧路径得到一次真实验证。
- 正式发布（2026-08-13 04:36 +0800）：112,606 行、5,529 只，PK 唯一；正式事实 55,745 条（现金分红 44,450、混合 8,899、送转 2,364、unknown 32），`ex_date` 覆盖 1991-02-26..2026-08-21；既有 56,861 条 adj 派生信号原样保留。verification 表：4,971 只 `verified_events`、116 只 `verified_no_event`、456 只 `unverified`、1 只 `source_failed`。
- 诚实边界：5,488 行 `quarantined`，主因是本地复权因子只覆盖到 2026-07 下旬，比其新的事件（含未来除权日）暂无法双向核对；扩充 adj 覆盖后可复核降级，不在本轮擅自执行。
- Catalog：corporate_actions 重扫 `succeeded / healthy / 112,606 行 / latest=2026-08-21`；`stock_adj_factor` 重扫 `degraded`（既有 legacy lineage 语义，非本轮引入）。
- 写前备份：同 4.14 备份目录（含 `corporate_actions-before` 56,861 行与 `adj_factor-before`）。

#### 自动检查、状态与边界

- 回归：`tests/test_corporate_actions_sync.py` 9 项（注册、标记映射、信号/正式事实边界、批量报表解析、分页失败如实报告、隔离、验证标记、lab 端到端 + 幂等）；后端全量 `443 passed, 2 skipped`（04:08 +0800，早于当日 04:28/04:33 两处模块修正——批量解析显式 schema、prior 行 append-only 合并；两处修正后相关套件 9 项于 04:33 复跑通过）；目标文件 Ruff 通过。未提交 commit。
- 当前状态：`canary / 待用户验收`。不自动调度；PDF/正文、复权因子扩容、pay_date 补齐均另行授权。
- 回滚：用备份恢复 `reference/corporate_actions` 与 `adj_factor`，重扫目录；不影响其他数据集。

### 4.17 `hithink_official_special_data`（官方涨跌停池 / 龙虎榜 / 竞价 / 最新估值快照）

#### 目标与使用价值

- 用户于 2026-08-25 授权使用其 HiThink/Fuyao API Key，补当前数据台相对同花顺官方服务仍缺的独立事实层：官方涨停原因文本与封板时间、跌停/炸板官方池、龙虎榜、集合竞价快照、最新估值快照。
- 价值边界：补 `limit_up_events` 派生表没有的官方原因文本，以及本地尚未落库的龙虎榜、竞价、官方最新估值。不替换 TickFlow `stock_daily`，不覆盖本地派生 `valuation_daily` / `limit_up_events`。

#### GitHub 情报引用与固定上游点

- 主记录：`/Users/simon/Trading/数据台GitHub项目借鉴记录.md` 中 `HiThink-Tech/Financial-API`，固定点 `main@9dbef74d2ce535857e610eec265bcb9302942d48` / `v0.1.5`。
- 能力目录：`/Users/simon/Trading/数据台GitHub项目数据能力目录.md` 第 4.1 节。
- 真实生产者是同花顺官方服务 `https://fuyao.aicubes.cn`，仓库只是客户端情报，不 vendor CLI/DuckDB/MCP/Skill。

#### 真实生产者、参数、字段、分页、错误和更新

- 认证：Header `X-api-key`；成功条件 HTTP 200 且信封 `code==0`。`4001/5xxx` 可退避，`1xxx/2xxx` 不重试。Key 只进入本轮进程环境 `HITHINK_FINANCE_API_KEY`，未写入 git、`.env`、secrets.json、Hermes profile、日志或文档。
- 接入端点：涨跌停三池全市场分页、龙虎榜按交易日、集合竞价/最新估值默认本地 14 只自选股。竞价量单位为手。

#### 本地分支、commit、worktree、DATA_DIR

- 工作区：`/Users/simon/Trading/one-trading`，分支 `main@31216dd`，工作区本就有大量未提交/未跟踪改动；本轮未提交 commit。
- 正式 `DATA_DIR=/Users/simon/Trading/one-trading/data`。今日 Asia/Shanghai `2026-08-25` canary 已写入四个独立根，未改写 `kline_daily/date=2026-08-25`、`reference/limit_up_events`、`reference/valuation_daily`（基线 35 个 parquet，哈希未变）。

#### Provider/Adapter、schema、sync、manifest/checkpoint、Parquet

- Adapter：`backend/app/services/free_sources/hithink_finance.py`。龙虎榜官方 `stock_items` 可能对同一 `thscode` 给两行不同金额；canary 规范化按机构净额/净额绝对值保留更完整一行，再校验主键唯一。
- 今日正式产物：
  - `hithink_limit_pool` 89 行（涨停 65 / 跌停 2 / 炸板 22）→ `data/reference/hithink_limit_pool/date=2026-08-25/part.parquet`
  - `hithink_dragon_tiger` 60 行 → `data/reference/hithink_dragon_tiger/date=2026-08-25/part.parquet`
  - `hithink_auction_snapshot` 14 行，lineage `volume_unit=lot` → `data/reference/hithink_auction_snapshot/date=2026-08-25/part.parquet`
  - `hithink_valuation_snapshot` 14 行，`history_guarantee=latest_snapshot_only` → `data/reference/hithink_valuation_snapshot/as_of=2026-08-25/part.parquet`
- Catalog：`2026-08-25 21:43 +0800` 只 rescan 这四个 id；四项 `local_materialized=true`，`quality=healthy`，生产者/lineage source 均为 `hithink_fuyao`。

#### local-only API 与实际消费者

- GET `/api/hithink/*` 只读本地独立目录。Data 页采集区有「同花顺官方特色数据」显式同步卡，说明四个独立根属于「参考数据」，不覆盖 TickFlow 日线或派生涨跌停/估值。无自动调度。

#### 数据质量、失败恢复和幂等

- mock 测试仍通过。真实 canary 中龙虎榜先因官方重复主键失败，涨跌停池已先发布；去重后重跑龙虎榜/竞价/估值成功。空值与负数估值原样保留。

#### 自动检查与真实运行面

- 后端 `tests/free_sources/test_hithink_finance.py` 8 passed（含重复龙虎榜去重）。前端同步卡 2 passed。
- Codex 内置浏览器于 21:45 打开 `http://192.168.1.104:3011/data`，被重定向到登录页 ` /login?redirect=%2Fdata `，未输入密码。采集区/来源追踪需管理员登录，本轮未完成屏幕点击验证；落点证据以独立 Parquet、lineage 和 catalog rescan 为准。

#### 当前状态与验收结论

- 状态：`canary`。四个独立目录已有今日 Parquet + lineage，catalog 四项已本地落库。**不是** `accepted` / `production`。

#### 阻塞、剩余风险和下一步

- 数据页三处屏幕验证仍差管理员登录：采集卡、参考数据四张卡、来源追踪里的 `reference/hithink_*` 与 `hithink_fuyao`。登录后即可看到，不需要再拉官方数据。
- 非目标保持有效：不替换 TickFlow 日线、不下载 10 年 dump、不覆盖 `limit_up_events` / `valuation_daily`、不把 HiThink MCP 接到 Hermes、Key 不入库、不自动调度。
- 下一步工程计划工作包：`D-R-04`。

#### 2026-08-26 盘中 KPI 同日只读消费

- 用户授权：盘中涨停 KPI 读今天官方池并标明来源；今天池不在就继续昨收近似；不要拿昨天 65 家冒充今天；收盘后仍以正式日为准，官方池不盖收盘口径。
- 实现：`load_limit_pool_for_date()` 只认 `reference/hithink_limit_pool/date={as_of}/part.parquet`，日期不符或分区不存在返回 None，绝不调用「最新日」回落。`build_market_overview` 仅在 `data_mode=intraday_snapshot` 时用同日池覆盖 `limit_*` / 炸板 / 连板梯队，并写 `limit.source=hithink_official_pool`。`data_mode=official` 忽略同日池。
- 不写 `kline_daily` / `kline_daily_enriched`，本轮不发起 HiThink 外连同步。物理盘仍只有 `date=2026-08-25`（65/2/22），没有 `date=2026-08-26`，因此今天运行面应继续走近似。
- 数据集状态仍是 `canary`，不是 `accepted` / `production`。
- 自动检查：`tests/test_market_overview_as_of.py`、`tests/free_sources/test_hithink_finance.py`。
- 回滚：去掉 overview 对 `load_limit_pool_for_date` 的同日覆盖即可。

### 4.16 `repair_daily_override_start`（日K修复指定起点）

- 用户可见故障：数据页「上游工具」点击日K修复后，前端只显示 `500 Internal Server Error`；群里/目录无新数据。
- 证据（as_of 2026-08-18 14:36/14:37，正式本地 `DATA_DIR=/Users/simon/Trading/one-trading/data`）：`POST /api/data/repair-daily` 请求体 `{start_date: "2026-07-19"}`，`repair_daily` 已打出 `override_start_date=2026-07-19`，随后 1.7–3.2ms 返回 500。
- 根因：上游修复包装层调用 `daily_pipeline.run_now(..., override_start_date=...)`，但本地盘后管道签名只有 `repo / capset / on_progress`，实际抛 `TypeError: unexpected keyword argument`。用户台 `RepairDailyPanel` / `api.ts` 本身已接通，无需改页面。
- 本轮改动只落数据台：`run_now` 增加可选 `override_start_date`；日常盘后调度不传则仍走原分支。修复入口传入后跳过「今天已有数据只刷实时行情」捷径，日K / 除权 / 指数 / ETF 起点对齐用户日期。
- 自动检查：`backend/tests/test_repair_daily_override.py`。
- 当前状态：`isolated`。代码层已消除 500；未在正式运行面点一次真实修复，也未重算已存在交易日的 enriched。已存在日期被覆盖后，指标不一定自动重算。
- 回滚：去掉 `run_now` 的 `override_start_date` 参数及对应测试即可；不涉及用户台页面回滚。

<a id="news_market_flash"></a>
### 4.19 `news_market_flash`（财联社/新浪/外媒快讯缓存，旁路）

- 目标与边界：用户授权把 go-stock 三栏市场快讯重写进 one-trading。不依赖 go-stock HTTP/SQLite/GPL Runtime。禁止全局定时抓取、PDF/OCR、通知、交易、模型、远端部署。
- GitHub 情报：用户台 go-stock 主记录；真实生产者是财联社 `www.cls.cn/api/cache`、新浪 `zhibo.sina.com.cn/api/zhibo/feed`、TradingView `news-mediator.tradingview.com`。仓库不是权利方。
- 本地：`backend/app/services/free_sources/news_public.py`、`backend/app/services/news.py`、缓存 `DATA_DIR/news/market/{cls,sina,foreign}.json` + `lineage/news_market_*`。
- GET `/api/news/market` 零外连；POST `/api/news/market/refresh` 按源显式取数。单源失败保留上次 items。新浪 JSONP 只剥包装，不执行 JS。
- 当前阶段：`isolated`。自动测试已覆盖解析/失败不覆盖/GET 零外连。
- 2026-09-09 有限真实 POST（隔离 `DATA_DIR=/Users/simon/Trading/one-trading/data/news-isolated-20260909`）：财联社 20 条、新浪 20 条、外媒 20 条，三源均成功。随后 GET `/api/news/market` 读到同一缓存。不是 accepted/production。
- 同日 P2-3：单源 market 成功/失败替换加进程内锁，失败路径重新读当前缓存，避免把并发成功回滚。未宣称跨进程锁。本轮未再 POST 三源。隔离 GET 仍各 20、`from_cache=true`。
- 计划工作包 `D-R-06`。证据：`docs/cursor-handoffs/news-policy-20260909/live-fetch.json`（交接目录，非实施权威）。本轮锁/测试见 `p2-fix/fix-check.md`。
- 同日收口：独立数据复核 `5613e51d` Technical PASS（39 tests；隔离 GET 三栏各 20）。主审 IAB 在隔离 3041 见到真实缓存与单源刷新。生命周期仍 `isolated`。as_of 2026-09-09 收口当时写「正式 `data/news` 仅 `.gitkeep`」；**那是当时事实，不是当前事实**。
- 2026-09-11 纠正（只读核 hash，未写这 10 个 JSON）：正式 `data/news` 已有 9/10 三源各 20、目录 82、政策 56。政策 `items.json` sha256=`de17d4826c89b72c3990470b3c52316819dba82cb990638a54d737eb9e5bfd1a`。旧隔离 `data/news-isolated-20260909/news` 仍各 20 / 目录 82 / 政策 526，`items.json` sha256=`bf6a424d87e7437eb3786e0657feba4857ff0c28ea2eafa4ba24078e4a8aa84c`。外媒缓存 `producer` 字段仍写「外媒」；GET 覆盖为 TradingView 聚合，不把 go-stock 写成生产者。
- 2026-09-11 readiness：只读元数据叠加（最近成功/最后尝试/缓存更新/状态中文）。GET 零抓取零写。本轮不对正式/旧隔离执行 POST，不真实外源抓取。自动测试 57 passed（夹具/tmp_path）。生命周期仍 `isolated`，不是 `canary`/`accepted`/`production`。运行面未由本任务启动。见 `docs/cursor-handoffs/news-readiness-20260911/`。
- 2026-09-11 P2 修补（不重做原实现）：政策 24h 新鲜度不再回退 `cache_updated_at`/`updated_at`；仅 `last_success_at` 或可验证的 `last_refresh.ok=true`+`fetched_at` 可判新旧，未知保持 unknown/null/`known=false`，不宣布新鲜或 stale。失败写不再用 `updated_at` 补造 `last_success_at`；`cache_updated_at` 只表示本次写缓存。原 workflow `wf-bb9c0f1c-efe0-4c8c-86c7-34318de7de9a` failed/verification_failed 与独立审计 `bcc3ee1b-5c6f-44df-8edd-0deda29f30e6` partial/changes_requested 保留为失败门，不是 PASS。正式 20/20/20/82/56 与旧隔离 20/20/20/82/526 只读未合并。后端无 reload，旧 PID 旧模块不能当新代码。生命周期仍 `isolated`。证据：`docs/cursor-handoffs/news-readiness-20260911/p2-repair.md`。
- 基线分类（2026-09-12）：9/9 快讯基础闭环属于 00:19 基线。9/11 readiness 元数据与 P2 是**基线不含 / 仅历史未重新授权**。57/62 等原测试数字保留，不降级删除。

<a id="news_policy_items"></a>
### 4.20 `news_policy_items`（官方部门目录 + 部委官网政策缓存，旁路）

- 目标与边界：完整官方部门目录与部委官网政策入库。关键词搜索是 `GetStoredPolicyNews` 语义的本地历史检索，不是国务院政策文件库远端搜索。`gov_policy_lib_api.go` 不属于此政策页，本轮不扩建。
- 真实生产者：中国政府网部门列表 `https://www.gov.cn/home/2023-03/29/content_5748953.htm`，再抓目录内官方站点及已核验 JSON（金监总局/证监会/疾控局/能源局）。取数限定静态已核验来源/官方部门目录，拒绝用户任意 URL 与 SSRF。
- 本地：`backend/app/services/news_sources/policy.py`、`DATA_DIR/news/policy/{departments,items}.json`。重点部门写入 `user_data/news/key_departments.json`，按账号隔离。
- GET 只读缓存并支持本地分页/加载更多；刷新用 POST。上游无真正可见分页，仅有 100/200 抓取限额，不得虚称上游已支持翻页。
- 当前阶段：目录 `source-verified`（官网页真实解析 82 个部门）；条目缓存 `isolated`。
- 2026-09-09 有限真实 POST：重点部门 11/12 成功；国家统计局 SSL handshake timeout，未造样本。全部门浅抓 fetched=302、入库累计 495、7 个部门失败（公安部 HTTP 521、司法部 too many redirects、海关总署 HTTP 412、国务院新闻办公室 HTTP 521、国家消防救援局 HTTP 405、国家药品监督管理局 HTTP 412、国家卫生健康委员会 HTTP 502）。本地关键词「新能源」GET 命中 4 条，`from_cache=true`。
- 同日验收修复：首轮样本把教育部 `/2026/78355/`、`/2026/2026_zt09/` 误读成 `2026-78-35` / `2026-20-26`。已加公历校验；隔离 `DATA_DIR` 清除 7 条无效日期（条目保留、日期留空、不再排到最新）。首轮 `live-fetch.json` 不改；重测见 `retest-policy-dates.json`。状态仍 `isolated`，不是 accepted。
- 同日日期来源续修：旧 `URL_DATE_RE` 会把 `/202609/1194319.shtml`、`/202607/1200abc.shtml` 拼成 `2026-09-11` / `2026-07-12`。现只接受完整有边界的 URL 日期；隔离缓存清除 46 条月目录+编号/长编号拼接日期，条目保留。民委 `1194319` 按官网同条列表日与原文 `PubDate` 更正为 `2026-09-09`，不是文章编号。另对民委单部门做了有限列表刷新（+30），未做全市场/历史补抓。GET 仍零外连、不隐形写。正式 `one-trading/data` 未写。证据：`retest-policy-date-provenance.json`。状态仍 `isolated`，不是 accepted。
- 同日独立复核确认：技术 PASS；P2-1 为央行长编号 `.../2026090909080511735/` 与真实列表日 `2026-09-09` 碰撞时被 `legacy_loose_url_date` 误清。`7d39a518` / `c89fcd1c` 失败历史不改写。
- 同日 P2-1/P2-3：可选 `date_source` 贯通 provider/merge/存储/GET；只 scrub `/YYYYMM/`+文章编号跨斜杠拼接；长 ID 前 8 位与已清空历史不得猜日。refresh/scrub 进程内锁 + 重新读当前缓存。隔离只刷新央行一次：源 `http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html` → `https://www.pbc.gov.cn/...` 200；15 条本条列表日（`date_source=list`），长编号条恢复 `2026-09-09`。未造数据。同标题跨部门去重曾丢掉外汇局 `safe/2026/0814/27784.html`，已改为按 `(标题, 来源)` 去重并从备份合回该条。磁盘 **526**；民委 `1194319` 仍 `2026-09-09`；无 `2026-09-11`。GET 零写。as_of 2026-09-09 当时正式 `one-trading/data/news` 仍仅 `.gitkeep`。证据：`p2-fix/pbc-refresh-evidence.json`。状态仍 `isolated`，不是 accepted。
- 不是 accepted/production。计划工作包 `D-R-06`。证据：`docs/cursor-handoffs/news-policy-20260909/live-fetch.json`。
- 同日收口：`5613e51d` PASS + 隔离 526；主审 IAB 见 82 部门、央行 15 条有日期、空日期不猜、失败源可见。生命周期仍 `isolated`（目录仍 `source-verified`）。不升 `canary`：as_of 9/9 非正式 `data/news`，未宣称全 82 源/全部历史完整采集。P2-2/P2-5/单进程锁仍保留。见 `docs/cursor-handoffs/news-policy-20260909/closeout/acceptance.md`。
- 2026-09-11 纠正：正式政策缓存现为 56 条（sha256=`de17d4826c89b72c3990470b3c52316819dba82cb990638a54d737eb9e5bfd1a`），`last_refresh.scope=department` / 证监会，不能当成 82 部门已全部更新。旧隔离仍 526（sha256=`bf6a424d87e7437eb3786e0657feba4857ff0c28ea2eafa4ba24078e4a8aa84c`）。本轮只读元数据，不 POST、不 scrub、不合并两套缓存。筛选无匹配 ≠ 源空。正式接入方案待授权，见 `docs/cursor-handoffs/news-readiness-20260911/formal-admission-plan.md`。
- 2026-09-11 P2 修补：只改读时新鲜度判定与失败写的成功时间语义；不迁移正式/旧隔离 JSON。正式缓存现有 `last_refresh.ok=true`+`fetched_at`，GET 仍可推导成功时间，但单部门刷新不能代表 82 部门已全部更新。生命周期仍 `isolated`，不是 `canary`/`accepted`/`production`。
- 基线分类（2026-09-12）：9/9 政策基础页/缓存属于基线。9/11 元数据与 P2 新鲜度语义是**基线不含 / 仅历史未重新授权**。

<a id="d-offline-margin-api"></a>
### 4.21 `D-OFFLINE-MARGIN-API`（离线两融只读查询 + K 线读失败语义）

- 目标/边界：现有 `GET /api/f10/margin-trading` 增加显式 `source=offline_quantdb`；默认仍读自有 `DATA_DIR`。只读 QuantDB `2_base_sector/margin_trading/<symbol>.parquet`。附带修正日 K / 分钟本地读取异常被吞成空数据、从而误触发 TickFlow/TDX 的问题。不改 Catalog/Provider/UI，不接分钟或历史日线原包，不写原包/`DATA_DIR`/lineage。
- GitHub 情报：沿用 2026-09-09 数据链简化审查，不重审上游。调查：`/Users/simon/Trading/one-trading/docs/investigations/2026-09-09-data-chain-simplification/`。本轮实现证据：`/Users/simon/Trading/one-trading/docs/investigations/2026-09-09-offline-margin-implementation/`。
- 坐标：one-trading 脏主树；正式 `DATA_DIR=/Users/simon/Trading/one-trading/data`。备份：`/Users/simon/备份/codex/20260909-160932-offline-margin-kline-read`。
- 实现：`margin_trading_public.query_margin_trading_result` + 就近映射；`stock_f10.py` 回真实 source/`as_of`/`status`/`missing_fields`；`config.offline_quantdb_root`（环境键 `OFFLINE_QUANTDB_ROOT`）源码默认关闭；本机 `.env` 已开启并指向 `/Users/simon/Trading/下载数据/quant_data`。`user_console_data.stock_margin_trading` 可选参数增加 `source`，不是新查询页。K 线：`KlineReadError`；`_scan_daily_symbol` / `get_minute` 无文件仍空，损坏/权限/解析失败上抛；`GET /api/kline/daily|minute` 返回 503，不 fetch/persist。
- 自动检查（一次，实施当时，未在收尾重跑）：`38 passed` / exit 0（`test_margin_trading_public` / `test_offline_margin_api` / `test_kline_read_failure` / `test_stock_f10_api` / `test_kline_minute_api` / `test_hermes_data` / `test_get_daily_cache_reuse`）。不是全仓 tests 通过。`test_repository_index` 与 `test_kline_daily_latest` 一条失败经独立 review 对照备份确认是既有问题：backup `kline.py:494` / current `kline.py:501` 的 `_latest_live_candle` 本来就没有传 `refresh=refresh_asset`；`get_name_map` / `rebuild_views` 在 backup 与 current `repository.py` 都不存在。本轮未改对应逻辑。Hermes `source` 转发只有代码/测试覆盖，未验收真实 Hermes 调用。
- 运行面：实施当时 3018 reload 监督进程 PID `3510`，worker PID `36813` 于 `2026-09-09 16:12:35 +0800` 拉起，晚于本轮源码与 `.env`。当时对 `300502.SZ` 的 local/offline GET 均为 HTTP 401（已设密码、未登录、未新建会话），只作历史。同 venv 只读真实文件：local 5 行 `as_of=2026-08-04`；offline 5 行 `as_of=2026-08-26`，`securities_lending_balance`/`margin_balance` 为 null。`300502.SZ.parquet` 与自有 `part.parquet` 读写前后 size/hash 不变。
- 目标运行面验收（Codex IAB 观察，2026-09-09 约 16:24 +08，不是本执行端调用）：已登录 `http://127.0.0.1:3011`，Vite 代理 3011→3018；同源 `GET /api/f10/margin-trading?symbol=300502.SZ&limit=5&source=local|offline_quantdb` 均 HTTP 200。local：`source=local` / `status=ok` / `count=5` / `as_of=2026-08-04`。offline：`source=offline_quantdb` / `status=ok` / `count=5` / `as_of=2026-08-26`。使用现有登录态，未读/打印 cookie，未改认证。不能再声称业务接口未验证。
- 当前阶段：仍 `canary`。功能实现 + 相关小样本测试 + Codex 小样本运行面已接受「两融原包单文件直读 + 日K/分钟K读取失败明确 503 且不补拉」。独立 review `2f6bf8b8-878e-452d-9a05-45222c04efeb`（session `9757c5a9-9540-4dc0-beb5-829fdd17c781`）PASS，无必改 P1/P2；候选 `65c0282f1e6fd248e48c032494099b163d952d6fe56d681a4c90a757f65560b9`。不是全市场源数据 `accepted` / `production`。不顺带接受全市场/分钟估值。下一数据集不开工。
- 2026-09-11 用户台目录只读入口见 `docs/workbench-development-log.md` 的 `data_catalog_offline_margin_20260911`。本条 API/失败语义未改，不因此升生命周期。
- 回滚：用上述备份目录恢复已改文件，并从 `.env` 删除 `OFFLINE_QUANTDB_ROOT`。

<a id="external-readonly-metadata"></a>
### 4.22 `external_readonly_sources_metadata`（外置包只读状态，不是新数据集）

- 目标/边界：为 `/data` 总览提供轻量只读元数据：`offline_quantdb_root` 未配置 / 目录不可访问 / 已配置；声明目前只支持两融。只 `stat` 配置根，不 walk/hash，不进托管存储，不扫入 Catalog，不复制/新 DB。HTTP 不接受路径参数。路径仅管理员字段返回。
- GitHub 情报：不重审。调查依据 `docs/investigations/2026-09-09-data-source-ui-overlap/README.md`。实现说明 `docs/investigations/2026-09-09-data-source-convergence/README.md`。
- 用户台总览展示与查询按钮见 `docs/workbench-development-log.md` 的 `data_source_overview_status_20260909`。2026-09-11 目录折叠入口见同文件 `data_catalog_offline_margin_20260911`。仍不是新数据集，不扫入 Catalog、不计入托管存储。
- 坐标：one-trading 脏主树；正式 `DATA_DIR` 不变。备份：`/Users/simon/备份/codex/20260909-210317-data-source-convergence`。
- 接口：`GET /api/data/external-readonly-sources`。查询仍走既有 `GET /api/f10/margin-trading?source=offline_quantdb`。默认 local 两融行为不变。
- 矩阵状态映射：`build_capability_matrix` 为复权/实时/财务列出已实现的 `public` 候选，并把 `same_as_daily` 解析为跟随日K；只改展示/usable，不改 getter 默认值或 fallback。
- 当前阶段：9/9 只读元数据接口属于 00:19 基线。9/11 目录折叠入口的隔离 UI `verified`（2026-09-11 14:55–15:00，总工线程 `01a07a79-1c8e-73e0-af8f-85939177bb8b`；精确指针 `docs/workbench-development-log.md` 的 `data_catalog_offline_margin_20260911`）是**基线不含**的历史记录。恢复后新授权重做见工作台 `data_catalog_offline_margin_restore_20260912`，不把本条 9/11 状态降级或删除。80GB 原包非全导入。不是 `source-verified` 之后的数据集晋升，也不是 `accepted` / `production`。相邻 `4.21` 仍 `canary`，不因此升级。
- 回滚：用上述备份恢复本轮已改既有文件；新文件直接删除。

<a id="offline-valuation-readonly-contract"></a>
### 4.23 `offline-valuation-readonly-contract`（QuantDB 估值历史原包只读查询契约）

- 目标/边界：用户本轮明确授权完成估值历史原包只读查询契约与 4 样本对账。只读 QuantDB `5_technical_derived/valuation/<symbol>.parquet`。不重扫 80G，不重做 `D-OFFLINE-MARGIN-API`，不改 Catalog/Provider/API/UI/调度，不写原包或正式 `DATA_DIR`，不加载 StockDB 恢复或前收盘候选，不把项目 null overlay 到外包。协调源任务 `01a08eff-a837-7103-82fd-860c84b2fbec`。
- GitHub 情报：不重审。沿用 2026-09-06 本地包评估与 `package_sanity.json` 估值盘点。修复 SQL 边界仍以 `/Users/simon/Trading/下载数据/stockdb_repair_20260905/read.sql`、`read_preclose.sql` 为准：精确身份、仅原 null 补、前收盘独立 opt-in；本轮只读未改。
- 坐标：`/Users/simon/Trading/one-trading` 脏主树 `main@31216dda527cd4ec177b9cbf6fd1c524dbadbe82`；正式 `DATA_DIR=/Users/simon/Trading/one-trading/data` 未写。默认 QuantDB root=`/Users/simon/Trading/下载数据/quant_data`。首次落地备份：`/Users/simon/备份/codex/20260911-valuation-readonly-01a06d0f`。P2 改前备份：`/Users/simon/备份/codex/20260911-171200-offline-valuation-p2-readonly`（脚本、测试、本包证据、本日志；不备份原包）。本日志只增量改本段，不恢复整份旧日志。
- 实现：`scripts/offline_valuation_query.py` 可 import/CLI；`--symbol --start --end --limit`；`--audit --summary` 默认只读打印、不写文件。详细证据仅显式写到 `docs/investigations/2026-09-11-offline-valuation-readonly/`。不导入 `app`/DataStore，无远程 fallback。结果含 source、dataset/layout、symbol/date、覆盖/`as_of`、文件真实 `fields.original`、optional 缺失与 `missing_versus_project` 分披露、quality；JSON `allow_nan=False`。负 PE 保留；NaN/Inf 输出 null 并打 anomaly。无源/无文件/无窗口/缺字段/损坏/权限/重复键/父级或文件 symlink 逃逸/空错身份键/非法 schema 可区分。P2：解析链必须落在 resolved root 内；空 Symbol 不补 requested_symbol；字符串日期严格 YYYY-MM-DD；limit 拒绝 bool 与非整数截断。
- 自动检查：`backend/.venv/bin/python -B scripts/test_offline_valuation_query.py -v`，18 passed / exit 0。修复前 12 项不能充当本轮验收。新增覆盖两种父级 symlink 逃逸、空/错 Symbol、错误 time/数值类型、重复 null time、日期尾缀、bool/float limit、Inf 不计入恒等式、optional 缺失不写入 original。夹具只在 temp。
- 4 样本实读（不是全市场扫描）：`000001.SZ`/`000338.SZ`/`600519.SH` 各 2588 行、2016-01-04..2026-08-27；`300750.SZ` 1995 行、2018-06-11..2026-08-27。四文件均无重复 symbol+date、无 NaN/Inf、无负 PE。`total_mv==close*total_capital` 在有限值行上分别 2530/2530/2530/1995 精确成立，只记恒等式一致性；单位 `unknown/unverified`，已移除 `inferred_share_and_cny`，未静默换算，未套日 K `amount×10000`。`dividend_rate` 不凭外观确认 ratio/percent。全市场覆盖只引用 2026-09-06 盘点：by_symbol 5554 文件 / 10,770,127 行。
- 与项目 `valuation_daily` 重叠键（2026-07-21..2026-08-12）：只对正式 `data/reference/valuation_daily`，不用 isolated-runtime 证明正式库缺数。外包 68，项目 36，共同 36，项目独有 0。8 月 3–12 日项目分区约 507–509 行（范围采集），这 4 只不在其中。`close` 36/36 原值相等。`pe_ttm`/`pb`/`ps_ttm`/`total_mv`/`total_share` 项目侧 36 行全 null（`valuation_daily_v2` 设计 + `shares_pit_safe=false`）；null 不等于外包值，不填 0，不 overlay。二源 close 相等不是行情真值，也不是 PIT 通过。
- 运行面：查询目标是本脚本 CLI，不需 UI/API/服务重启。重复查询 `000001.SZ` 2026-07-21..2026-08-12 limit=5 两次 stdout 一致；`as_of=2026-08-27`。实读 26 个源/对账/SQL 文件读写前后 size/mtime/SHA 不变。外部 `/Users/simon/Trading/下载数据/stockdb_quantdb_integration_review_20260906/README.md` 保持不动，不是本轮交付，也不是验收阻断；新旧报告互相链接即可。
- 当前阶段：`isolated`。查询契约 + P2 夹具测试 + 4 样本真实原包/项目重叠对账已完成。工程 CLI 验收不等于源数据 `accepted` / `production`，也不把本轮 4 样本写成全市场 canary。API/Provider/Catalog/UI/调度未改。
- 回滚：用 P2 备份恢复脚本/测试/本包证据/本段日志；首次落地备份仍可用于更早报告。备份可恢复，不自动回滚。
- 2026-09-12 恢复/核验：任务开始时，2026-09-10 00:19:35 数据采集版树缺失上述两脚本（这是当时历史句，不是现在判断）。写前可恢复备份 `/Users/simon/备份/codex/20260912-offline-valuation-readonly-restore-before-wf1`（当时两脚本与新证据目录均 absent；只复制本日志 `sha256=769f0d979d6b7097155954c809c810894aba456b14d2b0a8d18c652dcab7caa2`；未备份大包）。从最终 post-P2 备份原样恢复、未改写：`scripts/offline_valuation_query.py` `d33d6d1354d9c8e79361b2fbf31968422e78a62322acf09ff55d9cf9e05b8a85`；`scripts/test_offline_valuation_query.py` `10aa5a107ff98e94080ae48453a6909a6209886051018108a4c20713a045fe50`。源：`/Users/simon/备份/codex/20260911-restore-pre-cursor-before-20260911T224838/overwritten-or-removed/scripts/`。本轮证据：`docs/investigations/2026-09-12-offline-valuation-readonly-restore/`。未改 `docs/investigations/2026-09-11-offline-valuation-readonly/`。新授权任务 `01a09186-52ee-7311-962b-b642b18be905` 已把两脚本留在当前树；不要再复用「文件缺失」。
- 2026-09-12 检查：`backend/.venv/bin/python -B scripts/test_offline_valuation_query.py -v` 18 passed / exit 0。四样本有界查询 `000001.SZ`/`000338.SZ`/`600519.SH`/`300750.SZ` `--start 2026-07-21 --end 2026-08-12 --limit 5` 均 `status=ok`，`source=offline_quantdb`，单位仍 `unknown/unverified`。重叠对账外包 68 / 项目 36 / 共同 36；`close` 36/36 原值相等；`pe_ttm`/`pb`/`ps_ttm`/`total_mv`/`total_share` 项目侧仍全 null，不填 0、不 overlay。同参查询两次 stdout sha `a7247052e5036e72f684563939b8a9f6a2e83a871fd9533ab45161cc8a84189b`（7212 bytes）稳定。CLI 区分 `root_missing` / `not_found` / `empty_window` / `unreadable` / `permission` / `duplicate_key` / `invalid_symbol` / `invalid_date` / `invalid_limit` / `symlink_escape`；NaN/Inf 输出 JSON null + `value_flags`。26 个相关输入 before/after 不变；`.env` sha `8855712d771c3fc3396eaf360a594b48f1fbab3332c73abcde87d6d317711d38` 不变且未暴露内容。四样本不得外推全市场、真值、单位或 PIT。
- 当前阶段仍为 `isolated`。这是缺失 CLI 的原样恢复与有界复验，不是 `source-verified` 之后的晋升，也不是 `accepted` / `production`。未开始 Provider/API/Catalog/UI/调度或下一数据包。未来 local-only API 仍缺：明确 API contract/route、严格 local-only adapter 边界、响应/错误映射、auth/exposure 决策、针对性 API 测试、目标运行面核验。
- 本轮回滚：用 `/Users/simon/备份/codex/20260912-offline-valuation-readonly-restore-before-wf1/files/one-trading/docs/data-platform-development-log.md` 恢复本段；删除本轮恢复的两个脚本与 `docs/investigations/2026-09-12-offline-valuation-readonly-restore/`。不自动回滚。

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

### 5.3 `local_catalog_recovery_20260813`

#### 问题、授权与边界

- 用户于 2026-08-13 01:36 +0800 授权 P0：本地 catalog 恢复、残留目录清理与 runtime 日志轮转。
- 问题证据：本地 `control/catalog.sqlite3` 在 2026-08-12 15:31 +0800 全量重扫中 8 个数据集 `catalog_quality_failed`（legacy 分区缺 lineage、`adj_factor/verification.parquet` QA 文件误判、`financial_shares` v1/v2 契约、`kline_index_*` 旧 `index_daily_v1` unit_version、`quote_snapshot` 扫描竞态），dataset_state 冻结在 2026-07-22 旧值（如 `stock_daily` 记录 1,389,629 行，物理实际 8,064,651 行）。
- 事实澄清：2026-08-12 18:59 本地已写入 739 条 `legacy_local_artifact` lineage（stock_daily 251、kline_etf_daily/kline_etf_enriched 各 242、balance/shares/sealed_l1/adj_factor 各 1），且开发树已含 scanner 当前 lineage 选择契约；`scripts/reconcile-legacy-market-lineage.py` 对正式 `DATA_DIR` dry-run 计划为 0。恢复只需一次持久化重扫；本轮未改任何 Parquet、未新增任何 lineage。

#### 执行与结果

- 写前备份：`/Users/simon/备份/codex/20260813-014411-one-trading-p0-local-catalog-recovery`；`catalog.sqlite3` SHA-256 `f67d1db86f40cc4f656f03fbf0a95cf4b66b13dd2540e1e3ea7227ac91cbc617`。
- 重扫（2026-08-13 01:45 +0800，离线驱动、`3018` 无服务、单写者）：26 数据集，16 healthy / 7 degraded / 3 unknown / 0 failed；sync_runs 19 succeeded / 7 degraded。`stock_daily` 8,064,651 行（degraded 为 legacy lineage 诚实标记）、`stock_enriched` healthy 8,064,651、`quote_snapshot` healthy 84,353、`index_daily`/`index_enriched` healthy 231,576。与线上 Deployment `6a7c57c70d41a78958bb46a2` 的 16/7/3 分布一致。
- 存储归档（同备份目录）：`.data.staging-233907...`（275M）与 `data.k4-residual-20260722_114016`（186M）移入 `residue/`；184M 无轮转 `runtime.jsonl` 移入 `logs-archive/`。历史文档引用这两个残留目录时以备份位置为准。
- 代码：`backend/app/services/runtime_logging.py` 为 `runtime.jsonl` 增加与 `app.log` 同策略的 20MB x 5 滚动；回归测试 `backend/tests/test_runtime_logging.py::test_runtime_jsonl_rotation`；日志套件 3 passed，目标文件 Ruff 通过。未提交 commit。
- 边界：本轮不改变任何数据集生命周期状态；7 个 degraded 是 legacy 和解的预期语义，3 个 unknown 为无物理数据的空数据集。回滚方式见备份 README。

### 5.4 `workspace_worktrees_cleanup_20260813`

- 用户于 2026-08-13 02:25 +0800 授权"任务 A：历史 worktree 清理"；执行窗口 02:27–02:35 +0800。
- 删除前快照（02:27）：`git worktree list` 共 33 条（主树 + `/private/tmp` 5 条 prunable + `.worktrees` 27 条）与 29 个本地分支清单，已存入备份；`four-atom-closeout/output`（约 6.1G K4 事故产物）整体移入备份。
- 删除（02:29–02:35）：`.worktrees` 下全部 27 个工作副本删除（含已确认干净、定位为参考实现的 `data-platform-convergence-v1@7019d03`），`git worktree prune` 清除 `/private/tmp` 5 条失效记录。首次删除在沙箱内因 `.venv` 硬链接受保护而残留，经用户批准后在沙箱外完成。
- 边界核验：29 个本地分支全部保留；`codex/data-platform-convergence-v1` 分支仍指向 `7019d031ef81c00ca5e812f7910278d291d1f841`；主树未提交改动与 `data/` 未触碰。任一 worktree 可用 `git worktree add <path> <branch>` 重建。
- 效果：项目目录约 21G 降至约 1.9G（其后数据集工作使数据量回升，2026-08-13 04:45 快照约 2G 量级）。
- 备份：`/Users/simon/备份/codex/20260813-022700-one-trading-worktrees-cleanup`（worktree/分支快照 + `four-atom-closeout-output/` + README/恢复说明）。
- 本条为工作区维护记录，不改变任何数据集生命周期状态。

### 5.5 `zeabur_data_platform_sync_20260814`

#### 目标、授权与边界

- 用户于 2026-08-13 授权把本地已完成的数据台修复同步到既有 Zeabur `one-trading` service；未新建第二套 service 或 PVC。
- 发布仍从 `/Users/simon/Trading/one-trading-release` 执行。镜像不含开发 `DATA_DIR`、身份库、Session、Hermes、Secret 或日志。
- 本条记录的是代码发布与线上共享参考数据闭环，不把各数据集生命周期提升为 `accepted / production`。

#### 应用发布

- 当前 Deployment：`6a7df12c201aaa81bcf9fedb`（前一失败尝试 `6a7df0b7201aaa81bcf9fec1` 因 `.zeaburignore` 丢弃 `scripts/` 导致 `COPY scripts/sync-share-capital.py` 失败；随后取消对 `/scripts/` 的忽略后重建成功）。
- 前一生产 Deployment：`6a7c57c70d41a78958bb46a2`，现为 `REMOVED`。
- build：`local-sync-20260814-fcb218172c4bd451`（内容 SHA-256 `fcb218172c4bd4510c64f0aa4e497a0611bc7d0c0dffc9570644bfd64ddb5f9d`）。
- 公网 `/health`：`200 / status=ok / version=0.1.68 / release_channel=private / build_sha=local-sync-20260814-fcb218172c4bd451`。
- 未登录 `/api/auth/status`：`configured=true / multi_user=true / registration_enabled=true / invite_required=false`。
- 镜像内 30 个 `DATASET_DEFINITIONS`，并包含 `rebuild-reference-derived.py`、`sync-share-capital.py`、`sync-corporate-actions.py`、`reconcile-legacy-market-lineage.py`。
- release 树验证：后端 447 passed / 2 skipped；前端 144 passed；`tsc` 与生产构建通过；本地 Docker 镜像 `one-trading-sync-20260814` 冒烟 `/health=ok`。

#### 数据叠加与线上重建

- 备份根：`/Users/simon/备份/codex/20260814-002514-one-trading-zeabur-data-platform-sync`。
- 目标目录写前快照：远端 `/home/ubuntu/one-trading-migration/20260814-002514/pre-overlay-targets.tar`，SHA-256 `153c758344d0fb0d3dd6205784835acd041fb4f19ad8faa0de2a22096f0b4175`。
- 本地叠加包已打好（41 Parquet + 81 lineage，SHA-256 `74efb3fdd7fdc2ebba65481e77d09a9988ece464c1b7c1febee9deb02ab3e46e`），但 `zeabur server/service exec` 不转发 stdin，改在新镜像内用 PVC 已有日线/财务重建，并对外部生产者做一次显式同步。
- 容器内 `rebuild-reference-derived.py --apply --start 2026-07-21 --end 2026-08-12`：估值 17 分区、涨跌停 17 分区、成分历史 850 行。2026-08-12 估值按线上全日线覆盖（5,262 只），早于本地 pipeline 范围。
- `sync-corporate-actions.py --apply`：`actions.parquet` 2,862,830 bytes / 112,616 行。
- `sync-share-capital.py --universe pipeline --apply`：503/503 成功，发布 32,025 行，PIT 可用 19,092 行 / 503 只。
- `sync_market_pulse(2026-08-12)`：241 分钟 + 21 事件共 262 行，替换 8-12 盘中部分分区。
- 未覆盖身份库、`tenants/`、`user_data/`、`hermes/`、`control/` 密钥；保留线上独有 `market/pulse/date=2026-08-13`。

#### Catalog 与当前物理事实

- 全量重扫会因 `quote_snapshot` 盘中写入 `file changed during scan` 而 fail-closed 并保留旧快照（`stale=true`）。改为对新增/变更数据集逐个 `rescan(dataset_id)`。
- 最终 `list_catalog`：30 项，`stale=false`，刷新 `2026-08-13T17:12:45.939669Z`；21 healthy / 6 degraded / 3 unknown / 0 failed。
- 新闭环：`valuation_daily` healthy 58,117；`limit_up_events` healthy 1,799；`index_membership_history` healthy 850；`corporate_actions` healthy 112,616；`financial_shares` healthy 32,025；`market_pulse` healthy 1,558。
- 3 个 unknown 仍是空数据集（`etf_minute` / `etf_adj_factor` / `depth5`）；6 个 degraded 仍是 legacy lineage 诚实标记。

#### 状态

- 本条为 `production deployment verified`。各数据集用户验收仍以各自 4.x 条目为准。
- 回滚应用：前一 Deployment `6a7c57c70d41a78958bb46a2`。回滚 PVC 与回滚应用相互独立；完整 PVC 根仍是 `/Users/simon/备份/codex/20260812-164436-one-trading-zeabur-latest-sync/online-pvc/pre-sync-complete-pvc.tar.zst`。

### 5.6 `source_trace_github_as_adapter_reference`

#### 目标与边界

- 用户 2026-09-02 授权减法第一步：来源追踪不再把 GitHub 当数据集父母。只改登记和展示，不改 Parquet、同步、查询，也不关 `stock.db` 写入口。
- 本条不是数据集闭环，不改变 `stock_daily` / 资金流 / 分钟线的 lifecycle，也不把 `D-P0-01` 改成 `active`。

#### 登记与 Interface

- 数据台：`backend/app/data_catalog/provenance_registry.py`、`backend/app/data_catalog/provenance.py`。
- `SUBJECT_REFERENCES` 只保留 Adapter 对照。`stock_daily` 为 `tickflow-stock-panel` + `go-stock`（非运行时）；`stock_instruments` 不再挂 easy_tdx/akshare；`stock_minute` 仍登记 `easy_tdx` 为运行时 Adapter。
- 资金流扩展的 `true_producers` 只申报东财；`go_stock_snapshot` 只在 lineage 实际观测到时出现。go-stock 默认角色不再带 `local_fallback`。
- `missing_github_mapping` 保持 `info`：不是数据缺失，也不表示生产者未知。

#### 自动检查

- `backend/.venv/bin/python -m pytest tests/data_catalog/test_provenance.py -q`：8 passed。
- 用户台对应检查见工作台开发日志 `source_trace_github_as_adapter_reference`。

#### 当前状态

- 当前状态：展示层 `verified`。只读对照正式 `DATA_DIR`：`stock_daily` 对照 `tickflow-stock-panel` + `go-stock`（均非运行时）；`stock_minute` 的 `easy_tdx` 为运行时 Adapter；资金流日线 `true_producers=['eastmoney']`。
- 正式 `3018` 曾因热重载卡住；只结束卡住的 spawn worker，未重启用户长驻 uvicorn 父进程。恢复后 `GET /health` 为 200。
- 各数据集 lifecycle 不变。未标记 `accepted / production`。

#### 回滚与下一步

- 回滚恢复 `provenance_registry.py` / `provenance.py` 即可；不涉及物理数据。
- 第 2 步见 `5.7`；第 3 步见 `5.8`。

### 5.7 `stock_db_default_fallback_off`

#### 目标与边界

- 用户 2026-09-03 授权减法第二步：挡住单板块资金流日线仍可能把 `go-stock/data/stock.db` 写进正式分区的入口。
- 只改默认兜底。不改 63 日窗口算法，不删 `stock.db`，不重写已有分区，不插入 `D-P0-01`。

#### Adapter 与写入口

- `fetch_board_daily_history` 默认 `allow_local_fallback=False`。`FUND_FLOW_HISTORY_PREFER_LOCAL` 不能在默认路径上重新打开 `stock.db`。
- `GET /fund-flow/board/{code}/history` 刷新与空缓存显式传 `allow_local_fallback=False`。东财失败且无缓存时 502；有缓存则继续返回旧行，不再 persist。
- 行业/概念窗口回补本来就是 H5 + `allow_local_fallback=False`，本轮未改。
- 本地函数仍保留 opt-in `allow_local_fallback=True`，供测试或显式调用，不是页面默认路径。

#### 自动检查

- `backend/.venv/bin/python -m pytest tests/free_sources/test_fund_flow.py tests/free_sources/test_free_ext_api.py -q`：34 passed。

#### 只读运行面

- 正式 `DATA_DIR` 只读：行业 63 日 `window_complete=True`、`128/128` 满窗，`2026-06-03..2026-08-31`。概念 63 日 `window_complete=True`、`covered=504`。
- 已有残片未动：`ext_fund_flow_bk_daily` 仍有 256 行 `go_stock_local_snapshot`；`ext_fund_flow_concept_daily` 仍有 272 行。窗口累计继续只认 `eastmoney_fflow_day`。
- `go-stock/data/stock.db` 仍在。`GET /health` 200。本轮没有对正式分区执行 refresh 写入。

#### 当前状态

- 当前状态：写入口减法 `verified`。不是资金流数据集 `accepted / production`。
- 未标记任何 4.x 数据集 lifecycle 变化。

#### 回滚与下一步

- 回滚恢复 `fund_flow.py` 默认值和 `free_ext.py` 的显式参数即可。
- 第 3 步见 `5.8`。

### 5.8 `catalog_ext_data_directory_split`

#### 目标与边界

- 用户 2026-09-03 授权减法第三步：把 Catalog 里整桶 `ext_data` 拆成固定目录项。只改目录定义、扫描归属和来源追踪展示。
- 不改窗口算法、资金流写路径、正式 Parquet 内容或查询引擎。查询仍走 `ExtConfigStore` + `ext_data/{id}`。不把 Catalog SQLite 当查询真相，不把动态扩展表收进深 Module，不插入 `D-P0-01`。

#### Catalog 定义与扫描归属

- 数据台：`backend/app/data_catalog/definitions.py`、`scanner.py`、`provenance.py`、`provenance_registry.py`、`service.py`。
- 固定目录项：`ext_fund_flow_bk` / `_bk_daily` / `_concept` / `_concept_daily` / `_stock`、`ext_gn_ths` / `ext_hy_ths`。扫描根为 `ext_data/{id}`。
- `ext_data` 只保留 opaque 余项。允许它与 `ext_data/{id}` 父子重叠；扫描按最长前缀归属，同一文件只属于一个目录项。
- 来源追踪不再把这 7 个 ID 再列成 extension，避免和目录项重复。未建目录的用户表/分时余项仍走 extension。

#### 自动检查

- `backend/.venv/bin/python -m pytest tests/data_catalog/test_models.py tests/data_catalog/test_scanner.py tests/data_catalog/test_provenance.py tests/data_catalog/test_service.py -q`：78 passed。
- 用户台：`npm run test:run -- src/components/data/__tests__/DataCatalogSection.test.tsx src/pages/__tests__/Data.test.tsx`：26 passed。

#### 只读运行面

- 正式 `DATA_DIR` 只读扫描（未改 Parquet）：`ext_fund_flow_bk` 128 行、`_bk_daily` 16033/128 日、`_concept` 504、`_concept_daily` 59010/123 日、`_stock` 851、`ext_gn_ths` 5535、`ext_hy_ths` 5539，质量均为 healthy。
- 余项只剩 `ext_fund_flow_concept_minute`：357 行 / 2 个分区。
- 为把目录投影到页面，只对上述 8 个 dataset_id 做了 `POST /api/data/catalog/rescan`。未全量重扫，未点资金流回补/refresh。
- 用户台对应检查见工作台开发日志 `catalog_ext_data_directory_split`。

#### 当前状态

- 当前状态：Catalog 目录拆分 `verified`。不是资金流或同花顺分类池 `accepted / production`。
- 未标记任何 4.x 数据集 lifecycle 变化。`D-P0-01` 仍不因此开工。

#### 回滚与下一步

- 回滚恢复 Catalog 定义、扫描归属、来源追踪跳过规则和用户台「扩展数据」分组即可。已投影的 8 项 Catalog 状态可用同接口再扫回旧语义，或不扫只回代码。
- 第 4 项是明确不做的「简化」，不是下一张待授权工单。
- 三条总账见 `5.9`。

### 5.9 `subtraction_playbook_closed`

#### 目标与边界

- 用户 2026-09-03 要求把已做完的减法三条记成总账。本条不新增代码，不改 Parquet，不把任何数据集写成 `accepted / production`，不把 `D-P0-01` 改成 `active`。
- 这三条是平台减法，不是日 K / 分钟 / 同花顺四表闭环。日常页面可以继续用；正式数据集验收仍要另授。

#### 三条与指针

| 步 | 内容 | 本日志 | 用户台日志 |
| --- | --- | --- | --- |
| 1 | 来源追踪不再把 GitHub 当数据集父母 | `5.6 source_trace_github_as_adapter_reference` | `source_trace_github_as_adapter_reference` |
| 2 | 资金流日线默认关掉 `stock.db` 兜底 | `5.7 stock_db_default_fallback_off` | `fund_flow_stock_db_fallback_off` |
| 3 | Catalog 拆开 `ext_data` 糊桶 | `5.8 catalog_ext_data_directory_split` | `catalog_ext_data_directory_split` |

- 计划第 4 项仍是禁区：不统一 TickFlow/东财/腾讯 Provider，不恢复 `data_sync`，不把质量门改成「不过就不能切正式文件」。没有第 4 步工单。

#### 当前状态

- 三条减法工单关闭。各步状态仍以 `5.6` / `5.7` / `5.8` 为准，均为展示或写入口或目录 `verified`。
- `stock_daily`、资金流、分钟线、同花顺四表的 lifecycle 不因本条改变。
- 下一步工程若继续，另授 `D-P0-01` 或验收已落地 canary，不要再开减法工单。
- 总览存储分类中文标题是展示跟进，见 `5.10`，不是第 4 步减法。

### 5.10 `storage_category_titles_zh`

#### 目标与边界

- 用户 2026-09-03 要求按已落地的减法三条，把数据总览「本地存储」左栏改准确。只改正文标题和目录/来源跳转，不拆 `ext_data` 磁盘桶，不重写正式 Parquet，不改数据集 lifecycle。
- `ext_data` 仍是一个存储桶：7 个固定池 + 余项同目录。Catalog 目录项已经在 `5.8` 拆开；本条只避免把整桶「来源」误指到余项。

#### 展示 remap

- `backend/app/data_catalog/scanner.py` `_MANAGED_TITLES` / `_OPERATIONAL_CATEGORIES` 与 `service.py` `_CATEGORY_TITLES` 改为中文。
- `list_catalog()` 按 category key 回写 title，旧英文 meta 不用全量重扫也能出中文。
- 用户台跳转见工作台 `storage_overview_simplified_labels`。

#### 自动检查

- 后端含 `test_list_catalog_uses_current_chinese_storage_titles_for_legacy_english_meta` 的 catalog 测试已随本轮改动覆盖。
- 用户台：`StorageBreakdownCard` / `DataCatalogSection` / `Data.test` 共 29 passed。

#### 只读运行面

- 正式 `DATA_DIR` 未重扫、未改 Parquet。总览「扩展数据」仍是 396 文件 / 4.5 MiB。
- 未点资金流回补/refresh。未标记任何 4.x 数据集 lifecycle 变化。

#### 当前状态

- 当前状态：存储分类展示 remap `verified`。不是数据集 `accepted / production`。
- `D-P0-01` 仍不因此开工。

#### 回滚与下一步

- 回滚恢复 scanner/service 标题常量和 `list_catalog()` remap 即可。
- 不要把本条当成第 4 步减法。

### 5.11 `catalog_partial_commit_and_shares_lineage`

#### 目标与边界

- 用户 2026-09-03 要求检查并修复数据板块里的故障/降级展示。只修 Catalog 投影、扫描提交和一条缺失的 shares lineage。不重写正式 Parquet，不补日 K/分钟/复权，不开工 `D-P0-01`。
- 页面上的「降级」主要来自 2026-08-12 旧快照：全量重扫只要有一项先前可服务的数据集失败，整页状态都不提交。

#### 失败原因

- `quote_snapshot` 当日指数分区在扫描中被实时写入替换，报 `file changed during scan`。
- `financial_shares` 文件已在 2026-08-31 长到 41,784 行，匹配 lineage 仍停在 32,215 行，扫描记 `matching lineage is missing`。
- 这两项把 36 个已成功扫描（含复权因子/ETF/封板现为 healthy）整页丢弃，`catalog_stale=true`，卡片继续显示 8 月降级。
- 「准入状态未登记」不是数据故障：控制库只有 `trading_calendar` 一条策略。

#### 本地改动

- `CatalogService._rescan_locked`：全量扫描改为提交成功项，只保留失败且先前可服务项的旧状态；不再因为一项失败冻结全部 41 项。
- `CatalogScanner._parquet_facts`：文件中途被替换时最多重试 3 次，读到完整新版本；连续失败仍 fail-closed。
- 为当前 `financials/shares/part.parquet` 补 `legacy_local_artifact` sidecar：`lineage/financial_shares/unpartitioned/legacy-dffd14cfaaaa21ca8a1d9cab.json`，行数 41784。未改 Parquet。

#### 自动检查

- `backend/.venv/bin/python -m pytest tests/data_catalog/test_service.py tests/data_catalog/test_scanner.py -q`：39 passed。
- 用户台目录/数据页测试 26 passed。

#### 只读运行面

- 正式 `DATA_DIR` 全量重扫 `2026-09-03T08:03:11Z`：`catalog_stale=false`，38 healthy / 7 unknown（空数据集）/ 0 degraded / 0 failed。
- `stock_daily` 现为 8,192,756 行、最新 2026-09-03（旧卡片 2026-08-20 是过期投影）。
- `financial_shares` 41,784 行 healthy；`quote_snapshot` 167,842 行 / 最新 2026-09-03 healthy。
- 未点资金流回补/refresh。未标记任何 4.x 数据集 lifecycle 变化。

#### 当前状态

- 当前状态：目录投影修复 `verified`。不是日 K / 复权 / 股本 / 分钟 `accepted / production`。
- `D-P0-01` 仍不因此开工。

#### 回滚与下一步

- 回滚恢复 `service.py` 全量扫描提交、`scanner.py` 重试，并删除上述 shares lineage 文件即可。已提交的 catalog 状态可用同接口再扫。
- 分钟线 4 只、复权因子最新 2026-07-23 仍是覆盖缺口，不要用目录健康标签掩盖。

### 5.12 `financial_provider_local_key_first`

#### 目标与边界

- 用户 2026-09-03 要求在去掉采集页「采集状态」的同时，先改财务偏好键读取顺序。只改 runtime getter 和 setter 双写，不重写正式 `preferences.json`，不改 Parquet，不验收财务数据集。
- 现场文件同时有 `financial_provider=public` 和遗留 `financial_data_provider=tickflow`。旧 getter 让 v0.2 键获胜，页面可写 TickFlow，管道却跳过东财公开财务刷新。

#### 本地改动

- `get_financial_provider()` 改为 `financial_provider` 优先，没有本地键时才读 `financial_data_provider`。
- `PUT /preferences/financial-provider` 与 `PUT /preferences/data-providers` 同时写这两个键，避免再次分叉。删除自定义源时也一起复位。
- 未静默改官方 `data/user_data/preferences.json`。磁盘上两键仍分叉；runtime 现解析为 `public`，`is_public_financial_provider()` 为 True。
- 用户台采集页减法见工作台 `collection_status_control_plane_removed`。

#### 自动检查

- `backend/.venv/bin/python -m pytest tests/test_financial_provider_preference.py -q`：4 passed。
- 用户台 Data 页测试 16 passed。

#### 只读运行面

- 正式 `DATA_DIR` 未改 Parquet、未点资金流回补/refresh。
- 本机 getter：`financial_provider_resolved=public`，`is_public=True`；raw 仍是 `public` / `tickflow`。
- 已登录页自动调度出现「财务」；总览公开源兜底含「财务」。这是偏好读取，不是财务数据集 `accepted`。

#### 当前状态

- 当前状态：偏好读取顺序 `verified`。不是财务 / 日 K / 分钟 / 复权 `accepted / production`。
- `D-P0-01` 仍不因此开工。这不是第 4 步减法，也没有把 TickFlow / 东财 / 腾讯收成一个 Provider。

#### 回滚与下一步

- 回滚恢复 `preferences.py` getter 顺序和 settings 双写即可。
- 日历停在 2026-08-31、分钟线 4 只、复权最新 2026-07-23 仍是数据事实，不要靠文案消掉。

## 5.90 upstream_908b385_merge_foundation_20260908

### 目标与边界

- 只在候选目录做 4d27→908 的本地优先三路合并基底和静态诊断。
- 不写正式 `DATA_DIR`，不启动候选后端，不碰 3018 / WatchFiles 83220。
- 不是任何一个数据集的 `canary / accepted / production`。

### GitHub 情报引用与固定上游点

- `908b3855010fca39a424db43c6292f686c4418ba` / 基线 `4d27f3139ef58e25fc410b373363dd6bf40c6dfa`。
- 完整记录：`/Users/simon/Trading/docs/upstream-integrations/2026-09-08-latest-local-first/merge-foundation.md`。
- 旧 preflight 对 pipeline / kline_sync / quote_service / ext_pull 的整文件排除已被本轮完整整合取代。

### 真实生产者与本地实现

- 无新生产者。`capabilities.py:83` 仍是 `full_minute.field=None`。`indices.py` 仍有 `/list` `/search`。
- `pipeline.py` / `quote_service.py` / `repository.py` 已 `--ours` 并修到可 `py_compile`；908 的 staging / `guarded_collect` / ETF 生成仍有未接块，见 `next-adaptation.json` A3–A4 / A9–A11。

### 自动检查与运行面

- 候选 backend 598 个 `.py`：`py_compile` 退出码 0。未跑 pytest，未拉真实源。
- canonical HEAD / index 未动。

### 当前状态

- 当前状态：候选 `isolated`。
- 未标记 `canary / accepted / production`。

### 阻塞与下一步

- `backtest/strategy.py` 仍缺 `BacktestResultPolicy` / `StrategyDependencyResolver`（A8）。
- 下一阶段在候选里接完数据契约后再考虑隔离 fixture，不写正式盘。

## 5.91 upstream_908b385_candidate_adaptation_20260908

### 目标与边界

- 只在候选闭合 pipeline staging 与本地安全 publish，并跑隔离 DATA_DIR 上的针对性测试。
- 不写正式 `DATA_DIR`，不启动候选后端，不碰 3018 / WatchFiles。
- 不是任何一个数据集的 `canary / accepted / production`。

### GitHub 情报引用与固定上游点

- `908b3855010fca39a424db43c6292f686c4418ba` / 基线 `4d27f3139ef58e25fc410b373363dd6bf40c6dfa`。
- 完整记录：`/Users/simon/Trading/docs/upstream-integrations/2026-09-08-latest-local-first/adaptation.md`。

### 真实生产者与本地实现

- 无新生产者。`capabilities.py` 仍是 `full_minute.field=None`。指数 `/list` `/search` 仍在。
- `run_pipeline` 全量：908 流式暂存 + 本地 `_publish_enriched_partition`（原子写 + lineage）。不再和 `date_buffers` 交错。
- `historical_shares` 作为可选参数叠进本地涨跌停/换手计算。
- lots / custom_factors store 走 `user_data_dir`。

### 自动检查与运行面

- 候选 `compileall` exit 0；`app_py_tree_sha256=51073e55541a75d8a317c208f2c380d08afb8ac724f585b18684a563fa7b189f`。
- 针对性 pytest **70 passed**（含 enriched 全量重建/lineage、lots/factors 跨用户、publish ACL、ext pull 空 Key、回测 max_hold）。官方 venv 只读。
- 未做候选独立 `uv sync`。未拉真实源。canonical HEAD / index 未动。

### 当前状态

- 当前状态：候选 `isolated`。
- 未标记 `canary / accepted / production`。

### 阻塞与下一步

- A4 quote_service/repository 908 hunk、A9 ETF 加载器、A11 深度路由、A16 候选独立依赖仍开。
- 隔离 fixture 服务未证实，不启动。

## 5.91 upstream_9a4bdcd_a16_v6_isolation_20260909

### 目标与边界

- 只在候选关闭 A16 锁一致，以及 Polars 1.44.1 日线/enriched 多批次、并发写入、失败恢复、lineage 和 collect-guard 重入。
- 不写正式 `DATA_DIR`，不启 Web，不新增数据源工程。不是 `canary / accepted / production`。

### GitHub 情报引用与固定上游点

- 固定上游 `9a4bdcd07dfe999f123a8226608d4c90213fae5b`。
- 报告：`/Users/simon/Trading/docs/upstream-integrations/2026-09-08-latest-local-first/deps-isolation.md`。

### 真实生产者与本地实现

- 无新生产者。easy-tdx 1.20.6 用官方 wheel URL pin，不收窄 `requires-python>=3.11`。
- 候选独立 venv：Python 3.13.5 / Polars 1.44.1。正式 `.venv` 只读，仍是 Polars 1.40.1。

### 自动检查与运行面

- `uv lock --check` exit 0；`pnpm install --frozen-lockfile` exit 0。日志 `diagnose-a16-lock-check.log`。
- 首跑 `diagnose-a16-v6.log`：**5 failed, 28 passed**, exit 1，保留失败。
- 复跑 `diagnose-a16-v6-rerun.log`：**33 passed**, exit 0。含 `test_job_stall_and_cancel.py` 全部 10 项，无 skip。
- 未启 3111/3118，未碰 3011/3018。

### 当前状态

- 当前状态：候选 `isolated`。A16 `closed_on_candidate`。
- 未标记 `canary / accepted / production`。

### 阻塞与下一步

- A18 隔离 fixture 服务仍开。`attach_deviation_columns` 仍未在本地 pipeline 定义。独立复核后再谈写回。

## 5.92 upstream_9a4bdcd_unified_qa_20260909

### 目标与边界

- 在候选关闭 remaining-qa 数据链路缺口（板块偏离列、历史股本、异动基准、环境补算执行），并在独立 venv / sandbox `DATA_DIR` 做统一离线回归。
- 不写正式 `DATA_DIR`，不新增数据源工程，不是软件升级当数据集投产。

### GitHub 情报引用与固定上游点

- 固定上游 `9a4bdcd07dfe999f123a8226608d4c90213fae5b`。
- 主记录回 `/Users/simon/Trading/用户台GitHub项目借鉴记录.md` 2026-09-09 子记录。
- 报告：`/Users/simon/Trading/docs/upstream-integrations/2026-09-08-latest-local-first/unified-qa.md`。

### 真实生产者与本地实现

- 无新生产者。`load_benchmark_momentum` 读本地 `kline_index_daily`；`get_historical_shares` 走本地 `load_share_history`。
- fixture `DATA_DIR` 是 sandbox `runtime/data`，与单元测试 `data-unified-qa` 分开，也不是正式库。

### 自动检查与运行面

- remaining-qa 目标集 64 passed。
- 候选全量首跑 352 failed / 1544 passed 保留（908-only）。
- 本地可收集绿集 1107 passed（`--ignore` 132 文件，原因表 `reports/unified-qa-exclusions.json`）。
- 未把失败改成 skip/弱断言。未标 `canary / accepted / production`。

### 当前状态

- 当前状态：候选 `isolated`。
- 未标记 `canary / accepted / production`。

### 阻塞与下一步

- Codex 浏览器与独立复核仍开。正式写回另授权。`e827c380` 仍是 FAILED `artifact_dir_too_large`。

## 5.93 upstream_9a4bdcd_regression_fix_20260909

### 目标与边界

- 只在候选关闭基线对照确认的 R1–R6 升级回归，并用隔离 fixture `runtime/data` 供页面读取。
- 不写正式 `DATA_DIR`，不新增数据源工程。不是 `canary / accepted / production`。
- 上一执行任务 `172ec9c4` 实际写出了这些修复，但桥接 `structured_final=false`；本条按当时候选真实状态补记，不伪报该任务正常 finish。

### GitHub 情报引用与固定上游点

- 固定上游 `9a4bdcd07dfe999f123a8226608d4c90213fae5b`。
- 报告：`/Users/simon/Trading/docs/upstream-integrations/2026-09-08-latest-local-first/regression-fixes.md`。

### 真实生产者与本地实现

- 无新生产者。fixture 当时用真实 `DataStore` / pipeline 写 sandbox `runtime/data`；enriched 仍混有上轮 Aug20/周末样本，不得当干净日历。

### 自动检查与运行面

- 完整 original 358f/1002p/78e exit 1；完整 shadow candidate 331f/1575p/64e exit 1。17 identical OG/NR 为 still_green。
- 未标 `canary / accepted / production`。

### 当前状态

- 当前状态：候选 `isolated`。R1–R6 `closed_on_candidate`（R6=ledger）。
- 未标记 `canary / accepted / production`。

### 阻塞与下一步

- 干净 `data-v18` 与 preferences HTTP 见 `5.94`。正式写回另授权。

## 5.94 upstream_9a4bdcd_data_v18_preferences_http_20260909

### 目标与边界

- 重种干净自洽的小型 daily/enriched/index 样本到 sandbox `runtime/data-v18`，并让 `GET /api/settings/preferences` 在真实路由上不再 500。
- 不写正式 `DATA_DIR`，不删生产数据。旧 fixture 进废纸篓。不是 `canary / accepted / production`。

### GitHub 情报引用与固定上游点

- 固定上游 `9a4bdcd07dfe999f123a8226608d4c90213fae5b`。
- 主记录回用户台 2026-09-09 preferences HTTP 子记录。
- 报告：`reports/preferences-http-fix.md`。

### 真实生产者与本地实现

- 无新生产者。真实 `KlineRepository.append_daily` + `append_index_daily` + `pipeline.run_pipeline`。
- 本地工作日日历 2026-08-24..2026-09-08，12 个交易日；2 股 + 4 指数；分区与 `600000.SH` 12 根一致。`pipeline_written=24`。

### 自动检查与运行面

- HTTP 日线 12 行、10.2→11.08。admin/canduser GET preferences 200。
- 完整 live candidate 322f/1591p/64e exit 1（Polars 1.44.1，pycache-v18）。
- 未标 `canary / accepted / production`。

### 当前状态

- 当前状态：候选 `isolated`。
- 未标记 `canary / accepted / production`。

### 阻塞与下一步

- Codex 浏览器需重新登录后再验收。独立复核仍开。正式写回另授权。

## 5.95 upstream_9a4bdcd_watchlist_import_codes_20260909

### 目标与边界

- 让候选 `POST /api/watchlist/import-codes` 解析 `data-v18` 的 `instruments/part.parquet`，去重匹配后不写自选、不写正式库。
- 无新生产者。OCR 未装。不是 `canary / accepted / production`。

### GitHub 情报引用与固定上游点

- 固定上游 `9a4bdcd07dfe999f123a8226608d4c90213fae5b`。
- 主记录回用户台 2026-09-09 自选粘贴解析子记录。
- 报告：`reports/watchlist-import-codes.md`。

### 真实生产者与本地实现

- lookup 现可读 hive `instruments/*.parquet`。粘贴 `600000`/`000001` 匹配浦发银行/平安银行。
- 解析不调用 `add_batch`。CSV 5MB 上限保留。

### 自动检查与运行面

- 相关 pytest 44 passed。活 HTTP canduser parse 200、matched 2、自选仍 0；admin 仍 2。
- OCR 因 fixture 无 PIL 不可收集，不称通过。

### 当前状态

- 当前状态：候选 `isolated`。
- 未标记 `canary / accepted / production`。

### 阻塞与下一步

- 交 Codex 在仍打开的导入对话框再点解析。不要正式回写，不要独立 review。

## 5.96 upstream_9a4bdcd_review_f2_minute_fallback_20260909

### 目标与边界

- 修独立 review F2：自定义分钟源解析成功后 `get_minute` 失败时，HTTP 缺 capset / 无资格不得隐式回退 TickFlow。
- 自定义成功可继续。内部 `capset=None` 仍兼容，但不能让真实 HTTP 借 None 绕过。不连真实外部端点。
- 无新生产者。不是 `canary / accepted / production`。

### GitHub 情报引用与固定上游点

- 固定上游 `9a4bdcd07dfe999f123a8226608d4c90213fae5b`。
- 主记录回用户台 2026-09-09 F1/F2 子记录。
- 报告：`reports/review-fixes.md`。

### 真实生产者与本地实现

- 门控只在 `sync_minute_batch` 即将 `get_client()` 前。HTTP `_pull` / extend-history / `sync_and_persist_minute` 传入 capset。
- 本地分钟缓存读取与已具 `KLINE_MINUTE_BATCH` 的 fallback 保留。

### 自动检查与运行面

- 相关 pytest 134 passed（含 historical minute atomic、kline transport、ETF 拆分）。
- fixture backend 94240 skip-seed；data-v18 无信号回测 JSON 仍在。未写正式库。

### 当前状态

- 当前状态：候选 `isolated`。
- 未标记 `canary / accepted / production`。

### 阻塞与下一步

- 交全新独立 review。全套 pytest 未重跑。不要正式回写。

## 5.97 upstream_9a4bdcd_official_promotion_f2_20260909

### 目标与边界

- F2 分钟 TickFlow fallback 门控随正式源落地。不新开生产者，不做全量分钟回填，不写正式 `backend/data`。
- 不是 `canary / accepted / production`。

### GitHub 情报引用与固定上游点

- 固定上游 `9a4bdcd07dfe999f123a8226608d4c90213fae5b`。
- 主记录回用户台 2026-09-09 正式晋升子记录。
- 报告：`reports/local-promotion.md`。

### 真实生产者与本地实现

- 门控代码与候选 `6a28` 相同，现位于正式 `backend/app/services/kline_sync.py` 与 `backend/app/api/kline.py`。
- 测试副产物 parquet 已从 promotion 排除并进 Trash。

### 自动检查与运行面

- 正式 venv Polars 1.44.1。相关 134 pytest 在 `baseline-audit/data-promo-official-134` 通过；`REGEN_BACKEND_DATA=no`。
- 正式 backend 3510/3545 使用默认 `/Users/simon/Trading/one-trading/data`。启动时既有 sealed-L1 补跑今天定版，不是新全历史回填。

### 当前状态

- 当前状态：正式 API / F2 逻辑更新 **verified**。最终报告 `reports/final-acceptance.md`。
- Codex after-IAB 未点采集。市场脉搏：09-08 为 117 分钟 + 16 events；隔日要 216–242 分钟；09-07 **总行数 240、分钟 223**。`market_pulse*.py` 与晋升备份同哈希。不是本次质量代码回归。
- **不新宣称任何数据集** `canary / accepted / production`。启动时既有 sealed-L1 今日 77 行 catchup，不报生产 data 完全没变化。

### 阻塞与下一步

- 全套 pytest 未在 `6a28` 重跑。不要为 toast 改产品。
- 运行收尾未改数据集/正式 `DATA_DIR`。3111/3118 仍空。

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
