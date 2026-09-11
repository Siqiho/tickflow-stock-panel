# 数据源接线再审计（2026-09-12 round 14 / fourteenth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-thirteen-4a5a` / PR #14 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: fourteenth-round leftover mix-source / fail-open paths around same-date daily/enriched writes, public adj coverage/status, share-capital public writes, reference-derived shares, financial last_sync backfill, and minute date helpers. Same-date daily/enriched persist replaces other-route partitions instead of concat-mixing (historical other dates stay until re-sync). Public sina adj / coverage writers and readers refuse custom/unresolved adj. Share-capital public fetch/write refuses custom financial. Reference valuation no longer raw-reads leftover shares. Financial scheduler last_sync does not treat leftover TickFlow parquet mtime as current. `latest_minute_date` / `earliest_minute_date` use file provenance instead of a possibly ungated DuckDB view.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 同日日K / enriched 落盘 | 裸 concat 旧分区 | 切源后重同步同一天把 TickFlow + 自定义 bar 写进同一文件 |
| 实时 merge 日K / enriched | 不看 route | 切回 leftover 或切到自定义仍拼进旧源当天 |
| 公开复权 coverage | 状态页 / 公司行动裸读 | 自定义复权下仍把 leftover 新浪 no_event 算成当前覆盖 |
| 公开复权写入 | `merge_write` / `sync_adj_factor_public` 不看出路 | 自定义复权文件被公开新浪因子覆盖 |
| 公开股本脚本 | 裸读 shares + 公开东财写入 | 自定义财务下混进公开股本 |
| 估值派生股本 | 裸读 `financials/shares` | 自定义财务下 leftover TickFlow 股本进入估值 |
| 财务 last_sync 回填 | 见 parquet mtime 就当已同步 | 自定义财务把旧 TickFlow 文件当成“已经同步” |
| 分钟最早/最晚日 | `SELECT min/max FROM kline_minute` | 视图一旦裸刷新，自定义分钟把旧 TickFlow 当天当覆盖 |

## 改了什么

1. **同日日K / enriched 写路径**：`daily_cache_usable` + `_tag_daily_route`；`_write_daily_partition` / live merge / flush 遇到其它 route 旧分区则替换，不混 bar。`unresolved` 不写。历史其它日期仍留给用户重同步（leftover 契约）。
2. **公开复权 coverage / 写入**：`read_adj_coverage` 在 custom/unresolved 下空读；`merge_write_adj_factor` / `merge_write_adj_coverage` / `sync_adj_factor_public` 拒绝写入。leftover TickFlow / public 仍走新浪。
3. **公开股本**：`sync_share_capital_public` 在 custom/unresolved 下不拉不写；可用旧盘才 merge，并打当前 route。
4. **估值派生**：`_load_pit_safe_shares` 走 `get_financial_df`。
5. **财务 last_sync**：parquet mtime 回填前先过 `financial_cache_usable`。
6. **分钟日期辅助**：`latest_minute_date` / `earliest_minute_date` / `latest_minute_date_global` 按 provenance 过滤。

未改：盘后默认时刻、A 股未声明 daily / minute / full_minute / adj 回退 TickFlow（有日志）、leftover TickFlow + free 复权走公开新浪 qfq（读路径认 public 标签）、TickFlow 默认五档空结果公开 L1、leftover TickFlow 单票公开分时 / 自选历史 TDX、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、Lab `/api/free-ext` 仍是显式公开写入（自定义复权下写入会被本轮写入门挡住，避免混源）、历史日 K / enriched 分区在用户重同步前仍可能是旧源、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round14 \
  .venv/bin/python -B -m pytest -q \
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
    tests/test_quote_index_merge.py
```

云环境结果见 `evidence/test-results.md`。
