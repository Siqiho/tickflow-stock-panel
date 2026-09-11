# 数据源接线再审计（2026-09-12 round 21 / twenty-first round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-twenty-6f23` / PR #21 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: twenty-first-round leftover mix-source / fail-open paths that round 20 left on the minute / live-rebuild / index / persist side. Minute scans use usable partitions so leftover schema cannot empty the current route. Live enriched full-rebuild hist stays on the current daily route. Index benchmark / overview / SSE quote fallbacks use file provenance instead of leftover-visible DuckDB. Process caches key by daily route. Minute null-datetime cleanup does not wipe leftover TickFlow. Live publish and daily writes refuse custom / unreadable prefs. Adj status does not count leftover DuckDB rows. Leftover TickFlow still sees untagged partitions.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 分钟 scan | 全 glob leftover + 强制 schema | leftover Int64/坏文件把自定义分区扫成空 |
| HTTP minute-range | `get_minute_range` 缺失后再 leftover glob | 切源后分时区间仍吃 TickFlow |
| 盘中 enriched 全量回退 | `kline_daily/**/*.parquet` | 切回 leftover TickFlow 后仍混自定义历史 |
| 指数偏离基准 | 全 glob leftover + 缓存只按 data_dir | 切源后 10 分钟内仍用 TickFlow 基准 |
| 看板 / SSE 指数兜底 | DuckDB `kline_index_daily` | 视图短暂未门控时 leftover 成看板价 |
| 分钟 null-datetime 清理 | DuckDB count 后删全部 parquet | 自定义源修复误删 leftover 分钟 |
| live publish / 日 K 写 | 调用方门控 / resolve 抛错向上冒 | 直接调用或 except 后再 leftover-mix |
| 复权状态行数 | DuckDB `count(*)` | 切源后 coverage 行数仍是 leftover |
| 异动 / 轮动 / 总览缓存 | 键不含 daily route | 切源后短窗口仍返回 leftover |

## 改了什么

1. **分钟 scan**：`usable_minute_partition_paths` / `scan_usable_minute`。`get_minute` / batch / range 与 HTTP fallback 只扫当前 minute route。探针失败时 leftover TickFlow 仍可见不可读日期标记。
2. **盘中回退**：`_flush_live_enriched` 全量路径走 `scan_usable_daily` + `filter_daily_cache`。
3. **指数读面**：`load_usable_index_latest_quotes` 替代 DuckDB。看板 / SSE / `load_benchmark_momentum` 走可用分区；基准缓存按 daily route 分键。
4. **清理 / 写入**：分钟 null-datetime 只删当前 route 分区。`publish_live_enriched_asset` 与 `_daily_write_context` fail-closed。
5. **状态 / 缓存**：复权状态用 gated reader，不再数 leftover SQL。异动快照 / RPS / 总览缓存键带 daily route。
6. **HTTP 分时区间**：指数代码不再扫个股分钟；getter 结果走 `filter_minute_cache`；`prev_close` 只读当前 daily route；`execute_one` MagicMock/非 SQL 行不再挡住 instruments 缓存。
7. **单票分钟落库**：`sync_minute_single` 写完刷新 `kline_minute` 视图，避免 leftover DuckDB 继续对外。
8. **今日脏指数行**：`benchmark_momentum_today` 同时排除 `date.today()` 与 `cn_today()`，UTC 主机不再把监控今日行当昨收。
9. **实时指数缓存**：`QuoteService.get_index_quotes` 按 realtime provider 分键，切源后不再复用 leftover TickFlow 报价。

未改：盘后默认时刻、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、leftover TickFlow 单票公开分时 / 自选历史 TDX、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、显式 `adj=public` / `depth5=public`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round21 \
  .venv/bin/python -B -m pytest -q \
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

云环境结果：见 `evidence/test-results.md`。
