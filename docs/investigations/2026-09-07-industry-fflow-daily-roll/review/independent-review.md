# 行业资金流每日续更 — 独立技术复查

- 日期：2026-09-07
- 复查者：本会话独立审阅（只读主树/overlay；写入仅本目录 `review/`）
- 对象：`/Users/simon/Trading/one-trading/docs/investigations/2026-09-07-industry-fflow-daily-roll/`
- 层：数据台（续更/调度/落盘）+ 用户台（行业窗口时效展示）；未改主树、未改 overlay、未改权威日志、未写正式 `DATA_DIR`
- 结论：**不应按当前 APPLY 进入主树。** 源实现本身有一条调度超时/重入阻断；APPLY 回滚说明也不安全。其余核心数据语义（全集、失败保旧、非空≠到齐、质量门不污染、窗口完整与时效独立、概念规则不动）在 overlay 离线测试上成立。
- **不能宣称生产修好。** 真实东财 / 真实 HTTP / 已登录 Codex 内置浏览器 / 盘后真实运行均未验证。

执行者 12 pytest + 10 vitest 只作背景，不替代本轮判断。本轮另跑 11 条独立 pytest（全过）+ 3 条 overlay 时效 vitest（全过）。

---

## 阻断进入主树的发现

### P1-1 调度超时未隔离：`run_now` 在“完成”之后仍同步续更，10 分钟卡死检测会再开一条完整日K管道

**最小复现 / 断言**

1. overlay 把续更接在 `emit("done", 100)` 之后、`return` 之前，且无总超时。
2. `/api/pipeline/run` 若 running > 600s，只 `job_store.fail()`，**不取消** 仍在 `_long_task_executor` 里的线程，然后 `create()` 可再开一条 `run_now`。
3. 独立测试 `test_second_run_now_redoes_daily_k_while_first_roll_holds_lock`：第一条卡在 H5 fetch 持锁时再开第二条。

**实际结果**

- `quotes["n"] == 2`：第二条把日K `sync_daily_by_quotes` 又跑了一遍。
- 两条结果里有一条 `industry_fund_flow_daily.status == "busy"`：行业锁只挡住续更，挡不住整段日K。
- 进度里先出现 `done`，续更才开始（`test_emit_done_happens_before_industry_roll`）。

**精确位置**

- overlay `daily_pipeline.py` L41–55、L854–860：质量已定后同步调用 `roll_industry_daily_from_h5`，异常才包成 `status=error`。
- overlay `fund_flow.py` L1321–1356、L1388–1416：本地快照全集串行；`limit=120`，`batch_size=8`，`pause_s=0.35`；单请求 `timeout=8.0`，最多 4 个 host；**没有整轮墙钟超时**。
- 主树 `backend/app/api/pipeline.py` L32–56、L68–71：10 分钟后 `job_store.fail(...)` 再 `create`；旧线程继续写盘。
- 主树 `backend/app/jobs/daily_pipeline.py` L1229–1236：盘后 cron 同样同步等完整 `run_now`，无 `timeout` / `max_instances`。

**为何阻断**

128 只 × 4 host × 8s 量级可超过 10 分钟。失败虽不改 `quality`/`daily_days`，但会：

- 让盘后任务/手动管道在已报 100% 后继续占线程；
- 触发“孤儿任务”误杀后 **第二路全日K** 与第一路行业写盘并行。

**修改建议**

- 续更从 `run_now` 热路径拆出：独立 job、独立超时、失败只写 `industry_fund_flow_daily`。
- 或保留挂接但加墙钟超时 + 取消点；`/api/pipeline/run` 的 10 分钟检测不得在续更仍持锁时再开第二条 `run_now`。
- `emit("done")` 必须在全部附属工作结束之后。

### P1-2 APPLY / 回滚说明会抹掉无关变化，当前按该说明应用/回滚不安全

**事实**

