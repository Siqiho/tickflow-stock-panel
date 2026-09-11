# 数据链现版本优化审查（2026-09-09，用户澄清后）

- 主台：数据台。次台：用户台只作稳定入口，不改页面。
- 完整记录：本文件。能力目录 / 计划 / 开发日志：未更新（未新审 GitHub、未实施）。
- 次台短指针：无。入口仍是 `GET /api/f10/margin-trading`、`GET /api/kline/daily|minute`、`GET /api/reference/valuation-daily`。
- 本文件取代旧报告「独立脚本当终点」。旧容量与三证券样本仍有效。
- 模型：要求 Grok 4.6 + Extra High。无供应商回执，**未核验**。

只读源码与正式数据，只写本目录。未改产品/原包/`DATA_DIR`/规则/计划/日志，未打产品 HTTP/UI。

---

## 1. 首要结论

三步减法已在**当前脏主树**成立，不是新收益：GitHub 只对照、资金流默认不写 `stock.db`、`ext_data` 已拆项、Catalog 事后展示、查询直接读 Parquet。自采自存链已够短，不造总 Provider / 万能查询 / 发布事务，不撤原子写与来源追踪。

还能做的只有：**现有查询入口加可选只读分支，按需原地读选定离线数据集**。不能把原包塞进旧校验，也不能把独立脚本当产品。自采、整理、持续更新必须留。

| 问 | 答 |
| --- | --- |
| 可合并/可省 | 离线包不必再 Adapter→归一→再写 Parquet→lineage→Catalog；不新建 Provider；不拷 76GiB 进 `DATA_DIR`；不跨源/跨布局 union；ML/L1/L2 不进主链 |
| 必须保留 | 自采 Adapter、写路径单位校验、原子写+lineage、Catalog 目录/覆盖/来源、默认只读自有库 |
| 原包哪部分能直接用 | 两融 by_symbol 最值得接现有 GET；历史日线可补 2019 前对照；估值可独立读但非官方 PIT；分钟与因子不混入 |
| 怎样接入原有入口 | 默认读自有 `DATA_DIR`；显式 `source=offline_quantdb` 时按股票+日期读原文件并映射；缺文件只报该源不可用，不写回、不拼 0 |

这是**建议**。当前事实：查询只认 `DATA_DIR`，两融还会跑导入校验。

---

## 2. 坐标（独立核）

| 项 | 值 |
| --- | --- |
| HEAD | `31216dda527cd4ec177b9cbf6fd1c524dbadbe82`（2026-08-12）。实现在脏树 |
| 无 `data_sync/` | 成立 |
| 三步文件 | `provenance_registry.py` 未跟踪；`fund_flow.py:651` 默认 `allow_local_fallback=False`；Catalog 三文件已改 |
| 自有日 K | 1743 分区，`2019-07-05`～`2026-09-08` |
| 自有两融 | `f10/stock_margin_trading/part.parquet` 69614B，8 只至 `2026-08-04` |
| 原包 | 复用已核 81,726,698,819B；原生 `股票数据/stockdb` 不存在 |
| 用户台 | `api.ts:3287` 只有 POST sync；查询入口已是 GET 与 `user_console_data.py:312-318`，不必改前端 |

---

## 3. 调用层级（层数不是缺陷）

自采写：真实源 → 各 Adapter（`kline_sync` / `margin_trading_public` / TDX / 东财资金流）→ 就近归一 → `atomic_write_parquet` + lineage → 写后 `refresh_after_mutation`（只投影）。

查询：`GET` → `query_*` / `repo.get_*` → 扫自有 Parquet。`repository.py` 不含 catalog。`serving_ready`（`service.py:432`）和 `catalog_stale`（`provenance.py:209-216`）只进目录文案，**不挡查询**。

现有耦合（不是三步回退）：

- 日 K 空窗现场拉 TickFlow（`kline.py:236-238`）。`_scan_daily_symbol` 失败吞成空（`repository.py:1196-1198`），可能误触发。
- 自选历史分钟 miss 会 TDX 写入并刷新 Catalog（`kline.py:1021-1045`）。`get_minute` 失败也吞空（`repository.py:1110-1112`）。
- 两融固定 `DATA_DIR/.../part.parquet` 且 `_validate_frame`（`margin_trading_public.py:329-341`）。外层 `source` 写死 `local`（`stock_f10.py:52-56`）。
- 资金流坏文件 `continue`（`fund_flow.py:1635-1638`）。

映射各写各的：两融 `normalize_margin_trading_rows`、日 K `_normalize_daily`、分钟 `persist_historical_minute`。离线字段/单位不同，不能复用写校验。

---

## 4. 六环节

| 环节 | 现行职责 | 本次可合并/绕过/保留 | 可用性/稳定性 | 最小改动 |
| --- | --- | --- | --- | --- |
| 真实源 | 自采 TickFlow/东财/TDX；原包是第二库存 | 留自采。原包不当第三生产者、不自动下载 | 自更新不断 | 无 |
| Adapter | 各源各写 | 离线绕过网络 Adapter。不新建总 Adapter | 少误写 | 无新模块 |
| 字段/单位 | 写时各函数归一；东财空值变 0 | **建议**查询旁一个映射。写校验不用于读离线 | 避名称错位和假 0 | 见工作包 |
| 安全写+来源 | 原子替换+lineage；写后刷新目录 | **保留。** 原包只读 | 自有库不被污染 | 读路径禁止 persist |
| Catalog | 事后目录/覆盖/来源 | **留展示。** 不扫 80GB；索引陈旧不得判查询失败 | 查询本就不读 Catalog | 不改查询语义 |
| 本地查询 | 只读 `DATA_DIR` | **建议**现有 GET 加显式 source | 按股票日期读选定离线行 | `query_margin_trading` + `stock_f10.py` |

