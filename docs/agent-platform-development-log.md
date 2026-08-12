# one-trading Agent 台开发日志

最近维护：2026-08-12（多用户 Hermes 最新版 Zeabur 上线验收）

适用项目：`/Users/simon/Trading/one-trading`

职责：只记录 one-trading 本地 Agent Module、模型 Adapter、工具、策略生成、量化决策、复盘解释、权限和审批的设计、实现、验证与运行状态。

## 0. 权威边界

- GitHub 上游项目与采用判断：`/Users/simon/Trading/Agent台GitHub项目借鉴记录.md`。
- 工具、能力、消费接口与权限：`/Users/simon/Trading/Agent台工具与能力目录.md`。
- 未来工程优先级、权限前置和开工门：`/Users/simon/Trading/Agent台下一步工程工作计划.md`。
- 用户可见入口：`/Users/simon/Trading/one-trading/docs/workbench-development-log.md`。
- 数据集实现和准入：`/Users/simon/Trading/one-trading/docs/data-platform-development-log.md`。
- 本文件不复制上游完整调查，不把 Codex 外部工具或 AGD 插件已安装写成 one-trading Agent Runtime 已完成。

## 1. 本地状态词

- `planned`：目标、用户价值和权限边界已定义。
- `designed`：Interface、数据依赖、Adapter、审计和验收路径已明确。
- `sandbox`：本地隔离实现可运行，但未接入正式用户流或外部动作。
- `verified`：自动检查、目标运行面和相关失败路径已验证。
- `approved`：用户确认能力、权限和使用价值，可进入受控启用。
- `production`：approved 能力已在正式目标运行面启用并复核。
- `blocked / no-go / superseded`：阻塞、明确不采用或被后续实现替代。

GitHub 的“设计采纳/工程机制参考”不能替代上述本地状态。

## 2. 初始化边界

- 2026-08-01 本次工作只建立三台文档与规则体系，没有修改 one-trading Agent 代码、启动服务、调用模型、运行回测或执行外部动作。
- one-trading 当前存在 AI 设置和策略/回测基础，但尚未据此证明独立 Agent 台已经形成。
- Codex 的 AGD 工作区记忆是外部开发工具，不是 one-trading 产品 Runtime。

## 3. 当前能力条目

### 3.1 AI 设置入口

- GitHub 情报：go-stock、tickflow-stock-panel。
- 本地线索：`frontend/src/pages/settings/AI.tsx` 等。
- 当前状态：`planned`（现有入口待在具体任务中重新核对代码、模型调用链和真实运行面）。

### 3.2 GitHub 远程研究工具链

- GitHub 情报：github-mcp-server、git-mcp、gitingest、repomix。
- 边界：属于 Codex 工作方式，不等于 one-trading Agent 产品功能。
- 当前状态：不进入 one-trading 生命周期；只在 Agent 能力目录记录可用工具和权限。

### 3.3 量化决策 Module

- GitHub 情报：portwine 的在线 `step()`、动态 Universe 和分析器问题清单。
- 推荐 Interface：`AgentDataView(as_of)` 与 `DecisionIntent`，通过 Adapter 进入现有 StrategyDef/回测撮合链。
- 明确不采用：portwine Runtime、数据 Provider/Store 和 Alpaca 实盘执行。
- 当前状态：`planned`。
- 数据阻塞：动态历史 Universe、退市/状态、可信公司行动、PIT 基本面、长周期 benchmark 和相应数据准入尚未闭合。

### 3.4 AI 个股分析财务日期序列化修复

#### 用户目标、权限与外部副作用

- 用户目标：修复“个股分析 → AI 个股分析”对 `300274.SZ` 返回 `Object of type date is not JSON serializable`、无法生成报告的问题。
- 授权边界：只修改 one-trading Agent 台的本地分析服务与聚焦回归测试；不修改财务 Parquet、财务 API、前端、AI 配置或 Provider。
- 外部副作用：真实运行面验证调用了当前已配置的 AI Provider；Codex 内置浏览器主路径完成后，按既有产品行为保存了一条 `300274.SZ` 验证报告。未下单、未外发消息、未部署。

#### Interface、Module、Seam 与 Adapter

- Interface：`POST /api/stock-analysis/analyze`，NDJSON 协议保持 `meta / delta / error / done` 不变。
- Module：`backend/app/services/stock_analyzer.py`。
- 修复边界：`_load_financials()` 将 Polars `to_dicts()` 产生的 Python `date / datetime` 在内存中转为 `isoformat()`；保留财务字段集合、数值精度、排序和最近两期语义。
- 测试 Seam：`analyze_stock_stream()`；使用临时财务 Parquet、fake 日 K repository 和 fake AI Provider，覆盖真实财务读取、prompt 构建与流式事件序列。

#### 数据台和用户台依赖

- 只读消费 `data/financials/metrics/part.parquet` 与 `data/financials/income/part.parquet` 的强类型日期字段；未迁移、重写或降级数据台 schema。
- 用户台继续消费原有 NDJSON 事件和报告保存接口；本轮未修改前端错误分类或“去配置 AI”按钮逻辑。

#### 审计、确认、失败和回滚语义

- RED：新增回归测试在旧实现下稳定得到 `meta -> error`，精确错误为 `Object of type date is not JSON serializable`，且未进入 fake AI Provider。
- GREEN：最小日期转换后得到 `meta -> delta -> done`，prompt 中 `period_end=2026-03-31`、`fetched_at=2026-04-28T15:30:00`。
- 回滚：移除 `_load_financials()` 的日期转换分支并删除对应测试文件即可；无数据迁移需要回滚。

#### 自动检查与真实目标运行面

