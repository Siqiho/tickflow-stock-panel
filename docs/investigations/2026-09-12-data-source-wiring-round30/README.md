# 数据源接线再审计（2026-09-12 round 30 / thirtieth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-twenty-nine-4230` / PR #30 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: thirtieth-round leftover mix-source / fail-open paths that round 29 left documented. Leftover TickFlow single-symbol minute no longer silent-mixes public / TDX; explicit public minute still uses that view. Leftover TickFlow minute / depth / full-minute / adj jobs skip after a custom or unresolved daily. Leftover TickFlow daily + public realtime no longer overlays. Unreadable leftover TickFlow date markers are fail-closed. DuckDB remount no longer fail-opens an ungated leftover view. HTTP ext remount no longer leftover-globs `instruments_ext`. Leftover TickFlow still sees untagged-only partitions. Leftover TickFlow + free realtime stays `mode=none`. Explicit `adj=public` / `depth5=public` stay user-selected. After-hours default clock times stay ops schedule.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 单票分钟公开 / TDX 兜底 | leftover TickFlow 无自定义分钟时打腾讯/新浪/TDX | TickFlow 分时面静默混入公开源 |
| 盘后 leftover 分钟 / 五档 / 全量分钟 / 复权 | 自定义日 K 后仍拉 leftover TickFlow | 自定义日 K 面再混 TickFlow |
| 日 K 覆盖公开快照 | leftover TickFlow 日 K + `realtime=public` 仍 overlay | TickFlow 蜡烛上叠公开快照 |
| 不可读日期标记 | leftover TickFlow 探测失败仍计入日历 | 空/坏 parquet 冒充有数据 |
| DuckDB remount | 门控 CREATE 失败后裸挂 leftover glob | SQL 再看见 leftover TickFlow |
| HTTP ext remount | `instruments_ext` 裸 `**/*.parquet` | 自定义日 K 后维表再混 leftover |

## 改了什么

1. **单票分钟**：`minute_may_use_leftover_public()` 仅显式 `public`；leftover TickFlow 不再公开 / TDX 兜底。
2. **盘后 leftover TickFlow**：`leftover_tickflow_follow_daily()`；分钟同步 / 单票拉取 / 五档 / 全量分钟 / 复权 live 在自定义或 unresolved 日 K 后跳过。
3. **快照 overlay**：日 K 与 realtime 路由必须相同。
4. **不可读标记**：daily / minute / quote_snapshot 探测异常一律 fail-closed。
5. **DuckDB**：门控失败只建空视图，不再裸挂 leftover TickFlow / public。
6. **HTTP ext**：`instruments_ext` 走 `re_gate_catalog_views`，不再 leftover-glob。

未改：盘后默认时刻（15:30 / 09:10 / 15:02）、leftover TickFlow 仍可见「只有 untagged」的旧分区、实时 leftover TickFlow + free 仍是 `mode=none`、显式 `adj=public` / `depth5=public`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round30 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_thirty_route_hardening.py \
    tests/test_round_twenty_nine_route_hardening.py \
    tests/test_leftover_route_hardening.py
```

云环境结果见 `evidence/test-results.md`。
