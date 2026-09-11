# 数据源接线再审计（2026-09-12 round 18 / eighteenth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-seventeen-be9a` / PR #18 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: eighteenth-round leftover mix-source / fail-open paths that round 17 left on the calendar / matrix / status side. Market overview, daily quality, and integrity no longer glob leftover `date=*` when a route probe throws. Pipeline incremental, partial prune, index/ETF start, and minute cover use route-usable dates. Extend-history and rebuild-enriched day counts hide leftover partitions. Backtest matrix bounds / fingerprints / Arrow dataset skip leftover TickFlow. Regime stale detection, RPS as_of, and enriched lineage reconcile stay on the current route. Index/ETF status calendars use provenance. Leftover TickFlow still sees untagged partitions.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 看板 / 日质检 / 完整性 except | 探针失败后全 glob `date=*` | 切源后仍把 leftover 当天当官方日 |
| 管道增量日历 | 数全部 daily/enriched 目录 | leftover 已存在则跳过自定义日 K 重算 |
| 部分 enriched prune | 用 leftover 日 K 行数比自定义 enriched | 切源后误删当前分区 |
| 指数 / ETF 增量起点 | 认 leftover 最新日 | 自定义源只从 leftover 日期续拉 |
| 分钟覆盖天数 | 数全部 `kline_minute/date=*` | 状态页把 leftover 分钟当天当覆盖 |
| 回测矩阵 | 全根目录进 bounds / fingerprint / dataset | 切源后矩阵仍混 TickFlow 历史 |
| regime stale / RPS as_of / lineage | 认 leftover mtime / 缓存 / 分区 | 重算、轮动右端、血缘把 leftover 当当前 |
| 指数 / ETF 状态日历 | DuckDB 裸聚合 | 视图短暂未门控时 leftover 进 earliest/latest |

## 改了什么

1. **fail-closed 日历**：`safe_usable_daily_partition_dates` / `safe_usable_minute_partition_dates` 探针失败返回空列表，不再回退 leftover glob。看板 `latest_official_enriched_date`、日质检 latest、完整性扫描走它。
2. **管道覆盖**：`_coverage_calendars` / `_usable_partition_dates` 只数当前 daily route。部分 prune 跳过 leftover daily vs 自定义 enriched。指数 / ETF 起点与分钟覆盖天数同样门控。
3. **状态与扩展**：extend-history / HTTP rebuild-enriched 天数、指数/ETF `/api/data` 日历按 provenance。rebuild 视图走 `_refresh_single_view`（再门控）。`_refresh_daily_view` / public EOD 刷新后立即 re-gate。
4. **矩阵 / 派生**：`_usable_partition_entries` 过滤 leftover 后才算 bounds、fingerprint、Arrow dataset。regime stale、RPS as_of、enriched lineage reconcile 跳过 leftover。

未改：盘后默认时刻、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、leftover TickFlow 单票公开分时 / 自选历史 TDX、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、显式 `adj=public` / `depth5=public`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round18 \
  .venv/bin/python -B -m pytest -q \
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
    tests/test_market_overview_as_of.py
```

云环境结果：backend 目标 **597 passed**。见 `evidence/test-results.md`。
