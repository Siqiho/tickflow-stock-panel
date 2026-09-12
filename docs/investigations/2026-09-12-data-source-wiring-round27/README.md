# 数据源接线再审计（2026-09-12 round 27 / twenty-seventh round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-twenty-six-c11d` / PR #27 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: twenty-seventh-round leftover mix-source / fail-open paths that round 26 left on extras-blind calendars and leftover caches. Daily / minute dates now see current extras sitting behind leftover `part.parquet`. Paths no longer take leftover `extras[0]`. Screener / overview / overlay / prune / pipeline / mining / regime / quality / financial / depth / quote_snapshot read current-route extras only. Strategy cache is stamped by daily route and dropped on provider switch. Leftover TickFlow still sees untagged partitions.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| daily / minute 日历 | `part.parquet` 存在就只探它 | leftover 占 part 时当前 extra 从覆盖日历消失 |
| daily / minute paths | 优先 leftover `part.parquet`，否则 `extras[0]` | 无 part 时按文件名吃到 leftover TickFlow |
| screener / overview / overlay | 只读 `part.parquet` | leftover 占 part 时看板/选股仍吃 TickFlow |
| prune / pipeline / mining / regime | 只看 leftover part 可用性 | 当前 extra 不修、不进指纹、不标 stale |
| financial / depth / quote_snapshot | 只读 part | leftover 占 part 时当前 extra 不可见 |
| strategy cache | 不打 daily route | 切源后策略页仍返回 leftover 命中 |

## 改了什么

1. **日历 / paths**：`usable_daily_partition_dates` / `usable_minute_partition_dates` 扫全部 extra；paths 只返回当前 route 文件。
2. **读助手**：`read_usable_daily_partition`、`usable_minute_partition_files`、`usable_quote_snapshot_files`。
3. **读路径**：screener、overview official、intraday overlay、quality enriched、reference daily、prune、pipeline coverage / lineage、mining fingerprint、regime stale、minute datetime / refresh、financial extras、depth extras、quote_snapshot extras。
4. **策略缓存**：写入打 `daily_route`；切源 / unresolved 不读 leftover；`refresh_route_surfaces` 清策略缓存与 ext 帧缓存。

未改：盘后默认时刻、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、leftover TickFlow 单票公开分时 / 自选历史 TDX、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、显式 `adj=public` / `depth5=public`、Lab leftover TickFlow、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round27 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_twenty_seven_route_hardening.py \
    tests/test_round_twenty_six_route_hardening.py \
    tests/test_round_twenty_five_route_hardening.py \
    tests/test_leftover_route_hardening.py
```

云环境结果见 `evidence/test-results.md`。
