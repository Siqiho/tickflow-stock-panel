# 只读审计：2026-09-10 数据采集开发基线与市场看板缺口

> **性质**：只读审计报告。本文不修改应用代码、配置、依赖、CI 或运行时行为。  
> **审计日**：2026-09-11  
> **对象仓库**：`Siqiho/tickflow-stock-panel`（本工作区）  
> **对照上游**：`shy3130/tickflow-stock-panel`（数据采集/看板的 9/10 开发基线所在）

---

## 0. 范围、假设与方法

### 0.1 审计范围

1. **9/10 数据采集开发基线**：文档、脚本、批次、平台日志、备份引用。  
2. **市场看板**：数据源、字段、刷新管道、已知问题。  
3. **缺口清单**：期望基线 vs 当前检出，优先级、证据路径、风险。  
4. **相关线程**（数据台简化 / 30g）：只记发现，不实施。

### 0.2 明确假设

| # | 假设 | 依据 |
| --- | --- | --- |
| A | 「Sept 10」指 **2026-09-10**（日历日），不是盘前 cron `09:10`。二者在代码里并存，下文分开写。 | 任务标题；上游 9/10 当日有看板/数据相关合入 |
| B | 「当前」= **本 fork 工作区 `main` 检出**，不是上游 `shy3130` 的 9/11 HEAD。 | 本仓 `origin` 为 `Siqiho/tickflow-stock-panel`，`HEAD=34eaba3` |
| C | 「9/10 期望基线」= 上游在 2026-09-10 前后已合入的数据采集/看板栈（标签约 `v0.2.2`/`v0.2.3`），以 `upstream/main@54ef03ac`（2026-09-11）作可读对照尖。 | 上游当日提交 + 9/11 01:02Z 合并的 #294–#299 |
| D | 本工作区没有用户运行时 `data/`、没有平台生产日志、没有备份快照。日志/备份只能从**代码引用**还原。 | `.gitignore` 排除 `data/**`；工作区无 `data/` 实体 |

### 0.3 方法

- 通读本仓文档、盘后管道、看板 API/前端、job 存储、桌面日志路径。  
- 只读 `git fetch` 上游 `main`，对比数据/看板相关路径（未改工作区产品文件）。  
- 阅读上游 Issue/PR：#7、#23、#208、#216、#223、#225、#226、#241、#245、#294、#298、#301。  
- **未**跑应用、未改配置、未执行任何修复。

---

## 1. 基线摘要

### 1.1 当前检出（本 fork）

| 项 | 值 |
| --- | --- |
| 仓库 | `https://github.com/Siqiho/tickflow-stock-panel` |
| 分支 / 提交 | `main` / `34eaba3010315c570be78f5f728a0c85e30aa014` |
| 提交日 | 2026-07-17 |
| `VERSION` | `v0.1.84`（工作区文件；历史中有 0.1.85 提交，文件未再对齐） |
| 相对上游滞后天数 | 约 **56 天**（7/17 → 9/11） |
| 本仓 Issues | 已关闭 |
| 本仓最近 GitHub 更新 | 2026-07-17T15:54:26Z（与检出一致，fork 未跟上游 8–9 月） |

**一句话**：本仓是 7 月中旬的量化工作台；9/10 上游已经演变成带数据完整性、市场环境、因子/挖矿的 `v0.2.x`。缺口首先是 **fork 未同步**，其次才是 9/10 当日仍未收口的残差。

### 1.2 9/10 上游开发基线（期望）

对照尖：`shy3130/tickflow-stock-panel` `54ef03ac`（2026-09-11），`VERSION=v0.2.2`，远程标签已有 `v0.2.3`。

**数据采集栈（9/10 时已应具备）：**

