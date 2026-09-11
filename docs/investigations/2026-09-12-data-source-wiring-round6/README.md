# 数据源接线再审计（2026-09-12 round 6 / sixth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-leftover-routes-cce3` / PR #6 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: sixth-round leftover mix-source / fail-open paths around adj / minute / realtime / depth / pipeline. Declared custom daily / minute / full_minute resolve failures are fail-closed (no TickFlow mix). Pipeline public EOD no longer overlays a custom daily source. Declared custom adj is no longer treated as the public sina adapter (universe no longer shrinks to `public_data_scope`). ETF adj uses the same live-fetch gate as stock adj. Declared custom minute call failure no longer falls through to public single-symbol bars. Missing full-minute fetch boundary (`fetch_intraday_full_market_burst` / universe increment / custom batch+latest) is restored and fail-closed. Capability labels no longer mark declared custom adj unavailable, or advertise `public_l1` under a custom depth source.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 日 K / 分钟 / 全量分钟解析异常 | `_resolve_*_provider` 异常 `fallback=True` | 已声明扶摇/插件源 registry 损坏时静默改打 TickFlow |
| 盘后 public EOD | `should_use_public_eod_fallback` 不看日 K 源 | 自定义日 K 今日缺口被腾讯/新浪行情覆写进同一分区 |
| 管道复权范围 | `adj_sync_uses_public_adapter` 只要无 `Cap.ADJ_FACTOR` 就当公开适配器 | 已声明自定义复权在 none/free 被收成 CSI300 |
| ETF 复权门槛 | 只看 `Cap.ADJ_FACTOR` | 公开/自定义复权在 none/free 跳过 ETF 因子 |
| 单票分钟公开兜底 | `fetch_minute_single` 自定义调用失败后仍打公开分时 | 已声明分钟源失败后混入腾讯/东财分时 |
| 分钟落盘解析失败 | `sync_and_persist_minute` 把 resolver 异常当非 custom | 有 TickFlow minute cap 时继续混源 |
| 全量分钟边界 | 本树缺 burst / universe / custom batch+latest | `test_intraday_burst_fault_isolation` / 自定义全量分钟无法跑；解析失败还会降级 TickFlow |
| 能力表 | 自定义复权无 cap 标 unavailable；自定义五档仍标 `fallback=public_l1` | UI 与真实路由不一致 |

## 改了什么

1. **resolver**：daily / minute / full_minute 解析异常改为 `(None, False, err)`。`sync_and_persist_daily_batch` / `fetch_routed_daily` / `_try_custom_minute` / `sync_and_persist_minute` / `intraday_monitor_support` fail-closed，不回退 TickFlow。未声明数据集仍回退 TickFlow（有日志）。
2. **管道日 K**：`should_use_public_eod_fallback(..., daily_is_custom=)`。自定义日 K 不再叠公开 EOD。batch 路径 `daily_source` 报 `custom` / 真实源名，不再一律 `tickflow_batch`。
3. **管道复权**：`adj_sync_uses_public_adapter` 对已声明 / 解析失败的自定义复权返回 False。ETF 复权改走 `adj_live_fetch_allowed`。
4. **单票分钟**：已声明自定义分钟调用失败 → 有资格仍可 TickFlow（旧契约）→ 不再打公开分时。leftover TickFlow 单票公开分时保留。
5. **全量分钟**：恢复 `fetch_intraday_full_market_burst`（单块容错、>4 失败块不重试）、`fetch_intraday_universe_increment`、`fetch_intraday_custom_batch` / `latest`。自定义调用失败 fail-closed。full_minute 解析失败本轮中止，不降级 TickFlow。
6. **能力表**：已声明自定义复权不看 TickFlow cap；自定义五档不再广告 `public_l1`。

未改：盘后默认时刻、A 股未声明 daily / minute / full_minute 回退 TickFlow、leftover TickFlow + free 复权走公开新浪 qfq、TickFlow 默认五档空结果公开 L1、leftover TickFlow 单票公开分时、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、实时 leftover TickFlow + free 仍是 `mode=none`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round6 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_six_route_hardening.py \
    tests/test_intraday_burst_fault_isolation.py \
    tests/test_minute_refresh.py \
    tests/test_leftover_route_hardening.py \
    tests/test_remaining_provider_routes.py \
    tests/test_public_eod_daily_fallback.py \
    tests/test_adj_factor_provider_routing.py \
    tests/test_minute_routing.py \
    tests/test_minute_availability.py \
    tests/test_custom_depth_provider.py \
    tests/test_realtime_mode.py \
    tests/test_kline_detail_transport.py
```

云环境结果：backend 目标 **195 passed**（含恢复的 `test_intraday_burst_fault_isolation` 与全量分钟自定义路由）。见 `evidence/test-results.md`。
