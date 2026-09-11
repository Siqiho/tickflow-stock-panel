# 数据源接线再审计（2026-09-12 round 20 / twentieth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-nineteen-cce9` / PR #20 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: twentieth-round leftover mix-source / fail-open paths that round 19 left on the cache / overview / persist / scan side. Overview official-day no longer treats leftover TickFlow as official when the probe throws. Screener latest stays on disk provenance. In-memory enriched latest / hist / overlay / live-agg caches drop leftover TickFlow after a custom switch. Daily / index / ETF scans use usable partitions only so leftover schema cannot empty the current route. History / range filter throws return None. Index/ETF status calendars no longer count leftover DuckDB rows. Auction enrich and official trend overlay fail-closed on probe throw. Public EOD persist refuses custom / unresolved daily internally. Leftover TickFlow still sees untagged partitions.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 看板 official 探针 | 探针抛错后 `path.exists()` | 切源后仍把 leftover 当天当正式日 |
| 选股 latest | disk 空后再回退内存缓存 / DuckDB | 切源后 as_of 仍是 leftover TickFlow 日 |
| enriched 内存 latest / hist | 自定义源下仍返回 leftover 缓存 | HTTP / 选股 / 回测把 TickFlow 当当前 |
| live-agg 基准日 | DuckDB `max(date)` | 视图短暂未门控时 leftover 成上一交易日 |
| 竞价 enrich / 趋势 overlay | 探针抛错向上冒 | 调用方 except 后再 leftover-mix |
| 公开 EOD 落盘 | 只靠调用方门控 | 直接调用会把公开行情标成自定义 route |
| 派生日历 | 走会抛的 `usable_*` | 探针失败时估值窗口不确定 |
| 日 K / 指数 / ETF scan | 全 glob leftover + 强制 schema | leftover Int64/坏文件把自定义分区扫成空 |
| hist / range / live-agg | 过滤抛错或 leftover 命中当空结果 | 回测 / 轮动 / 盘中递推吃 TickFlow 或静默空 |
| 指数 / ETF 状态行数 | 日历已门控仍读 DuckDB count | 切源后 coverage 行数仍是 leftover |

## 改了什么

1. **fail-closed official / overlay**：`_has_official_enriched` 探针失败返回 False。竞价 enrich 与盘中趋势 overlay 探针抛错返回空，不再把 leftover 当天当正式日。
2. **内存读面**：`get_enriched_latest` / ETF latest / `get_daily` hist / `_filter_cached*` 丢 leftover TickFlow。选股 `latest_date` 只认磁盘 provenance。
3. **live-agg 基准**：上一交易日走 `safe_usable_daily_partition_dates`，不读可能短暂未门控的 DuckDB。
4. **公开 EOD**：`sync_daily_by_public_quotes` 内部拒绝自定义 / 偏好不可读日 K，leftover TickFlow 仍可补今日。
5. **派生日历**：`list_partition_dates` 走 `safe_usable_daily_partition_dates`。
6. **scan 不再吃 leftover 文件**：`get_daily` / batch / 指数 / ETF 只扫 `scan_usable_daily`。leftover TickFlow 分区的 schema 差异不能再把当前源扫成空。
7. **hist / range / live-agg**：过滤抛错返回 None / 空；leftover 内存 hist 不再当命中。RPS 缺缓存时走可用分区。
8. **状态行数**：指数 / ETF 日历只认 provenance，不再用 leftover-visible DuckDB `count(*)`。

未改：盘后默认时刻、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、leftover TickFlow 单票公开分时 / 自选历史 TDX、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、显式 `adj=public` / `depth5=public`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round20 \
  .venv/bin/python -B -m pytest -q \
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
    tests/test_dragon_tiger.py
```

云环境结果：见 `evidence/test-results.md`。
