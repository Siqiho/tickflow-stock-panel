# 数据源接线再审计（2026-09-12 round 35 / thirty-fifth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-thirty-four-b177` / PR #36 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: thirty-fifth-round leftover mix-source / fail-open paths that round 34 left documented. kline_loader leftover-glob no longer mix untagged extras beside tagged leftover. Leftover TickFlow financial `_sync_table` / scheduler body and QuoteService watchlist / full-market polls skip after a custom or unresolved daily. Financial HTTP availability no longer fail-opens `Cap.FINANCIAL` when prefs throw. Leftover-part-only public financial merge / share-capital / period-stats still serve extras-only leftover. Ext delete / provenance / snapshot remount no longer leftover-union unreadable extras. Catalog / get_minute stay fail-loud on leftover TickFlow. Leftover TickFlow still sees untagged-only partitions. Leftover TickFlow daily + public realtime still overlays (default install, labeled). Leftover TickFlow + free realtime stays `mode=none`. Explicit `adj=public` / `depth5=public` stay user-selected. After-hours default clock times stay ops schedule.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| kline_loader leftover-glob | `rglob` 后再按文件 `daily_partition_usable` | 同目录 untagged extra 静默混入 leftover TickFlow 筹码 / 日 K 读 |
| leftover TickFlow 财务底层 | `_sync_table` / `_run_body` / `_run_loop` 只在 `sync_all` 门控 | 自定义日 K 后仍可打 TickFlow 财务并盖 last_sync |
| leftover TickFlow QuoteService | 自选 / 全市场 TickFlow 轮询无 daily leftover 门 | 自定义日 K 面再混 leftover TickFlow 实时 |
| 财务 available 异常 | `_fin_available` 偏好抛错后按 `Cap.FINANCIAL` 认可用 | 不可读偏好 fail-open 成专家财务面 |
| leftover-part-only 公开财务 | merge / 股本 / period-stats 只认 `part.parquet` | extras-only leftover 财务被当成没数据 |
| ext 删除 / 物化 / remount | 删除只清 `part.parquet`；物化认坏文件；快照 remount `*.parquet` | 不可读 extra 留下或 leftover-union |

## 改了什么

1. **日 K 读**：`load_daily_bars_for_symbol` 走 `usable_daily_partition_files`，不再 leftover-glob。
2. **作业**：财务 `_sync_table` / scheduler body / QuoteService TickFlow 自选与全市场在自定义 / unresolved 日 K 后跳过。
3. **HTTP / remount**：财务 available 偏好异常 fail-closed；扩展删除清 extras；物化只认可读 parquet；快照 remount 不再 leftover-union 不可读 extras；DuckDB leftover_public 回退去掉。
4. **extras-only leftover**：公开财务 merge / 股本 / period-stats / 策略缓存 mtime / 盘中 overlay stamp / 管道探针看见 leftover extras。

未改：盘后默认时刻（15:30 / 09:10 / 15:02）、leftover TickFlow 日 K + 公开 realtime 仍 overlay（默认安装，带 `is_quote_snapshot`）、leftover TickFlow 仍可见「只有 untagged」的旧分区、实时 leftover TickFlow + free 仍是 `mode=none`、显式 `adj=public` / `depth5=public` / `financial=public` / `pool=public`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round35 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_thirty_five_route_hardening.py \
    tests/test_round_thirty_four_route_hardening.py \
    tests/test_leftover_route_hardening.py
```

云环境结果见 `evidence/test-results.md`。
