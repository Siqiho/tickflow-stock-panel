# 数据源接线再审计（2026-09-12 round 12 / twelfth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-eleven-99f9` / PR #12 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: twelfth-round leftover mix-source / fail-open paths around DuckDB catalog refresh, minute getters/SQL, depth sealed provenance, share-history fallback, and ETF adj incremental start. Pipeline / extend-history / minute-view refresh no longer undo adj/financial/minute/depth gates. `repo.get_minute` / `get_minute_batch` and DuckDB `kline_minute` refuse stale TickFlow/public parquet after a custom minute switch. Minute writes replace a stale other-route partition instead of mixing bars. Share-history no longer raw-reads `financials/shares` when the gated reader fails. Depth sealed parquet is route-tagged; boot restore / HTTP sealed map / DuckDB `depth5` skip leftover TickFlow files under a custom depth route (leftover TickFlow may still read untagged or public-L1 tags). ETF adj incremental start and `_load_etf_factors` use the gated adj reader.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 管道 / 扩历史刷新视图 | `CREATE VIEW` 全扫 adj/minute parquet | round 11 的 DuckDB 门被盘后刷新打掉，SQL 又看见旧源 |
| `repo.get_minute` / batch | 只扫盘，不看 route | 信号 / 其它调用方在自定义分钟下仍吃 TickFlow 旧分时 |
| DuckDB `kline_minute` | `read_parquet` 全扫 | SQL 与 HTTP 门不一致 |
| 分钟落盘 merge | 旧分区直接 upsert | 切源后同一天混进 TickFlow + 自定义 bar |
| 股本历史 | `get_financial_df` 异常再读裸 parquet | 财务门失效后仍混旧股本 |
| 五档定版 | 无 `route`，boot 见文件就恢复 | 切到自定义五档仍用 TickFlow/公开 sealed |
| ETF 复权增量起点 | `scan_parquet` 旧盘 max date | 自定义复权被旧 TickFlow 日期截短 |

## 改了什么

1. **目录再挂门**：`_refresh_views` / `_refresh_single_view` / `extend_history` / `refresh_minute_views` 在 raw 刷新后重跑 `_register_gated_catalog_views`。
2. **分钟 DuckDB + getter**：`kline_minute` / `kline_etf_minute` SQL 按 `minute_route` 过滤；`get_minute` / `get_minute_batch` 走 `filter_minute_cache`。
3. **分钟写**：`_write_minute_partition` 遇到其它 route 旧分区则替换，不混 bar。
4. **股本**：`load_share_history` 失败直接空表，不再裸读 parquet。
5. **五档 provenance**：`depth_route` / `depth_cache_usable`；写入打 `route`；boot / 内存 / parquet / DuckDB `depth5` 认标签。leftover TickFlow 仍可读无标签与 `public` 标签（公开 L1 契约）。
6. **ETF 复权**：`adj_coverage_start` + `_load_etf_factors` 走 `get_adj_factor_df`，旧盘不推进增量窗口。
7. **全量分钟覆盖探测**：当日分区对 `full_minute_route` 不可用则当无数据，走全天修复而不是当新鲜 TickFlow。

未改：盘后默认时刻、A 股未声明 daily / minute / full_minute / adj 回退 TickFlow（有日志）、leftover TickFlow + free 复权走公开新浪 qfq（读路径认 public 标签）、TickFlow 默认五档空结果公开 L1、leftover TickFlow 单票公开分时 / 自选历史 TDX、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、Lab `/api/free-ext` 仍是显式公开写入、历史日 K / enriched 分区在用户重同步前仍可能是旧源、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round12 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_twelve_route_hardening.py \
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

云环境结果见 `evidence/test-results.md`。
