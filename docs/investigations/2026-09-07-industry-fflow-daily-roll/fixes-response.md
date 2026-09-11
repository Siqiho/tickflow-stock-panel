# 阶段 B 返工对照独立复查

- 日期：2026-09-07 18:47 +0800
- 执行端：本会话 Cursor；要求 Grok 4.6 / Extra High。供应商回执 / 实际 model id **未核验**。
- 独立报告（只读）：`review/independent-review.md`
- 独立旧用例未改：`review/tests/test_independent_findings.py`
- 主树四源码文件 18:44 再核仍等于 Phase B baseline。未应用主树、未写正式 data、未抓源、未启停服务。

## P1-1 调度超时 / 重入

**修法：** 不另造通用任务平台。`run_now` 外包非阻塞锁；第二次立刻 `busy`，不跑日K。`/api/pipeline/run` 的 600s 只在 `pipeline_in_flight() is False` 时 `job_store.fail`（reload 孤儿）；在飞则复用。行业有 `cancel_event` + 默认 180s 墙钟，检查点在每只 fetch / 下一批之前。`emit("done")` 移到行业返回之后。不是缩小 600s，也不是 `Future.result(timeout)`。

**文件 / 行（overlay）：**

- `overlay/backend/app/jobs/daily_pipeline.py` L42–156 闸/busy/cancel；L958–965 行业后 `done`；L960–963 传入 `cancel_event` / `time_limit_s`
- `overlay/backend/app/api/pipeline.py` L32–57 在飞不 fail；L112 `request_pipeline_cancel()`
- `overlay/backend/app/services/free_sources/fund_flow.py` L1315–1323 `_roll_should_stop`；L1374–1382 循环检查点；L1470–1482 默认 180s 截止

**测试：** `test_second_run_now_does_not_redo_daily_k_while_first_is_in_flight`；`test_emit_done_happens_after_industry_roll`；`test_pipeline_time_limit_stops_further_writes_and_keeps_quality`；`test_cancel_event_stops_before_second_code`；`test_stale_job_helper_does_not_fail_in_flight_worker`。含在 2026-09-07 18:45 的 25 passed 内。之后未重跑这 25 条。

**仍未验证：** 真实盘后 cron、真实 `/api/pipeline/run` HTTP、reload 后真孤儿、128 只真实 H5 是否在 180s 内跑完。

## P1-2 APPLY / 回滚

**修法：** 删除整文件 copy 与 15:50 备份覆盖源码/权威日志。应用与反向都先看现有差异再 `patch --dry-run`；漂移时三方只加/撤本轮 hunk。日志只追加。写明日志漂移至少包含 Phase B 自己追加的 `ext_fund_flow_bk_daily_industry_roll_phase_b_20260907` 与 `industry_fundflow_daily_roll_freshness_20260907`。

**文件：** `APPLY.md` 全文；`README.md`；两台开发日志 18:47 追加段。

**测试：** 文档检查，无运行时用例。

**仍未验证：** 未对主树执行 dry-run/apply（本轮禁止）。

## P2-1 快照外日期污染 latest

**修法：** `_industry_h5_latest_coverage` 先滤快照 code，再滤 `eastmoney_fflow_day`，再 `max(date)`。

**文件 / 行：** `fund_flow.py` L1240–1275。

**测试：** `test_leftover_newer_date_outside_snapshot_does_not_poison_latest`；`test_old_day_h5_reply_keeps_local_latest_complete`。独立旧用例 `test_leftover_newer_date_on_non_snapshot_code_poisons_latest_complete` 未改。

**仍未验证：** 正式 `DATA_DIR` 当前无这条脏数据；未对真实盘再扫。

## P2-2 原子持久化

**修法：** 复用现有 `atomic_write_parquet`。`write_ext_parquet(..., atomic=False)` 默认仍 `df.write_parquet`。仅行业 persist 传 `atomic=True`。

**文件 / 行：** `overlay/backend/app/services/ext_data.py` L12、L394–454；`fund_flow.py` L944、L1412–1418。

