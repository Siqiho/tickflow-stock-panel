# 云端审阅简报（不改路由）

- 性质：只读审阅。本文件是文档，不改数据源路由、不改 `.env` / 密钥 / 鉴权、不碰正式 `DATA_DIR`。
- 日期：2026-09-12。
- 云端 checkout：已 `git fetch` 并核对远端；工作树在写本文件前干净。
- **当前 tip**：`cursor/harden-round-thirty-three-3261` / [PR #34](https://github.com/Siqiho/tickflow-stock-panel/pull/34)
- **tip SHA**：`e16dad28b165bfc1288b8720dc299c8bd29f0829`（短 SHA `e16dad2`）
- 其上没有更新的 stacked harden PR。GitHub 列表里最新加固 PR 就是 #34（创建于 2026-09-12T03:20:13Z）。
- 本栈 **全部 OPEN、未合入 `main`**。不是 `accepted` / `production`。正式数据目录与用户 Mac 运行面不在云环境。

## 1. 本次 checkout 记录

```
$ git fetch origin cursor/harden-round-thirty-three-3261
$ git fetch origin main
$ git log --oneline -15
e16dad2 docs: record thirty-third-round isolated routing test evidence
48f064c fix(data): close leftover instrument caches, scan poison, and leftover jobs
65120c9 docs: record thirty-second-round isolated routing test evidence
1488fc6 fix(data): close leftover TickFlow extras mix and leftover jobs
dac5aff docs: record thirty-first-round isolated routing test evidence
fd0ffa8 fix(data): close leftover TickFlow unreadable mix and job probes
6801484 docs: record thirtieth-round isolated routing test evidence
c89985d fix(data): close leftover TickFlow public minute, overlay, and fail-open probes
68d5a58 docs: record twenty-ninth-round isolated routing test evidence
bf9fea4 fix(data): close leftover TickFlow instrument readers and extras-blind ext
bffc770 docs: record twenty-eighth-round isolated routing test evidence
8a61be5 fix(data): close leftover TickFlow minute, instrument, overlay, and Lab mix
b9a395c docs: record twenty-seventh-round isolated routing test evidence
09bfbd0 fix(data): close leftover extras-blind calendars and stale caches
3684e3c docs: record twenty-sixth-round isolated routing test evidence

$ git status
On branch cursor/harden-round-thirty-three-3261
nothing to commit, working tree clean
```

本地 HEAD 与 `origin/cursor/harden-round-thirty-three-3261` 同为 `e16dad2`。

## 2. 栈怎么叠

从 PR #2 起就是「上一轮 head → 下一轮 head」的线性栈。**PR 号比加固轮次多 1**：PR #18 = 第 17 轮，PR #34 = 第 33 轮。

本简报覆盖用户指定的 **#18–#34**（第 17–33 轮）。更早的 #2–#17 是同一条 harden 链的底座，已合进这些 tip，不必为了审阅再单独 merge。

```
#18  round 17  cursor/harden-round-seventeen-be9a      f41aa38
#19  round 18  cursor/harden-round-eighteen-0fc0       32308c7
#20  round 19  cursor/harden-round-nineteen-cce9       3f9b0c8
#21  round 20  cursor/harden-round-twenty-6f23         f87058b
#22  round 21  cursor/harden-round-twenty-one-605e     798e652
#23  round 22  cursor/harden-round-twenty-two-cdef     7b0e45c
#24  round 23  cursor/harden-round-twenty-three-7ae5   f07405d
#25  round 24  cursor/harden-round-twenty-four-3628    4d938e7
#26  round 25  cursor/harden-round-twenty-five-399b    d0d521f
#27  round 26  cursor/harden-round-twenty-six-c11d     3684e3c
#28  round 27  cursor/harden-round-twenty-seven-dd25   b9a395c
#29  round 28  cursor/harden-round-twenty-eight-5b8d   bffc770
#30  round 29  cursor/harden-round-twenty-nine-4230    68d5a58
#31  round 30  cursor/harden-round-thirty-57e9         6801484
#32  round 31  cursor/harden-round-thirty-one-f3d5     dac5aff
#33  round 32  cursor/harden-round-thirty-two-d50f     65120c9
#34  round 33  cursor/harden-round-thirty-three-3261   e16dad2   ← 当前 tip
```

只看 tip 即可看到 #18–#33 的全部代码；不必把 17 个 PR 逐个 checkout 到 Mac。

## 3. 各轮关上了什么

每轮调查目录：`docs/investigations/2026-09-12-data-source-wiring-roundN/`。下面是「关上的混源 / fail-open」，不是产品合同。

| PR | 轮次 | 关上的路径 |
| --- | --- | --- |
| [#18](https://github.com/Siqiho/tickflow-stock-panel/pull/18) | 17 | 自定义日 K 后，回测 / live-agg / ETF / 主线 / 选股 / overlay / 挖掘 / 完整性 / prune / 日质检 / 竞价 / 龙虎不再把 leftover TickFlow 当当前日历；`/api/kline/minute-range` 在自定义分钟源下不再扫 leftover parquet |
| [#19](https://github.com/Siqiho/tickflow-stock-panel/pull/19) | 18 | overview / 日质检 / 完整性在探测抛错时不再 glob leftover `date=*`；pipeline 增量 / 部分 prune / 指数+ETF 起点 / 分钟覆盖、延长历史与重建 enriched 日数、回测矩阵、regime stale / RPS as_of / enriched lineage、指数/ETF 状态日历走当前 route |
| [#20](https://github.com/Siqiho/tickflow-stock-panel/pull/20) | 19 | 竞价 / 龙虎 except-fallback 不再 leftover-glob；竞价 enrich、筹码 loader、选股 warmup 留在当前日 K；完整性 prune 不再在自定义修复时抹 leftover；repo / 挖掘 / regime 日历探测 fail-closed；DuckDB re-gate 失败会清空 leftover 可见 SQL，不再留下第一遍未门控视图 |
| [#21](https://github.com/Siqiho/tickflow-stock-panel/pull/21) | 20 | overview 官方日探测抛错不再 fail-open leftover；选股 latest 走磁盘 provenance；enriched latest / hist / overlay / live-agg 内存缓存切源后丢掉 leftover；日/指数/ETF 扫描只用可用分区（schema poison 不再掏空当前源）；hist/range 过滤抛错返回 None；指数/ETF 状态不再数 leftover DuckDB 行；竞价 enrich / 趋势 overlay 探测抛错 fail-closed；公开 EOD persist 拒绝自定义 / unresolved 日 K |
| [#22](https://github.com/Siqiho/tickflow-stock-panel/pull/22) | 21 | 分钟扫描用可用分区（schema poison 不再掏空当前源）；live enriched 全量重建走当前日 K；指数基准 / overview / 上证报价回退走文件 provenance；进程缓存按 daily route 分键；空 datetime 清理不抹 leftover 分钟；live publish / 日 K 写入拒绝自定义 / 不可读 prefs；除权状态不数 leftover DuckDB 行；HTTP minute-range leftover getter / 指数 stock-store 混读、单票分钟 persist 留下 leftover 视图、脏指数今日叠进基准动量、实时源切换后复用指数报价缓存——一并关上 |
| [#23](https://github.com/Siqiho/tickflow-stock-panel/pull/23) | 22 | 官方趋势 overlay 与 regime 历史缓存按 daily route 分键；HTTP minute-range / get_minute 对 ETF 带 `asset_type`，不再用个股 leftover 分时填 ETF；DuckDB refresh 只 re-gate，不再先裸 glob；旧按标的分区的分钟迁移会过滤并打 route 标签；depth 读跳过过期 `depth5`、保留当前 `sealed_l1`；股本 append / 历史股本缓存在 prefs 抛错或财务切源时 fail-closed；指数 / ETF / 分钟派生日历走可用分区 |
| [#24](https://github.com/Siqiho/tickflow-stock-panel/pull/24) | 23 | DataStore 初始化不再先建 leftover 可见的裸 kline/adj/财务/depth glob；regime / 主线磁盘历史按 daily route 打标过滤，增量 upsert 不再把 leftover 并进自定义；池成分在切 pool 后不再用 leftover CSI 播种；财务 PIT 迁移拒绝把 leftover 改写成当前；目录兼容日历按 prefs route token 覆盖可用分区，上次扫描的 leftover 日期不再当当前覆盖 |
| [#25](https://github.com/Siqiho/tickflow-stock-panel/pull/25) | 24 | 目录 rescan 切源后不再把 leftover TickFlow 日历写成当前覆盖；list/get 在 daily / adj / depth / realtime 切换后隐藏 leftover（token 含这些 route）；只剩 leftover 的财务字节不再变成当前日历；池切源后成分历史拒绝 leftover 改写；reference 查询跳过 leftover 估值 / 成分 / 公司行动；quote snapshot 按 realtime route 打标过滤；估值 / 涨停写入带 daily route；公司行动 prior merge 在 adj 切源后跳过 leftover；日质检跳过 leftover TickFlow enriched 成交额 |
| [#26](https://github.com/Siqiho/tickflow-stock-panel/pull/26) | 25 | 回测 PanelCache 按 daily route 分键；公开财务 depth 探测走已门控利润表，不再被 leftover 报表选成 light mode；缺 token 的旧目录库只在全部 route 仍是 leftover TickFlow / public 时可见，自定义 / unresolved 后隐藏；regime batch / enriched warmup 做行级 leftover 过滤；DuckDB / 选股 ext 时序只挂最新 `date=*`；缺 ext 配置不再回退到未门控 `ext_*`；RPS 维度图按 daily route 缓存；未知 `list_partition_dates` 表 fail-closed |
| [#27](https://github.com/Siqiho/tickflow-stock-panel/pull/27) | 26 | 完整性 quote_ts / snapshot 跳过当前日旁的 leftover extras；日质检 concat 先丢掉 leftover extras；prune 行数与过期价比较跳过 leftover extras；overview / RPS / 自选 / 板块监控 ext 时序只用最新 `date=*`；竞价 OHLC 与回测矩阵指纹跳过 leftover extras；设置切源会 re-gate DuckDB 并丢掉进程缓存；无本地日 K 或窗口内 snapshot 时开 realtime 会被挡住（409 + 修复，不写 pref）；盘后「今日已有 → 只跑 quotes」会自愈窗口内 snapshot；live `_build_daily` 把 `timestamp` 映到 `quote_ts`，停牌 leftover snapshot 不再冒充今日 K |
| [#28](https://github.com/Siqiho/tickflow-stock-panel/pull/28) | 27 | 日 / 分钟日历看见 leftover `part.parquet` 后面的当前 extras，不再只探针 leftover part、也不再取 leftover `extras[0]`；选股 / overview / overlay / prune / pipeline / 挖掘 / regime / 质检 / 财务 / depth / quote_snapshot 只读当前 route extras；策略缓存打 daily route 戳，切源即丢 |
| [#29](https://github.com/Siqiho/tickflow-stock-panel/pull/29) | 28 | 已声明自定义分钟 *调用失败* 不再有资格回退 TickFlow；维表跟随 daily route：自定义 / unresolved 日后跳过 TickFlow 个股 / 指数 / ETF sync，DuckDB / 宇宙 / 主线 / OCR / 公司行动隐藏 leftover 宇宙；自定义 / unresolved 日后禁止 quote-snapshot overlay；Lab leftover TickFlow 拒绝 public sina（除非显式 `public`）；leftover TickFlow 同日优先 tagged extras，不再 concat 旁边的 untagged extras |
| [#30](https://github.com/Siqiho/tickflow-stock-panel/pull/30) | 29 | 剩余 leftover TickFlow 维表读者跟随 daily route（估值 / 财务宇宙 / 公开股本 / 质检覆盖 / ext lookup / enriched pipeline / HTTP 名称）；pipeline remount 已门控 DuckDB，不再裸 leftover glob；ST 标的 TTL 按 instrument route 打戳，切源即丢；Lab shadow 日 K 不再取 leftover `part.parquet` / `extras[0]`；HTTP ext 与资金流 snapshot 能看见 leftover part 旁的 extras |
| [#31](https://github.com/Siqiho/tickflow-stock-panel/pull/31) | 30 | leftover TickFlow 单票公开 / TDX 分钟不再静默混源（显式 public 分钟仍走该视图）；自定义 / unresolved 日后跳过 leftover TickFlow 分钟 / depth / 全市场分钟 / adj 作业；不可读 leftover 日期标记 fail-closed；自定义 route 的 DuckDB remount 不再 leftover-glob；HTTP ext remount 不再 leftover-glob `instruments_ext`。catalog / get_minute 对 leftover TickFlow 保持 fail-loud |
| [#32](https://github.com/Siqiho/tickflow-stock-panel/pull/32) | 31 | 不可读 leftover TickFlow 日历保持 fail-closed；不可读 tagged leftover 不再回退到同日 untagged extras（读 / catalog / get_minute 对 leftover TickFlow 仍 fail-loud）；自定义日后 leftover TickFlow `kline_ext` remount / 日期范围跳过；不可读 leftover `kline_ext` 日期标记不再铸视图；自定义 / unresolved 日后跳过 leftover TickFlow 财务 / 池作业 |
| [#33](https://github.com/Siqiho/tickflow-stock-panel/pull/33) | 32 | 不可读 tagged leftover 在维表 / 财务 / depth / leftover TickFlow `kline_ext` 不再回退 untagged extras；leftover TickFlow DuckDB 视图不再把 untagged extras coalesce 进 tagged leftover；自定义 / unresolved 日后跳过 leftover TickFlow adj / 分钟批 / monitor / burst 作业；不可读用户 ext 日期标记不再铸最新分区 |
| [#34](https://github.com/Siqiho/tickflow-stock-panel/pull/34) | 33 | 内存维表缓存不再 leftover-glob tagged leftover 旁的 untagged extras；只认 `part.parquet` 的 enriched / 分钟 / adj / 财务 remount 仍能服务 extras-only leftover TickFlow；自定义 / unresolved 日后跳过 leftover TickFlow 交易日探针；leftover TickFlow 公司行动 `fetch_missing_adj` 不再写 public sina；用户扩展因子帧仍能看见 leftover part 旁 extras；不可读 hithink 日期标记不再铸最新分区。catalog / get_minute 对 leftover TickFlow 仍 fail-loud |

## 4. 仍属故意留下的 TickFlow 合同

权威表：[`docs/investigations/2026-09-12-data-source-wiring-round33/leftover-contracts.md`](./2026-09-12-data-source-wiring-round33/leftover-contracts.md)。

**不要把下面这些当成下一轮 Harden 目标**，除非产品明确改合同。

| 合同 | 位置 | 为什么留下 |
| --- | --- | --- |
| 盘后默认时刻 | pipeline / scheduler | 运维时钟，不是混源 bug。15:30 / 09:10 / 15:02 未改。leftover TickFlow 分钟 / depth / 全市场分钟 / adj / 财务 / 池 / 交易日探针 *作业* 在自定义日后已经跳过 |
| leftover TickFlow + free 实时 → `mode=none` | `QuoteService.realtime_mode` | 禁止静默落到公开实时 |
| leftover TickFlow 日 K + 公开实时 overlay | `_quote_overlay_allowed` | 默认安装（`daily=tickflow`, `realtime=public`）；响应带 `is_quote_snapshot`。自定义 / unresolved 日 K 仍然拒绝 |
| leftover TickFlow 仍可见「只有 untagged」的旧分区 | daily / minute / instruments / snapshots / adj / financials / enriched | 打标前的遗留文件。同日 tagged leftover 旁的 untagged extras 不再混入；不可读 leftover 不再铸日历、也不再回退 untagged extras。catalog / get_minute 对 leftover TickFlow fail-loud |
| 显式 `adj=public` / `depth5=public` / `financial=public` / `pool=public` | settings + `/api/free-ext` + 公司行动 `fetch_missing_adj` | 用户自己选的公开面。Lab leftover TickFlow 仍拒绝；leftover TickFlow adj 不再写 public sina |
| 用户 ext extras 在 leftover `part.parquet` 旁仍可见 | `latest_ext_parquet_files` / `usable_ext_snapshot_files` / 扩展因子帧 | 前几轮 extras-blind 已关；因子 snapshot / 时序现在也读 extras。leftover TickFlow `kline_ext` remount 仍优先 tagged leftover |
| `.env` / 鉴权 | settings / secrets | 路由加固范围外 |

第 17 轮当时写进 leftover 表、后来已被关上（不要再当「故意留下」）：

- 已声明自定义分钟 *调用失败* 后回退 TickFlow → **第 28 轮关上**
- leftover TickFlow 单票公开 / 自选 TDX 分钟 → **第 30 轮关上**
- 个股 / 指数 / ETF 维表固定 TickFlow（无 `instrument_provider`）→ **第 28–29 轮改为跟随 daily route**
- 自定义 / unresolved 日 K 上的 quote-snapshot overlay → **第 28 轮禁止**（默认 leftover 日 K + 公开实时仍 overlay）

## 5. 隔离 pytest 计数

全部在云 agent、`backend/.venv`、**隔离 `DATA_DIR=/tmp/ot-data-source-wiring-roundN`** 下跑。不读 `.env`，不写正式数据，不触网。计数来自各轮 `evidence/test-results.md`，不是本简报新跑的。

| PR | 轮次 | 隔离结果 | `DATA_DIR` |
| --- | --- | --- | --- |
| #18 | 17 | **568 passed** | `/tmp/ot-data-source-wiring-round17` |
| #19 | 18 | **597 passed** | `/tmp/ot-data-source-wiring-round18` |
| #20 | 19 | **636 passed** | `/tmp/ot-data-source-wiring-round19` |
| #21 | 20 | **661 passed**, 41 warnings | `/tmp/ot-data-source-wiring-round20` |
| #22 | 21 | **715 passed**, 42 warnings | `/tmp/ot-data-source-wiring-round21` |
| #23 | 22 | **734 passed**, 42 warnings | `/tmp/ot-data-source-wiring-round22` |
| #24 | 23 | **766 passed**, 42 warnings | `/tmp/ot-data-source-wiring-round23` |
| #25 | 24 | **816 passed**, 42 warnings | `/tmp/ot-data-source-wiring-round24` |
| #26 | 25 | **837 passed**, 42 warnings | `/tmp/ot-data-source-wiring-round25` |
| #27 | 26 | **893 passed**, 47 warnings | `/tmp/ot-data-source-wiring-round26` |
| #28 | 27 | **916 passed**, 47 warnings | `/tmp/ot-data-source-wiring-round27` |
| #29 | 28 | **948 passed**, 47 warnings | `/tmp/ot-data-source-wiring-round28` |
| #30 | 29 | **978 passed**, 47 warnings | `/tmp/ot-data-source-wiring-round29` |
| #31 | 30 | **998 passed**, 47 warnings | `/tmp/ot-data-source-wiring-round30` |
| #32 | 31 | **1019 passed**, 47 warnings | `/tmp/ot-data-source-wiring-round31` |
| #33 | 32 | **1040 passed**, 47 warnings | `/tmp/ot-data-source-wiring-round32` |
| **#34 tip** | **33** | **1069 passed, 47 warnings** | `/tmp/ot-data-source-wiring-round33` |

警告主要是既有 Polars `streaming` / `join_asof` sortedness / ext_factors escape，不是本栈新引入的失败。

Tip 上完整 leftover-routing 套件命令（只作核对，勿对 Mac 正式目录跑）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round33 \
  .venv/bin/python -B -m pytest -q --tb=line \
    tests/test_round_thirty_three_route_hardening.py \
    tests/test_round_thirty_two_route_hardening.py \
    tests/test_leftover_route_hardening.py
    # …以及 evidence/test-results.md 里列出的其余文件
```

完整文件列表见 [`2026-09-12-data-source-wiring-round33/evidence/test-results.md`](./2026-09-12-data-source-wiring-round33/evidence/test-results.md)。

## 6. 怎么审、不要把栈 merge 进 Mac

云环境明确写了：正式 `DATA_DIR` 与用户 Mac 运行面 **不在这里**。这条栈是 17 个仍 OPEN 的 stacked PR，**不要**为了看代码把 tip rebase / merge / reset 到本机正在跑行情的 checkout。

建议审阅顺序（全部在 GitHub / 浏览器，零本地切换）：

1. **先读本文件**，再读 tip 合同 [`round33/leftover-contracts.md`](./2026-09-12-data-source-wiring-round33/leftover-contracts.md) 与 [`round33/README.md`](./2026-09-12-data-source-wiring-round33/README.md)。
2. **只打开 [PR #34](https://github.com/Siqiho/tickflow-stock-panel/pull/34)** 看 Files changed。因为它叠在 #18–#33 之上，tip diff 相对 `main` 会很大；相对 #33 的 diff 才是第 33 轮本身。
3. 若要核对某一轮「关上了什么」，打开该轮 PR 的 Conversation + 对应 `docs/investigations/2026-09-12-data-source-wiring-roundN/README.md`，不要 checkout 那根分支到 Mac。
4. 证据只信各轮 `evidence/test-results.md` 的隔离计数。不要在 Mac 上对正式 `DATA_DIR` 复跑这套 pytest。
5. **不要** `git merge` / `git rebase` / `git pull` 这些 `cursor/harden-round-*` 到本机 `main` 或正在跑的工作树。不要用这栈覆盖本机 `.env`。不要把 leftover 合同当成 bug 再开一轮 Harden。
6. 若必须在本机看文件：用 **只读** `git fetch` + `git show e16dad2:path`，或另开一个 **一次性 worktree**（空 `DATA_DIR`），看完删掉。不要用正在服务的那份 tree。
7. 产品是否接受、是否合入 `main`，等你在 GitHub 上点。本简报 **不开新的加固 PR、不发明新的路由改动**。

相对 `main` 的整栈仍是草稿链。合入策略（squash 整栈 vs 按轮 merge）不在本文件范围；先审 tip 合同与 #34 即可。
