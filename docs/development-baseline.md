# one-trading 开发基线

`/Users/simon/Trading/one-trading/docs/development-baseline.md` 是 `/Users/simon/Trading/one-trading` 的**唯一开发基线导航**。它说明代码锚点、恢复证据、数据与代码为何不同步回滚、基线含/不含什么，以及恢复后三项新授权增量该读哪条现行日志。它**不是**平行开发状态总账，也不替代三台十二份权威文件或三份开发日志里的条目事实。本导航只约束 one-trading 开发与记忆，不影响参考项目自己的基线。

权威顺序：当前用户指令 > `/Users/simon/Trading/AGENTS.md` > 本文 + 对应台计划/日志 > 带日期的历史会话或记忆摘要。

## 1. 锚点

| 项 | 固定值 |
| --- | --- |
| 代码基线 | `2026-09-10T00:19:35+08:00` 数据合集 / 数据源融合完成版 |
| 不是 | `2026-09-09 05:12` 晋升前旧树；也不是基线后的目录瘦身、9/11 后写功能 |
| 恢复写回时点 | `2026-09-12T00:55:46+08:00`（三份开发日志 `restore_whole_20260910_0019`） |
| 恢复实际完成 | 约 `2026-09-12T01:10`；restore-report `as_of=2026-09-12T01:10:57+08:00`，`restored=true` |
| 只读历史证据 | `/Users/simon/Trading/docs/audits/restore-whole-20260910-0019/restore-report.md` |
| 只读 manifest | `/Users/simon/Trading/docs/audits/restore-whole-20260910-0019/source-manifest.json` |
| 写前备份 | `/Users/simon/备份/codex/restore-whole-20260910-0019-before-20260912T005125` |

原 `restore-report.md` / `source-manifest.json` 是只读历史证据，不得改写。不得为了回到该次基线哈希，再次覆盖恢复后已获用户授权的新实现。

## 2. 恢复证据（不重算）

恢复任务把正式产品源码拉回 00:19 融合完成树。restore-report 已记录：

- 正式 `DATA_DIR=/Users/simon/Trading/one-trading/data` **未整树覆盖、未回滚**。
- `.env` sha `8855712d771c3fc3396eaf360a594b48f1fbab3332c73abcde87d6d317711d38` 未改。
- identity / catalog 身份未改；sqlite integrity ok。
- 原业务数据、原包、账户、后写 docs 保留。
- 当时验证 wrapper 不是日常 `uvicorn`；未采集、未同步、未外网回填。
- 当时正式树 pytest：90 passed / 4 failed（`quote_interval_min` 固有 4 条）+ `test_quote_name_map_reuse` collect ImportError。这些数字是恢复当时证据，不是当前验收。

中间曾出现 `restore_pre_cursor_20260911`（回到 9/9 05:12 晋升前）。那是**已被 00:19 整树恢复取代**的历史操作范围，不是当前入口。

## 3. 数据与代码不同步回滚

代码可以回到 00:19 融合完成版；正式 Parquet / Catalog / 原包 / 账户 **按用户要求不跟着重做一次数据回滚**。因此：

- 磁盘上的行业/概念 H5、资讯缓存、估值原包等，可以新于 00:19 源码锚点。
- 不能把「磁盘已有 9/10 窗」写成「00:19 基线已经验收了基线后的目录瘦身或 9/11 功能」。
- 也不能把「恢复后源码暂时缺少某脚本」写成永远缺失；要以开工时读到的现行日志和当前树为准。

## 4. 基线功能范围

### 4.1 属于 00:19 基线（保留，不撤销）

- `data_entry_unification_20260909`：侧栏「数据」唯一入口、能力卡 + 来源卡、设置数据源跳 `/data?section=sources`。这是融合完成版的核心，不撤销。
- 资讯 9/9 基础页：`/news` 市场快讯 + 政策信息；数据台 `4.19` / `4.20` 的 9/9 缓存闭环。生命周期仍以各条目为准，不是 accepted/production。页面与缓存保留；未来工作包 `U-R-01` / `D-R-06` 为 `parked`，等待新授权。
- 9/9 离线两融只读 API（`4.21`）与总览外部只读元数据（`4.22` 的 9/9 接口）。现有 API 保留供 UI 复用；前端目录入口新授权不授权后端新开发。这不等于 9/11 目录折叠入口。
- 行业 H5 日线续更函数、概念 90% 满窗加总、行业日历 freshness 语义：恢复盘点时已在 00:19 树中。
- 正式盘当时保留的行业/概念 Parquet 与日历覆盖，是数据事实，不是新功能验收。

### 4.2 基线明确不含（锚后内容）

