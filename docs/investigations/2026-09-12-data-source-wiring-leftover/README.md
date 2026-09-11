# 数据源接线再审计（2026-09-12 leftover / fifth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-remaining-routes-a711` / PR #5 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: fifth-round leftover mix-source / fail-open paths. Declared custom `adj_factor` now writes and live-fetches through `get_adj_factors` (fail-closed). Live daily HTTP no longer requires TickFlow `Cap.ADJ_FACTOR` for public or declared custom adj. `fetch_intraday_monitor_batch` is restored and routed; leftover TickFlow + free still returns empty (no public mix). Prefs-read failure and leftover TickFlow watchlist no longer fail-open to public quotes. Undeclared daily / minute / full_minute / adj still fall back to TickFlow (logged). Entitled TickFlow minute fallback after a custom call failure is unchanged.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 自定义复权 | `sync_adj_factor` / `fetch_adj_factor_single` 只分 public / TickFlow | 扶摇已声明 `adj_factor`，盘后与现场日 K 仍打 TickFlow 或 leftover 公开新浪 |
| 现场日 K 复权门槛 | 只看 `Cap.ADJ_FACTOR` | 公开/自定义复权在 none/free 档被跳过 |
| 监控分时批量 | 本树缺 `fetch_intraday_monitor_batch` | `test_intraday_monitor_signals` / 监控注入后半段无法跑；自定义分钟也无处可路由 |
| 监控分时注入 | `QuoteService` 无 `_inject_intraday_signals` | 健康全量分钟时股票不读本地分区，ETF/不健康路径也接不上 |
| leftover TickFlow + free 实时 | `realtime_mode` 读偏好失败默认 `public`；自选空结果仍打公开源 | 明确的 `mode=none` 契约被 fail-open 打破 |
| 未声明数据集 | daily / minute / full_minute / adj 静默回退 TickFlow | 旧契约保留，但完全无日志，排查会当成「源坏了」 |

## 改了什么

1. **kline_sync adj**：已声明 `adj_factor` 的自定义/插件源走 `get_adj_factors` 落盘；解析失败或调用失败 fail-closed，不混 TickFlow/公开源。未声明仍回退 TickFlow（有 cap）或 leftover 公开适配器（无 cap），并打 info 日志。
2. **现场日 K**：`adj_live_fetch_allowed` — 公开源或已声明自定义复权不看 TickFlow cap；`fetch_adj_factor_single` 按同一路由。
3. **`fetch_intraday_monitor_batch`**：恢复。优先已声明自定义分钟；调用失败且具备 `INTRADAY_BATCH` / `KLINE_MINUTE_BATCH` 时回退 TickFlow（旧契约）。leftover TickFlow + free（无 cap）返回空，不打公开分时。
4. **`_resolve_full_minute_provider`**：补齐 minute_refresh 解析入口；未声明 full_minute 仍回退 TickFlow 并记日志。
5. **quote_service**：偏好不可读 → `mode=none`；自选空结果仅当 `realtime=public` 才走公开源。补 `_inject_intraday_signals`（股票+健康读本地，ETF/不健康走监控批量）。
6. **capabilities**：读实时偏好失败不再默认标 `public`。

未改：盘后默认时刻、A 股未声明 daily / minute 回退 TickFlow、leftover TickFlow + free 复权走公开新浪 qfq、TickFlow 默认五档空结果公开 L1、`.env`、鉴权。实时 leftover TickFlow + free 仍是 `mode=none`（本轮只关掉 fail-open，不改成公开源）。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-leftover \
  .venv/bin/python -B -m pytest -q \
    tests/test_leftover_route_hardening.py \
    tests/test_intraday_monitor_signals.py \
    tests/test_custom_provider_indices.py \
    tests/test_remaining_provider_routes.py \
    tests/test_adj_factor_provider_routing.py \
    tests/test_realtime_mode.py \
    tests/test_minute_availability.py \
    tests/test_minute_routing.py \
    tests/test_custom_daily_routing.py \
    tests/test_index_daily_routing.py \
    tests/test_financial_custom_routing.py \
    tests/test_custom_depth_provider.py \
    tests/test_capability_augment.py \
    tests/test_quote_snapshot_persistence.py \
    tests/test_realtime_public_full_market.py \
    tests/test_kline_detail_transport.py \
    tests/test_repair_daily_override.py \
    tests/test_capability_matrix.py
```

云环境结果：backend 目标 **163 passed**（含先前因缺 `fetch_intraday_monitor_batch` 被deselected 的监控分时用例）。见 `evidence/test-results.md`。