采集→写盘**已够简单，不值得改**。要改的是查询不读第二源，以及把导入校验套在查询上。

---

## 5. 推荐最小工作方式（建议，非当前事实）

两条入口，一个服务：

1. **自采**（已有）：显式 sync / 盘后管道 → 归一 → 原子写 `DATA_DIR` + lineage → Catalog 展示。
2. **离线**（建议）：只读根指向原路径，按 `source+dataset+layout+symbol+日期` 定位；**不导入、不复制、不回写**。

消费者仍走原有数据服务。映射只放在该查询函数旁。Catalog 只回答自有库有什么、从哪来、覆盖到哪；文件读得出就能查。重叠日不混值：调用方选源，默认自有。原包缺失/移动：该 source 不可用，自有照旧。不自动下载、不拼 0。

当前没有 source 分支；两融查询先 `_validate_frame`；GET 不报真实离线源；数据页只采集。

---

## 6. 原包可直接采用程度

复用旧 E1：81.727GB / 76.114GiB；QuantDB 59.607GB，ML 40.869GB=68.6%；by_date 8.623GB 仍仅候选。按数据集选，不递归 union。

| 类别 | 级别 | 依据 | 接入 |
| --- | --- | --- | --- |
| 两融 `by_symbol` | **小适配可供现有功能** | 3 证券各 250 共同日：`finance_repay`→融券卖出量，`slo_sell_amount×10000`→融资偿还额；数量误差 0；金额浮点/舍入。缺余额两列。不能锁全市场 | 现有 GET 加 `source=offline_quantdb`。读允许 null，禁止补 0。不扫 by_date |
| 历史日线 StockDB | **独立可读，对照可补缺** | 300502@20260804 OHLC 同；量约 ×100。StockDB 至 08-25，自有至 09-08 | 不要打 `GET /api/kline/daily`（空窗会拉网写入）。补 2019 前须另开只读分支并标单位 |
| 估值 | **独立可读，不混官方表** | 共同日收盘相等；QuantDB 有 PE/PB，自有全 null。收盘≠PIT | 可另源展示，禁止回填 `valuation_daily` |
| 分钟 | **不适合直接混入** | 09:31–15:00 vs 09:30–14:59；bar/量额不同 | 不要进 `GET /api/kline/minute`（miss 会 persist） |
| 因子/ML | 独立可读，不进主链 | API 不消费 | 不接入 |
| 修复包 | 候选 overlay | 不是第三份行情 | 不默认读 |

默认自有（更新、可续采）。离线仅显式 source。禁止跨源拼行。

---

## 7. 稳定可用：最低检查

复跑 `check_offline_reads.py` 一次：`2026-09-09T15:27:04`，exit 0，无 HTTP/校验/写。三证券 overlap 各 250；数量 max_abs=0；600756 `finance_net` 相对误差约 1.01%（分母 297）。估值 inner=9、收盘相等、自有 PE=0。分钟时间标签仍错位。StockDB 1 行。耗时 0.02–0.55s，**小范围、受缓存影响，不能证明 80GB 全库稳定**。

内存边界（未写真实文件）：null→`TypeError`；补 0→`margin balance mismatch`；缺文件→空表；空窗口→0；重复键失败。故不能把原包塞旧查询，也不能用写校验当读校验。

单股 by_symbol 约 100KB，现查不必缓存。只读根须显式配置。索引陈旧只影响定位，不应让已存在 parquet 变失败。非全市场、非负载基准。

---

## 8. 三个改动里只选一个包

均未实施：1. **选这个**——现有两融查询加可选只读分支。2. 写/读校验拆开（可并进 1）。3. 日 K 空窗误拉网，本轮不选。

### `D-OFFLINE-MARGIN-API`（建议 / 不启动）

不写入计划，不进入 `active`。目标：现有 `GET /api/f10/margin-trading` 按股票+日期返回选定离线两融；来源/截至日/缺失明确；自有东财默认可查可采；原包无写无整包复制；缺文件不污染自有库。

- 改：`margin_trading_public.py`（`query_margin_trading` 加显式 `source`；默认仍 `ARTIFACT_RELATIVE`；离线 by_symbol + 就近映射；**读路径不调用现行 `_validate_frame`**）、`stock_f10.py`（参数 `source`，回真实 source / `as_of` / `unavailable`；缺文件 200+空+原因，不写盘）、两测试。可选：`user_console_data.py` 增加 `source`（同一 GET）。
- 配置：只读根，默认关闭离线分支。
- 不改：Catalog 扫描、`kline_sync`、`repository`、`DATA_DIR`、采集卡、计划/日志。用户台不必改；数据页卡是采集入口，查询验收走已有 GET。不要新 UI，也不把脚本重跑写成集成完成。

验收：无 `source` 仍出东财本地行；`source=offline_quantdb` 出映射行、真实 source、`as_of`=文件最大日、缺列保持 null；缺文件则该源不可用，自有 `part.parquet` 不变，Catalog 不因查询刷新。零网络、不扫 by_date、不写 lineage。

非目标：不接分钟/估值/日 K 写路径；不删 8.62GB；不 union；不声称可回测；不启动 `D-P0-01`。

---

## 9. 限制

未全量 hash、未扫分钟全市场、未跑产品测试/HTTP/浏览器。三证券不是全市场容差。旧「不再开第四步减法」指不再拆架构；本建议是查询可选分支，不是第四步工单。
