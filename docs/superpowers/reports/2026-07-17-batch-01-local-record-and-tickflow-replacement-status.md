# Batch 01 本地任务记录与 TickFlow 替换状态

> 记录日期：2026-07-17（Asia/Shanghai）
> 适用项目：`/Users/simon/Trading/one-trading`
> 结论口径：以本地代码、候选分支、生产 Provider composition、Source Matrix 和本轮验证证据为准。

## 1. 本次已经完成并保存在本地的工作

- 完成“TickFlow 等价替代与退役”正式设计和 Batch 01 基础设施整合计划。
- 建立 one-trading 自有 Provider、canonical schema、ProviderRuntime、路由、质量门、Parquet transaction、lineage、checksum 和 recovery 基础。
- 保持 TickFlow 为唯一生产 Provider；没有把 `easy_tdx` 或其他 GitHub 来源注册到生产 composition。
- 为 `easy_tdx × daily × stock × by_symbol` 保留 one-trading 自主实现的默认禁用 Adapter 和 fake protocol/conformance 测试。
- 修复两项测试确定性/静态检查问题，没有放宽数据质量规则。
- 完成后端、前端、内置浏览器、正式数据 checksum 和 clean-main 门禁验证。

本地候选状态：

```text
ready branch: codex/foundation-integration-b01-ready
ready SHA: b0554ee839b2478e67817d2bfd6980223cfb9ffb
local main SHA: edcffcfaadcdbc3c81be392f4e418503baf05a8f
landing status: MERGE-READY, not merged
```

主工作树包含用户保留改动，所以 Batch 01 没有合并、暂存、清理、重置或覆盖 `main`。

## 2. 关于“是否已经全部接入并替换 TickFlow”的事实结论

**没有。当前既没有把所有 GitHub 数据源接入 one-trading，也没有完全替换或停用 TickFlow。**

当前生产运行时仍只有：

```text
descriptors: tickflow
factories: tickflow
daily/stock/by_symbol: tickflow
daily/stock/batch: tickflow
```

`easy_tdx` 不在生产 descriptors、factories 或 selections 中。应用主生命周期仍导入 TickFlow client、policy、repository 和 capability 探测；TickFlow Key 的设置、删除和 endpoint 配置路径仍存在。因此不能表述为“已替换 TickFlow”“已无 TickFlow 依赖”或“已完全停用 TickFlow”。

## 3. GitHub 来源的当前接入状态

| 来源 | 当前状态 | 是否生产可用 | 还缺什么 |
| --- | --- | --- | --- |
| `handsomejustin/easy_tdx` | `daily/stock/by_symbol` 为 `target-disabled`；one-trading 自有 Adapter 已有 fake fixtures | 否 | 真实 TDX host、市场边界、分页、单位、交易日、数据完整性、shadow、canary、回滚验收 |
| `simonlin1212/a-stock-data` | 资金流、筹码、人气仅来源情报；operation 为 `unavailable` | 否 | 原始字段语义、时间、交易日、单位、limits、错误分类及自主 HTTP Adapter |
| `1nchaos/adata` | 东财资金流端点已记录；operation 为 `unavailable` | 否 | 单位、时区、交易日、限频、错误分类、conformance 和自主 HTTP Adapter |
| `finvfamily/finshare` | 资金流字段和项目证据已记录；仍为 design-only / `unavailable` | 否 | 真实 endpoint、batch 契约、时间、limits、conformance 和自主 HTTP Adapter |
| `ArvinLovegood/go-stock` | reference-only 数据源地图 | 否 | 逐个固定底层 endpoint 和字段证据后，才能形成 one-trading SourceRecord/Adapter |
| `shy3130/tickflow-stock-panel` | reference-only 上游工作台 | 否 | 不作为新的自有数据源；当前 one-trading 仍保留其 TickFlow 生产能力 |

这里的原则是：只借鉴这些项目暴露的底层数据来源和语义证据，不复制它们的 loader、registry、缓存、数据库、调度器或 UI。实际接入必须由 one-trading 自主实现 transport、Adapter、canonical/ext schema、质量校验、lineage、transaction 和 Provider 路由。

## 4. 尚未完成的 TickFlow 等价替代矩阵

### P0 核心基础

- 股票日线真实 TDX 实验室验收。
- 证券列表、交易日历。
- `daily/stock/by_symbol` shadow、临时 canary 和生产灰度。

### P1 核心等价能力

- 复权因子和公司行为。
- 分钟线和实时行情。
- 同一 operation 的多源 conformance、cooldown、熔断和 fallback。

### P2 产品必要能力

- 指数、ETF。
- 财务/F10。
- 同步、选股、回测、图表和后台任务的 owned-provider 全链路。

### P3 独立实时能力

- depth、订阅和 WebSocket 类能力；不得和普通 HTTP 行情混为同一故障域。

### 特色扩展数据

- `market.fund_flow`、`market.chips`、`market.popularity`、抢筹、概念和行业。
- 初期进入 `ext_data`，不污染日线 canonical schema。
- 必须重新核查真实底层端点，由 one-trading 自主实现 HTTP Adapter；不能直接把 GitHub 项目整体接入。

## 5. 完全停用 TickFlow 的硬门槛

只有同时满足以下条件，才能宣布“已经替换并完全停用 TickFlow”：

1. 删除 TickFlow Key 后服务正常启动。
2. 所有生产必需的 `dataset × asset_type × operation` 都解析到 one-trading 自有 Provider。
3. 数据同步、选股、回测、图表、财务和后台任务全部通过无 Key 验收。
4. TickFlow 实际网络请求计数为零。
5. owned Provider 具备经 conformance 验证的 cooldown、熔断和 fallback。
6. 连续观察期没有不可解释的数据缺口。
7. 生产 composition 和默认 selection 已移除 TickFlow。
8. 稳定观察期结束后，TickFlow 配置、客户端引用、依赖、页面提示和专用代码已经删除。

Batch 01 的“外部 Provider 请求为零”是在 `ONE_TRADING_ALLOW_PROVIDER_NETWORK=0` 的隔离验证中得到的，只证明基础设施没有越权联网，**不等于无 TickFlow Key 的真实生产替换验收已经完成**。

## 6. 后续必须遵循的实施顺序

```text
先无损协调并落地 Batch 01
→ 真实 TDX daily/stock/by_symbol 实验室验收
→ shadow 与小范围 canary
→ 按 operation 补齐 TickFlow 等价矩阵
→ 无 TickFlow Key 全链路验收
→ 先移出生产 composition，再删除 TickFlow 专用代码
→ 最后扩展资金流、筹码、人气等特色数据
```

不得一次性接入所有 GitHub 项目，也不得在等价矩阵和无 Key 验收完成前一次性关闭 TickFlow。每个切换单元必须按 `source evidence → one-trading Adapter → canonical/ext schema → shadow → canary → production selection` 单独验收和回滚。

## 7. 本轮验证摘要

- 后端 guarded suite：`1157 passed, 18 warnings`。
- 前端定向测试：`2 files / 8 tests passed`；TypeScript/Vite build 通过。
- 内置浏览器：TickFlow 为唯一可见生产 Provider；`easy_tdx` 不可选；隔离运行外部 Provider 请求为 `0`。
- 正式数据：`1001` 个文件、`985` 个 Parquet，与备份 manifest 比较均为 `0` 差异。
- 最终分支审查：无 Critical 或 Important 问题。
- 当前交付状态：`MERGE-READY`，不是 `LANDED`，更不是“TickFlow 已替换”。
