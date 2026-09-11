# 2026-09-09 行业资金流正式接入 + 真实续更

- as_of：2026-09-09 14:29 +0800（文档P2收尾：权威日志状态/回滚/调度句；代码/数据未因本条重跑或回滚）
- 执行端：文档P2会话 Cursor。要求 Grok 4.6 Extra High。供应商/模型回执 **未核验**（配置不等于回执）。
- 主台：数据台。次台：用户台。
- 本文件是本轮实施记录，不是整数据台验收。独立技术复核已完成，见 §7。
- 交付修复回执：`docs/investigations/2026-09-09-industry-fflow-live/delivery-repair/receipt.md`。本阶段新 artifact：`acceptance/closure.md`。

## 可独立核验的结论

- **真实 H5 最大日：`2026-09-08`**。不是 8/31 旧响应，也不是本地 fallback。
- **正式行业日线全量：128/128 `eastmoney_fflow_day` 覆盖 `date=2026-09-08`**。缺码 0。一次合作式 180s 内完成（42.8s），未二次从头重跑。
- **5 日窗已前移**到 `2026-09-02`～`2026-09-08`，满窗 128/128。
- **63 日窗已前移**到 `2026-06-11`～`2026-09-08`，满窗 128/128。
- **备份**：脏树起点 `/Users/simon/备份/codex/20260909-131435-industry-fflow-live`；交付修复 `/Users/simon/备份/codex/20260909-134048-industry-fflow-live-delivery-repair`；文档P2改前 `/Users/simon/备份/codex/20260909-142907-industry-fflow-docs-p2`
- **回滚（本会话未执行）**：不要用备份 `files/` 整文件覆盖六源码——那会覆盖本轮之后其他任务的有效写入。应以本轮相对脏树起点的 `evidence/diffs/*.diff` 生成反向补丁，先 dry-run；冲突或当前哈希已不等于本轮交付版本则停止，并留存当前状态。行业日线只回滚 `data/ext_data/ext_fund_flow_bk_daily/`（不要整份 `data/`），同样先校验当前哈希仍等于本轮交付版本；存在后续有效写入则停，只回滚本轮变化。
- **运行面**：后端 `--reload` 父进程 PID `3510`（05:20:24），**当前 worker PID `91841`（13:17:10，晚于本轮后端 mtime）**；前端 Vite PID `3528`（05:20:24）已在 `3011` 吐出新面板源。本阶段未重启。
- **未观察**真实自然盘后触发。保留现有调度逻辑；配置默认 15:30 / 注释 15:35 不一致，不能冒充已观察的实际调度。受控路径是 `roll_industry_daily_from_h5`（`run_now` 质量门后调用的同一函数），不是全日 K。
- **HTTP**：执行端未登录 `GET /api/free/fund-flow/boards/window` = **401**「未登录或会话已过期」（未登录事实）。总工 IAB 05:26:04 UTC 已登录浏览器 + 已登录 CDP 观测（2026-09-09 05:37:04 UTC）同端点 **200** / `ok=true`，5/63 日均 128 满窗。未关认证，未打印 token。详见 §5.1 / §5.2。
- **时效**：日历仍止于 `2026-08-31`，行业窗 `freshness_status=unknown`。这是设计，不是接入失败。
- 当前范围 **已** `accepted`（六源码 + 正式行业受控续更 + 当前 5/63 UI/API 技术验收）。不是 `production`。文档P2本阶段修正待独立定点复查。

## 坐标

| 项 | 值 |
| --- | --- |
| checkout | `/Users/simon/Trading/one-trading` `main@31216dda527cd4ec177b9cbf6fd1c524dbadbe82` dirty |
| DATA_DIR | `/Users/simon/Trading/one-trading/data`（`.env` `DATA_DIR=./data`；worker 打开该目录日志/Parquet） |
| 调度 | 保留现有 `_run_tracked` + `try_acquire_run_slot` / `reap_stale`。配置默认 15:30 / 注释 15:35 不一致；未观察真实自然触发 |
| 备份 | 脏树起点 `/Users/simon/备份/codex/20260909-131435-industry-fflow-live`；交付修复 `/Users/simon/备份/codex/20260909-134048-industry-fflow-live-delivery-repair`；文档P2改前 `/Users/simon/备份/codex/20260909-142907-industry-fflow-docs-p2` |
| 证据 | `docs/investigations/2026-09-09-industry-fflow-live/evidence/` |
| 测试 | 既有 `evidence/pytest.txt`「14 passed, 1 warning in 4.88s」仍在。控制器 `ecf15990` 已用 `/tmp/industry-fflow-20260909-controller-repair-v3` 重跑 `14 passed in 4.20s`，exit 0。本阶段未再跑 pytest |
| 交付修复 | `docs/investigations/2026-09-09-industry-fflow-live/delivery-repair/` |

