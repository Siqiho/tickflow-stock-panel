# 2026-09-09 industry-fflow-live 交付修复回执

- as_of：2026-09-09 13:41 +0800
- 阶段：fix / delivery-repair。不恢复旧会话 d13c6e88-a978-436e-b295-e576313025e9。
- 执行端：本会话 Cursor。要求 Grok 4.6 Extra High。供应商/模型回执 **未核验**。
- 主台：数据台。次台：用户台。
- 本文件是交付修复证据，不是独立复查，也不是 `accepted` / `production`。
- 本阶段只写本目录与已授权的 `implementation.md` / 备份目录。未改六产品源码、tests、evidence、业务 data、bridge、全局。未装依赖。未重启。未重跑 H5 / 正式 data。未开浏览器。未执行回滚。

## 1. symlink 清理

Codex 只读定位经本会话复核：旧 root 内全部 11 个 symlink 都在这一个本任务临时目录，且都是 pytest 自动 `*current` → 各自临时测试目录。

| 项 | 值 |
| --- | --- |
| 精确路径 | `/Users/simon/Trading/one-trading/docs/investigations/2026-09-09-industry-fflow-live/.pytest-tmp` |
| 自身 | 普通目录，不是 symlink |
| 顶层 | 11 个 `*0` 目录 + 11 个 `*current` 绝对路径 symlink |
| 移动前 root symlink 数 | 11，全部在 `.pytest-tmp` 内 |
| 未跟随 | `os.walk(..., followlinks=False)` 核 target；`os.rename` 移动目录 inode |
| 未覆盖 | `/Users/simon/.Trash` 下先 `os.mkdir` 独占唯一名；目标已存在则停止 |
| 未永久删除 | 未 `rm` / 未清空废纸篓 |

11 个 `*current` → target（均在同一 `.pytest-tmp` 内，target 均为对应 `*0` 目录）：

| symlink | target |
| --- | --- |
| `test_atomic_tmp_and_replace_facurrent` | `.../.pytest-tmp/test_atomic_tmp_and_replace_fa0` |
| `test_concurrent_lock_and_histocurrent` | `.../.pytest-tmp/test_concurrent_lock_and_histo0` |
| `test_done_after_roll_timeout_ccurrent` | `.../.pytest-tmp/test_done_after_roll_timeout_c0` |
| `test_freshness_calendar_and_cocurrent` | `.../.pytest-tmp/test_freshness_calendar_and_co0` |
| `test_old_day_reply_and_leftovecurrent` | `.../.pytest-tmp/test_old_day_reply_and_leftove0` |
| `test_roll_incomplete_batch_andcurrent` | `.../.pytest-tmp/test_roll_incomplete_batch_and0` |
| `test_roll_keeps_old_rows_when_current` | `.../.pytest-tmp/test_roll_keeps_old_rows_when_0` |
| `test_roll_new_day_moves_5_and_current` | `.../.pytest-tmp/test_roll_new_day_moves_5_and_0` |
| `test_roll_selects_all_local_incurrent` | `.../.pytest-tmp/test_roll_selects_all_local_in0` |
| `test_timeout_resume_fetches_tacurrent` | `.../.pytest-tmp/test_timeout_resume_fetches_ta0` |
| `test_top6_heads_unchangedcurrent` | `.../.pytest-tmp/test_top6_heads_unchanged0` |

Trash 去向（唯一名，不覆盖）：

- 容器：`/Users/simon/.Trash/industry-fflow-live-pytest-tmp-20260909T134040+0800-pid7299`
- 内容：`.../pytest-tmp`（原目录 inode；内仍有 11 个 symlink 条目，绝对 target 指向已搬走前的旧路径，这是预期，本会话未改写链接）

验证：

- 原路径 `.../2026-09-09-industry-fflow-live/.pytest-tmp`：`exists=False`，`lexists=False`
- Trash 容器与 `pytest-tmp` 子目录存在，且都不是 symlink
- 旧 root 再走 `os.walk(followlinks=False)`：`OLD_ROOT_SYMLINK_COUNT=0`
- 未按旧猜测动 `node_modules`

## 2. 原测试日志 / 证据仍在

