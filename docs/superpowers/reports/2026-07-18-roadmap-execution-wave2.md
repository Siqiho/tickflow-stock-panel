# 路线图执行状态 — Wave 2（2026-07-18）

## 本波完成

### 1) go-stock 测量 / 波浪画框
- **提交:** `b085942` `feat(kline): add measure box and wave drawing tools`
- 文件:
  - `frontend/src/components/kline/measurePrimitive.js`
  - `frontend/src/components/kline/wavePrimitive.js`
  - `frontend/src/components/kline/drawingManagerHost.js`（预留，未强依赖 npm drawing 包）
  - `StockLightweightKlineChart.vue` 工具栏「测量」「波浪」+ 点击/十字光标/清理
- 构建: `npm run build` 已通过（dist 生成）
- 使用: 打开个股多周期 K 线 → 点「测量」两点画框 / 「波浪」两点选区；ESC 清除，Ctrl/Cmd+Z 撤销

### 2) Custom HTTP Provider 基础（默认不接管生产）
- **提交:**（本仓库 main 最新）`feat(data): custom HTTP provider foundation with staging-only writes`
- 模块:
  - `backend/app/data_providers/custom/*`（config/loader/mapper/provider/security/staging）
  - `backend/app/tickflow/rate_limits.py`
  - `backend/app/api/custom_sources.py`
  - `docs/custom-data-source.md` + examples
- API:
  - `GET  /api/custom-sources` — 列表，声明 default=tickflow、不写生产库
  - `POST /api/custom-sources/reload`
  - `PUT/DELETE /api/custom-sources/{name}`
  - `POST /api/custom-sources/test` — 试拉，不落库
  - `POST /api/custom-sources/stage-daily` — **仅 staging**
- 策略硬约束:
  - TickFlow 仍是默认生产源
  - SSRF 默认拒绝 localhost/私网（可用 `CUSTOM_HTTP_ALLOW_PRIVATE=1` 开本地 mock）
  - staging 路径: `data/staging/custom/{name}/daily/run=.../`
  - **无自动 promote 到 kline_daily**

### 3) 回归测试
```
24 passed
- custom foundation 6
- minute honesty 5
- free_sources 13
```

## 明确延后（未做）

| 项 | 原因 |
|---|---|
| Walk-forward 全套 | 策略引擎+SSE+UI 绑定大包，单独 PR |
| stock-sdk 插件 | 合规/Node/与 free_sources 重叠，lab only |
| Feishu / DeepAgents | go-stock Agent 轨，独立账号与权限 |
| Custom → 生产 promote | 需质量门禁 + canary + 双源对照后再做 |
| 数据源设置页完整 UI | 可下一波；API 已可 curl 管理 |

## 建议验证

```bash
# one-trading
curl -s http://127.0.0.1:3018/api/capabilities | python3 -m json.tool | head -60
curl -s http://127.0.0.1:3018/api/custom-sources | python3 -m json.tool

# go-stock :18081
# 自选股 → 多周期K线 → 「测量」「波浪」
```

本地 mock custom 源（仅 lab）:

```bash
# 终端1
python docs/examples/custom-data-source/mock_server.py
# 终端2（允许私网）
export CUSTOM_HTTP_ALLOW_PRIVATE=1
# 将 mock_source.yaml 复制到 data/data_sources/ 后
curl -s -X POST http://127.0.0.1:3018/api/custom-sources/reload
curl -s -X POST http://127.0.0.1:3018/api/custom-sources/test \
  -H 'Content-Type: application/json' \
  -d '{"name":"mock_source","dataset":"daily","symbols":["000001.SZ"]}'
```