- 四份目标源码 **此刻仍等于** `baseline/SHA256.txt`（见文末）。`patch --dry-run` 打在这四份的 **副本** 上成功，打完后 SHA 与 overlay 一致。
- 两份权威日志 **已经相对 15:50 备份漂移**，不能当“还等于基线”：
  - `docs/data-platform-development-log.md` 磁盘 `5d16b0be…` ≠ 备份 `f511f509…`
  - `docs/workbench-development-log.md` 磁盘 `03e438e3…` ≠ 备份 `842c90d7…`
- `APPLY.md` L25 仍允许“按文件把 overlay 整份拷进主树”。
- `APPLY.md` L31–35 回滚写的是：用 `/Users/simon/备份/codex/20260907-154837-industry-fflow-daily-roll/files/` **覆盖四个绝对路径**，并用同目录备份 **覆盖两份开发日志**。

**为何阻断**

主树已有大量脏改，且日志已继续变化。整文件 copy / 旧备份覆盖会丢掉本轮之外的源码和日志。`patch` 预检今天能过，不表示明天四文件仍无漂移，更不表示回滚可以整文件倒回去。

**合理方案（不要现在执行）**

1. 再核四文件 SHA 是否仍等于本次 baseline。
2. `patch --dry-run -p1` 预检本轮 `patches/phase-b-industry-fflow-daily-roll.diff`。
3. 有漂移：三方处理（当前磁盘 / baseline / overlay），禁止整文件覆盖。
4. 应用：只打本轮 patch（不要 copy overlay 整文件，除非 SHA 仍精确等于 baseline）。
5. 回滚：只 `patch -R` 撤本轮 diff；**禁止** 用 15:50 备份覆盖源码或权威日志。
6. 热重载：改 `backend/` 前单独授权停/启 worker，不在本复查执行。

---

## 非阻断限制与次要缺陷

### P2-1 最新日到齐用“全库最大日期”，快照外遗留新日期会把全集续更判失败

- 位置：overlay `fund_flow.py` `_industry_h5_latest_coverage` L1230–1237。
- 复现：`test_leftover_newer_date_on_non_snapshot_code_poisons_latest_complete`。
- 结果：快照只有 BK0001/BK0002 且 H5 都成功落到 2026-08-31，但盘里有 BK9999@2026-09-02 时，`latest_data_date=2026-09-02`，`latest_day_complete=False`，`status=incomplete_latest_day`，`ok=False`。
- 只读看正式数据：当前 128 只快照与日线代码一致，最新东财日 2026-08-31 到齐，**此刻没有这条脏数据**。仍应改成“快照全集自己的最大东财日”。

### P2-2 分区合并按 code 保旧，但文件写入不是原子的，读路径不取续更锁

- `persist_board_daily_history`（overlay `fund_flow.py` L932–960）按日调用 `write_ext_parquet`，合并 key 是 `code`（主树 `ext_data.py` L381–388、L436–447），失败拒绝整日覆盖。这保护了同日其他代码和未写入的更旧分区。
- 但 L447 是 `df.write_parquet(out_path)`，**不用** `atomic_write_parquet`。`test_write_ext_parquet_is_not_atomic` 断言成立。
- 续更锁只挡第二路 roll，挡不住窗口 API 读到半截 parquet。这是既有写路径，本轮把它放到盘后全行业重写上放大了。
- 建议：时序分区改 `atomic_write_parquet`；读窗口最好避开正在写的分区或接受短失败。

### P2-3 时效不看收盘时刻；交易日盘中会把“昨日已齐”标成已陈旧

- 位置：overlay `fund_flow.py` `assess_industry_window_freshness` L1167–1179；日历有 `close_time` 但未用。
- `test_intraday_trading_day_marks_yesterday_complete_as_stale`：2026-08-31 开市、数据截止 08-28、窗口完整 → `freshness_status=stale`。
- `test_weekend_uses_last_open_day_as_fresh`：周六日历覆盖且 `is_open=false` → 期望上周五，对齐则 `fresh`。
- `test_holiday_weekday_uses_previous_open_day`：周一放假 → 期望上一开市日。
- 日历 `max(all_days) < today` → `unknown`（与需求一致）。正式日历只到 **2026-08-31**，今天 2026-09-07，**应用后行业面板会显示无法确定**，直到日历续到当日。这是设计如此，不是误用日K。
- 产品若要“最新完整交易日是否已到齐”，盘中应期望上一开市日，或在 `close_time` 前不要把当日当定期望日。