未 reset/stash，未覆盖整份文件，未把 9/7 overlay 整文件 copy 进主树。四份已漂移源码只迁行业 hunk，保留 job slot / reap_stale 与现有调度逻辑。

## 1. 最小主树集成

`fund_flow.py` 与 `SectorFundFlowPanel.tsx` 在脏树起点仍等于 9/7 baseline，打了已审查 patch，再补超时续跑（缺最新 H5 日的码优先，避免 180s 反复从头饿死尾部）。

另外四份相对 9/7 已漂移，**没有**直接打旧 patch：

- `pipeline.py`：只在 `cancel_job` 增加 `request_industry_roll_cancel()`。`reap_stale` + `try_acquire_run_slot` 不动。
- `daily_pipeline.py`：质量门决定后、`emit("done")` 前调用行业 roll。不包第二套 `_PIPELINE_GUARD`。
- `ext_data.py`：`write_ext_parquet(..., atomic=False)` 默认不变；行业 persist 传 `atomic=True`。保留现有 merge / `_invalidate_ext_derived`。
- `api.ts`：只给 `FundFlowWindowResponse` 增加时效可选字段。

行业路径：本地 `ext_fund_flow_bk` 快照全集 → `fetch_board_daily_history(h5_only=True)` → 只落 `eastmoney_fflow_day` → date+code 合并 + 原子替换。失败保旧。与日 K `quality` 分离。概念 90% / 5 天=1 周 / Top6 两端未改。

## 2. 隔离真实源

隔离 `DATA_DIR`：`docs/investigations/2026-09-09-industry-fflow-live/canary-data`

代表码（此前 5/63 两端 + 现 5 日一端）：元件 `BK0459`、电池 `BK1033`、种植业 `BK1261`、半导体 `BK1036`、航运港口 `BK0450`。

5/5 真实 H5：`n=120`，`2026-03-18`～`2026-09-08`，`source=eastmoney_fflow_day`，`unit_amount=yuan`，host 仅 `https://emdatah5.eastmoney.com/dc/ZJLX/getDBHistoryData`。未把旧响应说成最新成功。

隔离 roll：5/5 ok，最新日 2026-09-08 到齐，新分区 `09-01/02/03/04/07/08`。见 `evidence/canary-live-fetch.json`、`evidence/canary-roll.json`。

## 3. 正式 128 只续更

`roll_industry_daily_from_h5(/Users/simon/Trading/one-trading/data)`，默认 180s。

- PASS1：`ok=True`，fetched=128，skipped=0，failed=0，`latest=2026-09-08`，complete=True，42.796s。
- 未触发第二遍。
- 新分区：`2026-09-01`～`2026-09-04`、`2026-09-07`、`2026-09-08`。
- 分区跨度仍从 `2026-03-02`（11 行保留）到 `2026-09-08`（128 行）。
- `go_stock_local_snapshot` 残片 256 行仍在；概念日线仍止于 `2026-08-31`。

见 `evidence/official-pre-roll.json`、`evidence/official-roll.json`。

## 4. 回读与测试

代表码独立加总（全窗，不只 Top6）见 `evidence/independent-sums-full.json`。与 window API Top6 重叠项逐字段相等（元件 5 日 +60.01 亿；半导体 63 日 -3182.35 亿）。

离线测试（主树模块，不是 overlay）：14 passed。覆盖全集、5/63 前移、失败保旧、超时续跑尾部、原子写失败保旧、H5-only、盘中/日历 unknown、概念规则、`done` 在行业后、行业失败不改 `quality`、现有 job slot/reap_stale。

前端：`tsc --noEmit` exit 0；既有 `SectorFundFlowPanel.history.test.tsx` 7 passed。Vite `3011` 已返回带 `industryWindowFreshnessLine` 的面板源。

