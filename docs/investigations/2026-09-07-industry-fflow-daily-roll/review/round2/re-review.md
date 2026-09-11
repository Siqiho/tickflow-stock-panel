# 行业资金流每日续更 — 独立复验（round2）

- 日期：2026-09-07 18:56 +0800；精度澄清 2026-09-07 18:59 +0800（只改正文，不改代码、不重跑测试）
- 复查者：本会话独立复验（不新建 agent、不换模型）
- 任务根：`/Users/simon/Trading/one-trading/docs/investigations/2026-09-07-industry-fflow-daily-roll/`
- 写入范围：仅 `review/round2/`
- 只读：原报告、旧用例、overlay、主树、正式 data、权威日志、`fixes-response.md`、新六文件 patch、`APPLY.md`
- 层：数据台（续更/调度/落盘）+ 用户台（行业窗口时效）；未改产品代码，未应用主树，未启停服务，未访问外网
- **供应商 wire 回执 / 实际 model id / effort：未核验**

结论：重入与 `done` 时序等原 P1/P2 阻断点在 overlay 离线针对验证上已关闭。合作式 deadline / 取消点已实现并被测试覆盖。**严格墙钟上界未证明**，不能写成「在飞 HTTP≤8s」或「180+8 已证明总体有界」。六目标主文件仍等于各自磁盘 baseline。副本 dry-run/apply 与 overlay 一致，反向可恢复且保留无关后续 hunk。  
**仍阻断进入主树的可复现问题：无。** 不因此另造新架构或改本轮代码。  
离线通过只表示可以准备主树应用，以及之后的真实源 / HTTP / 已登录 Codex 内置浏览器 / 盘后验收。真实源阶段需评估耗时与部分成功。**不能写成 production / 已修好。**

旧 `review/tests/test_independent_findings.py` 断言的是 bug 存在，本轮未当通过门，也未改。

---

## 仍阻断进入主树的可复现问题

无。

本轮没有再复现：第二条 `run_now` 重跑日K、600s 误杀在飞 worker、整文件 copy/备份覆盖回滚、快照外日期污染 latest、行业路径非原子覆盖、盘中把昨日已齐标 stale、roll 打 push2 备用、或 APPLY 抹掉无关后续 hunk。

---

## 原发现逐项

### P1-1 任务 600s 判失效与重入 — **closed**

原阻断：续更接在 `emit("done")` 之后且无墙钟；`/api/pipeline/run` 超 600s 只 `job_store.fail()` 再开第二条完整 `run_now`；行业锁挡不住日K；`quotes["n"]==2`。

现实现：

- 进程内 `_PIPELINE_GUARD` / `_PIPELINE_IN_FLIGHT` / `_PIPELINE_CANCEL`。第二次 `run_now` 立刻 `busy`，不跑日K。`finally` 释放闸。
- 600s 只在 `pipeline_in_flight() is False` 时 fail（reload 孤儿）。在飞则复用 `job_store.create()` 已有 running id，不开第二条 executor。
- 行业 `cancel_event` + 默认 180s 合作式 deadline（检查点见下节，不是已证明的严格墙钟上界）；`emit("done")` 在行业返回之后。
- `cancel_job` 调 `request_pipeline_cancel()`；worker 在下一代码/下一批检查点停。闸仍持有，故取消后立刻再 `run_now` 也不重跑日K。
- persist 异常经 `_run_industry_fund_flow_daily_roll` 收成 `status=error`，不翻 `quality`；行业锁在 `roll_industry_daily_from_h5` 的 `finally` 释放。并发第二条得 `busy`。

证据：

