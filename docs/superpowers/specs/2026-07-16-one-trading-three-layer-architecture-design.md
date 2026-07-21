# one-trading 三层正式架构设计

> 状态：设计稿，待项目负责人核查
> 日期：2026-07-16
> 适用工作区：/Users/simon/Trading
> 主项目：/Users/simon/Trading/one-trading

## 0. 文档目的

本文把 one-trading 的正式目标固化为三层架构，并说明它如何落到当前工作区的代码边界中：

1. **工作台层（Workbench）**：面向用户的行情、分析、选股、回测、监控和交易工作流。
2. **数据平台层（Owned Data Platform）**：one-trading 自己拥有的 Provider、规范化 schema、存储、质量、血缘、调度和路由能力。
3. **AI Agent 层（Future Agent Control Plane）**：未来的规划、工具调用、研究编排和受控动作层。

本文是设计和实施边界，不是代码实施记录。本轮只新增本文档，不修改业务代码、配置、依赖或真实数据。

## 1. 正式目标与决策

### 1.1 正式目标

one-trading 最终不是 TickFlow 的前端，也不是任何 GitHub 项目的二次发行版，而是一个由 one-trading 自己定义接口、schema、存储和运行时的数据平台，并在其上提供工作台和 AI Agent。

最终状态应满足：

- TickFlow 只作为迁移期间的临时基线，**最终从生产数据路径完全停用**。
- 参考过的 GitHub 项目只贡献数据来源情报和设计经验，不作为 one-trading 的运行时依赖。
- 每个目标数据能力都有 one-trading 自己的 adapter、canonical schema、质量/血缘记录和可观测状态。
- 工作台和 Agent 只依赖 one-trading 的稳定 API/工具契约，不直接请求东财、Sina、Tencent、TDX、RSS 或其他原始端点。
- 现有 data/**/*.parquet、DuckDB 视图、Polars 热缓存和主要业务 API 在迁移过程中保持兼容，避免因为更换底层来源而重写上层产品。

### 1.2 “全部接入”的定义

本项目的完整性按**数据能力和字段覆盖**定义，而不是按“把每个 GitHub 仓库的每一个接口都搬进来”定义。

最终需要完成的是：

- 建立一份 source matrix，逐项登记参考项目中的来源、端点、字段、时间粒度、复权方式、认证、限流和失败特征。
- 对 one-trading 需要的每项能力，至少有一个自有主 adapter；高价值或高可用性能力再配置自有备用 adapter。
- 对不纳入当前产品范围的能力明确标记为 optional、experimental 或 unsupported，不让“全部”变成不可收敛的范围。

因此，“全部 GitHub 数据源接入”在本设计中具体解释为：**所有纳入 one-trading 目标能力矩阵的数据来源，都由 one-trading 自己实现接口并接入自己的数据平台；不是 vendoring 上游整套系统。**

## 2. 当前基线（用于迁移，不代表最终架构）

### 2.1 工作区项目角色

| 项目 | 正式角色 | 处理方式 |
| --- | --- | --- |
| one-trading | 主项目、最终交付面 | 所有产品、数据平台和未来 Agent 的实际实现落在这里 |
| go-stock | 数据来源地图和产品能力参考 | 参考 Sina/Tencent/EastMoney/TDX/Tushare 的功能分布，不直接并入主工作流 |
| perilla-leaf-chokepoint-skills | 研究工作台和数据质量设计参考 | 参考 source result、证据、质量和血缘思想，不作为行情主源 |
| GitHub项目借鉴记录.md | 上游情报台账 | 记录项目 URL、借鉴内容、排除理由和落地位置 |

### 2.2 one-trading 当前运行面