故障/取消/并发只在隔离 pytest，未对正式 data 造故障。

## 5. HTTP / 页面（给 Codex 内置浏览器）

未开系统浏览器或 Cursor 浏览器。

| 项 | 值 |
| --- | --- |
| 服务 | 后端 `http://127.0.0.1:3018` worker `91841`；前端 `http://127.0.0.1:3011` Vite `3528` |
| 鉴权 | 执行端未登录 curl **401**。总工已登录 HTTP **200**（§5.2）。认证未关。 |
| 行业页 | `http://127.0.0.1:3011/industry-analysis`（`SectorFundFlowPanel kind=board`） |
| 首页 | `http://127.0.0.1:3011/` 资金流模块 `kind=both` |
| 概念页 | `http://127.0.0.1:3011/concept-analysis` 不应出现行业时效行 |
| 预期行业窗 | 5 日 `2026-09-02`～`2026-09-08` 满窗 128/128；文案 `数据截止 2026-09-08 · 无法确定 · 窗口完整`（日历未覆盖今日） |
| 预期 5 日两端 | 流入通信设备 / 元件；流出半导体等 |
| 预期 63 日 | `2026-06-11`～`2026-09-08` 满窗；流入种植业；流出半导体 |
| API | 已登录后 `GET /api/free/fund-flow/boards/window?days=5&top=6` 与 `days=63` |

### 5.1 总工 IAB 实际观测（用户可见结果，2026-09-09）

总工在 Codex 内置浏览器验收，时间 **2026-09-09 05:26:04 UTC**（13:26:04 +0800）。URL `http://127.0.0.1:3011/`，标题 `one-trading · Quant Terminal`。页面已有正常登录权限；本轮未改认证。

只记用户可见结果。**不替代**上文执行端的真实 H5 采样、正式回读、未登录 HTTP 401、worker 身份，以及 `evidence/independent-sums-full.json` 独立加总。未因本条重抓源或重跑测试。

| 面 | 总工看到的结果 |
| --- | --- |
| 行业 5 日 | `2026-09-02`～`2026-09-08`；覆盖 128/128；满窗 128/128 |
| 行业时效行 | 数据截止 9/8 · 无法确定 · 窗口完整 |
| 行业 5 日两端 | 通信设备 **+61.60 亿**；半导体 **-217.53 亿** |
| 行业「1 个季度」 | 实际切换下拉后：63 日 `2026-06-11`～`2026-09-08`；同为 128/128 满窗 |
| 行业 63 日两端 | 种植业 **+24.14 亿**；半导体 **-3182.35 亿** |
| 概念 5 日（对照，未改） | 仍为 `2026-08-25`～`2026-08-31`；满窗 503/504 |

### 5.2 总工已登录 HTTP（CDP 只观测响应，2026-09-09 05:37:04 UTC）

总工在 Codex IAB 原 tab1 / browser2 观测。主页 UI 已切 5 日与「1 个季度」。通过 CDP **只观测响应**；不取 / 不打印 token，不改认证。本条补齐「已登录 HTTP」门。执行端未登录 401 仍是不同身份的历史事实，见 `evidence/http-status.txt` 与 `evidence/http-window.json`。

未因本条重抓源、重跑测试、重开浏览器。下列数字由总工提供；与 `evidence/official-roll.json` 的 `window5` / `window63` Top6 两端 `code`+`main_net` 一致。

`GET http://127.0.0.1:3011/api/free/fund-flow/boards/window?days=5&top=6`

- 200，`ok=true`，`2026-09-02`～`2026-09-08`
- `requested` / `trading_days` = 5
- `full` / `covered` / `snapshot` = 128，`missing` = 0，`window_complete=true`
- `source=ext_fund_flow_bk_daily`，`data_as_of=2026-09-08`
- `freshness=unknown`，`calendar=false`

12 项（`code`, `main_net` 元）：

| code | main_net |
| --- | ---: |
| BK0448 | 6159681280 |
| BK0459 | 6001295616 |
| BK0727 | 3256390672 |
| BK0481 | 1992616016 |
| BK1034 | 1595884608 |
| BK1231 | 1458051088 |
| BK1036 | -21752673536 |
| BK0735 | -7917515360 |
| BK1033 | -6996499056 |
| BK1238 | -6701752768 |
| BK0473 | -5235561872 |
| BK1038 | -4919745632 |