| 路径 | 状态 |
| --- | --- |
| `tests/test_industry_fflow_live.py` | 仍在，非 symlink |
| `tests/helpers.py` / `tests/conftest.py` | 仍在 |
| `evidence/pytest.txt` | 仍在；正文 `14 passed, 1 warning in 4.88s`。本会话未重跑 |
| `evidence/tsc.txt` | 仍在；`tsc_exit=0`。本会话未重跑 |
| `evidence/*.json` / `evidence/diffs/` / `evidence/SHA256-six-files.txt` | 未改 |
| `.pytest_cache/` | 仍在；无 symlink。未授权故未移 |

以后 pytest `basetemp` 必须在 `/tmp/industry-fflow-20260909-*`。artifact 内绝不再产生 symlink。控制器将用新 `/tmp` 目录重跑 14 pytest；不必重复已通过的 7 vitest 及 tsc。本会话未跑这 14 条，也未跑 vitest。

本目录未见单独 `vitest` 日志文件；「7 passed」只存在于 `implementation.md` 既有陈述。本会话不把它写成新的执行端实测。

## 3. 六产品文件 SHA（只读比对）

对照 `evidence/SHA256-six-files.txt`（as_of=2026-09-09T13:24:25+08:00）。本会话重算 live SHA，**六份全部 MATCH**。未改这些文件。

| 文件 | live sha256 = 证据 sha256 |
| --- | --- |
| `backend/app/services/free_sources/fund_flow.py` | `304ec3ff2d0a5a6d0175c641ff64d334e50f412d5ad670b1dcb9fa4b2100aa4c` |
| `backend/app/jobs/daily_pipeline.py` | `4a7f7085c034d9f9043b5ba0b9e44dcf9cbb074da570582d1ce3eaef8a011652` |
| `backend/app/api/pipeline.py` | `aaa2e1cd391144bb5baa4f8f70aeb5f611e94c67540286d30a5c408b3d239be7` |
| `backend/app/services/ext_data.py` | `1fb7425545c5f980633afe5cdb8d4bbef65b1f0a6889659701212503c9c3a6de` |
| `frontend/src/components/SectorFundFlowPanel.tsx` | `f79dd28a35f38a7e94d909a6bfed93dbde51a65f0f87eb0f5b9e98468ad13f28` |
| `frontend/src/lib/api.ts` | `1d21603da3698d7542e7f2f6c6b254d59408d216e657e8597eb4037e896d5db2` |

mtime 仍为 13:15:57–13:16:52。相对脏树起点 diff 仍在 `evidence/diffs/`。

## 4. 已验证 128 行业 9/8 与 5/63 窗（只读，未重跑）

正式目录只列分区，未写 data，未装 pyarrow / 未读 parquet 行：

- `data/ext_data/ext_fund_flow_bk_daily/timeseries`：134 个 `date=` 分区
- min=`2026-03-02`，max=`2026-09-08`
- 存在 `2026-09-01/02/03/04/07/08`；`date=2026-09-08/part.parquet` size=9104
- 5 日窗日期 `2026-09-02/03/04/07/08` 分区齐全

`evidence/official-pre-roll.json`：roll 前 max=`2026-08-31`，`has_0908=false`。

`evidence/official-roll.json`：

- PASS1 `ok=true` fetched=128 skipped=0 failed=0 `latest=2026-09-08` complete=true 42.796s
- `source_days["2026-09-08"]`：n/codes=128，`eastmoney_fflow_day`
- window5：`2026-09-02`～`2026-09-08` complete=true fresh=unknown calendar_covers=false data_as_of=2026-09-08
- window63：`2026-06-11`～`2026-09-08` complete=true

`evidence/independent-sums-full.json`：5 日窗 5 个交易日 `full_count_128=128`；63 日窗 63 个交易日 `full_count_128=128`。

## 5. 总工已登录 HTTP（本会话未观测，只记录）

观测者：总工。时间：2026-09-09 05:37:04 UTC（13:37:04 +0800）。Codex IAB 原 tab1 / browser2。主页 UI 已切 5 日与季度。CDP **只观测响应**；不取 / 不打印 token，不改认证。

执行端未登录 401 仍是不同身份的历史事实：`evidence/http-status.txt` 与 `evidence/http-window.json` 均为 boards5/boards63/concepts5 = 401「未登录或会话已过期」。已登录 HTTP 这一门现在由总工观测补齐，全文见 `implementation.md` §5.2。

`GET http://127.0.0.1:3011/api/free/fund-flow/boards/window?days=5&top=6`

