# 数据源接线再审计（2026-09-12 remaining）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-provider-routing-4003` / PR #4 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: remaining silent wrong-source paths after the provider-routing PR. `Cap.QUOTE_POOL` no longer overwrites a custom daily source with TickFlow quotes. Public `pool_provider` is fail-closed (no TickFlow mix on CSI / CN_Equity_A). Declared custom minute is fail-closed. Live stock/index daily HTTP uses `daily_data_provider`. Custom realtime (`get_realtime` + optional indices) is restored; TickFlow/custom no longer silently top up from public quotes. Depth / minute capability labels report the configured source.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 盘后 `Cap.QUOTE_POOL` | 今天已有日 K 就 `sync_daily_by_quotes` | 日 K 已切扶摇/自定义后，盘后仍用 TickFlow 全市场行情覆写今日分区 |
| `pool_provider=public` | CSI 拉取失败 / 全 A 仍走 `quote.pool` | 设置页选了公开成分，管道 ALL 仍打 TickFlow universes |
| 自定义分钟调用失败 | `_try_custom_minute` 回退 TickFlow | 已声明 minute 的源超时后静默混源 |
| 个股 / 指数日 K 现场补拉 | `sync_daily_batch`（TickFlow） | 缓存未命中时看板/详情忽略 `daily_data_provider` |
| 自定义实时 | `_fetch_full_market_quotes` 只分 public / TickFlow | 扶摇等实时源被当成 TickFlow；核心指数还先打公开源 |
| TickFlow 无付费 Key | 全市场实时回退公开源 | leftover TickFlow 路由静默改走腾讯/新浪 |
| 五档 / 分钟能力表 | 自定义五档无 TickFlow cap 报 unavailable；分钟无 cap 报 public_fallback | UI 与真实路由不一致 |
| 管道指数 / 分钟门槛 | 只看 `Cap.KLINE_*_BATCH` | 未增广的 capset 会跳过已配置的自定义源 |

## 改了什么

1. **daily_pipeline**：自定义日 K 不再走 `sync_daily_by_quotes`。`pool_provider=public` 时 ALL 不用 TickFlow `CN_Equity_A`。指数/分钟步骤在自定义源已解析时也可跑。
2. **pools**：公开成分失败 fail-closed；公开源不能再经 universes 取全 A / 指数。
3. **kline_sync**：已声明的自定义分钟调用失败返回空，不回退 TickFlow。未声明 minute 的旧回退语义未动。
4. **kline / indices API**：现场日 K 走 `fetch_routed_daily`；分钟同步/扩展走 `_minute_allowed`。
5. **quote_service**：恢复自定义 `get_realtime` + `get_realtime_indices`；公开源 bootstrap/补指数仅限 `realtime=public`；TickFlow 无付费客户端 fail-closed。抽出 `_process_full_market_records`（含定版时间戳门槛）。
6. **capabilities / depth**：自定义五档、分钟按配置源标可用；`_depth_source` 报真实源名。

未改：盘后默认时刻、未声明数据集仍回退 TickFlow 的旧语义、`.env`、鉴权。TickFlow 默认五档空结果仍可走公开 L1（产品兜底，仅默认 TickFlow）。实时 leftover TickFlow + free 仍是 `mode=none`。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-remaining \
  .venv/bin/python -B -m pytest -q \
    tests/test_remaining_provider_routes.py \
    tests/test_custom_provider_indices.py \
    tests/test_final_sync_confirmation.py \
    tests/test_index_daily_routing.py \
    tests/test_custom_daily_routing.py \
    tests/test_repair_daily_override.py \
    tests/test_minute_routing.py \
    tests/test_minute_availability.py \
    tests/test_custom_depth_provider.py \
    tests/test_realtime_mode.py \
    tests/test_quote_snapshot_persistence.py
```
