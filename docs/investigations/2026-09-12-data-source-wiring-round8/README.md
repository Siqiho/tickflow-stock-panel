# 数据源接线再审计（2026-09-12 round 8 / eighth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-seven-9c5c` / PR #8 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: eighth-round leftover mix-source / fail-open paths around pool / universe / financial / capability labels. `get_pool_provider` no longer heals a stored custom/plugin name to public. TickFlow `CN_Equity_A` expansion is only for explicit leftover TickFlow pool + undeclared-or-TickFlow daily (public/custom pool, custom daily, unreadable prefs, and CSI scopes do not expand via TickFlow). HTTP `POST /api/kline/sync_minute` uses the same universe resolver as the pipeline. CSI refresh no longer public-syncs under a TickFlow/custom pool. Daily capability prefs-read failures match minute (`resolve_failed` / `source=none`). Feature-matrix no longer rewrites leftover TickFlow minute labels to a stored custom name. Financial prefs-read and public-scope failures are fail-closed (no TickFlow mix, no instruments widen). Custom financial without TickFlow cap can start/run the scheduler.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| `pool_provider` getter | 未注册名静默改写成 public | 解析器看不到已声明成分源；CSI/ALL 按公开池走 |
| 自定义成分 | `_fetch_pool` 只要不是 public 就打 TickFlow | 扶摇等成分名被当成 TickFlow universes |
| 偏好不可读成分 | `_use_public_pools` 当 public | 可能先打中证 XLS，而不是空结果 |
| `resolve_universe` ALL | 只挡 public pool | 自定义日 K / 自定义成分仍扩 TickFlow 全 A |
| `extend_history` | 忽略管道范围，有日 K batch 就扩全 A | CSI300 设定下仍打 TickFlow `CN_Equity_A` |
| HTTP 全市场分钟 | 写死 watchlist ∪ `CN_Equity_A` ∪ instruments | 公开/自定义成分与管道标的池不一致 |
| CSI 刷新 | TickFlow 成分也先 `public.sync_pools` | 成分源是 TickFlow 时静默写入中证 XLS |
| 日 K 能力表 | 偏好异常改写成 tickflow leftover | 真实 fetch fail-closed，UI 报 TickFlow 可用 |
| 分钟能力表覆写 | 未声明自定义仍把 source 改成插件名 | leftover TickFlow 回退被标成自定义源 |
| 财务偏好不可读 | public/custom 都假 → 有 cap 就打 TickFlow | 已声明扶摇财务被 TickFlow 覆写 |
| 公开财务范围失败 | 掉到 instruments 全表 | CSI300 设定下公开东财拉全 A |
| 财务调度 | 只认 TickFlow cap / public | 自定义财务无 cap 时自动/手动入口不跑 |

## 改了什么

1. **getter**：`get_pool_provider` 空值才回 public；已声明自定义名原样交给 `pool_route`。
2. **成分路由**：`pool_route()` = public / tickflow / custom / unresolved。只有 explicit tickflow 才打 TickFlow universes。
3. **全 A 扩张**：`tickflow_all_a_expansion_allowed` — 管道与 extend-history 共用；自定义日 K / 非 tickflow 成分 / 非 ALL 范围不扩。
4. **HTTP 分钟**：`sync_minute` 改走 `_resolve_minute_universe`（即 `resolve_universe`）。
5. **CSI**：缺缓存时 public 才刷中证；tickflow 走 `get_pool`；custom/unresolved 空。
6. **能力表**：日 K 偏好不可读 `resolve_failed`；分钟不再把 leftover TickFlow source 改写成插件名。
7. **财务**：偏好不可读 / 公开范围失败 fail-closed；调度与 HTTP 认自定义财务。

未改：盘后默认时刻、A 股未声明 daily / minute / full_minute / adj 回退 TickFlow（有日志）、leftover TickFlow + free 复权走公开新浪 qfq、TickFlow 默认五档空结果公开 L1、leftover TickFlow 单票公开分时、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、实时 leftover TickFlow + free 仍是 `mode=none`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round8 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_eight_route_hardening.py \
    tests/test_round_seven_route_hardening.py \
    tests/test_round_six_route_hardening.py \
    tests/test_leftover_route_hardening.py \
    tests/test_remaining_provider_routes.py \
    tests/test_financial_custom_routing.py \
    tests/test_daily_pipeline_universe.py \
    tests/test_minute_availability.py \
    tests/test_public_eod_daily_fallback.py \
    tests/test_adj_factor_provider_routing.py \
    tests/test_minute_routing.py \
    tests/test_custom_daily_routing.py \
    tests/test_index_daily_routing.py \
    tests/test_capability_matrix.py \
    tests/test_realtime_mode.py
```

云环境结果见 `evidence/test-results.md`。
