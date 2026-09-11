# 2026-08-13 数据台维护与恢复会话记录

> 状态：会话级历史记录，`as_of=2026-08-13 04:45 +0800`；时间均为 +0800 当日时刻。
>
> 当前权威入口：数据集与平台状态见 `/Users/simon/Trading/one-trading/docs/data-platform-development-log.md`（条目 5.3 / 5.4 / 4.13 / 4.14 / 4.15）；工作包见 `/Users/simon/Trading/数据台下一步工程工作计划.md`（D-R-01 / D-R-02 / D-R-03）。
>
> 本文件只按时间索引本次会话的改动、授权与证据落位，不替代上述权威条目，也不构成任何数据集的 `accepted / production` 结论。

## 0. 会话概览

单一会话内按用户逐步授权完成六段工作：数据台只读体检 → P0 本地 catalog 恢复与存储治理 → 历史 worktree 清理 → M6 三数据集本地派生恢复（D-R-01）→ PIT 股本与估值市值（D-R-02）→ corporate_actions 外部生产者接入（D-R-03）。所有代码改动停留在主树未提交状态；所有正式数据写入均有写前备份。

## 1. 时间线与改动索引

### 01:20–01:35 数据台只读体检（无改动）

- 通读数据台四份权威文档；探索后端数据台代码（185 个 Python 文件）；只读检查物理 Parquet、`control/catalog.sqlite3`、lineage。
- 主要发现：本地 catalog 8 个数据集 `catalog_quality_failed` 且状态冻结于 2026-07-22（stock_daily 记录 139 万行 vs 物理 806 万行）；约 21G worktree/残留/日志存储垃圾；`backend/app/data_sync` 深模块仅存在于分支；valuation/limit_up/membership 等参考数据集停更于 7 月下旬。
- 无文件改动，无外部访问。

### 01:36–02:00 P0：本地 catalog 恢复与存储治理（授权 01:36）→ 开发日志 `5.3`

- 01:44 写前备份 `data/control/` → `/Users/simon/备份/codex/20260813-014411-one-trading-p0-local-catalog-recovery`。
- 01:45 离线持久化重扫：26 数据集 16 healthy / 7 degraded / 3 unknown / **0 failed**（与线上 Deployment `6a7c57c70d41a78958bb46a2` 分布一致）；`stock_daily` 恢复真实 8,064,651 行。事实澄清：739 条 legacy lineage 已于 08-12 18:59 本地写入，恢复只差这次重扫，未改任何 Parquet/lineage。
- 01:49 存储归档（移入同一备份目录）：`.data.staging-233907…`（275M）、`data.k4-residual-20260722…`（186M）、无轮转 `runtime.jsonl`（184M）。`data/logs` 从 301M 降至 117M。
- ~01:55 代码：`backend/app/services/runtime_logging.py` 为 `runtime.jsonl` 增加 20MB x 5 轮转；`backend/tests/test_runtime_logging.py` 新增轮转回归（3 项通过，Ruff 通过）。

### 02:25–02:35 任务 A：历史 worktree 清理（授权 02:25）→ 开发日志 `5.4`

- 02:27 快照与备份：`git worktree list` 33 条、29 分支清单、6.1G `four-atom-closeout/output` → `/Users/simon/备份/codex/20260813-022700-one-trading-worktrees-cleanup`。
- 02:29–02:35 删除 `.worktrees` 全部 27 个工作副本 + `git worktree prune` 清 `/tmp` 5 条失效记录（首次沙箱内 `.venv` 受保护残留，批准后沙箱外完成）。
- 核验：29 个分支全部保留，`codex/data-platform-convergence-v1` 仍指向 `7019d03`；项目目录约 21G → 约 1.9G。

### 02:35–03:50 任务 B / D-R-01：M6 三数据集本地派生恢复（授权 02:25）→ 开发日志 `4.13`