- 聚焦测试：`13 passed`（新增 stock analyzer 回归、engineering closure、financial normalize、public financials）。
- 静态检查：本轮范围 ruff 通过，新增测试已格式化；目标文件仍有两项本轮之前已存在的 `UP035 / RUF100`，未扩大范围处理。
- 当前运行面：后端 `127.0.0.1:3018` 热重载到本轮新 worker 后，`300274.SZ` 返回 `meta + 2174 delta + done`，正文 3084 字符，无日期序列化错误。
- Codex 内置浏览器：`http://127.0.0.1:3011/stock-analysis` 完成真实“AI 个股分析”主路径，报告显示六个章节、完整免责声明和完成态操作；控制台无本轮错误。
- 报告持久化：验证报告创建时间 `2026-08-01T22:43:59`，内容 2728 字符，summary 已保存。

#### 当前状态与用户批准

- 当前状态：`verified`。
- 用户已明确授权实施本次修复；尚未将该能力标记为 `approved` 或 `production`。

#### 阻塞和下一步

- 本次日期序列化故障无剩余阻塞。
- 前端对所有包含“AI”字样的错误统一显示“去配置 AI”属于独立用户台问题，本轮未处理。

### 3.5 自选股票 AI 上下文贯通

#### 用户目标、权限与外部副作用

- 用户目标：从自选股选定一只股票后，在 AI 功能目录的四个能力之间保持同一 `symbol + name`，由用户选择适合的能力，不改变完整自选列表。
- 授权边界：只修改本地前端路由上下文、复盘关注输入、策略生成草稿及相应测试；未调用模型、未保存策略、未生成或改写 AI 报告、未下单、未外发消息、未部署。

#### GitHub 情报与固定上游点

- 本轮没有新增 GitHub 审阅；依据 one-trading 现有 AIHub、财务分析、复盘、策略生成和个股分析调用链实施。

#### Interface、Module、Seam 与 Adapter

- 上下文 Interface：页面查询参数 `symbol`、`name`，由 AIHub 的四个能力链接共同透传。
- 目录 Module：`frontend/src/pages/AIHub.tsx` 显示当前股票并为现有目标 URL 合并查询参数。
- 复盘消费 Seam：`frontend/src/pages/Review.tsx` 将股票写入可编辑的重点关注输入；既有生成和报告保存流程会继续使用该输入。
- 策略消费 Seam：`frontend/src/pages/Screener.tsx` 与 `frontend/src/components/screener/StrategyBuilderDialog.tsx` 将股票写入可编辑的策略名称、说明和规则草稿，并明确要求提炼可泛化条件。
- 个股分析和财务分析继续使用其既有股票参数接口，未复制分析逻辑。

#### 数据台和用户台依赖

- 用户台负责自选入口、当前股票提示和跳转；Agent 台仅消费用户选择的股票上下文。
- 没有修改数据台 Provider、Parquet、行情范围或 API schema；复盘仍是市场级能力，股票只作为重点关注对象。

#### 审计、确认、失败和回滚语义

- 新增回归先证明旧实现只有 AI 个股分析继承上下文，其他三条路径失败；实现后四条链接及复盘、策略消费断言通过。
- 回滚只需恢复 AIHub 卡片原 URL、移除复盘关注预填和策略草稿预填；无持久数据、权限或外部动作需要恢复。

#### 自动检查与真实目标运行面

- AIHub、原有自选到 AI 流程、复盘上下文、策略生成上下文等前端聚焦测试全部通过；相关生产构建通过。
- Codex 内置浏览器实测 `300502.SZ 新易盛` 在 AIHub 四条路径中保持一致；复盘输入和策略草稿均实际消费该上下文。
- 控制台无本轮功能 error，仅有既存 React Router v7 future flag 提醒。

#### 当前状态与用户批准

- 当前状态：`verified`。
- 用户已授权本轮修复；尚未标记为 `approved` 或 `production`。

#### 阻塞和下一步

- 本轮无功能阻塞。后续如需让市场复盘或策略生成对单股执行专属模型 prompt，应作为独立 Agent 能力设计和授权，不能仅凭路由参数宣称已具备。

### 3.6 Hermes `one-trading` 个人 Agent 对话沙箱

#### 用户目标、权限与外部副作用

- 用户目标：在本机已安装的 Hermes Agent 中新建 `one-trading` Profile，并在用户台 AI 板块增加可直接对话的个人 AI 助理入口，先完成一条真实试用链。
- 授权边界：允许创建/配置本机 Hermes Profile、独立 loopback gateway/launchd 服务，修改 one-trading Agent 后端 Adapter 与用户台入口，并更新 Agent 台权威记录；未授权部署、多用户生产、Hermes 升级、外发消息、账户操作或交易。
- 外部副作用：真实验证调用了现有外部模型 provider；对话与 Session 保存到本机 `one-trading` Profile。新增 Session 标题修改与删除能力，但浏览器验收全部取消，没有改名或删除真实 Session；没有写 one-trading 业务数据、策略、报告或账户，没有下单、外发或部署。

#### GitHub 情报与固定上游点

- Hermes 完整主记录：`/Users/simon/Trading/Agent台GitHub项目借鉴记录.md#71-nousresearchhermes-agent`；在线固定点 `main@a1da384c6d968000773ba0d1617d6931dfe25748`。
- 本机实际运行 checkout：`/Users/simon/.hermes/hermes-agent`，`main@91937a6dc3ffbbe2f3be91a500f0ecf962c4cf53`；`hermes --version` 报告 `v0.20.0`。本轮未升级或修改 Hermes 仓库源码。
- Pi 对比记录：`/Users/simon/Trading/Agent台GitHub项目借鉴记录.md#72-earendil-workspi`；只保留低层 harness/协议参考，没有进入本地 Runtime。

#### Interface、Module、Seam 与 Adapter

