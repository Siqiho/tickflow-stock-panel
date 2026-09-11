# 数据源接线再审计（2026-09-12 round 11 / eleventh round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-ten-0010` / PR #11 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: eleventh-round leftover mix-source / fail-open paths around live-enriched overlay, adj-factor provenance, financial bypass readers, and DuckDB catalog views. TickFlow/custom realtime no longer publishes in-memory enriched (or injects `/api/kline/daily/latest` live candles) when daily is custom or prefs are unreadable — `get_enriched_latest` drops a live-published cache and reloads disk. Adj parquet is route-tagged; `get_adj_factor_df` / pipeline / corporate-actions / catalog stats refuse stale TickFlow files under a custom adj route (leftover TickFlow may still read untagged or public-sina tags). Watchlist join, backtest fundamentals, financial status, capability readiness, and share-history all go through `get_financial_df`. DuckDB `financials_*` and `adj_factor*` views are re-registered from the gated readers so SQL no longer scans stale parquet after a provider switch.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 现场 enriched 内存 | `persist=False` 仍 `publish_live_enriched` | 自定义日 K + TickFlow/公开实时把混源蜡烛打进图表/筛选/最新日 |
| `get_enriched_latest` | 不区分 live 缓存与磁盘缓存 | 切源后同进程仍返回盘中 TickFlow 行 |
| 复权 parquet | 无 `route`，读写不过门 | 切到自定义复权仍用 TickFlow/公开旧因子算 qfq |
| 财务旁路 | watchlist / 回测 / status / ready / 股本直读 parquet | `get_financial_df` 已挡，旁路仍混旧源 |
| DuckDB 财务/复权视图 | `read_parquet` 全扫 | SQL 与 HTTP 门不一致 |

## 改了什么

1. **现场 enriched**：`live_enriched_overlay_allowed`（同 `live_daily_persist_allowed`）。自定义/偏好不可读不发布内存 enriched，不注入 `/api/kline/daily/latest`。
2. **内存缓存标记**：`publish_live_enriched_asset` 打 `_enriched_cache_live`；自定义日 K 下 `get_enriched_latest` 丢掉 live 缓存并回磁盘（历史 leftover）。
3. **复权 provenance**：`adj_route` / `adj_cache_usable` / `get_adj_factor_df`。写入打 `route`；自定义不读无标签或 TickFlow 标签旧盘；leftover TickFlow 仍可读无标签与 `public` 标签（公开新浪契约）。
4. **财务旁路**：watchlist join、`load_fundamental_snapshot`、`/api/financials/status`、`local_financials_ready` / `local_adj_factor_ready`、`load_share_history` 走 gated reader。
5. **DuckDB 目录**：启动时按 gated 结果重挂 `financials_*` / `adj_factor*`，自定义 + 旧盘 → 空视图。

未改：盘后默认时刻、A 股未声明 daily / minute / full_minute / adj 回退 TickFlow（有日志）、leftover TickFlow + free 复权走公开新浪 qfq（读路径认 public 标签）、TickFlow 默认五档空结果公开 L1、leftover TickFlow 单票公开分时 / 自选历史 TDX、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、Lab `/api/free-ext` 仍是显式公开写入、历史日 K / enriched 分区在用户重同步前仍可能是旧源、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round11 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_eleven_route_hardening.py \
    tests/test_round_ten_route_hardening.py \
    tests/test_round_nine_route_hardening.py \
    tests/test_round_eight_route_hardening.py \
    tests/test_round_seven_route_hardening.py \
    tests/test_round_six_route_hardening.py \
    tests/test_intraday_burst_fault_isolation.py \
    tests/test_minute_refresh.py \
    tests/test_leftover_route_hardening.py \
    tests/test_remaining_provider_routes.py \
    tests/test_financial_custom_routing.py \
    tests/test_daily_pipeline_universe.py \
    tests/test_public_eod_daily_fallback.py \
    tests/test_adj_factor_provider_routing.py \
    tests/test_minute_routing.py \
    tests/test_minute_availability.py \
    tests/test_custom_depth_provider.py \
    tests/test_realtime_mode.py \
    tests/test_custom_daily_routing.py \
    tests/test_index_daily_routing.py \
    tests/test_capability_matrix.py \
    tests/test_data_source_write_path.py \
    tests/test_capability_augment.py \
    tests/test_realtime_public_full_market.py \
    tests/test_financial_shares.py \
    tests/test_custom_provider_indices.py \
    tests/test_intraday_monitor_signals.py \
    tests/test_kline_detail_transport.py \
    tests/test_kline_minute_api.py \
    tests/test_quote_snapshot_persistence.py \
    tests/test_universe_scope.py \
    tests/test_universe_scope_csi1800.py \
    tests/free_sources/test_pools_public.py \
    tests/test_capabilities_features.py \
    tests/test_financial_normalize.py \
    tests/free_sources/test_adj_factor_public.py
```

云环境结果：backend 目标 **351 passed**。见 `evidence/test-results.md`。
