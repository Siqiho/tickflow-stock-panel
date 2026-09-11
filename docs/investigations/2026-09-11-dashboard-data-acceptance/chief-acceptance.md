# WP1 看板数据核对 · chief 归档

层：数据台只读核对 + 用户台契约。不是新数据集。不是 accepted / production。

本文件只归档总工工程验收。不另开 model 封装阶段。

## 身份

| 项 | 值 |
| --- | --- |
| 旧 workflow | `352f625c-50d1-457d-965c-6a0be438e523` blocked（预算）。旧 review `d273` 取消，保留为历史。 |
| 新独立 audit | `01bbde76-e057-4fea-b74f-b959962184e5` PASS |
| review session | `23a8f1fd-d292-4062-8941-ef29bd90d793` |
| candidate | `fe4b29b9d34201819d1dbda3854b2f42591ab3353618e5a335865f3eeb5d92a4` |
| 对照 impl | `883367d3`。Codex 比原 impl 共同源码/测试/API hash 全同，仅两日志变动。 |
| 自动检查 | 46 后端 + 14 前端 / tsc / build 可复用。未在本执行端重跑 WP1 套件。 |

## Codex IAB（隔离 3011，本执行端未亲测）

观察来自 Codex，约 2026-09-11 15:00，目标 `http://127.0.0.1:3011/`，runtime owner `01a07a79-1c8e-73e0-af8f-85939177bb8b`。

- 行业 5 / 63 / 126 = 128/128，截止 9/10。
- 概念 5 = 504/504；概念 63 = 490/504。截止 9/10。
- 主要金额与 `evidence/window-sums.json` 相同。
- 概念 126 与双方 250：窗口不足 / 9/2 快照日期 / 不能当完整累计。产品未开门。
- 15:05:57 再看行业 126 显示「已陈旧」。这是日内 freshness 门随时间变化，不能把早前「足够新」写成一直 fresh。
- 全负 TOP 是 2026-08-27 既定两端 Top6 规则，不修改。
- 正式日 K 仍 9/9；job `f7864b8bdd` `daily_days=0` / quality 9/9 仍未解决。非 production。

`window-sums.json` 里部分窗 `freshness_status=null` 是当时内存聚合未带时效参数的旧原始值，不要篡改。它与 UI 实时 freshness 不是同一字段。

## 状态

工程验收：通过（独立 audit PASS + Codex IAB 主路径）。目标页/用户 accepted / production：否。日 K 9/10：观察，非本包修复。