- 盘前 **09:10** 全量覆盖个股维表；盘后默认 **15:35**（不再是 15:30）拉日 K / 除权 / enriched。  
- A 股 / ETF / 指数拉取开关**真实可读**（`pipeline_pull_a_share` 不再写死 `True`）。  
- 日 K 分支：实时覆写今日 / batch 补缺口 / 首次 1 年 / 修正强制区间。  
- `quote_ts` + `data_integrity`：区分盘中快照 vs 盘后权威，自动修近窗坏分区。  
- `#223`：自选实时写出的残缺 enriched 分区会被剪掉再全市场补齐。  
- `#269`：停牌分区不再反复误删重算。  
- 分钟 K：北京时区窗口、流式分段落盘、前部空洞自愈。  
- 自定义源：日 K / 除权 / 实时 +（9 月初）五档 `depth5`。  
- 数据页新增：除权同步门闩、市场环境（regime）覆盖卡、能力矩阵路由展示。  
- 新文档：`docs/market-phase.md`、`docs/mining.md`、因子平台两份、TickFlow Pro 探测/限速。

**9/10 当日与看板/数据直接相关的合入：**

| 提交 / PR | 主题 |
| --- | --- |
| `7755ab3a` / #294 | 看板板块领涨股不再把 `0.00%` 当成缺失 |
| `77b829a0` | 看板广度条与涨跌分布统一左绿右红 |
| `2b059d4b` / #298 | 非交易日已交易分钟按全天算，量比不再被折算放大 |
| `40c2468c` / #295 | 涨停梯队时序扩展列只取最新分区 |
| `79eb150d` / #299 | 扩展数据 `rows` 的 date 先校验再拼分区路径 |
| `e956e3a6` / #296 | 交易日「未知」结论按 TTL 缓存，减少探测风暴 |

**9/11 已见、但晚于 9/10 日终的残差（记入「基线之后」）：**

- #301 仍 **OPEN**：能力矩阵漏传 `full_minute_data_provider`，全量分钟卡片恒显不可用（`54ef03ac` 声称修复，Issue 当日仍开）。  
- `ea4d8a82`：挖矿在环境数据覆盖不足时弹窗补算。

### 1.3 本仓已有的数据采集能力（7/17 快照，并非空白）

本检出**已经**具备一套可运行的采集台，不能写成「没有管道」：

| 子系统 | 本仓现状 | 主要路径 |
| --- | --- | --- |
| 盘前维表 | cron 默认 09:10，全量覆盖 instruments，刷新 enriched 缓存 | `backend/app/jobs/daily_pipeline.py` `start_scheduler` / `run_instruments_sync` |
| 盘后管道 | 默认 **15:30**；日 K → 除权 → enriched → 指数/ETF → 可选分钟 K → 刷 DuckDB | 同上 `run_now` |
| 批次 | TickFlow `kline.daily.batch` 等按 `tiers.yaml` rpm/batch 切片 | `tiers.yaml`；`kline_sync` + `rate_limits` |
| 任务台账 | `data/job_store/{id}.json`，最多 50 份；普通 1200s / 分钟长任务 1800s | `backend/app/services/pipeline_jobs.py` |
| 数据画像页 | 维表/日K/除权/Enriched/指数/ETF/分钟/财务 + 扩展数据卡片 | `frontend/src/pages/Data.tsx` |
| 看板 | `GET /api/overview/market`，5s TTL；SSE `overview-market` 失效 | `overview.py` / `market_overview_builder.py` / `Dashboard.tsx` |
| 备份语义 | 「拷贝整个 `data/`」；扩展配置迁移写 `.json.bak` | `docs/configuration.md`；`ext_data.py` |
| 平台日志 | 桌面端 `data/desktop.log`；管道进度进 job JSON + 应用 logger | `desktop.py`；`daily_pipeline` |

---

## 2. 数据采集基线详单

### 2.1 调度与批次

```
工作日 09:10  CST  —— 盘前 instruments 全量覆盖（偏好可调，不晚于 09:15）
工作日 15:30  CST  —— 本仓盘后管道（上游期望改为 15:35，且禁止早于 15:35）
工作日 15:02  CST  —— 五档 sealed 定版（偏好 15:01–18:00）
每 60 分钟          —— 能力重探
工作日（可选）      —— AI 复盘
```

日 K 决策树（本仓 `run_now`）：

1. 未勾选 A 股且非修正 → 跳过（**但本仓开关恒为 True，见缺口 G1**）。  
2. 修正 `override_start_date` → 强制 batch `[start, today]`。  
3. 今日已有 + 付费 `quote.pool` + tickflow → 实时行情覆写今日。  
4. 有历史 → batch 从 `latest_daily` 补到今天。  
5. 无数据 → batch 拉近 1 年（约 5500 只，文档写 1–3 分钟）。

