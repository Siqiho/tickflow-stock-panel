# 数据源接线再审计（2026-09-12 round 32 / thirty-second round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-thirty-one-f3d5` / PR #32 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: thirty-second-round leftover mix-source / fail-open paths that round 31 left documented. Unreadable tagged leftover no longer mixes untagged extras in instruments / financials / depth / leftover TickFlow `kline_ext`. Leftover TickFlow DuckDB views no longer coalesce-mix untagged extras beside tagged leftover. Leftover TickFlow adj / minute-batch / monitor / burst jobs skip after a custom or unresolved daily. Unreadable user-ext date markers no longer mint the latest partition. Leftover TickFlow still sees untagged-only partitions. Leftover TickFlow daily + public realtime still overlays (default install, labeled). Leftover TickFlow + free realtime stays `mode=none`. Explicit `adj=public` / `depth5=public` stay user-selected. After-hours default clock times stay ops schedule.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 不可读 tagged leftover + untagged extra | instruments / financials / depth / leftover `kline_ext` 仍可能回落到同日无标签 extra | 未知来源 extra 静默混入 leftover TickFlow |
| leftover DuckDB 视图 coalesce | `coalesce(route, tickflow)` 把同目录 untagged extra 当成 leftover | SQL 再看见混源 |
| leftover TickFlow 除权 / 分钟作业 | 自定义日 K 后 `sync_adj_factor` / `sync_minute_batch` / monitor / burst 仍拉 TickFlow | 自定义日 K 面再混 TickFlow 除权与分钟 |
| 不可读 user-ext 日期标记 | 空 parquet 仍当最新分区 | 坏文件冒充当前扩展面 |

## 改了什么

1. **tagged 回落**：`preferred_readable_route_files` 看见不可读 tagged leftover 不再回落到同日 untagged extra；instruments / financials / depth / leftover `kline_ext` remount 共用。
2. **DuckDB**：leftover TickFlow / public 视图按分区 prefer tagged 可读文件；untagged-only 仍走 leftover glob。
3. **除权 / 分钟作业**：`sync_adj_factor` / `fetch_adj_factor_single` / `sync_minute_batch` / `fetch_intraday_monitor_batch` / burst / increment 在自定义或 unresolved 日 K 后跳过 leftover TickFlow。
4. **user-ext 日历**：不可读日期标记不计入最新分区；同日 extra 仍可见（extras-blind 合同保留）。

未改：盘后默认时刻（15:30 / 09:10 / 15:02）、leftover TickFlow 日 K + 公开 realtime 仍 overlay（默认安装，带 `is_quote_snapshot`）、leftover TickFlow 仍可见「只有 untagged」的旧分区、实时 leftover TickFlow + free 仍是 `mode=none`、显式 `adj=public` / `depth5=public` / `financial=public` / `pool=public`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round32 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_thirty_two_route_hardening.py \
    tests/test_round_thirty_one_route_hardening.py \
    tests/test_leftover_route_hardening.py
```

云环境结果：`1040 passed, 47 warnings`（隔离 `DATA_DIR=/tmp/ot-data-source-wiring-round32`）。详见 `evidence/test-results.md`。
