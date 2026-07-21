# trading_calendar 单独生产发布清单

- **状态：** 待你确认（本文件只是清单，**不执行**生产写入）
- **日期：** 2026-07-21
- **代码基线：** `42a58ab`（含 M5 Lab + 二次源对照 + live 复验文档）
- **范围：** 仅 `trading_calendar`
- **明确排除：** `instrument_status_history`、`listing_delisting_events`、目录/工作台注册、部署、远端 merge/push、付费源

---

## 0. 一句话结论

Lab 证据已足够支持“**讨论并在确认后单独发布 trading_calendar**”。  
**当前默认仍是 NO-GO 写入生产**，必须你明确回复批准后，才按本清单执行。

推荐首发窗口（与已复验 live 双源一致）：

- **首发覆盖：** `2025-01-01` … `2026-07-21`（可按你确认调整）
- **主生产者：** 深交所 monthList（`szse_month_list`）
- **二次校验：** 腾讯 `sh000001` 开市日序列（代理，不是上交所官方 API）
- **正式落盘路径：** `data/reference/trading_calendar/calendar.parquet`
- **unit_version：** `trading_calendar_v1`

---

## 1. 已具备的证据（无需再争论的部分）

来源：live 复验报告  
`docs/superpowers/reports/2026-07-21-m5-calendar-live-reverify-go-no-go.md`

| 项 | 结果 |
|---|---|
| 深交所 live 全窗口可拉 | 2025-01…2026-07，19 个月无缺失 |
| 腾讯 SH/SZ 开市日一致 | 是 |
| 深交所开市日 == 腾讯 SH | `2025-01-01`…`2026-07-21` 均为 **374** 天，差异 0 |
| 旧隔离缓存是否被网络写坏 | 否；与新鲜 live 在重叠段完全一致 |
| 生产是否已有 reference | 否（`data/reference` 不存在） |
| 上交所官方机读日历 | 仍不可用（SOA null） |

---

## 2. 发布前门禁（全部勾选后才允许写生产）

### 2.1 授权门禁（必须你口头/文字确认）

- [ ] **A1** 明确批准：允许写入生产  
  `/Users/simon/Trading/one-trading/data/reference/trading_calendar/`
- [ ] **A2** 确认首发窗口：默认 `2025-01-01` … `2026-07-21`（或你指定）
- [ ] **A3** 确认本轮**只发** `trading_calendar`，不发 listing/status
- [ ] **A4** 确认本轮**不**注册工作台目录、**不**切换 3011/3018、**不** push/deploy
- [ ] **A5** 接受 BJ/SH/SZ 行由深交所开市标志**显式扩展**（非三套独立交易所官方日历）

### 2.2 权利与语义门禁

- [ ] **R1** 接受主源为深交所公开 monthList；生产 lineage 标注 `source=szse_month_list`
- [ ] **R2** 接受腾讯仅作交叉校验，**不**作为权利主源、不写入为 official SSE
- [ ] **R3** 接受上交所官方机读 API 仍缺失，不阻塞首发，但记入 residual risk
- [ ] **R4** 接受 `session_type` 语义：  
  开市=`normal`；周末休市=`closed`；工作日休市=`holiday`；半日/特殊未建模为独立生产规则（首发不宣称 half_day 完备）

### 2.3 技术门禁（执行当日现场再跑一遍）

- [ ] **T1** 代码在 `main` 且至少包含 `42a58ab`
- [ ] **T2** `backend/tests/data_lab` 全绿
- [ ] **T3** 深交所 live probe HTTP 200 且当月 rows≥28
- [ ] **T4** 腾讯 SH/SZ live 可拉
- [ ] **T5** 发布前隔离 dry-run：live 双源 equal，且 quality gates 全过
- [ ] **T6** 生产 `data/reference` 发布前快照/备份已做好

---

## 3. 数据集契约（发布时必须满足）

