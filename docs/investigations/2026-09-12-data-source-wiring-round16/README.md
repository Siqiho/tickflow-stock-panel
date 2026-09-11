# 数据源接线再审计（2026-09-12 round 16 / sixteenth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-fifteen-4c7d` / PR #16 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: sixteenth-round leftover mix-source / fail-open paths that round 15 documented but left open. Undeclared custom daily / minute / full_minute / adj no longer TickFlow-mix. Leftover TickFlow without `Cap.ADJ_FACTOR` no longer silent-writes or live-fetches public sina qfq; leftover adj reads no longer serve `route=public` tags. Leftover TickFlow empty depth no longer mixes public L1, and leftover depth reads no longer serve public-tagged sealed files. Lab `/api/free-ext` adj / financial / pool / quotes / intraday refuse custom or unresolved routes. Historical HTTP / screener / chips / overview daily and enriched reads use file provenance after a custom daily switch. Leftover TickFlow still sees untagged partitions.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 未声明自定义 daily / minute / full_minute / adj | 日志后回退 TickFlow | 切到未声明插件名仍混 TickFlow / 公开新浪 |
| leftover TickFlow 无 ADJ cap | 静默公开新浪 qfq | 免费档 leftover 把 sina 因子写成当前复权 |
| leftover TickFlow 复权读 | 认 `route=public` | 切回 leftover 仍把公开 sina 文件当 TickFlow |
| leftover TickFlow 五档空 | 回退公开 L1 | 封单判断混进腾讯 L1 |
| leftover TickFlow 五档读 | 认 `route=public` | leftover 把公开 L1 封单当当前五档 |
| Lab `/api/free-ext` | 自定义源下仍拉/写公开 | 切源后 Lab 把公开复权/财务/池写进当前文件 |
| HTTP / screener / chips 历史读 | 全扫 leftover 分区 | 切日 K 源后图表和选股仍吃 TickFlow 历史 |

## 改了什么

1. **未声明自定义源**：`_resolve_daily_provider` / `_resolve_minute_provider` / `_resolve_full_minute_provider` / `_try_custom_adj_provider` 未声明数据集改为 fail-closed（`unresolved` / `skip`），不再回退 TickFlow。
2. **leftover sina qfq**：`sync_adj_factor` / `fetch_adj_factor_single` / `adj_live_fetch_allowed` leftover 无 cap 不再走公开新浪。`adj_public_write_allowed` 只给显式 public。`adj_cache_usable` leftover TickFlow 不再认 public 标签。能力表不再广告 public_fallback。
3. **公开 L1**：`DepthService._call_depth_batch` leftover TickFlow 空结果保持空。`depth_cache_usable` / `depth_stored_usable` leftover 不再认 public 标签。能力表不再广告公开 L1。
4. **历史读 provenance**：`filter_daily_cache` 用于 HTTP `get_daily` / 批量扫描、enriched 内存缓存、screener、chips loader。DuckDB `kline_daily` / `kline_enriched` 等日 K 视图按 daily route 过滤。看板 `latest_official_enriched_date` 走可用分区。扫描 schema 补上 `route`（否则 `extra_columns=ignore` 会丢掉 provenance，自定义分区会被当成未打标而拒读）；`_tag_daily_route` 会填空/null `route`，避免 schema 插入空列后 leftover 写盘不再打标。
5. **Lab**：`/api/free/adj-factor*`、`/financials*`、`/pools*` 写/拉、以及 quotes / intraday 在对应 route 为 custom / unresolved 时 409。leftover TickFlow / 显式 public 仍可作显式 Lab 公开面。

未改：盘后默认时刻、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、leftover TickFlow 单票公开分时 / 自选历史 TDX、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、`.env`、鉴权。显式 `adj=public` / `depth5=public` 仍走公开适配器。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round16 \
  .venv/bin/python -B -m pytest -q \
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
    tests/free_sources/test_free_ext_api.py
```

云环境结果见 `evidence/test-results.md`。
