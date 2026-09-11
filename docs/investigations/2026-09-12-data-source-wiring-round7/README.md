# 数据源接线再审计（2026-09-12 round 7 / seventh round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-six-10c0` / PR #7 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: seventh-round leftover mix-source / fail-open paths around adj / minute / realtime / depth / pipeline / capabilities. Preference getters no longer rewrite a stored custom/plugin name to TickFlow or public when the registry is down or the plugin is not in `names()`. Explicit `depth5=public` is no longer healed to TickFlow. Capability labels honor an explicit public realtime/depth selection even when TickFlow has quote/depth caps. Daily/minute availability mark declared-custom resolve failures unavailable (no public_fallback advertisement). Prefs-read failures in adj / full-minute / depth / pool / pipeline adapter are fail-closed. HTTP/pipeline minute gates no longer treat TickFlow minute-batch as sufficient when custom minute resolve failed. Extend-history ALL no longer expands via TickFlow `CN_Equity_A` under a public pool; adj sync is always attempted (leftover TickFlow + free still uses public sina inside `sync_adj_factor`).

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| getter 校验 | 未注册 / `names()` 异常时把扶摇等改写成 tickflow；实时改写成 public | 解析器的 fail-closed / 未声明日志根本看不到；实时静默打公开源；五档有 TickFlow cap 时静默打 TickFlow |
| 五档 public | `_allowed_data_providers` 不含 public → 治愈成 tickflow | 用户选了公开五档，有 DEPTH cap 时先打 TickFlow |
| 能力表实时/五档 | `has_quote` / DEPTH cap 优先标 tickflow | 实际走公开源，UI 报 TickFlow |
| 日 K / 分钟能力表 | 自定义解析失败仍借 TickFlow cap 标 available / public_fallback | UI 与真实 fail-closed 路由不一致 |
| HTTP/管道分钟门 | TickFlow minute-batch 短路，忽略自定义解析失败 | 入口放行，落盘再 fail-closed；标签也跟着谎报 |
| 偏好不可读 | adj / 全量分钟 / 五档 / 成分池当成 leftover TickFlow | 静默公开新浪 qfq / TickFlow burst / public L1 / TickFlow 全 A |
| 历史扩展标的池 | 有日 K batch 就打 TickFlow `CN_Equity_A` | 公开成分设定下仍扩全 A |
| 历史扩展复权 | 只看 `Cap.ADJ_FACTOR` | 公开/自定义复权在 none/free 被跳过 |

## 改了什么

1. **getter**：`_coerce_routed_provider` 空值才回默认；公开源别名照旧归一；已声明自定义名即使 registry 损坏也原样交给 resolver。
2. **五档 public**：`get_depth5_data_provider` 认 `public`，`_call_depth_batch` 只走公开 L1。
3. **能力表**：公开实时/五档先于 TickFlow cap；自定义分钟/日 K 解析失败标 unavailable；偏好不可读不广告 leftover public_fallback。
4. **分钟门**：`minute_sync_allowed` — 自定义解析失败 fail-closed，即使有 TickFlow minute-batch。管道与 HTTP 共用。
5. **偏好异常**：`sync_adj_factor` / `fetch_adj_factor_single` / `adj_live_fetch_allowed` / `adj_sync_uses_public_adapter` / 全量分钟 / 五档 / `_use_public_pools` fail-closed。
6. **extend_history**：公开成分不扩 TickFlow 全 A；复权与管道一样总是调用 `sync_adj_factor`（leftover TickFlow + free 仍走公开新浪 qfq）。

未改：盘后默认时刻、A 股未声明 daily / minute / full_minute / adj 回退 TickFlow（有日志）、leftover TickFlow + free 复权走公开新浪 qfq、TickFlow 默认五档空结果公开 L1、leftover TickFlow 单票公开分时、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、实时 leftover TickFlow + free 仍是 `mode=none`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round7 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_seven_route_hardening.py \
    tests/test_round_six_route_hardening.py \
    tests/test_leftover_route_hardening.py \
    tests/test_remaining_provider_routes.py \
    tests/test_minute_availability.py \
    tests/test_capability_matrix.py \
    tests/test_data_source_write_path.py \
    tests/test_realtime_mode.py \
    tests/test_custom_depth_provider.py \
    tests/test_adj_factor_provider_routing.py \
    tests/test_minute_routing.py
```
