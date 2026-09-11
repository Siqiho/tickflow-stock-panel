# 数据源接线再审计（2026-09-12 round 13 / thirteenth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-twelve-8349` / PR #13 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: thirteenth-round leftover mix-source / fail-open paths around HTTP minute extend-history, minute coverage/incremental start, catalog re-gate after clear/index refresh, public financial merge, share-history PIT append, and corporate-actions public adj fetch. HTTP `/api/kline/extend_minute_history` no longer concat-merges leftover TickFlow bars or raw-refreshes `kline_minute` without the catalog gate. Minute incremental start and `/api/data` minute/financial status ignore stale other-route parquet after a custom switch (leftover TickFlow still sees untagged files). `clear_data` and `refresh_index_views` re-run gated catalog registration. Public financial merge refuses to write when financial route is custom. Share-history PIT append drops stale TickFlow shares under a custom financial route. Corporate-actions `fetch_missing_adj` does not write public sina factors when adj is custom/unresolved.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| HTTP 扩分钟历史 | 裸 concat 旧分区 + `CREATE VIEW` 全扫 | 自定义分钟把 TickFlow bar 写进同一天，SQL 门被打掉 |
| 分钟增量起点 | `SELECT max(datetime) FROM kline_minute` | 视图一旦裸刷新，自定义分钟把旧 TickFlow 当天当已覆盖 |
| 数据页分钟/财务统计 | 数目录 / 裸读 parquet | 切源后状态页仍显示旧源覆盖 |
| `clear_data` / 指数视图刷新 | 只挂 raw view | adj/minute/financial/depth 门被清数据或指数刷新打掉 |
| 公开财务 merge | 不看出路 | 自定义财务下脚本/公开写入仍混进 TickFlow 旧表 |
| 股本 PIT 追加 | 裸读旧 shares | 自定义财务仍把 TickFlow 股本拼进新截面 |
| 公司行动补 adj | `fetch_missing_adj` 必走公开新浪 | 自定义复权文件被公开因子覆盖 |

## 改了什么

1. **扩分钟写路径**：`persist_routed_minute_bars` 打 `route`、走 `_write_minute_partition` 替换旧源分区，并 `refresh_minute_views` 重挂门。HTTP extend 用当前源可用分区算 earliest。
2. **分钟覆盖探测**：`usable_minute_partition_dates` / `latest_usable_minute_datetime` 按 provenance 过滤；`_latest_minute_datetime` 不再信可能被打掉的 DuckDB 视图。
3. **状态页**：分钟统计只数当前 route 分区；财务统计走 `get_financial_df`。
4. **目录再挂门**：`clear_data` 与 `refresh_index_views` 在 raw 刷新后重跑 `_register_gated_catalog_views`。
5. **公开财务写入**：`merge_write_financial_table` 在 custom/unresolved 下拒绝写入；resume 统计走 gated reader。
6. **股本 PIT**：`append_shares_history` 丢掉不可用旧盘并打当前 route。
7. **公司行动**：`fetch_missing_adj` 仅 leftover TickFlow / public 可走公开新浪。

未改：盘后默认时刻、A 股未声明 daily / minute / full_minute / adj 回退 TickFlow（有日志）、leftover TickFlow + free 复权走公开新浪 qfq（读路径认 public 标签）、TickFlow 默认五档空结果公开 L1、leftover TickFlow 单票公开分时 / 自选历史 TDX、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、Lab `/api/free-ext` 仍是显式公开写入、历史日 K / enriched 分区在用户重同步前仍可能是旧源、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round13 \
  .venv/bin/python -B -m pytest -q \
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
    tests/test_corporate_actions_sync.py
```

云环境结果：backend 目标 **405 passed**。见 `evidence/test-results.md`。
