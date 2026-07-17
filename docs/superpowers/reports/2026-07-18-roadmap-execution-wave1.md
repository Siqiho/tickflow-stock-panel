# 路线图执行状态 — Wave 1（2026-07-18）

按修订顺序执行：架构诚实度 → 数据底座 → 可见 UI。

## 1. A-W5 分钟能力诚实化 — 已完成

**one-trading commit:** `9933947`  
`feat(data): honest minute capability gating and reasons`

| 项 | 内容 |
|---|---|
| `capabilities.py` | `minute_availability` / `feature_availability` 结构化 reason |
| `/api/capabilities` | 增加 `features` / `daily` / `minute` |
| `daily_pipeline.py` | `minute_sync: {status, reason, reason_code, rows, ...}`；无权限时 emit 原因 |
| `MinuteSyncConfig.tsx` | 不可用原因 + fallback 提示（单票公开分时） |
| `ActiveJobCard.tsx` | 任务结果展示分钟跳过原因 |
| 测试 | `test_minute_availability` + `test_capabilities_features` + free_sources **18 passed** |

**验收语义：** 无分钟权限时 pipeline 仍成功、`minute_rows=0`、API/UI/job 可共享 reason。

## 2. go-stock TDX 证券主数据增量校准 — 已完成

**go-stock commit:** `9490ebb`（含概念 UI）  
实现：

- `GetAllStockList` / `GetHKUSStockList` / `SyncStockBasicToDB` / `SyncHKUSStockBasicToDB`（自上游移植）
- `CheckStockBaseInfo` 全量后 `go a.syncStockBasicFromTdx()` / `syncHKUS...`（失败只 Warn，不阻断）
- **注意：** 校准的是 go-stock `StockBasic`，不是 one-trading `instruments`

`go build -tags web` 通过。

## 3. 概念标签 UI + RPC 暴露 — 已完成（B 轨）

- wailsjs `App.js` / `App.d.ts` 增加 concept CRUD 的 `callWails` 绑定（Web RPC 可用）
- `stock.vue`「全部」表格：概念列、概念筛选、设置概念下拉（新建/加入/移出）
- 依赖已有 A-W3 API+DB

## 未做（下一批）

- 全部表格其它 UX 大改 / 测量·波浪画框
- Custom HTTP Provider + staging
- Walk-forward / stock-sdk / Agent

## 验证命令

```bash
# one-trading
cd /Users/simon/Trading/one-trading/backend
uv run pytest tests/test_minute_availability.py tests/test_capabilities_features.py tests/free_sources -v

# 服务起来后
curl -s http://127.0.0.1:3018/api/capabilities | python3 -m json.tool | head -80

# go-stock
cd /Users/simon/Trading/go-stock
go test ./backend/data -run TestStockConceptApi -count=1
go build -tags web -o /tmp/gs-web .
# 浏览器打开 18081 → 自选「全部」→ 概念列/筛选/设置概念
```
