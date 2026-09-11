# fund-flow window chain restore · Codex 最终只读验收

层：数据台保留数据只读链 + 用户台可见门槛。概念续更实现仍 isolated。不是 `canary` / `accepted` / `production`。

本文件只归档 Codex 总工只读观察与 Bridge/review 证据。不是 Cursor 观察。不另开 model 封装阶段。不改正式数据、调度或源码。

## 身份

| 项 | 值 |
| --- | --- |
| 新授权任务 | `01a09187-8f63-7193-9645-b38acbf9803a`（核对市场看板数据 (2)） |
| 实现 workflow 任务 | `383980cb-c599-4d65-a483-27c074941445` succeeded |
| 自动 review preflight | blocked：其他序列化任务在 candidate hash 之后追加了两份开发日志 |
| 独立只读 review | `3f1b61e4-49af-4f4c-abb6-34dcd830c902` pass |
| review session | `111d4686-cea4-4d41-8f7c-567300d9d426` |
| 实现写前备份 | `/Users/simon/备份/codex/20260912-015545-fund-flow-window-chain-restore-before` |
| 收尾写前备份 | `/Users/simon/备份/codex/20260912-025119-fund-flow-window-chain-restore-closeout-before` |
| 模型 | 请求/配置 Cursor Grok 4.6 Extra High；无供应商返回的 model/effort 身份 |

`changed-files.json` 不改正：它正确记录实现当时边界，早于后来序列化日志追加。

## Codex 总工观察 · Runtime/UI

观察来源：**Codex 总工观察，不是 Cursor 观察**。Codex in-app browser URL `http://127.0.0.1:3011/`，title `one-trading · Quant Terminal`，使用当前热加载源。

- 行业 126：UI 显示「近126个交易日累计」，`2026-03-12`..`2026-09-10`，coverage 128/128，full 128/128，「数据截止 2026-09-10 · 已陈旧 · 窗口完整」，农业综合Ⅱ -2.36亿、半导体 -5683.45亿。
- 概念 63：UI 显示 `2026-06-15`..`2026-09-10`，coverage 504/504，full 490/504，CAR-T细胞疗法 33.08亿、融资融券 -1.84万亿。
- 行业 250/年：显示 9/2 当日快照 + 明确「窗口数据不足，当前仍显示当日快照，不能当作 1 年 完整累计榜」。
- 概念 126/半年与 250/年：各为当日快照 + 对应明确窗口不足文案。
- 最终停在概念 63 + 行业 126，该 tab 标为可交付。
- Console 无 error；仅一条无关 React Router v7 future-flag warning。

## Codex 总工观察 · 已登录 HTTP GET

实际已登录浏览器 HTTP GET。Canonical digest 字段为 `[start,end,window_days,snapshot_count,covered_count,full_count,missing_count,window_complete,freshness_status,items as code/name/integer-main_net/days]`。每个 digest 与 `evidence/parquet-vs-service.json` 的 service 侧完全一致；该独立分支从保留正式 Parquet 重算全部返回行。这证明实际 HTTP == service artifact == 独立 Parquet（五个必核窗口）。

| 窗 | HTTP | 区间 | coverage | full | missing | complete | freshness | SHA-256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| industry_5 | 200 | 2026-09-04..2026-09-10 | 128/128 | 128 | 0 | true | stale | `c2b3070fd9c281f9ddb86dfd4266894d78bbfe89918d31cd2295e199eab1e01b` |
| industry_63 | 200 | 2026-06-15..2026-09-10 | 128/128 | 128 | 0 | true | stale | `76ffa5c5bbf5dab41a9fea8c54042f404c4d2c45e65ddaedca995a549d7978a9` |
| industry_126 | 200 | 2026-03-12..2026-09-10 | 128/128 | 128 | 0 | true | stale | `ee4a3e1d3204d87fd28aba86a8e83ecb381b6374d0db57e0337d8bae0377b514` |
| concept_5 | 200 | 2026-09-04..2026-09-10 | 504/504 | 504 | 0 | true | 无概念时效行 | `424a869e4ef605fcfa17d968bb8bc6ce05055cfb31ea65b2ae6286ee19b136ec` |
| concept_63 | 200 | 2026-06-15..2026-09-10 | 504/504 | 490 | 0 | true | 无概念时效行 | `07f87d543eebe8e0deceb4fa0515945a6bf627d188ed1fb2cd6c4a70b2edfb4f` |

## Bridge / 独立 review

- 实现任务 `383980cb-c599-4d65-a483-27c074941445` succeeded。
- 其自动 review preflight 仅因其他序列化任务在 candidate hash 之后追加两份开发日志而 blocked。
- 新独立只读 review `3f1b61e4-49af-4f4c-abb6-34dcd830c902`，session `111d4686-cea4-4d41-8f7c-567300d9d426`，在当前树源码审查后返回 pass。
- reviewer 自身不能跑 native 命令；返回后，挂到该 review 任务的 Bridge controller checks 全部 exit 0：backend focused pytest、frontend focused Vitest、TypeScript noEmit、formal Parquet verifier。
- 请求/配置 Cursor 模型为 Grok 4.6 / Extra High；无供应商返回的 model/effort 身份。

## 生命周期与非声称

- 数据台：保留数据读/API/UI 链已核。概念续更实现仍 isolated（未执行真实 H5 roll / 正式 `run_now`）。不是 `canary`，不是 `accepted`，不是 `production`。scheduler 启用/开火未验证。真实续更未验证。
- 用户台：仅可见行业 126 / 概念 63 与窗口不足回退为 `verified`。不是 `accepted` / `production`。
- 明确保留：未联网、未回填、未写正式数据、未 enable/开火调度、未跑真实行业/概念 roll、未跑正式 `run_now`；2026-09-10 历史 15:30 未复验。
- 本轮只改两份开发日志的 `fund_flow_window_chain_restore_20260912` 段，以及本文件与 `evidence/chief-iab.json`。未改正文段外既有行，未改 `changed-files.json`。

工程只读验收：通过（独立 review pass + Codex IAB 主路径 + HTTP==service==Parquet）。目标页用户 accepted / production：否。
