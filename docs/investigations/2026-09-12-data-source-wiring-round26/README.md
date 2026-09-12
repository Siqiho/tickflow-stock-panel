# 数据源接线再审计（2026-09-12 round 26 / twenty-sixth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-twenty-five-399b` / PR #26 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: twenty-sixth-round leftover mix-source / fail-open paths that round 25 left on the integrity / quality / prune / ext-view / provider-switch / live-gate side. Integrity quote_ts and snapshot scans skip leftover TickFlow extras sitting beside a current-route date. Daily quality concat skips leftover extras before metrics. Prune row counts and stale-price compares skip leftover extras so leftover TickFlow cannot inflate daily vs enriched or false-delete current enriched. Overview / RPS / watchlist / sector-monitor ext timeseries use the latest `date=*` only. Auction OHLC and backtest matrix files/fingerprints skip leftover extras. Settings provider switch re-gates DuckDB views and drops process caches. Enabling realtime now gates on local daily presence and in-window snapshots (409 + repair, no pref write). The after-hours pipeline self-heals in-window snapshots instead of “today exists → quotes only”. Live `_build_daily` maps `timestamp` → `quote_ts` so halted leftover snapshots cannot become today’s candle. Leftover TickFlow still sees untagged partitions.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| integrity quote_ts / snapshot | 同日 leftover extra 裸 glob | 切源后 leftover 盘中 quote_ts 把当前 batch 分区判成快照并触发修复 |
| daily quality | 先 concat 全部 extra 再滤 route | leftover 负量/脏行进质量报告，或 schema 毒化 concat |
| prune row count / stale-price | 同日 leftover extra 计入行数/收盘价 | leftover 把 daily_n 抬高或 close 拉偏，错删当前 enriched |
| overview / RPS / watchlist / 板块 ext | `timeseries/**/*.parquet` 全量 union | 历史 leftover 分区混进看板/轮动/自选/板块成员 |
| auction OHLC / matrix | 同日 leftover extra 进 OHLC / Arrow / fingerprint | 竞价基准与回测矩阵吃到 leftover TickFlow 价 |
| settings 切源 | 只写 prefs，不 re-gate / 不清缓存 | DuckDB 视图与 TTL 缓存继续按旧 route 出 leftover TickFlow |
| 开实时门禁 | 不扫完整性就落 prefs | 昨天盘中快照留下时仍开启今日实时覆写 |
| 盘后管道 | 今天已有分区 → 只刷今天 | 停机日盘中快照永久留存并污染 lookback |
| `_build_daily` | 注释按 quote_ts 滤旧快照，实际丢掉 timestamp | 停牌旧日快照复制成当日假蜡烛 |

## 改了什么

1. **usable extras**：`usable_daily_partition_files` 只收当前 route parquet；probe / unresolved 失败关。
2. **integrity**：`_quote_ts_max_ms` / `_partition_is_snapshot` 只扫当前 route 文件。
3. **daily quality**：先按 route 选文件再 concat；leftover-only 报 `unusable_route`。
4. **prune / stale-price**：行数与 raw_close 比对只读当前 route。
5. **ext 视图**：`latest_ext_parquet_files`；overview / builder / watchlist / RPS / sector-monitor 只挂最新 `date=*`。
6. **auction / matrix**：OHLC、fingerprint、Arrow dataset 只挂当前 route 文件。
7. **切源**：`refresh_route_surfaces` re-gate DuckDB、清 repo / data / overview / regime / screener / RPS / abnormal / benchmark / overlay 缓存。
8. **开实时**：本地无日K / 窗口内快照 → 409，不落开关；窗口内坏日启动 `realtime_gate` 修复。
9. **盘后自愈**：窗口内坏日把 `override_start_date` 降到最早坏日并删对应 enriched。
10. **实时落盘**：`timestamp` → `quote_ts`，按北京日过滤旧快照。

未改：盘后默认时刻、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、leftover TickFlow 单票公开分时 / 自选历史 TDX、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、显式 `adj=public` / `depth5=public`、Lab leftover TickFlow、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round26 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_twenty_six_route_hardening.py \
    tests/test_data_integrity.py \
    tests/test_enriched_stale_price_partition.py \
    tests/test_round_twenty_five_route_hardening.py \
    tests/test_round_twenty_four_route_hardening.py \
    tests/test_round_twenty_three_route_hardening.py \
    tests/test_round_twenty_two_route_hardening.py \
    tests/test_round_twenty_one_route_hardening.py \
    tests/test_round_twenty_route_hardening.py \
    tests/test_round_nineteen_route_hardening.py \
    tests/test_round_eighteen_route_hardening.py \
    tests/test_round_seventeen_route_hardening.py \
    tests/test_round_sixteen_route_hardening.py \
    tests/test_round_fifteen_route_hardening.py \
    tests/test_round_fourteen_route_hardening.py \
    tests/test_round_thirteen_route_hardening.py \
    tests/test_round_twelve_route_hardening.py \
    tests/test_round_eleven_route_hardening.py \
    tests/test_round_ten_route_hardening.py \
    tests/test_round_nine_route_hardening.py \
    tests/test_round_eight_route_hardening.py \
    tests/test_round_seven_route_hardening.py \
    tests/test_round_six_route_hardening.py \
    tests/test_leftover_route_hardening.py
```

云环境结果：`893 passed, 47 warnings`（隔离 `DATA_DIR=/tmp/ot-data-source-wiring-round26`）。详见 `evidence/test-results.md`。
