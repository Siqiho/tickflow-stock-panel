# 数据源接线再审计（2026-09-12 round 23 / twenty-third round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-twenty-two-cdef` / PR #23 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: twenty-third-round leftover mix-source / fail-open paths that round 22 left on the DuckDB-init / derived-history / pool / financial-migration / catalog-status side. DataStore init no longer creates leftover-visible raw kline / adj / financial / depth globs before gating. Regime and mainline history tag and filter by daily route so incremental upsert cannot merge leftover TickFlow into custom. Pool membership seeds skip leftover CSI caches after a pool switch. Financial PIT migration refuses leftover rewrite after a financial switch. Catalog compatibility calendars overlay usable partitions so last-scan leftover dates cannot serve as current coverage. Leftover TickFlow still sees untagged partitions.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| DataStore 启动挂视图 | 先裸 glob `CREATE VIEW` 再 gate | 启动窗口并发 SQL 看见 leftover TickFlow |
| regime 磁盘历史 | 不按 daily route 分键 / 过滤 | 切源后增量把 leftover 环境日当成已有并混写 |
| 主线磁盘历史 | 读旧 parquet 不看 route | 切源后 leftover 主线日挡住自定义补算 |
| 指数成分种子 | 全量读 `pools/*.parquet` | 切 pool 源后 leftover TickFlow CSI 仍进 membership |
| 财务 PIT 迁移 | 无条件 rewrite leftover | 切财务源后把 TickFlow 表洗成当前文件 |
| 画像 compatibility | 用上次 scan 的 leftover 日历 | 切源后未 rescan 仍显示 TickFlow 覆盖 |

## 改了什么

1. **DuckDB 启动**：`_register_views` 只裸挂 instruments* / kline_ext（无 `instrument_provider`），kline / adj / financial / depth 直接门控。
2. **regime / 主线历史**：读写走 `filter_daily_cache` + `_tag_daily_route`。偏好不可读或 unresolved 拒绝落盘。
3. **成分种子**：`build_index_membership_from_pools` 跳过 custom / unresolved 下的 leftover CSI；leftover TickFlow 仍可见无标签快照。
4. **财务 PIT 迁移**：`migrate_existing_financials_to_pit` / `migrate_financial_table_to_v2` 对 stale route skip。
5. **画像日历**：`compatibility_status` 用可用分区覆盖 leftover scan 日历；财务表走 gated reader。

未改：盘后默认时刻、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、leftover TickFlow 单票公开分时 / 自选历史 TDX、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、显式 `adj=public` / `depth5=public`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round23 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_twenty_three_route_hardening.py \
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
    tests/test_minute_range_api.py \
    tests/data_catalog/test_service.py
```

云环境结果：见 `evidence/test-results.md`。
