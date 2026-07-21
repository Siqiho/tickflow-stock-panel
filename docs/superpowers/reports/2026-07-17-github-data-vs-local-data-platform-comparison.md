# GitHub 数据参考 vs 本地数据台对照报告

> 生成日期：2026-07-17（Asia/Shanghai）  
> 核查方式：只读  
> 主依据：
> - `/Users/simon/Trading/GitHub项目借鉴记录.md`
> - `/Users/simon/Trading/one-trading/.worktrees/exchange-daily-feasibility-b11/docs/superpowers/specs/2026-07-16-owned-source-matrix【codex】.md`
> - 本地正式数据：`/Users/simon/Trading/one-trading/data`
> - 本地主代码：`/Users/simon/Trading/one-trading`（dirty main）
> - 候选 worktree adapters / lab（B01–B11）
>
> 结论口径：  
> **“GitHub 项目提供的数据”≠“GitHub 仓库本身吐出的行情文件”**。  
> 这些项目大多只是**底层取数地图**（endpoint / 字段 / 单位 / 协议）。  
> 真正数据产地是 TickFlow、通达信 host、东财、新浪、Tushare、BaoStock、交易所等。  
> 本报告对照的是：  
> 1）参考项目声称/实现的数据能力；  
> 2）one-trading 本地数据台**实际已有代码/正式落库**。

---

## 0. 一句话总结论

**本地正式数据台目前并没有“包含这些 GitHub 项目里的数据”。**

更准确地说：

| 层 | 现状 |
|---|---|
| 正式落库 `data/` | **几乎全部来自 TickFlow 同步**（个股日线、指数日线、证券列表、同花顺概念/行业扩展） |
| 生产运行时 Provider | **只有 TickFlow** |
| GitHub 参考项目 | 多数只落到 **source matrix / 文档 / 禁用态 lab adapter** |
| 与 GitHub 候选能力重叠的正式数据 | **字段级“看起来像同一类行情”**（如日线 OHLCV+amount），**来源并不相同** |
| 资金流 / 筹码 / 人气 / 抢筹 / 分钟 / 财务 / 复权因子表 | **正式数据中基本没有** |

所以：  
**不是“已经把 GitHub 项目的数据接进来了”，而是“参考了它们的取数方法，并开始自建替换路径；生产数据仍是 TickFlow”。**

---

## 1. 本地正式数据台现状（深挖结果）

### 1.1 目录与填充情况

路径：`/Users/simon/Trading/one-trading/data`

| 数据集 | 文件数 / Parquet | 状态 | 实际内容摘要 |
|---|---:|---|---|
| `kline_daily` | 245 / 245 | **有数据** | 股票日线；日期 `2025-07-03` → `2026-07-07` |
| `kline_daily_enriched` | 245 / 245 | **有数据** | 日线 + `raw_*` / 换手 / 连板等 |
| `kline_index_daily` | 245 / 245 | **有数据** | 指数日线 |
| `kline_index_enriched` | 245 / 245 | **有数据** | 指数 enriched |
| `instruments` | 1 / 1 | **有数据** | 5529 只股票（SH 2308 / SZ 2896 / BJ 325） |
| `instruments_index` | 1 / 1 | **有数据** | 指数维表 |
| `ext_data/ext_gn_ths` | 2 / 1 | **有数据** | 同花顺概念分类 |
| `ext_data/ext_hy_ths` | 2 / 1 | **有数据** | 同花顺行业分类 |
| `job_store` | 11 / 0 | 任务日志 | 同步任务成功记录 |
| `user_data` | 3 / 1 | 用户态 | 自选股、策略缓存等 |
| `capabilities.json` | 1 | 有 | 当前探测仅 daily by_symbol / batch |
| `adj_factor` | 0 | **空** | 无复权因子表 |
| `adj_factor_etf` | 0 | **空** | |
| `depth5` | 0 | **空** | 无五档 |
| `financials/*` | 0 | **空** | 无财务三表/指标 |
| `kline_minute` | 0 | **空** | 无分钟线 |
| `kline_etf_*` | 0 | **空** | 无 ETF 行情 |
| `pools` / `screener_results` / `backtest_results` / `ai_cache` | 0 | **空** | |

