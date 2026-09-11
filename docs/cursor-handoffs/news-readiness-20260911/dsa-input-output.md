# A-P1-04 独立 input/output（未实施）

计划状态保持 `candidate`。本轮只整理对照，不改 `stock_analyzer.py`，不启动 AI 包，不写 Agent 开发日志为已实现。

权威计划：`/Users/simon/Trading/Agent台下一步工程工作计划.md` 的 `A-P1-04`。对应用户台 `/stock-analysis`，数据台消息面仍未准入。

## 目标

把 DSA 决策信封接到现有 `POST /api/stock-analysis/analyze` 与现有 NDJSON 流，而不是另装上游 Web、搜索 API 或 Hermes Skill。

## Input（现有，只读消费）

| 输入 | 来源 | 无数据时 |
| --- | --- | --- |
| 本地日 K / 关键价位 | 现有分析链 | structured unavailable，不编造 |
| 轻量财务 | 现有分析链 | 明确缺字段 |
| 本地筹码摘要 | 页面已有，需只读摘要进 prompt | 无筹码则写 unavailable |
| 本地个股资金流摘要 | 页面已有，需只读摘要进 prompt | 无资金流则写 unavailable |
| 快讯 / 公告 / 政策 | **本轮资讯页不是分析链输入** | 消息面必须 `unavailable`，沿用现有“价量推断待接入”语义，不得假装检索 |

禁止输入：DSA SearchService、Anspire/SerpAPI/Tavily/Bocha/Brave/MiniMax/SearXNG、美股 Reddit/X/Polymarket、飞书/企业微信、GitHub Actions、15 策略 YAML、外部模型重写、go-stock Runtime。

## Output（现有契约）

- 继续现有 NDJSON 事件流，不换协议。
- 用户台仍渲染 Markdown。
- 四段信封只是系统提示/输出骨架候选：结论 / 数据视角 / 情报 / 作战计划。
- 情报段在无本地快讯/公告时必须写 unavailable，不能引用本轮 `/news` 演示夹具或 isolated_preview 当真实检索。
- 买卖点不是可执行意图。

## 依赖

- 用户台：现有 `/stock-analysis`。
- 数据台：日 K / 筹码 / 资金流本地只读；消息面留给 `D-P2-05` / `announcement_events` accepted 之后的 `A-P1-05`。
- Agent：`A-P0-01` 审计信封仍是前置；本包不因此 active。
- 本轮资讯 readiness 只让 `/news` 可解释，不自动成为分析链输入。

## 非目标

- 不 clone/安装 [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis)
- 不新增 `/chat` 或决策信号页
- 不改数据台 Provider
- 不把三栏资讯墙搬进分析链
- 不改 `stock_analyzer` 代码（本任务未改）

## 本地开发日志

Agent 台开发日志：**未更新**。用户授权并改代码后才能建条目。当前不是 `sandbox` / `verified` / `approved` / `production`。
