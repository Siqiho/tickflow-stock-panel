# 数据源接线再审计（2026-09-12 round 34 / thirty-fourth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-thirty-three-3261` / PR #34 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: thirty-fourth-round leftover mix-source / fail-open paths that round 33 left documented. Catalog / reference leftover-glob no longer mix untagged extras beside tagged leftover. Leftover-part-only hithink / ext snapshot / financial PIT / fund-flow HTTP still serve extras-only leftover. Leftover TickFlow watchlist quotes skip after a custom or unresolved daily. Remount leftover-union of unreadable extras stays fail-closed. Catalog / get_minute stay fail-loud on leftover TickFlow. Leftover TickFlow still sees untagged-only partitions. Leftover TickFlow daily + public realtime still overlays (default install, labeled). Leftover TickFlow + free realtime stays `mode=none`. Explicit `adj=public` / `depth5=public` stay user-selected. After-hours default clock times stay ops schedule.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| catalog leftover-glob | `_catalog_file_usable` 按文件认 leftover untagged | 同目录 untagged extra 静默混入 leftover TickFlow 覆盖计数 |
| reference leftover-glob | `_scan_dataset` rglob 后再逐文件 filter | 估值 / 涨停事件 leftover 同目录 extra 静默混入 |
| leftover-part-only 官方池 | hithink 最新日 / query 只认 `part.parquet` | extras-only leftover 官方池被当成没数据 |
| leftover-part-only 扩展快照 | 状态 / 物化 / HTTP 资金流只认 `part.parquet` | extras-only leftover 扩展被挡住（与 extras-visible 合同相反） |
| remount leftover-union | `_latest_date_partition_glob` 可读 extras>1 仍回 `*.parquet` | 不可读 extra 被 leftover-union 进 DuckDB 视图 |
| leftover TickFlow 自选行情 | `watchlist.fetch_quotes` 自定义日 K 后仍打 TickFlow | 自定义日 K 面再混 leftover TickFlow 实时 |
| leftover-part-only 财务 PIT | migrate / append 只认 `part.parquet` | extras-only leftover 财务被当成没数据 |

## 改了什么

1. **catalog / reference**：同目录 tagged leftover 旁 untagged extras 不再计入当前覆盖。不可读 tagged leftover 仍 fail-loud。只有 untagged 的旧分区仍服务 leftover TickFlow。
2. **官方池 / 扩展 / 财务**：hithink 最新日与 query、扩展快照状态 / 物化 / 资金流 HTTP、财务 PIT migrate / append 看见 leftover `part.parquet` 旁 extras。
3. **作业 / remount**：自选 TickFlow 行情在自定义 / unresolved 日 K 后跳过；扩展 timeseries remount 不再 leftover-union 不可读 extras。

未改：盘后默认时刻（15:30 / 09:10 / 15:02）、leftover TickFlow 日 K + 公开 realtime 仍 overlay（默认安装，带 `is_quote_snapshot`）、leftover TickFlow 仍可见「只有 untagged」的旧分区、实时 leftover TickFlow + free 仍是 `mode=none`、显式 `adj=public` / `depth5=public` / `financial=public` / `pool=public`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round34 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_thirty_four_route_hardening.py \
    tests/test_round_thirty_three_route_hardening.py \
    tests/test_leftover_route_hardening.py
```
