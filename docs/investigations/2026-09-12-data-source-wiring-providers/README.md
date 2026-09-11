# 数据源接线再审计（2026-09-12 providers）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-data-source-routing-ad5e` / PR #3 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: remaining preference / fetch / capability / UI mismatches after the follow-up wiring PR. Index and ETF daily now honor `daily_data_provider` (custom sources are fail-closed, no silent TickFlow). Custom `financial_provider` writes through `get_financials` instead of the TickFlow client. Full-minute is routable end-to-end. Apply-source also covers depth5 / full_minute. Capability labels report the configured source when it is not TickFlow.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 指数 / ETF 日 K | `sync_and_persist_index_daily` / `_etf_daily` 一律 `klines.batch`，且先卡 `KLINE_DAILY_BATCH` | 日 K 已切扶摇/自定义后，指数与 ETF 仍打 TickFlow；无档时写 0 行，有档时静默混源 |
| 财务自定义源 | `financial_sync._sync_table` 只分 public / TickFlow | 矩阵里套用了扶摇财务，同步仍打 TickFlow；未声明 financial 时只要有 Cap.FINANCIAL 也会误打 |
| 全量分钟 | 取数读 `full_minute_data_provider`，注册表 `field=None`，API 不收该字段 | UI 说不可路由，后台任务却可能走残留自定义源；套用/删除也不写回该偏好 |
| 一键套用 | 只带 daily/adj/realtime/minute/financial | 声明了 depth5 / full_minute 的源套用后这两路仍留 TickFlow |
| 自定义源编辑器 | DATASETS 无 depth5 / financial | UI 建的源声明不了这两项，和矩阵候选对不上 |
| 能力表 source | 增广后一律标 `tickflow` | 自定义分钟/五档/财务/实时在 `/api/capabilities` 上说成 TickFlow |

## 改了什么

1. **index_sync**：日 K 走 `kline_sync.fetch_routed_daily`，`asset_type=index/etf`。自定义源 fail-closed（扶摇只做 A 股 → 指数/ETF 写 0，不回退 TickFlow）。TickFlow 路径仍要 `kline.daily.batch`。
2. **financial_sync**：`financial_provider` 为插件/自定义时走 `get_financials` 落盘；未声明 financial 也不回退 TickFlow。public / TickFlow 旧路径不动。
3. **capabilities 注册表**：`full_minute.field=full_minute_data_provider`。写偏好、矩阵注入、删除回退、GET preferences 对齐。
4. **UI**：套用覆盖 depth5 / full_minute；编辑器可声明这两项与财务；`routingForSource` 与后端默认一致（未设实时仍是 public）。
5. **feature_availability / financials.status**：自定义源报真实源名，不再在增广后冒充 TickFlow。

未改：盘后默认时刻、分钟全市场默认、`.env`、鉴权、`pool_provider`（仍走独立设置项）。实时 leftover TickFlow + free 仍是 `mode=none`。A 股自定义日 K 未声明 daily 时回退 TickFlow 的旧语义未动。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-providers \
  .venv/bin/python -B -m pytest -q \
    tests/test_index_daily_routing.py \
    tests/test_financial_custom_routing.py \
    tests/test_data_source_write_path.py \
    tests/test_custom_daily_routing.py \
    tests/test_fuyao_daily_streaming_sync.py \
    tests/test_adj_factor_provider_routing.py \
    tests/test_pipeline_pull_types.py \
    tests/test_public_eod_daily_fallback.py \
    tests/test_realtime_mode.py \
    tests/test_capability_matrix.py \
    tests/test_capability_augment.py \
    tests/test_minute_availability.py \
    tests/test_financial_provider_preference.py
```

前端：

```
cd frontend && npx vitest run src/lib/dataSources.test.ts src/lib/dataSourceCatalog.test.ts \
  src/pages/__tests__/DataUnifiedSources.test.tsx src/pages/__tests__/Data.test.tsx
```

云环境结果：backend 目标 71 passed；相邻 10 passed；frontend 44 passed。见 `evidence/`。
