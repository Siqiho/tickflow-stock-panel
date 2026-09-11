# 数据源接线再审计（2026-09-12 round 17 / seventeenth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-sixteen-381b` / PR #17 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: seventeenth-round leftover mix-source / fail-open paths that round 16 left on the read/coverage side. Backtest panel scans, in-memory enriched / live-agg / ETF refresh, market mainline, screener official date + history TTL, intraday overlay, mining preflight/fingerprint, reference consecutive_limit_ups, integrity, stale-price prune, daily quality, and auction / dragon-tiger calendars no longer treat leftover TickFlow partitions as current after a custom daily switch. HTTP `/api/kline/minute-range` leftover parquet is gated under a custom minute route. Leftover TickFlow still sees untagged partitions.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 回测 panel 扫盘 | 全 glob enriched | 切日 K 源后矩阵/旧回测仍吃 TickFlow 历史 |
| enriched 内存 / live-agg | 最新分区被滤空仍保留旧缓存；降级路径裸扫 | 切源后看板/选股/盘中递推仍用 TickFlow |
| ETF enriched 刷新 | 按目录名取最新日 | 自定义日 K 下 leftover ETF 进内存 |
| 主线 / 盘中 overlay | 裸扫 enriched | 题材主线与均线叠 TickFlow 连板 |
| 选股 official date / history TTL | 先信内存日期；TTL 不含 route | 切源后 as_of 与历史窗口仍是 leftover |
| 挖掘预检 / 指纹 | 数全部 `date=*` | 周挖矿把 leftover 当天当覆盖 |
| 涨跌停派生连板 | 日 K 已门控，enriched 高度未门 | 自定义日 K 配 leftover 连板高度 |
| 完整性 / 过期价 prune / 日质检 | 认全部目录 | 修/删/报告 leftover 分区 |
| 竞价/龙虎日历 | 全扫 daily 目录 | 切源后交易日锚在 leftover |
| HTTP `/minute-range` 扫盘 | 无分钟 provenance | 自定义分钟源仍读 leftover TickFlow 文件 |

## 改了什么

1. **可用分区扫描**：`scan_usable_daily` 只扫当前 daily route 分区。回测 engine / 旧 BacktestService、主线、选股 history 慢路径、live-agg 降级、ETF 刷新走它。
2. **内存缓存**：`_refresh_enriched` 最新分区缺失或滤空时 `clear_cache()`。`get_enriched_history` / `get_enriched_range` 再套 `filter_daily_cache`。选股 TTL key 带 `daily_route()`，repo 历史缓存命中也滤 route。
3. **覆盖日历**：mining preflight / schedule 指纹、integrity、daily quality latest、auction / dragon-tiger `_local_trading_days` 只用 `usable_daily_partition_dates`。
4. **派生与 prune**：`build_limit_up_events` 连板高度只读可用 enriched；`_prune_stale_price_partitions` 不跨 route 比对/删除。
5. **分钟 HTTP**：`/api/kline/minute-range` 扫盘走 `filter_minute_cache`。leftover TickFlow 无标签仍可见。

未改：盘后默认时刻、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、leftover TickFlow 单票公开分时 / 自选历史 TDX、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、显式 `adj=public` / `depth5=public`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round17 \
  .venv/bin/python -B -m pytest -q \
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
    tests/free_sources/test_daily_quality.py
```

云环境结果：backend 目标 **568 passed**。见 `evidence/test-results.md`。
