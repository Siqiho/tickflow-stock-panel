# one-trading 用户台开发日志

最近维护：2026-09-12（当前入口改为 2026-09-10T00:19:35+08:00 融合完成基线导航，见 `/Users/simon/Trading/one-trading/docs/development-baseline.md`。`restore_pre_cursor_20260911` 的「回退 9/9 05:12 之前」已是 superseded 历史范围。保留 9/12 新授权增量，不伪报验收。）

最近追加：2026-09-12 文档/记忆对齐。现行新授权条目仍是 `data_catalog_offline_margin_restore_20260912` 与 `fund_flow_window_chain_restore_20260912`；旧 9/11 历史正文不改数字。

适用项目：`/Users/simon/Trading/one-trading`

职责：只记录用户直接看到的页面、交互、图表、设置入口和产品工作流在 one-trading 中的本地设计、实现、验证、验收与运行状态。

## 0. 权威边界

- GitHub 上游项目与采用判断：`/Users/simon/Trading/用户台GitHub项目借鉴记录.md`。
- 产品/界面能力反查：`/Users/simon/Trading/用户台产品与界面能力目录.md`。
- 未来工程优先级与开工门：`/Users/simon/Trading/用户台下一步工程工作计划.md`。
- 数据台本地实现：`/Users/simon/Trading/one-trading/docs/data-platform-development-log.md`。
- Agent 台本地实现：`/Users/simon/Trading/one-trading/docs/agent-platform-development-log.md`。
- 本文件不复制上游完整源码调查，也不把数据集或 Agent 工具状态写成用户台完成状态。
- 开发基线导航：`/Users/simon/Trading/one-trading/docs/development-baseline.md`。旧会话/PID/「已完成」不能覆盖现行条目。

## 1. 本地状态词

- `planned`：目标和用户价值已定义，尚未形成设计。
- `designed`：界面、交互、依赖接口和验收路径已明确。
- `implemented`：代码已实现，但尚未完成目标运行面验证。
- `verified`：自动检查和真正的 one-trading 浏览器运行面主路径已验证。
- `accepted`：用户确认产品行为和使用价值。
- `production`：accepted 功能已在正式目标运行面启用并复核。
- `blocked / no-go / superseded`：阻塞、明确不采用或被后续实现取代。

GitHub 项目的“采用/产品参考”不能替代上述本地状态。

## 2. 初始化边界

- one-trading/Tick4Panel 是当前用户台主项目，默认代码位置为 `frontend/` 以及仅为界面服务的轻量 Adapter。
- 2026-08-01 本次工作只建立三台文档职责，没有修改用户台代码、启动网页、运行构建或进行浏览器验证。
- 因此本轮不为任何既有页面补写 `verified / accepted / production`；历史实现需要在后续具体任务中按真实代码和运行面逐项回填。

## 3. 当前能力清单（非验收状态）

L3 当前入口（2026-09-12）：固定代码基线是 `2026-09-10T00:19:35+08:00` 数据合集/融合完成版。`data_entry_unification_20260909` 与资讯 9/9 基础页属于基线。9/10 瘦身、9/11 总览范围与资讯 metadata/P2 是基线不含且仅历史未重新授权。恢复后新授权重做：目录外包两融见 `data_catalog_offline_margin_restore_20260912`；资金流概念/日历/行业 126 见 `fund_flow_window_chain_restore_20260912`。

| 能力 | 上游情报 | 本地位置 | 本轮结论 |
| --- | --- | --- | --- |
| Tick4Panel 产品壳和主要页面 | tickflow-stock-panel | `frontend/` | 已有代码基座；本轮未重新验证 |
| 策略与回测用户流 | tickflow-stock-panel、portwine 仅作 Agent 机制参考 | `frontend/src/pages/backtest` 等 | 已有本地页面；本轮未重新验证 |
| AI 设置入口 | go-stock、tickflow-stock-panel | `frontend/src/pages/settings/AI.tsx` 等 | 入口雏形；Agent 能力另记 |
| AI 功能目录 | tickflow-stock-panel + one-trading 本地代码盘点 | `/ai`、`frontend/src/pages/AIHub.tsx` | 四项真实 AI 能力已聚合；本轮只验证目录和跳转，不重新验收模型输出 |
| 数据目录页面 | one-trading 自有实现 | `frontend/src/pages/Data.tsx` 等 | 当前运行代码是 9/10 00:19 数据合集布局 + 本轮 `data_catalog_offline_margin_restore_20260912` 目录外包入口候选。9/10 紧凑目录 / 总览瘦身与 9/11 `data_catalog_offline_margin_20260911` 仍是历史记录，不代表当前树。本轮不是 `accepted` / `production`。 |
| 市场脉搏 | go-stock 产品形态与财联社端点情报；运行时为 one-trading 自有实现 | 看板 `#market-pulse`、数据页、概念/行业/复盘深链 | P0/P1/P2 已完成真实桌面与 375px 验证；状态见 `market_pulse_workbench` |
| 管理员数据板块来源追踪 | one-trading 自有实现；数据集事实回到数据台 provenance | 用户台各数据板块图标 + `/data?section=source-trace` | 故障链只追真实生产者；GitHub 只在 Adapter 对照。见 `source_trace_github_as_adapter_reference` |
| 资讯：市场快讯 + 政策信息 | 本地 go-stock `PolicyNewsList.vue` / `newsList.vue` / `market.vue` 为功能权威；主记录仍是用户台 go-stock 条 | `/news`，侧栏「数据」后「资讯」 | 9/9 基础页属于 00:19 基线。9/11 metadata/P2 是基线不含、仅历史未重新授权（原 57/62 passed 与 failed 门保留）。现行读 `news_policy_workbench`，不是 accepted |

## 4. 功能条目

### data_catalog_offline_margin_restore_20260912

新授权任务：`01a09186-b2af-73c0-aa8b-9037194f80f6`（数据台简化 (2)）。只加折叠外包两融入口，不恢复瘦身。

#### 用户目标与可见结果

- 在已恢复的 2026-09-10 00:19:35 数据合集版本上，只于 `/data?section=catalog` 卡片网格之外增加/恢复仅管理员可见、默认折叠的「外部只读原包 · 两融查询」。
- 保留当前合集版整体布局、能力展示、来源分类、融合总览和来源详情。不恢复 9/10 总览瘦身、紧凑目录、目录搜索/筛选或其他布局改造。
- 外部原包不进入 catalog entries、分组计数、容量、托管来源筛选或托管数据集数量。展开才挂载现有 `ExternalReadOnlyData`；收起卸载。普通用户无入口。

#### 与历史 9/11 记录的关系

- `data_catalog_offline_margin_20260911` 是恢复前树上的工程 `verified` 历史条目，连同当时隔离 IAB。该条不回写、不升格，也不代表本轮当前代码。
- 本轮按当前 00:19 合集树重做同一用户可见目标：目录网格外折叠入口 + 查询组件补强（`compact` / `idPrefix` / 管理员才取元数据 / 显式提交 / 失败清旧表 / 同标的重试）。
- 数据台边界仍见 `docs/data-platform-development-log.md` 的 `4.21`（`canary`）与 `4.22`。本轮未改后端。

#### 本地路由、Module、Adapter 与跨台依赖

- 用户台：`Data.tsx` 向 `DataCatalogSection` 传入 `isAdmin`；`DataCatalogSection.tsx` 在卡片网格外渲染折叠入口；复用 `ExternalReadOnlyData.tsx`（`compact` + `idPrefix=catalog-offline-margin`）。
- 只读消费既有 `GET /api/data/external-readonly-sources` 与 `GET /api/f10/margin-trading?source=offline_quantdb&limit=20`。不改 backend / `.env` / 原包 / 设置数据源档位组件。
- `/settings?tab=data-sources` → `/data?section=sources` 既有跳转保留。

#### 自动检查与构建

- 最终 controller：4 个目标 test files 共 **53 passed**（`DataCatalogSection` / `ExternalReadOnlyData` / `Data` / `DataUnifiedSources`）；随后 `frontend` `tsc -b && vite build` exit 0；目标文件 `git diff --check` exit 0。不是全仓 tests。最终候选 `69614d25783067a4e734c13b4b0eca63a0a92bbf0b09d1bd77a4c010d6563ba0`。
- 全新独立复核 task `92133218-f181-49e5-8fe8-acec4d689a19`，session `db5c1d50-2acd-414a-a6cc-e85e46af9f81`，`review_verdict=pass`，候选相同。
- 配置请求为 Grok 4.6 / Extra High，选择器已确认；供应方实际返回 model/effort 未提供，**未核验**，不伪报。
- 普通用户无入口、无元数据请求仅由上述组件/页面权限测试覆盖，未做真实普通账户试用。

#### 隔离运行面

- 本任务拥有。正式 3011 PID 31589 / 3018 PID 31588 全程未占用、未停止、未重启。
- Codex 内置浏览器隔离验收使用本轮代码：前端 `http://127.0.0.1:3211/` 最终重启 PID **61362** 代理后端 `http://127.0.0.1:3218` PID **48175**。旧前端 PID 48192 已被该次重启取代，不是最终验收进程。
- 后端 `http://127.0.0.1:3218` PID **48175** 于 2026-09-12 02:13:28 +08，cwd=`/Users/simon/Trading/one-trading/backend`，无 reload。
- `DATA_DIR=/tmp/one-trading-data-catalog-offline-margin-20260912`（自 `one-trading/data/shared-isolated-runtime-20260911` 复制约 5.3MB，排除 vite-cache；未复制正式数据或 80GB 原包）。
- `ONE_TRADING_DISABLE_BACKGROUND=1`、`NEWS_CACHE_MODE=isolated_preview`、`ONE_TRADING_HERMES_RUNTIME_ENABLED=false`、`ONE_TRADING_HERMES_MULTIUSER_ENABLED=false`。`OFFLINE_QUANTDB_ROOT` 未写入进程环境，只读沿用现有项目 `.env`。
- 日志：后端 `/Users/simon/.local/state/cursor-task-bridge/cursor/data/projects/Users-simon-Trading/terminals/319608.txt`；前端同目录 `319609.txt`。
- 只读探针（验收前实现阶段）：`/health` 3218 与 3211 代理均为 200，`v0.1.68`。`GET /api/data/external-readonly-sources` → `configured`。`GET /api/f10/margin-trading?symbol=300502.SZ&source=offline_quantdb&limit=20` → `source=offline_quantdb` / `as_of=2026-08-26` / `count=20` / `missing_fields` 含 `securities_lending_balance`，该字段真实 null。隔离身份 `configured=false`，本机放行，不是已登录普通用户。
- 隔离 3211/3218 验收后已停止并确认端口空闲；正式 3011/3018 仍在。

#### Codex 内置浏览器目标运行面验证

以下为 **Codex 总工观察，不是 Cursor / 本执行端观察**。隔离 3211/3218、本轮代码；正式 3011/3018 未用。未开系统浏览器。

- 默认折叠时 textbox=0；展开后才加载管理员元数据与查询组件。输入 `300502.SZ` 本身不请求，明确提交后显示 `source=offline_quantdb`、`as_of=2026-08-26`、20 条、缺字段 `securities_lending_balance` 与 `margin_balance`、null 显示「—」。
- 总工发现并要求修复：成功 A 后只编辑草稿 B 曾残留 A。最终修复后编辑 `000000.SZ` 立即隐藏旧来源/日期/表格且未自动请求。
- `000000.SZ` 明确提交返回 404「没有该标的的两融文件」，旧成功结果保持清除；同标的重试访问日志出现两次 GET（03:10:54、03:11:11）。切回 `300502.SZ` 成功。`INVALID` 返回 400「股票代码无效」，旧表不出现。
- 真正 `status=empty` 在现有外包里没有可自然触发的空文件，只有组件测试覆盖；**不是**真实浏览器已测空记录。
- 390×844：`document`/`body` `scrollWidth` 均 390，无横向页溢出；表格可读但表头/单元格会换行，非阻断限制。
- 融合总览仍有能力路由、数据来源、外部只读详情/真实生产者/实际数据集；旧 `/settings?tab=data-sources` 最终到 `/data?section=sources`。console 无应用 error，仅既有 React Router future warning。
- 外包入口始终不计入托管目录分组/数量/容量/托管筛选；标签精确为「外部只读原包·两融查询」。

#### 当前状态与用户验收

- 当前状态：`verified`（仅隔离 3211/3218 本轮代码主路径）。不是 `accepted` / `production`。
- 回滚：用 `/Users/simon/备份/codex/one-trading-data-catalog-offline-margin-20260912-001` 覆盖本轮改过的原文件。不要回滚正式数据、`.env` 或 80GB 原包。隔离 3211/3218 已停且端口空闲；不要 kill 3011/3018。
- 下一步工程计划未更新。按用户要求在本条停止，不继续布局或其他数据源。

### restore_whole_20260910_0019

- 时点：2026-09-12T00:55:46+08:00。用户授权把正式 one-trading 恢复到 2026-09-10 00:19 数据源融合完成、后续瘦身前。不是 9/10 下午瘦身，也不是 9/11 功能。
- 范围：用户台 `frontend/` 产品源（含补写的 `frontend/src/components/data` 7 个漏文件）。正式 3011 PID 31589 为官方 `vite.config.ts`。
- 本条只记恢复时点/范围/报告指针。IAB 由 chief。不是 daily-run，也不是 accepted/production。
- 完整证据：`/Users/simon/Trading/docs/audits/restore-whole-20260910-0019/restore-report.md`；备份 `/Users/simon/备份/codex/restore-whole-20260910-0019-before-20260912T005125`。

### fund_flow_window_chain_restore_20260912

新授权任务：`01a09187-8f63-7193-9645-b38acbf9803a`（核对市场看板数据 (2)）。资金流概念/日历/行业 126；禁后台/联网补数。

#### 用户目标与可见结果

- 已登录资金流面板按 kind 开门：行业最长 126（半年）走窗口 API 并渲染保留数据；概念最长 63。
- 行业 250、概念 126/250、以及本地窗不完整时，显示当日快照 + 明确「窗口数据不足…不能当作{档}完整累计榜」。不假装已有长窗。
- 行业时效行仍在；概念不加时效行。本条只记可见门槛，不把数据台续更写成用户台已验收。

#### GitHub 情报与固定上游点

- 无新 GitHub 审阅。126 加总见数据台 `industry_window_126_sum_20260910` / 本轮只读 `parquet-vs-service.json`。

#### 本地路由、Module、Adapter 与跨台依赖

- `frontend/src/components/SectorFundFlowPanel.tsx`：`BOARD_WINDOW_MAX_DAYS = { board: 126, concept: 63 }`。`wantsWindow = selectedWindow.days <= BOARD_WINDOW_MAX_DAYS[kind]`。
- 只读 `GET /api/free/fund-flow/{boards|concepts}/window`。不改 API schema。

#### 自动检查与构建

- `SectorFundFlowPanel.history.test.tsx` + `industry-freshness.test.tsx`：**15 passed**。本执行端未跑 tsc/vite，未开 Codex 内置浏览器。
- 数据台只读加总与概念 roll 测试见对应条目，不复制为用户台已实现闭环。

#### Codex 最终只读验收 / IAB

以下为 **Codex 总工观察，不是 Cursor / 本执行端观察**。归档见 `docs/investigations/2026-09-12-fund-flow-window-chain-restore/chief-acceptance.md` 与 `evidence/chief-iab.json`。

- 目标页 `http://127.0.0.1:3011/`，title `one-trading · Quant Terminal`，当前热加载源。
- 行业 126：UI 显示「近126个交易日累计」，`2026-03-12`..`2026-09-10`，coverage 128/128，full 128/128，「数据截止 2026-09-10 · 已陈旧 · 窗口完整」，农业综合Ⅱ -2.36亿、半导体 -5683.45亿。
- 概念 63：`2026-06-15`..`2026-09-10`，coverage 504/504，full 490/504，CAR-T细胞疗法 33.08亿、融资融券 -1.84万亿。
- 行业 250/年：9/2 当日快照 + 明确「窗口数据不足，当前仍显示当日快照，不能当作 1 年 完整累计榜」。
- 概念 126/半年与 250/年：各为当日快照 + 对应明确窗口不足文案。
- 最终停在概念 63 + 行业 126，该 tab 标为可交付。Console 无 error；仅一条无关 React Router v7 future-flag warning。
- 本条 `verified` 范围仅上述可见行业 126 / 概念 63 与窗口不足回退。不把数据台概念续更写成用户台已验收。

#### 当前状态与用户验收

- 当前状态：`verified`（仅可见行业 126 / 概念 63 与窗口不足回退）。不是 `accepted` / `production`。
- scheduler 启用/开火未验证；真实续更未验证；9/10 15:30 页结果未复验。未联网、未回填、未写正式数据。
- 收尾写前备份：`/Users/simon/备份/codex/20260912-025119-fund-flow-window-chain-restore-closeout-before`

### restore_pre_cursor_20260911

**superseded 历史范围**：本条记录 2026-09-11 撤回到 9/9 05:12 晋升前。该操作已被 `restore_whole_20260910_0019` 取代。当前入口是 00:19 融合完成基线 + 其后新授权增量。本条 IAB/测试数字不改，也不再表示当前运行代码。

#### 用户目标与可见结果

- 用户授权把正式 one-trading 恢复到 2026-09-09 05:12 晋升前旧版，撤销本轮 Cursor 上游升级及之后的代码修改。不是恢复 9/9 日末。
- 用户台：`frontend/` 已回到 A+B 旧源（B 补齐 A 漏掉的 40 个 `frontend/src/components/data/**`）。9/9 之后新增页面/组件已移入废纸篓，不是就地改旧版。
- 本条只记用户可见旧版看板/数据目录主路径。数据集身份与 wrapper 暂停见数据台同名条；AI/Hermes 进程关闭见 Agent 台同名条。

#### GitHub 情报与固定上游点

- 无新 GitHub 审阅。完整证据只引用 `/Users/simon/Trading/one-trading/docs/cursor-handoffs/restore-pre-cursor-20260911/restore-report.md`，不在本条复制 phase1 全树。

#### 本地路由、Module、Adapter 与跨台依赖

- 正式 3011 PID 5690 是官方 `frontend/vite.config.ts`，不是 isolated sandbox 页。
- 3018 PID 5762 是验证 wrapper，不是日常 `uvicorn app.main:app`。用户台不把该进程写成全功能日常恢复。
- 后续新版实现已从当前运行代码撤回；本日志历史条目保留。

#### 自动检查与构建

- 静态前端（既有日志，本收尾未重跑）：`frontend-tsc.log` `tsc -b` EXIT 0；`frontend-vite-build.log` `vite build` EXIT 0。
- 隔离旧测试（既有日志，本收尾未重跑）：`backend-isolated-tests.log` **46 passed, 12 errors**，12 个全是旧树 `test_preferences_cache.py` 调用不存在的 `preferences._invalidate_cache`。`PYTEST_EXIT:1`，不是测试 workflow 成功。未修补。
- 代码/依赖还原与 SOURCE 1533/1533 见 restore-report，不在本条重算。

#### Codex 内置浏览器目标运行面验证

- 以下为 **Codex 主审观察，不是本执行端观察**。本收尾未再开浏览器、未点同步/更新、未调用 AI。
- IAB tab1 `http://127.0.0.1:3011/` 旧版看板 `v0.1.68`：9/9 本地 5468 股、241 分钟市场脉搏，行业资金流 128/128；现有后续 9/10 数据保留。
- `/data` → 数据目录 → 查看 Stock daily bars 详情点击成功；旧版卡片目录显示 8,214,828 日线 / 5572 标的；详情正确打开。
- 浏览器 error logs `[]`。

#### 当前状态与用户验收

- 当前状态：旧版用户台主路径已被 Codex IAB 观察。不是正式状态词 `verified`（3018 为验证 wrapper、自动同步/AI 仍暂停、12 个旧测试 error 未修）。不是 `accepted` / `production`。不是全功能日常恢复。
- 独立 review 另任务 `aca6` 运行中；本条不声称独立 review 通过。

#### 阻塞、回滚和下一步

- 3018 verification wrapper 后台暂停；自动同步/AI 仍暂停。
- 回滚用写前备份 `/Users/simon/备份/codex/20260911-restore-pre-cursor-before-20260911T224838`；废纸篓 `/Users/simon/.Trash/one-trading-restore-pre-cursor-20260911-20260911T224838`。本收尾编辑前文档副本：`.../docs-closeout-before-edit-20260911T230722`。
- 完整证据：`/Users/simon/Trading/one-trading/docs/cursor-handoffs/restore-pre-cursor-20260911/restore-report.md`。


#### 收尾记录（restore-docs-wording-20260911-close）

- 恢复事实（不重算）：2026-09-09 05:12 升级前；SOURCE 1533/1533；206 还原 / 176 新增移 Trash / 40 从 9/8 补全；`.env`/现有数据保留。
- 前端 tsc/build 通过（既有日志，本收尾未重跑）。后端 46 passed / 12 errors 为旧版 `preferences_cache` 缺 `_invalidate_cache`，不修旧版。
- 3011/3018 wrapper 后台任务暂停，不是日常全功能验收。
- Codex 实测（转录，非本执行端观察）：3011 旧版看板 9/9 5468 股票 + 241 分钟脉搏 + 行业资金流 128/128；`/data` 展示 8,214,828 条日线，打开 Stock daily bars 详情成功；浏览器 error logs `[]`；后续数据仍保留。
- 独立只读 review `aca6de45-3dcf-4aa3-8b86-12c80cef1590`，session `b09672e5-80b9-4d25-b8ee-eefdedf1f63c`，完成 success/pass：无恢复阻断、384 extras 仅 docs 资料、176 已 trash、12 errors 旧版固有。
- review 请求 Grok 4.6 Extra High 配置 ack 有，实际模型/effort 未核验。实现任务传输超时，不写 workflow 成功。
- 完整证据：`/Users/simon/Trading/one-trading/docs/cursor-handoffs/restore-pre-cursor-20260911/restore-report.md`。

### overview_scope_fix_20260911

#### 用户目标与可见结果

- 5 条旧 quote 样本不得显示成今日全 A（4/0/1、55.72 亿）。缺覆盖元信息时主 KPI 为 —，横幅标明范围/样本数/日期；55.72 亿只作为样本统计。
- 显式 `full_market` 才显示「今日公开行情」合计。正式日可合计，日期不漂到 today。Layout 缺 `mode` 为「未知」，`none` 为「未开启」，显式 `full_market` 才「全市场」。

#### GitHub 情报与固定上游点

- 无新 GitHub 审阅。数据台装配见 `overview_scope_fix_20260911`。资讯 Layout.mobile 失败归因：共享 mock 缺 `mode` 却断言全市场；不是资讯回归。

#### 本地路由、Module、Adapter 与跨台依赖

- `Dashboard.tsx` / `Layout.tsx` / `api.ts` `OverviewCoverage`。只读 `GET /api/overview/market` 的 `coverage`。不改资金流/脉搏/官方池节奏。

#### 自动检查与构建

- 本执行端：vitest `Dashboard.scope` 5 + `Dashboard.multiuser` 17 + `Layout.mobile` 21 = **43 passed**。`tsc --noEmit` exit 0。`vite build --outDir /tmp/ot-overview-scope-vite-dist` 成功，未写 shared `frontend/dist`。
- 2026-09-11 lineage P2 最小修复未改 frontend。WP2 前端 6 文件 SHA 与检查任务 `0238cce4` / candidate `c79a1b122751cd0802301177873afae044d8236374d35cbfb1d732686e657252` 一致，复用其 43 / tsc / vite 证据，不机械重跑。

#### 当前状态与用户验收

- 当前状态：`implemented`。独立 review `f4889223-1dcd-4362-9dd1-97e8ff9c5455` 虽 PASS，总工将 lineage 残余 P2 提升为本包必修；修复在数据台 overview 装配，用户台可见契约未改。IAB 待 Codex；3018 须由 runtime owner `01a07a79-1c8e-73e0-af8f-85939177bb8b` 刷新后才能看新后端。不是 `accepted` / `production`。
- 基线分类（2026-09-12）：**基线不含；仅历史未重新授权**。43 passed / tsc / vite 原数字保留，不当作当前已重做。

### industry_half_year_window_open_20260910

#### 用户目标与可见结果

- 已登录首页行业「半年」改为 126 日窗口排名，带时效行。概念「半年」和两边「1 年」仍是当日快照。
- 门槛按 kind：行业最长 126，概念最长 63。年档 250 即使 API 完整也不请求。

#### GitHub 情报与固定上游点

- 无新 GitHub 审阅。126 加总证据见数据台日志 `industry_window_126_sum_20260910`。日历覆盖见 `industry_window_freshness_calendar_cover_20260910`。

#### 本地路由、Module、Adapter 与跨台依赖

- `frontend/src/components/SectorFundFlowPanel.tsx`：`BOARD_WINDOW_MAX_DAYS = { board: 126, concept: 63 }`。`wantsWindow = selectedWindow.days <= BOARD_WINDOW_MAX_DAYS[kind]`。
- 只读 `GET /api/free/fund-flow/boards/window?days=126`。时效行仍仅行业。
- 不请求 `fundFlowConceptsWindow(126)`，不请求任一侧 `days=250`。

#### 自动检查与构建

- 前端 `SectorFundFlowPanel.history.test.tsx` + `SectorFundFlowPanel.industry-freshness.test.tsx`：14 passed。
- 后端 `test_industry_window_126_complete_and_250_incomplete` 与已升主树的 freshness 用例随日历套件 7 passed。

#### 当前状态与用户验收

- 当前状态：`verified`（仅行业半年开门 + 概念/年档锁死）。不是 `accepted` / `production`。不是概念 126 或年档 250 开门。
- 2026-09-10 Cursor 内置浏览器已登录 `http://127.0.0.1:3011/` 另开首页（不是 WP2 时效验收同一次）：行业「半年」`近126个交易日累计 · 行业日线窗口排名`，`2026-03-11`～`2026-09-09`，128/128，`数据截止 2026-09-09 · 足够新 · 窗口完整`，农业综合Ⅱ -2.67 亿 / 半导体 -5719.16 亿。同页概念「半年」当日快照（军工 +25.20 亿）；两边「1 年」仍当日快照。见 `docs/investigations/2026-09-10-industry-half-year-open/evidence/browser-wp3.json`。
- 2026-09-10 15:30 自然触发后行业窗截止可能已离开上条 `2026-09-09`；数据三件证据见数据台 `daily_pipeline_natural_1530_observe_20260910`。本条未重开浏览器。
- 2026-09-11 核对：正式盘行业 126 已是 `2026-03-12`～`2026-09-10`，128/128。概念「半年」与两边「1 年」源码仍不请求长窗、回退当日快照并标明不足；不能称已有长窗。前端 14 例 + tsc 通过。独立 audit PASS（见数据台 `dashboard_data_acceptance_20260911` / `chief-acceptance.md`）。Codex IAB ~15:00 隔离 3011：行业 5/63/126=128/128，至 9/10，主要金额与 window-sums 相同；15:05:57 行业 126「已陈旧」是日内 freshness 门变化。本执行端未亲测。不是 `accepted` / `production`。
- 基线分类（2026-09-12）：kind-specific 126/63 门槛是**基线不含；恢复后新授权重做**，见 `fund_flow_window_chain_restore_20260912`。本条 14 passed 与 9/10–9/11 页数字保留。

### concept_fundflow_daily_roll_visible_20260910

#### 用户目标与可见结果

- 已登录首页概念「5 天 / 1 个季度」离开 `2026-08-25`～`2026-08-31`，跟到东财 H5 最新已收盘日。
- 概念不加时效行。「半年 / 1 年」仍是当日快照。前端门槛本条未改。

#### GitHub 情报与固定上游点

- 无新 GitHub 审阅。数据闭环见 `docs/data-platform-development-log.md` 的 `ext_fund_flow_concept_daily_h5_roll_live_20260910`。

#### 本地路由、Module、Adapter 与跨台依赖

- 用户台未改 `SectorFundFlowPanel.tsx`。只读 `GET /api/free/fund-flow/concepts/window`。
- 路由：首页 `/` both 面板概念一侧。

#### 自动检查与构建

- 前端未改，无新 vitest。数据台 HTTP/加总见对应条目。

#### 当前状态与用户验收

- 当前状态：`verified`（仅可见概念 5/63 窗前移）。不是 `accepted` / `production`。不是概念 126 开门。
- 2026-09-10 Cursor 内置浏览器已登录 `http://127.0.0.1:3011/`：概念 5 日 `2026-09-03`～`2026-09-09`，覆盖 504/504，5G概念 +253.70 亿 / 融资融券 -334.78 亿；「1 个季度」`2026-06-12`～`2026-09-09`，满窗 490/504，CAR-T +42.23 亿；「半年」当日快照（军工）。概念无「数据截止 / 足够新 / 已陈旧」行。
- 2026-09-10 15:30 自然触发后概念 5/63 窗截止可能已离开上条 `2026-09-09`；见数据台 `daily_pipeline_natural_1530_observe_20260910`。本条未重开浏览器。
- 2026-09-11 核对：磁盘概念 5 日 `2026-09-04`～`2026-09-10` 504/504，63 日满窗 490/504。概念仍无时效行。「半年 / 1 年」仍当日快照契约。Codex IAB ~15:00：概念 5=504/504、63=490/504；概念 126 与双方 250 窗口不足 / 9/2 快照日期 / 不能当完整累计。本执行端未亲测。不是 `accepted` / `production`。
- 基线分类（2026-09-12）：概念 H5 续更代码是**基线不含；恢复后新授权重做**，见 `fund_flow_window_chain_restore_20260912`。本条可见窗数字保留。旧 15:30 正式批写不是当前授权。

### industry_window_freshness_calendar_cover_20260910

#### 用户目标与可见结果

- 行业窗时效离开「交易日历未覆盖到当日」的无法确定，改为足够新或已陈旧。
- 5/63 金额不变。前端未改门槛。

#### GitHub 情报与固定上游点

- 无新 GitHub 审阅。数据台覆盖补丁见开发日志 `4.6` 2026-09-10 条。不是 `D-P2-04`。

#### 本地路由、Module、Adapter 与跨台依赖

- 用户台未改组件。只读 `GET /api/free/fund-flow/boards/window`。

#### 当前状态与用户验收

- 当前状态：`verified`（仅行业时效文案离开缺日历 unknown）。不是 `accepted` / `production`。日历生命周期不提升。
- 2026-09-10 已登录首页行业 5 日：`数据截止 2026-09-09 · 足够新 · 窗口完整`，128/128，通信设备 +179.73 亿。
- 2026-09-11 核对：日历仍覆盖到 2026-10。盘中 13:58 只读聚合行业 5/63/126 `fresh` / `calendar_covers=true`，截止 `2026-09-10`。金额已随窗滚动，上条 9/9 数字不是本轮页结果。Codex IAB 15:05:57 行业 126「已陈旧」证明 freshness 门随时间变，不能把早前「足够新」当一直 fresh。`window-sums.json` freshness=null 是旧原始值，与 UI 实时 freshness 不同，未改。本执行端未亲测。
- 基线分类（2026-09-12）：日历覆盖语义在 00:19 树已成立；9/12 新授权只读核验，不改日历文件。

### data_catalog_compact_20260910

#### 用户目标与可见结果

- `/data?section=catalog` 去掉「数据集目录 / 数据目录」双重标题。六导航、目录显示设置、focusGroup 与隐藏偏好语义不变。
- 目录改为紧凑分组行：中文业务名（known-ID 映射，未知/自定义 title fallback）、dataset_id、登记提供方、本地/服务一条、记录质量、覆盖日期、标的/行/体积、详情/追踪。四 AvailabilityBadge 与覆盖条进详情。
- 前端临时搜索/来源/状态筛选；零结果与目录空/加载失败分开。待关注只按 failed/degraded/unknown 与缺本地/未服务，不按数据旧判坏。

#### 本地路由、Module、Adapter 与跨台依赖

- 用户台：`Data.tsx`、`DataCatalogSection.tsx`、`DatasetCatalogCard.tsx`、`DatasetDetailDrawer.tsx`。共用 `catalogDisplayTitle` 也被总览来源详情消费。
- 只读 catalog/control/schema/lineage。不改 dataset ID、来源、库、80GB 原包、总览结构。

#### 自动检查与构建

- 历史自动检查（截至 2026-09-10 01:22:59，不是本轮重跑）：controller 两 checks exit 0；`frontend` vitest 4 files / 52 passed + `tsc -b && vite build`。`checks.log` sha256 `3e4c92bef1949c5cce443aab61cc6fc060455c416ac3b46956cdef5e6273bd49`。实施 `d6121999-52c0-47a8-a1be-89c213a1ec32` completed；独立 review `13b341a7-bdfa-4fea-b1ff-6bdc9514cf72` completed/pass，session `80da7216-fe0f-4970-82dc-1ef2d234e281`，candidate `5739f4024f240c315936e329a70be54f32912dbffd9c0c7a6c91111695df58d5`。
- 2026-09-11 对照该 candidate：目录实现文件当时仍同 hash（`DataCatalogSection.tsx` `9d3b5539…`、`Data.tsx` `25efa5f8…`、`Data.test.tsx` `2a2d8885…`）。漂移只在后续共用 `docs/workbench-development-log.md`（`1e582437…` → 后继条目续写）。本轮目录外包增量另改 `DataCatalogSection.tsx` / `Data.tsx`，见 `data_catalog_offline_margin_20260911`。

#### 备份

- `/Users/simon/备份/codex/one-trading-catalog-compact-20260910_011501`

#### 当前状态与用户验收

- 历史状态（截至 2026-09-10）：`historical verified`。紧凑目录自动检查与独立 review 已通过（hashes/时间见上，未重跑）。总工当时已在现有 3011 看过宽/窄、筛选 hithink 4 集、两融详情、来源血缘、空筛选，无新增错误；该 IAB 由同一线程上轮工具产生，不是 9/11 运行面证据，也不把本条升为用户 `accepted` / `production`。
- 当前：9/10 紧凑目录本身按当时证据保持 `historical verified`。9/11 目录外包增量另见 `data_catalog_offline_margin_20260911`，不回写本条生命周期。
- 基线分类（2026-09-12）：**基线不含；仅历史未重新授权**。新授权明确不恢复瘦身/紧凑目录。52 passed 等原数字保留。
- 下一步工程计划未更新。

### data_overview_layout_slim_20260910

#### 用户目标与可见结果

- `/data` 总览在既有 `max-w-6xl` 内取消内层 `max-w-5xl`；宽屏能力列表与来源列表约 4:6 并排，窄屏上下排列。
- 七项能力改为紧凑行：能力名、当前配置源或「配置未就绪」、本地数据状态；不再并列「能力不可用」。提供方选项收进每行「切换」，展开不写入。
- 来源改为紧凑可选行；能力芯片/套用/安装离开列表。新增数据源在标题区；重载/接入文档/目录路径默认折叠。默认不展开 TickFlow，点击来源才出详情，可收起；档位/密钥说明默认折叠。
- 普通用户横幅与无密钥提示缩短，不写死仍免费/全可用。六导航、存储/采集/来源追踪仍可达。

#### 本地路由、Module、Adapter 与跨台依赖

- 用户台布局：`frontend/src/pages/Data.tsx`、`frontend/src/pages/settings/DataSources.tsx`、`frontend/src/components/data/SourceDatasetDetails.tsx`。
- 不改融合映射、backend、密钥、路由偏好、插件配置、依赖。既有脏修改与 Mock 自定义源全部保留。

#### 自动检查与构建

- 历史自动检查（截至 2026-09-10 00:59:16，不是本轮重跑）：controller tests+build exit 0；`frontend` vitest 4 files / 40 passed + `tsc -b && vite build`。`checks.log` sha256 `670d3c03039172436368f775af75a91dfa6b58bd4f7b2290f684d5890365da02`。实施 `a67a54b7-6b1a-4620-a990-c98a99322074` completed；独立 review `4309c1bf-01db-46fd-93ae-abcbd0204d45` completed/pass，session `a62eed5f-c5f1-4784-a3f4-aaddbc361e24`，candidate `06b4fcab2a7af12547f270f92caa1616e1e92742595d5be0a001d27c357579f5`。
- 2026-09-11 对照该 candidate：总览面板文件当时仍同 hash（`DataSources.tsx` `f28b6757…`、`ExternalReadOnlyData.tsx` `ceb4fe1e…`）。其后目录紧凑包改过 `Data.tsx` / `Data.test.tsx` / `DataUnifiedSources.test.tsx`；共用日志续写。本轮只再改查询组件与目录入口，见 `data_catalog_offline_margin_20260911`。

#### 备份

- `/Users/simon/备份/codex/one-trading-data-layout-slim-20260910_004346`

#### 当前状态与用户验收

