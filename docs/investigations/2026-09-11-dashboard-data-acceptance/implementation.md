# 2026-09-11 核对市场看板数据

层：数据台只读核对 + 用户台契约/自动检查。Agent 台未动。不扩 Project display 与因子包。

状态区分：工程已查 / 自动通过 / 目标页待 Codex / 独立复查待 workflow。不是用户 accepted / production。

本轮未改声明源码。未发现可复现 P1/P2，故无代码变动。正式 `DATA_DIR` 只读。未重启 3011/3018。

## 四包证据链（9/10 旧报告 ≠ 本轮结果）

| 包 | 9/10 固定点 | 2026-09-11 13:57 正式盘 |
| --- | --- | --- |
| `ext_fund_flow_concept_daily_h5_roll_live_20260910` | WP1 续到 9/9；15:30 后再到 9/10 | H5 max 仍 `2026-09-10`，504/504，`source=eastmoney_fflow_day`，`unit_amount=yuan`，date+code 重复 0；go-stock 272 行保留 |
| 日历 4.6 覆盖补丁 | 1824→2007，`2025-01-01`～`2026-10-31` | 仍 2007 行 / 三所各 669 / `szse_month_list`；sha `dfd9f647…` ≠ 备份 `475f809e…`（WP2 已切，之后未再写） |
| `industry_half_year_window_open_20260910` | 行业 126：`2026-03-11`～`2026-09-09` 128/128 | 行业 126：`2026-03-12`～`2026-09-10` 128/128 完整。概念半年 / 两边 1 年仍是当日快照契约，不是已开长窗 |
| `daily_pipeline_natural_1530_observe_20260910` | job `f7864b8bdd` succeeded；行业+概念 9/10；质量核 9/9 | job 原文未变；日 K 分区仍无 `date=2026-09-10` |

9/10 目录只作定位：`docs/investigations/2026-09-10-concept-fflow-live`、`calendar-extend`、`industry-half-year-open`、`pipeline-1530-observe`。

备份（只读）：`/Users/simon/备份/codex/20260910-140918-ext-fund-flow-concept-daily-before-wp1`（概念 H5 max 仍 `2026-08-31`）；`/Users/simon/备份/codex/20260910-142649-trading-calendar-before-wp2`（1824 行，max `2026-08-31`）。本轮文档备份：`/Users/simon/备份/codex/20260911-135943-dashboard-data-acceptance-before-docs`。

## 源码契约（工程已查，行号 2026-09-11）

概念 H5 严格来源：`fetch_board_daily_history(..., h5_only=True, allow_local_fallback=False)` 且落盘前再滤 `eastmoney_fflow_day`；单位 `yuan`。`fund_flow.py:1488-1501,750-751`。独立锁：行业 `.industry_daily_roll.lock` / 概念 `.concept_daily_roll.lock` 与两把 thread lock，互不 `busy`。`1092-1095,1327-1341,1608-1676`。`cancel_job` 同时 `request_industry_roll_cancel` + `request_concept_roll_cancel`。`pipeline.py:110-111`。失败保旧：空 hist 不写；`write_ext_parquet` 时序合并失败拒绝整日覆盖；roll `atomic=True`。`ext_data.py:506-514`；`fund_flow.py:1522-1528,947`。date+code 正式盘重复 0。合作式限时：行业默认 180s、概念 720s，经 `deadline_monotonic` 停下一码，不是硬杀进程。`1611-1613,1655-1657,1387-1395`。概念 `ok` 看上一本地末日稳定码；新主题 90%：满窗码 ≥ `max(20, 0.9*snapshot)` 才 `window_complete`。`1540-1548,2094-2102`。

日历：空月 `CalendarProbeError`，不切正式文件，`kept_prior`；候选 = prior ∪ 新月。`calendar_probe.py:97-99,188-198,237-270`。SH/SZ/BJ 仍是深交所开闭旗展开，未丢 `2025-01-01` 历史。