- 前端已经具备看板、自选、策略、回测、个股分析、概念/行业、财务、监控、复盘、指数、交易和数据等工作台路由。
- 后端由 backend/app/main.py 统一启动 API、数据仓库、行情服务、深度服务、定时任务和扩展数据拉取任务。
- backend/app/data_providers/ 已有 Provider 协议、schema/normalizer 和 registry，但主分支目前只注册 TickFlow。
- backend/app/tickflow/ 仍承担客户端、能力检测、策略、仓库和调度等 TickFlow 相关职责。
- data/ 已承载日 K、分钟 K、复权因子、财务、标的、深度、扩展数据、回测结果、AI 缓存和用户数据等持久化内容。
- 当前 AI 是 OpenAI 兼容接口/Codex CLI 适配器、AI 策略生成和报告类能力，尚未形成可自主规划、调用工具、审批和审计的 Agent runtime。

### 2.3 已有基础与未完成项

隔离工作树 one-trading/.worktrees/owned-market-data-core 中已有存储核心和 ProviderRuntime 基础设计/实现痕迹，包含 canonical models、ProviderRuntime、分区写入、恢复和 lineage 模块；它尚未合并到当前 main。

当前不能据此宣称以下事项已经完成：

- 外部 GitHub 参考来源已经全部转化为 one-trading 自有 adapter；
- TickFlow 已从生产路径移除；
- 所有数据能力已经具备主备路由、健康状态和质量闭环；
- AI Agent runtime 已经开发。

## 3. 总体架构图

~~~mermaid
flowchart TB
    U[用户] --> W[工作台层<br/>Workbench]
    W -->|REST / SSE / Domain API| APP[应用服务与 API Facade]
    AG[未来 AI Agent<br/>规划·工具·记忆·审批·审计] -->|受控 Tool Contract| APP

    subgraph D[one-trading 数据平台层]
        APP --> R[ProviderRuntime<br/>能力·注册·解析·健康·路由]
        R --> A1[自有市场数据 adapters<br/>行情·K线·财务·资金流·筹码·人气]
        R --> A2[自有备用 adapters<br/>TDX·Sina·Tencent·EastMoney 等]
        R --> A3[扩展输入 adapters<br/>HTTP·CSV/Excel·JSON·THS 种子]
        R -.迁移期临时基线.-> TF[TickFlow adapter]
        A1 --> N[Canonical Schema 与规范化]
        A2 --> N
        A3 --> N
        TF --> N
        N --> Q[质量、血缘、时间/复权语义]
        Q --> S[原始快照与提交式存储<br/>Parquet · DuckDB · Polars 缓存]
        S --> APP
    end

    APP --> P[产品动作服务<br/>筛选·回测·监控·报告·交易确认]
    AG -.禁止直接访问.-> R
    AG -.禁止直接写入.-> S
~~~

### 3.1 关键方向

数据只向上流动：raw source -> adapter -> canonical dataset -> application API -> workbench/Agent。

Agent 可以调用应用服务暴露的工具，但不能绕过应用服务直接访问 provider、原始 HTTP、Parquet 或 DuckDB 文件。工作台同样不能把 provider 选择、失败重试和原始字段映射散落到页面代码中。

## 4. 三层职责与边界

### 4.1 第一层：工作台层（Workbench）

**职责**

- 提供用户可见的导航、页面、表格、图表、筛选器和操作反馈。
- 组合筛选、分析、回测、监控、复盘、报告、交易确认等产品工作流。
- 通过稳定的 domain API 读取数据和提交动作，不感知底层 provider 的 URL、限流、字段别名和 fallback 顺序。
- 展示数据的 as_of、质量状态、来源摘要和缺失告警，但不自行计算来源可信度。

**当前代码落点**

- 页面入口和路由：frontend/src/router.tsx。
- 全局布局和产品导航：frontend/src/components/Layout.tsx。
- 主要页面：frontend/src/pages/ 下的 dashboard、analysis、screener、backtest、monitor、review、data 等页面。
- 后端 API：backend/app/api/ 下的行情、筛选、策略、回测、监控、数据和报告路由。
- 应用启动编排：backend/app/main.py（当前仍把工作台和数据生命周期放在一个进程中）。

**边界约束**

- 页面和业务服务不得直接 requests/SDK 调用原始数据源。
- 页面不得直接写 data/**/*.parquet、lineage 或 provider health 文件。
- 页面不负责决定“哪个源优先”；只消费 API 返回的能力和质量结果。