- Profile：`/Users/simon/.hermes/profiles/one-trading`；专属 SOUL 约束其身份、记忆写入和禁止动作；CLI 别名 `/Users/simon/.local/bin/one-trading`。
- Runtime：launchd `ai.hermes.gateway-one-trading`，数据工具验证重启后 PID `56068`，API Server `127.0.0.1:8650`，`max_concurrent_runs=1`；API model route `one-trading` 固定到 `grok-4.5`，通过 one-trading loopback 模型桥接复用用户台 xAI OAuth。
- 工具权限：启用 `memory / session_search` 与 Profile-local MCP `one-trading-data`；MCP 仅有目录发现、单视图查询两个只读工具。web、browser、terminal、file、code execution、skills、todo、delegation、cron、computer-use、外部消息与多媒体工具均禁用；loop guard hard stop 开启。
- 后端深 Module：`backend/app/services/hermes_agent.py` 统一处理 Profile 配置、Bearer auth、状态、Session、历史和 Hermes SSE → one-trading NDJSON；`backend/app/services/hermes_model_proxy.py` 与 `/api/hermes-xai/v1/*` 隐藏用户台 OAuth 刷新、模型锁定及 `responses / chat-completions` 协议差异。
- 数据深 Module：`backend/app/services/user_console_data.py` 维护 68 个精确只读视图、参数 allowlist、loopback/internal-key 鉴权、敏感字段脱敏和输出预算；`backend/app/api/hermes_data.py` 只开放 `/catalog` 与 `/query`；`backend/scripts/hermes_user_console_mcp.py` 把这两个 Interface 注册为 `one-trading-data` stdio MCP。默认无筛选目录为 745 bytes 的领域摘要，按 domain/search 才展开视图，避免整目录占满 Agent 上下文。
- Session 路由：创建 Session 时锁定 Profile 的 `one-trading` API model route，避免命名 custom provider 在恢复时降级成无凭据的 bare `custom`；`HermesAgentAdapter.list_sessions()` 与 `GET /api/hermes-agent/sessions` 只转发 Hermes 原生列表中的 client-safe 字段并过滤空 Session。新增 `PATCH /api/hermes-agent/sessions/{id}` 与 `DELETE /api/hermes-agent/sessions/{id}`，后端用 Bearer credential 转发到 Hermes 原生 Session API；标题在前后端均限制为非空且最多 120 字符。前端不接触 Hermes/API/provider credential，也未新增归档动作。
- 用户台：`frontend/src/pages/HermesAgentChat.tsx`、`frontend/src/pages/AIHub.tsx`、`frontend/src/lib/api.ts`、`frontend/src/router.tsx`；入口 `/ai/hermes`，支持新对话、历史恢复、流式回复、状态/边界提示和同 Session 连续消息。

#### 数据台和用户台依赖

- 当前 Agent 可读取用户台已展示或支撑展示的 11 个领域、68 个只读视图：system、data、extended_data、market、stock、financial、index、strategy、monitor、reports、backtest。覆盖行情、自选、K 线、财务、指数、策略定义、监控结果、数据目录、扩展数据、已保存报告和回测状态/因子字段；不会主动同步、刷新、保存、删除、清理或执行回测。
- `announcement_events` 只在隔离候选与历史记录中，当前 checkout 无对应用户运行面，因此没有伪装成已接入；账户/持仓/交易后端尚未实现，`/trading` 仅为规划占位页，且账户、订单、交易、认证/设置路径没有进入 allowlist。本轮没有修改 Provider、Parquet、业务数据或交易链。
- 用户台只负责可见卡片、对话交互和本地保存告知；用户台短指针见 `/Users/simon/Trading/用户台产品与界面能力目录.md`，目标运行面证据见工作台开发日志 `hermes_agent_personal_chat_sandbox`。
- 未来数据接入必须新增受限 one-trading 工具 Adapter，并绑定 `as_of`、权限、审计和数据台 accepted Interface；不得直接扩大本 Profile 文件权限。

#### 审计、确认、失败和回滚语义

- 首次真实调用暴露本机 xAI OAuth `invalid_grant`；在切换 provider 前，已备份到 `/Users/simon/备份/codex/20260810-1751-hermes-one-trading-profile-before-provider-switch`，README 记录原因、原路径和时间。
- 注册数据 MCP、更新 SOUL 和重启 gateway 前，另备份 Profile 配置、环境、launchd plist 与 SOUL 到 `/Users/simon/备份/codex/20260810-2059-one-trading-hermes-before-data-mcp`；README 记录原因、全部原路径和时间。
- 随后只复用本机既有 custom provider 配置，未把 provider credential 写入仓库、前端或用户可见响应。Hermes 命名 custom provider 的 Session API 恢复问题通过 Profile 自有 `model_routes.one-trading` 与确认锁解决。
- one-trading Adapter 将 Profile 不可用、Session/历史失败、HTTP/SSE 中断和 Hermes error 转为不含凭据的用户错误；状态接口只返回 profile/model/version/toolset 等非敏感字段。
- 删除属于显式副作用：用户台必须先展示永久删除提示并二次确认；删除当前 Session 后同时清除前端本地 Session 指针与消息区。浏览器验收不提交改名或删除，真实写路径由 MockTransport 和组件测试验证。
- 回滚：代码侧移除新增 router/page/API/tests；Runtime 侧停止并卸载 `ai.hermes.gateway-one-trading`，删除 CLI 别名，并从上述备份恢复 Profile。任何删除 Session/长期记忆需另行确认，本轮未执行清理。

#### 自动检查与真实目标运行面

