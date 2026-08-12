# one-trading 用户台开发日志

最近维护：2026-08-12（最新版 Zeabur 用户台上线验收）

适用项目：`/Users/simon/Trading/one-trading`

职责：只记录用户直接看到的页面、交互、图表、设置入口和产品工作流在 one-trading 中的本地设计、实现、验证、验收与运行状态。

## 0. 权威边界

- GitHub 上游项目与采用判断：`/Users/simon/Trading/用户台GitHub项目借鉴记录.md`。
- 产品/界面能力反查：`/Users/simon/Trading/用户台产品与界面能力目录.md`。
- 未来工程优先级与开工门：`/Users/simon/Trading/用户台下一步工程工作计划.md`。
- 数据台本地实现：`/Users/simon/Trading/one-trading/docs/data-platform-development-log.md`。
- Agent 台本地实现：`/Users/simon/Trading/one-trading/docs/agent-platform-development-log.md`。
- 本文件不复制上游完整源码调查，也不把数据集或 Agent 工具状态写成用户台完成状态。

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

| 能力 | 上游情报 | 本地位置 | 本轮结论 |
| --- | --- | --- | --- |
| Tick4Panel 产品壳和主要页面 | tickflow-stock-panel | `frontend/` | 已有代码基座；本轮未重新验证 |
| 策略与回测用户流 | tickflow-stock-panel、portwine 仅作 Agent 机制参考 | `frontend/src/pages/backtest` 等 | 已有本地页面；本轮未重新验证 |
| AI 设置入口 | go-stock、tickflow-stock-panel | `frontend/src/pages/settings/AI.tsx` 等 | 入口雏形；Agent 能力另记 |
| AI 功能目录 | tickflow-stock-panel + one-trading 本地代码盘点 | `/ai`、`frontend/src/pages/AIHub.tsx` | 四项真实 AI 能力已聚合；本轮只验证目录和跳转，不重新验收模型输出 |
| 数据目录页面 | one-trading 自有实现 | `frontend/src/pages/Data.tsx` 等 | 当前工作树另有用户未提交改动；本轮不改、不验收 |
| 市场脉搏 | go-stock 产品形态与财联社端点情报；运行时为 one-trading 自有实现 | 看板 `#market-pulse`、数据页、概念/行业/复盘深链 | P0/P1/P2 已完成真实桌面与 375px 验证；状态见 `market_pulse_workbench` |

## 4. 功能条目

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