总规模：约 **1001 文件 / 985 Parquet**。

### 1.2 核心字段深挖

#### 股票日线 `kline_daily`（最新分区 `2026-07-07`）

- 行数：5417
- 列：`symbol, date, open, high, low, close, volume, amount`
- 交易所分布：SZ 2891 / SH 2203 / BJ 323
- 无 `provider` / `source` 列；来源靠同步链路与 repository 视图默认写成 `tickflow`
- 单位启发式（`000001.SZ`）：
  - `volume=805221`, `amount=840465778`, 均价约 10.465
  - `amount / 均价 / volume ≈ 99.74`
  - 更像 **成交量单位=手（100 股）**，不是 easy_tdx 文档常说的“股”
- 这与 Tushare 文档的 `vol=手` 形态接近，但**不能据此说本地已接入 Tushare**；它只说明 TickFlow 返回的 volume 语义更像“手”

#### 股票 enriched `kline_daily_enriched`

- 额外列：`raw_close, raw_high, raw_low, turnover_rate, consecutive_limit_ups, consecutive_limit_downs`
- 最新日 `close == raw_close` 比例 = **1.0**
- 说明：当前样本上看，**没有观察到有效复权价差**；更像 raw 或复权因子恒为 1 的落库结果

#### 指数日线

- 最新日约 598 行
- 字段同为 OHLCV + amount
- 同步日志：`指数 612 只 / ETF 0 只`

#### 证券列表 `instruments`

- 5529 只，`type=stock`
- 覆盖 SH/SZ/BJ
- 最新日日线比 instruments 少 112 只（多为停牌/无成交等，日线不写行是正常现象）

#### 扩展数据 `ext_data`

- `ext_gn_ths`：同花顺概念；拉取 URL `https://files.688798.xyz/ths/concepts.json`
- `ext_hy_ths`：同花顺行业；拉取 URL `https://files.688798.xyz/ths/industries.json`
- 这是 **TickFlow 工作台自带扩展数据机制**，不是 a-stock-data / go-stock 正式接入结果
- `pull.enabled=false`，当前是历史快照

#### capabilities.json

```json
{
  "label": "None",
  "capabilities": {
    "kline.daily.by_symbol": {"rpm": 60, "batch": 1},
    "kline.daily.batch": {"rpm": 60, "batch": 100}
  },
  "probe_log": ["无 API Key(无档 · free-api 服务器)"]
}
```

含义：当前运行面只探测到 **日线** 能力，且是 **无 Key / free-api** 状态；财务、分钟、depth、复权等正式能力未在此文件中开通。

### 1.3 同步链路证据（job_store）

最近成功任务显示同步阶段只有：

1. `sync_instruments`（约 5528–5535 只）
2. `resolve_universe`
3. `sync_daily`
4. `compute_enriched`
5. `sync_index`
6. `refresh_views`

**没有** fund_flow / chips / popularity / minute / financials / adj_factor / depth 同步阶段。

代码侧 `backend/app/tickflow/repository.py` 的统一视图也默认标注：

```text
'tickflow' AS source
```

### 1.4 dirty main 代码面 vs worktree

| 位置 | 数据台实现 |
|---|---|
| dirty main `backend/app/data_providers/` | 只有 `tickflow_provider` + 基础 schema/normalizer/registry |
| B01–B11 worktrees | 另有 `easy_tdx`、`eastmoney_daily`、`tdx_protocol/codec`、lab runner |
| 生产 composition | 文档与测试一致：**TickFlow only** |
| 正式 `data/` | **没有** easy_tdx / eastmoney / sina / baostock / tushare 写入痕迹 |

---

## 2. 对照基准：工作区记录了哪些 GitHub 数据参考

