# 数据源接线再审计（2026-09-12 round 29 / twenty-ninth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-twenty-eight-5b8d` / PR #29 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: twenty-ninth-round leftover mix-source / fail-open paths that round 28 left after it closed entitled minute call-failure fallback and instruments-follow-daily. Remaining leftover TickFlow instrument readers now follow the daily route. Pipeline remounts gated DuckDB views instead of a raw leftover glob. ST-symbol TTL cache is stamped by instrument route and dropped on provider switch. Lab shadow daily no longer takes leftover `part.parquet` / `extras[0]`. HTTP ext and fund-flow snapshots see extras sitting beside leftover part. Leftover TickFlow still sees untagged-only partitions. After-hours default clock times stay ops schedule.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 估值 / 财务 / 股本 / 质量 / 扩展映射 | 裸读 leftover instruments | 切到自定义日K后仍吃 leftover TickFlow 维表 |
| enriched 管道 | `instruments/**/*.parquet` 裸 glob | 自定义日K复权/涨跌停仍混 leftover 名称与股本 |
| 管道刷新 instruments 视图 | `CREATE VIEW` 裸 `**/*.parquet` | 覆盖 round-28 门控，SQL 再看见 leftover TickFlow |
| 主线 ST 缓存 | 600s TTL 不打 route | 切源后 10 分钟内仍剔除 leftover TickFlow ST |
| Lab shadow 日K | leftover `part.parquet` / `extras[0]` | 自定义 extra 被 leftover TickFlow 挡住 |
| HTTP ext / 资金流快照 | 只读 leftover `part.parquet` | 同日 extra 或 extra-only 新日期从服务面消失 |

## 改了什么

1. **维表读路径**：`read_usable_instruments()`；估值、财务标的、公开股本、质量覆盖、code lookup、ext 名称、enriched 管道共用。
2. **DuckDB**：`_refresh_instruments_view` 走 `refresh_gated_catalog_views`，不再裸 glob remount。
3. **ST 缓存**：按 `instrument_route` 隔离；`refresh_route_surfaces` 清空。
4. **Lab shadow**：日K 用 `usable_daily_partition_files`；维表过滤 leftover。
5. **扩展 / 资金流快照**：`latest_ext_parquet_files` / `usable_ext_snapshot_files` 看见 leftover part 旁的 extra。

未改：盘后默认时刻、leftover TickFlow 单票公开分时 / 自选历史 TDX、实时 leftover TickFlow + free 仍是 `mode=none`、leftover TickFlow 仍可见「只有 untagged」的旧分区与不可读日期标记、显式 `adj=public` / `depth5=public`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round29 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_twenty_nine_route_hardening.py \
    tests/test_round_twenty_eight_route_hardening.py \
    tests/test_leftover_route_hardening.py
```

云环境结果见 `evidence/test-results.md`。
