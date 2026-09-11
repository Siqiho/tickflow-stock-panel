# 数据源接线纠正（2026-09-12）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：本地快照 `cursor/local-snapshot-20260912` 上的云修复分支。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

## 错在哪里

盘后管道、实时行情、复权与看板领涨各自读一套「当前源」，彼此不一致；若干测试已经写了正确契约，实现没跟上。

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| A 股拉取开关 | `get_pipeline_pull_a_share()` 恒 `True` | 数据页取消 A 股无效（#216） |
| 当日日 K 公开合成 | 仅当 `realtime_data_provider=public` | 残留 TickFlow 路由时跳过合成，工作日收盘后没有 `date=today` 分区（9/11 看板核对已记录） |
| TickFlow none/free 实时 | `realtime_mode()` 返回 `watchlist`，能力表仍报 `local_public` | 未选公开源却静默走腾讯/新浪，或反过来宣称有实时 |
| 复权默认 | `same_as_daily` 原样返回；无 `ADJ_FACTOR` 就跳过 | none/free 不拉新浪 qfq，复权空 |
| 板块领涨 | `change_pct or -999` | `0.00%` 被当成缺失，平盘板块领跌股会被写成领涨（#294） |

## 改了什么

1. **preferences**：A 股开关读 `load_server()`；`same_as_daily` 自愈为当前日 K 源。
2. **daily_pipeline**：`should_use_public_eod_fallback` — 今日缺失 + 工作日 + 无 `quote.pool` 即公开合成，**不再看实时路由**。
3. **quote_service / capabilities**：TickFlow none/free → `mode=none`，不拉行情、不改走公开源；能力表 `quote.source=none`。`public` 与自定义源仍是全市场。
4. **kline_sync.sync_adj_factor**：无 TickFlow 复权能力时走已实现的公开复权适配器。
5. **market_overview_builder / overview**：领涨键只把 `None` 当缺失。

未改：盘后默认时刻、分钟全市场、`.env`、鉴权、备份/原包。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-pytest \
  .venv/bin/python -B -m pytest -q \
    tests/test_pipeline_pull_types.py \
    tests/test_public_eod_daily_fallback.py \
    tests/test_realtime_mode.py \
    tests/test_realtime_public_full_market.py \
    tests/test_minute_availability.py \
    tests/test_board_leader_sort.py \
    tests/test_adj_factor_provider_routing.py \
    tests/test_capability_matrix.py \
    tests/test_financial_provider_preference.py
```

手工核对（有正式后端时）：

1. 设置 → 数据源：取消「A 股」后立即同步，日志应有 `pipeline_pull_a_share=False`。
2. none/free 且实时仍为 TickFlow：`GET /api/capabilities` 的 `quote.mode` 为 `none`；当日日 K 缺失时盘后管道仍应写 `public_quote_eod`。
3. 实时改为公开源：`quote.mode=full_market_public`，看板指数走腾讯/新浪。
4. 概念/行业里全员 `0.00%` 的板块，领涨股的 `change_pct` 必须是 `0`，不能是组内最负的一只。