| 字段 | 值 |
|---|---|
| dataset_id | `trading_calendar` |
| unit_version | `trading_calendar_v1` |
| schema_version | `1`（若后续进目录定义） |
| PK | `exchange + trade_date` |
| 交易所枚举 | `SH` / `SZ` / `BJ` |
| 正式文件 | `data/reference/trading_calendar/calendar.parquet` |
| lineage | `data/lineage/trading_calendar/date=<as_of>/<run_id>.json` |
| staging | `data/.staging/trading_calendar/<run_id>/`（成功后可清理；失败保留） |

### 必填列

`exchange, trade_date, is_open, session_type, open_time, close_time, source, as_of`

### 质量硬门

1. 非空  
2. PK 唯一 100%  
3. 枚举合法  
4. `is_open=true` ⇒ `session_type∈{normal,half_day,special}` 且开收盘时间非空  
5. `is_open=false` ⇒ `session_type∈{closed,holiday,special}`  
6. 空结果**不得**覆盖已有正式文件  
7. 与既有正式数据 overlap 时，`is_open` 冲突默认拒绝（除非显式 allow）  
8. lineage 必须含非空 `unit_version`

---

## 4. 推荐执行步骤（确认后才做；现在不要做）

> 全部在仓库 `/Users/simon/Trading/one-trading` 进行。  
> 生产 root：`DATA_DIR=/Users/simon/Trading/one-trading/data`

### 步骤 0 — 冻结与备份

1. 记录 `git rev-parse HEAD`  
2. 确认工作区无意外脏改（允许无视无关 `output/`）  
3. 备份当前生产 data 指纹/清单到：  
   `/Users/simon/备份/codex/<timestamp>-one-trading-before-trading-calendar-publish/`  
   至少包含：  
   - 备份原因  
   - 原路径  
   - 备份时间  
   - `data/` 文件清单（path/size/hash 或既有 manifest 风格）  
4. 若 `data/reference` 已存在（当前应不存在），额外备份该树

### 步骤 1 — 隔离 dry-run（强制）

使用**临时** `lab_dir`（例如 `/tmp/one-trading-cal-prod-dryrun-XXXX`）：

1. live 拉深交所窗口  
2. 规范化 SH/SZ/BJ  
3. M5.1 `publish_dataset` 写入 lab_dir  
4. live 拉腾讯 SH/SZ 开市日  
5. 断言：  
   - SZSE SH open == Tencent SH open  
   - Tencent SH == Tencent SZ  
   - quality report `passed=true`  
   - weekend open rows == 0  
6. 产出 dry-run JSON 报告，路径记入发布记录

**任一失败：停止，不碰生产。**

### 步骤 2 — 生产发布（仅 dry-run 通过后）

1. `run_id = cal-prod-YYYYMMDDTHHMMSSZ`  
2. `as_of = 发布当日`（或你指定）  
3. 目标：  
   `DATA_DIR=.../data`  
   `publish_dataset(trading_calendar, source=szse_month_list, run_id=...)`  
4. 成功后检查：  
   - `data/reference/trading_calendar/calendar.parquet` 存在  
   - row_count = 窗口天数 × 3  
   - lineage 文件存在且含 `unit_version=trading_calendar_v1`  
   - `source=szse_month_list`  
5. 可选：保留 staging quality_report 副本到  
   `docs/superpowers/reports/` 或备份目录

### 步骤 3 — 发布后校验（生产只读）

1. 再读生产 parquet，重算 SH open set  
2. 再拉腾讯 SH，对比 equal  
3. 抽样人工看：  
   - 春节/国庆等已知休市是否为 `is_open=false`  
   - 周末无开市  
   - SH/SZ/BJ 同行一致  
4. 确认**未**创建 listing/status 正式集  
5. 确认未改 kline/instruments 等非目标数据  
6. 重新计算 data 指纹/清单，与备份对比：  
   - 仅允许新增 `reference/trading_calendar/**`、对应 lineage、以及必要 staging 残留（若未清理）

### 步骤 4 — 记录

写发布记录（建议路径）：  
`docs/superpowers/reports/<date>-trading-calendar-production-publish-record.md`

至少包含：

