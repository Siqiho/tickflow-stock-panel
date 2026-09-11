# 行业资金流日线续更 — 阶段 B（隔离）

- 日期：2026-09-07
- 范围：行业 `ext_fund_flow_bk_daily` 最小续更 + 独立复查返工
- 状态：`MARKET_DASHBOARD_PHASE_B_FIXES_READY_20260907`，等待原独立复查者复验
- 主树源码：未改。现行 `--reload` 后端未重启。正式 `DATA_DIR` 未回补。`review/` 只读未改。

## 写入者 / 工作树

- 仅一个 git worktree：`/Users/simon/Trading/one-trading` @ `31216dda527cd4ec177b9cbf6fd1c524dbadbe82` `[main]`
- 现行服务：uvicorn `--reload` 监视 `backend/`（父 PID `83220`；worker `15035`）；前端 Vite `3011` PID `83232`
- 因此本轮只改本任务 overlay / tests / patches / results / README / APPLY，以及两台开发日志追加

## 原基线（主树四源码文件，2026-09-07 18:44 再核仍相等）

- `fund_flow.py` `87ef39074dd2aae76f99b4c913b120c30947bf66f0ccca00722cdbce8a548e0b`
- `daily_pipeline.py` `7003b64ca634a230a588ffca43e3ddaba89529ce32e33ccecfdb600acd0bba58`
- `SectorFundFlowPanel.tsx` `4163d9f8c75e9f42d42c78e8f663de89bc351fe1945894a2e6550447343f31a8`
- `api.ts` `32055dd67d8065674d14d45554f4f1179dfcf2f8ac291fb9cbe55c2996cba957`

返工额外纳入（主树此时仍等于 baseline 副本）：

- `backend/app/api/pipeline.py` `af18dda3…686ed70` — 600s 孤儿误杀会再开第二条 `run_now`
- `backend/app/services/ext_data.py` `3b0e5b43…06a8137` — 行业续更要可选原子写，默认行为不变
- `frontend/src/lib/api-v02.ts` `f0aaabfc…46dc977` — **无逻辑改动**，只为 overlay `api.ts` 的 `./api-v02` 相对导入；**不进 apply patch**

副本：`baseline/` ；备份：

- Phase B：`/Users/simon/备份/codex/20260907-154837-industry-fflow-daily-roll/`
- 返工前：`/Users/simon/备份/codex/20260907-183500-industry-fflow-phase-b-fixes/`

## 精确变更清单

| 目标（应用到主树时） | overlay | 做什么 |
| --- | --- | --- |
| `backend/app/services/free_sources/fund_flow.py` | 同相对路径 | 快照全集续更；行业专用 `h5_only=True`；`persist(..., atomic=True)`；协作式 `cancel_event` + 默认 180s 墙钟；latest 只在快照∩`eastmoney_fflow_day` 内算；时效按 Asia/Shanghai + `close_time` |
| `backend/app/jobs/daily_pipeline.py` | 同 | 进程内闸：第二次 `run_now` 直接 `busy`、不重跑日K；行业在 quality 之后、`done` 之前；失败不改 `quality`/`daily_days` |
| `backend/app/api/pipeline.py` | 同 | 600s 仅当 **不在飞** 才 `job_store.fail`；在飞则复用；`cancel` 先 `request_pipeline_cancel()` |
| `backend/app/services/ext_data.py` | 同 | `write_ext_parquet(..., atomic=False)` 默认仍 `df.write_parquet`；`atomic=True` 走现有 `atomic_write_parquet` |
| `frontend/src/components/SectorFundFlowPanel.tsx` | 同 | 仅 `kind==='board'` 显示时效行（Phase B 已有，本轮未改判定文案） |
| `frontend/src/lib/api.ts` | 同 | 仅业务可选时效字段；无测试专用导出 |

独立复查补丁：`patches/phase-b-industry-fflow-daily-roll.diff`（六文件，对 `baseline/`）。

## P1-1 选定方案与取舍

**选定（最小，不另造通用任务平台）：**

1. `run_now` 外包非阻塞锁。第二次触发立刻 `status=busy`，**不跑日K**。
2. `/api/pipeline/run` 的 600s 只在 `pipeline_in_flight() is False`（reload 真孤儿）时 `fail`；在飞则复用，不开第二条。
3. 行业续更有协作退出点：每只 fetch / 下一批之前看 `cancel_event` 与 `time.monotonic()` 截止。默认墙钟 180s。超时/`cancelled` 后函数返回，线程结束，不再写盘。
4. `emit("done")` 移到行业续更之后。日K `quality`/`daily_days` 在行业之前算完。

**明确不采用：**

- 只把 API 600s 改小
- `Future.result(timeout)` 当取消（那不会停旧线程）
- 拆独立通用任务平台 / 把行业从 `run_now` 拆成第二套调度器

限制：当前这一只 H5 请求仍受现有 `timeout=8.0` 约束；截止检查在请求边界，不中途杀 HTTP。这是复用现有 client，不是伪取消。

## 未改

- 概念日线、半年/一年窗口、交易日历扩修、Top20 helper、`stock.db`、正式 `DATA_DIR`、现行服务、commit/push/部署
- `review/` 历史报告与断言旧 bug 的独立用例

## 测试

- 原 12 pytest + 本轮 13 条修正回归 = 25 passed：`results/pytest.txt`
- overlay 面板 vitest 10 passed（未因本条总工意见重跑）：`results/vitest.txt`
- overlay `api.ts` 加载：测试插件记录已解析绝对路径 + 契约 vitest 1 passed；隔离 `tsc --noEmit` 0：`results/tsc-overlay-api.txt`、`results/vitest-resolved-paths.json`
- 逐项对照：`fixes-response.md`

## 权威日志

- 数据台：`docs/data-platform-development-log.md` 条目 `ext_fund_flow_bk_daily_industry_roll_phase_b_20260907`，状态仍为 `isolated`
- 用户台：`docs/workbench-development-log.md` 条目 `industry_fundflow_daily_roll_freshness_20260907`，状态仍为 `implemented`
- 相对 15:50 备份的日志漂移**至少包含 Phase B 自己追加的这两条**，回滚不得整份覆盖日志