- 后端：Hermes 数据 + Agent + 模型桥接聚焦测试 `11 passed`；目标 ruff format/check、MCP Python compile 与 `git diff --check` 通过。
- Session Adapter 跟进：`backend/tests/test_hermes_agent.py` 2 项通过，覆盖列表请求参数、空 Session 过滤、状态/创建/历史/流式以及原生 `PATCH/DELETE` 契约；目标 ruff check 通过。
- 前端：本轮 `HermesAgentChat.test.tsx` 5 项通过，其中两项覆盖重命名持久化与删除前确认；目标 ESLint、TypeScript/Vite 生产构建与 `git diff --check` 通过。只保留项目既有 `api.ts` 混合动静态导入与大 bundle 提醒。
- Hermes 原生 API：首次真实验证暴露 API model route 仍调用 `/chat/completions`，补齐桥接协议后第二次真实调用返回助手文本“Grok 与 Hermes 已接通。”，`runtime_provider=custom`、`runtime_model=grok-4.5`、`model_lock=confirmed`。
- 记忆：`hermes memory status` 确认 Holographic installed / available / active；Profile 本地 `memory_store.db` 已初始化。内建 Memory/User profile 和 `memory` tool 均仍启用。
- MCP 与数据运行面：`hermes mcp test one-trading-data` 在 576ms 建连并发现 2 个工具；68 视图目录覆盖 11 个领域，代表性 11 领域查询均为 HTTP 200。Hermes 原生真实查询调用 `mcp__one_trading_data__one_trading_data_query`，正确返回 `financial_metrics` 的 600519.SH 2026 一季报和 ROE 10.57%，同时保持 `grok-4.5 / model_lock=confirmed`。
- Codex 内置浏览器：`http://127.0.0.1:3011/ai/hermes` 实际显示 `模型：grok-4.5`、`Holographic 长期记忆`、`用户台数据 · 68 个只读视图`。新对话先按 domain 读取 market/stock/financial 目录，再完成 `market_overview`、`watchlist_enriched`、`financial_metrics(600519.SH)` 三项真实查询并给出 view、as_of/查询时间与来源口径；页面回复明确未涉及账户或交易。
- 浏览器控制台无本轮 error；只有项目既有 React Router v7 future flag warning。
- Session 菜单浏览器验收使用同一构建的隔离 `127.0.0.1:3118/ai/hermes`：10 个真实 Session 均显示菜单，行内重命名和删除确认正常；两项都取消，Hermes 会话库未发生本轮写入。默认 `3018` 既有后端当时无响应，未重启或替换；隔离进程已退出。

#### 当前状态与用户批准

- 当前状态：`verified`。
- 用户已授权创建本机试用链；尚未完成实际使用验收，因此不能标记为 `approved / production`。

#### 阻塞和下一步

- 当前单用户试用无阻塞，用户可直接在保留的 Codex 内置浏览器 `/ai/hermes` 页面继续对话。
- 尚未交付“每个产品用户一个 Hermes Agent”的多用户服务器：需另行设计 user/profile mapping、认证、租户隔离、进程或 multiplex 策略、容量测量、并发配额、备份/删除、worker 回收和数据工具权限；不能从本机单 Profile 结果外推生产容量。
- 当前只读数据链已接通；后续不应继续横向扩大工具数量，先由用户实际试用 68 个视图，再决定是否补公告 accepted 数据集、统一 `AgentDataView(as_of)`，或另建有副作用的回测执行工具。

### 3.7 Hermes `lieflat-charts` Skill 适配

#### 用户目标、权限与外部副作用

- 用户目标：让本机 `one-trading` Hermes Profile 使用已经安装的 `lieflat-charts`，在读取用户台数据后主动按该 Skill 选择图型；同时为未来服务器自带能力保留明确实现路径，但本轮不上传或部署服务器。
- 授权边界：允许修改本机 `one-trading` Profile、SOUL、one-trading 状态 Adapter/用户台可见状态和权威文档；允许重启该 Profile 的独立 gateway 并做一次真实模型/工具调用。没有授权升级 Skill、复制仓库、部署、生成生产镜像、商业分发、账户/交易或开放高权限工具。
- 权限结果：API Server toolset 从 `memory / session_search` 增加为 `memory / session_search / skills`；`terminal / file / code_execution / browser / web / messaging` 继续关闭。数据 MCP 仍只有目录发现和单视图查询两个只读工具。

#### GitHub 情报、许可证与单一权威副本

- 主记录：`/Users/simon/Trading/Agent台GitHub项目借鉴记录.md#73-larashero3-dotcomlieflat-charts`。
- 本机权威 Skill：`/Users/simon/.agents/skills/lieflat-charts`，固定 `7421362b4650557d2123c37555a18e4e323f93e7`；本轮 validator 通过 `22 HTML / 25 text`，未更新到上游 `main@e05f777261a774c945bdd0157817ef68f3c4766d`，也未在 Profile 或仓库复制第二份。
- 许可证：`PolyForm Noncommercial 1.0.0`。本机个人试用继续；商业或付费多用户服务器需先取得商业授权或替换实现，许可证门未通过时不得打进生产镜像。

#### Interface、Module、Seam 与用户台依赖

- Profile `/Users/simon/.hermes/profiles/one-trading/config.yaml` 新增 `skills.external_dirs: [/Users/simon/.agents/skills/lieflat-charts]`，并只给 `api_server` 平台新增 `skills` toolset。保留 `.no-bundled-skills`，避免意外加载其他内建能力。
- `/Users/simon/.hermes/profiles/one-trading/SOUL.md` 约束图表、排行、变化、构成或明显可视化数值问题先查询 one-trading 数据，再调用 `skill_view(name="lieflat-charts")`；先比较 Lupi/Basics，输出模板编号、`view`、`as_of` 与来源。当前没有 Artifact renderer，因此不得声称图表已经渲染；除非用户明确要求，也不返回整份 HTML。
- `backend/app/services/hermes_agent.py` 在现有状态调用中读取 `/v1/skills`，只返回非敏感的 `enabled_skills` 与 `lieflat_charts_enabled`；`backend/tests/test_hermes_agent.py` 覆盖发现结果。
- `frontend/src/lib/api.ts` 补状态类型；`frontend/src/pages/HermesAgentChat.tsx` 的 Agent 设置增加 `图表 Skill · Lieflat Charts`；组件测试覆盖该可见结果。用户台仍不读取 Profile 文件或 Skill 路径。