批次参数（`tiers.yaml`，free/none 日 K）：`kline.daily.batch` = **60 rpm / 100 标的/批**。全 A ≈ 55 批。  
分钟 K：文档与代码均警告数据量是日 K 的 **~240 倍**；本仓已做分段流式落盘。

### 2.2 脚本 / 入口（本仓）

| 入口 | 作用 |
| --- | --- |
| `./dev.sh` / `dev.ps1` | 一键起前后端 |
| 数据页「立即同步」/ 看板「立即获取数据」 | `POST` 盘后管道 job |
| 数据页：向前扩展 / 日 K 修正 / Enriched 重算 / 分钟同步 | 独立面板 |
| `run_instruments_sync` / `run_now` | 调度与手动共用 |
| `repair_daily.py` | 修正窗口重拉 |
| `extend_history.py` | 历史向前扩展 |
| 自定义源 YAML | `data/data_sources/*.yaml`（运行时，不入库） |

本仓 **没有** 独立的离线批处理 shell/SQL 脚本；采集全在 Python 管道里。

### 2.3 平台日志（仅代码引用，工作区无实文件）

| 引用 | 路径 / 形式 | 说明 |
| --- | --- | --- |
| 桌面启动日志 | `{DATA_DIR}/desktop.log` | `backend/app/desktop.py`；无控制台时的唯一落盘 |
| 打包安装日志 | `packaging/install.log`、`packaging/installed_run.log`、`backend/_desktop_run.log` | `.gitignore`，本地构建产物 |
| 管道任务 | `{DATA_DIR}/job_store/*.json` | 终态落盘；running 只在内存 |
| 应用日志 | stdout / `LOG_LEVEL` | Docker/dev 标准输出 |
| 复盘/告警 | `alerts.jsonl`、复盘报告 JSON | 业务日志，不是采集审计日志 |

**缺口**：没有按交易日归档的「采集平台日志」、没有成功/失败批次的独立审计表。要复盘 9/10 某次拉取，只能靠当时机器上的 `job_store` + 容器日志——本审计环境两者都没有。

### 2.4 备份引用

| 引用 | 证据 |
| --- | --- |
| 「迁移=拷贝整个 `data/`」 | `docs/configuration.md`；`backend/app/config.py` 注释 |
| 扩展配置迁移备份 | `ext_configs.json` → `ext_configs.json.bak`（`ext_data.py`） |
| git 物理隔离用户数据 | `.gitignore`：`data/**`，防止 `git pull` 覆盖本地行情 |
| 无自动快照 / 无异地备份作业 | 全库搜索无 cron 备份、无对象存储、无版本化 parquet |

**风险**：`data/` 是单点。误点数据页「清空」、磁盘满、或把盘中快照当成收盘定版，都没有自动回滚点。

### 2.5 上游 7/17→9/10 采集层新增（本仓缺失的模块级文件）

只列与采集/看板直接相关的**新文件**（完整 diff 远大于此）：

- `backend/app/services/data_integrity.py` + `tests/test_data_integrity.py`  
- `frontend/src/components/AdjFactorSyncGate.tsx`  
- `frontend/src/components/data/RegimeConfigCard.tsx`  
- `frontend/src/lib/dataSources.ts`  
- `docs/market-phase.md`、`docs/mining.md`、`docs/factor-*.md`、`docs/tickflow-pro-*.md`  
- `backend/app/services/market_phase.py` / `market_mainline.py`（市场环境，看板的下游消费方）

路径级统计（`git diff --stat HEAD upstream/main` 子集）：

| 路径 | 量级 |
| --- | --- |
| `backend/app/jobs/daily_pipeline.py` | +366 行级 |
| `backend/app/services/kline_sync.py` | +770 |
| `backend/app/services/quote_service.py` | +831 |
| `backend/app/services/pipeline_jobs.py` | +310 |
| `frontend/src/pages/Data.tsx` | +280 |
| `frontend/src/pages/Dashboard.tsx` | +310 |