- 02:35–02:52 调研 `7019d03` 的 M6 代码与主树差异、schema/物理数据核对；确认真实覆盖边界为 07-31（全市场 5,197..5,528/日）与 08-03 起（管道范围 507..509/日），修正了授权信息中假定的 07-24 边界。
- 02:39 移植 `backend/app/price_limits.py`、`backend/app/services/financial_pit.py`（含 4 个测试文件，按主树边界裁剪）。
- ~02:45–03:00 新写 `backend/app/services/reference_derived.py`（三处披露过的修正：sealed_l1 只取同日、membership 快照差分、lineage 覆盖披露）；`DATASET_DEFINITIONS` 注册 3 个数据集（26→29）；`scripts/rebuild-reference-derived.py` 显式入口；`backend/tests/test_reference_derived.py` 等 24 项测试通过。
- 02:53 写前备份 → `/Users/simon/备份/codex/20260813-025300-one-trading-m6-reference-recovery`。
- 02:54 pools 一次显式同步（用户单独授权）：CSI300/CSI500/SSE50 共 850 只，`as_of=2026-08-12`，全部成功。
- 03:43 正式回填 `refderived-20260812194343`（窗口 07-22..08-12）：valuation 16 分区、limit_up 16 分区、membership 差分合并（成分零变动，850 行保留原区间）。
- 03:46 补充运行 `refderived-20260812194648`：重建 07-21 两个 v1 老 schema 分区（首轮目录重扫如实失败暴露）；03:45/03:47 pools 与三数据集重扫全部 `succeeded`。期间修复重建脚本"读 dataset_state 旧值误报 healthy"缺陷，改为按真实 `sync_run` 判定。
- 03:47 终态：valuation_daily 17 分区 53,036 行、limit_up_events 17 分区 1,654 行、membership 850 行，全部 healthy；后端全量 431 passed / 2 skipped（02:52 起后台运行）。
- ~03:48 文档：工程计划登记 `D-R-01`；开发日志 `4.13`。

### 03:51–04:20 D-R-02：PIT 股本与估值市值（授权 03:51）→ 开发日志 `4.14`

- 03:52–03:58 调研与真实生产者 live 核查：东财 `RPT_F10_EH_EQUITY`（股本结构，`NOTICE_DATE` 真实公告日）与 `RPT_SHAREBONUS_DET`（分红送转批量报表）两个端点均于 03:58 前后探测通过。
- ~03:55–04:00 代码：`backend/app/services/free_sources/share_capital_public.py`、`scripts/sync-share-capital.py`、`backend/tests/free_sources/test_share_capital_public.py`（3 项通过）。
- 04:00 写前备份（shares / corporate_actions / adj_factor）→ `/Users/simon/备份/codex/20260813-040000-one-trading-pit-shares-and-corporate-actions`。
- 04:03–04:11 正式同步：CSI500+自选并集 509/509 只成功、0 失败，19,282 条股本历史；`financials/shares` 20,133 → 32,215 行（严格 PIT 可用 19,282 行 / 509 只）。
- 04:19 估值重建（17 分区）：范围分区（08-03..08-12）市值覆盖 100%；全市场分区（07-21..07-31）如实覆盖 509 只（约 9.2%）。抽查 `600756.SH` 市值 = close x total_share 逐位一致。
- 04:37 `financial_shares` 目录补重扫：`succeeded / healthy / 32,215 行`（此前 degraded/20,133）。

### 04:20–04:40 D-R-03：corporate_actions 外部生产者接入（授权 03:51）→ 开发日志 `4.15`

- ~03:57–04:07 代码：`backend/app/services/corporate_actions_sync.py`（自 `7019d03` 移植适配：批量报表替代逐股 F10、egress 机制由显式入口替代）；`data_lab/schemas_reference.py` 移植 corporate_actions schema（v2）；`DATASET_DEFINITIONS` 注册（29→30）；`scripts/sync-corporate-actions.py`；`backend/tests/test_corporate_actions_sync.py` 9 项通过。
- 04:08 后端全量 443 passed / 2 skipped（后台；含当日全部 12 项新增回归，早于下述两处修正）。
- ~04:26 首次 apply 被 publish 质量门如实拦截（`overlap_conflicts: plan_status=4449`、kept_prior）——失败保旧路径获得一次真实验证；04:28 修正批量解析显式 schema，04:33 修正 prior 行 append-only 合并（只给新增行盖 crosscheck 章），相关套件 9 项复跑通过。
- 04:31–04:36 二跑发布成功：112,606 行 / 5,529 只（正式事实 55,745：现金分红 44,450、混合 8,899、送转 2,364、unknown 32；`ex_date` 1991-02-26..2026-08-21；既有 56,861 条 adj 派生信号原样保留）；5,488 行 `quarantined`（本地复权因子仅覆盖至 7 月下旬，较新事件暂无法双向核对）。corporate_actions 目录重扫 `succeeded / healthy`。
- ~04:45 文档：工程计划登记 `D-R-02/03`；开发日志 `4.14/4.15`；备份 README 补执行结果。

## 2. 代码改动总清单（截至 04:45，全部未提交）

新增文件（14）：