- overlay `daily_pipeline.py` L42–156、L958–965、L151–156
- overlay `pipeline.py` L32–68、L104–114
- 主树 `pipeline_jobs.py` L218–219：running 则复用 active id
- 本轮 `test_second_run_now_and_cancel_route_do_not_redo_daily_k`：`quotes["n"]==1` 当第一条在飞；`should_force_fail_stale_pipeline_job(in_flight=True, elapsed_s=900) is False`；cancel 后仍 `n==1`；结束后第三条才把 `n` 增到 2
- 本轮 `test_done_after_roll_and_cooperative_deadline`：`events[-1]=="done"`，`quality.ok is True`，`status=="timeout"`
- 本轮 `test_cancel_stops_next_code_and_exception_releases_lock`：第二码不 fetch；persist 爆炸后下一轮不是 `busy`

残留（不阻断进入主树）：

- `cancel_job` 立即 `job_store.fail`，worker 可能还在写当前码。这是合作式取消，不是第二条日K。
- overlay 含 `_reset_pipeline_guard_for_tests`（测试夹具，不是业务常量）。生产路径不调用。

### 180s 默认时限 — **合作式限时实现已验证；严格墙钟上界未证明**

与 P1-1 分开：重入（第二条 `run_now` 不重跑日K）和 `done` 落在行业返回之后，已关闭。本节只谈限时语义。

已验证的合作式 deadline / 取消点：

- 每批之前、每码 `fetch` 之前查 `_roll_should_stop`（`fund_flow.py` L1315–1323、L1374–1382）。
- 默认 `time_limit_s = 180.0`（L1480–1482）。无 `Future.result`，无缩小 600s，也不是强制取消在飞请求。
- `fetch_board_daily_history` 仍传 `timeout=8.0`，函数体无 `cancel_event`，不会把取消送进 httpx。
- 检查点之后若已截止，仍会 persist 当前已取到的批次，再 `break`（L1412–1421）。本地写本身没有 deadline。

`timeout=8.0` 不能证明「在飞 HTTP≤8s」。httpx 该参数通常是 connect / read / write / pool 各阶段或网络不活动超时，不是整个请求的严格 8 秒墙钟上限。慢速持续返回、各阶段累计、以及截止后的本地持久化，都不能由这一配置推出 180+8 硬上界。本轮**删除**「不是无界 / 已证明总体有界」的过强结论。

实际测试覆盖：`test_done_after_roll_and_cooperative_deadline` 用短 `industry_time_limit_s=0.05` 和 mock fetch（`sleep(0.12)`）证明下一码不再 fetch、BK0002 旧值保留、`status=="timeout"`、`done` 在 roll 之后。源码断言有默认 180、fetch 块无 `cancel_event`、无 `Future.result`。这覆盖合作式检查点，**不覆盖**真实慢响应、分阶段累计超时、或本地写耗时。

未验证：真实 H5 慢速/持续返回会把单次请求拖多久；一批 persist / 原子写要多久；128 只真实回补在合作式 180s 后会停在哪一只、部分成功有多大。这些留给真实源阶段评估耗时与部分成功，不因此另造强制 abort / Future 墙钟架构，也不改本轮代码。

### P1-2 APPLY / 反向 patch 保留无关差异 — **closed**

`APPLY.md` 已禁止整文件 copy 与 15:50/18:36 备份覆盖源码或权威日志。应用/回滚改为 baseline SHA + `patch` / `patch -R`；漂移时三方只加/撤本轮 hunk。日志只追加。六文件列表含 `pipeline.py`、`ext_data.py`；`api-v02.ts` 不进 patch。

证据：`review/round2/results/six-files-and-patch.txt`

- 六文件磁盘 SHA == baseline
- `patch --dry-run -p1` 与副本 apply 后六文件 == overlay
- 在 `ext_data.py` 副本追加 `# ROUND2_UNRELATED_HUNK_KEEP_ON_REVERSE` 后 `patch -R`：其余五文件回到磁盘 baseline；`ext_data.py` = 原磁盘 + 该 hunk

### P2-1 快照外日期 / 旧日回复 — **closed**

`_industry_h5_latest_coverage` 先滤快照 code，再滤 `eastmoney_fflow_day`，再 `max(date)`（L1240–1275）。