用户台门槛：`BOARD_WINDOW_MAX_DAYS = { board: 126, concept: 63 }`；`wantsWindow` 才请求；250 永不请求。缺窗 / `window_complete === false` 用当日快照，文案「窗口数据不足…不能当作{档}完整累计榜」。`SectorFundFlowPanel.tsx:32-36,173,188,236,255-257,344-346`。行业 250 与概念 126/250：API 可算，`window_complete=false`（250 `full=0`；概念 126 `full=448/504` 低于 90%）。产品未开门，不能称已有长窗。

## 日 K 滞后诊断（不改 15:30）

`succeeded` ≠ 日 K 已到 9/10。原 job 与当前分区一致：`daily_days=0`，`quality.date=2026-09-09`，`kline_daily` max 仍 9/9（1744 分区，最新 5468 行），无 `date=2026-09-10`。

路径：`latest_daily=2026-09-09` → gap-fill batch `[9/9 ~ 9/10]` → 新增 0 分区 → `today_missing` 且工作日本可走 public 合成，但 `realtime_data_provider=tickflow` 走 `daily_pipeline.py:486`「跳过 public 合成」。质量门用最新已有分区（`daily_quality.py:37`），9/9 通过，job `succeeded`。行业/概念 H5 是另一生产者，15:31–15:35 已写入 9/10。

要有 9/10 日 K，依赖 TickFlow batch 在 cron 时已有收盘 bar，或 realtime=public 才启用公开合成，或更晚调度（文件头仍写 15:35 缓冲，偏好默认 15:30）。本轮不改点、不补写、不全日 K。

## 独立加总（只读内存）

算法：最近 N 个 `eastmoney_fflow_day` 日期，逐码 `main_net` 求和。与 `aggregate_board_window` 十二组 Top6 code/name/金额全部精确相等。见 `evidence/window-sums.json`。

| 窗 | 区间 | count/full/missing | 完整 | Top6 入 / 出（元） |
| --- | --- | --- | --- | --- |
| 行业 5 | 09-04～09-10 | 128/128/0 | 是 | 元件 +20159566848 / 半导体 -16502635520 |
| 行业 63 | 06-15～09-10 | 128/128/0 | 是 | 炼化及贸易 +687999424 / 半导体 -325643005696 |
| 行业 126 | 03-12～09-10 | 128/128/0 | 是 | 农业综合Ⅱ -235641869 / 半导体 -568344604928 |
| 概念 5 | 09-04～09-10 | 504/504/0 | 是 | 5G概念 +26824410368 / 融资融券 -50429288448 |
| 概念 63 | 06-15～09-10 | 504/490/0 | 是（90%） | CAR-T +3308004432 / 融资融券 -1842728054784 |

行业时效（盘中 13:58，收盘前）：`data_as_of=2026-09-10`，`expected=2026-09-10`，`fresh`，`calendar_covers=true`。概念无时效字段。

相对 9/10 上午 HTTP：窗右端从 9/9 滚到 9/10，左端各进一日。金额已变，旧浏览器数字不能当本轮页结果。

## 自动检查

- backend 列明 4 文件：46 passed（`/tmp` basetemp）
- frontend 14 passed；`tsc -p tsconfig.json` 通过
- vite build 写到 `/tmp/ot-dash-accept-frontend-dist`，未覆盖项目 `frontend/dist`

## 运行面 / HTTP

目标 URL：`http://127.0.0.1:3011/`（Vite）→ `http://127.0.0.1:3018/`。13:56 两端口无 LISTEN、无 uvicorn/vite PID。匿名 curl 为 connection refused，不是 401。未重启。已登录 HTTP 与真实首页待 Codex 内置浏览器。源码 mtime：`fund_flow.py` 09-10 14:07，`daily_pipeline.py` 14:07，`calendar_probe.py` 14:23，`SectorFundFlowPanel.tsx` 15:12，`pipeline.py` 14:07。HEAD `31216dd` dirty。

## 尚缺

- 真实源续更 / 已登录 HTTP / 目标页（Codex）
- 独立复查（workflow 新会话）
- 用户 accepted / production
- 日 K 9/10（观察，非本轮修复）
