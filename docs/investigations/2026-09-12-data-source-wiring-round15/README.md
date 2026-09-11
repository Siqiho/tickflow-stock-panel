# 数据源接线再审计（2026-09-12 round 15 / fifteenth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-fourteen-720c` / PR #15 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: fifteenth-round leftover mix-source / fail-open paths around enriched pipeline writes, public financial/adj merge exception fail-open, daily/enriched status and operational dates, reference-derived daily/depth inputs, and regime history date selection. Enriched pipeline no longer computes or concat-mixes leftover TickFlow partitions after a custom daily switch (same-date stale enriched is replaced; unresolved daily skips publish). Public financial/adj merges refuse to write when the route gate raises. Daily/enriched status, adj daily window, `latest_daily_date` / `earliest_daily_date` / `latest_enriched_date`, and pipeline day counts use file provenance. Reference valuation / limit events and sealed L1 fund maps skip leftover inputs. Regime `enriched_date_set` ignores stale other-route partitions. Historical HTTP / screener reads of leftover daily/enriched stay leftover.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| enriched 管道落盘 | 裸 concat 旧分区 / 全扫 daily | 切源后同日 TickFlow + 自定义 bar 写进 enriched，或用旧源日K重算派生 |
| 覆盖缺口补齐 | 见目录就当当前覆盖 | 自定义日K仍把 leftover enriched 当已有、或从 leftover daily 补洞 |
| 公开财务 / 复权 merge 异常 | except 继续 concat | 门失效时公开行混进自定义文件 |
| 数据页日K / enriched 统计 | 数全部 `date=*` 目录 | 切源后状态页仍显示 leftover 覆盖 |
| 复权状态日K窗口 | `SELECT min/max FROM kline_daily` | 自定义日K下 leftover 日期锚定 adj 覆盖 |
| 管道 / 扩历史日期 | DuckDB / 目录全扫 | 增量起点把 leftover 当天当已同步 |
| 估值 / 涨跌停派生 | 裸读 daily | 自定义日K下 leftover TickFlow 进入 reference |
| 封单金额 | 裸读 sealed_l1 | 自定义五档下 leftover TickFlow/公开 L1 进入涨停事件 |
| 市场环境日期 | 数全部 enriched 目录 | 自定义日K下 leftover enriched 被写成 regime_history |

## 改了什么

1. **日K / enriched 分区 provenance**：`daily_partition_usable` / `usable_daily_partition_dates` / `usable_daily_partition_paths`。leftover TickFlow 仍见无标签分区。
2. **enriched 管道写路径**：只扫当前 route 日K；同日其它 route enriched 替换不混；`unresolved` 不发布。增量历史前缀也只读可用 enriched。
3. **公开 merge 异常**：`merge_write_financial_table` / `merge_write_adj_factor` 门不可用时拒绝写入。
4. **状态与操作日期**：日K / enriched 统计、adj 日K窗口、`latest_daily_date` / `earliest_daily_date` / `latest_enriched_date`、盘后管道日计数走 provenance。HTTP / screener 历史读路径未改。
5. **估值派生**：`build_valuation_daily` / `build_limit_up_events` / `_seal_fund_map` 只吃当前 route 日K / 五档。
6. **regime**：`enriched_date_set` / `_compute_batch` 只扫可用 enriched。

未改：盘后默认时刻、A 股未声明 daily / minute / full_minute / adj 回退 TickFlow（有日志）、leftover TickFlow + free 复权走公开新浪 qfq（读路径认 public 标签）、TickFlow 默认五档空结果公开 L1、leftover TickFlow 单票公开分时 / 自选历史 TDX、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、Lab `/api/free-ext` 仍是显式公开写入、历史日 K / enriched 分区在用户重同步前仍可能被 HTTP / screener 读到、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round15 \
  .venv/bin/python -B -m pytest -q \
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
    tests/test_enriched_generation.py \
    tests/test_regime_builder.py
```

云环境结果：见 `evidence/test-results.md`。
