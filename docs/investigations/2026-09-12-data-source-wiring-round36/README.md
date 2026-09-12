# 数据源接线再审计（2026-09-12 round 36 / thirty-sixth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-thirty-five-d89e` / PR #37 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: thirty-sixth-round leftover mix-source / fail-open paths that round 35 left documented. FinancialScheduler lifecycle now stops after a custom or unresolved daily, not only the sync body. Ext remount empties stale leftover-union views on unreadable / parse failure. Snapshot DESCRIBE no longer leftover-unions unreadable extras. Share-capital and public financial height no longer leftover-part-only fail-open when the gated reader throws. Leftover TickFlow index-instrument primitive skips after custom daily. Financial HTTP / capability status no longer advertise live TickFlow just because `Cap.FINANCIAL` is present. Sector-monitor stamps skip unreadable extras. Catalog / get_minute stay fail-loud on leftover TickFlow. Leftover TickFlow still sees untagged-only partitions. Leftover TickFlow daily + public realtime still overlays (default install, labeled). Leftover TickFlow + free realtime stays `mode=none`. Explicit `adj=public` / `depth5=public` stay user-selected. After-hours default clock times stay ops schedule.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| FinancialScheduler 生命周期 | 日 K / 财务切换只 `update_capabilities`，`_running` 仍为 True | 自定义日 K 后 leftover TickFlow 财务循环看起来还在跑 |
| ext remount `except: pass` | 无可用文件 / 解析失败时 `continue` 或吞异常 | 昨天的 leftover-union 视图留下 |
| snapshot DESCRIBE leftover-union | `_parquet_glob` 快照仍回 `*.parquet` | 不可读 extra 被 DESCRIBE / 列发现 leftover-union |
| 股本 / 公开财务高度 leftover-part-only | `get_financial_df` 抛错后读 `part.parquet` | 不可读偏好 fail-open 成 leftover TickFlow 行数 / 合并底 |
| 指数维表原语 | `_fetch_instruments_by_type` 直接 `get_client()` | 外层已门控，直接调用仍打 leftover TickFlow |
| 财务 status / 能力面 | `Cap.FINANCIAL` 仍标 `provider=tickflow` | 自定义日 K 后把 leftover 本地文件宣传成 live TickFlow |
| 板块监控 stamp leftover-glob | `_data_signature` `rglob("*.parquet")` | 不可读 extra 进入缓存签名 |

## 改了什么

1. **作业生命周期**：`FinancialScheduler.start` / `update_capabilities` 在自定义 / unresolved 日 K 后停循环；设置页 route refresh 同步停调度器。
2. **remount / DESCRIBE**：扩展刷新失败或无可读文件时清空视图；快照 glob 只认可读 extras。
3. **公开财务写**：股本合并与公开财务高度在 reader 抛错时 fail-closed，不再 leftover-part-only。
4. **原语 / HTTP**：指数维表 `_fetch_instruments_by_type` 跟日 K 走；财务 status / `feature_availability` 自定义日 K 后不再用 `Cap.FINANCIAL` 冒充 live TickFlow。
5. **缓存签名**：板块监控 stamp 走 `latest_ext_parquet_files`，不 leftover-glob 不可读 extras。

未改：盘后默认时刻（15:30 / 09:10 / 15:02）、leftover TickFlow 日 K + 公开 realtime 仍 overlay（默认安装，带 `is_quote_snapshot`）、leftover TickFlow 仍可见「只有 untagged」的旧分区、实时 leftover TickFlow + free 仍是 `mode=none`、显式 `adj=public` / `depth5=public` / `financial=public` / `pool=public`、`.env`、鉴权。Catalog / `/api/data` 存储字节仍看见 leftover 文件（ops leftover，不是行级混源）。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round36 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_thirty_six_route_hardening.py \
    tests/test_round_thirty_five_route_hardening.py \
    tests/test_leftover_route_hardening.py
```

云环境结果：`1129 passed, 47 warnings`（隔离 `DATA_DIR=/tmp/ot-data-source-wiring-round36`）。详见 `evidence/test-results.md`。