本轮 `test_leftover_outside_snapshot_and_old_day_reply`：盘里 BK9999@2026-09-02，H5 只回 2026-08-28；`latest_data_date==2026-08-31`，`latest_day_complete is True`；08-31 旧值保留；08-28 新行写入；09-02 遗留行仍在。

### P2-2 原子写 — **closed（行业 persist 路径）**

`write_ext_parquet(..., atomic=False)` 默认仍 `df.write_parquet`（`ext_data.py` L394–454）。行业 roll persist 传 `atomic=True` → `atomic_write_parquet`（tmp + `os.replace`）。`persist_board_daily_history` 把 `atomic` 传到按日分区写（`fund_flow.py` L944–965、L1412–1418）。

本轮 `test_atomic_tmp_and_replace_failures_keep_history`：真实临时分区名含 `.tmp-` 时写失败、以及 `os.replace` 失败，均保留 08-31 旧值、03-02 长历史、08-02 `go_stock_local_snapshot`。默认非原子路径未改，不要求本轮改所有 ext 写。

### P2-3 上海盘中 / 收盘 / 休息日 / 日历不足 — **closed**

`assess_industry_window_freshness`（L1140–1217）：Asia/Shanghai；仅日期 = 当天 23:59:59；开市且 `now < close_time`（缺省 15:00）→ 上一开市日；否则最近已完成开市日；`max(all_days) < today` → `unknown`，不补日历。

本轮 `test_shanghai_intraday_close_rest_unknown`：08-31 10:00 → 期望 08-28 / fresh；15:00 → 期望 08-31 / stale；周六 08-29 → 08-28 / fresh；`as_of_today=2026-09-07` → unknown。假日路径读了执行者 `test_weekend_and_holiday_and_unknown_calendar`（把 08-31 标 holiday → 期望 08-28），未机械重跑。

应用后：正式日历仍止于 2026-08-31 时，行业时效会 `unknown`。这是设计，不是误用日K。

### P2-4 H5-only 实际 URL 无备用 — **closed（roll 路径）**

roll 传 `h5_only=True`。hosts 只留 `https://emdatah5.eastmoney.com/dc/ZJLX/getDBHistoryData`（L50、L708–709、L1384–1391）。默认 `h5_only=False` 仍 4 host。

本轮 `test_h5_only_one_url_no_fallback`：失败只打 1 个 H5 URL，无 push2。真实东财 JSON 仍未打。

### P2-5 API / 类型加载 overlay — **closed**

本轮 conftest 加载 overlay `ext_data` / `fund_flow` / `daily_pipeline` / `pipeline`；`inspect.getfile` 钉死 overlay 绝对路径。overlay `api.ts` 无 `INDUSTRY_FFLOW_WINDOW_CONTRACT`，只有业务可选字段（L4011–4015）。路径证明在测试侧：`tests/vitest.overlay.ts` → `results/vitest-resolved-paths.json`；契约 `api.overlay-contract.test.tsx` 断言 alias 指向 overlay。`api-v02.ts` 磁盘 == baseline == overlay，不进 patch。

执行者证据（只读，未整包复跑）：25 pytest（18:45）、面板 vitest 10（18:45，契约改完后未重跑这 10）、契约 1 + `tsc --noEmit` exit 0（18:47）。覆盖与本轮 8 条修正预期用例对齐，足够关闭本发现。旧独立用例全过不能当新门。

### P2-6 其他已观察 — **仍为观察，不阻断**

persist 异常不按批次吞掉，成功批次留盘；go-stock 遗留不计入 latest H5；前端只在 `kind==='board'` 画时效；概念 90%/5d=1w/Top6 overlay 窗口算法未改。本轮未重开这些要求。

---

## 新增风险（真实影响，不升格为新架构门）

