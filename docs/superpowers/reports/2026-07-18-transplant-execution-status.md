# 移植清单执行状态 2026-07-18

## 已完成

### A-W1 free_sources → one-trading main
- Commit: `f0771d2` `feat(data): free_sources chips, fund flow, quality, quote fallback`
- 路径：`backend/app/services/free_sources/*`、`api/free_ext.py`、pipeline quality、quote fallback
- 测试：`pytest tests/free_sources` → **13 passed**
- 烟测：`quality ok` 最新日；`chips 000001.SZ` 可用

### A-W2 go-stock 数据 parity
- 报告：`docs/superpowers/reports/2026-07-18-A-W2-go-stock-data-parity.md`
- 竞价 / MAC 资金流 / ETF 搜索 / 分组改名：**本地已齐**
- 缺口：`syncStockBasicFromTdx` 增量校准（未本轮实现）

### A-W3 go-stock 概念标签 API+DB
- 新增 `backend/data/stock_concept_api.go`（修正 NewStockConceptApi 使用注入 dao）
- `app.go` CRUD 方法；`main.go` AutoMigrate Concept/ConceptStock
- 测试：`go test ./backend/data -run TestStockConceptApi` **ok**
- **未**合前端概念列（属 B-W2）

## 未做（按清单）
- A-W4 custom HTTP / A-W5 分钟门控 / A-W6 stock-sdk
- B 轨 UI、C 轨飞书/DeepAgents
- go-stock TDX 增量校准

## 如何验证
```bash
# one-trading
cd /Users/simon/Trading/one-trading/backend && uv run pytest tests/free_sources -v
# API（服务启动后）
curl -s http://127.0.0.1:3018/api/free/quality/run | head
curl -s 'http://127.0.0.1:3018/api/free/chips/000001.SZ?days=30' | head

# go-stock
cd /Users/simon/Trading/go-stock && go test ./backend/data -run TestStockConceptApi -count=1
```