### P2-4 声称 H5-only，实现仍回退 push2his / push2delay / push2

- overlay `fund_flow.py` L704–705：`prefer_h5=True` 只是把 `getDBHistoryData` 放到最前，随后仍打另外三个 host。
- `allow_local_fallback=False` 与 `source==eastmoney_fflow_day` 过滤成立（独立测试有断言）。不是混 `stock.db`，但不是严格只打 H5。
- 真实 H5 JSON 本轮未打。主树历史测试按 `data.klines` 解析；若线上形态变了，会落到备用 host 或整码失败。

### P2-5 执行者测试边界够用，但没覆盖本轮阻断点

- conftest 确实用 overlay 替换 `sys.modules`（本轮 `inspect.getfile` 钉死 overlay 绝对路径；主树 `fund_flow.py` **没有** `roll_industry_daily_from_h5`）。
- 网络只 mock `fetch_board_daily_history`，落盘走真 `persist`/`write_ext_parquet`，这是对的。
- 未覆盖：旧日回复、快照外新日期、盘中/周末/假日时效、`write_ext_parquet` 非原子、`run_now` 重入日K、APPLY 漂移。
- vitest 只 alias 面板，`@/lib/api` 仍是 **主树** `api.ts`。overlay `api.ts` 只加可选字段，运行时靠 JSON 多字段，风险低，但类型契约没有 overlay 加载验证。

### P2-6 其他已观察、不单独阻断

- persist 异常不按批次吞掉，会整轮上抛成 pipeline `status=error`；已成功批次留盘。失败保旧对“未写入日期”仍成立。
- 正式 `ext_fund_flow_bk_daily` 混有 `go_stock_local_snapshot`（2026-07-19、2026-08-02，256 行）。最新日 2026-08-31 全是 `eastmoney_fflow_day`。覆盖函数会忽略 go-stock；120 日窗口重写会按 code keep-last 盖掉重叠日的 go-stock 值，更旧分区保留（`test_go_stock_leftover_not_counted_as_latest_h5_coverage`）。
- 前端只在 `kind==='board'` 画时效行；概念 90% / 5 天=1 周 / Top 两端规则 overlay 未改窗口算法，执行者测试与本轮未复跑的那几条仍指向同一 overlay 函数。

---

## 已核对且成立的行为（overlay，离线）

| 要求 | 结论 | 证据 |
| --- | --- | --- |
| 本地行业快照全集，不走 Top20 | 成立 | overlay L1286–1299；执行者 `test_roll_selects_all_local_industry_codes_not_top20` |
| H5 优先、禁止 go-stock fallback | 调用参数成立；host 非严格 H5-only | L1326–1337；本轮 old-day 测试断言 kwargs |
| 串行分批、线程锁+flock 防重入 | 成立，但锁只管续更 | L1388–1416；busy 在双重 `run_now` 测试中出现 |
| 同源按日分区合并、保护长历史 | 合并语义成立 | 执行者 150 日保留；`write_ext_parquet` 按 code keep-last |
| 失败保旧 / 部分成功 / 幂等 | 成立 | 执行者失败/部分批次/幂等；本轮旧日回复改值不丢日 |
| 非空 ≠ 最新日到齐 | 成立 | 执行者 `incomplete_latest_day`；见 P2-1 的遗留日期坑 |
| 日K 质量结论不被污染 | 成立 | 执行者爆炸路径；本轮 `partial` 仍 `quality.ok=True` |
| 窗口完整与时效独立 | 成立 | 完整+stale / 完整+unknown |
| 日历不覆盖 → unknown | 成立 | 不用 kline 目录；正式日历未到 09-07 会 unknown |
| 仅行业前端展示时效 | 成立 | overlay 面板 L352–354；3 条 freshness vitest |
| 概念 90% / 5=1周 / Top 两端 | overlay 未改判定公式 | 执行者对应 3 条；本轮未复跑全套 |