---

## 3. 市场看板：源、字段、刷新、已知问题

### 3.1 数据源

```
 enriched 当日截面 (kline_daily_enriched / Polars 缓存)
    ├─ 广度 / 涨跌分布 / 情绪雷达 / 趋势 / 活跃度 / 涨跌榜 / 成交额榜 / 换手榜 / 连板梯队
    └─ 依赖盘后管道或实时 flush 写好的分区

 quote_service 实时缓存
    └─ 核心指数：000001.SH / 399001.SZ / 399006.SZ / 000680.SH
       无实时或指定历史日 → 回退 kline_index_daily

 depth_service（需 depth5.batch / Pro+）
    └─ 真假涨停、封板率修正（sealed_ready / fake_up / fake_down）

 ext_data 概念/行业配置
    └─ concept_rank / industry_rank（缺扩展数据则空）
```

装配入口：`build_market_overview`（`backend/app/services/market_overview_builder.py`）。  
HTTP：`GET /api/overview/market?as_of=`（`backend/app/api/overview.py`）。  
复盘与看板**声明同源**（`market_recap.py` 注释）。

Free / watchlist 模式：大盘是**盘后快照**，仅自选实时。`Dashboard.tsx` 已有 Amber 提示。

### 3.2 字段契约（本仓 `OverviewMarket`）

| 块 | 字段 | 计算输入 |
| --- | --- | --- |
| `as_of` | 截面日 | enriched 最新日或查询参数 |
| `quote_status` | enabled/running/age/mode | QuoteService |
| `indices[]` | last_price, change_pct, change_amount | 实时或指数日 K |
| `breadth` | total/up/down/flat/up_pct + avg/median/strong_* | `change_pct`；过滤 volume=0 且涨跌=0 |
| `amount` | total, avg | `amount` |
| `limit` | limit_up/down, broken, max_boards, seal_rate, tiers, sealed_* | 涨停信号 + 连板 + 五档 |
| `distribution[]` | 8 档涨跌幅桶 | `change_pct` |
| `trend` | 站上 MA5/20/60、60 日新高/低 | ma* / high_60d / low_60d |
| `activity` | 均换手、高换手数、放量占比、均量比 | turnover_rate / vol_ratio_5d |
| `radar` + `emotion` | 指数/赚钱/量能/投机/抗跌/主线 → 5 档中文标签 | 上述派生 |
| `top_*` | 涨跌/成交额/换手前 8 | 同截面 |
| `concept_rank` / `industry_rank` | leading/lagging + leader | ext_data × 截面涨跌幅 |
| `boards[]` | 板块计数（API 有，看板主 KPI 未铺） | 代码前缀 |

### 3.3 刷新管道

```
盘中 quotes_updated SSE
  → 后端 invalidate_overview_cache()
  → 前端 SSE_INVALIDATE_PREFIXES 含 'overview-market'
  → React Query staleTime 5s + TTL 5s

depth_updated SSE → 刷新 overview-market + limit-ladder

看板「重载」→ POST /api/data/refresh-cache（重建 Polars 缓存）→ 再拉 overview

盘后管道成功 / 首次「立即获取」→ invalidate dataStatus + overview

日期选择器 → as_of 历史截面（指数改走库，不走实时）
```

### 3.4 本仓已知问题（证据级）

1. **板块领涨把 0.00% 当缺失**（#294，9/10 上游已修，本仓未带）：  
   `leader = max(..., key=lambda s: _finite(s.get("change_pct")) or -999)`  
   平盘变成 `-999`，领跌股被当成领涨。复盘 prompt 同步写错。  
2. **Free 档看板非实时**：产品已提示，但仍是误读高发点。  
3. **自选实时残缺 enriched 被当成全日完整**（#223）：本仓按「日期目录是否存在」判断，会跳过计算 → 均线/看板截面错。  
4. **盘中停机快照固化**：本仓 `quote_service` 已写 `quote_ts`，但 **没有** `data_integrity` 扫描/自动修；次日管道看到「今天已有」就不再回补停机日。  
5. **量比在非交易日被放大**（#298）：影响 `activity.vol_ratio` 与雷达「量能」。  
6. **五档未就绪**：`sealed_ready=false` 时涨停数含假涨停，看板打「未修正/降级」。  
7. **扩展概念未拉**：热度卡空白，情绪「主线」维退化到 50。  
8. **看板加载失败无字段级诊断**：只有整页「看板加载失败」。  
9. **`boards[]` 已算未展**：沪/深/创业/科创/北交所结构在 API 里，主界面 KPI 没用。