- 历史状态（截至 2026-09-10）：`historical verified`。总览瘦身自动检查与独立 review 已通过（hashes/时间见上，未重跑）。总工当时已在现有 3011 看过：宽屏能力/来源约 4:6 并列，窄屏上下；默认详情收起；hithink 4 集详情可开合；日 K 提供方切换只展开未写入；stock-sdk 摘要；无新增错误。该 IAB 由同一线程上轮工具产生，不是 9/11 运行面证据，也不把本条升为用户 `accepted` / `production`。不要把目录条的筛选/两融/血缘 IAB 复制到本条。
- 当前：9/10 总览布局本身按当时证据保持 `historical verified`；总览外包详情复用未改。9/11 目录增量另见 `data_catalog_offline_margin_20260911`，不回写本条生命周期。
- 基线分类（2026-09-12）：**基线不含；仅历史未重新授权**。新授权明确不恢复总览瘦身。40 passed 等原数字保留。
- 下一步工程计划未更新。

### data_catalog_offline_margin_20260911

#### 用户目标与可见结果

- `/data?section=catalog` 在托管列表外增加默认关闭的紧凑行「外部只读原包 · 两融查询」。不把虚拟 80GB 原包计入目录条数、体积、来源筛选或托管 schema。
- 仅管理员可见；普通用户不发 `external-readonly-sources`、不暴露路径。展开才 mount 查询 UI。
- 查询只显式提交标的，走既有 `GET /api/f10/margin-trading?source=offline_quantdb&limit=20`，不 fallback / local / 联网补拉。总览 `SettingsDataSourcesPanel` 详情复用不变。
- 已配置不代表全部数据可读。未查写「截止按标的查询获取」，不硬编码旧日期。empty 如实无记录并可带 source/as_of。错误后不再展示旧成功表。同标的失败后手动重试会 refetch。

#### 本地路由、Module、Adapter 与跨台依赖

- 用户台：`DataCatalogSection.tsx` 折叠入口；复用 `ExternalReadOnlyData.tsx`（`compact` + `idPrefix=catalog-offline-margin`）。`Data.tsx` 传入 `isAdmin`。
- 只读消费既有 `GET /api/data/external-readonly-sources` 与 `GET /api/f10/margin-trading`。不改 backend / 权限 / `.env` / 原包。
- 数据台边界仍见 `docs/data-platform-development-log.md` 的 `4.21`（`canary`）与 `4.22`。

#### 自动检查与构建

- 本轮声明 checks 已跑一次（2026-09-11 14:40:36）：`frontend` vitest 5 files / 62 passed；随后 `tsc -b && vite build` exit 0。不是全仓 tests。实施 `509502e6`。独立 review `d90bf644-cc57-4639-9397-c6e51460604f` PASS，NEW session `0bf68b5f-6944-4cb6-8e8c-0e2b97f69ac7`，candidate `6c7fa0fd3a45ff319546435108b5c89b633dd0e3b0341c2fdf7bbb692c70d769`。主审此前核对最终产品 hash 与运行记录 codehash 均无漂移；本条不重做已完功能。不沿用口头或上轮 IAB。本纠偏未重跑 checks。
- 备份：`/Users/simon/备份/codex/one-trading-catalog-offline-margin-20260911-141307`

#### 当前状态与用户验收

- 当前状态：工程 `verified`，待用户体验验收。仅限 2026-09-11 隔离验收，不是正式服务、不是 15:30 恢复、不是 `accepted` / `production`。
- 运行范围（既有 `docs/cursor-handoffs/shared-isolated-runtime-20260911/runtime.json`）：backend PID 64083 于 14:50:41 +08，frontend PID 64159 于 14:51:26 +08；`DATA_DIR=/Users/simon/Trading/one-trading/data/shared-isolated-runtime-20260911`；禁后台、`NEWS_CACHE_MODE=isolated_preview`；Vite 当前源码、后端无 reload。隔离只复制约 4.2MB 必要输入，不把其中空日 K 当正式缺数。
- 真实 IAB：总工本线程 `01a07a79-1c8e-73e0-af8f-85939177bb8b` 于 9/11 14:55–15:00 在 `http://127.0.0.1:3011/data?section=catalog` 获得。六 tab；41 登记、40 可见；`stock_margin_trading` 筛选 1/40。外部原包默认关闭，展开才查询，不计托管。`300502.SZ` 返回 20 条 `source=offline_quantdb` / `as_of=2026-08-26`，缺字段提示、缺值—。`000000.SZ` 缺文件 404 时旧成功表消失，同标的重试两条 GET 日志 14:57:17 / 14:57:26；切回 `300502.SZ` 成功。本地两融详情 1886 行、8 标的、68KiB、latest 2026-08-04；hithink 4/40。390×844 目录换行可读，查询表头较挤为非阻断样式限制，viewport 已 reset。console 仅 Router/动画 warnings，无应用 error。
- 普通用户 guard/empty/unreadable 由上述 62 tests 覆盖，不伪称真人角色或损坏原包实测。本机隔离未配置身份，走现有本机放行，不是「已登录」，未创建账号。IAB 只略过 onboarding、只读查询。
- 下一步工程计划未更新。
- 基线分类（2026-09-12）：9/11 目录外包是**基线不含；恢复后新授权重做**，见 `data_catalog_offline_margin_restore_20260912`。本条 62 passed 与 9/11 IAB 数字保留，不降级、不删除。

### data_entry_unification_20260909

#### 用户目标与可见结果

- 侧栏「数据」是唯一主入口。`/data` 总览同时给出能力卡（谁提供 / 配置就绪 / 本地已有）和来源卡（在线提供方、按证据归组的本地采集、未登记、管理员外部只读原包）。
- 点击来源看支持能力、匹配数据集、字段/单位、覆盖时间、真实生产者。付费档位只出现在 TickFlow。新建源仍走原上面板。
- `/settings?tab=data-sources` 重定向到 `/data?section=sources`；设置页不再保留重复「数据源」tab。密钥仍在设置 → 数据密钥。

#### GitHub 情报与固定上游点

- 无新 GitHub 审阅。实现说明：`docs/investigations/2026-09-09-data-entry-unification/README.md`。评估：`docs/investigations/2026-09-09-data-entry-unification-assessment/README.md`。

#### 本地路由、Module、Adapter 与跨台依赖

- 用户台：`Data.tsx` 嵌入 `SettingsDataSourcesPanel`；映射 `dataSourceCatalog.ts`；详情 `SourceDatasetDetails.tsx` 复用目录字段与 provenance。
- 只读消费既有 capability-matrix / data-sources / catalog / source-provenance / external-readonly。不改后端权限。

#### 自动检查与构建

- 本条不声称控制器 checks、独立 review 或 IAB 已通过。检查阶段只收紧页面测试选择器并去掉两处未用类型，未改产品行为。
- 2026-09-09/10：按独立 review 与总工 IAB 三点修正（双套七卡、只读 redetect 403、catalog 未就绪误报无关联）。修正前已验路径：旧 settings 数据源 tab → `/data?section=sources`；公开源 11 集、hithink 4 集可开字段 drawer + 生产者同花顺官方金融数据服务；原包 `300502.SZ` 20 条 `offline_quantdb` 截至 2026-08-26 空值—。修正后唯一矩阵/只读态仍待总工。本会话未跑整组 tests/build。

#### 当前状态与用户验收

- 当前状态：`implemented`。待总工用现有 3011 做 UI 验收。不是 `verified` / `accepted` / `production`。
- 基线分类（2026-09-12）：**00:19 基线核心，不撤销**。
- 下一步工程计划未更新。

### data_source_overview_status_20260909

#### 用户目标与可见结果

- `/data` 总览把「配置源」「配置/能力是否就绪」「本地是否已有数据」分开，不再用 `source_health` 0 失败行数冒充全部数据源正常。
- 提供方/Key/插件仍只在 `/settings?tab=data-sources` 编辑；总览只读摘要并链到该页。原「配置」不再误指 `tab=account`。
- 总览增加「外部只读数据」：未配置/目录不可访问/已配置，目前只支持两融小样本查询。

#### GitHub 情报与固定上游点

- 无新 GitHub 审阅。固定调查：`docs/investigations/2026-09-09-data-source-ui-overlap/README.md`。实现说明：`docs/investigations/2026-09-09-data-source-convergence/README.md`。
- 数据台只读元数据见 `docs/data-platform-development-log.md` 的 `4.22`。

#### 本地路由、Module、Adapter 与跨台依赖

- 用户台：`frontend/src/pages/Data.tsx`、`ControlPlaneSummary.tsx`、`ExternalReadOnlyData.tsx`、`settings/DataSources.tsx`。
- 只读消费 `GET /api/settings/capability-matrix`、Catalog、`GET /api/data/external-readonly-sources`、`GET /api/f10/margin-trading?source=offline_quantdb`。
- 不改真实路由默认值、偏好持久化或网络 fallback。

#### 自动检查与构建

- 实现中可跑最窄单项；本条不声称控制器 3 条 checks、独立 review 或 IAB 已通过。
- 未重跑旧 38 tests / 原包 3 股票对照 / 全仓 tests。

#### 当前状态与用户验收

- 当前状态：`implemented`。待总工用现有 3011 做 UI 验收。不是 `verified` / `accepted` / `production`。
- 下一步工程计划未更新。

### upstream_v022_sync_20260831

#### 用户目标与可见结果

- 保留全部本地魔改：`/ai`、Hermes、多用户、`/admin/users`、`/trading`、Dashboard 市场脉搏/同花顺 KPI、数据目录、HiThink 四表 Adapter。
- 补上本地没有的上游 v0.2.2 用户可见能力：`/mining` 因子挖掘、`/abnormal` 异动中心、自选 M:N 分组、分钟策略/分时列、市场环境情绪周期+主线、设置「数据源 / 超时」、监控异动/放量、复盘龙虎榜入口。
- 不整仓 merge/rebase；不替换 Catalog、Hermes、Dashboard、HiThink `/api/hithink`。
- Fuyao 插件只作可选能力路由；同花顺官方池/龙虎榜/竞价/估值仍走本地 HiThink Adapter。

#### GitHub 情报与固定上游点