---

## 覆盖范围与剩余风险

**本轮做了**

- 只读核四文件磁盘 SHA（不用 HEAD）。
- 读 README / APPLY / REVIEW / overlay / baseline / 整包 diff / 执行者测试。
- 沿 `run_now` → roll → fetch → persist → `write_ext_parquet` → `aggregate_board_window` → 面板契约。
- 在 `review/` 用已有 `.venv` / pnpm 做离线针对测试与 sandbox `patch`（未打主树）。
- 只读查看正式 `DATA_DIR` 日历与行业日线现状（未写）。

**明确未做，不能写成已修好**

- 未请求真实东财 / 真实 HTTP。
- 未用已登录 Codex 内置浏览器看行业资金流页。
- 未跑盘后真实调度，未写正式 `DATA_DIR`。
- 未应用 patch，未重启/热重载，未部署。
- 未验证 H5 `getDBHistoryData` 线上 JSON 是否仍是 `data.klines`。

---

## 四文件基线是否漂移

| 文件 | 磁盘 vs `baseline/SHA256.txt` |
| --- | --- |
| `backend/app/services/free_sources/fund_flow.py` | **未漂移** `87ef3907…548e0b` |
| `backend/app/jobs/daily_pipeline.py` | **未漂移** `7003b64c…0bba58` |
| `frontend/src/components/SectorFundFlowPanel.tsx` | **未漂移** `4163d9f8…f31a8` |
| `frontend/src/lib/api.ts` | **未漂移** `32055dd6…ba957` |

主树这四份 **没有** 本轮实现；实现只在 overlay。`patches/phase-b-industry-fflow-daily-roll.diff` 打在四文件副本上后与 overlay SHA 一致。

权威日志 **已漂移**（见 P1-2），APPLY 不得用备份覆盖它们。

---

## 实际测试命令与结果

工作目录与缓存均在本任务 `review/`（`PYTHONDONTWRITEBYTECODE=1`）。

```text
# 基线 + sandbox patch（未改主树）
backend/.venv/bin/python review/scripts/check_baseline_and_patch.py
# 结果：四文件未漂移；日志漂移；dry-run/apply 副本成功；patched==overlay
# 见 review/results/baseline-and-patch.txt

# 独立 pytest 11
cd backend && .venv/bin/python -m pytest \
  $TASK/review/tests/test_independent_findings.py \
  -o cache_dir=$TASK/review/.pytest_cache \
  --basetemp=$TASK/review/.pytest-tmp -q
# ...........  11 passed in 0.45s
# 见 review/results/independent-pytest.txt

# overlay 时效 vitest 3（沿用 isolation config，只跑 freshness 文件）
cd frontend && pnpm exec vitest run --config $TASK/tests/vitest.overlay.ts \
  $TASK/tests/frontend/SectorFundFlowPanel.industry-freshness.test.tsx
# 3 passed
# 见 review/results/independent-vitest.txt
```

执行者原 12+10 本轮未整包复跑；不作为通过依据。

---

## 模型配置与返回证据

- 用户要求：本会话 Cursor **Grok 4.6 / Extra High**，不建子 agent、不转交其他模型。
- 配置显示：按该要求在本会话执行。
- 供应商回执 / 实际返回 model id / effort 票据：**拿不到，未核验。**
- 未调用 Superpowers，未改主树/服务/全局配置。

---

## 给总工

先修 P1-1（续更脱离 `run_now` 热路径或加超时且禁止第二条全日K），并改写 APPLY/回滚为“基线 SHA + 本轮 patch / 反向 patch”。P2 可同轮或随后。在那之前不要把 overlay 打进主树。