- 批准语句摘要（谁/何时确认）  
- commit  
- 窗口  
- run_id / as_of  
- row_count  
- 双源 equal 结果  
- 备份路径  
- 回滚命令  
- residual risks

---

## 5. 回滚方案

若发布后发现错误：

### 快速回滚（当前是首发、发布前无旧 reference）

```bash
# 仅删除本数据集正式文件与对应 lineage（执行前再次确认路径）
rm -f data/reference/trading_calendar/calendar.parquet
rm -rf data/lineage/trading_calendar/date=<as_of>/
# 如有空目录可再清理
```

### 若将来非首发（已有旧正式文件）

1. 从发布前备份恢复 `calendar.parquet`  
2. 保留失败 run 的 staging/quality_report 供审计  
3. 不自动重试覆盖

### 回滚验收

- 生产日历文件回到发布前状态  
- 非目标数据集指纹不变  
- 服务无需重启也可（当前工作台未注册该集；若以后注册了，再单独处理缓存）

---

## 6. 本轮明确不做

- 不写 `instrument_status_history` / `listing_delisting_events`  
- 不把 `trading_calendar` 注册进 `DATASET_DEFINITIONS` / 工作台（可作**后续可选清单**）  
- 不替换 `filter_halt_days`  
- 不改 daily pipeline 调度  
- 不 deploy、不切 3011/3018  
- 不 git push / 不 merge origin/main  
- 不用腾讯序列直接当正式主源落盘

---

## 7. 发布后可选跟进（单独授权）

按优先级：

1. **目录可见性：** 把 `trading_calendar` 加入 `DATASET_DEFINITIONS` + 扫描根 `reference/trading_calendar`  
2. **工作台卡片：** `/data` 显示覆盖与最近同步  
3. **消费者接入：** 回测交易日、日更 expected coverage（需单独设计与测试）  
4. **上交所官方源：** 若未来出现稳定机读 API，升级二次源  
5. **历史加长：** 向 2024/更早扩展，每段 live 双源 equal 后再 append/publish  
6. **半日市/特殊会话：** 若业务需要再建模 `half_day`

---

## 8. 残留风险（即使发布成功也要接受）

1. 无上交所官方机读日历，SH 语义依赖“A 股现货与深交所开市标志一致 + 腾讯代理校验”  
2. BJ 无独立官方日历源，属扩展假设  
3. 深交所 HTTP 仍可能再次抖动；发布执行窗口需 live 健康  
4. 权利/转载条款尚未做法律签核（工程清单不能替代）  
5. 首发不自动服务化；业务代码不会立刻消费，除非另做接入

---

## 9. 建议你确认时回复的模板

直接回复下面任一即可：

**批准首发（默认窗口）**
> 批准按清单发布 trading_calendar 到生产 data/reference；窗口 2025-01-01..2026-07-21；只发日历；不注册工作台；不部署。

**批准但改窗口**
> 批准发布 trading_calendar；窗口改为 <start>..<end>；其余按清单。

**先不要发布**
> 清单先存档，暂不发布。

**批准发布 + 顺带注册目录（扩大范围）**
> 批准发布 trading_calendar，并允许加入 DATASET_DEFINITIONS / 工作台只读展示。

---

## 10. 执行责任划分

| 角色 | 动作 |
|---|---|
| 你 | A1–A5 授权；可选扩大范围 |
| Codex（确认后） | 备份 → dry-run → 生产发布 → 校验 → 写记录 |
| Codex（未确认前） | **停止在本清单，不写生产** |

---

## 11. 快速对照：现在 vs 确认后

| 项 | 现在 | 你确认后 |
|---|---|---|
| 生产 `data/reference/trading_calendar` | 不存在 | 创建并写入 |
| 隔离 Lab 证据 | 已有 | 再跑一次 dry-run |
| 工作台显示 | 无 | 默认仍无（除非你扩大授权） |
| 回滚 | 不适用 | 删除/恢复 parquet + lineage |

---

*生成时间：2026-07-21T22:15:48+08:00*  
*本文件不构成已发布声明。*