- `backend/app/price_limits.py`、`backend/app/services/financial_pit.py`（7019d03 移植）
- `backend/app/services/reference_derived.py`、`scripts/rebuild-reference-derived.py`
- `backend/app/services/free_sources/share_capital_public.py`、`scripts/sync-share-capital.py`
- `backend/app/services/corporate_actions_sync.py`、`scripts/sync-corporate-actions.py`
- 测试：`backend/tests/test_reference_derived.py`、`test_price_limits.py`、`test_financial_pit_e6.py`、`test_financial_pit_v2.py`、`tests/free_sources/test_share_capital_public.py`、`tests/test_corporate_actions_sync.py`

修改文件（6）：

- `backend/app/services/runtime_logging.py`（runtime.jsonl 20MB x 5 轮转）
- `backend/tests/test_runtime_logging.py`（+轮转回归）
- `backend/app/data_catalog/definitions.py`（+4 个数据集定义，目录 26→30）
- `backend/app/data_lab/schemas_reference.py`（+corporate_actions schema）
- `backend/tests/data_catalog/test_models.py`（必备数据集清单 +4）
- `backend/tests/data_catalog/test_api.py`（未注册目录示例由 corporate_actions 换为 governance_events）

测试终态：后端全量 443 passed / 2 skipped（04:08；会话前基线 406，当日净增 37 项 = 轮转 1 + 三数据集/移植 24 + 股本 3 + 公司行动 9）；其后两处 corporate_actions 修正经 9 项目标套件复跑通过（04:33）；全部目标文件 Ruff 通过。

## 3. 正式数据与控制面改动

- `control/catalog.sqlite3`：01:45 全量重扫（0 failed）；其后按数据集多次目标重扫；目录数据集数 26 → 30。
- 归档移出：staging 残留 275M、K4 残留 186M、runtime.jsonl 184M；删除 `.worktrees` 约 20G（6.1G 产物归档）。
- `data/pools/`：3 个成分池刷新至 `as_of=2026-08-12`（一次显式同步）。
- `data/reference/valuation_daily|limit_up_events`：各 17 个分区重建/回填（07-21..08-12，两轮：03:43 无市值、04:19 含市值）。
- `data/reference/index_membership_history/members.parquet`：快照差分合并（850 行，零成分变动）。
- `data/financials/shares/part.parquet`：20,133 → 32,215 行（04:11，PIT 升级）。
- `data/reference/corporate_actions/actions.parquet`：56,861 → 112,606 行（04:36，正式事实接入）。
- `data/adj_factor/verification.parquet`：重写为当前逐股验证标记（4,971 verified_events / 116 verified_no_event / 456 unverified / 1 source_failed）。
- 新增 lineage：valuation/limit_up/membership（两轮 run）、financial_shares、corporate_actions；未修改任何既有 lineage。

## 4. 备份目录（4 个，均含 README 与回滚说明）

| 时间 | 目录 | 覆盖内容 |
| --- | --- | --- |
| 01:44 | `/Users/simon/备份/codex/20260813-014411-one-trading-p0-local-catalog-recovery` | control/ 全目录；归档 staging/K4 残留与 runtime.jsonl |
| 02:27 | `/Users/simon/备份/codex/20260813-022700-one-trading-worktrees-cleanup` | worktree/分支快照；6.1G four-atom output |
| 02:53 | `/Users/simon/备份/codex/20260813-025300-one-trading-m6-reference-recovery` | 三个派生数据集原目录 + pools |
| 04:00 | `/Users/simon/备份/codex/20260813-040000-one-trading-pit-shares-and-corporate-actions` | financials/shares、corporate_actions、adj_factor |

## 5. 文档改动

- 开发日志：新增 `5.3`（01:36–02:00 段）、`4.13`（03:48 前后）、`4.14`/`4.15`（04:45 前后）、`5.4`（本记录同步补登，04:50 前后）。
- 工程计划：登记 `D-R-01/02/03` 三个旁路工作包（均 `active`，不占固定串行顺序）。
- 数据能力目录：分红送转配股、历史日频估值两行补本地实现指针（04:50 前后）。
- 本会话记录：`docs/investigations/2026-08-13-data-platform-maintenance-and-recovery-session.md`（本文件）。

## 6. 当前状态与待用户决策（as_of 04:45）

- 生命周期：valuation_daily / limit_up_events / index_membership_history / financial_shares（PIT 升级）/ corporate_actions 均为 `canary / 待用户验收`；catalog healthy 不等于 accepted。
- 待决策（均不自动开工）：股本扩容到全市场 5,539 只（约 5.5k 请求）；复权因子覆盖扩容（复核降级 5,488 行 quarantine）；`data-platform-convergence-v1` 分支的集成或 superseded 决策；主树 263+ 项未提交改动（含本会话 20 个文件）的收敛提交。