---

## 4. 缺口表（期望 9/10 基线 vs 当前 fork）

优先级：P0 = 数据正确性/用户会按错数交易研究；P1 = 采集完整性或运维；P2 = 体验/文档/债。

| ID | 主题 | 期望（9/10 基线） | 当前（本仓 7/17） | 优先级 | 证据 | 风险 |
| --- | --- | --- | --- | --- | --- | --- |
| G1 | A 股拉取开关 | `get_pipeline_pull_a_share()` 读偏好，默认 True | **写死 `return True`**，UI 取消无效 | P0 | `preferences.py:228-230`；上游 #216 已关 | ETF-only 场景仍拉 ~5500 只 A 股，内存/额度浪费 |
| G2 | 残缺 enriched 误判完整 | 按标的覆盖剪分区后再补算（#223） | 只比日期目录个数 | P0 | 本仓 `daily_pipeline.py` enriched 分支；上游 `_prune_partial_enriched_partitions` | 均线、看板、选股、回测全错 |
| G3 | 盘中快照当收盘 | `data_integrity` + `quote_ts` 修近 5 日坏分区 | 无完整性模块；kline_sync 实时覆写不保证带齐 `quote_ts` 语义 | P0 | 上游 `data_integrity.py`；本仓无此文件；#276 上游补写 quote_ts | 停机日 OHLCV 永久污染 lookback |
| G4 | 板块领涨 0.00% | `_leader_sort_key`，None 才是 -inf（#294） | `or -999` 吞掉 0.00% | P0 | `market_overview_builder.py:288` | 看板热度 + AI 复盘写错龙头 |
| G5 | 盘后默认时刻 | 15:35，且不能早于 15:35 | 默认 15:30，最早可拨到 15:00 | P1 | 本仓 `preferences.py:276-288`；上游同函数 | 当日分区缺盘后量，与 quote 定版窗口撞车 |
| G6 | 日 K 修复部分成功仍报成功 | 覆盖不足 / 单批 502 应失败（#226） | 本仓有 `PipelineStageError`，但 stock-sdk 部分覆盖 + laggard 只 WARNING | P1 | `daily_pipeline.py:226-239,535-538`；#226 | 数据页绿灯、分区只数百行 |
| G7 | 掉队标的 | 可见化；自动回补仍不做 | 仅 WARNING + 计数 | P1 | 同上 laggard 段 | 退市/停牌/失败股缺口无限期 |
| G8 | 低配 OOM | 偏离列窄窗、regime 逐批、重任务单飞（#208/#241/#281） | 2c2g 同步打满的历史问题在 7 月关过，8–9 月新 OOM 路径本仓无对应修复 | P1 | #7、#208、#241；本仓 `kline_sync.py:857` 仍警告「数十 GB」 | 小机器同步即死，看板长期空 |
| G9 | 分钟能力展示 | 能力矩阵带 `full_minute_data_provider` | 无该路由字段；自定义源分钟也容易显示不可用 | P1 | 上游 #301（9/11 OPEN） | 用户以为没分钟，不采/不看 |
| G10 | 自定义分钟 date | datetime 字符串不得写成 `date=none`（#225） | 本仓仍走旧 cast 路径（未带 9 月修复） | P1 | #225 | 分钟分区丢失，盘中信号/看板量能间接受损 |
| G11 | 自定义五档 | 插件可授 `DEPTH5_BATCH`（#245） | DepthService 仍直连 TickFlow | P2 | 本仓 `depth_service.py`；#245 | 非 TF 用户看板封板永不「真封」 |
| G12 | 看板 UX（9/10） | 左绿右红；板块可点成分；除权门闩；导航高亮 | 无 AdjFactor 门闩、无成分股弹层升级、配色未统一 | P2 | Dashboard diff + `77b829a0` | 误读涨跌方向；除权未同步时看板静默用错价 |
| G13 | 市场环境/阶段 | `docs/market-phase.md` + Data 页 regime 卡 | 本仓无 market_phase / 无 RegimeConfigCard | P2 | 上游 docs + Data.tsx | 看板情绪与「阶段」两套口径无法对齐 |
| G14 | 数据页复杂度 | （相关线程：应简化） | 8 张画像卡 + 管道/修正/扩展/分钟/扩展数据，上游还加了 regime/门闩 | P2 | `Data.tsx`、`PageSettingsModal.tsx` | 见 §6.1 |
| G15 | 文档/版本 | 上游 `v0.2.2` + 多份新 docs | 本仓 docs 停在 7 月；`VERSION=v0.1.84` | P2 | `docs/` 目录对比 | 按旧文档运维会设错 15:30、误以为无完整性 |
| G16 | 备份与审计日志 | 至少有可复盘的 job + 完整性报告 | 无 9/10 实日志；无自动备份 | P2 | §2.3–2.4 | 无法事后证明「9/10 采全了」 |
| G17 | fork 同步 | 跟到 9/10 基线后再谈增量 | `Siqiho` fork 停在 7/17 | P0（治理） | `gh repo view` updatedAt；`git rev-parse` | 单独修 G1–G4 而不跟上游，会与 9 月语义分叉 |

