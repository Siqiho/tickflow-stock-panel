# 数据源接线再审计（2026-09-12 round 22 / twenty-second round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-twenty-one-605e` / PR #22 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: twenty-second-round leftover mix-source / fail-open paths that round 21 left on the overlay / ETF-minute / DuckDB / persist / financial side. Official trend overlay and regime history caches key by daily route. HTTP minute-range / get_minute pass ETF `asset_type` so leftover stock minute cannot fill an ETF request. DuckDB refresh helpers re-gate only (no leftover-visible raw glob). Legacy symbol-partition minute migration filters and route-tags instead of republishing leftover TickFlow untagged. Depth sealed reads skip stale `depth5` and keep current-route `sealed_l1`. Shares append and historical-shares cache fail-closed on unresolved prefs or a financial switch. Derived calendars for index / ETF / minute stay on usable partitions. Leftover TickFlow still sees untagged partitions.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 盘中趋势 overlay 缓存 | 键只有 data_dir + 日期 + mtime | 切源后短窗口仍返回 leftover 均线/连板 |
| HTTP minute-range / get_minute | ETF 仍扫 `kline_minute` / stock daily | 同代码 ETF 吃个股 leftover 分时/昨收 |
| DuckDB refresh | 先裸 glob `CREATE VIEW` 再 re_gate | 并发 SQL 短暂看见 leftover TickFlow |
| 旧 symbol= 分钟迁移 | 全量 concat 后写未标记 date 分区 | 自定义源下 leftover 被洗成未标记当前文件 |
| 五档 sealed 读 | 先存在的 `depth5` 挡住 `sealed_l1` | leftover depth5 让当前 sealed 变空 |
| 股本 PIT append | 偏好/探针抛错后继续 merge leftover | 切源失败时 TickFlow 股本写进自定义表 |
| 历史股本缓存 | 只按文件 mtime | 切财务源后同一文件仍返回 leftover |
| regime 历史缓存 | 键不含 daily route | 切源后 5s 内仍返回 leftover 环境 |
| 派生日历 | 只门控 daily/enriched | 指数/ETF/分钟表仍 leftover-glob |

## 改了什么

1. **overlay / regime 缓存**：`load_official_trend_overlay` 与 `/api/regime/history` 按 `daily_route()` 分键，切源后不再复用 leftover。
2. **ETF 分钟 HTTP**：`get_minute_range` / `get_minute` / `latest_minute_date` / prev_close 走 `asset_type`；指数代码不再扫个股分钟。
3. **DuckDB refresh**：`refresh_gated_catalog_views` 只重挂门控视图。管道 / extend-history / clear_data / index+minute refresh 不再先裸 glob。
4. **分钟迁移**：`_migrate_symbol_to_date_partition` 先 `filter_minute_cache`，再 `_with_minute_route` + `_write_minute_partition`。偏好不可读直接跳过。
5. **五档 sealed**：`_sealed_df_for_read` 逐个探测 `depth5` / `sealed_l1`，只返回当前 route 可用文件。
6. **股本**：`append_shares_history` 偏好/unresolved fail-closed。`get_historical_shares` 按财务 route 分键。
7. **派生日历**：`list_partition_dates` 对指数 / ETF / 分钟走 `safe_usable_*`。

未改：盘后默认时刻、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、leftover TickFlow 单票公开分时 / 自选历史 TDX、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、显式 `adj=public` / `depth5=public`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round22 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_twenty_two_route_hardening.py \
    tests/test_round_twenty_one_route_hardening.py \
    tests/test_round_twenty_route_hardening.py \
    tests/test_round_nineteen_route_hardening.py \
    tests/test_round_eighteen_route_hardening.py \
    tests/test_round_seventeen_route_hardening.py \
    tests/test_round_sixteen_route_hardening.py \
    tests/test_round_fifteen_route_hardening.py \
    tests/test_round_fourteen_route_hardening.py \
    tests/test_round_thirteen_route_hardening.py \
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
    tests/free_sources/test_adj_factor_public.py \
    tests/free_sources/test_financials_public.py \
    tests/test_financial_pit_e6.py \
    tests/test_corporate_actions_sync.py \
    tests/free_sources/test_share_capital_public.py \
    tests/test_adj_public_no_event.py \
    tests/test_quote_index_merge.py \
    tests/test_reference_derived.py \
    tests/test_enriched_full_rebuild.py \
    tests/test_regime_builder.py \
    tests/free_sources/test_free_ext_api.py \
    tests/test_market_mainline.py::TestComputeMainline \
    tests/test_intraday_overview.py \
    tests/test_enriched_stale_price_partition.py \
    tests/free_sources/test_daily_quality.py \
    tests/test_rps_rotation_map_cache.py \
    tests/test_market_overview_as_of.py \
    tests/test_auction_benchmark.py \
    tests/test_dragon_tiger.py \
    tests/test_abnormal_moves.py \
    tests/test_kline_read_failure.py \
    tests/test_minute_range_api.py
```

云环境结果：backend 目标 **734 passed**。见 `evidence/test-results.md`。