- 200，`ok=true`，`2026-09-02`～`2026-09-08`
- requested / trading_days=5
- full / covered / snapshot=128，missing=0，window_complete=true
- source=`ext_fund_flow_bk_daily`，data_as_of=9/8
- freshness=unknown，calendar=false
- 12 项 (code, main_net 元)：BK0448 6159681280；BK0459 6001295616；BK0727 3256390672；BK0481 1992616016；BK1034 1595884608；BK1231 1458051088；BK1036 -21752673536；BK0735 -7917515360；BK1033 -6996499056；BK1238 -6701752768；BK0473 -5235561872；BK1038 -4919745632

`GET .../boards/window?days=63&top=6`

- 200，`ok=true`，`2026-06-11`～`2026-09-08`，full/snapshot=128，freshness=unknown
- 12 项：BK1261 2413849499；BK1256 459873697；BK1045 424516678；BK1249 322527702；BK1274 300768752；BK0482 48889184；BK1036 -318235362560；BK0448 -219514637056；BK0459 -92431463936；BK1038 -81439874416；BK1033 -78520394288；BK1037 -74580737024

与 `evidence/official-roll.json` 的 window5/window63 `code`+`main_net` 一致。与总工 IAB 用户可见结果（05:26:04 UTC，见 `implementation.md` §5.1）方向一致：5 日通信设备 +61.60 亿 / 半导体 -217.53 亿；63 日种植业 +24.14 亿 / 半导体 -3182.35 亿。

本会话未独立 review 产品逻辑，未用浏览器复核。

## 6. 回滚建议更正（未执行回滚）

文档风险：`implementation.md` 顶部旧句「用备份 files/ 覆盖六源码」会覆盖本轮后续其他任务修改。

已改为：以本轮相对脏树起点 `evidence/diffs/*.diff` 为依据的反向补丁 dry-run；冲突则停。行业分区回滚须校验当前哈希是否仍等于本轮交付版本并留存当前状态；存在后续有效写入则停，只回滚本轮变化。不要整文件覆盖。

本会话 **没有** dry-run 或应用任何反向补丁，也没有动 `data/ext_data/ext_fund_flow_bk_daily/`。

脏树起点备份（六源码 + 行业分区元数据，本阶段只读）：`/Users/simon/备份/codex/20260909-131435-industry-fflow-live`

## 7. tests / UI / 服务 / 备份路径

| 面 | 本会话事实 |
| --- | --- |
| tests | 源与 `evidence/pytest.txt` 仍在。未重跑。未来 basetemp=`/tmp/industry-fflow-20260909-*` |
| UI | 未开浏览器。§5.1 / §5.2 均为总工既有观测 |
| 服务 | 沿用 `evidence/runtime.txt`：后端父 PID 3510 / worker 91841 @3018；Vite PID 3528 @3011。本阶段未重启、未探活 |
| 实现记录备份 | `/Users/simon/备份/codex/20260909-134048-industry-fflow-live-delivery-repair` |
| 备份内容 | `implementation.pre-delivery-repair.md` sha256 `4102ea17b030b75494f8d767351713cdd18a051289894b50bf7ec06efa7f7a06`；`implementation.md` sha256 `4a551ff991a439814dd37e95ffbcfad3f9052e95cb9cfe85ebf525e918e9fafd`；`README.md` 附本说明 |
| 权威状态（未改） | 数据台条目 `ext_fund_flow_bk_daily_industry_roll_live_20260909` = canary；用户台 `industry_fundflow_daily_roll_live_20260909` = verified（仅用户可见窗）；计划 `D-R-05` active |

## 8. 剩余边界

- 未独立 Cursor 复查。不是 `accepted` / `production`。
- 日历仍止于 `2026-08-31`，行业窗 freshness=`unknown`，`calendar=false`。这是设计，不是接入失败。本轮不扩修日历。
- 未来自然 15:35 `_run_tracked` → `run_now` 未观察。
- 概念正式写入不在本轮。
- 执行端 HTTP 401 与总工已登录 200 是不同身份；本会话未再 curl。
- `.pytest_cache/` 仍留在旧 root；无 symlink。
- 废纸篓内 11 个 `*current` 仍是绝对路径 symlink（指向已不存在的旧 `.pytest-tmp`）。不恢复、不跟随。
- 控制器尚未用 `/tmp/industry-fflow-20260909-*` 重跑 14 pytest。本会话不声称这 14 条刚跑过。