#### 备份、启动与回滚

- 修改前备份：`/Users/simon/备份/codex/20260811-1633-one-trading-hermes-before-lieflat-skill`。README 记录备份原因、Profile config/SOUL、launchd plist、目标代码/文档的全部原始绝对路径、时间和回滚说明。
- gateway 通过 `launchctl kickstart -k gui/$(id -u)/ai.hermes.gateway-one-trading` 重启；验证时 Hermes gateway PID `3926`，`/health` 为 200、版本 `0.20.0`。PID 属瞬时运行证据，不作为长期配置事实。
- 回滚：恢复上述 Profile config/SOUL 与目标代码/文档后重启独立 gateway；不会删除 Hermes Session、Holographic memory 或用户数据。若仅撤回 Skill，可移除 exact external dir 与 `api_server` 的 `skills` toolset，并保留原记忆/数据 MCP。

#### 自动检查与真实目标运行面

- Skill validator：`22 HTML / 25 text` 通过；`hermes skills list` 只发现 1 个本地 Skill `lieflat-charts`；`/v1/skills` 返回同名条目。
- 权限：`/v1/toolsets` 只启用 `skills / memory / session_search`；Hermes tool summary 再确认终端、文件、代码执行、浏览器、Web、消息和外部动作均未启用。
- 数据 MCP：`hermes mcp test one-trading-data` 357ms 建连并发现 2 个工具。
- 后端：Hermes Agent/数据/模型桥接聚焦测试 `11 passed`；目标 ruff format/check 通过。
- 前端：`HermesAgentChat.test.tsx` 5 项通过，包含 `图表 Skill / Lieflat Charts`；目标 ESLint 通过；TypeScript/Vite 生产构建通过。只保留项目既有 `api.ts` 混合动静态导入与大 bundle warning，没有新增构建错误。
- 为避免影响正在监听 `3011` 的发布版，本轮在 `127.0.0.1:3018` 启动无 lifespan 的开发验收后端，只初始化现有 DataStore/Repository，不启动实时行情、盘后调度、扩展拉取或五档补跑；Vite 用户台使用临时 `127.0.0.1:3021`。该运行面只用于本轮本地试用，未部署。
- Hermes 真实 Session `api_1786437722_ca0d509b` 同时调用 `skill_view`、`mcp__one_trading_data__one_trading_data_catalog` 与 `mcp__one_trading_data__one_trading_data_query`；runtime 返回 `provider=custom / model=grok-4.5 / route_source=session_model_lock / model_lock=confirmed`。
- 真实数据为 `market_overview`、`as_of=2026-08-10`、样本 509 只。回答比较 `F1 Rung Bars / F5 Tick Rows / L2 Dot Cascade` 后选择 `F1`，并明确写出非实时、非全市场、来源和数据质量缺口；没有生成 HTML、写文件或读取账户/交易数据。
- Codex 内置浏览器 `http://127.0.0.1:3021/ai/hermes`：Agent 设置真实显示 `Profile 已连接 / one-trading / grok-4.5 / Holographic / 68 个只读视图 / 图表 Skill · Lieflat Charts`；历史 Session 能恢复上述完整回答与实际工具列表。控制台 error 为 0，仅有项目既有 React Router v7 future flag warning。

#### 服务器候选与当前状态

- 未来服务器使用 `SkillSupplyManifest + Local/Server Adapter`：manifest 固定 source URL、commit、digest、license、validator、install path 与 toolset；镜像或受管共享卷只保存一份只读 Skill，所有用户 Profile 引用同一路径，各自的 config/SOUL/session/memory/log 继续隔离。
- 图表文件/图片不是本轮能力。后续若需要可视 Artifact，必须另建只接收结构化 chart spec 与获准数据快照的最小 Adapter，并以 CSP/隔离 iframe 或服务端渲染限制输出；不得用开放 terminal/file/code execution 代替。
- 当前本地状态：`verified`；仍待用户实际试用后决定是否 `approved`。服务器工作包 `A-P1-03` 为 `candidate`；由于许可证、Artifact Interface、多租户 Runtime 和部署授权均未闭合，不能写成服务器已自带或 production。

### 3.8 多用户受管 Hermes Profile

#### 用户目标、权限与外部副作用

- 将发布树的账户到 Hermes Profile 一对一映射、Profile-scoped 内部凭据、Session/记忆隔离、服务器统一 Grok 订阅与每日用户额度合入本地主开发树。
- 管理员只读查看用户 AI 使用、策略和历史对话；不能代用户发送、修改或删除。终端、文件、代码执行、浏览器、消息和下单等高副作用能力没有因此开放。

#### Interface、Module、Seam 与 Adapter

- `backend/app/services/hermes_tenant.py` 创建并校验 `ot-<user_id>` 受管目录和 Profile 凭据；`hermes_agent.py` 对每次 Hermes 请求强制 `/p/<profile>`，网关忽略前缀时 fail closed。
- `hermes_model_proxy.py` 只代理服务器统一 xAI/Grok 凭据，并在上游就绪后才扣用户额度；`hermes_user_console_mcp.py` 用 Profile-scoped 数据 key 调用精确只读路径。
- `hermes_runtime.py` 与 `Dockerfile.one-trading` 固定 multiplex gateway、Hermes commit、`aiohttp==3.14.1` 和持久根；默认本地开关仍关闭，不能把代码存在写成运行时已启用。
- 认证来源 IP 只在直连 peer 位于 `AUTH_TRUSTED_PROXY_IPS` 时接受 `X-Forwarded-For`，避免首次设置与登录限流被直接伪造。

#### 自动检查与真实目标运行面