### 4.2 第二层：数据平台层（Owned Data Platform）

**职责**

1. **Provider adapter**：把具体来源包装成 one-trading 自己的接口；来源可以来自开源项目情报中的 EastMoney、Sina、Tencent、TDX、Tushare、RSS、Yahoo/SEC 等，但实现属于 one-trading。
2. **ProviderRuntime**：维护 registry、CapabilitySet、operation 解析、主备路由、cooldown、熔断、stale cache、限流和健康状态。
3. **Canonical schema**：为 instruments、daily/minute/realtime、adj factor、financial、fund flow、chips、popularity、news/research 等数据定义稳定的字段、时间和复权语义。
4. **质量与血缘**：记录 provider、请求、抓取时间、有效时间、字段覆盖、缺失/延迟/冲突、质量分和 lineage id。
5. **存储与恢复**：通过提交式/原子分区写入保护 Parquet；以 DuckDB 提供冷查询，以 Polars 提供热缓存；保留必要 raw snapshot 便于复核和重放。
6. **调度与回填**：按数据集和 operation 调度实时刷新、日终落盘、历史回填和失败重试，局部失败不阻塞整页。
7. **平台 API**：向应用层提供稳定的 domain API、能力矩阵、健康摘要、数据新鲜度和来源/质量查询。

**当前代码落点与目标落点**

| 能力 | 当前代码/状态 | 目标归属 |
| --- | --- | --- |
| Provider 协议与归一 | backend/app/data_providers/base.py、normalizer.py、schemas.py；已有雏形 | backend/app/data_providers/，补齐 operation contract 和自有 adapters |
| Provider registry | backend/app/data_providers/registry.py；目前只注册 TickFlow | ProviderRuntime 统一注册、解析、健康和路由 |
| TickFlow 适配 | backend/app/data_providers/tickflow_provider.py、backend/app/tickflow/ | 仅作为迁移期 adapter，最终移除生产依赖 |
| 存储入口 | backend/app/tickflow/repository.py 中的 DataStore/KlineRepository | 独立 storage 模块，保持现有 Parquet/DuckDB/Polars 读接口兼容 |
| 提交/恢复/血缘基础 | 隔离工作树的 backend/app/storage/ 和 ProviderRuntime 文件 | 评审后分阶段合并到主项目，不与业务页面同时大改 |
| 扩展数据 | data/ext_data/、HTTP pull、CSV/Excel、JSON ingest | 独立扩展 adapter，和核心行情 schema 通过显式 JOIN 关联 |
| 能力 API | backend/app/api/routes.py 的 /health、/api/capabilities 仍直接依赖 TickFlow | 改为读取 ProviderRuntime snapshot 和数据质量摘要 |

**平台层不负责**

- 页面布局和交互细节；
- LLM prompt、Agent 规划和自然语言记忆；
- 未经定义的任意上游字段透传；
- 把某一个 GitHub 项目当作不可替换的核心依赖。

### 4.3 第三层：未来 AI Agent 层（Control Plane）

**职责**

- 接收自然语言目标，拆解为可审计的研究、查询、筛选、回测或报告步骤。
- 通过工具注册表调用 one-trading 应用服务和数据平台 API。
- 管理短期会话、研究上下文、任务状态、结果引用和可选的长期记忆。
- 对写操作、交易动作、策略发布和批量任务执行显式审批、权限检查和审计。
- 在数据不足、来源冲突或质量降级时，把不确定性传回用户，而不是静默补值。

**当前代码落点**