---

## 5. 证据路径索引

### 5.1 本仓（当前）

```
README.md
VERSION
docs/features.md
docs/configuration.md
docs/custom-data-source.md
docs/deployment.md
tiers.yaml
.gitignore

backend/app/jobs/daily_pipeline.py          # 09:10 / 15:30 调度、run_now、laggard
backend/app/services/preferences.py        # G1 硬编码；15:30 默认
backend/app/services/kline_sync.py         # batch / 分钟流式落盘 / 「数十 GB」
backend/app/services/quote_service.py      # 实时 flush、overview 缓存失效、quote_ts
backend/app/services/pipeline_jobs.py      # job_store、30 分钟长任务
backend/app/services/repair_daily.py
backend/app/services/market_overview_builder.py   # G4 领涨键
backend/app/api/overview.py                # 5s TTL
backend/app/api/data.py                    # 画像、refresh-cache
backend/app/desktop.py                     # data/desktop.log
backend/app/config.py                      # 备份/迁移语义
backend/app/services/ext_data.py           # .json.bak

frontend/src/pages/Dashboard.tsx
frontend/src/pages/Data.tsx
frontend/src/lib/api.ts                    # OverviewMarket
frontend/src/lib/queryKeys.ts              # SSE 前缀
frontend/src/lib/useQuoteStream.ts
frontend/src/components/data/PageSettingsModal.tsx
```

### 5.2 上游对照（只读 fetch，未合入本仓）

```
upstream/main:backend/app/services/data_integrity.py
upstream/main:backend/app/jobs/daily_pipeline.py          # _prune_partial_enriched_partitions 等
upstream/main:backend/app/services/preferences.py         # 15:35；可读的 pull_a_share
upstream/main:docs/market-phase.md
upstream/main:docs/features.md                            # 盘后 15:35 表述
upstream/main:frontend/src/pages/Dashboard.tsx
upstream/main:frontend/src/pages/Data.tsx
```

### 5.3 上游 Issue / PR

| 编号 | 与本审计关系 |
| --- | --- |
| #216 | G1 开关失效（8/29 报，9/3 关） |
| #223 | G2 残缺 enriched（8/31 报，9/3 关） |
| #226 | G6 修复假成功（9/1 报，9/3 关） |
| #225 | G10 分钟 date=none |
| #208 / #241 / #7 | G8 内存 / 30g 邻近 |
| #245 | G11 自定义五档 |
| #294 / #298 | G4 / 量比，**9/10 当天** |
| #301 | G9，**9/11 仍 OPEN** |
| #23 | 早期「每次全量同步」诉求（6 月已关，管道已增量） |

---

## 6. 相关线程（只记发现，不实施）

### 6.1 数据台简化

