# 数据源接线再审计（2026-09-12 round 10 / tenth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-nine-f1f1` / PR #10 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: tenth-round leftover mix-source / fail-open paths around live-daily persist, minute/financial cache provenance, monitor full_minute fallback, public adj scope, and depth capability honesty. TickFlow/custom realtime no longer writes canonical `kline_daily` / enriched when daily is custom or prefs are unreadable — those quotes stay in `quote_snapshot` (same isolation as public). `sync_daily_by_quotes` now refuses the same gate internally. Minute partitions are tagged with the effective route; HTTP `/api/kline/minute` and minute-batch skip stale TickFlow/public parquet after a custom switch (untagged legacy files remain valid only for leftover TickFlow / public). Monitor signals do not fall through to `minute_data_provider` when `full_minute` is a declared custom source. Public-sina adj no longer widens to the pipeline universe when `public_data_scope` is empty or fails. Depth `_has_capability` matches the fetch route (undeclared custom / unreadable prefs are false; leftover TickFlow still unlocks public L1). Financial parquet is tagged and `get_financial_df` refuses stale TickFlow/public files under a custom route.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 实时落盘 | QuoteService 无视日 K 源，TickFlow/自定义实时写 `kline_daily` | 扶摇日 K + TickFlow 实时在同一张正式表里混源；管道已挡，盘中没挡 |
| `sync_daily_by_quotes` | 只靠管道 `daily_provider_is_custom` 门 | 其他调用方仍可用 TickFlow quote.pool 覆写自定义日 K |
| 分钟本地短接 | 完整本地分区直接 `source=local`，无 route | 切到自定义分钟后仍返回 TickFlow/公开旧 parquet |
| 监控分时 | 全量分钟不健康就打 `fetch_intraday_monitor_batch` | 自定义 full_minute 静默混 `minute_data_provider` / TickFlow |
| 公开复权范围 | `resolve_symbols(...) or adj_universe` | public_data_scope 空/失败时公开新浪拉到管道全 A |
| 五档能力 | `_has_capability()` 恒 True | 未声明/偏好不可读仍启动轮询与 boot 补跑 |
| 财务缓存 | `get_financial_df` 不看当前源 | 切到扶摇财务后仍读 TickFlow/公开旧 part.parquet |

## 改了什么

1. **现场日 K 落盘**：`live_daily_persist_allowed` — 只有 leftover TickFlow 日 K 才允许 TickFlow/自定义实时写正式 `kline_daily` / enriched。自定义/偏好不可读改写 `quote_snapshot`，内存 enriched 仍发布。
2. **`sync_daily_by_quotes`**：同样的门，自定义/不可读直接 0 行，不打 TickFlow quote.pool。
3. **分钟 provenance**：`minute_route` / `full_minute_route` / `minute_cache_usable`。新写入打 `route`；HTTP 单票/批量本地短接只认匹配标签。无标签旧文件只给 leftover TickFlow / public。
4. **监控分时**：本地全量分钟也走 cache usable；已声明自定义 full_minute 不再回退 `minute_data_provider`。leftover TickFlow full_minute 仍可走监控批量（旧契约）。
5. **公开复权范围**：`resolve_adj_sync_universe` — 空/失败返回 None，管道跳过，不扩管道宇宙。TickFlow/自定义复权仍用管道宇宙。
6. **五档能力**：`_has_capability` 认 public / leftover TickFlow / 已声明 depth5；未声明与偏好不可读为 False。
7. **财务 provenance**：写入打 route；`get_financial_df` 自定义不读无标签或 TickFlow 标签旧盘，返回时丢掉 route 列。

未改：盘后默认时刻、A 股未声明 daily / minute / full_minute / adj 回退 TickFlow（有日志）、leftover TickFlow + free 复权走公开新浪 qfq、TickFlow 默认五档空结果公开 L1、leftover TickFlow 单票公开分时 / 自选历史 TDX、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、Lab `/api/free-ext` 仍是显式公开写入、历史日 K 分区在用户重同步前仍可能是旧源、DuckDB financial 视图仍扫原始 parquet、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round10 \
  .venv/bin/python -B -m pytest -q \
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
    tests/test_capabilities_features.py
```

云环境结果：backend 目标 **326 passed**。见 `evidence/test-results.md`。