- 主记录：`/Users/simon/Trading/用户台GitHub项目借鉴记录.md` 的「2026-08-31 上游 v0.2.2 与本地魔改对照」。
- 固定点：`shy3130/tick-stock-panel` `main@4d27f3139ef58e25fc410b373363dd6bf40c6dfa` / `v0.2.2`。
- 本轮是本地实现，不是新的 GitHub 审阅。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/router.tsx`、`frontend/src/components/Layout.tsx` 增加 `/mining`、`/abnormal`；侧栏保留 AI / 交易 / 用户管理。
- 新页：`frontend/src/pages/Mining.tsx`、`frontend/src/pages/Abnormal.tsx`；叠加上游 Watchlist / Regime / Monitor / Screener / Review / CustomSignals / Backtest 后回接 PageContext。
- 设置：`frontend/src/pages/Settings.tsx` 增加 `data-sources`、`timeout`；`frontend/src/pages/settings/DataSources.tsx` 与本地「数据密钥」并存。
- 数据台接口只作消费：`/api/backtest/mining/*`、`/api/abnormal/*`、`/api/watchlist/groups*`、`/api/settings/data-sources`、`/api/regime/*`。分钟批量只读本地 parquet，不现场回补。
- 2026-08-31 续：复盘龙虎榜 `get_dragon_tiger` 在 fuyao 缺失/失败时只读本地 HiThink 分区；异动 `change_pct`/`amplitude` 在 enriched 与盘中聚合两层把报价百分点换成小数。
- 2026-08-31 再续：`KlineRepository` 补上挖掘指纹要用的 `get_matrix_data_generation` / `latest_enriched_date`。前者接到已有 `get_enriched_generation`，后者只扫本地 enriched 分区。创建任务不再因缺方法 500。
- 2026-08-31 三续：挖掘 worker 按本地 `StrategyEngine(enriched_loader=...)` 构造，不再传上游-only 的 `override_loader` 当唯一入口；`StrategyDef` 补 `execution_backend` / `resolve_params`，回测引擎补世代读写。创建任务已在本机 `POST /api/backtest/mining/runs` 得到 200 `queued`。作业进程下一步还缺本地 `strategy.py` 的矩阵挖掘入口（`BacktestResultPolicy` / `StrategyDependencyResolver`），未整段替换回测服务。
- 2026-08-31 四续：策略页首屏打 `GET /api/screener/cached-summary`，后端当时没有这条路由，已登录日志为 404，页面右下角连弹「Not Found」。已补 `cached-summary` / `cached-result/{id}`，空缓存返回空摘要而不是 404。`策略池 0/19` 是本地池为空，不是接口挂了。
- 扩展插槽：`frontend/src/extensions/ExtensionSlot.tsx` 在注册表未冻结时空渲染，避免自选页整页炸掉（`finalizeFrontendExtensions` 当前未被调用）。

#### 自动检查与构建

- `frontend` `tsc -b --force`：通过。
- 新增依赖：`@tanstack/react-virtual@3.14.10`。
- `from app.main import app`：347 条路由。OpenAPI 有 abnormal / watchlist groups / data-sources / regime / backtest mining；`/api/health` 仍 404，探活用 `/health`。
- 未跑全量 vitest / pytest。未 commit。

#### Codex 内置浏览器目标运行面

- 已登录 `http://127.0.0.1:3011/`（admin）。前端 Vite `:3011`，后端 uvicorn `:3018`。
- 首页：侧栏同时有「挖掘 / 异动监控」和「AI / 交易 / 用户管理」；看板盘中快照正常。
- `/mining`：挖掘配置、因子目录、周度自动挖掘渲染。2026-08-31 续：策略对照改为 `strategyList()` 再按 `asset_types` 过滤，不再把 `stock`/`etf` 当成 `owner_user_id`；已登录复检无「目标普通用户不存在或已停用」，`GET /api/strategies` 为 200。点「开始挖掘」曾因仓库缺指纹方法 500（「研究任务 · 创建任务」）；已补 `get_matrix_data_generation` / `latest_enriched_date`。2026-08-31 三续：本机已登录 `POST /api/backtest/mining/runs` 为 200 `queued`，创建任务 500 已消失；作业随即因 `app.backtest.strategy` 缺 `BacktestResultPolicy` 失败，未在 Codex 浏览器再点一遍「开始挖掘」。
- `/abnormal`：竞价/盘中/偏移三栏与当日量价信号表可开。2026-08-31 续：报价百分点已换成 enriched 小数；盘中涨停样例为 `+20.00%` / `+19.99%`，无 `+2002%`。偏移 tab 仍需手动开启监控。
- `/watchlist`：分组条「全部 / 未分组」与 14 只自选表可开。首次因 ExtensionSlot 抛错整页崩溃，已修后复检通过。
- `/regime`：市场环境日历/四维拆解可开；「情绪周期」可切到主线排行，提示阶段数据未生成，未点「重算」。
- `/settings?tab=data-sources`：能力路由 + TickFlow 介绍；本地「我的账号 / 数据密钥 / AI 设置 / 运行日志 / 超时设置」仍在。
- 本地保留页未回归：`/ai` 功能目录、`/admin/users` 账户表、`/data` catalog 总览、`/monitor`（含异动监控/轮询放量筛选项）。
- `/review`：2026-08-31 续：无 fuyao 时读本地 `reference/hithink_dragon_tiger`。已登录复检为「本地最近一期官方榜 · 同花顺官方 · 2026-08-25 · 60 只」，明细涨跌为 `+10.0%` / `+20.0%`，不再提示「需要 fuyao」。不现场同步、不改 `/api/hithink`。

#### 自动检查与构建（2026-08-31 续）

- 后端：`tests/test_abnormal_intraday.py`、`tests/test_dragon_tiger.py`、`tests/test_enriched_change_pct_units.py` 共 20 passed。
- 前端：`tsc -b --force` 通过。
- 未 commit。

#### 当前状态与用户验收

- 当前状态：`implemented`。三处跟进已在已登录 Codex 浏览器核对（挖掘误报、异动涨跌幅、复盘龙虎榜接本地 HiThink）。创建挖掘任务的 500 已在仓库层补指纹方法，本机 `POST /api/backtest/mining/runs` 为 200。挖掘作业本身未跑通（本地 `strategy.py` 缺 `BacktestResultPolicy` / `StrategyDependencyResolver`）。策略页 `cached-summary` 404 已补路由，本机未登录探测为 401（路由已挂上）；未再做已登录浏览器点击验收。下一步工程只在用户台计划 `U-P1-04`，本条不升 `verified / accepted / production`。情绪周期未重算。
- 回滚：去掉本轮迁入的 `/mining` `/abnormal` 路由与叠加页，恢复自选/环境/监控/策略的本地副本；不要整仓回退到 `origin/main`。

### industry_fundflow_daily_roll_freshness_20260907

#### 用户目标与可见结果

- 行业资金流窗口/面板写明实际数据截止日，以及足够新 / 已陈旧 / 无法确定。
- 窗口完整和足够新是两种判断；日历不覆盖时显示无法确定，不用日K日期假装法定日历。
- 5 天=1 周、季度 63、Top6 两端、概念 90% 与半年/一年回退快照保持原样。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。数据闭环见 `docs/data-platform-development-log.md` 的 `ext_fund_flow_bk_daily_industry_roll_phase_b_20260907`。

#### 本地路由、Module、Adapter 与跨台依赖

- 用户台：隔离 overlay `frontend/src/components/SectorFundFlowPanel.tsx`，仅 `kind==='board'` 增加时效行。
- 类型：`FundFlowWindowResponse` 增加可选 `data_as_of` / `freshness_status` / `freshness_note` / `expected_trading_day` / `calendar_covers`。
- 只读消费既有 `GET /api/free/fund-flow/boards/window`；本轮未打开已登录页面，也未验证 HTTP。
- 数据台续更与时效字段见对应数据台条目；概念面板不加这些文案。

#### 自动检查与构建

- 隔离 vitest 10 passed（既有 history 7 + 行业时效 3）：`docs/investigations/2026-09-07-industry-fflow-daily-roll/results/vitest.txt`
- 未跑全量前端构建，未用 Codex/系统浏览器验证。

#### 当前状态与用户验收

- 当前状态：`implemented`。不是 `verified` / `accepted` / `production`。
- 主树面板文件未改；补丁在 `docs/investigations/2026-09-07-industry-fflow-daily-roll/patches/`。
- 下一步工程计划未更新。

#### 2026-09-07 18:47 独立复查返工（只追加，不整份回退）

- 本条相对 15:50 备份的漂移包含 Phase B 本条追加，回滚不得用该备份覆盖本文件。
- 行业时效判定改为 Asia/Shanghai + 日历 `close_time`：盘中期望上一开市日，日终/收盘后期望当日；周末/假日走最近已完成开市日；日历不覆盖仍 `unknown`。
- overlay `api.ts` 只保留业务可选字段，无测试专用导出。vitest 用插件记录 `@/lib/api` 已解析绝对路径；隔离 `tsc --noEmit` 检查 `FundFlowWindowResponse` 时效字段。
- 面板 7+3 未因本条总工意见重跑。契约 vitest 1 passed；`tsc --noEmit` 0。
- 当前状态仍为 `implemented`。未用已登录 Codex 内置浏览器，未验证真实 HTTP。

### industry_fundflow_daily_roll_live_20260909

#### 用户目标与可见结果

- 行业资金流窗口显示实际截止日、时效、完整度。日历不够时是「无法确定」，不是用日 K 假充。
- 5 天=1 周、季度 63、Top6 两端、概念 90% 不改。概念面板不加时效行。

#### GitHub 情报与固定上游点

- 无新 GitHub 审阅。数据闭环见 `docs/data-platform-development-log.md` 的 `ext_fund_flow_bk_daily_industry_roll_live_20260909`。

#### 本地路由、Module、Adapter 与跨台依赖

- `frontend/src/components/SectorFundFlowPanel.tsx`：仅 `kind==='board'` 显示 `数据截止 … · 足够新/已陈旧/无法确定 · 窗口完整/不完整`。
- `frontend/src/lib/api.ts`：`FundFlowWindowResponse` 可选时效字段。
- 路由：`/industry-analysis`；首页 `/` 的 both 面板里行业一侧同样消费该字段。
- 只读 `GET /api/free/fund-flow/boards/window`。数据台续更见对应数据台条目。

#### 自动检查与构建

- 原实现记录：`tsc --noEmit` exit 0（`evidence/tsc.txt`）。既有面板 vitest「7 passed」只存在于 `implementation.md` 陈述，无单独 vitest 日志，本阶段不把它写成新的执行端实测。
- 原 14 pytest 日志：`evidence/pytest.txt`「14 passed, 1 warning in 4.88s」。控制器 `ecf15990-52f4-48f8-ba7f-1d949aba4285` `checks.log` 重跑 `14 passed in 4.20s`，exit 0。独立 review 未重跑，不是漏测。
- Vite `3011` 已返回带 `industryWindowFreshnessLine` 的面板源。
- 执行端未登录 HTTP 401 是未登录事实。总工已登录 IAB 05:26:04 UTC + HTTP 05:37:04 UTC 已完成 5/63 窗。

#### 当前状态与用户验收

- 当前状态：`accepted`（仅当下可见行业 5/63 窗）。不是 `production`。不是整用户台完成；概念窗与日历未完成不可混写。
- 独立技术复核 task `9cd3cd22-b5e1-4262-950d-29300d799fed` / session `75c6b767-3e2c-422d-ab3b-fcba37faf477`：产品 P1 无；独立 Parquet 逐日求和与总工 HTTP200 12+12 项 `main_net` 精确相等。文档P2本阶段修正待独立定点复查。
- 2026-09-09 05:26:04 UTC：总工在 Codex 内置浏览器打开已登录 `http://127.0.0.1:3011/`，标题 `one-trading · Quant Terminal`。行业 5 日 `2026-09-02`～`2026-09-08`，覆盖 128/128，满窗 128/128，文案「数据截止 9/8 · 无法确定 · 窗口完整」，两端通信设备 +61.60 亿 / 半导体 -217.53 亿。实际把行业窗口下拉切到「1 个季度」后：63 日 `2026-06-11`～`2026-09-08`，同为 128/128 满窗，种植业 +24.14 亿 / 半导体 -3182.35 亿。同页概念 5 日仍是 `2026-08-25`～`2026-08-31`，满窗 503/504。本条只记用户可见结果，不替代执行端真实源/回读/HTTP/运行身份与独立金额验证，也不因此重抓源。
- 完整记录：`/Users/simon/Trading/one-trading/docs/investigations/2026-09-09-industry-fflow-live/implementation.md`

### industry_fundflow_quarter_window_ranking

#### 用户目标与可见结果

- 行业主力资金流向在磁盘满窗后，选「1 个季度」按近 63 个交易日累计排名，不再回退当日快照。
- 文案写明「近63个交易日累计」，并显示覆盖 / 满窗 128/128。
- 若窗口未满（缺日期或有行业 `days<63`），仍显示当日快照并标明窗口数据不足。
- 「半年 / 1 年」继续回退快照。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。数据闭环见 `docs/data-platform-development-log.md` 的 `ext_fund_flow_bk_daily_h5_63d_128`。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/components/SectorFundFlowPanel.tsx`，`BOARD_WINDOW_MAX_DAYS = 63`，且 `window_complete !== false` 才用窗口榜。下拉增加「1 周」（5 个交易日）。
- 只读接口：`GET /api/free/fund-flow/boards/window`。`window_complete` 现在要求快照每只 `days>=requested`。
- 测试：面板 7 项（含概念窗口）。

#### 自动检查与构建

- `pnpm exec vitest run src/components/__tests__/SectorFundFlowPanel.history.test.tsx`：7 passed。
- 后端窗口/合并测试 28 passed。

#### 当前状态与用户验收

- 当前状态：`verified`（行业 + 概念「5 天 / 1 周 / 1 个季度」主路径）。未标记 `accepted`。
- 2026-09-01：窗口终点改为最新东财 H5 已收盘日，再往前数交易日。「1 周」按 5 个交易日，与「5 天」同一窗口。已登录 `http://127.0.0.1:3011/`：两边 5 天/1 周都是 `2026-08-25 ~ 2026-08-31`；1 个季度都是 `2026-06-03 ~ 2026-08-31`。行业 5 日流入元件 +142.07 亿；季度流入种植业 +2.41 亿、流出半导体 -3180.95 亿。概念 5 日流入 2026中报预增 +428.22 亿；季度流入钛白粉概念 +5.09 亿。数据闭环见 `ext_fund_flow_bk_daily_h5_roll_20260831` 与 `ext_fund_flow_concept_daily_h5_roll_20260831`。今天 9/1 盘中未进累计。
- 2026-08-27 数据台探测：东财 H5 / `push2his` daykline 对单行业最多约 121 根（`2026-03-05`～`2026-08-27`），不够 126 / 250。`BOARD_WINDOW_MAX_DAYS` 保持 63；「半年 / 1 年」继续回退当日快照并标明窗口数据不足。详见 `docs/data-platform-development-log.md` 的 `ext_fund_flow_bk_daily_h5_126_250_blocked`。
- 2026-08-31：概念下拉不再误触发 Top20 回补；`1 天～1 个季度` 与行业一样走窗口累计。接口 `GET /api/free/fund-flow/concepts/window`。数据闭环见 `ext_fund_flow_concept_daily_h5_63d_504`。概念与行业名称/代码/金额无交集，季度榜不应相同。
- 2026-08-31 续：已登录 `http://127.0.0.1:3011/` 两边都切到「1 个季度」。概念是 `近63个交易日累计 · 概念日线窗口排名`，`2026-06-02 ~ 2026-08-28`，满窗 482/504，流入 CAR-T / 粮食 / 钛白粉，流出 融资融券 / 富时罗素 / MSCI中国。行业仍是贵金属 +18.41 亿 / 半导体 -3408.71 亿，`2026-06-02 ~ 2026-08-26`，128/128。概念「半年」回退当日快照（元宇宙，as_of 2026-08-31 11:09），文案写「不能当作半年完整累计榜」。
- 2026-08-27 续：首页 `top=6` 时，窗口接口曾按净流入从大到小只切前 48 条，5 天流出被切空、季度流出榜不是真实最大流出。已改为同时返回流入/流出两端。
- 2026-08-27 再续：季度累计只有 2 只为正时，流入栏不再只显示这两只；按 63 日合计从高到低取满 Top 6，从低到高取满 Top 6。
- 目标运行面：刷新已登录首页行业资金流。5 天应同时有流入 TOP 和流出 TOP；1 个季度流入仍可能只有贵金属、焦炭Ⅱ两只为正，但流出应出现半导体等真实大流出，而不是普钢。Cursor 内置浏览器如未登录，不算已登录主路径验收。

### dashboard_header_refresh_all_modules

#### 用户目标与可见结果

- 标题栏「刷新」重读看板上所有模块的本地数据：总览、市场脉搏、板块/概念资金流、监控记录、行情状态。
- 今天的激活态可以是「非实时」。上海时间午休（11:35–12:55）和 15:05 后即使行情进程还在跑，标题栏也是「非实时」，计时为 —，不再显示 73ms 这种盘中年龄。
- 「刷新」在「非实时」同样重读全部模块本地数据；只有当前仍在交易时段且是盘中快照时，才催行情缓存。历史日 / 午休 / 收盘不催行情。
- 页面每 15 秒用上海墙钟重判一次时段，午休结束后可以自行回到「实时」，不卡在上一份接口里的 `is_trading_hours`。
- 不拉同花顺官方池，不走脉搏「更新」外连，不走资金流 POST 刷新，不启动日更流水线。
- 按钮可见文案仍是「刷新」；辅助名是「刷新全部模块」。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/lib/dashboardFeed.ts` 的 `invalidateDashboardModules`，`frontend/src/pages/Dashboard.tsx` 的 `handleRefresh`。
- 数据台：只消费已有 local-only GET；盘中额外催现有 `POST /api/intraday/refresh`。不改 Provider、官方池或外连同步。

#### 自动检查与构建

- `frontend/src/pages/__tests__/Dashboard.multiuser.test.tsx`：模块 query 前缀作废、午休/收盘为「非实时」且不催行情、下午开盘可回「实时」、不调用脉搏/资金流/官方池/流水线同步。

#### 当前状态与用户验收

- 当前状态：`implemented`。今天午休看首页应是「非实时 / —」；点「刷新」会重读模块，不会把标签改成「实时」。13:00 后盘中快照仍在更新时，应自行回到「每 15 秒 · 已过 … / 实时」。

### dashboard_header_historical_vs_live

#### 用户目标与可见结果

- 选过去一天（如 2026-08-25）时，标题栏显示「历史」，计时为 —，不借用当天行情轮询的「实时 / 23s」。
- 只有看今天、且仍是盘中可更新快照时，才显示「实时」。盘中钟是「每 15 秒 · 已过 Xs」：一轮快照重装整份 `/api/overview/market`，不是每张卡各走各的钟。
- 今天已收成正式日后显示「非实时」。历史日整页静止，SSE 不作废带日期的总览查询。
- 市场脉搏、板块资金流、同花顺官方池、监控小组件不跟这根秒针。卡片「更新」只是手刷同一份总览的一块。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/lib/dashboardFeed.ts`、`frontend/src/pages/Dashboard.tsx`、`frontend/src/lib/useQuoteStream.ts`。
- 行情默认间隔：`QuoteService.DEFAULT_INTERVAL` / `BOARD_QUOTE_INTERVAL_S` = 15。本机 `preferences.json` 的 `realtime_quote_interval` 为 15。
- 2026-08-27：报价进程内存曾残留 8 秒，看板钟显示「每 8 秒」。`QuoteService.status` / 轮询循环现在会从偏好同步间隔；看板「实时」时 `/api/overview/market` 按同一间隔重拉，且 SSE `quotes_updated` 始终作废当天总览，不再被页面 SSE 开关关掉。

#### 自动检查与构建

- `frontend/src/pages/__tests__/Dashboard.multiuser.test.tsx`：盘中钟、实时总览前缀与 15 秒 refetch。
- `backend/tests/test_quote_service_interval.py`：残留 8 秒会被偏好 15 秒覆盖。

#### 当前状态与用户验收

- 当前状态：`implemented`。刷新已登录首页：今天盘中应看到「每 15 秒 · 已过 … / 实时」，指数和 KPI 随这根针更新。历史日仍是「历史」，不跟秒针。市场脉搏、资金流、官方池、监控小组件仍不跟这根针。

### dashboard_intraday_hithink_limit_kpi

#### 用户目标与可见结果

- 盘中涨停/跌停/炸板 KPI 只读**今天**的同花顺官方池，并标明「同花顺官方池」。
- 今天池不在磁盘上时，继续用现有盘中近似，绝不拿昨天官方池家数冒充今天。
- 收盘后正式日 `kline_daily_enriched` 仍优先；官方池不覆盖收盘口径。
- 本轮不自动同步官方池，也不外连。

#### GitHub 情报与固定上游点

- 消费数据台 `4.17` / `D-R-04` 的本地 canary 分区。本轮没有新增 GitHub 审阅。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/Dashboard.tsx`、`frontend/src/lib/api.ts`。`limit.source=hithink_official_pool` 时蓝条和 KPI/梯队写官方池，来源追踪指向 `hithink_limit_pool`。
- 数据台装配见数据平台开发日志 `4.17` 2026-08-26 同日只读消费。

#### 自动检查与构建

- 后端 overview + HiThink 同日门：`test_market_overview_as_of.py` + `test_hithink_finance.py` + `test_intraday_overview.py` 22 passed。
- 前端 `Dashboard.multiuser.test.tsx`：6 passed，含官方池文案。

#### 当前状态与用户验收

- 当前状态：`implemented`。今天本地还没有 `date=2026-08-26` 官方池，刷新后涨停 KPI 仍应是盘中近似，不应出现昨天的 65 家。数据页显式同步今天池之后，才会改标「同花顺官方池」。

### dashboard_intraday_approx_indicators

#### 用户目标与可见结果

- 交易日打开首页时，趋势强度、涨停梯队、炸板、量比不再显示成 0 / 1.00。能现算的显示盘中近似数；还没就绪的显示 — 或「盘后计算」，不再用 0 / 1.00 / 50% 填空。
- 蓝条写明这些是「盘中近似」，不是收盘后正式口径。趋势卡片在均线就绪时提示「现价对昨日均线」，未就绪时写「盘后计算」；涨停梯队带「盘中近似」；高低比在新高/新低都没有时显示 —，正式日也一样。
- 情绪雷达只平均已就绪维度。量能/投机未就绪时轴上标 —，标题写「盘中部分维度不可用」，角标带「部分」。
- 点回历史正式日仍走原来的收盘计算。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。不接 HiThink 官方池，不灌桌面 20G。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/Dashboard.tsx`、`frontend/src/lib/api.ts`。
- 数据台装配：`GET /api/overview/market` 在 `data_mode=intraday_snapshot` 时返回 `indicators_source=intraday_approx`。实现见数据平台开发日志 `4.1` 2026-08-26 条。

#### 自动检查与构建

- 后端 `tests/test_intraday_overview.py` + `tests/test_market_overview_as_of.py`：10 passed；缺数量比不进雷达、封板率空态为 null。
- 前端 `frontend/src/pages/__tests__/Dashboard.multiuser.test.tsx` + `pageContext.test.ts`：11 passed；未就绪维度显示 — /「盘后计算」，不把缺数量比写成 1.00。

#### 当前状态与用户验收

- 当前状态：`implemented`。请刷新已登录首页 `http://127.0.0.1:3011/`：能近似的看数，不能近似的应是 — /「盘后计算」/「盘中部分维度不可用」，不要再看到假 0 或 1.00。Cursor 内置浏览器本轮如未登录，不算已登录主路径验收。

### industry_fundflow_short_window_ranking

#### 用户目标与可见结果

- 行业主力资金流向默认「5 天」，按近 5 个交易日累计排名；「半个月」10 日，「1 个月」21 日。
- 文案写明「近N个交易日累计」，缺日线行业可见，不当成 0。
- 选「1 个季度 / 半年 / 1 年」不再用 63 天残缺日线假装完整窗口，回到当日快照并标明窗口数据不足。
- 下载云仍看当日快照；概念面板仍是当日快照。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。只读现有 `ext_fund_flow_bk_daily`。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/components/SectorFundFlowPanel.tsx`。
- 只读接口：`GET /api/free/fund-flow/boards/window`。
- 测试：面板 4 项、后端窗口聚合 2 项。

#### 自动检查与构建

- `pnpm exec vitest run src/components/__tests__/SectorFundFlowPanel.history.test.tsx`：4 passed。
- 后端窗口聚合 2 项通过。
- `pnpm exec tsc -b`：通过。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。本轮不补 128 只 × 63 天，不补概念窗口。

### fundflow_window_half_month_not_week

#### 用户目标与可见结果

- 资金流时间窗取消「1 周」。
- 新选项是「半个月」，按 10 个交易日（两周）累计。
- 「1 天」按 1 个交易日，「5 天」按 5 个交易日，不再都映射成 5 天。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/components/SectorFundFlowPanel.tsx`。
- 测试：`frontend/src/components/__tests__/SectorFundFlowPanel.history.test.tsx`。

#### 自动检查与构建

- 待跑面板测试和 tsc。

#### 当前状态与用户验收

- 当前状态：`implemented`。

### industry_fundflow_window_ranking

#### 用户目标与可见结果

- 行业主力资金流向选「1 个季度」后，净流入/净流出 TOP 改为近 63 个交易日累计，不再展示当日快照（如通信设备 75.49 亿）。
- 副文案写明「近63个交易日累计」，并显示日线覆盖与窗口外数据缺口。
- 下载云仍刷新当日快照；概念面板本轮继续用当日快照，不改成季度累计。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/components/SectorFundFlowPanel.tsx`。
- 只读接口：`GET /api/free/fund-flow/boards/window`。
- 测试：`frontend/src/components/__tests__/SectorFundFlowPanel.history.test.tsx`。

#### 自动检查与构建

- `pnpm exec vitest run src/components/__tests__/SectorFundFlowPanel.history.test.tsx`：3 passed。
- `pnpm exec tsc -b`：通过。

#### Codex 内置浏览器目标运行面验证

- 本轮以自动检查和本地日线聚合为主。刷新行业面板后，1 个季度应显示窗口累计第一名，而不是当日通信设备 75.49 亿。当前磁盘覆盖 72/128，缺数可见。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 完整 128 只行业日线需管理员再点一次窗口回补；本轮已把回补范围改为当前快照全部行业。概念累计不在本轮。

### fundflow_backfill_banner_autodismiss

#### 用户目标与可见结果

- 行业/概念主力资金流向点近N日回补成功后，绿色「回补完成」条显示约 3 秒后自动消失，行为与旁边云端更新按钮一致。
- 失败提示仍保留，方便排查。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。只改用户台资金流面板提示。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/components/SectorFundFlowPanel.tsx`。
- 测试：`frontend/src/components/__tests__/SectorFundFlowPanel.history.test.tsx`。

#### 自动检查与构建

- `pnpm exec vitest run src/components/__tests__/SectorFundFlowPanel.history.test.tsx`：2 passed。
- `pnpm exec tsc -b`：通过。

#### Codex 内置浏览器目标运行面验证

- 代码层已覆盖 3 秒后成功条消失。页面上再点一次「1 天」回补即可看到同样效果。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 备份：`/Users/simon/备份/codex/20260821-134227-one-trading-fundflow-backfill-banner`。
- 回滚：把备份中的面板和测试复制回原路径。

### aihub_review_page_top_tabs

#### 用户目标与可见结果

- `/ai` 顶部标签在个股分析右侧补上「复盘」和「页面」，与功能目录、历史记录、个股分析同级。
- 点「复盘」只看已保存的大盘复盘；点「页面」只看各业务页保存的 AI 分析。
- 历史记录分类条不再重复「复盘 / 页面」；共享历史只留全部、财务、策略。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。只改用户台 AI 入口导航。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/AIHub.tsx`、`frontend/src/components/ai/AIHistorySection.tsx`。
- 测试：`frontend/src/pages/__tests__/AIHub.test.tsx`。
- URL：`/ai?tab=review`、`/ai?tab=page`。

#### 自动检查与构建

- `pnpm exec vitest run src/pages/__tests__/AIHub.test.tsx`：11 passed。
- `pnpm exec tsc -b`：通过。

#### Codex 内置浏览器目标运行面验证

- 本轮以自动检查为主。刷新 `/ai` 后，顶部应出现五个标签；点「复盘」「页面」分别进入对应历史，不再从历史记录分类条进入。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 回滚恢复上述三个文件和本日志即可。

### aihub_stock_top_tab

#### 用户目标与可见结果

- `/ai` 顶部三个标签：功能目录、历史记录、个股分析。
- 个股不再放在历史记录的分类条里；历史记录只保留财务/复盘/策略/页面。
- 点「个股分析」只显示每只股票一张卡，点击进入该股完整历史。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。只改用户台 AI 入口导航。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/AIHub.tsx`、`frontend/src/components/ai/AIHistorySection.tsx`。
- 测试：`frontend/src/pages/__tests__/AIHub.test.tsx`。
- URL：`/ai?tab=stock` 打开个股分析标签。

#### 自动检查与构建

- `pnpm exec vitest run src/pages/__tests__/AIHub.test.tsx`：8 passed。
- `pnpm exec tsc -b`：通过。

#### Codex 内置浏览器目标运行面验证

- 已登录打开 `/ai`。顶部标签为「功能目录 / 历史记录 / 个股分析」。历史记录分类只剩全部/财务/复盘/策略/页面，没有个股，也没有罗曼股份卡。点「个股分析」后 URL 为 `/ai?tab=stock`，罗曼股份等 10 只股票各一张卡。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 备份：`/Users/simon/备份/codex/20260821-101234-one-trading-aihub-stock-tab`。
- 回滚：把备份中的三个文件复制回原路径。

### aihub_catalog_history_tabs

#### 用户目标与可见结果

- `/ai` 用「功能目录 / 历史记录」两个标签切换，不再把目录和历史叠在同一屏。
- 默认仍是功能目录；`/ai?tab=history` 直接打开历史。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。只改用户台 AI 入口布局。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/AIHub.tsx`，历史区仍用 `AIHistorySection`。
- 测试：`frontend/src/pages/__tests__/AIHub.test.tsx`。

#### 自动检查与构建

- `pnpm exec vitest run src/pages/__tests__/AIHub.test.tsx`：7 passed。
- `pnpm exec tsc -b`：通过。

#### Codex 内置浏览器目标运行面验证

- 已登录打开 `/ai`：默认「功能目录」选中，页面有 Hermes/个股分析卡，没有历史区说明。点「历史记录」后 URL 变为 `/ai?tab=history`，功能卡消失，只显示历史记录。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 备份：`/Users/simon/备份/codex/20260821-095801-one-trading-aihub-catalog-history-tabs`。
- 回滚：把备份中的 `AIHub.tsx` 和测试复制回原路径。

### ai_history_group_stock_cards

#### 用户目标与可见结果

- AI 功能目录「历史记录」里的个股，同一只股票只显示一张卡。
- 点击进入该股完整历史分析工作区，而不是每份报告一张卡。
- 个股计数按股票数，多份报告会提示「共 N 份历史分析」。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。只改用户台 AI 历史记录列表。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/components/ai/AIHistorySection.tsx`。
- 测试：`frontend/src/pages/__tests__/AIHub.test.tsx`。
- 点击仍进入既有 `/stock-analysis?symbol=&report=` 左右栏历史工作区。

#### 自动检查与构建

- `pnpm exec vitest run src/pages/__tests__/AIHub.test.tsx`：6 passed。
- `pnpm exec tsc -b`：通过。

#### Codex 内置浏览器目标运行面验证

- 已登录打开 `/ai` 并筛选「个股」。计数从 17 份报告变为 10 只股票；罗曼股份只出现一张卡，文案为「共 3 份历史分析」，点击进入 `/stock-analysis?symbol=605289.SH&report=...`。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 备份：`/Users/simon/备份/codex/20260821-092818-one-trading-ai-history-stock-cards`。
- 回滚：把备份中的 `AIHistorySection.tsx` 和 `AIHub.test.tsx` 复制回原路径。

### stock_analysis_history_workspace

#### 用户目标与可见结果

- 个股分析点「历史报告」后，左侧显示该股票完整分析正文，右侧是同一股票的历史列表，布局对齐复盘页。
- 点最近查看里的某份报告，或带 `report=` 深链进入，都留在这个工作区看全文，不再弹独立对话框。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。只改用户台个股分析历史入口。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/StockAnalysis.tsx`。
- 测试：`frontend/src/pages/__tests__/StockAnalysis.test.tsx`。

#### 自动检查与构建

- `pnpm exec vitest run src/pages/__tests__/StockAnalysis.test.tsx`：7 passed。
- `pnpm exec tsc -b`：通过。

#### Codex 内置浏览器目标运行面验证

- 已登录打开 `/stock-analysis?symbol=605289.SH&report=...`。左侧显示罗曼股份完整分析正文，右侧为「历史分析」列表，标题为「历史分析 · 罗曼股份 · 1 天前」。

#### 当前状态与用户验收

- 当前状态：`implemented`。请先看效果。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 备份：`/Users/simon/备份/codex/20260821-092007-one-trading-stock-analysis-history-layout`。
- 回滚：把备份中的 `StockAnalysis.tsx` 和测试复制回原路径。

### market_pulse_label_every_event_dot

#### 用户目标与可见结果

- 市场脉搏图上每个红/绿异动点都带板块名，不再只显示圆点。
- 同一分钟多个板块会写成 `A / B`，超过两个显示 `A / B +N`。相邻点标签上下错开。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。只改用户台图表标签策略。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/components/MarketPulsePanel.tsx`。
- 测试：`frontend/src/components/__tests__/MarketPulsePanel.test.tsx`。

#### 自动检查与构建

- `pnpm exec vitest run src/components/__tests__/MarketPulsePanel.test.tsx`：5 passed。
- `pnpm exec tsc -b`：通过。

#### Codex 内置浏览器目标运行面验证

- 代码层已覆盖两个靠近的红点都会带 `影视` / `航运` 标签。请刷新首页确认原先无名字的红点已有板块名。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 备份：`/Users/simon/备份/codex/20260820-152221-one-trading-market-pulse-event-labels`。
- 回滚：把备份中的 `MarketPulsePanel.tsx` 和测试复制回原路径。

### market_pulse_hide_write_banner_and_fix_markers

#### 用户目标与可见结果

- 看板市场脉搏点「更新」后，不再常驻显示“已写入 N 个分钟点和 N 条板块事件”。
- 板块异动标记固定为圆点，不再被拉成胶囊/横条；更新按钮改回云下载图标。
- 数据页同步卡的写入回执不动。

#### GitHub 情报与固定上游点

- 对照本地 go-stock `AnalyzeMartket.vue` 的 scatter `symbol: circle`，只借鉴标记形态，不引入其 Runtime。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/components/MarketPulsePanel.tsx`。
- 测试：`frontend/src/components/__tests__/MarketPulsePanel.test.tsx`。

#### 自动检查与构建

- `pnpm exec vitest run src/components/__tests__/MarketPulsePanel.test.tsx`：4 passed。
- `pnpm exec tsc -b`：通过。

#### Codex 内置浏览器目标运行面验证

- 已登录打开 `http://127.0.0.1:3011/`。市场脉搏区域无“已写入 N 个分钟点”条；241 分钟 / 21 条事件仍在。异动 scatter 已固定 `symbol: circle`，空标签不再画底框。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 备份：`/Users/simon/备份/codex/20260820-151759-one-trading-market-pulse-icons-banner`。
- 回滚：把备份中的 `MarketPulsePanel.tsx` 和测试复制回原路径。

### dashboard_align_breadth_radar_trend_heights

#### 用户目标与可见结果

- 「涨跌分布 / 广度」「情绪雷达」「趋势强度」三张卡片在宽屏下同高，按趋势强度那一列对齐。
- 不改数据口径，只改用户台卡片拉伸。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/Dashboard.tsx`。
- 测试：`frontend/src/pages/__tests__/Dashboard.multiuser.test.tsx`。

#### 自动检查与构建

- `pnpm exec vitest run src/pages/__tests__/Dashboard.multiuser.test.tsx`：3 passed。
- `pnpm exec tsc -b`：通过。

#### Codex 内置浏览器目标运行面验证

- 已登录打开 `http://127.0.0.1:3011/`。宽屏下「涨跌分布 / 广度」「情绪雷达」「趋势强度」三张卡片高度均为 339px。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 备份：`/Users/simon/备份/codex/20260820-150207-one-trading-dashboard-module-heights`。
- 回滚：把备份中的 `Dashboard.tsx` 复制回原路径。

### dashboard_sealed_correction_popover

#### 用户目标与可见结果

- 市场看板「涨停 / 跌停」点开黄色「修正/降级」后，说明弹层不再被 KPI 卡片裁切，也不会盖住 0/0 和封板率。
- 盘中 0/0 仍按现有快照口径：均线/涨停梯队未就绪时先降级，不在本轮改数据台计数。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目。复用用户台已有 `WarmupBadge` 的 portal 气泡做法。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/components/SealedBadge.tsx`、`frontend/src/pages/Dashboard.tsx`。
- 测试：`frontend/src/pages/__tests__/Dashboard.multiuser.test.tsx`。
- 跨台边界：只改用户台弹层定位；不改 `market_overview_builder` 的盘中涨停置零口径。

#### 自动检查与构建

- `pnpm exec vitest run src/pages/__tests__/Dashboard.multiuser.test.tsx`：2 passed。
- `pnpm exec tsc -b`：通过。

#### Codex 内置浏览器目标运行面验证

- 已登录打开 `http://127.0.0.1:3011/`。点「修正」后弹层完整显示「五档盘口修正结果」，与 KPI 卡片水平间距 12px，不再重叠；卡片仍可见 `0 / 0` 和封板率 0%。
- 盘中 0/0 仍是快照口径，本轮未改数据台计数。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 备份：`/Users/simon/备份/codex/20260820-120218-one-trading-dashboard-sealed-popover`。
- 回滚：把备份中的 `SealedBadge.tsx`、`Dashboard.tsx` 复制回原路径。

### page_embedded_hermes_limit_concept_20260819

#### 用户目标与可见结果

- 在「连板梯队」「概念分析」「行业分析」和「市场看板」右下角放同一套圆形 AI 按钮；点击后打开嵌入 Hermes，不离开当前页。
- Agent 读取当前页结构化快照（筛选、日期、可见梯队/概念和前 N 条），不是整页 HTML 或截图。
- 其他未登记快照的页面先不显示这个入口；`/login`、`/onboarding`、`/ai/hermes` 也不显示。

#### GitHub 情报与固定上游点

- 按钮视觉来自 session `019ff1cc-e77e-7a91-994b-bbc00dc82dec` 的对话光圈稿，本轮重绘为 SVG，不引用生成 PNG。
- 不移植 AHGGG/dsh-side-chat Runtime；仍走现有 `/api/hermes-agent/*`。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/lib/pageContext.ts`、`pageContextSnapshots.ts`、`components/AiMark.tsx`、`components/HermesPageAgentHost.tsx`、`Layout.tsx`。
- 页面登记：`pages/LimitUpLadder.tsx`、`pages/ConceptAnalysis.tsx`、`pages/IndustryAnalysis.tsx`、`pages/Dashboard.tsx`。
- 嵌入对话：`pages/HermesAgentChat.tsx` 增加 `embedded`，发送时附带 `composePageContextMessage()`；气泡只显示用户原话或「请阅读当前{页面}」。
- Agent 台消费：现有 Hermes Adapter + `one_trading_data_query`（`limit_ladder` / `fund_flow_concepts`）。本轮不改后端 Runtime。

#### 自动检查与构建

- `pnpm exec vitest run`：pageContext 2、HermesPageAgentHost 3、HermesAgentChat 19、Layout.mobile 10，共 34 passed。
- `pnpm exec tsc -b`：本轮目标文件无新增错误。

#### Codex 内置浏览器目标运行面验证

- 打开 `http://127.0.0.1:3011/limit-ladder` 被重定向到 `/login?redirect=%2Flimit-ladder`。内置浏览器无已登录会话，未代替用户登录，因此未看到右下角按钮和嵌入面板。
- 前端 3011、后端 3018 当时在听；`/api/healthz` 返回 401「未登录或会话已过期」。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `verified` / `accepted`。请在已登录的 `http://127.0.0.1:3011/limit-ladder`、`/concept-analysis`、`/industry-analysis` 和 `/` 看右下角按钮，点开后确认快照标题，再发一条空消息或问题。

#### 阻塞、回滚和下一步

- 回滚：移除 `HermesPageAgentHost` / `AiMark` / `pageContext*`，并还原 `Layout.tsx`、`HermesAgentChat.tsx`、连板和概念页的登记 effect。
- 下一步：用户登录后验收四页入口和各自快照；确认后再扩展到其余业务页。

### upstream_capability_sync_20260818

#### 用户目标与可见结果

- 把上次代码核对出的上游能力迁入本地开发版：市场环境、组合策略、截图导入自选、板块监控、分时穿越信号、扩展列格式化、Walk-forward、日 K 修复、企业微信机器人长连接。
- 用户可见入口：侧栏「市场环境」、数据页日 K 修复/市场环境配置、策略页「叠加策略」、自选「截图导入」、监控规则可选分时穿越信号、扩展列可配千分位/单位。

#### GitHub 情报与固定上游点

- 上游 [shy3130/tickflow-stock-panel](https://github.com/shy3130/tickflow-stock-panel) `main@e5b105dd451ac895a2ba54df9767b23afaa24ab6`，VERSION 仍为 v0.1.88。
- 本轮按文件迁入，没有整仓 merge/rebase。

#### 本地路由、Module、Adapter 与依赖接口

- 完整页面/模块：`frontend/src/pages/Regime.tsx`、`frontend/src/components/data/RegimeConfigCard.tsx`、`RepairDailyPanel.tsx`、`CompositeStrategyDialog.tsx`、`WatchlistImportDialog.tsx`、`backend/app/services/regime_builder.py`、`repair_daily.py`、`watchlist_ocr/`、`strategy/composite.py`、`strategy/intraday_signals.py`、`backtest/walkforward.py`、`wecom_bot_service.py`、`sector_monitor.py`。
- 已接线：`/regime`、`/api/regime/*`、`POST /api/data/repair-daily`、`POST /api/strategies/composite/save`、`/api/watchlist/ocr-status|import-image`、`POST /api/backtest/walkforward`、监控 options 增加分时信号、扩展列 `formatExtNumber`。
- 仍是适配而非上游全量：组合策略保存写入本地用户策略工作区，不等于上游 composite 引擎已完整执行；板块成员弹窗/监控目录未接到实时聚合主路径；Walk-forward 目前是折切分预览接口，不是完整 OOS 回测页；企微长连接已挂服务对象，设置页完整凭证 UI 未做。

#### 自动检查与构建

- 相关后端文件 `py_compile` 通过。
- 本轮改动前端文件 `tsc -b` 无新增报错。

#### Codex 内置浏览器目标运行面验证

- 本轮未用已登录会话逐项点击 9 个入口跑通外部 OCR/企微/全量 regime 回填。

#### 当前状态与用户验收

- 当前状态：`implemented`。

### ai_sector_rotation_analysis

#### 用户目标与可见结果

- 概念分析和行业分析的「涨幅RPS轮动」弹窗不再显示「开发中」，可点击「生成分析」流式生成 AI 轮动报告。
- 行业页新增同一入口，支持 1/2/3 级行业切换；概念页保持原矩阵和搜索。
- AI 目录新增「AI 板块轮动分析」，跳到概念分析页打开该能力。

#### GitHub 情报与固定上游点

- 上游：[shy3130/tickflow-stock-panel](https://github.com/shy3130/tickflow-stock-panel)。
- 功能首次落地：`255688f`（2026-07-02，当时 VERSION 仍是 v0.1.64）。
- 行业参数化：PR #162 / `c9f01ba`（2026-08-02）。
- 当前默认分支：`main@e5b105dd451ac895a2ba54df9767b23afaa24ab6`（2026-08-14）。VERSION 文件仍写 `v0.1.88`，与 2026-08-01 审阅点 `8ead300` 相比又超 27 个提交，但未打新 tag。

#### 本地路由、Module、Adapter 与依赖接口

- 界面：`frontend/src/components/RpsRotationDialog.tsx`、`frontend/src/pages/ConceptAnalysis.tsx`、`frontend/src/pages/IndustryAnalysis.tsx`、`frontend/src/pages/AIHub.tsx`。
- API：`GET /api/rps/rotation` 现支持 `kind/level`；新增流式 `POST /api/rps/rotation-analyze`。
- 后端：`backend/app/services/rps_rotation.py`、`backend/app/services/concept_rotation_analyzer.py`、`backend/app/api/rps.py`。
- 复用本地 `stream_ai_text`、`require_ai_http_access` 和大盘总览，不新建模型配置。

#### 自动检查与构建

- `backend/.venv/bin/pytest tests/test_concept_rotation_analyzer.py -q`：3 passed。
- `pnpm exec vitest run src/pages/__tests__/AIHub.test.tsx`：5 passed。
- `pnpm exec tsc -b`：本轮改动的 `api.ts` / `RpsRotationDialog.tsx` / `IndustryAnalysis.tsx` / `AIHub.tsx` 无新增 TypeScript 报错。

#### Codex 内置浏览器目标运行面验证

- 当前本地前端 `http://127.0.0.1:3011`（Vite PID 5638，cwd=`one-trading/frontend`）与后端 `3018` 在跑。未登录访问 `/api/rps/rotation` 和 `/api/rps/rotation-analyze` 均返回 401，与现有 AI 接口一致。本轮未用已登录会话在内置浏览器点击「生成分析」跑通模型输出。

#### 当前状态与用户验收

- 当前状态：`implemented`。

### hermes_reply_symbol_preview

#### 用户目标与可见结果

- Hermes 助手回复里的官方 A 股代码（如 `605289.SH`、`300750.SZ`）高亮后可点击。
- 点击打开现有 `StockPreviewDialog`，不是悬停弹出完整 K 线窗。
- 用户气泡保持纯文本；财务分析/复盘等未传入回调的页面不变。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目。复用用户台已有个股预览弹窗。

#### 本地路由、Module、Adapter 与依赖接口

- 界面 Module：`frontend/src/components/financials/MarkdownRenderer.tsx`、`frontend/src/pages/HermesAgentChat.tsx`。
- 复用：`frontend/src/components/StockPreviewDialog.tsx`。
- 测试：`frontend/src/pages/__tests__/HermesAgentChat.test.tsx`。
- 跨台边界：只改用户台对话框。不改数据台、Hermes Runtime、Skill 或消息存储。

#### 自动检查与构建

- `pnpm exec vitest run src/pages/__tests__/HermesAgentChat.test.tsx`：17 项通过。
- `pnpm exec tsc -b`：TypeScript 项目检查通过。

#### Codex 内置浏览器目标运行面验证

- 本轮未做已登录浏览器验收；自动测试覆盖助手回复中的代码按钮会打开预览，用户气泡不会变成按钮。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。请在已登录 Hermes 对话里点助手回复中的 `605289.SH` 一类代码，确认打开现有个股预览。

#### 阻塞、回滚和下一步

- 备份：`/Users/simon/备份/codex/20260818-131153-one-trading-hermes-symbol-preview`。
- 回滚只需恢复 `MarkdownRenderer.tsx`、`HermesAgentChat.tsx`、对应测试和本日志；不会改动 Hermes Session 或长期记忆。
- 下一步可做悬停小卡；不要把完整 K 线窗绑到 mouseenter。

### hermes_chat_chart_render

#### 用户目标与可见结果

- Hermes 助手回复里的受控 `type: "chart"` 块不再只显示占位，有数值点时用 echarts 画成真图。
- 没有可绘制数据时诚实说明，不编造图形，也不渲染任意 HTML 或图片。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目。继续只用用户台已有 echarts，不引入 Lieflat HTML 运行时。

#### 本地路由、Module、Adapter 与依赖接口

- 界面 Module：`frontend/src/components/HermesChartBlock.tsx`、`frontend/src/lib/hermesRichContent.ts`、`frontend/src/pages/HermesAgentChat.tsx`。
- 测试：`frontend/src/lib/__tests__/hermesRichContent.test.ts`、`frontend/src/pages/__tests__/HermesAgentChat.test.tsx`。
- 跨台边界：只改用户台渲染；不改数据台、Hermes Runtime、Skill 或消息存储协议。

#### 自动检查与构建

- `pnpm exec vitest run src/lib/__tests__/hermesRichContent.test.ts src/pages/__tests__/HermesAgentChat.test.tsx`：18 项通过。
- `pnpm exec tsc -b`：TypeScript 项目检查通过。

#### Codex 内置浏览器目标运行面验证

- 本轮未做已登录浏览器验收；自动测试覆盖图表容器出现且不再显示旧占位文案。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 备份：`/Users/simon/备份/codex/20260817-162842-one-trading-hermes-chart-render`。
- 回滚：把备份中的同名文件复制回原路径，并移除 `HermesChartBlock.tsx`。

### hermes_chat_markdown_renderer

#### 用户目标与可见结果

- Hermes 助手气泡不再把回复当成纯文本墙；标题、列表、表格、加粗按现有安全 Markdown 渲染。
- 识别约定的 chart JSON 块后，显示受控图表占位，不直接渲染 HTML 或图片。
- 用户自己的输入仍按纯文本显示。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目。图表占位沿用 Agent 台已有 Lieflat 约束：当前没有 Artifact renderer，不得开放任意 HTML。

#### 本地路由、Module、Adapter 与依赖接口

- 界面 Module：`frontend/src/pages/HermesAgentChat.tsx`、`frontend/src/lib/hermesRichContent.ts`。
- 复用：`frontend/src/components/financials/MarkdownRenderer.tsx`。
- 测试：`frontend/src/lib/__tests__/hermesRichContent.test.ts`、`frontend/src/pages/__tests__/HermesAgentChat.test.tsx`。
- 跨台边界：只改用户台渲染；不改 Hermes Runtime、Skill、数据台或消息存储。

#### 自动检查与构建

- `pnpm exec vitest run src/lib/__tests__/hermesRichContent.test.ts src/pages/__tests__/HermesAgentChat.test.tsx`：18 项通过。
- `pnpm exec tsc -b`：TypeScript 项目检查通过。

#### Codex 内置浏览器目标运行面验证

- 本轮未做已登录浏览器验收；自动测试覆盖 Markdown 标题渲染和图表占位。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 备份：`/Users/simon/备份/codex/20260817-155107-one-trading-hermes-chat-markdown`。
- 回滚：把备份中的 `HermesAgentChat.tsx` 与测试复制回原路径，并移除新增 `hermesRichContent` 文件即可。

### hermes_stock_context_prefill

#### 用户目标与可见结果

- 从自选详情进入 AI 功能目录后，Hermes Agent 对话卡也会显示当前股票，并带上 `symbol/name`。
- 进入 `/ai/hermes` 后，输入框预填“请分析 <名称> <代码>”，上方提示当前标的；不自动创建 Session，也不自动发送。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目。沿用 one-trading 既有 AI 股票上下文深链和 Hermes 只读数据视图。

#### 本地路由、Module、Adapter 与依赖接口

- 路由：`/ai?symbol=&name=` → `/ai/hermes?symbol=&name=`。
- 界面 Module：`frontend/src/pages/AIHub.tsx`、`frontend/src/pages/HermesAgentChat.tsx`。
- 测试：`frontend/src/pages/__tests__/AIHub.test.tsx`、`frontend/src/pages/__tests__/HermesAgentChat.test.tsx`。
- 跨台边界：只预填用户台输入框；不改 Hermes Runtime、Skill、长期记忆或数据台查询契约。

#### 自动检查与构建

- `pnpm exec vitest run src/pages/__tests__/AIHub.test.tsx src/pages/__tests__/HermesAgentChat.test.tsx`：19 项通过。
- `pnpm exec tsc -b`：TypeScript 项目检查通过。

#### Codex 内置浏览器目标运行面验证

- 本轮未做已登录浏览器验收；自动测试覆盖预填且不发送。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 回滚方式：恢复 AIHub Hermes 文案排除，以及 Hermes 页对 URL 股票参数的读取与预填。

### admin_source_trace_panel_buttons

#### 用户目标与可见结果

- 管理员在用户台每个数据板块标题旁看到来源追踪图标，可进入 `/data?section=source-trace&trace=<subject_id>`，核对该板块对应的数据台对象和 GitHub 项目情报。
- 普通账户看不到该入口；数据页原有管理员「来源追踪」页保持不变。
- 本轮不改数据台 Provider、Adapter、物理数据或 provenance 契约，只复用现有只读 `/api/data/source-provenance`。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目。板块到 subject 的映射沿用数据台 `provenance_registry.py` 既有登记。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台 Module：`frontend/src/components/SourceTraceButton.tsx`、`frontend/src/lib/sourceTraceSubjects.ts`。
- 挂载面：概念/行业分析、资金流、热力图、看板、财务、自选、指数、连板梯队、选股、复盘、个股资金流、筹码、市场脉搏。
- 测试：`frontend/src/components/__tests__/SourceTraceButton.test.tsx`；既有 Data/Dashboard 多用户测试继续覆盖管理员边界。
- 跨台边界：只跳转到数据页来源追踪；不复制数据集生命周期，也不把 GitHub 仓库写成真实生产者。

#### 自动检查与构建

- `pnpm exec vitest run` 覆盖 SourceTraceButton、IndustryTreemap、MarketPulsePanel、Dashboard 多用户与 Data 页：25 项通过。
- `pnpm exec tsc -b`：TypeScript 项目检查通过。

#### Codex 内置浏览器目标运行面验证

- 本地前端 `http://127.0.0.1:3011` 与后端 `3018` 在跑，但当前无已登录管理员 cookie，无法在内置浏览器完成登录态截图。
- 管理员可见/普通用户不可见由组件测试与 Data/Dashboard 多用户测试覆盖；未把页面打开写成 `verified`。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `verified / accepted`。

#### 阻塞、回滚和下一步

- 回滚方式：移除 `SourceTraceButton` 挂载与新增文件即可，不影响数据台。

### source_trace_panel_position_swap

#### 用户目标与可见结果

- 在 `/data?section=source-trace` 中互换“同类替换候选”和“证据缺口与本地问题”的位置。
- 宽屏下，同类替换候选位于右侧上方；证据缺口与本地问题位于故障追踪链下方。
- 窄屏阅读顺序同步调整为“同类替换候选 -> 证据缺口与本地问题”。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目，只调整 one-trading 自有来源追踪界面。

#### 本地路由、Module、Adapter 与依赖接口

- 路由：`/data?section=source-trace&trace=<dataset_id>`。
- 界面 Module：`frontend/src/components/data/DataSourceTracePanel.tsx`。
- 测试：`frontend/src/pages/__tests__/Data.test.tsx`。
- 继续只读消费 `/api/data/source-provenance`；没有修改数据台 Provider、Adapter、目录状态或物理数据。

#### 自动检查与构建

- `npm run test:run -- src/pages/__tests__/Data.test.tsx`：14 项通过。
- `npm run build`：TypeScript 与 Vite 构建通过；保留既有动态导入和 bundle 大小提醒。

#### Codex 内置浏览器目标运行面验证

- 目标页面：`http://127.0.0.1:3011/data?section=source-trace&trace=stock_adj_factor`。
- 页面标题：`one-trading · Quant Terminal`。
- 1920 × 1080 下实测：同类替换候选位于右上区域；证据缺口与本地问题位于左侧故障链下方。
- 浏览器控制台没有本轮错误，仅有既存 React Router v7 future flag 提醒。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 用户已确认来源追踪整体界面可用；本次位置互换等待后续使用反馈，不标记 `accepted`。

#### 阻塞、回滚和下一步

- 无阻塞。
- 回滚方式：恢复 `DataSourceTracePanel.tsx` 中两个 section 的 DOM 顺序与 `xl/2xl` 网格位置类。

### source_trace_stock_daily_issue_cleared

#### 用户目标与可见结果

- 管理员打开 `/data?section=source-trace&trace=stock_daily` 时，不再因为最近一次目录扫描降级而看到“未记录错误详情”或 legacy lineage 黄条。
- 本轮没有改来源追踪界面、过滤规则或前端文案；黄条消失是因为数据台把 `stock_daily` 最近一次 `catalog_rescan` 收成 `succeeded / healthy`，`issues=[]`。

#### 跨台依赖

- 数据事实、lineage 补写和扫描规则只见 `/Users/simon/Trading/one-trading/docs/data-platform-development-log.md` 的 2026-08-17 三条。
- 用户台继续只读 `/api/data/source-provenance`。

#### 当前状态与用户验收

- 当前状态：`implemented`。本轮未重新做 Codex 内置浏览器截图，因此不把页面打开写成 `verified`。
- 不把数据台目录扫描 healthy 写成用户台 `accepted`。

#### 阻塞、回滚和下一步

- 回滚数据台当前 lineage / 扫描规则后，这张黄条会按证据再次出现；用户台无需单独回滚。

### watchlist_detail_to_stock_analysis

#### 用户目标与可见结果

- 在自选股详情弹窗顶栏的股票代码和名称后增加“AI 分析”按钮。
- 点击后进入“个股分析”，并自动选中、加载当前详情股票；不需要用户再次搜索。
- 入口只在自选股打开的详情弹窗显示，其他复用同一弹窗的页面保持原样。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目，只补齐 one-trading 既有自选股与个股分析页面之间的用户流程。

#### 本地路由、Module、Adapter 与依赖接口

- 来源路由：`/watchlist`；目标路由：`/stock-analysis?symbol=<symbol>&name=<name>`。
- 界面 Module：`frontend/src/components/StockPreviewDialog.tsx`、`frontend/src/pages/Watchlist.tsx`、`frontend/src/pages/StockAnalysis.tsx`。
- 行为测试：`frontend/src/components/__tests__/StockPreviewDialog.test.tsx`、`frontend/src/pages/__tests__/StockAnalysis.test.tsx`。
- 跨台边界：只通过现有前端路由参数交接股票代码和名称；没有修改数据台 Provider、API、物理数据或 Agent 后端。

#### 自动检查与构建

- 两个新增针对性测试共 2 项通过，覆盖详情入口参数和目标页 URL 自动选股，并验证显式 URL 股票优先于旧的本地记忆。
- 相关文件 ESLint 无错误；保留 `Watchlist.tsx` 两条既存 Hook 依赖警告，本轮未扩大范围处理。
- `pnpm build`：TypeScript 与 Vite 生产构建通过；保留既有动态导入和 bundle 大小提醒。
- 独立只读审查未发现正确性、路由、Hook、作用域泄漏、可访问性或回归问题。

#### Codex 内置浏览器目标运行面验证

- 目标运行面：`http://127.0.0.1:3011/watchlist`，页面标题为 `one-trading · Quant Terminal`。
- 实测打开 `300204.SZ 舒泰神` 详情后，顶栏代码和名称后显示“AI 分析”按钮。
- 实测点击后进入 `/stock-analysis?symbol=300204.SZ&name=%E8%88%92%E6%B3%B0%E7%A5%9E`，页面自动显示 `舒泰神 300204.SZ` 并加载 167 个交易日及关键价位。
- 控制台没有本轮功能相关错误，仅有既存 React Router v7 future flag 提醒。

#### 当前状态与用户验收

- 当前状态：`superseded`。
- 此前“从自选股详情直接携带股票参数进入个股分析”的版本已经完成验证；后续按用户要求改为先进入 AI 功能目录，由下方 `watchlist_detail_to_ai_hub` 取代。

#### 阻塞、回滚和下一步

- 无阻塞。
- 回滚方式：移除 Watchlist 传入的 `showAnalysisAction`、详情弹窗中的可选 Link，以及 `StockAnalysis.tsx` 的 URL 参数同步逻辑；不涉及持久数据回滚。

### watchlist_detail_to_ai_hub

#### 用户目标与可见结果

- 保留自选股详情弹窗顶栏的“AI 分析”按钮，但把目标从某只股票的个股分析页改为左侧主导航的 AI 板块。
- 点击后直接进入 `/ai` 的“AI 功能目录”，不携带 `symbol`、`name` 等当前 AI 目录不会消费的股票参数。
- 入口仍只在自选股打开的详情弹窗显示，其他复用该弹窗的页面不受影响。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目，只调整 one-trading 既有页面之间的前端路由。

#### 本地路由、Module、Adapter 与依赖接口

- 来源路由：`/watchlist`；目标路由：`/ai`。
- 界面 Module：`frontend/src/components/StockPreviewDialog.tsx`；目标页面继续复用 `frontend/src/pages/AIHub.tsx`。
- 行为测试：`frontend/src/components/__tests__/StockPreviewDialog.test.tsx`。
- 本轮没有修改数据台 Provider、API、物理数据或 Agent 后端；AI 功能目录内部各能力卡的既有目标保持不变。

#### 自动检查与构建

- `pnpm test:run src/components/__tests__/StockPreviewDialog.test.tsx`：1 项通过，覆盖按钮进入纯 `/ai` 路由。
- 相关组件与测试 ESLint 通过。
- `pnpm build`：TypeScript 与 Vite 生产构建通过；保留既有动态导入和 bundle 大小提醒。

#### Codex 内置浏览器目标运行面验证

- 目标运行面：`http://127.0.0.1:3011/watchlist`，页面标题为 `one-trading · Quant Terminal`。
- 实测打开 `300204.SZ 舒泰神` 详情，按钮链接为 `/ai`；点击后 URL 为 `http://127.0.0.1:3011/ai`，页面显示“AI 功能目录”。
- 左侧唯一 `AI` 导航项带 `aria-current="page"` 并显示激活样式。
- 控制台没有本轮功能错误，仅有既存 React Router v7 future flag 提醒。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 自动测试、静态检查、生产构建和实际浏览器点击主路径均已验证；等待用户实际使用确认后再标记 `accepted`。

#### 阻塞、回滚和下一步

- 无阻塞。
- 回滚方式：将 `StockPreviewDialog.tsx` 的按钮目标恢复为原来的个股分析深链，并恢复对应路由测试；不涉及持久数据回滚。

### stock_analysis_chip_and_fund_flow_rail

#### 用户目标与可见结果

- 在“个股分析”每一只已选股票的关键价位图右侧增加纵向辅助分析栏。
- 上方固定显示本地日 K 推算的筹码分布；下方显示单股主力资金方向、最新主力净流入、主力净占比、近 5 日与近 20 日累计及趋势图。
- 宽屏使用原右侧空白区域，窄屏时两张卡自动移动到关键价位图下方。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目；复用 one-trading 已有筹码与东财公开单股资金流链路。

#### 本地路由、Module、Adapter 与依赖接口

- 路由：`/stock-analysis?symbol=<symbol>&name=<name>`。
- 页面 Module：`frontend/src/pages/StockAnalysis.tsx`。
- 复用筹码 Module：`frontend/src/components/ChipDistributionPanel.tsx`。
- 新增资金 Module：`frontend/src/components/stock-analysis/StockFundFlowPanel.tsx`。
- 测试：`frontend/src/components/stock-analysis/__tests__/StockFundFlowPanel.test.tsx`，并回归 `StockAnalysis.test.tsx`、`StockPreviewDialog.test.tsx`。
- 数据依赖：只读使用现有 `/api/free/chips/{symbol}` 与 `/api/free/fund-flow/stock/{symbol}`；资金流外部刷新继续通过既有 POST，由用户明确点击触发。本轮没有修改后端 Provider、API 或数据文件。

#### 自动检查与构建

- 3 个相关测试文件共 6 项通过，覆盖资金正常态、空缓存显式获取、刷新失败仍保留缓存分析、可见 24 日累计基线和既有跳转行为。
- 相关文件 ESLint 通过；TypeScript project build 通过。
- `pnpm build`：Vite 生产构建通过；保留既有动态导入和 bundle 大小提醒。
- 独立只读审查发现并推动修复“已有缓存刷新失败静默”和“累计线包含不可见历史区间”两项问题；复审确认已解决且无新增阻塞。

#### Codex 内置浏览器目标运行面验证

- 目标页面：`http://127.0.0.1:3011/stock-analysis?symbol=300204.SZ&name=%E8%88%92%E6%B3%B0%E7%A5%9E`，标题为 `one-trading · Quant Terminal`。
- `1280 × 720` CSS 视口实测：关键价位图保持主视觉，右上筹码卡完整显示均成本、获利/套牢盘、70%/90% 成本区和筹码峰；右下资金卡完整显示当前无缓存空态和显式获取入口。
- 当前 `300204.SZ` 筹码数据正常；单股资金缓存为空，没有为了验证自动外连和写入数据。正常资金数据态通过固定样本组件测试验证。
- 浏览器控制台没有本轮功能错误，仅有既存 React Router v7 future flag 提醒。
- 设计 QA：`/Users/simon/Trading/one-trading/design-qa.md`，结论 `passed`。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 代码、自动检查、生产构建和真实页面主路径已验证；等待用户使用确认后再标记 `accepted`。

#### 2026-08-04 资金流数据源断连修复复核

- 本次后续问题属于数据台 Provider 可用性，不是资金卡片渲染或 3011 代理错误；完整实现、来源、备份和 Parquet 核对见 `docs/data-platform-development-log.md` 的 `4.7 ext_fund_flow_stock`。
- Codex 内置浏览器在 `000636.SZ 风华高科` 页面复测：缓存自动显示，点击“更新”成功，卡片显示最新 `08-03`、`+3.54亿`、`+3.85%` 与“东财公开资金流 · 单位元”，没有再出现英文断连提示，控制台无本次错误。
- 用户台交互契约保持不变：GET 只读本地缓存，外部刷新继续要求用户显式点击；没有新增页面自动外连或自动写入。

#### 阻塞、回滚和下一步

- 无阻塞。
- 资金流数据为空时需要用户点击“获取资金流”，这是避免浏览页面自动外连并写入本地缓存的刻意边界。
- 回滚方式：从 `StockAnalysis.tsx` 移除右侧 grid、`ChipDistributionPanel` 和 `StockFundFlowPanel`，删除新增资金组件与对应测试；不涉及持久数据回滚。

### stock_analysis_resizable_auxiliary_rail

#### 用户目标与可见结果

- 在个股分析主图与右侧“筹码分布 / 资金分析”之间增加竖向拖拽分隔条。
- 宽屏下向左拖动可加宽辅助栏，向右拖动可缩窄辅助栏，主图同步获得或让出空间；默认宽度保持原来的 296px。
- 右栏安全范围为 280–520px，并根据当前容器宽度动态收紧上限，至少为主图保留 640px；窄屏继续沿用原来的上下布局，不显示分隔条。
- 分隔条支持左右方向键微调、`Shift` 加速、`Home / End` 到达边界，以及双击恢复默认宽度。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目，只增强 one-trading 既有个股分析双栏布局。

#### 本地路由、Module、Adapter 与依赖接口

- 路由：`/stock-analysis?symbol=<symbol>&name=<name>`。
- 新增布局 Module：`frontend/src/components/stock-analysis/ResizableAnalysisLayout.tsx`。
- 页面接入：`frontend/src/pages/StockAnalysis.tsx`。
- 主图适配：`frontend/src/components/stock-analysis/AnalysisKChart.tsx` 增加容器 `ResizeObserver`；筹码图和资金图继续使用各自既有尺寸观察器。
- 行为测试：`frontend/src/components/stock-analysis/__tests__/ResizableAnalysisLayout.test.tsx`。
- 本轮没有修改数据台、Agent 后端、资金接口、筹码算法或本地缓存，也没有为栏宽增加持久化副作用。

#### 自动检查与构建

- 相关 3 个测试文件共 9 项通过，覆盖指针拖动、键盘调整、最小/最大宽度、容器动态上限、双击复位、资金卡和既有个股分析深链。
- 相关文件 ESLint 无错误；保留 `AnalysisKChart.tsx` 一条既有 Hook 依赖 warning。
- `pnpm build`：TypeScript 与 Vite 生产构建通过；保留既有动态导入和 bundle 大小提醒。
- 独立只读复核推动补齐指针捕获、焦点恢复、真实容器 clamp 测试与右栏 `min-w-0`，复审后无阻塞问题。

#### Codex 内置浏览器目标运行面验证

- 目标页面：`http://127.0.0.1:3011/stock-analysis?symbol=300274.SZ&name=%E9%98%B3%E5%85%89%E7%94%B5%E6%BA%90`；页面标题为 `one-trading · Quant Terminal`，Vite PID `44962`。
- 当前目标视口的动态范围为 280–336px：实测从默认 296px 向左拖至 336px、再向右拖至 280px，主图区宽度同步在 680px、640px、696px 间变化。
- 主 K 线画布和筹码画布在拖动时同步 resize，没有残留旧画布宽度；方向键从 280px 调到 304px，双击恢复 296px。
- 资金流仍保持既有按需缓存空态，没有为了界面验证触发外部获取或本地写入。
- 控制台没有本轮功能错误，仅有既存 React Router v7 future flag 提醒。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 自动测试、静态检查、生产构建和真实浏览器拖窄/拖宽主路径均已验证；等待用户实际使用确认后再标记 `accepted`。

#### 阻塞、回滚和下一步

- 无阻塞。
- 回滚方式：将 `StockAnalysis.tsx` 恢复为固定 `18.5rem` 右栏布局，移除 `ResizableAnalysisLayout` 和对应测试，并撤销 `AnalysisKChart` 的容器尺寸观察器；不涉及持久数据回滚。

### ai_feature_hub

#### 用户目标与可见结果

- 左侧主导航在“看板”后新增独立 `AI` 板块；点击进入 `/ai` 功能总览。
- 页面只归纳代码中真正调用统一 AI Provider 的四项能力：AI 个股分析、AI 财务分析、AI 大盘复盘、AI 策略生成。
- 每张卡进入原有工作位置；AI 策略生成使用 `/screener?ai=builder` 一次性深链，进入策略页后直接打开 AI 创建器并清理 URL 参数。
- 原有“策略、个股分析、财务分析、复盘”业务入口继续保留，避免把同一页面中的非 AI 能力一起隐藏到 AI 分类；概念、行业、扩展分析和回测因没有模型调用而明确排除。

#### GitHub 情报与固定上游点

- 上游实时固定点：`shy3130/tickflow-stock-panel main@8ead30037a8806518e400dc26b67a7e5a1294282` / `v0.1.88`，审阅日期 `2026-08-01`；完整审阅范围和 URL 见 `/Users/simon/Trading/用户台GitHub项目借鉴记录.md`。
- 本地固定点：`main@56d481076c008efca9ff40db8f5c89139bb7f600`；共同基点后本地 51 个独有提交、上游 253 个独有提交，且当前工作树另有既存未提交内容。
- 本轮没有 fetch、merge、rebase 或替换本地导航；上游更新与本地 AI 目录实现保持两条证据链。

#### 本地路由、Module、Adapter 与依赖接口

- 新路由与页面：`/ai`、`frontend/src/pages/AIHub.tsx`、`frontend/src/router.tsx`。
- 桌面/移动导航：`frontend/src/components/Layout.tsx`；菜单排序与隐藏：`frontend/src/pages/settings/MenuSettings.tsx`。
- 策略深链：`frontend/src/pages/Screener.tsx`，只负责打开既有 `StrategyBuilderDialog`，没有触发生成或保存。
- 跳转目标：`/stock-analysis`、`/financials`、`/review`、`/screener?ai=builder`；模型配置仍在 `/settings?tab=ai`。
- 跨台依赖：统一 AI Provider 和各分析服务属于 Agent 台；日 K、财务与市场/指数数据属于数据台。本轮只改用户台导航和轻量路由 seam，没有修改 Provider、模型 Adapter、API、数据文件或策略保存逻辑。

#### 自动检查与构建

- `pnpm test:run src/pages/__tests__/AIHub.test.tsx src/components/__tests__/Layout.mobile.test.tsx`：2 个文件、8 项测试全部通过。
- 相关文件 ESLint：0 error；保留 `Screener.tsx` 两条既存 Hook 依赖 warning，本轮没有新增 lint error。
- `pnpm build`：TypeScript 与 Vite 生产构建通过；保留既有 `api.ts` 动静态混合导入和大 bundle 提醒。

#### Codex 内置浏览器目标运行面验证

- 目标运行面：`http://127.0.0.1:3011/ai`；Vite PID `44962`，启动时间 `2026-07-30 13:01:07 +0800`，页面标题 `one-trading · Quant Terminal`，dev server 已加载本轮源码。
- 桌面实测：侧栏显示并高亮 `AI`；总览页显示四张能力卡和 `AI 配置` 入口，排除项说明可见。
- 主路径实测：四张卡分别到达 `/stock-analysis`、`/financials`、`/review` 和 `/screener`；策略卡进入后 `AI 生成` tab 与策略名称输入框可见，URL 一次性参数已清理。
- 移动端 `390 × 844` 实测：抽屉菜单存在唯一 `AI` 入口，点击后菜单关闭并返回 `/ai`；页面仍显示 AI 标题和功能卡。
- 控制台没有本轮 error；仅有既存 React Router v7 future flag warning。
- 为避免外部调用成本和持久写，本轮没有实际生成 AI 报告、没有调用模型，也没有保存 AI 策略文件；既有 AI 输出质量不在本条 `verified` 范围内。

#### 当前状态与用户验收

- 当前状态：`verified`（仅 AI 功能目录、导航和跳转范围）。
- 自动检查、构建、桌面与移动目标运行面已验证；等待用户使用确认后再标记 `accepted`。

#### 阻塞、回滚和下一步

- 无当前实现阻塞。
- 上游 `v0.1.88` 集成仍是独立高风险任务；必须先处理 51/253 分叉和既存脏工作树，不能从本条推导为“已同步上游”。
- 回滚方式：移除 `/ai` 路由和 `AIHub.tsx`、两处内置菜单条目、`Screener.tsx` 一次性深链 effect 及对应测试；不涉及数据或模型配置回滚。

### ai_saved_result_history

#### 用户目标与可见结果

- 在 `/ai` 功能目录下增加统一“历史记录”，集中展示已经保存的 AI 个股分析、AI 财务分析、AI 大盘复盘与 AI 策略，不把运行中任务、未保存草稿或普通本地分析混入。
- 历史记录按报告完成时间倒序显示，支持全部、个股、财务、复盘和策略分类；桌面为多列卡片，移动端为单列卡片。
- 每条记录可跳回原工作页面并恢复指定结果：个股、财务和复盘打开精确报告，AI 策略打开指定策略。
- 现有绿色“分析完成 / 点击查看”提示来自全局任务气泡，因挂在主布局中而会跨页面显示；本轮保留这个用于即时完成提醒的行为，历史记录负责长期回看，两者职责不同。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅；在既有 `ai_feature_hub` 本地能力目录上扩展已保存结果聚合与深链。

#### 本地路由、Module、Adapter 与依赖接口

- 历史聚合 Module：`frontend/src/components/ai/AIHistorySection.tsx`，由 `frontend/src/pages/AIHub.tsx` 挂载。
- 查询键：`frontend/src/lib/queryKeys.ts` 的 `QK.aiHistory`；每 10 秒只读刷新一次，单一来源失败时保留其他来源，四个来源全部失败时才显示整体错误。
- 复用既有只读接口：财务报告、个股报告、复盘报告和策略列表；策略仅保留 `source === 'ai'` 的已保存产物。本轮没有新增后端表、文件或重复保存一份报告正文。
- 精确深链：`/financials?symbol=...&name=...&report=...`、`/stock-analysis?symbol=...&name=...&report=...`、`/review?report=...`、`/screener?strategy=...`。
- 深链消费页面：`Financials.tsx`、`StockAnalysis.tsx`、`Review.tsx`、`Screener.tsx`。个股报告恢复由 `stockAnalysisStore.openHistoryReport()` 原子加载历史并打开目标报告，避免全局 Host 与页面订阅先后不一致时静默丢失弹窗。
- 跨台依赖：用户台只读汇总 Agent 台已经保存的输出；没有修改模型 Provider、分析生成流程、数据台 Provider 或物理数据。

#### 自动检查与构建

- `pnpm exec vitest run src/pages/__tests__/AIHub.test.tsx src/pages/__tests__/StockAnalysis.test.tsx --reporter=json`：2 个文件、5 项测试全部通过，覆盖四类聚合、排序、分类、空态、精确链接和个股历史恢复。
- `pnpm exec vitest run --reporter=json`：前端全量 23 个文件、62 项测试全部通过。
- 相关文件 ESLint：0 error；保留 `Review.tsx`、`Screener.tsx` 共 4 条既存 Hook 依赖 warning。
- `pnpm build`：TypeScript 与 Vite 生产构建通过；保留既有 `api.ts` 动静态混合导入和 bundle 大小提醒。

#### Codex 内置浏览器目标运行面验证

- 目标运行面：`http://127.0.0.1:3011/ai`，页面标题 `one-trading · Quant Terminal`；当前真实保存数据聚合为 7 条：个股 3、财务 1、复盘 3、AI 策略 0。
- 财务记录实测跳到盛新锂能指定报告并打开历史报告；个股记录实测跳到岱勒新材指定报告并打开“历史分析报告”；复盘记录实测跳到 `2026-07-31` 指定复盘并显示对应历史报告。
- 当前没有真实 AI 策略产物，因此未伪造数据做浏览器点击；固定样本测试覆盖策略历史条目的链接构造，目标页面消费逻辑通过类型检查与生产构建。
- `390 × 844` 实测功能卡和历史卡为单列布局，历史分类与记录仍可读取。
- 控制台无本轮 error，仅有既存 React Router v7 future flag warning。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 代码、全量自动测试、生产构建、桌面三类真实历史恢复和移动端布局均已验证；等待用户实际使用确认后再标记 `accepted`。

#### 阻塞、回滚和下一步

- 无当前阻塞。
- AI 策略目前只有“已保存策略产物”，没有独立生成任务历史与创建时间；因此策略条目排在有完成时间的报告之后，并显示“已保存到策略池”。如果以后需要记录未保存/失败的策略生成任务，应在 Agent 台单独设计任务审计契约。
- 回滚方式：移除 `AIHistorySection.tsx` 及 `AIHub.tsx` 挂载，恢复四个目标页面的 `report/strategy` 深链 effect 与 `stockAnalysisStore` 历史打开逻辑，并删除新增测试；不涉及报告正文、策略文件或模型配置回滚。

### stock_analysis_recent_stocks_and_ai_context

#### 用户目标与可见结果

- 个股分析页把搜索框下方改为“最近查看”股票列表，最多保留 10 只，按最近访问倒序去重，当前股票显示高亮和“当前”标记，点击旧股票可直接切换。
- 兼容原有 `last_stock:stock-analysis` 单只记忆：已有的“上次查看”股票会自动出现在新列表中，不要求用户重新访问。
- 从自选股票详情点击“AI 分析”时，`symbol/name` 会显式传到 `/ai`；AI 功能页的“AI 个股分析”卡继续把参数传到 `/stock-analysis`，目标页自动选中并记录该股票。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅；这是现有用户台本地路由和查看记忆的修复。

#### 本地路由、Module、Adapter 与依赖接口

- 最近查看状态：`frontend/src/lib/useLastStock.ts`，新增 `recent_stocks:<scope>` 本地列表，同时保留原 `last_stock:<scope>`。
- 列表组件：`frontend/src/components/stock-analysis/RecentStockList.tsx`。
- 来源入口：`frontend/src/components/StockPreviewDialog.tsx` 生成 `/ai?symbol=...&name=...`。
- 中转路由：`frontend/src/pages/AIHub.tsx` 只为 AI 个股分析卡承接股票参数，并显示“继续分析”提示。
- 目标页面：`frontend/src/pages/StockAnalysis.tsx` 读取参数、自动选中、写入最近列表，并将页面改为左侧搜索/最近查看、右侧分析内容的响应式布局。
- 本轮没有修改后端 API、行情数据、AI 生成流程或报告存储。

#### 自动检查与构建

- 新增端到端组件回归 `AIStockContextFlow.test.tsx`；修复前稳定失败，实际收到 `/stock-analysis` 而非带股票参数的目标，修复后通过完整“自选详情 → AI → AI 个股分析 → 最近查看”链路。
- 4 个相关测试文件共 8 项通过；前端全量 25 个测试文件、67 项测试全部通过。
- 相关文件 ESLint 通过，0 error、0 warning。
- `pnpm build`：TypeScript 与 Vite 生产构建通过；仅保留既有动态/静态导入与大 bundle 提醒。

#### Codex 内置浏览器目标运行面验证

- 目标运行面：`http://127.0.0.1:3011`，页面标题 `one-trading · Quant Terminal`。
- 实测从自选 `300502.SZ 新易盛` 打开详情，“AI 分析”链接为 `/ai?symbol=300502.SZ&name=新易盛`；AI 页显示“继续分析 新易盛 · 300502.SZ”，个股分析卡链接继续保留相同参数。
- 到达个股分析页后，新易盛自动成为当前股票并出现在“最近查看”首位；点击旧记录 `300204.SZ 舒泰神` 后 URL、当前高亮和分析标的同步切换。
- 桌面布局和 `390 × 844` 窄屏布局均已检查；控制台没有本轮 error，仅有既存 React Router v7 future flag warning。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 代码、回归测试、全量测试、生产构建和真实页面完整点击路径已验证；等待用户实际使用确认后再标记 `accepted`。

#### 阻塞、回滚和下一步

- 无当前阻塞。
- 回滚方式：移除 `RecentStockList.tsx` 和 `recent_stocks:*` 扩展，恢复个股分析页原单列布局，并将自选详情和 AI 功能卡恢复为不带股票参数的路由；不涉及后端或数据回滚。

### stock_analysis_dated_history_and_collapsible_recent

#### 用户目标与可见结果

- 个股分析页移除页头右侧重复的“当前股票 + 股票代码”胶囊；当前标的仍在分析区和左侧最近查看中明确显示，页头只保留有独立用途的“历史报告 / 返回分析”切换。
- “最近查看”整体支持收起与展开；每只有已保存结果的股票还可单独展开日期列表，避免左栏被报告摘要长期占满。
- 左侧日期条目显示固定报告时间并打开该条精确历史结果；当前真实样本为 `东山精密 002384.SZ · 08-02 17:56`，不是重新生成、伪造或回填的报告。
- 顶部“历史报告”补齐首次进入页面时主动加载、失败提示与重试；删除操作按接口真实结果提示，不再把失败误报成成功。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅；这是既有个股历史报告、精确深链与最近查看组件的本地用户台闭环修复。

#### 本地路由、Module、Adapter 与依赖接口

- 页面装配与历史视图：`frontend/src/pages/StockAnalysis.tsx`。
- 左侧最近股票、按股票归组的日期报告及两级收放：`frontend/src/components/stock-analysis/RecentStockList.tsx`。
- 历史加载去重、刷新与删除结果：`frontend/src/lib/stockAnalysisStore.ts`。
- 复用既有只读报告接口和既有报告正文；本轮没有修改后端 schema、物理报告文件、模型 Provider、行情数据或分析生成流程，也没有发起模型调用或写入一份演示报告。

#### 自动检查与构建

- 修复前新增回归稳定暴露两项缺口：页头重复股票胶囊仍存在、左侧没有股票历史展开入口。
- `StockAnalysis.test.tsx` 与 `AIStockContextFlow.test.tsx` 共 6 项通过，覆盖重复信息移除、整体收放、按股票展开日期、精确报告打开、页面进入主动加载、顶部历史切换及自选到 AI 的股票上下文。
- 前端全量 25 个测试文件、70 项测试全部通过；相关文件 ESLint 0 error、0 warning。
- 最终防御性默认值补丁后再次执行相关 6 项测试、相关 ESLint 和 `pnpm build`，全部通过；生产构建只保留既有动静态混合导入与大 bundle 提醒。

#### Codex 内置浏览器目标运行面验证

- 干净目标页面：`http://127.0.0.1:3011/stock-analysis?symbol=002384.SZ&name=%E4%B8%9C%E5%B1%B1%E7%B2%BE%E5%AF%86`，标题 `one-trading · Quant Terminal`。
- 左侧实测展开东山精密后出现唯一 `08-02 17:56` 条目，摘要包含历史快照价 `171.48`；点击后 URL 精确加入 `report=sar_1785664583687_002384.SZ`，并打开对应“历史分析报告”。
- 顶部“历史报告”实测切换为“返回分析”，显示当前股票完整历史列表；收起“最近查看”后左侧股票条目消失，右侧历史列表继续保留。
- 桌面与 `390 × 844` 窄屏布局均已复核；新建干净标签页控制台无功能 error，仅有既有 React Router v7 future flag warning。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 代码、回归测试、全量测试、生产构建以及真实报告的展开、精确打开、顶部历史切换和模块收放均已验证；等待用户实际使用确认后再标记 `accepted`。

#### 阻塞、回滚和下一步

- 无当前阻塞。
- 回滚方式：恢复页头 `LastStockChip`，移除 `RecentStockList` 的报告与收放参数，并恢复历史 store 原加载方式；不涉及报告数据、行情数据或模型配置回滚。

### stock_analysis_full_sidebar_collapse_and_watchlist_visibility_audit

#### 用户目标与可见结果

- 个股分析页为“搜索 + 最近查看”整列增加桌面端向左收纳；展开时保持原 `18rem` 宽度，收纳后缩为 `2.75rem` 控制轨，只保留向右展开按钮，右侧分析区获得实际宽度。
- 整列收纳与“最近查看”组件内部收放互不替代：前者释放横向空间，后者只控制列表内容高度。
- 收纳入口只在 `lg` 桌面断点显示；窄屏继续显示完整搜索和最近查看，避免桌面状态使移动端失去选股入口。

#### 自选股显示数量只读排查

- 当前 `/api/watchlist`、物理文件 `data/user_data/watchlist.parquet` 均有 8 只：新易盛、浪潮软件、易点天下、风华高科、三环集团、安克创新、国际复材、舒泰神；本轮没有删除、清空或改写自选数据。
- 当前 `/api/watchlist/enriched` 的 `2026-08-03` 最新增强数据只返回 `301526.SZ 国际复材` 1 行。
- `Watchlist.tsx` 以增强数据行渲染表格，却用“自选总数 - 渲染行数”计算 `hiddenCount`，因此把 7 只“当前没有增强行”的股票误标成“已过滤 7”。这不是筛选器真的删掉或隐藏了 7 条完整行情记录。
- 本条只完成根因诊断；未修改自选页的数据合并与缺数呈现。若后续修复，应以 8 只自选为主表左连接增强数据，并把“筛选隐藏”与“增强数据缺失”分开计数和提示。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅；个股侧栏属于既有用户台本地布局扩展，自选结论来自当前运行 API、物理 Parquet 与前后端源码交叉验证。

#### 本地路由、Module、Adapter 与依赖接口

- 整列收纳状态、桌面响应式网格和控制按钮：`frontend/src/pages/StockAnalysis.tsx`。
- 回归测试：`frontend/src/pages/__tests__/StockAnalysis.test.tsx`。
- 只修改用户台布局和测试；没有修改 `Watchlist.tsx`、后端 API、`watchlist.parquet`、增强数据集、行情 Provider 或模型能力。

#### 自动检查与构建

- 修复前新增回归稳定失败，报错为无法找到 `向左收起股票侧栏`；实现后同一测试通过，并校验网格从 `18rem` 切换为 `2.75rem`。
- `StockAnalysis.test.tsx` 6 项全部通过；前端全量 25 个测试文件、71 项测试全部通过。
- 相关文件 ESLint 0 error、0 warning；`pnpm build` 的 TypeScript 与 Vite 生产构建通过，仅保留既有动静态混合导入和大 bundle 提醒。

#### Codex 内置浏览器目标运行面验证

- 目标页面：`http://127.0.0.1:3011/stock-analysis?symbol=002384.SZ&name=%E4%B8%9C%E5%B1%B1%E7%B2%BE%E5%AF%86`，标题 `one-trading · Quant Terminal`。
- 实测展开态存在唯一“向左收起股票侧栏”按钮，搜索和最近查看均可见，右侧内容宽度为 680px。
- 点击后按钮变为“展开股票侧栏”，搜索与最近查看均隐藏，右侧内容宽度增加到 924px，实际释放 244px；重新展开后恢复 680px 和完整左栏。
- 控制台无本轮功能 error，仅有既有 React Router v7 future flag warning。

#### 当前状态与用户验收

- 个股分析整列收纳状态：`verified`。
- 自选股状态：`diagnosed`，8 只数据仍在；“增强数据缺行 + 过滤提示误标”尚未实施修复。

#### 阻塞、回滚和下一步

- 个股侧栏无当前阻塞。回滚方式：移除 `sidebarCollapsed`、桌面收纳按钮和动态网格列，恢复固定 `lg:grid-cols-[18rem_minmax(0,1fr)]`；不涉及持久数据回滚。
- 自选页如需继续修复，应另行实现“自选主表左连接增强数据”的展示契约，并为缺行情、真实筛选与搜索结果分别提供诚实状态；不能通过清空筛选或重加股票掩盖增强数据覆盖缺口。

### stock_analysis_sidebar_toggle_visual_polish

#### 用户目标与可见结果

- 以“最近查看”标题右侧的轻量箭头为视觉基准，统一整列侧栏、最近查看和单只股票历史三个收放层级。
- 整列收纳按钮不再使用悬浮圆形、边框和阴影；展开态作为搜索框内部的轻量尾随操作，收纳态只保留 28px 方圆箭头控制。
- 最近查看标题的箭头获得统一 28px 交互热区；单股历史入口统一箭头尺寸、间距、数字字体和键盘聚焦反馈，同时保留历史数量语义。
- 搜索加载图标会在桌面端自动让开收纳按钮；空闲态不额外压缩占位文案，移动端仍维持原搜索框空间。

#### 自选股恢复方案只读复核

- 当前管道范围为 `CSI500`；`2026-08-03 15:30` 任务仅为 500 只写入当日公开行情和 enriched。8 只自选中只有 `301526.SZ 国际复材` 与该范围重合，因此自选页最新分区只显示这一只。
- 另外 7 只的自选记录、日 K 和 enriched 历史都仍存在，最新日期为 `2026-07-31`；本轮未修改自选、数据范围、Provider、任务或物理数据。
- 单独“清除筛选”无效；单独“重建 Enriched”也无效，因为它只基于既有日 K 重算，不能补齐缺少的 `2026-08-03` 日 K。
- 操作型临时恢复：数据 → 采集与同步 → 数据范围 → 管道标的范围选择“自选” → 立即同步 → 等任务完成后回到自选页刷新；若以后仍需 CSI500 定时范围，完成后再改回 CSI500。
- 长期正确修复仍应让自选列表以 8 只自选记录为主表、左连接 enriched，并把“数据待更新”与真实筛选分别呈现；否则下一交易日范围不重合时仍可能再次只显示部分股票。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅；视觉优化基于用户标注、当前产品截图和既有组件样式完成。

#### 本地路由、Module、Adapter 与依赖接口

- 侧栏收纳控件与搜索框尾随操作：`frontend/src/pages/StockAnalysis.tsx`、`frontend/src/components/financials/StockFinancialSearch.tsx`。
- 最近查看与单股历史收放：`frontend/src/components/stock-analysis/RecentStockList.tsx`。
- 视觉回归：`frontend/src/pages/__tests__/StockAnalysis.test.tsx`，明确禁止恢复为 `rounded-full + shadow-sm` 的重型悬浮样式。
- 没有修改 `Watchlist.tsx`、后端 API、管道偏好、自选 Parquet 或市场数据。

#### 自动检查与构建

- 视觉回归在修复前稳定失败：整列按钮仍为 `h-8 w-8 rounded-full shadow-sm`；修复后通过 `h-7 w-7 rounded-md` 并确认不含圆形和阴影样式。
- 个股分析相关 6 项测试全部通过；前端全量 25 个测试文件、71 项测试全部通过。
- 相关文件 ESLint 0 error、0 warning；`pnpm build` 的 TypeScript 与 Vite 生产构建通过，仅保留既有动静态混合导入和大 bundle 提醒。

#### Codex 内置浏览器目标运行面验证

- 目标页面：`http://127.0.0.1:3011/stock-analysis?symbol=002384.SZ&name=%E4%B8%9C%E5%B1%B1%E7%B2%BE%E5%AF%86`。
- 展开态截图、收纳态截图及前后对照保存在 `output/design-audit-stock-sidebar-20260803/`；均已重新打开检查，无空白、加载态或错误窗口。
- 实测整列收放、最近查看收放和东山精密历史展开均正常；日期报告 `08-02 17:56` 仍可见，三个控件保留明确的无障碍名称和聚焦样式。
- 控制台无本轮功能 error，仅有既有 React Router v7 future flag warning。

#### 当前状态与用户验收

- 侧栏收放视觉优化状态：`verified`。
- 自选股状态：只读方案复核完成；未执行临时同步，也未实施长期代码修复。

#### 阻塞、回滚和下一步

- 无视觉实现阻塞。回滚方式：恢复 StockAnalysis 的独立悬浮按钮、移除 StockFinancialSearch 的 `trailingAction`，并恢复 RecentStockList 原箭头尺寸和样式；不涉及数据回滚。
- 自选临时恢复会写入日 K/enriched 并改变管道范围设置，需由用户明确决定后再执行；长期方案则是独立的自选页工程修复。

### watchlist_truthful_restore_and_ai_stock_context_flow

#### 用户目标与可见结果

- 自选股继续显示用户保存的完整 8 只股票；行情增强数据暂缺的 7 只保留在表格中，以占位值和“待数据 7”提示呈现，不再误报为“已过滤 7”。
- 用户从自选详情点击“AI 分析”后，`symbol + name` 进入 AI 功能目录；目录明确显示当前分析股票，四个入口都继承同一股票上下文。
- AI 个股分析和 AI 财务分析按既有股票参数打开；大盘复盘将该股票写入“重点关注”，策略生成将其作为可泛化策略的参考标的，而不是把自选表筛成单只股票。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅或合并上游代码；修复依据是 one-trading 当前自选数据、运行 API、页面路由和组件调用链的本地证据。

#### 本地路由、Module、Adapter 与依赖接口

- 完整自选契约：`backend/app/api/watchlist.py` 以 watchlist 为主表左连接最新 enriched 分区，并用 instruments 补齐名称；没有修改 `watchlist.parquet`、行情 Provider 或采集范围。
- 自选可见状态：`frontend/src/pages/Watchlist.tsx` 分离真实筛选数量和增强数据待更新数量。
- 股票上下文路由：`frontend/src/components/StockPreviewDialog.tsx`、`frontend/src/pages/AIHub.tsx`。
- 目标能力消费：`frontend/src/pages/Review.tsx`、`frontend/src/pages/Screener.tsx`、`frontend/src/components/screener/StrategyBuilderDialog.tsx`；财务分析与个股分析继续消费原有 `symbol/name` 查询参数。
- 相关回归覆盖后端完整行契约、自选可见状态、AI 四入口、复盘关注文本、策略草稿预填和原有自选到 AI 个股分析链路。

#### 自动检查与构建

- 后端聚焦测试：`backend/tests/test_watchlist_enriched_join.py` 2 项通过，覆盖最新分区部分缺行和完全空分区。
- 前端聚焦测试：6 个测试文件、9 项测试通过。
- `pnpm build` 通过；保留既有动静态混合导入与大 bundle 提醒。
- 目标 ESLint 无 error；仅保留目标文件中本轮之前已有的 React Hook 与 TypeScript warning，未扩大范围处理。

#### Codex 内置浏览器目标运行面验证

- `http://127.0.0.1:3011/watchlist` 实测显示 8 只自选、完整名称、“8只”和“待数据 7”，不再显示虚假的“已过滤 7”。
- 自选股票 `300502.SZ 新易盛` 进入 AI 目录后，页面显示当前股票；四个卡片分别携带上下文进入个股分析、财务分析、大盘复盘与策略生成。
- 个股分析选中同一股票；财务分析显示同一股票；复盘重点关注输入已带入该股票；策略生成的名称、说明与规则草稿已带入该股票。
- 浏览器控制台无本轮功能 error，仅有既存 React Router v7 future flag 提醒。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 用户已授权修复；自动检查、生产构建和目标浏览器主路径已完成，等待用户实际使用确认后再标记 `accepted`。

#### 阻塞、回滚和下一步

- 7 只“待数据”来自当前最新 enriched 分区覆盖不足；本轮如实保留股票并显示缺数，不伪造行情，也不改变当前 CSI500 管道范围。
- 回滚方式：恢复 enriched 直接返回逻辑、Watchlist 原计数语义，以及 AIHub/复盘/策略的股票上下文传递；不涉及自选、报告、行情或 AI 配置的数据回滚。

### watchlist_realtime_snapshot_overlay

#### 用户目标与可见结果

- 自选股保持完整 8 只，不再等待盘后日 K 才显示当天行情；页面优先展示最新实时快照的现价、涨跌幅、涨跌额和成交额。
- 标题区增加“实时 N”与快照时间，当前 8 只均有实时快照时显示“实时 8 / 11:39”，不再显示“待数据 7”。
- 实时快照只覆盖同名行情字段；换手率、量比、RSI、动量等盘后指标继续来自正式 enriched 数据，避免把缺少的实时指标伪造成已更新。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅；实现复用 one-trading 已持久化的 `quote_snapshot` 与既有 Watchlist 表格，不引入新数据生产者或外部依赖。

#### 本地路由、Module、Adapter 与依赖接口

- 目标路由：`/watchlist`；界面 Module：`frontend/src/pages/Watchlist.tsx`。
- `GET /api/watchlist/enriched` 读取最新且不早于正式 enriched 日期的 `quote_snapshot`，按 symbol 左连接 `rt_price / rt_pct / rt_change_amount / rt_amount / rt_name / rt_source / rt_fetched_at`，并返回 `realtime_count / realtime_as_of`。
- 前端价格、涨跌幅、涨跌额、成交额及对应排序均采用实时字段优先、正式字段回退；“待数据”只统计实时价与正式收盘价均不存在的行。
- QuoteService 的运行时关闭改为 `persist=false`，热重载或进程退出不再把用户的“实时行情已启用”偏好误写成关闭。

#### 自动检查与构建

- 后端聚焦测试 25 项通过，覆盖实时快照 overlay、过期快照拒绝、快照持久化、公开源全市场模式、lifespan 与运行时关闭不落盘。
- 前端 `Watchlist.test.tsx` 2 项通过，覆盖实时价格/涨跌幅/涨跌额、实时计数与待数据口径。
- `pnpm build` 通过；保留既有动静态混合导入与大 bundle 提醒。目标 Ruff、Python compile 与 diff check 通过；目标 ESLint 0 error，保留 `Watchlist.tsx` 两条既有 Hook warning。

#### Codex 内置浏览器目标运行面验证

- `http://127.0.0.1:3011/watchlist` 实测显示 8 只自选、`实时 8`、快照时间 `11:39`；8 行均有当天现价、涨跌幅和涨跌额。
- 抽样确认：`300502.SZ 新易盛` 为 `440.88 / +11.88% / 46.80`，`600756.SH 浪潮软件` 为 `16.34 / -1.51% / -0.25`；不再出现实时上涨却显示旧负涨跌额的混合口径。
- 实时开关为启用状态；当前为非交易时段，页面明确提示将在交易时间自动开启。控制台没有本轮功能 error，仅有既存 React Router v7 future flag warning。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 代码、自动检查、生产构建、当前 API 与实际浏览器页面均已验证；等待用户实际使用确认后再标记 `accepted`。

#### 阻塞、回滚和下一步

- 当前快照时间为午间休市前 `2026-08-04 11:39`；交易恢复后 QuoteService 会继续按现有间隔更新。技术指标仍以最近正式 enriched 分区为准，不宣称为实时。
- 回滚方式：移除 watchlist API 的 quote snapshot overlay、前端实时徽标/字段优先和 QuoteService `persist` 参数；不需要修改自选记录或正式日 K/enriched 数据。

### stock_preview_kline_history_ranges

#### 用户目标与可见结果

- 自选股详情 K 线顶栏不再只有“半年、1年”，新增 `1月 / 3月 / 半年 / 1年 / 3年 / 5年 / 全部` 七档历史范围。
- 保留起止日期选择器；快捷项和手工日期仍共用现有日 K 日期范围查询。
- 选择范围后同步调整图表初始视窗，不再出现“请求了全部历史但仍只显示最近 60 根”的假切换。
- “全部”表示从本地最早可用日 K 到当前日期，不承诺固定上市以来年限。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅；只读参考本地 `/Users/simon/Trading/go-stock` 的产品与数据源实现。
- go-stock 的 `frontend/src/components/kline/constants.js` 区分 `1/5/15/30/60 分钟` 与 `日/周/月/季/年 K`；其后端 `backend/data/sina_kline_api.go`、`backend/data/tdx_kline_api.go` 依赖独立多周期取数和 MAC、东方财富、新浪、腾讯、通达信降级链。
- one-trading 当前正式契约仍是本地 enriched 日 K 日期范围和单日分钟数据，因此本轮只采用历史范围交互，不把尚未拥有独立契约的周/月/季/年 K 伪装成已接入能力，也没有把 go-stock 运行时或 Provider 搬入主项目。

#### 本地路由、Module、Adapter 与依赖接口

- 目标路由：`/watchlist` 的自选股详情弹窗。
- 界面 Module：`frontend/src/components/StockPreviewDialog.tsx`、`frontend/src/components/StockPanel.tsx`。
- 行为测试：`frontend/src/components/__tests__/StockPreviewDialog.test.tsx`。
- 继续使用 `GET /api/kline/daily?symbol=...&start_date=...&end_date=...`；未修改后端 API、Provider、Parquet、复权语义或正式数据。

#### 自动检查与构建

- 新增回归覆盖七档按钮，以及“3年”和“全部”对应的真实请求起止日期。
- 前端全量测试：18 个文件、76 项全部通过。
- `pnpm build`：TypeScript 与 Vite 生产构建通过；保留既有动静态混合导入和大 bundle 提醒。
- 目标 ESLint 无 error；`StockPanel.tsx` 保留一条本轮之前已有的 Hook 依赖 warning，未扩大范围处理。目标 `git diff --check` 通过。

#### Codex 内置浏览器目标运行面验证

- 目标页面：`http://127.0.0.1:3011/watchlist`，页面标题为 `one-trading · Quant Terminal`，运行前端 PID `17633` 的工作目录是当前 `frontend/`。
- 实测打开 `301526.SZ 国际复材`，顶栏完整显示七档历史范围，默认“半年”激活；布局无溢出或遮挡。
- “3年”切换后起始日期变为 `2023-08-05`；“全部”切换后请求起始日期为 `1990-01-01`，实际 API 返回本地可用的 631 根日 K，范围为 `2023-12-26 ～ 2026-08-05`。
- “全部”视窗实际展开全部 631 根，不再停留在最近 60 根。控制台无功能 error，仅有既存 React Router v7 future flag warning。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 代码、完整前端测试、生产构建、真实 API 和 Codex 内置浏览器主路径均已验证；等待用户实际使用确认后再标记 `accepted`。

#### 阻塞、回滚和下一步

- 当前没有实现真正的周/月/季/年 K 或多分钟聚合；这些能力需要数据台先建立独立周期、复权、来源和质量契约后再进入用户台。
- 回滚方式：恢复 `StockPreviewDialog.tsx` 的原两档范围并移除传入的 `visibleBars`，同时恢复 `StockPanel.tsx` 的固定 40/60 根视窗；不涉及任何行情数据或用户自选记录回滚。

### stock_preview_technical_signal_summary

#### 用户目标与可见结果

- 在个股日 K 详情中，把 go-stock 参考界面的 44 项技术指标信号放到行情信息条下方、原“成交量 / MACD / RSI / KDJ / BOLL / 异动”控制行上方。
- 默认展开全部 44 项；顶部同时显示看多、看空、震荡、中性数量与比例条，并标注当前计算截止日期。
- 用户收起后只保留汇总；再次展开恢复全部标签。用户移动十字光标或点击其他 K 线日期时，汇总按该日期之前的历史重新计算。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 在线审阅；定点参考本机 `/Users/simon/Trading/go-stock/frontend/src/components/StockLightweightKlineChart.vue` 的 `evaluateIndicatorSignals` 和信号汇总界面，以及 `frontend/src/components/kline/calc.ts` 的指标公式。
- 只把公式和信号判定迁入 one-trading 自有前端 Module；没有把 go-stock 作为运行时依赖、没有复用其 Vue 页面壳，也没有切换 one-trading K 线数据源。

#### 本地路由、Module、Adapter 与依赖接口

- 目标界面：所有复用 `StockPanel` 的个股日 K 详情；主验证路由为 `/stock-analysis?symbol=300502.SZ&name=新易盛` 打开的日 K 弹窗。
- 新增界面 Module：`frontend/src/components/TechnicalSignalSummary.tsx`。
- 新增自有计算 Module：`frontend/src/lib/technical-signal-calc.ts`、`frontend/src/lib/technical-signals.ts`。
- 接入位置：`frontend/src/components/StockPanel.tsx` 的 `StockInfoBar` 与 `StockDailyKChart` 之间。
- 十字光标联动：`frontend/src/components/EChartsCandlestick.tsx` -> `StockDailyKChart.tsx` -> `StockPanel.tsx`；悬停日期只更新指标汇总，不改变点击选中的分时日期。
- 测试：`frontend/src/components/__tests__/TechnicalSignalSummary.test.tsx`、`frontend/src/components/__tests__/EChartsCandlestick.pointer.test.tsx`。
- 继续只读消费既有 `GET /api/kline/daily` 返回的 OHLCV；没有修改后端 API、Provider、Parquet、复权、行情单位或自选记录。

#### 自动检查与构建

- 指标汇总测试 3 项通过，覆盖 44 项固定顺序与唯一性、四类计数总和、选中日期和展开/收起。
- 相关回归：`TechnicalSignalSummary.test.tsx`、`StockPreviewDialog.test.tsx`、`StockAnalysis.test.tsx` 共 11 项通过。
- 目标 ESLint 0 error；新增信号文件无 warning，`StockPanel.tsx` 只保留本轮之前已有的 Hook 依赖 warning。
- `pnpm build`：TypeScript 与 Vite 生产构建通过；保留项目既有动静态混合导入与大 bundle 提醒。
- 2026-08-05 悬停补强回归：新增 2 项测试，覆盖 `updateAxisPointer` 日期上传，以及十字线保留但全局/tooltip 两层轴标签均关闭；与指标汇总、弹窗范围回归合计 3 个文件、7 项通过。补强后的生产构建再次通过。

#### Codex 内置浏览器目标运行面验证

- 正式 `3018` 当时因既有热重载等待长连接关闭而没有响应；没有重启或修改用户的现有运行配置。使用同一工作树与本地数据启动隔离验证面 `127.0.0.1:3111/3118`。
- `1280 × 720` CSS 视口、浅色主题、`300502.SZ 新易盛` 实测：汇总位于用户确认的位置，显示 `共 44 项`、截止 `2026-08-05`、四类比例和 44 个不重复标签，没有横向溢出或覆盖 K 线。
- 展开态 `aria-expanded=true` 且 44 个标签可见；收起态 `aria-expanded=false` 且标签为 0；再次展开恢复 44 个。
- 控制台没有本轮功能 error，仅有既存 React Router v7 future flag warning。
- 设计 QA：`/Users/simon/Trading/one-trading/design-qa.md` 最新条目，结论 `passed`；聚焦对比图位于 `/Users/simon/.codex/visualizations/2026/08/05/019fd0f2-2d5f-7250-ab6e-546203a0daf2/07-signal-summary-comparison.png`。
- 悬停补强实测：光标从 `2026-05-18` 移到 `2026-06-18`，汇总由 `看多 16 / 看空 8 / 震荡 12 / 中性 8` 变为 `看多 28 / 看空 4 / 震荡 8 / 中性 4`；同步日期与现有 K 线行情栏一致。十字线继续显示，横轴/纵轴空白标签框均已消失，底部时间刻度不再被遮挡。截图：`/Users/simon/.codex/visualizations/2026/08/05/019fd0f2-2d5f-7250-ab6e-546203a0daf2/08-hover-crosshair-fixed.png`。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 代码、指标契约、针对性回归、生产构建和隔离 one-trading 目标运行面已验证；等待用户实际使用确认后再标记 `accepted`。

#### 阻塞、回滚和下一步

- 当前正式 `3011/3018` 运行面需要其既有后端热重载自行恢复或由用户另行授权重启；这不影响本轮隔离验证结论，但未把正式 3011 写成已复核。
- 回滚方式：从 `StockPanel.tsx` 移除 `TechnicalSignalSummary`，删除新增计算、汇总组件与测试；不涉及持久数据或用户配置回滚。

### data_stock_margin_trading_business

#### 用户目标与可见结果

- 数据目录从 24 个增加到 25 个数据集，并新增独立“股票 F10”分组；首个业务卡为“个股融资融券”，不再混在核心行情或普通财务表中。
- “采集与同步”增加个股融资融券卡片，可输入一个或多个股票代码显式同步；页面直接说明“东方财富单源”、金额为人民币元、融券量为股，以及 go-stock 只作接口情报。
- 同步成功后展示正式总行数、最新交易日与无数据股票，并刷新目录、Schema、运行记录和控制摘要。

#### 本地路由、Module 与跨台依赖

- 目标路由：`/data?section=catalog`、`/data?section=collection`、`/data?section=source-trace&trace=stock_margin_trading`。
- 界面 Module：`frontend/src/components/data/MarginTradingSyncCard.tsx`、`DataCatalogSection.tsx`、`PageSettingsModal.tsx`、`StorageBreakdownCard.tsx`、`DataSourceTracePanel.tsx` 与 `frontend/src/pages/Data.tsx`。
- API Adapter：`frontend/src/lib/api.ts::syncMarginTrading`，消费数据台的显式 sync API；实际 Provider、Schema、Parquet、lineage 和状态见同日数据日志 `stock_margin_trading` 条目，不在用户台复制成生产结论。

#### 自动检查、构建与浏览器验证

- 新增/相关前端测试覆盖同步参数与成功提示、来源跳转、独立 F10 目录分组和页面显示设置；全量 20 个测试文件、82 项通过。
- ESLint 无 error；生产构建通过，保留既有 Hook、混合动静态导入和 bundle 大小 warning。
- Codex 内置浏览器目标运行面 `http://127.0.0.1:3111/data`：目录徽标为 25；“股票 F10”显示 1 个业务、1,886 行、8 个标的、状态健康；采集页用 `600756.SH` 实测幂等同步成功并显示“已写入 1,886 行 · 最新 2026-08-04”。
- 来源追踪实测显示 EastMoney public endpoints 为真实生产者；go-stock 只显示融资融券 F10 参数/字段情报，“本地快照兜底”徽标为 0。控制台无本轮 error，仅有既有 React Router v7 future flag warning。

#### 当前状态、回滚和下一步

- 用户台当前状态：`verified / 待用户验收`。它证明业务入口、同步交互和披露界面可用，不把数据集提升为 `accepted / production`。
- 回滚：移除 F10 分组、显示设置项、同步卡和 API client 方法；数据与控制库回滚按数据平台日志执行。
- 本轮停止于融资融券单数据集，不预建大宗交易、股东户数、龙虎榜、机构预测、基金或新闻的空页面。

### watchlist_chinese_search_and_historical_chart_audit

#### 用户目标与可见结果

- 自选股搜索框将提示语由“搜索…”明确为“代码或中文名称”，继续复用既有全市场证券搜索接口；实测输入“新易盛”返回 `300502.SZ 新易盛`。
- 修复 `301526.SZ` 选中 `2026-07-20` 时的日期错配：筹码请求携带同一个 `as_of`，后端先按截止日截断本地日 K 再计算；历史分钟返回行必须与请求日期一致，错日公开回退会被拒绝为空。
- 目标日实测保持 `开 33.00 / 高 33.47 / 低 25.44 / 收 26.70 / -15.48%`；筹码显示“截至 2026-07-20”，推算现价为 `26.70`；本地无该日分钟数据时显示诚实空态，不再绘制 `2026-08-05` 的上涨分时。
- 筹码结果仍是本地日 K 的换手衰减与价格分布推算，不是交易所官方持仓成本；本轮没有写入或改写 K 线、分钟、筹码缓存和用户自选数据。

#### 本地路由、Module 与验证

- 目标路由：`/watchlist`；界面 Module：`frontend/src/pages/Watchlist.tsx`、`frontend/src/components/StockPanel.tsx`、`frontend/src/components/ChipDistributionPanel.tsx`；数据 API 契约见 `docs/data-platform-development-log.md` 的 `4.9 kline_historical_date_alignment`。
- 前端相关 5 个测试文件、11 项通过；后端筹码/分钟相关 4 个测试文件、9 项通过。目标 ESLint 0 error，保留 `StockPanel.tsx` 一条既有 Hook 依赖 warning；生产构建通过，保留既有混合导入与大 bundle 提醒。
- Codex 内置浏览器正式运行面 `http://127.0.0.1:3011/watchlist` 实测中文搜索成功；控制台无本轮 error，仅有既存 React Router v7 future flag warning。截图：`/Users/simon/.codex/visualizations/2026/08/05/019fd0f2-2d5f-7250-ab6e-546203a0daf2/09-watchlist-chinese-search.png`。
- 同一正式运行面将范围切到 1 月并点击 `2026-07-20` 蜡烛：日 K 为 `26.70 / -15.48%`，分钟为空态，筹码为“截至 2026-07-20”、获利盘 `3.3%`；截图：`/Users/simon/.codex/visualizations/2026/08/05/019fd0f2-2d5f-7250-ab6e-546203a0daf2/10-historical-date-alignment-fixed.png`。

#### 当前状态、回滚和下一步

- 中文名称搜索：`verified / 待用户验收`。回滚只需恢复搜索框提示语并移除对应回归用例。
- 历史筹码与分钟日期一致性：`verified / 待用户验收`。回滚需同时移除前端 `asOf` 查询契约、筹码后端截止日过滤和分钟日期门禁；不涉及持久数据恢复。

### watchlist_on_demand_historical_minute

#### 用户目标与可见结果

- 自选股详情选择历史 K 线后，分时面板使用同一个交易日；本地没有时按需读取该自选股/日期并缓存，不要求用户启动全市场分钟同步。
- `301526.SZ` 点击 `2026-06-29` 后，左侧日 K 显示 `开 52.25 / 高 52.25 / 低 45.68 / 收 47.80 / -8.51%`；右侧显示同日下跌分时，末点 `47.82`，不再显示最新日上涨曲线。
- 空态“重新读取该日分时”现在只重试当前 `symbol + date`，不再调用需要 Pro+ 的“最近 5 日全市场分钟 K”入口；加载文案改为“正在读取该日分时…”。

#### 本地路由、Module 与跨台依赖

- 目标路由：`/watchlist`；界面 Module：`frontend/src/components/StockPanel.tsx`、`StockIntradayChart.tsx`、`EChartsIntraday.tsx`。
- API Adapter：`frontend/src/lib/api.ts::klineMinute`；React Query key 保持 `['kline-minute',symbol,date]`，成功重试直接更新同一 key。
- 数据生产、范围门、日线对账、Parquet 与 lineage 见数据平台开发日志 `4.10 stock_minute watchlist on demand`；用户台不把 easy_tdx 或 Catalog 状态复制成自己的生产结论。

#### 自动检查、构建与 Codex 内置浏览器

- 后端自选范围、错日拒绝、价格/量/额对账、原子写入和幂等相关回归纳入本轮 `44 passed`；前端 TypeScript/Vite `pnpm build` 通过。
- 正式运行面 `http://127.0.0.1:3011/watchlist`：打开国际复材，开启分时并点击 `2026-06-29` 蜡烛；左右标题同日，右侧 240 点曲线完整，末点 47.82，页面没有 Pro+ 权限 toast。
- 页面控制台无业务 error；只看到既有 React Router v7 future flag warning。

#### 当前状态、回滚和下一步

- 用户台状态：`verified / 待用户验收`。真实页面和数据台 canary 已验证，但不自动写成用户接受或生产状态。
- 回滚：恢复 `StockIntradayChart` 原重试动作和文案，并停止数据台按需 Adapter；持久数据回滚按数据平台日志和备份执行。
- 非目标：不新增全市场分钟同步按钮，不把点击行为改成后台批量任务，不改变筹码面板算法。

### watchlist_custom_column_data_bridge

#### 用户目标与可见结果

- 修复“数据台已有扩展/财务数据，但自选股自定义列整列显示 `—`”的问题；不改变用户现有8只自选股、列偏好或数据源配置。
- 已保存的“名称（行业板块资金流）”从8/8空值恢复为7/8可见：国际复材=玻璃玻纤、新易盛=通信设备、浪潮软件=IT服务Ⅱ、易点天下=广告营销、风华高科=元件、安克创新=消费电子、舒泰神=化学制药。
- 三环集团仍为空是 `ext_hy_ths` 当前没有该股票行业记录，不再归因于 JOIN 故障或用推测值填充。

#### 本地路由、Module、Adapter 与跨台依赖

- 目标路由：`/watchlist`；用户台继续使用既有 `ColumnCustomizer`、`Watchlist.tsx` 和保存列配置，没有新增页面或改变筛选边界。
- 数据消费 Adapter：`backend/app/api/watchlist.py::watchlist_enriched`。
- 行业板块资金流通过 `ext_hy_ths.所属同花顺行业` 投影到股票，取股票行业路径中最细且能命中的板块；兼容 `IT服务Ⅱ/IT服务Ⅲ` 等层级后缀。
- 概念板块资金流通过 `ext_gn_ths.所属概念` 投影到股票；快照取所属概念中排名最高的一项，日线无排名时取绝对主力净流入最大的一项，不对重叠概念做虚假加总。
- 稀疏个股资金流不再只读全表最新分区，而是从既有时序分区中取每只股票各自的最新记录；没有触发外部采集或写入 Parquet。
- 本地 `financials/metrics` 以已有 provider 值优先、公开财务表兜底，补齐 EPS、BPS、ROE、毛利率、净利率、营收增速、净利增速和负债率；百分点在 API 边界转换为前端统一的小数比例。PE(TTM)/PB 仍只在上游 enriched 已提供时展示，不伪造估值数据。

#### 自动检查、构建与目标运行面

- 后端新增4类回归：行业映射、概念代表项、稀疏个股时序逐股票最新值、财务最新报告期与单位转换；相关资金流套件合计21项通过。
- 前端新增财务列排序/筛选映射测试；与自选股页面回归合计13项通过。
- Python 目标 Ruff（忽略同文件本轮前已有的 RUF100/RUF003/RUF005）通过，Ruff format check 通过，目标 `git diff --check` 通过。
- 前端 TypeScript/Vite 生产构建通过；保留项目既有混合动静态导入和 bundle 大小提醒。
- 正式 `3018` API 实测：行业快照7/8、行业日线6/8、概念快照8/8、概念日线8/8、个股资金流4/8、概念分类8/8、行业分类7/8、财务 EPS/ROE 8/8；单个已保存行业列请求约36ms。
- Codex 内置浏览器正式运行面 `http://127.0.0.1:3011/watchlist`：修复前8/8行末列为 `—`，修复后7项显示真实行业板块名称，仅三环集团保留 `—`；8只自选股仍完整保留。

#### 当前状态、回滚和下一步

- 当前状态：`verified / 待用户验收`。代码、回归、构建、正式 API 与真实页面主路径均已验证；未把数据源覆盖缺口写成代码已补齐。
- 本轮没有修改或覆盖任何 `data/` 资产，没有触发同步、外部抓取、用户列配置写入或 go-stock 运行时接入；现有数据集生命周期状态不变。
- 回滚：恢复 `watchlist.py` 的直接 symbol JOIN、移除财务兜底与对应测试，并恢复 `stock-table.ts` 的财务排序映射；不需要回滚自选记录或数据文件。
- 若要把三环集团行业补成8/8、把个股资金流补成8/8，需要另行进行源数据补采/覆盖验收，不能用本轮消费层修复冒充数据已存在。

### industry_analysis_dimension_and_percentage_display

#### 用户目标与可见结果

- 修复行业分析把主力净流入原始金额显示成行业名称、把行业板块代码显示成股票、并把 `6.41%` 放大为 `641.00%` 的问题。
- 页面主体恢复使用真实股票—行业分类：当前显示 90 个二级行业、4,635 只标的；行业矩阵、热度分布、领涨/领跌和龙头候选均显示真实行业与股票名称。
- 独立“行业主力资金流向”继续使用行业资金流快照，保持 `元件 124.31亿 / +6.41%` 等原有正确金额与百分点格式。

#### 本地路由、Module、Adapter 与依赖接口

- 目标路由：`/industry-analysis`。
- 页面 Module：`frontend/src/pages/IndustryAnalysis.tsx`；共享配置入口：`frontend/src/components/analysis-shared.tsx`。
- 轻量 Adapter：`frontend/src/lib/analysis-adapter.ts`；回归测试：`frontend/src/lib/__tests__/analysis-adapter.test.ts`。
- 行业主体只读消费 `ext_hy_ths.所属同花顺行业` 与既有 `/api/screener/market-snapshot`；资金流面板继续只读消费既有行业资金流 API。本轮没有修改后端 Provider、API、Parquet、用户自选或行情数据。
- 旧版已保存的 `ext_fund_flow_bk + main_net` 配置会在运行时被判定为不兼容并回退到 `ext_hy_ths`；不静默改写用户本地存储。数值字段和股票元数据不再进入维度字段候选。
- 行情快照在盘中与盘后曾出现百分点/小数比例两种横截面尺度；Adapter 以整批 75 分位识别并统一为页面使用的小数比例，避免逐只股票阈值误判。

#### 自动检查与构建

- 新增 5 项回归，覆盖资金流表拒绝、内置行业 membership 优先、旧错误配置回退、数值维度拒绝、缺失 `dtype` 兼容，以及行情快照两种涨跌幅尺度归一；测试均先验证失败再实现修复。
- 前端全量 25 个测试文件、102 项通过；目标 ESLint 0 error。
- `pnpm build`：TypeScript 与 Vite 生产构建通过；只保留项目既有动静态混合导入和大 bundle 提醒。

#### Codex 内置浏览器目标运行面验证

- 正式运行面：`http://127.0.0.1:3011/industry-analysis`；页面标题 `one-trading · Quant Terminal`。
- 干净新页面实测：`90 个行业 · 4635 只标的`；半导体 `31涨/3跌 / +3.12%`，中国稀土 `+10.00%`；页面不再出现 `12431377920`、`+641.00%` 或 `+409.79%`。
- 配置弹窗实测默认选中“扩展行业”，维度候选只有“所属同花顺行业”，打开/取消无崩溃。
- 干净页面控制台无本轮 error，仅有既存 React Router v7 future flag warning。

#### 当前状态与用户验收

- 当前状态：`verified / 待用户验收`。
- 代码、回归、全量前端测试、生产构建、正式 3011 页面、配置入口与可见数字均已验证；等待用户实际使用确认后再标记 `accepted`。

#### 阻塞、回滚和下一步

- 无阻塞；本轮没有触发行业分类或资金流刷新，也没有写入数据文件。
- 回滚：恢复 `IndustryAnalysis.tsx` 的旧自动选源、`analysis-shared.tsx` 的旧字段列表并移除 `analysis-adapter.ts` 新增的兼容选择/单位归一函数与对应测试；不涉及数据恢复。

### watchlist_quote_kline_latest_alignment

#### 用户目标与可见结果

- 修复自选股列表已显示最新行情、点开详情却仍停在旧日线的问题。`603261.SH 立航科技` 的列表与详情现在同为 `49.11 / -1.34 / -2.66%`。
- 详情最新 K 线从 `2026-07-31 / 45.39` 补齐到 `2026-08-07`，最新 OHLC 为 `50.46 / 50.97 / 48.67 / 49.11`；指标汇总截止日期也同步为 `2026-08-07`。
- 根因是 K 线接口只接受“日期等于系统今天”的内存行情；`2026-08-08` 为非交易日，已落盘的 `2026-08-03..07` 行情快照没有进入详情响应。

#### 本地路由、Module、Adapter 与依赖接口

- 目标路由：`/watchlist` 的个股详情弹窗。
- 用户台 Module：`frontend/src/components/StockInfoBar.tsx`；涨跌额和涨跌幅优先采用最新行情行自己的 `change_amount / change_pct`，在字段缺失时才从相邻 K 线推导。
- 数据消费 Seam：`backend/app/api/kline.py::get_daily`。它只把正式日线之后、请求日期范围内的 `quote_snapshot` 按交易日追加到 API 响应，并返回 `quote_overlay` 来源元数据。
- `quote_snapshot.change_pct` 从生产者百分点转换为 K 线接口的小数比例；成交量继续为手、成交额继续为人民币元。
- 同日已有 canonical 日线时正式日线优先；本轮不写入、覆盖或迁移 `kline_daily / kline_daily_enriched / quote_snapshot`，也不发起外部抓取。

#### 自动检查与构建

- 新增后端回归覆盖快照补齐、历史截止日门禁、百分点转换和“零正式日线写入”；相关 K 线、快照、自选接口共 `16 passed`。
- 新增前端回归固定旧可见行不得覆盖最新行情自身涨跌字段；相关自选详情与页面共 `6 passed`。
- TypeScript/Vite 生产构建通过；只保留项目既有混合动静态导入与大 bundle 提醒。
- `backend/app/api/kline.py` 全文件 Ruff 仍报告此前已有的全角标点、导入位置等存量债务；本轮没有批量格式化该脏文件，新增逻辑由聚焦测试、Python 编译和 `F/E9` 检查约束。

#### Codex 内置浏览器目标运行面验证

- 正式接口 `127.0.0.1:3018`：自选与 K 线最新行均为 `2026-08-07 / 49.11 / -1.34 / -2.66% / source=tencent`；响应报告只读补入 5 个交易日快照。
- 正式页面 `http://127.0.0.1:3011/watchlist`：打开立航科技后，弹窗标题、行情栏、最新蜡烛和指标截止日期全部对齐到上述值；页面控制台无 error。

#### 当前状态、回滚和下一步

- 当前状态：`verified / 待用户验收`。已验证代码、自动回归、生产构建、正式 API 和正式浏览器主路径；不把响应覆盖层写成 canonical 日线已封账。
- 回滚：移除 K 线 API 的 `quote_snapshot` 只读合并、前端权威涨跌字段优先和对应测试；不需要恢复任何行情或用户数据。
- 后续盘后正式日线补齐后，同日 canonical 行会自然取得优先权；无需清理本轮快照响应标记。

### market_pulse_workbench

#### 用户目标与可见结果

- 在看板 KPI 下方、原有主体卡片之前加入“市场脉搏”，把上证指数分时、分钟成交额和财联社板块异动放在同一交易日时间轴；`2026-08-10` 正式样本显示 241 个分钟点与 22 条事件。
- P0：同日时间轴与有限防碰撞事件标签；P1：点击轮动事件后显示内联详情，并可带 `focus` 到概念/行业查找、带 `as_of + focus` 到复盘；P2：显式即时指数比较、盘中回放、板块轮动轨迹与 AI 复盘预填。
- “刷新本地”只读 GET；“从财联社更新”才显式访问外部并写入。即时比较明确显示“不写入”，AI 入口只填充关注文本，用户仍需点击“生成复盘”才会调用模型。

#### GitHub 情报与固定上游点

- 沿用 `/Users/simon/Trading/用户台GitHub项目借鉴记录.md#32-arvinlovegoodgo-stock` 的固定点；本轮定点核对本地 go-stock `frontend/src/components/AnalyzeMartket.vue` 与 `backend/data/cls_market_api.go`。
- 只采用“指数分时 + 板块事件同轴”的产品形态、端点参数和字段情报；未采用 Vue/Wails/GPL Runtime、SQLite、最近 7 天静默回退或 go-stock 网络运行链。

#### 本地路由、Module、Adapter 与跨台依赖

- 主 Module：`frontend/src/components/MarketPulsePanel.tsx`；看板落点：`frontend/src/pages/Dashboard.tsx`。
- 数据台入口：`frontend/src/components/data/MarketPulseSyncCard.tsx`、`frontend/src/pages/Data.tsx`、目录与来源追踪组件；API 类型和缓存键位于 `frontend/src/lib/{api,queryKeys}.ts`。
- 跨页 Seam：`ConceptAnalysis.tsx`、`IndustryAnalysis.tsx` 解析 `focus`；`Review.tsx` 解析 `as_of/focus` 并显示返回同日时间轴的证据链接。该链只消费数据台本地 API，不把 Provider 或模型实现塞入用户台。
- 数据生产、Parquet、lineage、质量门和生命周期见 `/Users/simon/Trading/one-trading/docs/data-platform-development-log.md#411-market_pulse`；本条不复制成用户台生产结论。

#### 自动检查与构建

- 前端全量 27 个测试文件、107 项通过；4 项市场脉搏行为测试覆盖本地刷新/显式外部同步、交易日选择不外连、事件深链和按选择才触发即时指数查询。
- TypeScript/Vite 生产构建通过；目标市场脉搏组件 ESLint 0 error/0 warning。全项目 lint 0 error，保留 35 条既有 Hook/类型 warning；构建保留既有混合动静态导入和大 bundle 提醒。
- 跨层后端全量 313 项通过；详细数据测试与正式资产证据只写数据平台日志。

#### Codex 内置浏览器目标运行面验证

- 正式运行面 `http://127.0.0.1:3011/?as_of=2026-08-10#market-pulse`：首轮发现数据已加载但图表空白，根因是初始 loading 阶段容器未挂载而初始化 effect 只执行一次；改为数据点进入后初始化，复验产生 1030×340 ECharts canvas，指数线、成交额柱与异动标记完整可见。
- 事件详情实测“影视”可分别跳到 `/concept-analysis?focus=影视`、`/industry-analysis?focus=影视` 与带同日关注文本的复盘；概念/行业搜索均正确预填，复盘显示 241/22 盘面证据、同日时间轴链接和预填关注点，页面仍提示用户点击“生成复盘”。
- 回放推进到 `7 / 241` 后可暂停、退出；切换深证成指后显示 242 分钟和“即时指数查询，不写入”。切换前后 `market_pulse` Parquet 的 mtime、16,607 bytes 与 SHA-256 `7c6916a86b70ce3e66aa63ce09c79e9538918848056bddf86a6d84dec6e78754` 均不变。
- 375×812 验证：模块宽 349px、canvas 349×340、事件详情 325px，页面 `scrollWidth=375` 无横向溢出；轮动轨迹在自身 325px 容器内横向滚动。浏览器控制台无业务 error，只有项目既有 React Router future flag warning。

#### 2026-08-10 日期与文案细节复调

- 标题旁的静态日期改为复用现有 `DatePicker`；用户可在市场脉搏模块内选择日期，最大值限制为上海时区当天。日期切换只改变本模块的 local-only GET，不联动整张看板，也不自动触发财联社同步。
- 标题区域不再显示“本地 market_pulse”或其他来源技术标签；底层 dataset、API、Catalog、lineage 和来源追踪入口均保留。非默认指数仍通过下拉选项中的“（即时）”说明查询性质。
- 主操作从“从财联社更新”精简为“更新”，loading/error/空态文案同步改为“更新中/更新失败/点击更新”；数据页的完整生产者披露不变。
- 自动检查：市场脉搏组件 4 项通过，前端全量 107 项通过，目标 ESLint 0 error/0 warning，TypeScript/Vite 生产构建通过。
- Codex 内置浏览器正式 `3011`：日历弹层可见年月、星期和日期；选择 `2026-08-07` 后显示本地空态，按钮仍为“更新”，没有生成该日期文件。`2026-08-10` Parquet 的 mtime、16,607 bytes 和 SHA-256 `7c6916a86b70ce3e66aa63ce09c79e9538918848056bddf86a6d84dec6e78754` 均未变化；返回 `2026-08-10` 后 241 分钟/22 事件图表正常，控制台无 error。

#### 当前状态与用户验收

- 当前状态：`verified / 待用户验收`。代码、自动回归、生产构建、正式本地数据、桌面/移动界面和主交互均已验证；是否符合长期看板使用习惯仍由用户确认后才能进入 `accepted`。

#### 阻塞、回滚和下一步

- 无阻塞。回滚用户台时移除 `MarketPulsePanel`、数据页同步卡和三条 `focus/as_of` 深链；数据资产按数据平台日志独立回滚，不能由前端回滚顺带删除。
- 当前没有自动轮询、自动模型调用、后台全量回补或 go-stock Runtime 依赖；后续只有用户实际使用后提出新的阅读/密度问题才继续调整。

### hermes_agent_personal_chat_sandbox

#### 用户目标与可见结果

- 用户希望在 AI 板块看到一个可直接对话的 `one-trading` 专属 Hermes Agent 分类，并先在本机实际试用。
- `/ai` 新增“Hermes Agent 对话”卡片；`/ai/hermes` 提供连接状态、Profile/模型/工具边界、新对话、历史恢复、流式消息和本地保存告知；本轮状态栏进一步显示 `grok-4.5`、`Holographic 长期记忆`与`用户台数据 · 68 个只读视图`。
- 页面明确说明已接通行情、自选、K 线、财务、指数、策略、监控、数据目录、扩展数据和已保存报告；账户、交易、所有写操作与当前尚未进入运行面的公告仍排除。
- 本轮增加历史 Session 模块：桌面端为 15.5rem 左侧轨道，展示标题/首条问题预览、消息数和最后活跃时间；点击后恢复对应完整回答。375/768px 下改为顶部横向历史条，避免挤压正文宽度。
- 页面改为占满可用 App 视口；消息区独立滚动，输入框和保存提示固定在内容区底部，不再跟随长回答向下漂移。新 Session 用首条用户消息生成标题，空 Session 不进入历史列表。
- 本轮把 Profile 连接、Profile 名称、模型、Holographic 长期记忆、用户台只读视图和重新检查入口全部移入左下角“Agent 设置”齿轮面板，正文顶部不再保留状态栏。历史刷新按钮移动到 Session 数量旁；桌面侧栏可折叠为 4rem 图标轨道，刷新页面后保留折叠偏好。
- 本轮在同一 Agent 设置面板新增 `图表 Skill · Lieflat Charts`。该状态来自 one-trading 后端对 Hermes `/v1/skills` 的只读检查，不让前端读取 Profile 配置或本机 Skill 路径；未启用时明确显示“未启用”。
- 每条历史对话右上角新增“三点”菜单，只提供“重命名”和“删除对话”两个动作。重命名在当前条目内完成并支持保存/取消；删除先显示不可撤销提示和二次确认。删除当前会话成功后，页面回到新对话空态，不保留失效 Session 引用。

#### GitHub 情报与固定上游点

- 上游 headless Runtime 的完整审阅、Hermes/Pi 对比、许可证与采用判断归 Agent 台：`/Users/simon/Trading/Agent台GitHub项目借鉴记录.md#7-headless-个人-agent-harnesshermes-agent-与-pi`。
- 用户台只保留产品入口与可见行为，不复制 Runtime、tenant、memory 或权限事实。

#### 本地路由、Module、Adapter 与依赖接口

- 路由/页面：`frontend/src/router.tsx`、`frontend/src/pages/AIHub.tsx`、`frontend/src/pages/HermesAgentChat.tsx`。
- 前端 Adapter：`frontend/src/lib/api.ts`；只调用 one-trading `/api/hermes-agent/*`，Session 列表使用 `GET`，标题修改与删除分别使用 `PATCH /sessions/{id}`、`DELETE /sessions/{id}`，不读取 Profile 文件或任何 credential。
- Agent 依赖：后端 Hermes Adapter、Profile、toolset、模型路由和 Session/记忆权限归 `/Users/simon/Trading/one-trading/docs/agent-platform-development-log.md#36-hermes-one-trading-个人-agent-对话沙箱`。
- 数据台依赖：只消费现有只读 API；没有修改 Provider、Parquet、schema、Catalog 数据资产或触发同步。Agent 数据 allowlist、鉴权、脱敏与输出预算归 Agent 台日志。

#### 自动检查与构建

- 原实现 `HermesAgentChat.test.tsx` 与 `AIHub.test.tsx` 共 5 项通过；本轮 `HermesAgentChat.test.tsx` 5 项通过，覆盖新 Session 创建/流式回复、历史 Session 切换、齿轮设置面板、`图表 Skill / Lieflat Charts` 状态、折叠偏好、重命名持久化和删除二次确认；目标 ESLint 与 TypeScript/Vite 生产构建通过。
- 构建仅保留项目既有 `api.ts` 混合动静态导入和大 bundle warning，没有新增错误。

#### Codex 内置浏览器目标运行面验证

- `http://127.0.0.1:3011/ai` 可见新分类并能进入 `/ai/hermes`；本轮页面实际显示 `Profile：one-trading`、`模型：grok-4.5`、`Holographic 长期记忆`和`用户台数据 · 68 个只读视图`。
- 新对话真实完成 market/stock/financial 三领域目录发现，以及市场总览、自选增强数据、600519.SH 财务指标三项查询；最终回答含视图名、时间和来源口径，并明确没有账户或交易数据。
- 历史侧栏真实加载 10 条非空 Session；点击最近一条后恢复 15 条消息及完整历史回答，当前项具有明确选中态。
- 默认桌面、375×812 与 768×900 运行面均验证：输入区底边分别贴合视口底部，375/768 页面 `scrollWidth == clientWidth`，没有横向溢出；浏览器控制台本轮 error 为 0。
- 齿轮面板真实显示 `Profile 已连接 / one-trading / grok-4.5 / Holographic / 68 个只读视图`；侧栏折叠后仅保留可访问名称完整的 Session 图标、刷新、展开和设置入口，页面重载仍保持折叠，随后已恢复展开。375px 下齿轮入口仍可用且 `scrollWidth == clientWidth`；控制台 error 为 0。
- 本轮为避免干扰监听 `3011` 的发布版，在无后台行情/调度的 `127.0.0.1:3018` 开发验收后端与 Vite `127.0.0.1:3021` 上复核。齿轮面板新增行真实显示 `图表 Skill · Lieflat Charts`；点击历史 Session“Lieflat Charts 连通验收”后，页面恢复完整回答，能看到 `market_overview`、`as_of=2026-08-10`、F1/F5/L2 候选、最终 `F1 Rung Bars` 与实际工具列表。控制台 error 为 0，仅有项目既有 React Router v7 future flag warning。
- 本轮使用同一代码构建的隔离 `127.0.0.1:3118/ai/hermes` 复核：10 条真实历史 Session 均显示可访问的“三点”入口；菜单、行内重命名输入、保存/取消、删除警告与确认/取消均可见。验收只输入临时标题后取消，并打开删除确认后取消，没有重命名或删除任何真实 Session；1280px 页面无横向溢出，控制台 error 为 0。默认 `3018` 既有长驻后端当时无响应，因此未重启或替换该进程；隔离验收进程已退出。

#### 当前状态与用户验收

- 当前状态：`verified / 待用户验收`。入口、交互、真实两轮对话和边界文案已验证；用户实际使用后的价值与体验仍待确认。

#### 阻塞、回滚和下一步

- 当前功能代码无阻塞；本轮为试用启动的 `3018/3021` 是独立开发运行面，未替换 `3011` 发布版，也未启动数据后台任务。回滚本轮 Skill 状态行只需移除状态字段与 UI definition；Runtime 的 exact external dir、权限、备份和回滚归 Agent 台开发日志 3.7。不会自动删除 Hermes Session/长期记忆，本轮没有执行真实清理。
- 多用户、公告数据、主动回测工具和生产部署属于 Agent 台后续独立工作，不因页面可用而自动获得授权。

### industry_analysis_full_market_treemap

#### 用户目标与可见结果

- 按“先修数据，再复现热力图”的顺序完成：行业分析不再用 508/509 只 `CSI500 + 自选股` 行情计算全市场；页面现显示 90 个二级行业、5,539 只行业标的，并新增类似东方财富大盘星图的行业/个股矩形树图。
- 热力图使用 A 股红涨绿跌、灰色平盘；上层为行业、下层为个股，行业标题显示平均涨跌与 `行情/成员`，个股块显示简称和涨跌幅。默认面积按流通市值，可切换成交额和等权。
- 标题区同时显示 `行情 5,207/5,540`、`行业着色 5,193/5,539` 与当前质量状态“盘中快照”；缺失行情不会被误算成 0% 平盘。悬浮提示包含代码、行业、涨跌、流通市值、成交额和换手率；点击行业沿用详情选择，点击个股沿用 `StockPreviewDialog`。

#### 本地路由、Module 与跨台依赖

- 路由仍为 `/industry-analysis`；新增 `frontend/src/components/IndustryTreemap.tsx`，接入点为 `frontend/src/pages/IndustryAnalysis.tsx`，API 契约位于 `frontend/src/lib/api.ts`。
- 组件沿用 one-trading 现有卡片、按钮、颜色语义和股票预览，不复制东方财富品牌、侧栏或控制面板。参考图只作为热力图层级、面积和色彩密度的视觉真相。
- 全市场快照服务、行业分类刷新、覆盖口径、备份与剩余缺口见 `/Users/simon/Trading/one-trading/docs/data-platform-development-log.md#412-market_snapshot-全市场行业分析服务视图`。

#### 自动检查、构建与正式运行面

- 新增 3 项组件测试，覆盖 ECharts 两级 treemap、只纳入有效报价、覆盖徽标、三种面积口径、行业/个股回调，以及最大化、焦点、`Esc` 退出和 body 滚动恢复；前端全量 29 个测试文件、113 项通过。
- 新组件与测试目标 ESLint 通过；TypeScript/Vite 生产构建通过。构建只保留项目既有 `api.ts` 混合动静态导入和大 chunk 提醒。
- Codex 内置浏览器正式 `http://127.0.0.1:3011/industry-analysis`：页面显示 `2026-08-10 · 90 个行业 · 5539 只标的`，行情/行业着色覆盖徽标与数据台一致；流通市值、成交额、等权三按钮实测均可进入 `aria-pressed=true`，最终恢复流通市值。
- 首轮真实截图发现 ECharts 不接受空格式 HSL 而回退为默认蓝紫调色板，且 `leafDepth=1` 只显示行业钻取箭头；改为兼容 HSL 语法和 `leafDepth=2` 后，红涨绿跌、行业标题与个股文字完整出现。控制台最终无 error。
- 参考与实现同为 `2048×1024` 对照；实现截图：`/Users/simon/.codex/visualizations/2026/08/07/019fdb0d-0362-7ca2-879c-9608abaab43b/industry-heatmap-audit/implemented-2048x1024-20260810.png`，视觉 QA 见 `/Users/simon/Trading/one-trading/design-qa.md`。

#### 2026-08-10 首屏与最大化显示复调

- 按用户标注把 `IndustryTreemap` 从资金流和领涨/领跌之后移动到 `PageHeader` 下方的内容区第一位；现在进入行业分析后，热力图先于五项 KPI、行业资金流和行业矩阵出现。
- 普通模式画布由 `540/660px` 提高为 `620/680/720px` 响应式高度；行业标题提升到 14px/700，个股提升到 12px/500，tooltip 提升到 13px 并增强边框、行距和阴影。ECharts canvas 显式采用最高 2 倍 DPR，减少高密度屏幕文字与边界发虚。
- 最大化入口放在标题栏右侧，与面积口径和色阶同组，避免放在左下角遮挡股票块，也比画布内悬浮按钮更容易发现。入口使用项目既有 Lucide `Maximize2/Minimize2`；最大化通过 portal 占满应用视口，保留来源、覆盖、面积口径和色阶。
- 最大化时锁定背景滚动、将焦点移到“退出全屏”，支持按钮或 `Esc` 退出；ECharts 在普通/最大化 DOM 切换时销毁并重新初始化，ResizeObserver、面积口径、行业/个股点击和 tooltip 均保持工作。
- Codex 内置浏览器正式 `3011`：`1382×1024` 首屏截图确认热力图紧接标题且 KPI 在其后；`2048×1024` 最大化悬浮截图与用户参考同尺寸比较，行业/个股层级、暗化聚焦和 tooltip 对应；`1024×768` 页面 `scrollWidth=clientWidth=1024`，最大化按钮仍可见。控制台 error 为 0。
- 证据目录：`/Users/simon/.codex/visualizations/2026/08/10/industry-heatmap-top-fullscreen/`；详细视觉比较见 `/Users/simon/Trading/one-trading/design-qa.md#行业分析热力图首屏与最大化设计-qa`。

#### 当前状态、回滚和下一步

- 当前状态：`verified / 待用户验收`。正式页面、实际数据、三种面积口径、视觉对照、自动测试、构建和控制台均已验证；北交所与少量行业映射缺口按数据台事实继续显示，不把界面完成写成数据 100% 完整。
- 回滚用户台时移除 `IndustryTreemap` 接入并恢复原热度 chip 布局；数据回滚按数据平台日志单独执行，不能由 UI 回滚顺带恢复或删除 Parquet。
- 后续只有用户实际使用后提出新的密度或筛选需求才继续调整；全屏需求已在本轮完成。本轮不复制东方财富整页产品，也不新增自动外连、轮询或数据写操作。

### android_private_rc_v2_manual_fallback

#### 用户目标与可见结果

- Android 私人 RC 默认继续打开 Zeabur 主入口；主页面加载失败后不再停在白屏或让旧“重新连接”按钮只重载本地错误页，而是显示 APK 内置失败页。
- 失败页只有两个明确动作：“重试主线路”和“使用备用线路”。备用入口固定为 `https://one-trading-backup.siqiho.workers.dev`，由用户主动选择；不做测速排名、节点池、熔断、定时健康检查、远程配置或自动请求重放。
- 备用域名是 Capacitor `allowNavigation` 的唯一新增项；主入口仍是固定 `server.url`。两个按钮只接受内置 HTTPS allowlist，不接收用户 URL、query target 或任意 Host。

#### GitHub 情报与固定上游点

- 完整项目组审阅、recursive tree 覆盖、许可证与采用/排除判断见 `/Users/simon/Trading/用户台GitHub项目借鉴记录.md#34-android-私人-rc-主备用入口项目组`。
- 本轮只采用固定候选和本地失败页的产品机制；没有复制或安装 RetrofitUrlManager、MultiBaseUrls、RetrofitHelper、domainfront/fronted、llm-failover 或 redirect-when-blocked。

#### 本地路由、Module、Adapter 与依赖接口

- 目标发布树：`/Users/simon/Trading/one-trading-release`，branch `release/private-server-android`；开发主树业务代码未改。
- Capacitor 入口 allowlist 与 Android UA：`frontend/capacitor.config.ts`。
- 完全内置、离线可用的失败页与两个固定按钮：`frontend/public/offline.html`。
- Android 版本：`frontend/android/app/build.gradle` 为 `versionCode 2 / versionName 0.1.69`；前端 package 版本同步为 `0.1.69`。
- 回归：`frontend/src/lib/__tests__/offlineFallback.test.ts`，锁定两个 HTTPS endpoint、用户点击后才切换、无 `location.reload`、定时器或 `fetch()` 自动探测，以及 Capacitor 主/备用配置。
- 改造前备份：`/Users/simon/备份/codex/20260811_212933-one-trading-android-v2-before-fallback`；原始路径和备份原因见其中 `README.md`，不含任何凭据。

#### 自动检查、构建与签名产物

- 前端全量 31 个测试文件、122 项通过；目标 ESLint、TypeScript/Vite production build、`git diff --check` 通过。构建只保留既有 `api.ts` 混合导入和大 chunk warning。
- `scripts/build-android-release.sh` 使用项目既有 JDK 21、Android SDK 与私有发布签名完成 release build；APK Signature Scheme v2/v3 验证通过，签名证书 SHA-256 继续为 `7862b68a0f5b85dbef5236b03970f8c39e4017f9ebb1c5129afeb941d278d90d`。
- 本地签名 APK：`/Users/simon/Trading/one-trading-release/releases/android/one-trading-private-0.1.69.apk`，4,490,065 bytes，SHA-256 `27e275f220fcdf26bf0cd3592051c6a6542569a08c0e3d84f2937a828d2d24b1`。
- APK badging 确认 package `com.simon.onetrading`、`versionCode=2`、`versionName=0.1.69`、min API 24、target/compile API 36；打包后的 `capacitor.config.json` 仍为 Zeabur 主 URL、唯一 Worker allowNavigation、HTTPS only 和本地 `offline.html`。

#### Android 目标运行面与故障恢复验证

- 明确目标：AVD `Codex_API_36`、ADB serial `emulator-5554`、正式签名 APK。模拟器原有 `0.1.68` debug 包证书为 Android Debug，先只读提取确认；磁盘 V1/V2 正式 APK 则使用同一发布证书。
- 正式签名 V1 安装后执行 `adb install -r` 原位升级到 V2 成功；`versionCode 1 → 2`，`firstInstallTime=2026-08-11 21:41:25` 在升级后保持不变，证明升级路径没有卸载应用数据。
- 主/备用 `/health` 均返回 `status=ok`、`release_channel=private`、server version `0.1.68` 与同一 build SHA `375fc1e522814950b2f2d1751053e150f8776dab`；两边根 HTML 与备用 `/api/auth/status` 为 200。
- WebView 网络故障注入后，Capacitor 自动从远程主页面转到 `https://localhost/offline.html`；DOM 精确出现两个固定 endpoint。恢复网络后分别点击两按钮，主入口进入 `one-trading-private-simon.zeabur.app/login`，备用入口在同一 `MainActivity` WebView 内进入 `one-trading-backup.siqiho.workers.dev/login`。
- V1→V2 升级后的真实冷启动还捕获到一次主入口失败并自然进入内置页；显式恢复模拟网络状态后，点击备用线路成功进入 Worker 多用户登录页。没有请求或输入用户名、密码、Cookie、Token。
- 目标进程无 `FATAL EXCEPTION`、`AndroidRuntime` crash、`net::ERR`、未捕获 `TypeError/SyntaxError`。以 `-no-window` 运行 AVD 时 ADB surface 截屏为空白，但同一 WebView 的 DevTools DOM、布局与 `Page.captureScreenshot` 完整；这是 headless compositor 取证限制，不是应用白屏。
- 最终证据：`/Users/simon/.codex/visualizations/2026/08/11/019ff01a-2875-7fc3-8586-8a023e279600/android-v2/{offline-fallback,primary-recovery,backup-recovery}.png`。

#### APK 下载站发布与线上复核

- 2026-08-11 将已签名的 `0.1.69` 原位部署到既有 Zeabur `one-trading-android` 服务；Service ID 仍为 `6a762f1de4a69d66638cca79`，新 Deployment ID 为 `6a7b2a410d41a78958bb0a27`，状态 `RUNNING`。本轮没有重启或修改 `one-trading` 应用服务，也没有改动 Cloudflare Worker。
- 发布前备份：`/Users/simon/备份/codex/20260811-215454-one-trading-android-download-before-v2`，包含旧站点、`0.1.68` APK、部署脚本和回滚说明；原始路径与备份原因见其中 `README.md`。
- 上传前检查无阻塞项；本地 Caddy Docker 镜像构建和 GET 冒烟通过，`/health` 返回 `ok`，页面版本/链接/摘要均为 V2，下载文件为 4,490,065 bytes 且 SHA-256 精确匹配。Zeabur 构建日志确认使用目标根 `Dockerfile` 和 `COPY public /srv`，运行日志确认新容器成功启动。
- 正式域名 GET 复核：安装页展示 `0.1.69`，V2 响应为 `application/vnd.android.package-archive` 与 attachment disposition；重新下载后的 SHA-256 为 `27e275f220fcdf26bf0cd3592051c6a6542569a08c0e3d84f2937a828d2d24b1`，badging 仍为 `versionCode=2 / versionName=0.1.69`，APK v2/v3 签名及证书摘要均通过。Codex 内置浏览器同时确认版本、按钮目标和页面摘要，控制台无 warning/error。
- 旧 `/one-trading-private-0.1.68.apk` 继续返回 206 Range 响应，未删除旧链接；下载页当前入口为 `https://one-trading-android-simon.zeabur.app/one-trading-private-0.1.69.apk`。

#### 当前状态、边界与回滚

- 当前状态：APK 功能为 `verified / 待 OPPO 与三网真机验收`；APK 下载服务已发布并在正式域名复核。代码、自动检查、签名构建、正式 V1→V2 覆盖升级、主/备用在线响应、真实 WebView 失败页、两条恢复路径和线上分发文件均已验证。
- 现实边界：A/B 最终依赖同一 Zeabur 后端，服务器本身宕机时两条都失败；两个域名的 Cookie/localStorage 分离，首次切换可能重新登录；`workers.dev` 仍需中国大陆三网真机验证，模拟器不能替代 OPPO/ColorOS 或移动/联通/电信验收。
- 下载站回滚可用发布前备份重新部署旧页面和 `0.1.68`；旧 APK 直链当前也仍保留。已经安装 V2 的设备不能直接降 `versionCode`，如需恢复旧行为，应以更高 versionCode 重建，或卸载后安装 V1（会清除本地 Cookie/应用数据）。应用服务器、Cloudflare Worker 和用户数据不需要回滚。

### android_private_rc_v3_native_notifications_voice_and_pickers

#### 用户目标与可见结果

- 在已发布的 V2 基础上发布 V3：现有监控规则命中后可进入 Android 系统通知栏；文本输入框获得焦点时出现原生麦克风按钮，识别结果回填当前输入框。
- 通知首次开启先显示 one-trading 自己的用途说明，只有用户点击“开启并测试”才出现 Android 13+ 系统授权框。启用后建立独立“到价与策略提醒”高重要性 channel；通知点击返回 `/monitor`。
- 语音入口排除密码、只读和禁用字段；首次使用才请求录音权限。它调用手机自带 `SpeechRecognizer` 的 `zh-CN` 自由口述模式，不自行保存音频文件。
- 照片和文件沿用 Capacitor WebView 的系统文件选择器：页面已有 `<input type="file">` 时由 Android 只授予用户选中 URI 的临时访问权。V3 不申请整库照片、全盘存储或 all-files 权限，也没有虚构一个新的上传服务或 Hermes 附件协议。

#### 本地 Module、Adapter 与权限边界

- 发布树：`/Users/simon/Trading/one-trading-release`，branch `release/private-server-android`；本轮不部署 one-trading 主服务器，也不修改 Cloudflare Worker。
- Android 入口与可信域注入：`frontend/android/app/src/main/java/com/simon/onetrading/MainActivity.java`；只对固定 Zeabur 主域和固定 Worker 备用域注入 V3 bridge。
- 原生权限与语音 Module：`OneTradingNativePlugin.java`；能力只包括系统语音识别、停止/取消和打开应用设置。
- WebView 轻量 Adapter：`frontend/android/app/src/main/assets/one-trading-v3-native-bridge.js`；复用现有 `/api/intraday/stream` 的 `strategy_alert`，不复制规则引擎、不轮询行情、不自动重放写请求。
- Android 系统通知采用官方 `@capacitor/local-notifications@8.2.1`。V3 只即时发布 SSE 事件，不使用 exact alarm；Manifest merge 明确移除插件默认但本版不用的 `RECEIVE_BOOT_COMPLETED` 与 `WAKE_LOCK`。
- 最终 APK 普通/运行时权限为 `INTERNET`、`POST_NOTIFICATIONS`、`RECORD_AUDIO`、`MODIFY_AUDIO_SETTINGS` 和 AndroidX 自有 signature permission。不存在 `CAMERA`、`READ_MEDIA_*`、legacy external storage、`MANAGE_EXTERNAL_STORAGE`、定位、联系人、短信、电话、悬浮窗、无障碍或 exact-alarm 权限。
- 版本：`versionCode 3 / versionName 0.1.70`；保留 V2 的固定主入口、唯一 Worker allowNavigation、HTTPS only、WebView debugging off、Android backup off 和内置失败页。
- 修改前备份：`/Users/simon/备份/codex/20260812_021125-one-trading-android-v3-before-native-capabilities`；其中 `README.md` 逐项记录原始路径、时间与备份原因，不含访问凭据或签名私钥副本。

#### 自动检查、构建与签名产物

- 新增 3 项 V3 bridge 回归，覆盖语音识别结果进入当前文本框、服务器价格事件转为 importance 5 原生通知，以及 Manifest 不引入相机/媒体库/外部存储权限。
- 前端全量 33 个测试文件、127 项通过；TypeScript/Vite production build、Capacitor sync、raw bridge `node --check`、Android clean release build、Lint Vital 和 `git diff --check` 通过。构建只保留项目既有混合动静态 import、大 bundle 与 Android SDK XML 工具版本 warning。
- 本地签名 APK：`/Users/simon/Trading/one-trading-release/releases/android/one-trading-private-0.1.70.apk`，4,518,933 bytes，SHA-256 `06222abcd712eb14cf63f65bbd7ae52e592eed03fbef2e7fc547176a47c5831d`。
- badging：package `com.simon.onetrading`、`versionCode=3`、`versionName=0.1.70`、min API 24、target/compile API 36。APK Signature Scheme v2/v3 通过，证书 SHA-256 仍为 `7862b68a0f5b85dbef5236b03970f8c39e4017f9ebb1c5129afeb941d278d90d`。
- 包内复核确认 `one-trading-v3-native-bridge.js`、LocalNotifications plugin 描述与 `one-trading-android/0.1.70` 配置均存在；签名 APK 不含服务器密码、API key 或签名私钥。

#### Android 目标运行面验证

- 明确目标：`Codex_API_36` / `emulator-5554` / Android 16 API 36 / 正式签名 APK；没有请求、读取或输入用户名、密码、Cookie、Token。
- 模拟器原有正式 V2 为 `versionCode 2 / versionName 0.1.69`，`firstInstallTime=2026-08-11 21:41:25`。执行 `adb install -r` 后变为 V3，`firstInstallTime` 完全不变，证明同证书原位升级没有清除应用数据。
- V3 冷启动真实显示多用户登录页、左下“开启通知”和当前文本字段右侧麦克风按钮。点击通知入口后，先显示用途说明，再出现 Android 系统通知授权框。
- 授权后真实发布 `one-trading · 通知已开启`；Notification Manager 确认 package、importance `5`、channel `one-trading-market-alerts-v3`、默认声音/震动、正确图标和 `AUTO_CANCEL`。通知栏截图显示预期中文标题与正文。
- 聚焦用户名字段并点击麦克风后，Android 系统录音授权框真实出现；授权后 runtime permission 为 granted，Google RecognitionService 日志确认 microphone opened、audio session `OPENED` 并进入 `onStartOfSpeech`。目标 App 无 `FATAL EXCEPTION`。
- 该 headless 模拟器没有可用的 `zh-CN` language pack/真实话筒输入，系统 recognizer 最终报告 language-pack error；因此这里只证明权限、录音流和识别调用链，不能把它写成真实中文转录已验收。识别结果回填由 bridge 自动测试固定，仍需 OPPO/Android 真机说一句中文做最终消费验证。
- 照片/文件选择器由 Capacitor `BridgeWebChromeClient.onShowFileChooser` 的真实 Android 系统 chooser 提供，最终 Manifest 证明无宽权限；本轮未使用登录凭据进入管理员上传页面，因此没有把“系统 picker 能力存在”写成某个真实业务文件已上传。
- 视觉证据：`/Users/simon/.codex/visualizations/2026/08/12/android-v3/`，含初始入口、通知说明、两项系统权限框、真实测试通知与语音监听状态截图。

#### APK 下载站发布与线上复核

- 2026-08-12 将 V3 原位部署到既有 Zeabur `one-trading-android` 服务；Service ID `6a762f1de4a69d66638cca79`，最终 Deployment ID `6a7b6b970d41a78958bb15f2`，状态 `RUNNING`。Caddy 运行日志确认新 image 拉取、容器启动并监听 `:8080`。
- Codex 内置浏览器正式页 `https://one-trading-android-simon.zeabur.app/` 显示 `0.1.70 · V3 APK`、正确直链、SHA-256 与功能摘要；console warning/error 均为 0。
- HTTPS 重新下载为 4,518,933 bytes，SHA-256 与本地一致且 `cmp` 逐字节相同；响应为 `application/vnd.android.package-archive` 与 attachment disposition，badging、v2/v3 签名和证书摘要复核通过。
- 旧 `0.1.69` 直链继续返回 200、4,490,065 bytes 与原 SHA-256 `27e275f220fcdf26bf0cd3592051c6a6542569a08c0e3d84f2937a828d2d24b1`，没有删除 V1/V2 rollback artifacts。
- 主 Zeabur 与备用 Worker `/health` 仍返回同一 `version=0.1.68`、private channel 和 build SHA `375fc1e522814950b2f2d1751053e150f8776dab`；本轮只部署 APK 下载服务。

#### 当前状态、边界与回滚

- 当前状态：V3 功能 `verified`，APK 下载分发面已 `production`；用户验收、OPPO/ColorOS、真实中文转录、照片/文件业务上传和中国大陆三网仍待真机完成，不能提前标为 `accepted`。
- 通知事实边界：现有服务器监控仍负责规则与命中，V3 只把当前 WebView 收到的 SSE 事件转换为 Android 通知。APK 进程/WebView 存活时可在前后台收到；如果 Android 已彻底杀死或强制停止进程，SSE 不再运行。可靠的 killed-process delivery 需要后续 FCM 等服务器 push，V3 没有用耗电常驻前台服务、WorkManager 低频轮询或 exact alarm 冒充实时推送。
- 语音隐私边界：Android 官方 `SpeechRecognizer` 可能由手机选择本地或网络识别服务；App 不保存原始录音。用户可以拒绝/撤销权限，密码字段永不显示 V3 麦克风入口。
- 下载站可用本轮备份恢复旧页面并重新部署；`0.1.69` 直链已保留。已安装 V3 的手机不能直接降 versionCode；如需保留 App 数据回退，应以 versionCode 4 发布回退构建，卸载安装 V2 会清除本地 App 数据。主服务器、Cloudflare Worker 和用户数据均不需要回滚。

### multi_user_release_capabilities_port

#### 用户目标与可见结果

- 以 `/Users/simon/Trading/one-trading` 为唯一主开发树，合入发布树的多用户登录、角色菜单、用户管理、个人持仓、个人策略/回测历史、账户设置和 Android/离线能力。
- 普通用户继续读取服务器共享市场数据，但看不到用户管理、监控和服务器级同步/清理操作；自选、持仓、策略、报告、偏好和 Agent 会话仍按账户隔离。
- 保留主开发树原有市场脉搏、行情快照补 K 线、行业矩形树图和股票上下文深链，没有用发布树旧实现覆盖这些能力。

#### 本地路由、Module、Adapter 与依赖接口

- 主要路由：`/login`、`/settings`、`/admin/users`、`/data`、`/trading`、`/ai/hermes`。
- 主要前端 Module：`frontend/src/components/Layout.tsx`、`frontend/src/pages/Auth.tsx`、`AdminUsers.tsx`、`Data.tsx`、`Trading.tsx`、`Settings.tsx`、`HermesAgentChat.tsx`。
- 数据与 Agent 边界分别见本地数据台日志 `5.1 shared_market_multiuser_boundary` 和 Agent 台日志 `3.8 多用户受管 Hermes Profile`。

#### 自动检查与构建

- as_of 2026-08-12，基底 HEAD `56d481076c008efca9ff40db8f5c89139bb7f600` 加本轮未提交移植：前端 35 个测试文件、132 项通过；TypeScript/Vite 生产构建通过；ESLint 0 error、33 项既有 warning。
- 后端全量 393 项通过、1 项环境型跳过；`uv run` 可编辑安装、Python compile、`git diff --check` 均通过。
- 最新生产前端 bundle 已通过 `cap sync android` 写入 Android 工程；Capacitor Doctor 确认 Core/CLI/Android 均为 8.5.0。本轮没有生成签名 APK，也没有部署。
- `Dockerfile.one-trading` 本地完整构建通过；短暂容器确认 Hermes multiplex gateway 先就绪、FastAPI 后启动，两个账户的 Profile 状态均为 connected。验证容器与镜像随后已删除。

#### Codex 内置浏览器目标运行面验证

- as_of 2026-08-12 使用隔离临时 `DATA_DIR` 和 `127.0.0.1:38118` 验收，不占用既有 `3011/3018`；验收后进程和临时账户/凭据/数据已清理。
- 管理员页面显示 3 个账户、2 个普通用户和两个独立 Profile；普通用户菜单不含“用户管理/监控中心”，只读数据页只显示总览与目录。
- Alice 与 Bob 读取相同的 241 条市场脉搏分钟点和 19 条事件；Alice 的 1 条自选和 1 条持仓在 Bob 侧均为空。Alice 的交易页显示个人持仓账本，设置页显示独立用户空间和每日 AI 额度。
- 普通用户访问用户管理、数据清除和共享市场同步均为 403；浏览器控制台 error 为 0。

#### 当前状态、回滚和下一步

- 当前状态：`verified`，尚未标记 `accepted / production`；线上实例未修改或重新部署。
- 修改前备份位于 `/Users/simon/备份/codex/20260812-003726-one-trading-pre-release-feature-port`，原路径为 `/Users/simon/Trading/one-trading`。
- 回滚应按备份恢复本地主开发树；身份库、租户目录和 Hermes 运行时的真实迁移/部署仍需单独备份与授权。

### settings_account_passwordless_owner_state

#### 用户目标与可见结果

- 修复本地主开发实例 `http://127.0.0.1:3011/settings` 的“我的账号”卡片：当 `/api/auth/status` 已返回 `configured=false / authenticated=false / user=null` 时，不再永久显示“加载中…”和错误的“独立用户空间”。
- 本地未设置访问密码时，页面现在显示 `本地管理员 / 尚未设置访问密码`；隐藏无意义的“退出登录”和“修改密码”，改为明确的“设置访问密码”说明与入口。
- 已登录管理员和普通用户仍显示真实用户名、角色、退出登录、修改密码及普通用户 AI 额度；请求 pending 与失败分别显示真实加载态和明确错误，不再混用 `user=null`。

#### 本地路由、Module、Adapter 与权限边界

- 只修改用户台 `frontend/src/pages/settings/Account.tsx`，新增同目录组件测试；后端认证 API、身份库、密码、Session、Cookie、用户数据和 Agent Profile 均未修改。
- “前往设置访问密码”复用现有 `/login?redirect=/settings` 初始化流程；后端原有 `/api/auth/setup` 本机/内网限制仍是唯一设置密码边界。本轮浏览器只验证路由与表单出现，没有填写或提交密码。
- 修改前备份：`/Users/simon/备份/codex/20260812-154711-one-trading-settings-account-state-fix`，README 记录原始路径、时间与回滚方式，不含账户凭据或身份数据。

#### 自动检查与构建

- 新增 4 项组件回归，先在旧实现上得到 `3 failed / 1 passed`，精确覆盖真实 loading、本地免密码 owner、已登录管理员和接口失败；修复后 4 项全部通过。
- Account、Auth 与 Hermes 页面聚焦回归共 `13 passed`；TypeScript 与 Vite production build 通过。构建只保留项目既有 `api.ts` 混合动静态 import 和大 chunk warning。

#### Codex 内置浏览器目标运行面验证

- 真实 `3011/settings` 在后端 `users=0 / sessions=0` 的本地兼容 owner 状态下显示 `本地管理员 / 尚未设置访问密码`；精确计数：`加载中…=0`、`独立用户空间=0`、`退出登录=0`、`当前密码输入=0`、设置密码入口 `=1`。
- 点击入口后进入现有“设置管理员密码 / 设置并进入”页面，访问密码输入框存在；未输入或提交任何密码。返回设置页后结果保持不变，浏览器控制台 error 为 0，仅有项目既有 React Router v7 future flag warning。

#### 当前状态、回滚和下一步

- 当前本地主开发运行面状态：`verified`；用户尚未进行实际设置密码或已登录账号验收，因此不标记 `accepted / production`。
- 回滚只需从上述备份恢复 `Account.tsx` 和本日志；不需要、也不得回滚身份库、密码、Session、Hermes Runtime 或用户数据。

### public_account_registration

#### 用户目标与可见结果

- 本地主开发版本在服务器管理员已初始化后，登录页默认显示“没有账号？创建一个”。
- 访客可输入 3–32 位用户名、至少 6 位密码和确认密码，注册成功后直接进入普通用户工作台；普通用户仍不获得管理员菜单或服务器级数据写权限。
- 邀请码默认留空，表示任何访客可注册；注册仍受同一来源每日 3 次和最多 100 个普通账户限制。部署可用 `PUBLIC_REGISTRATION_ENABLED=false` 紧急隐藏入口并拒绝新注册，不删除已有账户。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台路由与表单：`/login`、`frontend/src/pages/Auth.tsx`。
- 后端接口：`GET /api/auth/status`、`POST /api/auth/register`；账户继续写入 `DATA_DIR/control/identity.sqlite3`，个人数据继续位于 `DATA_DIR/tenants/<user_id>/user_data/`。
- 默认策略：`backend/app/config.py`、`.env.example`、`Dockerfile.one-trading`；显式环境变量继续优先于代码默认值。
- 修改前备份：`/Users/simon/备份/codex/20260812-155010-one-trading-pre-public-registration`，其中 `README.md` 记录原始路径与备份原因，不含 `.env`、账户库或凭据。

#### 自动检查与构建

- 后端认证聚焦回归 `10 passed`；后端全量 `400 passed / 2 skipped`。跳过项和 warning 均为既有环境/弃用提示，没有本轮认证失败。
- 前端全量 `36` 个测试文件、`137` 项通过；TypeScript 与 Vite production build 通过。构建只保留项目既有 `api.ts` 混合动静态 import 和大 chunk warning。
- `Dockerfile.one-trading` 完整构建通过；镜像元数据确认 `PUBLIC_REGISTRATION_ENABLED=true`、`RELEASE_CHANNEL=private` 和 `DATA_DIR=/app/data`。临时验证镜像随后删除，未运行或部署。
- `git diff --check` 通过；隔离运行结果见本条后续验证记录。

#### Codex 内置浏览器目标运行面验证

- 使用独立临时 `DATA_DIR=/private/tmp/one-trading-registration-acceptance-20260812`、`127.0.0.1:38128` 和 393×852 移动端视口验证；未读取或修改正式账户库。
- 未登录页真实返回 `registration_enabled=true / invite_required=false`，显示“没有账号？创建一个”；切换后显示用户名、密码、确认密码和“注册并进入”。
- 浏览器注册 `regcheck_0812` 成功并落到普通用户看板；菜单不含“用户管理”和“监控中心”。设置页显示该用户名、“独立用户空间”和每日共享 AI 额度。
- 第二个隔离账户通过 HTTP 注册成功；临时身份库为 1 个管理员 + 2 个普通用户，SQLite `integrity_check=ok`，同源当日注册计数为 2。普通用户访问 `/api/admin/users` 和 `POST /api/data/clear` 均返回 `403`。
- 单独以 `PUBLIC_REGISTRATION_ENABLED=false` 启动 `127.0.0.1:38129`：状态返回关闭，直接调用注册接口返回 `403 公开注册尚未开启`，证明紧急关停路径仍有效。
- 浏览器控制台 error/warn 为 0；验收完成后临时进程、Cookie 文件和临时账户数据清理，不影响既有 `3011/3018`。

#### 当前状态与用户验收

- 当前状态：`verified`；尚未部署线上，线上 `registration_enabled=false` 的现状不变，用户尚未进行本地产品验收，因此不标记 `accepted / production`。

### zeabur_latest_workbench_release_20260812

#### 用户目标与可见结果

- 用户授权把本地当前开发版同步到既有 Zeabur service，并要求市场数据完整可见、公开注册开启，同时保持多用户隔离与每账户专属 Hermes Agent。
- 当前公网地址为 `https://one-trading-private-simon.zeabur.app`，Deployment `6a7c57c70d41a78958bb46a2`，build `local-sync-20260812-5379302b4970d31a`。没有新建第二套 service 或改变 Android APK 下载 service。
- 公网 `/api/auth/status` 在未登录状态返回 `configured=true / multi_user=true / registration_enabled=true / invite_required=false`；现有管理员账户和密码没有从本地复制，线上仍使用原 PVC 身份库。

#### 发布、自动检查与真实运行面

- release 树保留 Android 0.1.70 原生插件、Capacitor 依赖和签名产物，只选择性同步当前后端、用户台源码与发布配置；开发数据和凭据由 `.zeaburignore/.dockerignore` 排除。
- 后端 release 全量 `406 passed / 2 skipped`，ruff、`git diff --check`、Docker 构建和候选容器健康检查通过。前端源码未在目录修复阶段再次改动；部署镜像继续提供既有已通过完整前端测试/构建的 bundle `index-2C4Cq65W.js`。
- Codex 内置浏览器真实验收：页面标题 `one-trading · Quant Terminal`；数据总览显示目录更新到 2026-08-12、26 个目录项、641 MiB 托管数据；数据目录显示 stock 8,064,651、ETF 364,882、index 238,680，页面无失败状态。
- 用户管理页显示全部账户 1、普通用户 0、管理员 `admin`、Profile `ot-owner`、历史对话 1；Hermes 页显示“当前账户专属个人 AI 助理”和独立 Profile/Session/长期记忆/内部凭据/可见数据边界。
- 实时行情开关在 Catalog 扫描窗口临时暂停，最终恢复为选中；浏览器页面、用户管理和 Hermes 页控制台 error 均为 0。

#### 权限、注册与当前状态

- 未登录 `/api/data/catalog` 为 401；管理员会话下 `/api/admin/users` 为 200 且只有一个现有账户。未创建真实访客账户，不用生产用户数据作为测试样本。
- 当前 Codex 内置浏览器会话共享原管理员 Cookie，直接访问 `/login` 会按设计重定向到 `/admin/users`；为避免注销或破坏 7 个现有 Session，本轮以未登录公网状态接口、既有隔离注册验收和线上配置值共同证明注册入口条件已开启。
- 当前状态：本次用户台发布与真实线上主路径为 `production`；用户尚未从外部设备完成新用户注册与实际业务使用验收，因此不把该体验写成用户 `accepted`。
- 回滚入口：`/Users/simon/备份/codex/20260812-164436-one-trading-zeabur-latest-sync` 和前一线上 Deployment `6a7c47620d41a78958bb4107`；回滚应用与回滚 PVC 是两个独立动作，不得顺带覆盖线上账户或 Hermes 数据。

### zeabur_data_platform_sync_20260814

#### 用户目标与可见结果

- 用户授权把本地数据台修复同步到既有 Zeabur service。当前公网仍是 `https://one-trading-private-simon.zeabur.app`，Deployment `6a7df12c201aaa81bcf9fedb`，build `local-sync-20260814-fcb218172c4bd451`。没有新建第二套 service，也没有改 Android APK 下载 service。
- 公网 `/health` 为 `status=ok / version=0.1.68 / release_channel=private / build_sha=local-sync-20260814-fcb218172c4bd451`。
- 未登录 `/api/auth/status` 仍为 `configured=true / multi_user=true / registration_enabled=true / invite_required=false`。现有管理员账户未从本机复制。

#### 发布、自动检查与真实运行面

- 数据页现在由后端 `/api/data/source-provenance` 下发中文「数据说明/提供内容」；采集页披露派生数据靠显式脚本更新；页面设置增加「参考数据」显隐。
- 前端错误对象不再击穿 Toast。`market_pulse` 自动解析会跳过过夜失效的盘中分区。
- release 树前端 144 passed，后端 447 passed / 2 skipped。数据闭环与 catalog 事实见数据平台开发日志 `5.5`。
- 本轮未用管理员 Cookie 打开数据页，避免新增或替换线上 Session；目录 30 项、`stale=false`、新参考数据集 healthy 的证据来自容器内 `list_catalog` 与公网健康/注册状态接口。

#### 当前状态

- 用户台发布主路径为 `production`；用户尚未从外部设备做新的页面验收，不标记 `accepted`。
- 回滚应用：`6a7c57c70d41a78958bb46a2`。回滚 PVC 仍用 2026-08-12 完整备份，不得覆盖账户或 Hermes 数据。

### android_private_rc_v3_1_startup_hardening

#### 用户目标与可见结果

- V3.1 对 APK 白屏的两条已证实路径做最小修复：未登录启动不再等待 `/api/settings` 的四次 401 重试；核心 JS 未执行时不再永久停在纯白页。
- 首屏在应用 JS 开始前显示本地“正在连接…”；未登录时先查 `/api/auth/status` 并直接进入登录页。
- APK 原生层在固定 Zeabur/Worker 页面 8 秒内未看到 React 就绪信号时，进入已有本地失败页；仍由用户手动选择主线路或备用线路。

#### 本地路由、Module、Adapter 与边界

- 实现位于发布检出 `/Users/simon/Trading/one-trading-release`：`frontend/src/main.tsx`、`frontend/src/lib/api.ts`、`frontend/src/router.tsx`、`frontend/index.html`、`frontend/tailwind.config.ts`、`frontend/android/app/src/main/java/com/simon/onetrading/MainActivity.java`、`backend/app/main.py`。
- 版本为 `0.1.71 / versionCode 4`。HTML/API 是 `no-store`；仅匹配 Vite 内容哈希的 `/assets/*` 为一年 immutable，gzip 仅作用于 `/assets/*`，不包围 API 和流式返回。
- 保留 Ponytail 最小边界：无节点池、无健康轮询、无路由记忆、无自动切 Worker、无写请求重放。

#### 自动检查、构建与真实运行面

- V3.1 聚焦前端回归 `10/10`，本轮全量前端回归 `38 files / 144 tests`；后端缓存/API 回归 `4/4`，后端全量 `408 passed / 2 skipped`，`git diff --check` 通过。
- TypeScript/Vite 生产构建、clean Android Release 构建、Android Release 单元测试和 lint 通过。基础入口 JS `269,561 bytes / gzip 84.78 KiB`，路由块 `26.55 KiB`，登录块 `6.96 KiB`；不再请求 rsms/Google Fonts。
- FastAPI 真实响应检查：哈希入口 JS 返回 `gzip + immutable`，`/` 返回 `no-store, must-revalidate`，`/api/auth/status` 返回 `no-store`。
- Codex 内置浏览器在隔离临时 `DATA_DIR` 的 V3.1 Web 运行面直接进入 `/login?redirect=%2F`，页面完整、console error 为 0；服务日志只见启动必需的 `/api/auth/status`，没有 `/api/settings`。
- 签名 APK：`/Users/simon/Trading/one-trading-release/releases/android/one-trading-private-0.1.71.apk`，4,649,668 bytes，SHA-256 `93101ad18d76d1a587325b13ca45e81deecc10b49208d03a6ab49e2ad6a2ea88`；v2/v3 签名和原证书通过。
- `Codex_API_36 / emulator-5554` 冷启动无 fatal；在当前线上旧 Web 版中正常进入登录页且看门狗未误判。阻断主 JS 后 `root=0`，约 8 秒后到达 `https://localhost/offline.html`，两个手动恢复按钮完整可见，无 fatal。故障注入后已恢复飞行模式 0、Wi-Fi 1 和主线路登录页。
- 先安装已发布 V3 `0.1.70`，再以 `adb install -r` 原位升级 V3.1；系统最终读取 `versionCode=4 / versionName=0.1.71`，`firstInstallTime` 保持不变。

#### 当前状态、备份、回滚与下一步

- 当前状态：`verified / 本地发布候选 / 待用户验收`；未写成 production。
- 实施前定点备份：`/Users/simon/备份/codex/20260813_002721-one-trading-v3-1-preimplementation`，原发布项目为 `/Users/simon/Trading/one-trading-release`。
- 本轮没有部署 Zeabur 应用、Cloudflare Worker 或 APK 下载服务。在另行授权部署 Web/后端前，线上仍使用旧的认证与静态资源行为；本 APK 当前只先获得原生看门狗保护。
- 回滚可逐文件恢复上述备份，或继续使用已发布 V3 `0.1.70`；不需要回滚用户数据或账户库。

### settings_ai_extra_hosted_subscriptions

#### 用户目标与可见结果

- 本地开发版「设置 → AI」在现有 Grok 云订阅之外，增加 86game 和 SubRouter 两个服务器持有订阅源，可选择模型并启用；APK 仍只读。
- Hermes 对话页在非 Grok 源时显示对应订阅名，不再写死只有 Grok。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/settings/AI.tsx`、`HermesAgentChat.tsx`、`AIHub.tsx`。
- Agent 台拥有订阅切换与凭据：见开发日志 3.12。Key 不出现在页面。

#### 当前状态与下一步

- 当前状态：`implemented`。前端云订阅回归已补充订阅源展示；真实切换 86game / SubRouter 后的浏览器主路径尚未验收。

### dashboard_trend_full_a_universe

#### 用户目标与可见结果

- 看板「趋势强度 / 实用监控」不再按 CSI1800∪自选约 1804 只统计，改为当前官方全 A 日 K（今天有效约 5207 只）。刷新首页后均线占比、60 日新高低、炸板/跌停、高换手会换成全市场口径。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台未改卡片公式，仍读 `/api/overview/market`。
- 数据台拥有分区扩范围和 `pipeline_universe_scope=ALL`：见数据平台开发日志 `stock_daily_full_a_aug17_24_dashboard_universe`。

#### 当前状态与下一步

- 当前状态：`implemented`。请刷新 `http://127.0.0.1:3011/` 看新数字。今天北交所 338 只不在官方日 K 里，财务/复权仍是 CSI800。

### hermes_gateway_start_from_settings

#### 用户目标与可见结果

- `/ai/hermes` Agent 设置在内部网关掉线时，管理员看到「内部网关未运行」，并可直接点「启动内部网关」。
- 红条同样提供启动按钮。普通用户只看到原因，不能启动。网关连上后按钮消失，状态改回「Profile 已连接」。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/HermesAgentChat.tsx`、`frontend/src/lib/api.ts`。
- Agent 台拥有启动权限、loopback 根目录门和进程拉起：见开发日志 3.21。

#### 自动检查与构建

- `HermesAgentChat.test.tsx`：`25 passed`。

#### 当前状态与下一步

- 当前状态：`implemented`。当前本机 gateway 已连接，因此已登录页面不会显示启动按钮；掉线后刷新 `/ai/hermes` 即可验收该分流。

### hermes_gateway_offline_banner

#### 用户目标与可见结果

- `/ai/hermes` 在 multiplex gateway 没开时，不再只显示笼统的「Profile 当前不可用」；红条主文案改为「Hermes multiplex gateway 当前未运行」，并附带 `detail`。
- Profile 仍在、只是探测失败时，继续用原来的 Profile 不可用文案。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/HermesAgentChat.tsx` 离线 alert 同时渲染 `message` 和 `detail`。
- Agent 台拥有 gateway 进程和 `status()` 分类：见开发日志 3.13。

#### 自动检查与构建

- `HermesAgentChat.test.tsx`：`7 passed`。

#### 当前状态与下一步

- 当前状态：`implemented`。Cursor 内置浏览器无登录会话，未在该浏览器完成已连接主路径验收；用户刷新已登录的 `http://127.0.0.1:3011/ai/hermes` 后应看到 Profile 已连接。

### hermes_agent_admin_model_picker

#### 用户目标与可见结果

- 管理员在 `/ai/hermes` 的 Agent 设置里可配置提供商 URL、模型 Key、模型，并「保存提供商配置 → 测试连通 → 应用到全部账户」。
- 模型支持列表项与自定义 ID；正在编辑时不会被后台设置刷新覆盖。Key 只显示脱敏值。
- 普通用户同一面板只显示当前模型和来源，不能改。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/HermesAgentChat.tsx`。
- Agent 台拥有切换鉴权、探测与 Adapter：见开发日志 3.14。设置页「AI 设置」本来就是管理员 Tab。

#### 自动检查与构建

- `HermesAgentChat.test.tsx`：`10 passed`。

#### 当前状态与下一步

- 当前状态：`implemented`。请管理员刷新 `/ai/hermes` 后打开 Agent 设置验收下拉、测试连通与应用。

### hermes_failed_prompt_resend

#### 用户目标与可见结果

- `/ai/hermes` 发送失败后，不必再复制整段指令。失败回复下方会出现「重新发送」，点一次就把同一条用户指令再发出去。
- 适用于两种失败：流式错误事件，以及已经落成助手气泡的 `API call failed / overloaded` 一类短错误。
- 重发不会再复制一条用户气泡；成功后失败回复被新回复替换。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目，只补 one-trading 自有 Hermes 对话交互。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/HermesAgentChat.tsx`。
- 继续走现有 `api.hermesChatStream(sessionId, message)`；不改后端、Session 存储或模型路由。

#### 自动检查与构建

- `HermesAgentChat.test.tsx`：`13 passed`，覆盖即时失败重发和历史 overloaded 回复重发，且不复制用户气泡。

#### Codex 内置浏览器目标运行面验证

- 目标页面：`http://127.0.0.1:3011/ai/hermes`。
- Codex 内置浏览器打开后被重定向到 `/login?redirect=%2Fai%2Fhermes`。本轮没有输入任何账号或密码，因此没有在真实已登录页面点到「重新发送」。

#### 当前状态与用户验收

- 当前状态：`implemented`。请在现有失败对话上点「重新发送」确认同一条指令被再次提交。

#### 阻塞、回滚和下一步

- 回滚只需恢复 `HermesAgentChat.tsx`、对应测试和本日志；不会改动 Hermes Session 或长期记忆。


### dashboard_intraday_active_turnover

#### 用户目标与可见结果

- 首页「活跃换手」在盘中不再显示 TOP 0 / 暂无数据，按今日公开成交量和流通股本现算换手率排序。
- 点回正式收盘日仍用 enriched 自带的 `turnover_rate`。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台继续消费 `overview.active_leaders`。
- 数据台：盘中快照行补 `turnover_rate`，公式与行业分析服务视图一致；不写正式分区。

#### 自动检查与构建

- `test_market_overview_as_of.py` 4 passed。

#### 当前状态与用户验收

- 当前状态：`implemented`。请刷新已登录首页确认「活跃换手」出现今日名单。

### dashboard_default_as_of_live

#### 用户目标与可见结果

- 交易日中午打开首页、不选手动日期，应看到当天，而不是停在上一正式收盘日。
- 盘中模式标明“盘中快照，未收盘”；涨跌家数和成交额按今日公开行情，均线/涨停梯队先降级。
- 点回昨天回到正式收盘数字。15:30 正式日写出后，同一天从盘中快照变成正式日，日期不跳。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目，只收口 one-trading 首页看板的默认选日。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/Dashboard.tsx`、`frontend/src/lib/api.ts`。
- 数据台 Interface：`GET /api/overview/market` 未带 `as_of` 时 `default_to_live=True`；响应新增 `data_mode` / `official_as_of` / `snapshot_as_of` / `available_as_of`。
- 日期选择器最大值取正式 enriched 与快照最新日里更新的那个。未锁历史日期时，刷新重新走“看现在”。

#### 自动检查与构建

- 后端选日/装配 3 项 + 既有 snapshot 2 项 passed。
- 前端 `Dashboard.multiuser.test.tsx`、`ReviewStockContext.test.tsx` passed。

#### 当前状态与用户验收

- 当前状态：`implemented`。请在已登录的 `http://127.0.0.1:3011/` 不选手动日期确认看到 2026-08-18，并点回 17 日核对正式收盘。

#### 阻塞、回滚和下一步

- 回滚只需恢复 overview 默认只认正式 enriched 最新日，以及 Dashboard 日期/提示改动。不要删 Parquet，不要改管道范围。


### stock_analysis_recent_progress

#### 用户目标与可见结果

- 「AI 个股分析」进行中时，不再弹出右下角蓝色小胶囊。
- 进度并入左侧「最近查看」：该股票左边箭头换成转圈，右侧显示「分析中」。
- 任何弹窗界面也不再出现这颗个股分析小气泡；分析对话框本身仍可打开，只是不再用浮动胶囊提醒。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目，只改 one-trading 自有个股分析界面。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/StockAnalysis.tsx`、`frontend/src/components/stock-analysis/RecentStockList.tsx`、`frontend/src/components/Layout.tsx`。
- 任务状态仍来自 `stockAnalysisStore`；没有改数据台或 Agent 台。

#### 自动检查与构建

- `StockAnalysis.test.tsx` 与 `Layout.mobile.test.tsx` 已覆盖最近查看分析中状态，以及 Layout 不再挂载个股分析气泡。

#### Codex 内置浏览器目标运行面验证

- 本轮以自动检查为主。请在已登录的 `/stock-analysis` 点「AI 个股分析」后确认：最近查看行转圈，「个股分析」小胶囊不再出现。

#### 当前状态与用户验收

- 当前状态：`implemented`。

#### 阻塞、回滚和下一步

- 回滚恢复上述三个文件、`stockAnalysisStore.ts` 测试辅助和本日志即可。财务分析紫色胶囊未改。


### hermes_message_quote

#### 用户目标与可见结果

- 在 `/ai/hermes` 选中用户或助手消息中的一段文字后，直接在原文上留下蓝底和编号圆点，并在标注左右弹出对应追问输入框。
- 输入框上方仍保留 `1 条引用` / `N 条引用` 胶囊；hover 预览编号摘录，点某一条滚回原文对应标注。
- 旁路输入框可拖动，移动范围限制在 AI 弹层/对话界面内；左下角可删除该条引用。发送只带走这一条。底部输入栏发送仍可带走全部引用。不实现 Side Chat、More details 或 Session fork。

#### GitHub 情报与固定上游点

- 主会话编号胶囊交互借鉴 AHGGG/dsh-side-chat `master@81d62a07`，完整记录见 `/Users/simon/Trading/用户台GitHub项目借鉴记录.md` §3.5。不安装上游包，不移植 DSH Runtime。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/HermesAgentChat.tsx`。
- 仍走现有 `api.hermesChatStream(sessionId, message)` 字符串接口，不改后端。发送正文形如 `引用：\n1. excerpt\n\n用户问题`。

#### 自动检查与构建

- `HermesAgentChat.test.tsx`：覆盖划词后原文出现编号标注、旁路追问框和胶囊，发送内容含编号引用。

#### Codex 内置浏览器目标运行面验证

- 本轮未打开已登录 `/ai/hermes`。请在该页选中一段回复，确认原文出现蓝底编号，并在标注旁弹出对应输入框。

#### 当前状态与用户验收

- 当前状态：`implemented`。原文标注尚未用户验收。

#### 阻塞、回滚和下一步

- 回滚恢复 `HermesAgentChat.tsx`、对应测试和本日志即可。




### fund_flow_history_window_picker

#### 用户目标与可见结果

- 概念/行业主力资金流向的「近N日」改成可选回补窗口：1 天、5 天、1 周、1 个月、1 个季度、半年、1 年。
- 默认显示「1 个季度」。原先写死的 60 天并进季度和半年两档。
- 点某一档只回补该面板的 Top 流入/流出日线，不把今日排名表切成历史累计榜。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。继续走现有 `POST /api/free/fund-flow/{boards|concepts}/history/refresh`。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/components/SectorFundFlowPanel.tsx`。
- 测试：`frontend/src/components/__tests__/SectorFundFlowPanel.history.test.tsx`。
- 交易日映射：1 天/5 天/1 周都按接口下限回补 5 日；1 个月 21 日；1 个季度 63 日；半年 126 日；1 年 250 日。

#### 自动检查与构建

- `pnpm exec vitest run src/components/__tests__/SectorFundFlowPanel.history.test.tsx`：1 passed。
- `pnpm exec tsc -b`：通过。

#### Codex 内置浏览器目标运行面验证

- 本轮以自动检查为主。刷新概念分析或看板资金流后，原「近N日」应显示「1 个季度」，点开可选半年/1 年等档。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 回滚恢复上述两个文件和本日志即可。下载云更新按钮未改。

### concept_analysis_card_update_buttons

#### 用户目标与可见结果

- 概念分析页每个模块都有和看板相同的下载云「更新」按钮：KPI 区、领涨主线、领跌方向、概念矩阵、当前概念详情。
- 概念主力资金流向的刷新按钮改成同一套下载云图标；成功后显示「已更新 · 时间」，约 3 秒后收起。
- 点击只覆盖该模块正在看的数据：KPI 走概念资金流缓存，其余模块重拉行情快照和概念归属；不启动盘后管道。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。沿用看板卡片更新交互和现有概念/资金流只读接口。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/ConceptAnalysis.tsx`、`frontend/src/components/SectorFundFlowPanel.tsx`。
- 测试：`frontend/src/pages/__tests__/ConceptAnalysis.update.test.tsx`。
- 数据：`GET /api/screener/market-snapshot`、`GET /api/ext-data/ext_gn_ths/rows`、`GET /api/free/fund-flow/concepts`。管理员仍可通过资金流下载云走 `POST /refresh` 覆盖共享快照。

#### 自动检查与构建

- `pnpm exec vitest run src/pages/__tests__/ConceptAnalysis.update.test.tsx`：1 passed。
- `pnpm exec vitest run src/pages/__tests__/Dashboard.multiuser.test.tsx`：4 passed。
- `pnpm exec tsc -b`：通过。

#### Codex 内置浏览器目标运行面验证

- 本轮以自动检查为主。刷新 `/concept-analysis` 后，各模块标题旁应出现下载云；点击后该模块显示「已更新 · 时间」，其他模块数字不一起转圈。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 回滚恢复上述文件和本日志即可。页面顶部原有旋转刷新仍保留。

### concept_analysis_membership_source

#### 用户目标与可见结果

- 概念分析矩阵、最强主线、领涨/领跌不再把概念资金流快照的 `as_of` 切成 `2026-08-20` / `16:16:02` 两个假概念。
- 页面优先使用 `ext_gn_ths.所属概念` 做股票→概念归属；概念主力资金流向面板仍走 `ext_fund_flow_concept`，互不影响。
- 旧版若把资金流表或 `as_of` 存进概念分析配置，会自动回退到内置概念归属表。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。沿用数据台已登记的 `ext_gn_ths`（概念归属）和 `ext_fund_flow_concept`（概念资金流快照）。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/ConceptAnalysis.tsx` 改为与行业分析相同的字段级选源守卫。
- Adapter：`frontend/src/lib/analysis-adapter.ts` 把 `as_of` 排除出分组维度。
- 测试：`frontend/src/lib/__tests__/analysis-adapter.test.ts`。
- 不改数据管道、不重扫 Catalog、不动财务。

#### 自动检查与构建

- `pnpm exec vitest run src/lib/__tests__/analysis-adapter.test.ts`：9 passed。
- `pnpm exec tsc -b`：通过。

#### Codex 内置浏览器目标运行面验证

- 本轮以自动检查为主。刷新 `/concept-analysis` 后，标题不应再是 `2个概念 · 500只标的`，矩阵名称应是真实概念而不是日期/时间。

#### 当前状态与用户验收

- 当前状态：`implemented`。
- 未标记 `accepted`。

#### 阻塞、回滚和下一步

- 回滚恢复上述三个文件和本日志即可。资金流面板未改。

### dashboard_card_update_buttons

#### 用户目标与可见结果

- 市场看板里概念/行业热度、涨跌分布、情绪雷达、趋势强度、涨停梯队和四个榜单，在来源追踪旁增加「更新」按钮。
- 卡片「更新」改成与市场脉搏相同的下载云图标。
- 点击后只覆盖该卡片字段：概念热度只改概念榜，行业热度只改行业榜，四个个股榜互不影响；不启动盘后管道。
- 每个卡片更新后显示资金流同款状态：更新中、已更新时间戳、或失败原因。成功横幅约 3 秒后自动收起，只留下载云；失败提示会留下直到下次点击。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/Dashboard.tsx`。
- 数据仍来自 `GET /api/overview/market`；普通用户也可点卡片更新，因为这是读缓存而不是写数据。

#### 自动检查与构建

- 待补 Dashboard 测试：普通用户能看到更新按钮，点击不会调用 `pipelineJobs`。

#### Codex 内置浏览器目标运行面验证

- 本轮以自动检查为主。请在已登录首页确认红框空位出现旋转刷新图标，点击后面板数字会转圈重拉。

#### 当前状态与用户验收

- 当前状态：`implemented`。

#### 阻塞、回滚和下一步

- 回滚恢复 `Dashboard.tsx`、对应测试和本日志即可。资金流和市场脉搏按钮未改。

### source_trace_github_as_adapter_reference

#### 用户目标与可见结果

- 管理员打开 `/data?section=source-trace` 时，故障链只追到 TickFlow / 东财 / 腾讯等真实生产者。
- GitHub 项目只出现在「Adapter 对照（GitHub）」；空名单是说明，不是「需关注」。
- `stock_minute` 的 `easy_tdx` 仍显示为运行时 Adapter。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目。只调整已有登记在页面上的位置和语气。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/components/data/DataSourceTracePanel.tsx`。
- 路由：`/data?section=source-trace&trace=<subject_id>`。
- 数据台登记由 `/api/data/source-provenance` 下发；本轮对应改动见数据平台开发日志 `5.6 source_trace_github_as_adapter_reference`。
- 未改 Parquet、同步或查询。

#### 自动检查与构建

- `npm run test:run -- src/pages/__tests__/Data.test.tsx`：15 passed。

#### Codex 内置浏览器目标运行面验证

- 目标运行面：已登录管理员 `http://127.0.0.1:3011`，后端 `3018`。
- ` /data?section=source-trace&trace=stock_daily`：故障链止于 TickFlow / 腾讯 / 新浪等；GitHub 只在「Adapter 对照」；旧标题「GitHub 代码与接口情报」不存在。
- `trace=stock_minute`：真实生产者是通达信公开行情服务器；`easy_tdx` 显示「当前运行时 Adapter」。
- `trace=ext_fund_flow_bk_daily`：真实生产者只有东财；状态写明 stock.db 不在主路径；go-stock 只在 Adapter 对照。
- 「需关注」只留下 `quote_snapshot` / `ext_data` / `financial_shares` 三条既有告警，没有把空 GitHub 名单算进去。
- 未标记 `accepted / production`。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 第 2 步见 `fund_flow_stock_db_fallback_off`。

#### 阻塞、回滚和下一步

- 回滚恢复 `DataSourceTracePanel.tsx` 即可。

### fund_flow_stock_db_fallback_off

#### 用户目标与可见结果

- 行业/概念 63 日窗口继续只读已有东财日线，看起来仍是满窗。
- 单板块历史刷新失败时不再用 `stock.db` 悄悄补行；无缓存是 502，有缓存仍看旧行。
- 用户台页面没有改布局或窗口下拉。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台继续消费 `GET /api/free/fund-flow/boards/window` 与 `GET /api/free/fund-flow/board/{code}/history`。
- 写入口改动在数据台 `5.7 stock_db_default_fallback_off`。本轮没有改 `SectorFundFlowPanel.tsx`。

#### 自动检查与构建

- 本轮没有新增前端测试。数据台资金流/API 测试 34 passed。

#### Codex 内置浏览器目标运行面验证

- 已登录首页只读切换「1 个季度」，没有点回补或单板块 refresh。
- 行业：近 63 个交易日 `2026-06-03 ~ 2026-08-31`，覆盖 128/128，满窗 128/128，流入种植业。
- 概念：同一窗口，覆盖 504/504，满窗 482/504，流入钛白粉概念。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 未标记 `accepted / production`。

#### 阻塞、回滚和下一步

- 回滚见数据台 `5.7`。第 3 步见 `catalog_ext_data_directory_split`。

### catalog_ext_data_directory_split

#### 用户目标与可见结果

- 管理员打开 `/data?section=catalog` 时，「扩展数据」分组直接列出 7 个固定池和 1 个余项，不再只有一张 External data 糊桶。
- 来源追踪里这 7 个 ID 是目录数据；未建目录的分时余项仍是扩展数据。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/components/data/DataCatalogSection.tsx` 增加「扩展数据」分组。
- 路由：`/data?section=catalog`、`/data?section=source-trace`。
- 目录定义和扫描归属在数据台 `5.8 catalog_ext_data_directory_split`。查询仍走既有 `ExtConfigStore`，本轮没有改资金流页面。

#### 自动检查与构建

- `npm run test:run -- src/components/data/__tests__/DataCatalogSection.test.tsx src/pages/__tests__/Data.test.tsx`：26 passed。

#### Codex 内置浏览器目标运行面验证

- 目标运行面：已登录管理员 `http://127.0.0.1:3011`，后端 `3018`。
- `/data?section=catalog`：目录计数 41；「扩展数据」可见 `扩展数据余项` 357 行、`行业资金流快照` 128、`行业资金流日线` 16,033、`概念资金流快照` 504、`概念资金流日线` 59,010、`个股资金流` 851，以及扩展概念/行业。旧标题 External data 不存在。
- `/data?section=source-trace&trace=ext_fund_flow_bk_daily`：对象种类是目录数据；真实生产者是东财；状态写明 stock.db 不在主路径；物理路径 `ext_data/ext_fund_flow_bk_daily`。
- 来源追踪共 42 个对象：41 个目录项 + 余下的 `ext_fund_flow_concept_minute` 扩展配置。
- 未点资金流回补或单板块 refresh。未标记 `accepted / production`。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 未标记 `accepted / production`。

#### 阻塞、回滚和下一步

- 回滚恢复 `DataCatalogSection.tsx` 分组和对应 fixture/测试即可。目录投影回滚见数据台 `5.8`。
- 三条总账见 `subtraction_playbook_closed`。

### subtraction_playbook_closed

#### 用户目标与可见结果

- 把 2026-09-02 至 2026-09-03 的减法三条收成用户台总账，方便以后查「做完了什么、没验收什么」。
- 用户在数据页能看到：来源追踪不再把 GitHub 当父母；单板块资金流刷新失败不再默认写 `stock.db`；目录「扩展数据」是 7 张固定卡加余项。

#### GitHub 情报与固定上游点

- 本条没有新增或重新审阅 GitHub 项目。

#### 本地路由、Module、Adapter 与依赖接口

| 步 | 用户可见结果 | 本日志 | 数据台日志 |
| --- | --- | --- | --- |
| 1 | `/data?section=source-trace` 故障链止于真实生产者；GitHub 在 Adapter 对照 | `source_trace_github_as_adapter_reference` | `5.6` |
| 2 | 资金流 63 日窗口仍可看；单板块 refresh 失败不默默补 go-stock 行 | `fund_flow_stock_db_fallback_off` | `5.7` |
| 3 | `/data?section=catalog` 扩展数据分组列出固定池和余项 | `catalog_ext_data_directory_split` | `5.8` |

- 没有第 4 步用户台工单。

#### 自动检查与构建

- 本条不跑新测试。各步检查仍记在上表三条。

#### Codex 内置浏览器目标运行面验证

- 本条不新开浏览器。运行面证据仍在上表三条。

#### 当前状态与用户验收

- 当前状态：三条用户可见减法关闭。各步仍是 `verified`，不是 `accepted / production`。
- `U-P0-04` 数据目录与来源追踪的用户验收仍待另做。日 K / 分钟 / 同花顺四表不因本条验收。

#### 阻塞、回滚和下一步

- 回滚按各步条目分别恢复。
- 下一步若继续，另授数据台 `D-P0-01` 或验收已落地 canary，不要再开减法工单。
- 总览「本地存储」左栏中文与跳转是第 3 步之后的用户可见跟进，不是第 4 步减法。见 `storage_overview_simplified_labels`。

### storage_overview_simplified_labels

#### 用户目标与可见结果

- 数据总览「本地存储」左栏按减法后的真实结构改完：桶还是原来那些磁盘桶，标题改成中文，按钮按「单链追来源 / 多卡看目录」分开。
- 不再出现 `Stocks` / `External data` 等英文桶名。
- 「扩展数据」仍是一个磁盘桶（约 396 文件 / 4.5 MiB），按钮是「目录」，打开 Catalog「扩展数据」分组（7 张固定卡 + 余项），不再把整桶当成余项 `ext_data`。
- 「股票 F10」仍指向磁盘上的 `f10/stock_margin_trading`，来源追踪对象是 `stock_margin_trading`，不是整份 F10 百科。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/components/data/StorageBreakdownCard.tsx` 用 `STORAGE_CATEGORY_LABELS` 覆盖过期英文 `title`；`STORAGE_CATEGORY_NAV` 决定「来源」或「目录」。
- 路由：`/data?section=source-trace&trace=<subject>`；`/data?section=catalog&group=<etf|finance|ext|reference>`。切来源时清 `group`，切目录时清 `trace`。
- 来源：股票 → `stock_daily`，指数 → `index_daily`，行情快照 / 封板 L1 / 五档盘口 / 股票池 / 股票 F10 → 对应 subject。
- 目录：ETF → `etf`，财务 → `finance`，扩展数据 → `ext`，参考数据 → `reference`。
- 数据台只改存储分类中文标题和 `list_catalog()` 回读 remap，不拆磁盘桶，不重写 Parquet。见数据台 `5.10`。

#### 自动检查与构建

- `npm run test:run -- src/components/data/__tests__/StorageBreakdownCard.test.tsx src/components/data/__tests__/DataCatalogSection.test.tsx src/pages/__tests__/Data.test.tsx`：29 passed。

#### Codex 内置浏览器目标运行面验证

- 目标运行面：已登录管理员 `http://127.0.0.1:3011`，后端 `3018`。
- `/data` 总览左栏可见：股票、ETF、指数、行情快照、封板 L1、五档盘口、股票池、财务、股票 F10、扩展数据、参考数据。英文桶名不存在。
- 扩展数据仍报 396 文件 / 4.5 MiB。按钮：单链桶是「来源」，ETF / 财务 / 扩展数据 / 参考数据是「目录」。
- 「打开 扩展数据 目录」→ `http://127.0.0.1:3011/data?section=catalog&group=ext`，落到「扩展数据」分组。
- 「追踪 股票 来源」→ `http://127.0.0.1:3011/data?section=source-trace&trace=stock_daily`，当前对象是 Stock daily bars / `stock_daily`；页首仍写 GitHub 只作 Adapter 对照。
- 未点资金流回补或单板块 refresh。未标记 `accepted / production`。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 未标记 `accepted / production`。

#### 阻塞、回滚和下一步

- 回滚恢复 `StorageBreakdownCard.tsx`、`Data.tsx` 的 `group` 路由和 `DataCatalogSection` 的 `focusGroup` 即可。标题 remap 回滚见数据台 `5.10`。
- 这不是第 4 步减法，也不开工 `D-P0-01`。

### catalog_stale_false_degraded_repair

#### 用户目标与可见结果

- 管理员打开 `/data?section=catalog` 时，不再把「状态可能过期 + 每张卡准入未登记 + 复权/ETF/封板降级」当成一整片故障。
- 空控制库准入不再印在每张卡上。可服务文案改成「已落库并可服务」。
- 全量重扫后，有文件的目录项显示健康；空数据集仍是未知。日 K 最新日从过期快照里的 2026-08-20 回到当前文件的 2026-09-03。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`DatasetCatalogCard.tsx` 只在真正有控制库策略时显示准入芯片；`ControlPlaneSummary.tsx` / 来源追踪空策略文案改为「未使用控制库准入」。
- 路由仍是 `/data?section=catalog`。重扫按钮仍走 `POST /api/data/catalog/rescan`。
- 目录投影与扫描提交改动见数据台 `5.11`。

#### 自动检查与构建

- `npm run test:run -- src/components/data/__tests__/DataCatalogSection.test.tsx src/pages/__tests__/Data.test.tsx`：26 passed。

#### Codex 内置浏览器目标运行面验证

- 目标运行面：已登录管理员 `http://127.0.0.1:3011/data?section=catalog`，后端 `3018`。
- 点「重新扫描本地目录」后约 38s 完成。页面无「状态可能过期」，无「准入状态未登记」，无「降级」。
- 可见健康卡含 Stock daily bars `8,192,756` 行 / 最新 `2026-09-03`，Stock adjustment factors 健康，Shares outstanding `41,784` 行。空分钟/五档等仍是未知，不是故障。
- 未点资金流回补或单板块 refresh。未标记 `accepted / production`。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 未标记 `accepted / production`。

#### 阻塞、回滚和下一步

- 回滚恢复目录卡芯片文案即可。扫描提交回滚见数据台 `5.11`。
- 分钟线只有 4 只、复权因子最新仍是 2026-07-23，是数据覆盖事实，不是本轮目录故障。

### collection_status_control_plane_removed

#### 用户目标与可见结果

- 管理员打开 `/data?section=collection` 时，页顶不再出现「采集状态」控制库卡片（数据来源、同步进度、回补与修复、控制库策略）。
- 「采集与同步」页签不再挂扩展配置个数「8」；「数据目录」仍可显示目录项数。
- 留下真正会写盘的按钮，以及市场脉搏、个股融资融券、同花顺官方特色数据三张手写卡、实时行情、自动调度、扩展数据配置。「来源追踪」仍是独立页签。
- 不换成另一排「统一数据源」。不把日历停在 8-31、分钟线 4 只改成文案问题。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/Data.tsx` 不再渲染 `DataCollectionControlPanel`；`DataPageCategoryNav.tsx` 不再给采集页签传 `extensionCount`。
- 路由仍是 `/data?section=collection`。来源追踪仍走 `/data?section=source-trace`。
- 数据台只改财务偏好键读取顺序，见 `5.12`。本页自动调度因此可以出现「财务」，不是新 Provider。

#### 自动检查与构建

- `npm run test:run -- src/pages/__tests__/Data.test.tsx`：16 passed。

#### Codex 内置浏览器目标运行面验证

- 目标运行面：已登录管理员 `http://127.0.0.1:3011/data?section=collection`，后端 `3018`。
- 页签文本是「采集与同步」，DOM 无数字 8；「数据目录」仍是 41。
- 页面无「采集状态」「控制库策略」「支持回补和修复」「统一数据源」。
- 可见「立即同步」和其余写盘按钮；三张手写卡、实时行情、自动调度、扩展数据配置都在。
- 自动调度盘后链为 `日K → 复权 → 财务 → 指标 → 指数 → ETF`。总览「权限与公开源兜底」为「财务、股票池、实时行情使用公开源」。
- 点过「来源追踪」页签（只读），未点立即同步 / 市场脉搏 / 融资融券 / 同花顺 / 资金流回补。未标记 `accepted / production`。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 未标记 `accepted / production`。

#### 阻塞、回滚和下一步

- 回滚恢复 `Data.tsx` 的 `DataCollectionControlPanel` 和页签 `extensionCount` 即可。财务键回滚见数据台 `5.12`。
- 这不是第 4 步减法，也不开工 `D-P0-01`。日历 8-31、分钟线 4 只、复权 2026-07-23 仍是数据事实。

### collection_main_chain_maintenance_grouped

#### 用户目标与可见结果

- 采集页主位只留立即同步、数据范围、自动调度。
- 日 K 历史扩展、重建 Enriched、指数手动获取、分钟 K 设置、清除数据放进「维护」，默认收起。
- 三张手写卡、实时行情、下面 8 张扩展卡仍在本页。新建扩展数据 / 测试端点从主工具条挪到扩展数据配置标题旁，避免和立即同步排成一排。
- 不合成 Provider，不改日历 / 分钟线文案，不把来源追踪塞回这页。

#### GitHub 情报与固定上游点

- 本轮没有新增或重新审阅 GitHub 项目。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/Data.tsx` 采集面板改分组；`AdvancedDisclosure` 复用为「维护」。
- 路由仍是 `/data?section=collection`。后端、同步、Parquet 未改。

#### 自动检查与构建

- `npm run test:run -- src/pages/__tests__/Data.test.tsx`：16 passed。

#### Codex 内置浏览器目标运行面验证

- 目标运行面：已登录管理员 `http://127.0.0.1:3011/data?section=collection`，后端 `3018`。
- 默认可见：盘后主链、立即同步、数据范围、自动调度、维护（收起）、三张手写卡、实时行情、扩展数据配置。
- 默认不可见：日 K 历史扩展、重建 Enriched、指数手动获取、分钟 K 设置、清除数据。
- 点开「维护」后这五个按钮出现。未点立即同步 / 维护里任一按钮 / 市场脉搏 / 融资融券 / 同花顺 / 资金流回补。未标记 `accepted / production`。

#### 当前状态与用户验收

- 当前状态：`verified`。
- 未标记 `accepted / production`。

#### 阻塞、回滚和下一步

- 回滚恢复 `Data.tsx` 采集面板布局即可。
- 实时行情和 8 张扩展卡还没收。下一刀若继续，另授；不要把它们和本条混成一次大改。

### upstream_908b385_merge_foundation_20260908

#### 用户目标与可见结果

- 在隔离候选里留下本地优先的合并基底，再继续接 908 的 `/factors` `/lots` `/signals` 等可见能力。
- 本阶段用户还看不到新路由：候选 `router.tsx` / `Layout.tsx` 仍只有 `/ai` `/mining` `/trading` `/admin/users`。
- 不是完整升级完成，也不是浏览器验收。

#### GitHub 情报与固定上游点

- 上游 `shy3130/tick-stock-panel` `908b3855010fca39a424db43c6292f686c4418ba`，基线 `4d27f3139ef58e25fc410b373363dd6bf40c6dfa`。
- 记录：`/Users/simon/Trading/docs/upstream-integrations/2026-09-08-latest-local-first/merge-foundation.md`。
- 旧 preflight 整类 exclude 已被本轮 276 路径整合取代。

#### 本地路由、Module、Adapter 与跨台依赖

- 只改候选 `/Users/simon/Trading/_sandbox/upstream-20260908-local-first/candidate`。canonical 用户台源码未动。
- 90 个冲突文件用 `git merge-file -p --ours`。保护点仍在：挖掘页、`?tab=mining`→`/mining`、指数搜索 UI、品牌 `v0.1.68`。
- 后端候选已 `include_router(factors/lots)`；前端路由尚未挂上。下一阶段见 `next-adaptation.json` A1–A6 / A13–A14。

#### 自动检查与构建

- 候选 `pnpm exec tsc -b --force`：退出码 2，355 个类型错误，0 个语法错误。日志 `diagnose-tsc.log`。
- 未跑 vitest，未开候选前端。

#### Codex 内置浏览器目标运行面验证

- 未做。正式 3011 未停未改。

#### 当前状态与用户验收

- 当前状态：候选 `isolated` / 文档 `implemented`。
- 未标记 `verified / accepted / production`。

#### 阻塞、回滚和下一步

- 回滚：不要写回 canonical；候选可弃用，正式树仍是备份 `/Users/simon/备份/codex/20260908-one-trading-upstream-local-first-preflight`。
- 下一步：同一会话按 `next-adaptation.json` 做功能契约适配，再测；独立会话复核。

### upstream_908b385_candidate_adaptation_20260908

#### 用户目标与可见结果

- 在隔离候选里接上 `/factors` `/lots` `/signals`，同时保留 `/ai` `/ai/hermes` `/mining` `/trading` `/admin/users`。
- `?tab=factor` → `/factors`；`?tab=mining` 仍回 `/mining`。
- 用户还看不到正式树上的这些路由：canonical 用户台源码未动。
- 不是浏览器验收，也不是回写。

#### GitHub 情报与固定上游点

- 上游仍是 `908b3855010fca39a424db43c6292f686c4418ba`（`gh api commits/main` committer `2026-09-07T14:54:05Z`）。`resolve_ref(main)` 仍 `sha=null`。
- 记录：`/Users/simon/Trading/docs/upstream-integrations/2026-09-08-latest-local-first/adaptation.md`。
- 最初复制误跳过任意名为 `data` 的目录；`frontend/src/components/data` 已从预检备份恢复 37 个文件。

#### 本地路由、Module、Adapter 与跨台依赖

- 只改候选。canonical 用户台源码未动。
- 共享 API/类型已补 Lots/PullAuth/Backfill/Preferences/MonitorRule；`MinuteKlineRow.amount` 可为 null。
- 新页沿用现有 UI。自定义信号设置仍管理员限制。

#### 自动检查与构建

- 候选 `pnpm exec tsc -b --force`：exit 0，0 个类型错误。日志 `diagnose-tsc-adapt-5.log`。
- 未跑 vitest，未开候选前端，未碰 3011。

#### Codex 内置浏览器目标运行面验证

- 未做。隔离服务未证实，未启 3111/3118。

#### 当前状态与用户验收

- 当前状态：候选 `isolated` / 文档 `implemented`。
- 未标记 `verified / accepted / production`。

#### 阻塞、回滚和下一步

- 回滚：不要写回 canonical；正式树仍是备份 `/Users/simon/备份/codex/20260908-one-trading-upstream-local-first-preflight`。
- 剩余：A4/A9/A11/A12/A16/A18。独立会话复核后再谈 promotion。

### 5.24 upstream_9a4bdcd_v6_isolation_20260909

#### 用户目标与可见结果

- 候选上两名合成用户的因子缓存、回测身份、监控运行态按真实 user id 隔离；缺 capset 不能 HTTP 直通；`ONE_TRADING_DISABLE_BACKGROUND` 覆盖实际 lifespan 注册的后台任务。
- 用户看不见的正式树未改。未开页面。

#### GitHub 情报与固定上游点

- 上游 `9a4bdcd07dfe999f123a8226608d4c90213fae5b`。
- 报告：`/Users/simon/Trading/docs/upstream-integrations/2026-09-08-latest-local-first/remaining-qa.md`。

#### 本地路由、Module、Adapter 与依赖接口

- 只改候选。`/api/kline/sync*` 与 pipeline 走空 `CapabilitySet`，不是 `None`。
- 自定义因子创建仍 admin-only；`/api/strategies/ai/save` 普通用户可写自己的；`/publish` 普通用户 403。
- monitor 按 `owner_user_id` 切片，不是只建目录。

#### 自动检查与构建

- 首跑 5 failed / 28 passed 保留。复跑 33 passed。未跑 vitest，未开候选前端。

#### Codex 内置浏览器目标运行面验证

- 未做。A18 未启动 3111/3118。

#### 当前状态与用户验收

- 当前状态：候选 `isolated` / 文档 `implemented`。
- 未标记 `verified / accepted / production`。

#### 阻塞、回滚和下一步

- 回滚：不要写回 canonical。下一步 A18 + 浏览器 + 独立复核。

### 5.25 upstream_9a4bdcd_unified_qa_20260909

#### 用户目标与可见结果

- 候选 remaining-qa 代码缺口关闭；统一离线回归；隔离 3111/3118 fixture Web 供后续 Codex 内置浏览器验收。
- 用户看不见的正式树业务源未改。本执行会话未打开系统浏览器，也未做页面验收。

#### GitHub 情报与固定上游点

- 上游 `shy3130/tick-stock-panel` `main@9a4bdcd07dfe999f123a8226608d4c90213fae5b`（2026-09-09 `gh api` 再确认）。
- 主记录：`/Users/simon/Trading/用户台GitHub项目借鉴记录.md` 2026-09-09 子记录。
- 报告：`/Users/simon/Trading/docs/upstream-integrations/2026-09-08-latest-local-first/unified-qa.md`。

#### 本地路由、Module、Adapter 与依赖接口

- 只改候选。产品 cookie 仍是 `tf_session`；仅 sandbox 包装器改为 `tf_session_candidate_3118`。
- 本地品牌 `VERSION v0.1.68` 保留。Watchlist/Review 测试改跟本地文案，不是跟 908 UI。
- 正式三份开发日志从 promotion 复制清单排除，在本文件就地维护。

#### 自动检查与构建

- tsc/build exit 0；RuleEditor 在 `index--HknpV11.js`。
- vitest 首跑 5 failed / 217 passed 与次跑 3 failed / 219 passed 保留；rerun2 **222 passed**。
- 后端无效首跑（官方 cwd）与候选 352 failed / 1544 passed 保留；本地可收集绿集 **1107 passed**。

#### Codex 内置浏览器目标运行面验证

- 未做。fixture 已启动：http://127.0.0.1:3111 与 http://127.0.0.1:3118，PID 65384 / 65383。HTTP `/health` 200 ≠ 页面验收。

#### 当前状态与用户验收

- 当前状态：候选 `implemented` / fixture `isolated`。
- 未标记 `verified / accepted / production`。

#### 阻塞、回滚和下一步

- 回滚：不要写回 canonical。下一步 Codex 内置浏览器 + 独立复核。历史 `e827c380` / `94b3e368` 不得改写成成功。

### 5.26 upstream_9a4bdcd_regression_fix_20260909

#### 用户目标与可见结果

- 目标：把基线对照确认的升级回归修掉，并留下可给 Codex 内置浏览器用的隔离 fixture。前端本轮未改。
- 可见结果仍只在候选/隔离端口：3111/3118，产品 cookie 仍是 `tf_session`。

#### GitHub 情报与固定上游点

- 上游 `9a4bdcd07dfe999f123a8226608d4c90213fae5b`。主记录：用户台 2026-09-09 回归修复子记录。报告 `regression-fixes.md`。

#### 本地路由、Module、Adapter 与依赖接口

- 只改候选。包装器 cookie `tf_session_candidate_3118`。backend PID 75034；3111 listen 65402 / launcher 65384。

#### 自动检查与构建

- 前端未改：复用 vitest 222 / tsc / build / `index--HknpV11.js`。
- 完整 original pytest 358f/1002p/78e exit 1；完整 candidate 331f/1575p/64e exit 1。17 个 identical OG/NR 现为 still_green。1107-pass 仍不是全库通过。

#### Codex 内置浏览器目标运行面验证

- 未做页面验收。fixture HTTP/auth/kline/403/guard 已记录。`27dc9d57` `structured_final=false` 不得改写成正常结构化结束。

#### 当前状态与用户验收

- 当前状态：候选 `implemented` / fixture `isolated`。
- 未标记 `verified / accepted / production`。

#### 阻塞、回滚和下一步

- 下一步：Codex 内置浏览器 + 独立复核。不要写回 canonical。

### 5.27 upstream_9a4bdcd_preferences_http_20260909

#### 用户目标与可见结果

- 目标：修掉 Codex 内置浏览器已见到的主页 500 toast（`GET /api/settings/preferences` 缺 `get_sidebar_index_symbols`），并让隔离 fixture 的子进程阻断可继承。前端本轮未改。
- 可见结果仍只在候选/隔离端口：3111/3118。侧栏指数是当前账户 UI 偏好。DATA_DIR 换成 `data-v18` 后需重新登录。产品 cookie 仍是 `tf_session`。

#### GitHub 情报与固定上游点

- 上游 `9a4bdcd07dfe999f123a8226608d4c90213fae5b`。主记录：用户台 2026-09-09 preferences HTTP 子记录。报告 `reports/preferences-http-fix.md`。

#### 本地路由、Module、Adapter 与依赖接口

- 只改候选。`/api/settings/preferences` 与 `/preferences/realtime-monitor` 走用户 `load/save`。`/pipeline-index-symbols` 仍是服务器写。包装器 cookie `tf_session_candidate_3118`。当时 backend PID 81138；之后 backend 85484（04:10:27）。3111 listen 65402 / launcher 65384 保持。

#### 自动检查与构建

- 前端未改：复用 vitest 222 / tsc / build / `index--HknpV11.js`。
- 真实认证 HTTP 测试 5 项通过；settings 内 102 个 preferences 名齐全。
- 完整 original 358f/1002p/78e exit 1（未重跑）；完整 live candidate **322f/1591p/64e exit 1**。17 个 identical OG/NR 仍 green。1107-pass 仍不是全库通过。

#### Codex 内置浏览器目标运行面验证

- Codex IAB 记录见 `docs/upstream-integrations/2026-09-08-latest-local-first/reports/browser-acceptance.md`（Codex 观察，不是本 freeze 会话打开浏览器）。~03:56 旧 cookie 回 login；admin 登录后看板 2 股+4 指数、无 500 toast；StockPanel 12 根工作日 K、MA5 10.92/MA10 10.72。未标 `verified / accepted / production`。`172ec9c4` `structured_final=false` 不得改写成正常结构化结束。

#### 当前状态与用户验收

- 当前状态：候选 `implemented` / fixture `isolated`。IAB 已记录，不是整站验收。
- 未标记 `verified / accepted / production`。

#### 阻塞、回滚和下一步

- 独立复核由 Codex 新会话启动，本 freeze 不启动。不要写回 canonical。OCR / 真模型 / 有成交持久回测仍未验证。

### 5.28 upstream_9a4bdcd_watchlist_import_codes_20260909

#### 用户目标与可见结果

- 目标：canduser 在批量导入对话框粘贴 `600000.SH` / `000001.SZ` 并点解析时，不再 Method Not Allowed，应出现去重后的解析结果；不自动写入自选。
- 未改前端源码。未改 canduser 密码。OCR 仍报告不可用。

#### GitHub 情报与固定上游点

- 上游 `9a4bdcd`。报告 `reports/watchlist-import-codes.md`；IAB `reports/browser-acceptance.md`。

#### 本地路由、Module、Adapter 与依赖接口

- `POST /api/watchlist/import-codes` 与 `/import-csv` 在 `/{symbol}` 之前。解析走 `watchlist_csv`，写入仍走 `/batch`。

#### 自动检查与构建

- 相关 pytest **44 passed**。`test_watchlist_ocr` 因 fixture 无 PIL 仍不可收集。前端未重跑。

#### Codex 内置浏览器目标运行面验证

- Codex IAB 记录见 `reports/browser-acceptance.md`。405 先被观察到；backend 85484 后 canduser 粘贴 3 行→匹配 2、导入所选 2、页面与 reload 均为 2/2、toast 已添加 2 只、errorlogs `[]`。本 freeze 只读到 `data-v18/tenants/usr_cf24e5fbf4793d24/user_data/watchlist.parquet` 2 行（`added_at` 2026-09-08T20:11:10Z）。admin 根自选仍是更早的 2 行。OCR 未验证。

#### 当前状态与用户验收

- 候选 `implemented` / fixture `isolated`。IAB 已记录 405 闭环。未标 `verified / accepted / production`。

#### 阻塞、回滚和下一步

- 独立复核由 Codex 新会话启动，本 freeze 不启动。不要正式回写。

### 5.29 upstream_9a4bdcd_review_f1_prefs_cache_20260909

#### 用户目标与可见结果

- 目标：修独立 review F1——两账户偏好文件若同纳秒 mtime 且同 size，不得串读/串写。用户侧栏仍是当前账户 UI 偏好，不写进服务器管道指数。
- 前端未改。本轮未重开 Codex 浏览器。fixture backend 94240；frontend 65402/65384 保持。

#### GitHub 情报与固定上游点

- 上游 `9a4bdcd07dfe999f123a8226608d4c90213fae5b`。独立 review `c0347c16` 不可 promote。报告 `reports/review-fixes.md`。

#### 本地路由、Module、Adapter 与依赖接口

- 只改候选 `preferences.load()` 缓存签名为 `resolve(path)+mtime_ns+size`。`load_server()` 不加这套缓存。正式树 `load()` 仍无缓存，未写回。

#### 自动检查与构建

- 相关 pytest **134 passed / exit 0**（含 prefs HTTP、watchlist 相关、分钟门控）。解释器 sandbox `venv-backend` Python 3.13.5 / Polars 1.44.1。全套未重跑；322f/1591p/64e 仍是旧 `844850aa`。

#### Codex 内置浏览器目标运行面验证

- 本会话未打开浏览器。只追加 live HTTP：admin/canduser prefs 200；canduser sidebar 仍是 IAB 的两只指数。见 `reports/browser-acceptance.md` §5b。

#### 当前状态与用户验收

- 候选 `implemented` / fixture `isolated`。未标 `verified / accepted / production`。

#### 阻塞、回滚和下一步

- 交全新独立 review。不要正式回写。RQ1/RQ2/RQ3 未改产品。

### 5.30 upstream_9a4bdcd_official_promotion_20260909

#### 用户目标与可见结果

- 目标：把已独立复核的隔离 candidate（上游 `9a4bdcd` 本地优先适配，含 F1 偏好路径签名）回写正式 one-trading。冲突保留本地魔改。用户页仍是 http://127.0.0.1:3011/。
- 正式实时开关保持原 ON，不拷候选 OFF。产品 cookie 仍是 `tf_session`。

#### GitHub 情报与固定上游点

- 上游 `9a4bdcd07dfe999f123a8226608d4c90213fae5b`。主记录：用户台 2026-09-09 正式晋升子记录。
- 独立 review：`c0347c16`/`68c9bfc7` 找出 F1/F2；`b698fe16`/`b5791856` 关闭两项；落地 `6fbf26e9`/`8d30da7f` `review_of` `299f223c` 通过（无新增 P0/P1）。

#### 本地路由、Module、Adapter 与依赖接口

- 正式树复制 303 个 allowlisted added/modified 文件。三份开发日志就地更新，不用候选旧 docs 覆盖。
- 测试 parquet 不进正式 `backend/data`。37 个 nested data 源码保留。

#### 自动检查与构建

- 正式解释器 Python 3.13.5 / Polars 1.44.1。相关 pytest **134 passed / exit 0**。隔离 `DATA_DIR`；`REGEN_BACKEND_DATA=no`。
- 正式 `tsc -b` / `vite build` exit 0。先前候选 vitest 222 只作源证据。
- 全套 322f/1591p/64e 仍是旧 `844850aa`，未重跑。

#### Codex 内置浏览器目标运行面验证

- 本会话未打开浏览器。Health 200 `v0.1.68`。Codex after-IAB（browser2/tab2，listeners 3510+3545/3018、3528/3011）记录见 `reports/browser-acceptance.md` §7。
- 主路径：admin 仍登录；涨跌家数/四指数与 before 同值；实时仍 ON；自选 14/14 真实行情；骏亚半年 K+44 指标；`/data` 41 目录未点采集；`/ai` 原卡+Hermes 入口。控制台 `[]`。
- **不能说全部数值不变**：情绪 66→65；市场脉搏空+质量 toast。Subrouter「已连接」只是 UI 配置，不是真实模型验证。收尾判断见 `reports/closeout.md`。

#### 当前状态与用户验收

- scoped **engineering verified**（总工工程验收 + Codex 主路径 IAB + 独立技术复核 `6fbf26e9`）。最终报告 `reports/final-acceptance.md`。
- **不是**用户亲自验收，**不是**远端部署，**不是**整体项目 `production`。

#### 阻塞、回滚和下一步

- 回滚产品源只用 `/Users/simon/备份/codex/20260909T051220-one-trading-official-promotion`。Hermes 脱离备份：`/Users/simon/备份/codex/20260909T053634-one-trading-hermes-detach`。
- 运行收尾已完成：Hermes **83190** 未重启，仍听 `127.0.0.1:8651` 且脱离旧 TTY；旧 `one-trading-user` 已清。Helper 仅拒绝重复启动分支已查，启动/恢复未验收。`e1206b40`/`6b972faf` 桥接失败保留为历史。

### 5.31 navigation_consolidation_20260909

#### 用户目标与可见结果

- 目标：左侧边栏把策略/回测/因子/挖掘收成一个「量化」入口，把监控中心/持仓提醒/信号库/风控·异动监控/交易收成一个「交易」入口；组页顶部用链接式标签切换现有功能。
- 用户台 frontend 导航/页面容器改动。复用现有 Screener、Backtest、Factors、Mining、Monitor、Lots、Signals、AbnormalMoves、Trading，不改交易业务、算法、后端或真实数据。
- 独立风控仍只在回测高级设置内，留在回测。交易侧把 AbnormalMoves 标成「风控 · 异动监控」，不新造风控页。

#### GitHub 情报与固定上游点

- 本轮无新 GitHub 审阅，不是上游功能移植。
- daisyUI tab/menu 文档只作结构与语义参考。未安装 DaisyUI，未迁移 Tailwind，未改主题或依赖。

#### 本地路由、Module、Adapter 与依赖接口

- 共享定义：`frontend/src/lib/navGroups.ts`。Layout 与 Settings/菜单设置共用分组、旧 `nav_order`/`nav_hidden` 兼容和显隐语义。
- 薄 pathless group layout：`frontend/src/components/GroupPageLayout.tsx` + 原 child routes。`/screener` `/backtest` `/factors` `/mining` `/monitor` `/lots` `/signals` `/abnormal` `/trading` 及 query/hash/state 保留。
- 新增稳定入口 `/quant`、`/trade`，默认进入当前身份可见的首个标签。外层标签走 path，不争用子页 `?tab=`。
- 监控仍仅 admin 可见；设置未加载不露出 admin 标签。未读徽标挂在交易组入口，只有真正打开 `/monitor` 才按旧语义隐藏。`monitor_badge_enabled` 开关改指交易组。
- 不自动写用户偏好迁移。隐藏单个旧 `/trading` 不会误藏整个交易组。
- fix1：当前组标签 `Link` 保活 pathname+search+hash+state（replace）；未选中标签只去裸路径。组侧栏改用 `Link` 写 `aria-current`，因为 RR 6.30.3 `NavLink` 用内部 `isActive` 覆盖 `aria-current`（`/quant` 对不上 `/screener`）。叶子入口仍走 `NavLink`。

#### 自动检查与构建

- 首轮针对性 vitest **36 passed / 5 files / exit 0**。
- fix1 后针对性 vitest **40 passed / 5 files / exit 0**（`GroupPageLayout` 9、`Layout.mobile` 19，含 F1 点击+state 与 F2 桌面/移动 aria-current）。`GroupPageLayout` 类型修正后再跑 **9 passed / exit 0**。
- `tsc --noEmit -p tsconfig.json` **exit 0**。`vite build --config vite.config.ts` **exit 0**（4.05s）。未生成 `vite.config.js`。
- 未重跑全套。未改后端。未调用 `dev.sh`。未重启 3018/8651/8650。

#### Codex 内置浏览器目标运行面验证

- **修前 IAB（Codex，仅属 fix 前版本）**：正式 Vite PID3528/3011 cwd frontend；backend 3510+3545/3018 与 Hermes 83190/8651 未重启。1280×900 侧栏 15 个主入口，只有一个量化/一个交易（原 22，合并 9 为 2）。量化 4 标签和交易 5 标签均实际点击，原内容可加载。`/lots` 上 badge 1 仍可见，monitor 页消隐。390×844 交易 5 标签完整可见且 `document.clientWidth=scrollWidth=390`。mobile drawer 合并入口点量化后关闭。`/factors?tab=library` 显示 77/77 因子，reload 及 back 后保持 URL 与内容，外层因子 `aria-current=page`。菜单设置显示 `/quant`、`/trade` 及交易「关闭数字提示」。最终 reload 后 console error `[]`。未改真实持仓/规则/偏好，未跑回测/挖掘/AI。
- **修后 IAB（Codex，非本 closeout 会话）**：同一 PID3528/3011，backend/Hermes 未重启。点当前因子保留 `/factors?tab=library#row`；Enter 切策略到裸 `/screener`；390×844 抽屉量化 `aria-current=page`，点交易到 `/monitor` 后关闭再切 `/lots`；1280×900 风控 · 异动监控到 `/abnormal`，交易 5 页签与交易组 `aria-current=page`。交付停在 `/abnormal`。完整步骤与限制见 `docs/navigation-consolidation-20260909/acceptance.md`。

#### 当前状态与用户验收

- 本地状态：**verified**（本轮用户台导航工程验收完成）。
- **不是**用户亲自全部业务验收，**不是** `accepted / production`。
- 最终验收：`docs/navigation-consolidation-20260909/acceptance.md`。
- 身份指针：实现 `5077cf13-aae8-49f2-a271-6ce47bf3496f`；指出 F1/F2 的复核 `650a8b5b-003c-4571-b2d9-03e801b7dc6e`（最终 `structured_final=false`，不是干净通过）；修复 `45b1f361-a10a-4642-9c50-b42bc3ac8a02`；修后复核 `f4fe45b0-32ec-477c-8129-6897d3d2a705`；最终复核 `575fd316-5650-4ba9-a06e-0afc2b1ca6f0` / session `12a37731-e272-4bcd-802b-71aca201d234`。40 tests 证据来自修复轮 controller PID 62980（12:29:55，exit 0），最终复核未重跑。

#### 阻塞、回滚和下一步

- 首轮备份：`/Users/simon/备份/codex/20260909-navigation-consolidation`（不要重写）。
- fix1 备份：`/Users/simon/备份/codex/20260909-navigation-consolidation-fix1`（不要重写）。
- closeout 文档备份：`/Users/simon/备份/codex/20260909-navigation-consolidation-closeout`。
- 证据：`/Users/simon/Trading/one-trading/docs/navigation-consolidation-20260909`。
- 已知不修：`GET /api/custom-signals/options` 因 `signals.py` `str_entries` 未定义而 500。既存后端缺陷，不声称信号创建数据链可用。
- 下一步：无本轮导航工程待办。信号 options 500 不在本条范围。

<a id="news_policy_workbench"></a>
### news_policy_workbench

#### 用户目标与可见结果

- `/news`：市场快讯（财联社/新浪/外媒三栏）与政策信息页签。左侧「数据」之后新增「资讯」，进入 `navGroups` 唯一导航，设置可排序/隐藏，桌面与手机共用。
- 快讯：时间、标题/正文、题材、原文、重要/规则情绪、独立刷新、展开、新条目；单源失败可见且保留上次数据。
- 政策：完整官方部门目录、按日倒序、部门筛选/搜索、默认/自定义重点部门增删保存恢复、官网、已入库历史关键词搜索与退出搜索、刷新、日期/来源/标题/原文、本地加载更多。关键词搜索只读本地，不联网。

#### GitHub 情报与固定上游点

- 主记录：`/Users/simon/Trading/用户台GitHub项目借鉴记录.md` 的 go-stock 条。本地 go-stock HEAD `e96f5d7262fae35698b4bebd4b8650f8bfdf0e71` 只是合流基线，**不是** 2026-09 政策页引入 commit。政策/三栏功能权威是 dirty 工作树文件 hash：`PolicyNewsList.vue` `4dc45ed4adcadb4e38b7b91e704236f190843a4748ffc524a6e163a9888e0bab`（untracked）、`policy_news_api.go` `b500037e04a4f032013e809b40ac6002727f11c588cb64b3f1dd052804d0295b`（untracked）、`gov_policy_lib_api.go` `dac2ef990e490aad0fdfd2f9f94b463ba057df38951325bb1fb469e204c8b10d`（untracked）、`market.vue` `772ba7e1df0fe465683a0f312caa492c913788ed456b547594d0cb7a965b2310`（dirty）、`newsList.vue` / `market_news_api.go` 与 HEAD 相同。
- `gov_policy_lib_api.go` 只服务 AI 工具 `SearchGovPolicyLibrary`，不是政策页入口；本轮不扩建远端政策库搜索。

#### 本地路由、Module、Adapter 与依赖接口

- 用户台：`frontend/src/pages/News.tsx`、`frontend/src/components/news/*`、`frontend/src/lib/news.ts`、`navGroups.ts` `/news`、`router.tsx`、`Layout.tsx`。
- 数据台消费：`GET /api/news/*` 只读缓存并附加只读元数据；`POST /api/news/*/refresh` 与重点部门写入显式触发。
- 重点部门按 `user_context` 账号隔离。
- 权限：`authorization.py` 只把 `/api/news` 加入 `_PERSONAL_MUTATION_PREFIXES`，不放宽既有路由。改前备份见 `/Users/simon/备份/codex/news-policy-20260909-154419/files/one-trading/backend/app/services/authorization.py`。本轮未改 `authorization.py`。
- 2026-09-11 元数据/错误面：`NewsMetadata` 显示缓存身份、生产者/聚合平台、最近成功/最后尝试/缓存更新（缺字段明确未知）；Query/Mutation 错误与空记录分开；快讯首日显示日期；政策无日期写「日期未知（未从网址猜测）」；刷新失败按源/部门隔离。`NEWS_CACHE_MODE=isolated_preview` 只标识隔离预览，默认只能叫配置的本地缓存。不暴露本机绝对路径。

#### 自动检查与构建

- 2026-09-09 日期误识别修复：政策日期必须通过公历校验；URL 栏目/专题编号不得当日期；无可靠日期留空并排在有效日期之后。首轮 `live-fetch.json` 保留；隔离缓存已 scrub。状态仍不是 accepted。
- 同日日期来源续修：`/202609/1194319.shtml` 被旧宽松 URL 正则拼成 `2026-09-11`。现只接受有边界的完整 URL 日期（`/2026/09/09/`、`t20260909_`、`/2026-09/06/`、`/2026/0907/`），不跨月目录与任意编号拼接；无证据留空，不拿文章编号或邻条日期补造。民委该条按官网同条列表日 + 原文 `PubDate` 记为 `2026-09-09`。主审已观察旧 UI 三栏展开/部门关键词/重点部门持久。不是 accepted/production。
- 同日独立复核 `review/independent-review.md`：技术 PASS，无 P1。P2-1 央行长编号 URL 与真实列表日碰撞被 reconcile 误清；P2-3 无读改写锁；P2-4 文档仍写 HEAD `e96f5d` / 23 passed / 495。`7d39a518` `failed/read_only_candidate_changed` 与 `c89fcd1c` `failed/protected_input_changed` 历史保持不变。
- 同日 P2-1/P2-3/P2-4 续修：条目带可选 `date_source=list|url|pubdate`；只把 `/YYYYMM/` 或 `/YYYY/MM/` 跨斜杠接到更长文章编号当拼接；长连续数字 ID 不得发明或清空本条列表日。政策 refresh/scrub 与单源市场替换加进程内锁并重新读当前缓存。前端代码未改。
- 后端针对性 pytest（本执行端亲眼看到，`python -B` / `PYTHONDONTWRITEBYTECODE=1`）：**39 passed**（三份新闻测试；历史首轮 23、日期来源续修 30）。含长 ID 真列表日、真月份目录拼接、同条真日期碰撞、未知仍未知、GET 零写零外连、确定性并发。
- 前端针对性 vitest：as_of P2-fix 未重跑、复用既有 32 passed。as_of 窄屏 UI / 独立复核 `e18ac0cf`：**33 passed**（`News.test.tsx` 6 含 class 契约、`navGroups.test.ts` 8、`Layout.mobile.test.tsx` 19）。controller `a82d81bd` build exit 0。Layout 既有 `data-sources` queryFn stderr，不是失败。不把自动测试写成用户接受。
- 同日数据 P2 独立复核 task `5613e51d`：技术 PASS（39 后端测试、GET 526、央行 15 日期）。附加 UI 核对超时，**不能**当 UI 复核通过。原 fingerprint `35b397ea…` 仅历史。`7d39a518` / `c89fcd1c` 仍失败；`1eab309c` 超时不是通过。
- 同日窄屏 UI 续修（仅用户台 `PolicyPanel` class）：改前主审 IAB 在 `678x863` `/news?tab=policy` 点央行后结果 SECTION 高 2px。单列给结果行 `minmax(20rem,1fr)` + `min-h-[20rem]`，侧栏 `max-lg:max-h-[min(22rem,40vh)]` 可滚；`lg` 仍两列。`News.tsx` 未改。jsdom **不能**验证真实几何。
- 2026-09-11 readiness 增量（本执行端亲眼看到）：后端 `test_news_api.py` / `test_news_service.py` / `test_news_metadata.py` / `test_news_permissions.py` / `free_sources/test_news_public.py` **57 passed**；前端 `news.test.ts` 7 + `News.test.tsx` 9 **16 passed**。未跑全站、未启动服务、未做 IAB。`Layout.mobile.test.tsx` 本轮未改，其中「实时行情 · 全市场」失败与本增量无关，不记为本包通过。
- 2026-09-11 P2 修补：原 workflow `wf-bb9c0f1c-efe0-4c8c-86c7-34318de7de9a` failed/verification_failed；独立审计 `bcc3ee1b-5c6f-44df-8edd-0deda29f30e6` partial/changes_requested。本轮只修三项 P2（政策新鲜度未知、失败写不补造成功时间、<xl 市场栏正文高度）。不改共享 Layout / `Layout.mobile`（19pass1fail 交 WP2）。jsdom class 断言 ≠ IAB 几何。政策页既有 `min-h-[20rem]` / 搜索 / 筛选 / 滚动契约未回退。本执行端看见：news pytest **62 passed**；vitest `news.test.ts` 7 + `News.test.tsx` 10 + `navGroups.test.ts` 8 **25 passed**。`pnpm run build` 失败于既有 `Layout.mobile.test.tsx` `mode` 与无关 `Review.tsx` null，不是本包源码；不伪称旧组合门变绿。未自称浏览器验收。详情 `p2-repair.md`。

#### Codex 内置浏览器目标运行面验证

- 2026-09-09 主审 Codex IAB（tab 2，`678x863`，不是 Cursor 观察；**只覆盖当时增量**）：`http://127.0.0.1:3041/news`；隔离 API `127.0.0.1:3048` / `DATA_DIR=/Users/simon/Trading/one-trading/data/news-isolated-20260909`；当时 3041=`97951`；3048=`97934` 无 reload。改后结果区高 381.8046875px；可滚到 2026-08-14；console error 0。观察原文：`docs/cursor-handoffs/news-policy-20260909/closeout/chief-ui.json`。
- 独立 UI `e18ac0cf`（session `7f91193c-b466-49db-90ec-2e80a85222d5`）Technical PASS / no P1，无浏览器。数据 `5613e51d` PASS 不覆盖其后 UI PING 超时。收口：`docs/cursor-handoffs/news-policy-20260909/closeout/acceptance.md`。
- 2026-09-11：本任务**未启动**任何服务。主审再次实查 3011/3018/3041/3048 均未监听。9/9、9/10 页面**不能**当成本增量验证。IAB pending，等负责人 `01a07a79-1c8e-73e0-af8f-85939177bb8b` 回填 isolated_preview 运行面后再做 Codex IAB。
- 2026-09-11 已发生 IAB 只作修前事实（390×844 市场三栏各约 222px，ul 正文 33/33/17px；政策 ul 可滚）。修后几何与真实运行结果待主审；后端无 reload，必须由运行负责人刷新后再做新 IAB。不能把旧 PID 旧模块当新代码。

