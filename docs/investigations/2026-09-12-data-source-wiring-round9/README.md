# 数据源接线再审计（2026-09-12 round 9 / ninth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-eight-2110` / PR #9 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: ninth-round leftover mix-source / fail-open paths around daily/minute prefs-read, watchlist historical TDX, quote watchlist/full-market prefs, custom financial universe, pool apply-source, stale pool cache, ALL-scope TickFlow expansion, live adj public-sina parity, and capability-label honesty. Daily/minute getters throwing no longer fail-open to TickFlow or public. Pipeline universe-scope prefs failures skip TickFlow `CN_Equity_A`. Index live HTTP is fail-closed when the daily route cannot be read. Declared custom minute no longer TDX-mixes watchlist history (leftover TickFlow still may). Watchlist/full-market quote prefs-read is fail-closed; public realtime no longer calls TickFlow on the watchlist path. Custom financial uses `pipeline_universe_scope` (empty/error fail-closed) instead of widening to instruments. Apply-source / dedicated PUTs / delete / capability matrix now persist and display `pool_provider`. Stale pool parquet is no longer served after `pool_provider` switches away (custom/unresolved never reuse TickFlow/public cache; tagged files must match the current route). ALL-scope empty instruments no longer expand via cached `CN_Equity_A` or DEMO under custom/unresolved pool. Live daily adj with leftover TickFlow + no `Cap.ADJ_FACTOR` now uses the same public sina qfq adapter as `sync_adj_factor`. Minute persist / monitor-support prefs-read is fail-closed. Undeclared custom depth/realtime labels are unavailable. `watchlist.fetch_quotes` is TickFlow-only.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 日 K 偏好不可读 | `get_daily_data_provider` 上抛 | 管道 `quote.pool` 覆写 / 现场日 K 可能混 TickFlow |
| 分钟偏好不可读 | `_try_custom_minute` 上抛 | 单票分钟可能落到 TickFlow / 公开分时 |
| 管道标的范围偏好不可读 | `resolve_universe` 上抛或仍扩全 A | leftover TickFlow 池下静默打 `CN_Equity_A` |
| 指数现场日 K | `daily_provider_is_custom()` 上抛 → 500 | 偏好坏了还可能继续 live fetch |
| 自选历史分钟 | 已声明自定义分钟仍先打 TDX | 扶摇等分钟源被公开 TDX 混进落盘 |
| 自选实时 | 偏好不可读默认当 tickflow；public 仍先打 TickFlow | 静默混源 |
| 全市场实时 | `_fetch_full_market_quotes` 再读偏好上抛 | 外层 except 只记日志，路径不清晰 |
| 自定义财务范围 | 一律 instruments 全表 | CSI300 设定下自定义财务仍拉全 A |
| 套用 / 专用 PUT / 删除 | `pool_provider` 写不进、自定义名 400、删除不回退 | 成分插件套用无效，残留自定义成分 |
| 成分缓存短接 | `get_pool` / CSI 磁盘先读，不看 `pool_route` | 切到自定义/不可读后仍用 TickFlow/中证旧 parquet |
| ALL 空维表回退 | `resolve_symbols(ALL)` 打 `CN_Equity_A` 再 DEMO | 自定义成分下静默扩 TickFlow 全 A / 演示票 |
| 现场日 K 复权 | leftover TickFlow 无 ADJ cap 直接跳过 | 盘后已写公开新浪 qfq，现场 K 线仍未复权 |
| 分钟落盘偏好 | `sync_and_persist_minute` 读偏好上抛 | 管道 / HTTP 分钟任务 fail-open |
| 五档/实时能力表 | 任意非 tickflow 名标 available | 未声明 depth5/realtime 的源被当成可用 |
| 自选 `fetch_quotes` | 无视 realtime 偏好打 TickFlow | 潜伏混源（当前无调用方） |

## 改了什么

1. **日 K**：偏好不可读 → `daily_provider_is_custom=True`，batch / `fetch_routed_daily` 写 0，标签 `none`。
2. **分钟**：偏好不可读 fail-closed；`minute_may_use_leftover_public` 只给 leftover TickFlow / 未声明。
3. **管道标的池**：范围偏好不可读不扩 TickFlow 全 A。
4. **指数 HTTP**：日 K 路由读失败直接空结果。
5. **自选历史分钟**：只有 leftover TickFlow 才走 TDX；已声明自定义 / 解析失败 / 偏好不可读不混。
6. **实时**：watchlist / 全市场偏好不可读 fail-closed；public 自选不再打 TickFlow。
7. **自定义财务**：跟 `pipeline_universe_scope`，空/失败 fail-closed。TickFlow 财务仍用 instruments 全表。
8. **成分接线**：`update_data_providers` / 专用 PUT 认自定义名；删除源回退 `public`；能力矩阵 + 套用带 `pool_provider`。
9. **成分缓存**：`pool_cache_usable` — custom/unresolved 不读旧盘；带 `route` 列必须匹配当前路由；无标签旧文件只给 public。公开写入打 `route=public`。已声明 `pool` 的自定义源走 `get_pool` / `get_constituents`。
10. **ALL 范围**：instruments 空时只有 leftover TickFlow 才打 `CN_Equity_A`；custom/unresolved 空结果，不混 DEMO。管道 / extend-history 最后兜底 DEMO 同样只给 leftover public/TickFlow。
11. **现场复权**：leftover TickFlow / 未声明 adj 无 `Cap.ADJ_FACTOR` 时走公开新浪 qfq，与 `sync_adj_factor` 对齐。
12. **分钟落盘 / 监控能力**：读偏好失败 return 0 / `available=False`。
13. **能力表**：未声明 depth5 / realtime 的自定义名标 unavailable。`minute_refresh.status` 解析失败不把 stored 名标成可用。`watchlist.fetch_quotes` 只服务 leftover TickFlow。

未改：盘后默认时刻、A 股未声明 daily / minute / full_minute / adj 回退 TickFlow（有日志）、leftover TickFlow + free 复权走公开新浪 qfq（现已含现场日 K）、TickFlow 默认五档空结果公开 L1、leftover TickFlow 单票公开分时 / 自选历史 TDX、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、Lab `/api/free-ext` 仍是显式公开写入、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round9 \
  .venv/bin/python -B -m pytest -q \
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
    tests/test_kline_minute_api.py
```

云环境结果：backend 目标 **305 passed**。见 `evidence/test-results.md`。