| 主题 | 分类 | 现行读法 |
| --- | --- | --- |
| 基线后的紧凑目录 / 总览瘦身 | 基线不含；仅历史未重新授权 | 历史条目与测试数字保留。新授权明确**不恢复瘦身**。 |
| 9/11 总览范围 `overview_scope_fix_20260911` | 基线不含；仅历史未重新授权 | 12 passed / 30 passed 等原数字保留，不降级篡改，也不当作当前已重做。 |
| 9/11 资讯 metadata / P2 | 基线不含；仅历史未重新授权 | 57/62 passed 等原数字保留。9/9 基础页仍属基线。 |
| 9/11 目录外包两融入口 | 基线不含；**恢复后新授权重做** | 见工作台 `data_catalog_offline_margin_restore_20260912`。旧 9/11 条是历史 verified，不代表当前树。 |
| 9/11 估值只读 CLI | 基线不含；**恢复后新授权重做** | 见 `/Users/simon/Trading/one-trading/docs/data-platform-development-log.md` 小节 4.23 `offline-valuation-readonly-contract`（QuantDB 估值历史原包只读查询契约）的 2026-09-12 恢复段。开工时脚本已在当前树；「缺失」只是该任务开始时的历史句，不是现在判断。 |
| 9/10 概念 H5 续更代码 / `run_now` 接线 | 基线不含；**恢复后新授权重做** | 见数据台 `fund_flow_window_chain_restore_20260912（源码续接恢复，不是数据集验收）`。 |
| 9/10 行业 126 用户台开门门槛 | 基线不含；**恢复后新授权重做** | 见工作台 `fund_flow_window_chain_restore_20260912`。加总算法在 00:19 树已有；kind-specific 126/63 门槛按新条。 |
| 9/10 15:30 正式批写 / 后台续更 | 基线后历史；**现在未重新授权后台或正式批写** | 旧 `D-R-05` / `D-R-07` 历史 active ≠ 当前可跑调度或联网补数。9/12 新授权 `active` 只限源码/只读。 |

## 5. 恢复后三项新授权增量

用户仅明确保留以下三项。历史会话不是当前执行许可。本对齐不代替推进或重新开工它们；各任务按自身现行授权推进。以下状态以**本对齐任务开工时读到的现行日志**为准，不伪报验收。

### 5.1 核对市场看板数据 (2)

- 任务 ID：`01a09187-8f63-7193-9645-b38acbf9803a`
- 范围：资金流概念续接、日历覆盖核验、行业 126 窗；**禁止后台 / 联网补数**。
- 数据台锚点：`/Users/simon/Trading/one-trading/docs/data-platform-development-log.md` 小节 `fund_flow_window_chain_restore_20260912（源码续接恢复，不是数据集验收）`
- 用户台锚点：`/Users/simon/Trading/one-trading/docs/workbench-development-log.md` 小节 `fund_flow_window_chain_restore_20260912`
- 开工时状态：数据台「源码续接 + 自动检查 + 只读加总」，不是 canary 真实续更，不是 accepted/production。用户台 `implemented`（可见门槛 + 15 passed），不是 verified/accepted/production。IAB 待 chief。

### 5.2 数据台简化 (2)

- 任务 ID：`01a09186-b2af-73c0-aa8b-9037194f80f6`
- 范围：只在 `/data?section=catalog` 卡片网格外增加默认折叠的外包两融入口；**不恢复瘦身**。
- 用户台锚点：`/Users/simon/Trading/one-trading/docs/workbench-development-log.md` 小节 `data_catalog_offline_margin_restore_20260912`
- 数据台：本轮未改后端；现有 API 仍见 `4.21`（canary）与 `4.22`，供 UI 复用。前端新授权不授权后端新开发；`D-OFFLINE-MARGIN-API` 未来工作包 `parked`。
- 开工时状态：`implemented` 恢复候选。vitest 4 files / 52 passed，随后 `tsc -b && vite build` exit 0。隔离 3211/3218 已建，**待 GPT-6 IAB**。不是 verified/accepted/production。

### 5.3 30g数据 (2)

- 任务 ID：`01a09186-52ee-7311-962b-b642b18be905`
- 范围：只读估值 CLI + 4 样本；**不接 API/UI**，不扫 80G。
- 数据台锚点：`/Users/simon/Trading/one-trading/docs/data-platform-development-log.md` 小节 4.23 `offline-valuation-readonly-contract`（QuantDB 估值历史原包只读查询契约）（2026-09-12 恢复/核验段）
- 证据目录：`/Users/simon/Trading/one-trading/docs/investigations/2026-09-12-offline-valuation-readonly-restore/`
- 开工时状态：`isolated`。18 passed；四样本有界查询 ok；单位仍 `unknown/unverified`。不是 accepted/production，也未开始 Provider/API/Catalog/UI。

## 6. 分段：恢复前历史 vs 恢复后新增

### 6.1 恢复前（可追溯，但不是当前入口）

- 9/9 05:12 晋升及之后、直到 9/11 22:48 的 Cursor 上游升级与后写功能：曾被 `restore_pre_cursor_20260911` 从运行代码撤回。该条现为 **superseded 历史范围**。
- 00:19 之后的目录瘦身、总览瘦身、9/11 总览范围、资讯 metadata/P2、目录外包、估值 CLI、概念续更：历史条目保留原测试数字、日期和备份路径，**不篡改为从未发生**。
- 旧 Codex/Cursor 会话、ComputerHistory / Skysight / Chronicle、AGD / nativeMemory 里的「已完成 / 当前 PID / 队列状态」只作带日期证据。

### 6.2 恢复后（当前工程）

1. `restore_whole_20260910_0019`：正式树回到 00:19 融合完成版。
2. 上述三项用户新授权增量：各任务按自身现行授权推进各自精确范围。本对齐不代替推进或重新开工。
3. 本对齐：统一文档/记忆入口，不回滚源码，不覆盖这三项增量。

## 7. 以后任务怎么读

1. 先读本文，再读对应台下一步工程计划与开发日志的**现行条目**。
2. 计划 `active` 必须同时满足用户已单独授权且对应开发日志已有精确条目。旧 `D-R-07` 历史 active 不能自动意味着现在获准后台或正式批写。仅依据旧授权的未来工作包为 `parked`。
3. 发现「文件缺失 / 已完成 / 当前 PID」时，以现行日志和当前树为准；不可复用恢复前或排队快照的判断。
4. 禁止为对齐基线哈希覆盖新授权实现。各任务按自身现行授权推进，不授权其他任务代替推进。