**新增源码文件原因：** `ext_data.py` 纳入 overlay/baseline，因行业续更扩大写入，必须在写路径提供可选原子替换且默认不变。

**测试：** `test_atomic_write_keeps_old_partition_when_tmp_write_raises`；`test_atomic_replace_failure_keeps_old_partition`（旧分区可读，其他代码/源/更长历史保留）。独立旧用例 `test_write_ext_parquet_is_not_atomic` 未改。

**仍未验证：** 真实并发读窗口 API 是否碰到 tmp；正式盘写入。

## P2-3 日期 / 盘中时效

**修法：** `latest` 见 P2-1。时效：Asia/Shanghai；仅日期视为当天 23:59:59；开市且 `now < close_time`（缺省 15:00）则期望上一开市日；周末/假日用最近已完成开市日；日历 `max < today` 仍 `unknown`，不补日历。

**文件 / 行：** `fund_flow.py` L49、L1130–1217、L1767–1768、L1959–1961。

**测试：** `test_intraday_before_close_uses_previous_open_day`；`test_weekend_and_holiday_and_unknown_calendar`。独立旧用例只传 `as_of_today`（日终）仍应为 `stale`，未改。

**仍未验证：** 真实 2026-09-07 盘中/盘后面板；正式日历仍止于 2026-08-31，应用后行业时效会 `unknown` 直到日历续上。

## P2-4 H5-only

**修法：** `fetch_board_daily_history(..., h5_only=False)` 默认不变。行业 roll 传 `h5_only=True`，hosts 只留 `https://emdatah5.eastmoney.com/dc/ZJLX/getDBHistoryData`。失败上抛，不打 push2his/push2delay/push2，不走 go-stock。

**文件 / 行：** `fund_flow.py` L50、L653、L708–711、L1384–1392。

**测试：** `test_h5_only_uses_exact_url_and_does_not_probe_fallbacks`（失败只 1 个 H5 URL；`h5_only=False` 仍 4 host）。

**仍未验证：** 真实东财 H5 JSON 是否仍为 `data.klines`。

## P2-5 测试加载 overlay

**修法：** conftest 加载 overlay `ext_data` / `fund_flow` / `daily_pipeline` / `pipeline`。vitest alias `@/lib/api` → overlay `api.ts`，`api-v02.ts` 仅作相对导入副本、无逻辑、不进 patch。

**总工 18:47：** 已删除仅测试用的 `INDUSTRY_FFLOW_WINDOW_CONTRACT`。改为：

- `tests/vitest.overlay.ts` 插件记录已解析绝对路径 → `results/vitest-resolved-paths.json`
- 契约 vitest 断言该路径是 overlay，并导入已有业务 `api`
- 隔离 `tsc --noEmit -p tests/tsconfig.overlay-api.json` 检查 `FundFlowWindowResponse` 时效字段

**文件 / 行：** `api.ts` L3988–4015 只有业务可选字段；`tests/vitest.overlay.ts`；`tests/frontend/api.overlay-contract.test.tsx`；`tests/frontend/fund-flow-window-contract.ts`。

**测试：** 18:45 原 12+13 pytest 25 passed；面板 vitest 10 passed（本条意见后未重跑）。18:47 契约 vitest 1 passed；`tsc --noEmit` exit 0。独立旧用例未改、不当通过门。

**仍未验证：** 真实 HTTP 401/200、已登录 Codex 内置浏览器。

## 新增纳入 baseline 的源码

| 文件 | 原因 |
| --- | --- |
| `backend/app/api/pipeline.py` | 600s 孤儿误杀会再开第二条 `run_now` |
| `backend/app/services/ext_data.py` | 行业原子写需要可选参数，默认行为不变 |
| `frontend/src/lib/api-v02.ts` | overlay `api.ts` 相对导入；**无逻辑差，不进 patch** |

不是通用底层大重构。

## 仍未验证（全部发现共用）

- 真实东财 H5
- 真实 `/api/pipeline/run` 与资金流 window HTTP
- 已登录 Codex 内置浏览器
- 盘后真实调度
- 正式 `DATA_DIR` 回补
- 主树 apply / 热重载