- as_of 2026-08-12，基底 HEAD `56d481076c008efca9ff40db8f5c89139bb7f600` 加本轮未提交移植：后端全量 393 项通过、1 项跳过；包含租户、Profile 路由、模型代理、额度、管理员只读、Runtime 打包与 fail-closed 测试。
- 隔离 `127.0.0.1:38118` 为 Alice/Bob 创建不同的 `ot-<user_id>` Profile 和 tenant marker；由于本轮未启动真实 multiplex gateway，两者状态均按设计返回 unavailable，没有回退到共享 Profile。
- 随后用 `Dockerfile.one-trading` 构建完整本地发布镜像并短暂运行真实 multiplex gateway；Alice/Bob 分别经 `/p/<profile>/health`、`/v1/models`、`/v1/toolsets` 返回 connected，Profile 分别为 `ot-usr_890f96555a37e45f` 与 `ot-usr_9ebdfe3685dd37ab`。容器、账户、数据与验证镜像均已清理。
- Hermes Runtime 检测到其 SQLite 3.46.1 存在 WAL-reset 风险并自动降级为 `journal_mode=DELETE`；本轮没有数据损坏或错误，但正式高并发部署前仍应升级到 Hermes 提示的修复版 SQLite 并重新做重启/并发验收。
- 前端 Hermes/AI/管理员测试包含在 35 文件、132 项全通过；Codex 内置浏览器验证管理员能看到两个 Profile，普通用户只看到自身账户空间和额度，控制台 error 为 0。

#### 当前状态、回滚和下一步

- 当前状态：代码、隔离边界和短暂发布容器 Runtime 为 `verified`；本地主开发实例默认仍未启用多用户 Hermes，不能标记 `approved / production`。
- 本轮没有调用真实模型、没有写正式 Session/记忆、没有部署。真实启用必须提供受管 Hermes runtime、持久卷、服务器 Secret、`COOKIE_SECURE=true`、受信代理列表，并完成双账户重启持久性与失败恢复验收。
- 回滚使用 `/Users/simon/备份/codex/20260812-003726-one-trading-pre-release-feature-port` 恢复主开发树；正式 Profile/PVC 删除或迁移需另行明确授权。

### 3.9 Hermes 当前账户分析历史只读权限

#### 用户目标、权限与外部副作用

- 用户目标：让用户版 Hermes Agent 能看见并读取当前登录账户在个股分析、财务分析和大盘复盘中已经保存的历史报告，同时可查询行业/概念已有的轮动与资金流历史。
- 授权结果：只增加当前账户历史的目录与正文读取，不增加保存、修改、删除、同步、刷新、下单、外发、文件或系统权限；不允许读取其他账户的报告。
- 本轮没有调用真实模型，没有新建正式 Hermes Session/长期记忆，没有修改正式 Profile、服务器环境变量或持久业务数据，也没有部署。

#### Interface、Module、Seam 与 Adapter

- `backend/app/services/analysis_history.py` 只投影现有 `stock_reports / ai_reports / market_recap_reports` 三个功能自有存储，不搬迁或复制报告；`list_analysis_history()` 返回不含正文的轻量目录，`get_analysis_history_report()` 按 `kind + report_id` 返回一份完整正文。
- 新增只读 HTTP Interface：`GET /api/ai-history/reports`，支持 `kind / symbol / limit`；`GET /api/ai-history/reports/{kind}/{report_id}` 只读取一个精确报告。目录与详情都声明 `scope=current_account / mode=read-only`，正文标记为不可信数据。
- Hermes `one-trading-data` MCP 仍只有 `one_trading_data_catalog` 与 `one_trading_data_query` 两个工具，没有扩大工具数量。只读视图由 68 个增加到 70 个：`analysis_history` 先返回目录，`analysis_history_report` 再按需读取正文；原三类整包报告视图保留兼容。
- MCP 说明明确：已保存报告先发现 `domain=reports`，再执行目录 → 单条正文；行业/概念历史使用 `domain=market` 下已有的 `rps_rotation` 与 `fund_flow_board_history`。行业分析页当前不生成或保存独立 AI 报告，因此没有伪造“产业 AI 报告历史”。

#### 账户隔离、失败与回滚

- 浏览器与 Hermes 内部桥接都继续依赖 `user_context`；报告源通过 `DATA_DIR/tenants/<user_id>/user_data`（owner 为兼容的 `DATA_DIR/user_data`）选择当前账户目录。Profile-scoped data key 先映射回账户，再由精确 GET allowlist 进入历史接口。
- Alice/Bob 端到端桥接测试证明：各自目录只出现自己的报告；Alice 请求 Bob 的 `report_id` 失败为 502（内层报告接口为 404），响应不包含 Bob 正文。错误 Profile/key、非 allowlist 路径和写方法仍然失败关闭。
- 报告正文继续经过 Hermes 数据 Module 的字符串/总量预算与敏感字段脱敏，并附 `content_is_untrusted_data=true`；不存在报告为 404，`POST /api/ai-history/reports` 为 405。
- 修改前备份：`/Users/simon/备份/codex/20260812-023546-one-trading-hermes-analysis-history-read`，包含本轮会触碰的六个既有文件和 README；回滚时恢复这些文件并移除本轮新增 `ai_history.py / analysis_history.py / test_analysis_history.py`，不覆盖工作树其他未提交成果。

#### 自动检查与真实目标运行面

