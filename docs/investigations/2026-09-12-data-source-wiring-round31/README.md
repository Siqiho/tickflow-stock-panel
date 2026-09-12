# 数据源接线再审计（2026-09-12 round 31 / thirty-first round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-thirty-57e9` / PR #31 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: thirty-first-round leftover mix-source / fail-open paths that round 30 left documented. Unreadable leftover TickFlow calendars stay fail-closed; reads / catalog / get_minute stay fail-loud on leftover TickFlow. Unreadable tagged leftover no longer falls back to same-day untagged extras. Leftover TickFlow `kline_ext` remount and date-range skip after a custom or unresolved daily; unreadable leftover `kline_ext` markers no longer mint a view. Leftover TickFlow financial / pool jobs skip after a custom or unresolved daily. Explicit public financial / pool still run. Leftover TickFlow still sees untagged-only partitions. Leftover TickFlow daily + public realtime still overlays (default install, labeled). Leftover TickFlow + free realtime stays `mode=none`. Explicit `adj=public` / `depth5=public` stay user-selected. After-hours default clock times stay ops schedule.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 不可读 leftover 日历 | leftover TickFlow 空/坏 parquet 仍可能被日历 / extra 回落吃掉 | 坏文件冒充有数据，或同日 untagged extra 静默混入 |
| 不可读 tagged + untagged extra | tagged leftover 读失败回落到同日无标签 extra | 未知来源 extra 静默混入 leftover TickFlow |
| leftover `kline_ext` remount | 自定义日 K 后仍挂最新 leftover 分区 | SQL 再看见 leftover TickFlow 扩展 |
| 不可读 `kline_ext` 日期标记 | 空 parquet 仍当最新分区 | 坏文件冒充当前扩展面 |
| leftover TickFlow 财务 / 池 | 自定义日 K 后仍拉 leftover TickFlow | 自定义日 K 面再混 TickFlow 财务与成份 |

## 改了什么

1. **不可读日历**：日历仍只认可读 parquet；leftover TickFlow 读路径 / catalog / get_minute 对坏文件保持 fail-loud。
2. **tagged 回落**：`prefer_tagged_route_files` 看见不可读 tagged leftover 不再回落到同日 untagged extra。
3. **`kline_ext`**：只在 leftover TickFlow 日 K 下挂最新可读分区；自定义 / unresolved 建空视图；不可读标记不计入最新分区。
4. **财务 / 池**：`financials_live_allowed` / `get_pool` / `_fetch_pool` / `_ensure_csi_pool` 在自定义或 unresolved 日 K 后跳过 leftover TickFlow。

未改：盘后默认时刻（15:30 / 09:10 / 15:02）、leftover TickFlow 日 K + 公开 realtime 仍 overlay（默认安装，带 `is_quote_snapshot`）、leftover TickFlow 仍可见「只有 untagged」的旧分区、实时 leftover TickFlow + free 仍是 `mode=none`、显式 `adj=public` / `depth5=public` / `financial=public` / `pool=public`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round31 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_thirty_one_route_hardening.py \
    tests/test_round_thirty_route_hardening.py \
    tests/test_leftover_route_hardening.py
```

云环境结果：`1019 passed, 47 warnings`（隔离 `DATA_DIR=/tmp/ot-data-source-wiring-round31`）。详见 `evidence/test-results.md`。