主记录文件：

`/Users/simon/Trading/GitHub项目借鉴记录.md`

### 2.1 与“数据台/行情替换”直接相关的项目（重点）

| GitHub 项目 | 角色 | 真正底层产地（不是 GitHub） | 在 one-trading 的落点 |
|---|---|---|---|
| [shy3130/tickflow-stock-panel](https://github.com/shy3130/tickflow-stock-panel) | 上游工作台血统 | **TickFlow 云端 API** | **当前生产唯一数据源** |
| [handsomejustin/easy_tdx](https://github.com/handsomejustin/easy_tdx) | TDX 协议地图 | 通达信行情 host:7709 | worktree 禁用态 adapter/lab；正式数据无 |
| [rainx/pytdx](https://github.com/rainx/pytdx) / [injoyai/tdx](https://github.com/injoyai/tdx) | host / BSE 快照情报 | TDX / 北交所当前快照 | 仅 evidence，无 adapter 落库 |
| [ArvinLovegood/go-stock](https://github.com/ArvinLovegood/go-stock) | 东财/新浪/腾讯/TDX API 地图 | 东财、新浪、腾讯、TDX 等 | EastMoney 日线 target-disabled；新浪 JSONP 已排除 |
| [akfamily/akshare](https://github.com/akfamily/akshare) | 新浪 static KLC 地图 | 新浪财经 | `unavailable / written-permission-missing` |
| [millken/baostock](https://github.com/millken/baostock) | BaoStock 协议地图 | BaoStock 官方服务 | `unavailable` |
| [QYQSDTC/Money-Come-Terminal](https://github.com/QYQSDTC/Money-Come-Terminal) | Tushare 调用链地图 | Tushare Pro | `unavailable` |
| [simonlin1212/a-stock-data](https://github.com/simonlin1212/a-stock-data) | 资金流/筹码/人气地图 | 东财等 | matrix 全 `unavailable` |
| [1nchaos/adata](https://github.com/1nchaos/adata) | 资金流/多源 fallback 地图 | 东财等 | matrix `unavailable` / design-only |
| [finvfamily/finshare](https://github.com/finvfamily/finshare) | 多源韧性 + 资金流字段 | 东财/必盈等 | design-only，未进正式数据 |
| [myhhub/stock](https://github.com/myhhub/stock) | 筹码/抢筹/选股字段 | 东财等 | **主要落到 go-stock，不是 one-trading 正式 data/** |

### 2.2 重要边界

- go-stock 本地仓库 `/Users/simon/Trading/go-stock` 自己接了很多东财/新浪/腾讯/Tushare/TDX 能力；  
  **那不等于 one-trading 数据台已经包含这些数据。**
- one-trading 当前正式数据是 **TickFlow-stock-panel 路线** 的落库，不是 go-stock 的 SQLite 镜像。

---

## 3. 数据能力对照总表（一致 / 不一致）

> 判定口径：  
> - **正式一致**：本地 `data/` 已有同类数据，且生产可用  
> - **能力形似但来源不同**：字段看起来同类，但不是该 GitHub 底层源  
> - **代码/文档仅有**：worktree adapter、matrix、design  
> - **缺失**：本地无正式数据、无生产接入

| 数据能力 | 主要参考 GitHub | 真实底层 | 本地正式 data/ | 本地代码/平台 | 一致性判定 |
|---|---|---|---|---|---|
| 股票日线 OHLCV+amount | easy_tdx / go-stock / akshare / Money-Come / baostock | 计划：TDX/东财/新浪/Tushare/BaoStock；**现实：TickFlow** | **有**（245 日，约 5400+ 股/日） | TickFlow 生产；easy_tdx/eastmoney 禁用 | **能力形似，来源不一致** |
| 指数日线 | TickFlow 上游；go-stock 也有指数链路 | TickFlow | **有** | TickFlow | **正式一致于 TickFlow，不是 GitHub 自有源** |
| ETF 日线/分钟 | TickFlow / go-stock / a-stock-data 等 | TickFlow 或东财等 | **空** | Cap 有定义，数据无 | **不一致 / 缺失** |
| 分钟线 | easy_tdx / go-stock / TickFlow | TDX/东财/TickFlow | **空** | Cap 有定义，数据无 | **不一致 / 缺失** |
| 实时报价 / 盘口 depth5 | easy_tdx / go-stock / TickFlow | TDX/新浪/腾讯/TickFlow | **空** | Cap 有 `depth5`，数据无 | **不一致 / 缺失** |
| 复权因子表 | TickFlow / 东财 / Tushare | TickFlow ex_factors 等 | **空** | repository 预留目录 | **不一致 / 缺失** |
| 财务三表/指标 | TickFlow / go-stock F10 / finshare / Money-Come | TickFlow/Tushare/东财 | **空** | Cap 有 `financial`，数据无 | **不一致 / 缺失** |
| 证券列表 | TickFlow / Tushare stock_basic / 交易所 | TickFlow | **有**（5529） | TickFlow | **正式有，来源是 TickFlow** |
| 交易日历独立表 | Tushare / adata / 交易所 | 各源 | **未见独立 calendar 数据集** | 无正式 owned calendar provider | **不一致 / 缺失** |
| 资金流 fund_flow | a-stock-data / adata / finshare / go-stock | 东财等 | **无对应目录/文件** | matrix `unavailable` | **不一致 / 缺失** |
| 筹码 chips | a-stock-data / myhhub/stock / go-stock | 东财等 | **无** | matrix `unavailable` | **不一致 / 缺失** |
| 人气 popularity | a-stock-data | 东财/同花顺 hot list | **无** | matrix `unavailable` | **不一致 / 缺失** |
| 抢筹 chip race | myhhub/stock → go-stock | 东财等 | **one-trading 无** | 在 go-stock，不在 one-trading data | **不一致 / 缺失** |
| 概念/行业分类 | go-stock / finshare / 同花顺扩展 | 同花顺托管 JSON（经 TickFlow 扩展） | **有** `ext_gn_ths` / `ext_hy_ths` | TickFlow 扩展机制 | **有同类扩展，但不是 a-stock-data 接入** |
| 龙虎榜 / 异动 / 电报资讯 | go-stock | 东财/资讯源 | **one-trading 正式 data 无** | 非本数据台正式范围 | **不一致 / 缺失** |
| 多源 cooldown/fallback 方法 | finshare / adata / Money-Come | 方法，不是行情 | 无生产多 owned-provider fallback | 设计有，生产未用 | **方法未生产化** |

---

## 4. 按 GitHub 项目逐项深挖

### 4.1 `shy3130/tickflow-stock-panel` → TickFlow

**项目提供/代表的数据能力**

- 日线 / 分钟 / 实时 / quote / financial / adj_factor / depth / websocket 等（视 Key 档位）
- 本地 workbench 的 Parquet 分区模型、扩展数据、同步 job

**本地是否包含**

| 项 | 结果 |
|---|---|
| 股票日线 | **是** |
| 指数日线 | **是** |
| 证券列表 | **是** |
| 同花顺概念/行业 ext | **是** |
| 分钟 / quote / financial / adj_factor / ETF | **否（目录空或未同步）** |
| 生产 Provider | **是，且唯一** |

**一致性**

- **本地正式数据与该上游工作台路线一致。**
- 当前 `capabilities.json` 仅 daily，说明本机实际可用档位很窄（无 Key / free-api）。

---

### 4.2 `handsomejustin/easy_tdx`（+ pytdx / injoyai）

**项目提供的数据能力（地图）**

- TDX TCP 日线/分钟/实时
- host 池、ping、bars 分页
- 字段：`open/close/high/low/vol/amount/...`
- 文档语义常为 volume=股、amount=元

**本地是否包含 easy_tdx 数据**

| 项 | 结果 |
|---|---|
| 正式 `data/` 由 TDX 写入 | **否** |
| 生产 selection 含 easy_tdx | **否** |
| worktree 有自有 adapter/lab | **是（target-disabled）** |
| 真实 lab 过线 | **否**（setup_closed / no-setup-success） |

**与本地日线是否“数据一致”**

- 字段集合：本地日线也有 OHLCV+amount → **字段级同类**
- 单位：本地 volume 更像“手”，easy_tdx 常见“股” → **单位语义不一致风险高**
- 来源：本地是 TickFlow，不是 TDX host → **来源不一致**
- 覆盖：本地有 BJ；TDX lab 未证明生产级三市场+退市历史 → **覆盖未对齐**

**结论**：只借鉴了协议/host 情报和禁用态实现，**没有把 easy_tdx 数据装进本地数据台。**

---

### 4.3 `ArvinLovegood/go-stock`

**项目提供的数据能力**

- K 线 fallback：TDX / 东财 / 新浪 / 腾讯
- 实时：新浪 / 腾讯 / 东财 / Tushare
- 资金流：东财 daykline / 排行 / 板块
- F10、资讯、自选、龙虎榜等
- 本地 go-stock 还有筹码/抢筹（部分来自 myhhub/stock 借鉴）

**本地 one-trading 是否包含**

| 能力 | one-trading 正式 data | 说明 |
|---|---|---|
| 东财 raw 日线 | **否** | B04–B06 仅 target-disabled；B06 0 可用行 |
| 新浪 JSONP 日线 | **否** | 缺 amount，写 Adapter 前排除 |
| 腾讯行情 | **否** | 未作 one-trading 生产源 |
| 资金流/F10/龙虎榜 | **否** | 无对应正式落库 |
| 日线/指数/列表 | **有，但来自 TickFlow** | 仅能力重叠 |

**一致性**

- go-stock 与 one-trading **不是同一数据湖**。
- one-trading 只借了 go-stock 的 **EastMoney endpoint 情报** 做禁用态实验。
- 因此不能说“本地数据台已经包含 go-stock 的数据”。

---

### 4.4 `akfamily/akshare`（新浪 static）

**项目地图能力**

- 新浪静态历史日线，字段含 amount
- 文档单位：volume=股，amount=元；可含 qfq/hfq 语义

**本地**

- 无新浪 Adapter
- 无新浪写入
- 状态：`unavailable / written-permission-missing`

**与本地日线**

- 都有 date/OHLCV/amount → 字段形似
- 但本地不是新浪源；且本地 volume 单位更像手，和 AKShare 文档“股”不一致

---

### 4.5 `millken/baostock` / BaoStock 官方

**地图能力**

- 日线含 amount
- 文档称可查退市前历史
- amount=CNY

**本地**

- 无 BaoStock 客户端调用
- 无相关落库
- `unavailable / compatible-client-permission-and-bj-coverage-missing`

**一致性**：完全未包含。

---

### 4.6 `QYQSDTC/Money-Come-Terminal` → Tushare Pro

**地图能力**

- `daily`：`ts_code,trade_date,OHLC,pre_close,vol,amount...`
- `vol=手`，`amount=千元`
- stock_basic / 日历等（视积分）

**本地**

- 未读 Token，未调 API，无 Adapter
- `unavailable / production-license-and-coverage-missing`

**与本地日线的“形似点”**

- 本地 volume 启发式也像“手”
- 但 amount 本地像“元”量级（`000001` amount≈8.4e8），而 Tushare amount 常为千元  
  → 若真是 Tushare，amount 量级通常小 1000 倍；**更支持“不是 Tushare 原样落库”**
- 结论：形似单位片段 ≠ 已接入 Tushare

---

### 4.7 `simonlin1212/a-stock-data`

**地图能力**

- 资金流：东财 `fflow/kline`
- 人气：东财 hot rank / 同花顺 hot list
- 筹码：文档层描述，matrix 判定 endpoint 证据不足

**本地**

- `ext_fund_flow` / `ext_chips` / `ext_popularity`：**无正式数据**
- matrix 全部 `unavailable`
- 仅 source intelligence / 契约测试意图

**一致性**：未包含。

---

### 4.8 `1nchaos/adata` / `finvfamily/finshare`

**地图能力**

- 资金流字段与东财 endpoint
- 多源 fallback / cooldown / router 方法论

**本地**

- 无资金流落库
- 无生产 owned 多源 fallback
- finshare/adata 对 one-trading 基本是 design-only

**一致性**：方法有记录，数据未包含。

---

### 4.9 `myhhub/stock`

**地图能力**

- 抢筹、筹码获利比例、成本集中度、综合选股字段

**本地 one-trading**

- 无对应数据集

**落点**

- 主要在 `/Users/simon/Trading/go-stock`，不是 one-trading 数据台

---

## 5. “一致”与“不一致”清单（便于直接判断）

### 5.1 一致 / 部分一致

1. **工作台数据模型一致（与 TickFlow 上游）**  
   分区日线、enriched、instruments、ext_data、job_store 这一套，与 tickflow-stock-panel 路线一致。

2. **日线基础字段集合一致（跨很多项目）**  
   几乎所有候选源和本地正式日线都围绕：
   `symbol/date/open/high/low/close/volume/amount`
   这是“行情常识一致”，不是“已接入某 GitHub 源”。

3. **三市场股票列表覆盖形似**  
   本地 instruments 含 SH/SZ/BJ；多个候选源也声称覆盖 A 股。  
   但本地列表来自 TickFlow 同步，不是 Tushare/交易所官方 Adapter。

4. **概念/行业扩展“有数据”**  
   本地有同花顺概念/行业 parquet；  
   这与“特色扩展”方向一致，但来源是 TickFlow 扩展拉取 URL，不是 a-stock-data。

### 5.2 不一致 / 未包含

1. **来源身份不一致**  
   本地正式数据 source 语义是 TickFlow；  
   不是 easy_tdx / eastmoney_http / sina / baostock / tushare。

2. **单位语义未对齐**  
   - 本地 volume ≈ 手  
   - easy_tdx / 新浪文档常为 股  
   - Tushare vol=手、amount=千元，但本地 amount 量级像元  
   → 不能拿本地日线当任何 GitHub 候选源的等价样本

3. **复权语义不一致/缺失**  
   - 无 `adj_factor` 表  
   - enriched 中 close 与 raw_close 完全相同  
   - 东财 qfq/hfq、新浪复权、Tushare 复权均未进入正式数据

4. **GitHub 特色数据几乎全缺**  
   资金流、筹码、人气、抢筹、龙虎榜、异动资讯：one-trading 正式 data 均无。

5. **实时/分钟/财务/ETF/depth 全缺**  
   这些在多个 GitHub 项目和 TickFlow Cap 枚举里都有，但本地正式落库为空。

6. **代码接入层级不一致**  
   - dirty main：几乎只有 TickFlow provider  
   - worktree：有禁用态 owned adapters  
   - 正式 data：没有 owned provider 产物

7. **go-stock 有、one-trading 无**  
   若拿本机 go-stock 的多源数据能力来比 one-trading 数据台，会严重高估 one-trading 当前数据覆盖。

---

## 6. “哪些数据来源于哪个 GitHub 项目”——正确归因

| 本地已有数据 | 真正来源 | 是否来自某 GitHub 项目的底层接入 | 备注 |
|---|---|---|---|
| `kline_daily` | **TickFlow API 同步** | 否（只与 tickflow-stock-panel 工作台同源） | 不是 easy_tdx/go-stock/akshare |
| `kline_daily_enriched` | TickFlow 日线 + 本地计算 | 否 | 指标/连板等本地派生 |
| `kline_index_daily` | TickFlow | 否 | |
| `instruments` | TickFlow | 否 | |
| `ext_gn_ths` / `ext_hy_ths` | TickFlow 扩展 URL（同花顺分类文件） | 否 | URL 托管点不是 GitHub |
| `user_data/*` | 本地用户操作 | 否 | |
| `job_store/*` | 本地同步任务 | 否 | |
| worktree `easy_tdx` adapter 代码 | 自研，协议情报来自 easy_tdx/pytdx | **代码情报来自 GitHub，数据未落库** | target-disabled |
| worktree `eastmoney_daily` adapter 代码 | 自研，端点情报来自 go-stock | **代码情报来自 GitHub，数据未落库** | target-disabled |
| 资金流/筹码/人气 | — | 无 | 仅 matrix 记录 GitHub 地图 |

**硬结论：**

> 本地正式数据台当前**没有**“来自 easy_tdx/go-stock/akshare/baostock/tushare/a-stock-data/adata/finshare 的生产数据”。  
> 它有的是 **TickFlow 数据 + 本地派生/用户数据**；  
> GitHub 项目贡献的是 **替换路线的情报和少量禁用态代码**，不是现成数据包。

---

## 7. 对“是否已经包含这些项目里的数据”的直接回答

### 如果你问的是“数据内容有没有装进来”

**基本没有。**  
正式 `data/` 不包含这些 GitHub 候选源写入的行情/特色数据。

### 如果你问的是“有没有同类数据能力”

**只有部分同类：**

- 有：股票日线、指数日线、证券列表、同花顺概念/行业
- 无：分钟、实时/depth、复权因子表、财务、ETF、资金流、筹码、人气、抢筹

而且“有”的那部分，来源是 TickFlow，不是对应 GitHub 底层。

### 如果你问的是“有没有把方法论/端点接进平台”

**有限有：**

- Source Matrix 完整记录了多项目端点与否决原因
- easy_tdx / eastmoney 有 worktree 级自有 adapter/lab
- 全部未成为生产默认源，也未写入正式 data

---

## 8. 建议阅读顺序 / 相关文件

1. 本报告：  
   `docs/superpowers/reports/2026-07-17-github-data-vs-local-data-platform-comparison.md`
2. GitHub 借鉴总账：  
   `/Users/simon/Trading/GitHub项目借鉴记录.md`
3. Source Matrix：  
   `.worktrees/exchange-daily-feasibility-b11/docs/superpowers/specs/2026-07-16-owned-source-matrix【codex】.md`
4. 替换设计：  
   `.worktrees/exchange-daily-feasibility-b11/docs/superpowers/specs/2026-07-16-tickflow-equivalence-replacement-and-retirement-design.md`
5. 正式数据本体：  
   `/Users/simon/Trading/one-trading/data`

---

## 9. 核查限制（诚实边界）

1. 未对 TickFlow 云端原始响应做在线抓包；来源判断依据是：
   - repository 固定 `tickflow` source
   - job_store 同步阶段
   - capabilities / free-api 探针
   - 无 owned provider 生产注册
2. 未把本地日线与东财/新浪/Tushare 做逐标的数值 diff（因为本地并没有这些源的并行落库可对）。
3. go-stock 本地库有更多数据能力，但本报告默认对照对象是 **one-trading 数据台**，不是整个 Trading 工作区所有项目。
4. worktree 中的 lab 临时目录不计入正式数据台。

---

## 10. 最终判断

**本地 one-trading 数据台 ≠ 已整合 GitHub 项目数据包。**

它现在是：

```text
TickFlow 生产数据
+ 本地 enriched/用户数据
+（旁路）GitHub 情报驱动的禁用态自有 adapter 实验
```

而不是：

```text
easy_tdx + go-stock + akshare + tushare + a-stock-data + ... 的并集数据湖
```

若目标仍是“参考 GitHub 底层来源，由 one-trading 自主实现并最终停用 TickFlow”，  
当前完成度应表述为：

> **情报与门禁完成度高；正式数据替换完成度接近零。**