#### 当前状态与用户验收

- 2026-09-09 增量：当时 `verified`（主审 IAB + 独立 UI Technical PASS）。只作 as_of 历史。
- 2026-09-11 readiness 增量：`implemented`。自动测试已跑；目标运行面与 Codex IAB **pending**。
- 2026-09-11 P2 修补：仍 `implemented`。原 failed 门保留。修后 IAB pending（等 owner 刷新 3018）。**不是** `verified` / `accepted` / `production`。
- **不是** 用户 `accepted` / `production`。自动测试 ≠ 用户验收。isolated_preview ≠ production。
- 基线分类（2026-09-12）：9/9 基础页属于 00:19 基线。9/11 readiness 元数据与 P2 是**基线不含 / 仅历史未重新授权**。39/57/62 passed 等原数字保留。

#### 阻塞、回滚和下一步

- 备份：首轮 `/Users/simon/备份/codex/news-policy-20260909-154419`；日期来源 `/Users/simon/备份/codex/news-policy-date-provenance-20260909-162024`；P2 `/Users/simon/备份/codex/news-policy-p2-fix-20260909-174907`；UI `/Users/simon/备份/codex/news-policy-ui-fix-20260909-182318`；文档收口 `/Users/simon/备份/codex/news-policy-closeout-20260909-183503`；2026-09-11 `/Users/simon/备份/codex/news-readiness-20260911-20260911-142548`；本轮 P2 `/Users/simon/备份/codex/news-p2-20260911-20260911-172138`。不要用旧备份整份覆盖公共文件。
- 交接：`/Users/simon/Trading/one-trading/docs/cursor-handoffs/news-readiness-20260911/`（非实施权威）。P2 证据 `p2-repair.md`。9/9 收口仍见 `docs/cursor-handoffs/news-policy-20260909/closeout/acceptance.md`。
- 下一步：运行负责人 `01a07a79-1c8e-73e0-af8f-85939177bb8b` 刷新无 reload 的 3018 后再由主审做新 IAB。正式接入只按 `formal-admission-plan.md` 另行授权，本轮不批写、不调度、不 promotion。

## 5. 后续条目模板

```md
### feature_name

#### 用户目标与可见结果
#### GitHub 情报与固定上游点
#### 本地路由、Module、Adapter 与依赖接口
#### 自动检查与构建
#### Codex 内置浏览器目标运行面验证
#### 当前状态与用户验收
#### 阻塞、回滚和下一步
```
