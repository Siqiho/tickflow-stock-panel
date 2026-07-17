# A-W2 go-stock 数据能力 Parity 报告

> 日期：2026-07-18  
> 对照：本地 `HEAD` vs 上游 tag `v2026.07.10.1-release`

| 能力 | 本地 | 上游 | 结论 |
|---|---|---|---|
| GetCallAuctionAuto / 集合竞价 | YES | YES | **已齐** |
| GetMACCapitalFlow / MAC 资金流 | YES | YES | **已齐** |
| App 暴露竞价/资金流 | YES | YES | **已齐** |
| AI 工具 GetMACCapitalFlow | YES | YES | **已齐** |
| IsOnExchangeFund / ETF 放行 | YES | YES | **已齐** |
| tool_search_etf_stock | YES | YES | **已齐** |
| UpdateGroup 分组改名 | YES | YES | **已齐** |
| syncStockBasicFromTdx 增量校准 | NO | YES | **缺口**（P1 后续） |
| 概念标签 API+DB | 本轮补齐 | YES | **A-W3 已做** |
| 飞书 bot / 测量 / 波浪 | NO | YES | Track B/C，非本波 |

## 动作

- 无需为竞价/MAC/ETF 再 cherry-pick 大段上游。
- 概念标签 API+DB 在 A-W3 落地。
- TDX 证券列表增量校准 `syncStockBasicFromTdx` 列入后续 A 轨。
