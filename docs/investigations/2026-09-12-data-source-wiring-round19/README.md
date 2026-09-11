# 数据源接线再审计（2026-09-12 round 19 / nineteenth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-eighteen-0fc0` / PR #19 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: nineteenth-round leftover mix-source / fail-open paths that round 18 left on the calendar / view / loader side. Auction and dragon-tiger calendars no longer leftover-glob when a date probe throws. Auction enrich, chips loader, and screener warmup stay on the current daily route. Integrity prune no longer wipes leftover TickFlow during a custom-route repair. Repo latest/earliest dates and mining/regime calendars use fail-closed dates. DuckDB re-gate failure empties leftover-visible SQL instead of leaving the first-pass ungated view. Leftover TickFlow still sees untagged partitions.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 竞价 / 龙虎 except | 探针失败后全 glob `date=*` | 切源后仍把 leftover 当天当交易日锚 |
| 竞价收益 enrich | 裸读 leftover 日 K 收盘 | 自定义日 K 下 leftover 价混进复盘收益 |
| `scan_usable_daily` / paths | 探针抛错向上冒 | 调用方 except 后再 leftover-glob 或中断 |
| chips / 免费日 K loader | leftover enriched 存在就优先读它 | 自定义日 K 被 leftover 分区挡住 |
| 选股 warmup | 全 glob leftover 再滤 | 切源后均线仍吃 TickFlow 历史 |
| 完整性 prune | 按日期删全部 `date=*` | 自定义源修复误删 leftover 历史 |
| repo / 挖掘 / regime 日历 | 走会抛的 `usable_*` | 探针失败时日历/增量起点不确定 |
| DuckDB 刷新再门控 | 再门控失败留下首遍裸视图 | SQL 切源后仍见 leftover TickFlow |

## 改了什么

1. **fail-closed 日历**：竞价 / 龙虎 `_local_trading_days` 走 `safe_usable_daily_partition_dates`，探针失败返回空，不再回退 leftover glob。`usable_daily_partition_paths` / `scan_usable_daily`、repo latest/earliest、挖掘预检、regime 日期集同样 fail-closed。
2. **leftover 读面**：竞价 enrich 只读当前 daily route。chips loader 按可用分区选表，不让 leftover enriched 挡住自定义日 K。选股 warmup 走 `scan_usable_daily`。
3. **完整性 prune**：只删当前 route 分区，自定义源修复不再抹 leftover TickFlow。
4. **DuckDB 再门控**：`re_gate_catalog_views` 门控失败时清空 route 敏感视图。日 K / 管道 / 指数 / 分钟 / 清数据刷新走它。财务 / 复权 / 日 K 门控异常也改成空视图，不再 skip 留下首遍裸扫描。

未改：盘后默认时刻、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、leftover TickFlow 单票公开分时 / 自选历史 TDX、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、显式 `adj=public` / `depth5=public`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round19 \
  .venv/bin/python -B -m pytest -q \
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
    tests/test_data_integrity.py
```

云环境结果见 `evidence/test-results.md`。
