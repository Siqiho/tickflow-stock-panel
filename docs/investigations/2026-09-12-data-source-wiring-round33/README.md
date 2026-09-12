# 数据源接线再审计（2026-09-12 round 33 / thirty-third round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-thirty-two-d50f` / PR #33 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: thirty-third-round leftover mix-source / fail-open paths that round 32 left documented. In-memory instrument caches no longer leftover-glob untagged extras beside tagged leftover. Unreadable leftover no longer poisons history scans. Leftover-part-only enriched / minute / adj / financial remounts still serve extras-only leftover TickFlow. Leftover TickFlow trading-day probe skips after a custom or unresolved daily. Leftover TickFlow corporate-actions no longer write public sina. User-ext factor frames keep extras visible. Unreadable hithink date markers no longer mint latest. Leftover TickFlow still sees untagged-only partitions. Leftover TickFlow daily + public realtime still overlays (default install, labeled). Leftover TickFlow + free realtime stays `mode=none`. Explicit `adj=public` / `depth5=public` stay user-selected. After-hours default clock times stay ops schedule.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 内存维表 leftover-glob | `get_instruments` 仍扫 `**/*.parquet` 再 filter | 同目录 untagged extra 静默混入 leftover TickFlow 缓存 |
| 不可读 leftover 污染 scan | `scan_usable_daily` / minute 把坏文件放进 scan_parquet | 整段历史扫描失败，screener / backtest / enriched 丢可读 leftover |
| leftover-part-only 读 | enriched / minute-by-symbol / adj / financial remount 只认 `part.parquet` / `all.parquet` | extras-only leftover TickFlow 被当成没数据 |
| leftover TickFlow 交易日探针 | 自定义日 K 后仍打 TickFlow quotes | 自定义日 K 面再混 leftover TickFlow 时钟 |
| leftover TickFlow 公司行动补除权 | `fetch_missing_adj` 在 leftover TickFlow adj 上写 public sina | leftover TickFlow 除权面静默混公开源 |
| 扩展因子 leftover-part-only | 因子帧只读 `part.parquet` | 用户扩展 extras 被挡住（与 extras-visible 合同相反） |
| 不可读 hithink 日期标记 | 空 parquet 仍当最新分区 | 坏文件冒充当前官方池 |

## 改了什么

1. **维表缓存**：`_refresh_instruments` / index / ETF 走 `read_usable_instruments`，不再 leftover-glob。
2. **历史扫描**：`scan_usable_daily` / `scan_usable_minute` 跳过不可读 leftover；catalog / get_minute 路径仍 fail-loud。
3. **extras-only leftover**：enriched 最新日、分钟按标的最新日、adj、财务 DuckDB remount 读当前 route 可用 extras。
4. **作业**：交易日 TickFlow 探针在自定义 / unresolved 日 K 后跳过；公司行动 `fetch_missing_adj` 只在显式 `adj=public` 写 sina。
5. **扩展 / hithink**：因子帧看见 leftover `part.parquet` 旁 extras；不可读 hithink 日期标记不计入最新分区。

未改：盘后默认时刻（15:30 / 09:10 / 15:02）、leftover TickFlow 日 K + 公开 realtime 仍 overlay（默认安装，带 `is_quote_snapshot`）、leftover TickFlow 仍可见「只有 untagged」的旧分区、实时 leftover TickFlow + free 仍是 `mode=none`、显式 `adj=public` / `depth5=public` / `financial=public` / `pool=public`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round33 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_thirty_three_route_hardening.py \
    tests/test_round_thirty_two_route_hardening.py \
    tests/test_leftover_route_hardening.py
```

云环境结果见 `evidence/test-results.md`。