- 本仓与上游源码/Issue **均无**字面「数据台」标识。产品内对应物是侧栏 **「数据」页**（`Data.tsx`），承担画像、同步、修正、扩展、调度。  
- **现状与「简化」相反**：本仓已有 8 张可拖拽画像卡 + 管道/历史/修正/重算/分钟/范围/扩展数据。上游 9/10 基线又叠了：  
  - `AdjFactorSyncGate`  
  - `RegimeConfigCard` + `/api/regime/coverage`  
  - 能力矩阵 / 路由数据源名  
  - 挖矿预检与补算入口（9/11）  
- `PageSettingsModal` 的「默认只显示前 5 张卡」是已有的**局部**降噪，不是信息架构简化。  
- **发现**：若存在「数据台简化」并行线程，它还没有落在 9/10 基线里；继续往 Data 页堆功能会加大 G14。本审计**不设计、不改页面**。

### 6.2 「30g」

全库（本仓 + 上游 `*.md/*.py/*.ts/*.tsx`）**没有** `30g` / `30G` / `30GB` / `数据台` 字符串。

最接近的一等证据：

```857:858:backend/app/services/kline_sync.py
    # 流式落盘: 每段拉完立即写盘, 内存峰值 = 单段 (而非全量)。
    # 全量攒内存曾导致 1 年全市场分钟 K OOM 卡死 (3 亿行 / 数十 GB)。
```

邻近事实：

- 分钟任务超时按 **30 分钟**（`LONG_JOB_TIMEOUT_S = 1800`），注释写数据量 ≈ 日 K × 240。  
- 除权兜底窗口在注释里出现「30 天」（ETF 路径；A 股实时分支兜底是 15 天）。  
- 生产 Issue 是 **2G/4G 内存 OOM**（#7、#208、#241），不是「必须 30G 机器」的官方门槛。  
- 回测 API 文案提到「约 1.8GB 内存则区间最多 6 个月」。

**发现**：把「30g」读成「分钟全市场约数十 GB 内存/磁盘峰值」与代码一致；读成「独立 30G 数据台项目」则**本仓库无证据**。不在此线程做存储治理或页面裁剪。

---

## 7. 建议下一步（记录，不执行）

按依赖顺序，供人工/后续代理选用：

1. **治理**：决定本 fork 是跟 `shy3130` 9/10+ 基线，还是长期分叉。跟上游能一次性消化 G1–G5、G10–G13 的大部分。  
2. **若暂不跟上游**：至少把 G1（开关）、G4（领涨键）做成最小补丁——改动面小、用户可见对。  
3. **正确性**：移植或复刻 `data_integrity` + `#223` 剪枝（G2/G3），否则看板数字在「自选实时 + 偶发停机」下不可信。  
4. **运维**：盘后默认改 15:35（G5）；修复任务在覆盖率/ lagging 超阈时报失败（G6）。  
5. **容量**：把「数十 GB 分钟 K」写成数据页/文档硬提示；默认关闭全市场分钟（G8 / 30g）。  
6. **数据台**：若要做简化，先出信息架构（画像 / 同步 / 高级修复三层），再动 `Data.tsx`；不要在本审计分支改 UI。  
7. **可复盘性**：对 `job_store` 增加 per-stage 覆盖行数；保留 N 日 `desktop.log` 轮转。没有这些，下一次「9/10 采没采全」仍然无法审计。  
8. **核对 #301**：即使跟上游 HEAD，也要人工确认全量分钟卡片在自定义源下是否仍恒灰。

---

## 8. 审计约束复核

| 约束 | 结果 |
| --- | --- |
| 不改应用代码 / 配置 / 依赖 / CI / 行为 | 遵守。仅新增本 Markdown。 |
| 不修复、不重构、不改运行时 | 遵守。§7 未执行。 |
| 数据台简化 / 30g 只记发现 | 遵守。见 §6。 |
| 工作区无 9/10 实盘日志与备份 | 已在假设 D 与 G16 写明，不编造采集结果。 |

---

*报告结束。对照提交：本仓 `34eaba3`（2026-07-17）↔ 上游 `54ef03ac`（2026-09-11，含 9/10 看板/数据合入）。*