- LLM/CLI 适配：backend/app/services/ai_provider.py。
- AI 策略生成：backend/app/strategy/ai_generator.py 和 backend/app/api/strategy.py 的 /ai/* 路由。
- 现状属于“AI capability”，不是完整 Agent。未来可新增 backend/app/agent/，但应先定义工具契约，再实现 planner/runner/memory。

**首批只读工具契约（目标）**

| 工具 | 作用 | 允许的副作用 |
| --- | --- | --- |
| market.snapshot | 获取指定标的/市场的最新快照 | 无 |
| market.history | 查询日 K、分钟 K、复权因子 | 无 |
| market.fund_flow | 查询资金流 | 无 |
| market.chips | 查询筹码分布/筹码峰 | 无 |
| market.popularity | 查询人气/热度字段 | 无 |
| market.news | 查询已归一化资讯和来源 | 无 |
| research.query | 查询扩展数据和证据 | 无 |
| strategy.backtest | 在受控数据快照上运行回测 | 只写隔离回测结果 |

每个工具返回统一包络：data、schema_version、as_of、fetched_at、quality、source_summary、lineage_id、warnings 和 request_id。

**Agent 层禁止事项**

- 不直接调用 provider URL、API key 或第三方 SDK。
- 不直接改写核心 Parquet、lineage、provider health 或能力配置。
- 不把模型生成的代码直接加载为生产策略；必须经过 AST/权限/沙箱和用户确认。
- 不把“模型认为正确”当作数据质量结论。

## 5. 数据流、质量和血缘

~~~mermaid
sequenceDiagram
    participant C as 应用/API
    participant R as ProviderRuntime
    participant P as Owned Adapter
    participant N as Normalizer/Validator
    participant W as Staged Writer
    participant L as Lineage Ledger
    participant S as Canonical Storage

    C->>R: DatasetOperation + targets + time range
    R->>R: capability/health/cooldown/route resolution
    R->>P: ProviderRequest(request_id)
    P-->>R: raw payload + transport status
    R->>N: normalize + schema validation
    N-->>R: ProviderResult(status, frame, warnings)
    R->>W: stage partition + checksum
    W->>W: lock / validate / atomic commit
    W->>L: committed event + source + timestamps
    W->>S: Parquet partition
    S-->>C: data + quality + lineage + freshness
~~~

### 5.1 数据状态

每次 provider 请求都应能区分：ok、partial、failed、timeout、skipped、missing。失败一个 provider 或一个分区时，返回局部结果和告警，不把整张工作台页面变成无来源的空白数据。

### 5.2 必须记录的来源信息

- provider：one-trading adapter 名称，而不是任意 UI 标签；
- source_endpoint：必要时记录脱敏后的端点标识；
- request_id、run_id、lineage_id；
- fetched_at、数据的 as_of/交易时间、时区和复权模式；
- schema 版本、字段覆盖、缺失字段、冲突和质量评分；
- fallback 原因、cooldown/熔断状态和最终选中的 provider。

## 6. Canonical 数据能力矩阵

以下是平台应按 operation 管理的能力，不要求所有 provider 支持所有能力：

| 数据集 | 典型用途 | 第一阶段优先级 | 目标主/备来源策略 |
| --- | --- | --- | --- |
| instruments | 标的、交易所、资产类型 | P0 | 自有静态/交易所适配，必要时远端补齐 |
| daily_kline | 看板、指标、回测 | P0 | 自有历史日 K adapter；独立备用来源 |
| adj_factor | 前复权/后复权 | P0 | 与 K 线同源或可验证的独立 adapter |
| minute_kline/realtime | 盘中、监控 | P1 | 自有实时/分钟 adapter；按 operation 健康路由 |
| financials | 财务分析、筛选 | P1 | 自有财务 adapter，记录报告期和公告日 |
| fund_flow | 资金流 | P1 | 参考 a-stock-data/myhhub/stock 字段情报实现独立 adapter |
| chips/popularity | 筹码峰、人气 | P1 | 独立 adapter 或 ext_data，不污染核心 K 线 schema |
| concepts/industries | 概念/行业分析 | P1 | THS 种子 + 自有更新 adapter，记录版本和时间 |
| news/research | 复盘、研究报告 | P2 | RSS/资讯 adapter，统一来源和发布日期 |
| global/SEC/options | 外盘和扩展研究 | P2 | Yahoo/SEC 等独立 optional provider |

核心判断：优先完成能支撑现有工作台的 P0/P1，再扩展 P2；不为“看起来全”而把所有外盘和资讯接口提前塞进核心路径。

## 7. 上游 GitHub 项目的正确使用方式

上游仓库作为 source intelligence，转换成以下 one-trading 资产：

| 参考项目/类型 | 借鉴内容 | one-trading 的落地形式 |
| --- | --- | --- |
| go-stock | 功能驱动的数据源地图、K 线 fallback、东财/新浪/腾讯/TDX/Tushare 分布 | source matrix、operation 列表和 adapter 优先级 |
| a-stock-data、myhhub/stock | 资金流、筹码、人气等字段线索 | 自有 schema、字段映射、质量规则和独立 adapter |
| finshare、adata | stale cache、cooldown、同语义 fallback | one-trading 自己的 Router/Health/Circuit Breaker |
| easy_tdx | host 池、ping、最佳 host 持久化 | one-trading TDX host health 模块 |
| global-stock-data | Yahoo/SEC/期权数据边界 | optional global provider |
| investment-news、Vibe-Research | RSS 目录和研究编排方式 | news/research adapters 与 Agent 工具输入 |
| tickflow-stock-panel | 当前工作台的自定义数据源方向 | 只保留可兼容的产品和插件需求，不锁定 TickFlow |

禁止事项：复制上游仓库的统一网关、存储、页面或 Agent 系统；将上游依赖写进 one-trading 的生产依赖；未经 schema/质量/授权审核直接透传字段。

## 8. 代码落地蓝图（本轮只规划，不修改）

### 8.1 目标目录边界

~~~text
one-trading/
├── frontend/                         # Layer 1: 工作台 UI
├── backend/app/
│   ├── api/                          # 对外 domain API / SSE
│   ├── application/                 # Layer 1 与 Layer 2 的用例编排
│   ├── data_providers/              # Layer 2: contracts、adapters、runtime
│   ├── storage/                     # Layer 2: staged write、recovery、lineage
│   ├── jobs/                        # Layer 2: refresh、backfill、quality jobs
│   ├── strategy/                    # 工作台策略能力与受控执行
│   ├── services/ai_provider.py      # 现有 AI 模型适配，暂不等同 Agent
│   └── agent/                       # Layer 3: future tool/planner/memory/audit
├── data/
│   ├── raw/                         # 可复核的原始快照（目标）
│   ├── canonical/                   # 规范化 Parquet 数据集（目标/兼容迁移）
│   ├── ext_data/                    # 外部扩展 JOIN 数据
│   └── lineage/                     # 提交事件、质量和来源记录
└── docs/superpowers/specs/           # 设计与实施文档
~~~

这是逻辑边界，不要求一次性拆成多个仓库或多个进程。优先在现有 monorepo 内建立稳定接口，再根据负载和权限需求决定是否把 Agent 单独部署。

### 8.2 现有文件到三层的映射

| 现有文件/目录 | 归属 | 需要做的方向 |
| --- | --- | --- |
| frontend/src/router.tsx、frontend/src/components/Layout.tsx、frontend/src/pages/ | 工作台层 | 保持页面路由稳定，逐步把来源/质量展示接到 domain API |
| backend/app/api/ | 工作台 API facade | 去除路由对 TickFlow client/policy 的直接依赖，改读 runtime snapshot |
| backend/app/main.py | 进程组合根 | 保留单进程启动，改为组装 data platform/application/agent 边界 |
| backend/app/data_providers/base.py、schemas.py、normalizer.py | 数据平台 | 扩展为 operation contract 和 canonical dataset contract |
| backend/app/data_providers/registry.py、tickflow_provider.py | 数据平台 | 迁移为 ProviderRuntime + 自有 adapters；TickFlow 只保留过渡期 |
| backend/app/tickflow/ | 迁移兼容层 | 逐项抽离 repository/capability/scheduler，最后删除生产引用 |
| backend/app/tickflow/repository.py | 数据平台存储 | 迁移到独立 storage facade，同时保持旧读接口和 Parquet 布局兼容 |
| backend/app/services/ai_provider.py、backend/app/strategy/ai_generator.py | AI 能力基础 | 保留为模型/策略能力；在其上增加工具权限和 Agent runtime，不直接越过 API |
| data/ext_data/ 与上传/HTTP/JSON ingest | 数据平台扩展输入 | 保持独立命名空间、source/as_of/lineage，按 schema 显式 JOIN |
| GitHub项目借鉴记录.md | 架构治理 | 每新增 adapter 都记录来源 URL、借鉴字段和落地文件 |

## 9. 运行拓扑与权限边界

### 9.1 迁移期

~~~text
浏览器
  -> FastAPI / backend
      -> 应用服务
          -> ProviderRuntime
              -> 自有 adapter（逐项上线）
              -> TickFlow adapter（暂时兜底）
          -> DataStore / Parquet / DuckDB / Polars
      -> 现有工作台功能
~~~

迁移期允许 TickFlow 作为显式、可观测的 fallback，但所有请求都必须经过 ProviderRuntime；页面和 Agent 不得自行绕过 runtime。

### 9.2 最终态

~~~text
浏览器 / Agent
  -> Domain API / Tool Gateway
      -> Owned Data Platform
          -> one-trading 自有 adapters + router + quality + lineage
          -> one-trading canonical storage
      -> 产品动作服务（回测、报告、监控、交易确认）
~~~

最终验收时应能在生产路径中搜索不到 TickFlow client、TickFlow capability policy、TickFlow endpoint 和 TickFlow-only environment dependency；迁移脚本和历史文档可以保留，但不能被运行时加载。

### 9.3 权限原则

| 主体 | 可读 | 可写 |
| --- | --- | --- |
| 工作台用户/API | domain dataset、质量、血缘摘要 | 用户自选、策略草稿、回测结果、经确认的产品动作 |
| Provider adapter | 自己的 transport credential、raw response | staged/raw ledger；不能直接覆盖 canonical 分区 |
| Data platform jobs | canonical dataset、lineage、health | 原子提交 canonical 数据和质量事件 |
| Agent | 通过 tool gateway 读取允许的数据 | 默认无写权限；写操作必须逐项审批和审计 |
| 管理员/运维 | 全部健康、运行和审计信息 | provider 配置、路由和任务开关，需保留变更记录 |

## 10. 分阶段实施计划

每一阶段都以一个可验证的 operation 或边界为单位，避免一次性重写整个数据系统。

### Phase 0：设计和 source matrix（当前阶段）

- 核对工作区项目角色、目标能力和上游情报边界。
- 建立 source matrix：来源、字段、时间、复权、认证、限流、失败特征、许可和优先级。
- 评审本文档；未获确认前不开始业务代码重构。

### Phase 1：存储核心与 ProviderRuntime 接入

- 评审隔离工作树中的 storage/、canonical models、提交/恢复和 lineage 基础。
- 先接入现有 TickFlow adapter，保证旧 API、Parquet、DuckDB 和 Polars 热缓存可读。
- 把 /health、/api/capabilities 改为读取 runtime snapshot，不再由路由直接探测 TickFlow。
- 这一阶段不宣称已经替换 TickFlow；它只是把替换所需的运行时边界搭好。

### Phase 2：自有 adapters 和能力覆盖

按风险和现有工作台依赖逐项推进：

1. instruments、daily K、adj factor；
2. minute/realtime；
3. financials；
4. fund flow、chips、popularity；
5. concepts/industries、news/research；
6. global/SEC/options 等 optional 能力。

每个 adapter 必须通过同一份 contract test、schema validation、质量规则、lineage 写入和失败状态检查，才能进入 shadow 或主路由。

### Phase 3：自有路由、健康和切换

- 为每个 operation 配置主/备 provider、cooldown、熔断、stale cache 和恢复策略。
- 先 shadow/双读比较，再按数据集和 operation 灰度切换。
- 验证数值、字段覆盖、时间/复权语义、延迟、缺失和失败恢复。
- 只有当 P0/P1 目标能力达到验收标准，且工作台主路径稳定后，才移除 TickFlow 生产依赖。

### Phase 4：工作台边界稳定化

- 把来源、质量、as-of、血缘摘要以统一方式呈现在数据页、分析页和报告中。
- 让回测、筛选、监控和复盘统一从 canonical dataset/API 取数。
- 保持页面 URL 和用户工作流兼容，减少因换源引起的产品层改动。

### Phase 5：Agent 契约和只读 Agent

- 先实现 tool registry、输入/输出 schema、权限、超时、取消、引用和审计。
- 首批只开放查询、比较、筛选、回测和报告编排；不开放直接交易或直接写核心数据。
- 在真实工作台 API 上验证一次完整的“提问 -> 工具调用 -> 带来源回答”主路径。

### Phase 6：受控动作和长期记忆（未来）

- 增加策略草稿、监控规则、报告归档等可审批写工具。
- 交易动作必须有用户确认、幂等键、风控检查和审计回放。
- 只有当只读 Agent 稳定后，再评估长期记忆、自动任务和跨日研究计划。

## 11. 验收标准

### 数据平台

- 目标能力矩阵中每个 P0/P1 operation 都有 one-trading 自有主 adapter；高价值能力有明确备用或明确 unsupported 理由。
- 所有 adapter 返回 canonical schema，能记录 provider、as_of、fetched_at、quality、lineage_id 和 warnings。
- 写入具备 staged/validate/commit/recovery；不会因单个 provider 失败而覆盖有效历史分区。
- 健康、cooldown、fallback、stale cache 和局部失败能在 API/日志中观察。
- 现有 Parquet/DuckDB/Polars 读路径和主要工作台流程通过兼容性验证。
- 最终生产运行路径完全不依赖 TickFlow。

### 工作台

- 现有看板、选股、分析、回测、监控、复盘和数据页仍能通过稳定 domain API 工作。
- 页面显示数据新鲜度、质量降级和来源摘要，不自行解释原始字段。
- 不存在页面直连上游 provider 或直接写核心数据文件的路径。

### Agent

- 工具输入输出有版本和 schema；每次调用有 request/task/audit id。
- Agent 只能通过工具网关读取数据；写操作默认拒绝并可审计。
- 数据冲突、缺失和过期会被显式传递给用户。
- 模型不可用、工具超时或 provider 降级时，任务可取消、重试或降级，不污染 canonical 数据。

## 12. 当前未完成和本轮边界

截至本文档创建时：

- 当前 main 仍是 TickFlow-centric 运行面；
- 隔离 worktree 的存储/ProviderRuntime 基础尚未合并到 main；
- 自有的资金流、筹码、人气、TDX host health、路由和完整 source matrix 尚未完成；
- AI 仍是模型适配和策略生成能力，Agent runtime 尚未开发；
- 本轮没有修改代码、配置、依赖、服务或真实数据。

本文档完成的是**正式架构和可执行边界**，不是“已经完成数据源替换”的声明。后续实现应以本文档和评审意见为准，先完成 Phase 1，再逐 operation 推进 Phase 2/3。

## 13. 请项目负责人核查的决策点

1. 是否确认“工作台 / 数据平台 / AI Agent”三层名称和职责边界。
2. 是否确认“全部接入”按目标数据能力矩阵定义，而不是复制每个 GitHub 仓库的全部接口。
3. P0/P1 数据能力的排序是否符合实际使用：日 K、实时、财务、资金流、筹码、人气、概念/行业、资讯。
4. 是否同意 Agent 第一阶段只读，并要求所有写操作显式审批和审计。
5. 是否同意先在现有 monorepo/单进程内建立逻辑边界，待稳定后再考虑拆分部署。

---

**评审后动作**：只有在本文档获得确认后，才编写对应的实施计划并开始代码变更。实施时继续遵守“只借鉴数据来源情报，不搬整套系统”的边界，并先备份、再分阶段、可回滚地推进。