- 聚焦历史/租户/MCP 测试：`19 passed`；Hermes、身份、管理员、工作区相关回归：`50 passed, 1 skipped`；完整后端：`395 passed, 2 skipped`。跳过项和 20 条 warning 均为既有集成标记、Polars/时间 API 提醒，与本轮历史权限无关。
- 本轮 Python 文件 ruff check、`main.py` 新增 import 的 `F401/F811` 检查、`py_compile` 与 `git diff --check` 通过；未改动 `main.py` 备份前已有的 lint 告警。
- 正在运行的 `127.0.0.1:3018` 已热加载新路由：真实 owner 目录返回 20 条已保存报告（个股 14、财务 2、复盘 4），目录不含正文；按 ID 读取第一条正文为 3194 字符；不存在报告 404，写入方法 405。
- 临时隔离后端 + 受管 `ot-owner` Profile 通过真实 stdio MCP 协议发现原两个工具及两个新增历史视图；`analysis_history` 返回 1 条轻量样本，`analysis_history_report` 读取 19 字符样本正文，scope 为 `current_account`。临时进程已退出，临时目录按全局删除规则移入废纸篓。
- Codex 内置浏览器 `http://127.0.0.1:3011/ai` 显示 20 条历史及 14 / 2 / 4 分类计数，20 个历史链接均可见，控制台 error 为 0。页面继续明确行业分析使用本地数据计算，不伪装成 AI 报告历史。

#### 当前状态与发布边界

- 当前状态：本地主开发树的历史 Interface、Profile-scoped Hermes 桥接、跨账户拒绝和用户台回归为 `verified`。
- 当前 `3011/3018` 开发实例仍保持 `ONE_TRADING_HERMES_MULTIUSER_ENABLED=false`，所以本轮没有把本机旧单 Profile 伪装成用户版运行时；公网当前版本也未部署本轮代码。正式启用仍需在目标多用户 Hermes Runtime 完成构建、双账户重启持久性和部署后真实对话验收，之后才能进入 `approved / production`。

### 3.10 本地主开发实例多用户 Hermes Runtime 恢复

#### 用户目标、权限与外部副作用

- 用户目标：修复 `http://127.0.0.1:3011/ai/hermes` 重复显示“多用户 Hermes Agent 尚未启用”，在本地主开发实例启用当前账户独立 Profile，并让该 Agent 真正读取 3.9 已开放的当前账户分析历史。
- 本轮授权只覆盖本地代码、配置、运行进程、受管 Profile 和真实模型验收；没有部署或修改公网服务，没有变更旧个人 Hermes `127.0.0.1:8650`，没有开放写报告、账户、交易、终端、文件、浏览器、消息或外发权限。
- 真实验收调用一次现有 Grok 订阅并生成一条隔离验收 Session；该 Session 和首次失败样本都已从当前活动 Runtime 分离到备份，不作为用户正式对话继续展示。

#### 根因与修复边界

- 页面错误不是分析历史 Interface 缺失：本地 `.env` 仍关闭多用户开关，`dev.sh` 只启动 `3018/3011`，而后端配置期待 multiplex gateway；当状态请求失败后，页面又并发请求 Session/历史，React StrictMode 使通用错误 Toast 重复出现。
- 本地身份库尚无用户密码，HTTP 中间件使用兼容的虚拟 `owner`。原 `hermes_profiles` 外键流程只能接收真实 `users` 行，导致本地 owner Profile 无法预置。修复只在身份库为空且主体严格为 loopback legacy owner 时返回虚拟映射；没有自动创建用户、密码或登录会话。
- Hermes 0.20 会在 multiplex Profile 惰性创建前完成一次进程级 MCP 发现，首轮 Agent 因而看不到刚生成的 Profile 数据工具。项目入口 `backend/scripts/hermes_one_trading_runtime.py` 在创建 Agent 前按当前 Profile 重新发现 MCP；每个账户使用由 Profile 派生的唯一内部 MCP 名，避免进程级工具注册表发生租户凭据串用。

#### Interface、Module、Seam 与权限

- `.env` / `.env.example`、`backend/app/config.py` 和 `dev.sh` 将本地主运行面固定为项目受管 `data/hermes`、multiplex `127.0.0.1:8651`、Profile `ot-owner`；`dev.sh` 先等 gateway 健康再启动后端与前端，并监督三者，任一退出就停止其余运行面。原个人 gateway `8650` 保持独立监听。
- `backend/scripts/start_local_hermes_gateway.py` 复用已安装的本机 Hermes Runtime，不修改上游 checkout；`backend/app/services/hermes_runtime.py` 和 `start_one_trading_server.py` 支持项目入口，`Dockerfile.one-trading` 只打包该入口，未执行发布构建或部署。
- `backend/app/services/hermes_tenant.py` 为每个 Profile 生成唯一 MCP server 名，同时显式关闭 MCP `resources/prompts` 辅助工具；平台只给当前 Profile 的 API Server 开启 `memory / session_search / 该 Profile 数据 MCP`。用户界面仍只显示稳定名称 `one-trading-data`，不暴露内部哈希或凭据。
- `frontend/src/pages/HermesAgentChat.tsx` 改为先检查连接，只有 connected 才加载 Session/历史；启动流程对 StrictMode 幂等。离线时保留本地 Session 指针，避免一个连接问题引发多次 503 与重复红条。

#### 备份、失败和回滚

- 修改前与验收证据备份：`/Users/simon/备份/codex/20260812-143750-one-trading-hermes-local-multiuser-fix`。README 记录原始文件、SQLite 一致性备份、旧凭据存储、首次失败 Runtime 和成功验收 Runtime；私有目录限制为当前用户读取。
- 回滚时先停止本轮 `dev.sh` 管理的 `8651/3018/3011`，恢复备份中的项目文件与 `.env`；由于本轮前 `data/hermes` 不存在，可将当前新增 Runtime 整体移走。不要删除或替换旧个人 `~/.hermes/profiles/one-trading`、其 Session/记忆或 `8650` 服务。
- 当前活动 `data/hermes` 是成功验收后重新创建的干净 Runtime；浏览器验证前 Session 列表为空。测试用 Session/记忆只保存在备份证据目录。

#### 自动检查与真实目标运行面

