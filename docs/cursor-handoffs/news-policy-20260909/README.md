# 资讯/政策页交接（2026-09-09）

本目录是交接材料，**不是**三台实施权威。权威仍是：

- 用户台开发日志：`/Users/simon/Trading/one-trading/docs/workbench-development-log.md#news_policy_workbench`
- 数据台开发日志：`/Users/simon/Trading/one-trading/docs/data-platform-development-log.md#news_market_flash` 与 `#news_policy_items`
- 计划：`U-R-01` / `D-R-06`
- 主记录：`/Users/simon/Trading/用户台GitHub项目借鉴记录.md` 3.2 的 2026-09-09 功能证据子记录

## 当前阶段（2026-09-09 收口）

主审技术结论：当前实现 + 隔离预览可交用户验收。

- 用户台 `news_policy_workbench`：`verified`。不是用户 `accepted` / `production`。
- 数据台 `news_market_flash` / `news_policy_items`：保持 `isolated`（非正式 `data/news`，未升 `accepted`）。隔离实测有 canary 级证据；禁止写成全 82 源/全部历史完整采集或 `production`。

最终证据直达：

- 收口汇总：[`closeout/acceptance.md`](closeout/acceptance.md)
- 独立 UI finish（JSON 语义副本，**不宣称与 controller 字节相同**）：[`closeout/ui-review-finish.json`](closeout/ui-review-finish.json)
- 主审 IAB 观察（Codex in-app，不是 Cursor 观察）：[`closeout/chief-ui.json`](closeout/chief-ui.json)
- 数据独立复核原样：[`ui-fix/data-review-finish.json`](ui-fix/data-review-finish.json)（task `5613e51d` Technical PASS，39 tests / 526）
- 窄屏 UI 实现记录：[`ui-fix/ui-fix-check.md`](ui-fix/ui-fix-check.md)
- 隔离运行面（只读输入，本轮未改）：[`runtime.json`](runtime.json)（3048=`97934`，3041=`97951`）

独立 UI：task `e18ac0cf`，全新 session `7f91193c-b466-49db-90ec-2e80a85222d5`，Technical PASS / no P1；controller build exit 0（`a82d81bd`）；前端 33 tests（复核亲自跑）。原 controller finish.json sha256 `4d628224f80ff517afe87b8cea3f910b3fa2c375a81159b1a6c9932bc0b899ea`。附加 UI prompt 的 PING 超时不在数据 PASS 范围。

`7d39a518` `failed/read_only_candidate_changed` 与 `c89fcd1c` `failed/protected_input_changed` 保持失败历史，不得改成 completed。`1eab309c` 超时不是通过。

## 文件

- `closeout/`：本轮收口验收
- `feature-matrix.md`：上游功能 → 本地实现 → 验证（当前含窄屏 class 与前端 33）
- `changes.md`：变更文件、基线、测试（P2 段标 as_of，不要把「frontend unchanged/32」读成当前）
- `runtime.json`：隔离运行面（当前 PID；本收口未改）
- `limitations-rollback.md`：已知限制与回滚
- `p2-fix/`：数据 P2 静态证据
- `ui-fix/`：窄屏 UI 修正与数据独立复核原样 JSON

## 历史原始报告（保留不改）

以下是更早轮次的原始记录，不是本轮权威：

- `live-fetch.json`：首轮有限真实取数
- `retest-policy-dates.json`：第一次只清非法日历
- `retest-policy-date-provenance.json`：月份目录拼接续修
- `date-provenance-note.md`：日期来源续修短记
- `review/independent-review.md`：前序独立复核（技术 PASS，指出 P2）
- `check-seal/final-check.md`：前序封存