`GET http://127.0.0.1:3011/api/free/fund-flow/boards/window?days=63&top=6`

- 200，`ok=true`，`2026-06-11`～`2026-09-08`
- `full` / `snapshot` = 128
- `freshness=unknown`

12 项（`code`, `main_net` 元）：

| code | main_net |
| --- | ---: |
| BK1261 | 2413849499 |
| BK1256 | 459873697 |
| BK1045 | 424516678 |
| BK1249 | 322527702 |
| BK1274 | 300768752 |
| BK0482 | 48889184 |
| BK1036 | -318235362560 |
| BK0448 | -219514637056 |
| BK0459 | -92431463936 |
| BK1038 | -81439874416 |
| BK1033 | -78520394288 |
| BK1037 | -74580737024 |

## 6. 权威文件

- 数据台开发日志唯一条：`ext_fund_flow_bk_daily_industry_roll_live_20260909` → `accepted`（仅当前受控续更+5/63 窗；不是 production）
- 用户台开发日志唯一条：`industry_fundflow_daily_roll_live_20260909` → `accepted`（仅当下可见窗；不是 production）
- 计划：`D-R-05` 不改（自然调度依赖仍有效）。

## 剩余门

- 日历续到当日后时效才能离开 `unknown`。本轮不扩修日历。
- 未来自然盘后 `_run_tracked` → `run_now` 尚未观察。配置默认 15:30 / 注释 15:35 不一致，已知后续核对点；本阶段不改偏好、源码注释或运行调度。
- 概念正式写入与长周期不在本轮。整台未完成不可混写。
- 独立技术复核已完成（§7）。文档P2本阶段修正待独立定点复查。

## 7. 独立技术复核（摘要，不复制全文）

根据桥接 `finish_report` 归档，不是原 review 全文。

- task `9cd3cd22-b5e1-4262-950d-29300d799fed`；全新 session `75c6b767-3e2c-422d-ab3b-fcba37faf477`
- 产品 P1 无。P2 仅权威日志（本阶段修正：数据台过时「已登录浏览器未做」+ 整文件覆盖回滚句）。
- 正式 134 分区 `2026-03-02`～`2026-09-08`；9/8、5 日、63 日各 128/128；date+code 重复 0。
- `go_stock` 256 行（7/19、8/2）、3/2 长历史、snapshot/calendar/config 与改前备份 SHA 匹配。
- 独立直接 Parquet 逐日求和与总工 HTTP200 12+12 项 `main_net` 全部精确相等。
- 6/19 属日历休市；worker 91841@13:17:10 晚于源码。
- 原 14 pytest / tsc 日志可见（`evidence/pytest.txt`「14 passed, 1 warning in 4.88s」；`tsc_exit=0`）。无单独 vitest 日志，不冒充实测。
- 控制器 `ecf15990-52f4-48f8-ba7f-1d949aba4285` `checks.log`：`14 passed in 4.20s`，exit 0。独立 review 未重跑不是漏测，区分来源即可。

## 相对脏树起点的六文件哈希

见 `evidence/SHA256-six-files.txt` 与 `evidence/diffs/`。当前：

| 文件 | 当前 sha256 |
| --- | --- |
| `fund_flow.py` | `304ec3ff2d0a5a6d0175c641ff64d334e50f412d5ad670b1dcb9fa4b2100aa4c` |
| `daily_pipeline.py` | `4a7f7085c034d9f9043b5ba0b9e44dcf9cbb074da570582d1ce3eaef8a011652` |
| `pipeline.py` | `aaa2e1cd391144bb5baa4f8f70aeb5f611e94c67540286d30a5c408b3d239be7` |
| `ext_data.py` | `1fb7425545c5f980633afe5cdb8d4bbef65b1f0a6889659701212503c9c3a6de` |
| `SectorFundFlowPanel.tsx` | `f79dd28a35f38a7e94d909a6bfed93dbde51a65f0f87eb0f5b9e98468ad13f28` |
| `api.ts` | `1d21603da3698d7542e7f2f6c6b254d59408d216e657e8597eb4037e896d5db2` |