- 后端目标回归覆盖身份、租户、Runtime 打包、真实 Hermes multiplex、Agent/模型桥接、历史和数据权限，共 `49 passed`；目标 ruff、Python compile、Bash syntax 和 `git diff --check` 通过。真实双账户 Runtime 测试证明两账户的 `tool_search` 只见各自哈希前缀数据工具，且不发现 resource/prompt 辅助工具。
- 前端 `HermesAgentChat.test.tsx` 共 `6 passed`，覆盖离线启动不请求 Session/历史、不清除本地 Session 指针和连接后正常加载；TypeScript 与 Vite 生产构建通过。构建只保留项目既有 `api.ts` 混合动静态导入和大 chunk 提醒，没有本轮新增错误。
- 真实 owner Agent Session 按 `tool_search -> tool_describe -> one_trading_data_query` 调用链读取 `analysis_history`，返回 20 条，其中个股 14、财务 2、大盘复盘 4；runtime 锁定 `grok-4.5`。验收 Session 已移入上述备份，当前活动 Runtime 未保留该测试对话。
- Codex 内置浏览器刷新后分时检查到红色禁用提示、alert 和 Toast 均为 0；Agent 设置显示 `Profile 已连接 / ot-owner / grok-4.5 / Holographic / 70 个只读视图`，输入框可用。浏览器控制台 error 为 0，只保留项目既有 React Router v7 future flag warning；页面保留为本轮交付运行面。
- 当前 Runtime 的 `errors.log` 只有 Hermes 通用安全审计提示：本机 sshd 未显式关闭密码认证，以及未配置消息平台 allowlist；本 Profile 没有启用消息平台或 SSH 工具，二者没有阻断本轮 loopback 只读链。后端仍有项目既有 `preferences.json malformed` 与两个尚无 Parquet 的 ETF 视图 warning，均不在本轮 Hermes 调用链。

#### 当前状态与发布边界

- 当前状态：本地主开发实例为 `verified`；用户尚未完成实际对话验收，因此不标记 `approved / production`。
- 本轮没有部署。公网当前版本仍需单独确认目标 release、Secret/PVC、双账户隔离、重启持久性、配额与失败恢复后，才能另行进入部署与生产验收。

### 3.11 多用户 Hermes 最新版 Zeabur 发布

#### 用户目标、权限与外部副作用

- 用户明确要求上线时保留多用户隔离，并确保每个用户（每个 agent）都有自己的 Hermes Agent 体系。本轮部署到既有 Zeabur service，没有复制本地身份库、Profile、Session、记忆或模型凭据。
- 所有账户继续共享部署拥有的 Grok 订阅和只读市场数据，但每账户稳定映射一个 `ot-<user>` Profile；工作区、Session、Holographic memory、内部 API/model/data key、MCP connection 与任务所有权按 Profile 隔离。
- Agent 工具仍是分析只读边界：当前 Profile 数据 MCP 为 `one-trading-data`，70 个只读视图，BFL 显式禁用；不开放下单、账户修改、任意文件/终端、外发消息或部署工具。

#### 部署、隔离与重启证据

- 当前 Deployment `6a7c57c70d41a78958bb46a2`，build `local-sync-20260812-5379302b4970d31a`；镜像包含固定 Hermes upstream commit 与项目入口 `hermes_one_trading_runtime.py`，运行时为 multiplex gateway。
- 部署前后线上身份库均为 `integrity_check=ok / users=1 / sessions=7 / admins=1 / hermes_profiles=1`；市场数据 overlay、lineage 补齐、Catalog 重扫和 service 重启都没有改变这些值。
- 临时双账户 production-image canary 全部位于容器 `/tmp`，证明两个账户得到不同 workspace/Profile、不同 internal API/bridge/data key 和不同 MCP connection，2/2 跨 Profile key 均被拒绝；fresh process 后仍稳定。canary 完成后清理，生产身份库仍只有原 owner。
- 真实 owner 在新 Pod 重启后通过 `/api/hermes-agent/status` 返回 200：`connected=true / profile=ot-owner / isolation=dedicated_profile / memory_enabled=true / data_tool_enabled=true / data_view_count=70 / enabled_mcp_servers=[one-trading-data]`。
- Profile 错误 key 返回 401、未知 Profile 返回 404；未登录业务数据接口返回 401，普通用户管理员/数据控制边界由自动测试和前述隔离 canary 保持 403。

#### 自动检查、目标运行面与当前状态

- release 后端全量 `406 passed / 2 skipped`，覆盖 Hermes Agent、multiplex Runtime、Profile isolation、model/data bridges、认证角色和用户工作区；Docker 候选与线上重启持久性均通过。
- Codex 内置浏览器 `/ai/hermes` 显示历史对话 1 条、输入框可用，并明确 Session、长期记忆、内部凭据和可见数据按账户隔离；浏览器控制台 error 为 0。
- 最新 runtime 日志没有匹配到 traceback、exception、panic、segfault、Catalog/Hermes failure；service restart 为正常 SIGTERM shutdown 后新 Pod 接管。
- 当前状态：线上多用户 Hermes Runtime 和现有 owner Profile 为 `production`；用户尚未用新注册的普通账户完成真实模型对话验收，因此不把普通用户产品体验提升为 `approved`。新用户首次使用时仍需按正常惰性 provisioning 创建自己的 Profile。
- 回滚应用可恢复前一 Deployment；Profile/PVC 回滚或清理是独立高风险动作，必须使用 `/Users/simon/备份/codex/20260812-164436-one-trading-zeabur-latest-sync/online-pvc/pre-sync-complete-pvc.tar.zst` 并另行授权，不能因应用回滚覆盖现有账户对话或记忆。

## 4. 后续条目模板

```md
### capability_name

#### 用户目标、权限与外部副作用
#### GitHub 情报与固定上游点
#### Interface、Module、Seam 与 Adapter
#### 数据台和用户台依赖
#### 审计、确认、失败和回滚语义
#### 自动检查与真实目标运行面
#### 当前状态与用户批准
#### 阻塞和下一步
```