1. 180s 是合作式 deadline，不是已证明的严格墙钟上界。`timeout=8.0` 不能当成在飞 HTTP 的 8 秒硬顶。截止后当前批次仍可能写入。不要据此要求强制 abort httpx，也不要写成 180+8 已有界。真实源阶段评估耗时与部分成功。
2. `/jobs/{id}/cancel` 先把 job 标失败，线程在检查点才停。取消后 `/run` 可建新 job，但第二条 `run_now` 得 `busy`，不重跑日K。
3. overlay 产品模块里的 `_reset_pipeline_guard_for_tests` 是测试夹具。patch 无 `INDUSTRY_FFLOW_WINDOW_CONTRACT` / `pytest` / `__test__` / `TEST_ONLY`。
4. 进程闸在 reload 后丢失；那正是 600s 孤儿 fail 再开新 `run_now` 的场景。
5. 正式日历未覆盖 2026-09-07 时，应用后面板行业时效为 `unknown`，直到日历续上。

---

## 实际测试命令与结果

缓存 / 临时 data / 结果均在 `review/round2/`。未跑旧独立用例当门。未机械复跑执行者全部 25+10+1+tsc。

```text
# 六文件 baseline + 副本 patch/反向 + 无关 hunk
backend/.venv/bin/python review/round2/scripts/check_six_files_and_patch.py
# 见 review/round2/results/six-files-and-patch.txt
# 六文件 match=True；patched==overlay True；reverse 后无关 hunk 保留

# 修正预期 pytest（8）
cd /Users/simon/Trading/one-trading/backend
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=$TASK/review/round2/.pycache \
.venv/bin/python -m pytest \
  $TASK/review/round2/tests/test_round2_expected.py \
  -o cache_dir=$TASK/review/round2/.pytest_cache \
  --basetemp=$TASK/review/round2/.pytest-tmp -q
# ........  8 passed in 0.34s
# 见 review/round2/results/pytest-round2.txt

# 复验时再核六文件磁盘 SHA
# 见 review/round2/results/sha-and-pytest.txt  as_of=2026-09-07 18:56:44 +0800
# 六文件仍 match=True
```

执行者只读证据：`results/pytest.txt` 25 passed；`results/vitest.txt` 11 当时通过（含已作废契约）；18:47 契约 1 passed + `results/tsc-overlay-api.txt` exit 0。本轮抽查了这些测试的断言对象与 overlay 行号，不把“他们全过”当关闭依据。

---

## 六目标主文件仍为磁盘 baseline

| 文件 | 磁盘 == `baseline/SHA256.txt` |
| --- | --- |
| `backend/app/services/free_sources/fund_flow.py` | 是 `87ef3907…548e0b` |
| `backend/app/jobs/daily_pipeline.py` | 是 `7003b64c…0bba58` |
| `backend/app/api/pipeline.py` | 是 `af18dda3…686ed70` |
| `backend/app/services/ext_data.py` | 是 `3b0e5b43…06a8137` |
| `frontend/src/components/SectorFundFlowPanel.tsx` | 是 `4163d9f8…f31a8` |
| `frontend/src/lib/api.ts` | 是 `32055dd6…ba957` |

主树这六份仍无本轮实现。实现只在 overlay。`api-v02.ts` 无逻辑差，不在 patch 内。

---

## 限制

- 未请求真实东财 / 真实 `/api/pipeline/run` / 资金流 window HTTP。
- 未用已登录 Codex 内置浏览器看行业页。
- 未跑盘后真实调度，未写正式 `DATA_DIR`。
- 未对主树 apply，未热重载。
- 未验证线上 `getDBHistoryData` 是否仍为 `data.klines`。
- 未验证真实慢速/持续 HTTP、httpx 各阶段累计、或本地 persist 耗时；未证明严格墙钟上界。
- 供应商回执未核验。

---

## 给总工

重入与 `done` 已关闭。合作式限时实现已验证，严格墙钟上界未证明。可以按现行 `APPLY.md` **准备**主树六文件 patch 应用；真实源阶段评估耗时与部分成功。不另造强制取消架构，不改本轮代码。验收前不要把条目写成 accepted / production / 已修好。权威日志仍只追加，不得用备份覆盖。

MARKET_DASHBOARD_RE_REVIEW_PRECISION_DONE_20260907
