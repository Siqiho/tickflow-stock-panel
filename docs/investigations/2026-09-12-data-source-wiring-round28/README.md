# 数据源接线再审计（2026-09-12 round 28 / twenty-eighth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-twenty-seven-dd25` / PR #28 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: twenty-eighth-round leftover mix-source / fail-open paths that round 27 left documented. Declared custom minute *call* failure is fail-closed (no TickFlow mix). Leftover TickFlow + free realtime stays `mode=none`. Instruments follow the daily route: TickFlow stock / index / ETF sync is skipped after a custom or unresolved daily, DuckDB / universe / mainline / OCR / corporate-actions hide leftover TickFlow universe. Quote-snapshot overlay requires matching daily + realtime routes. Lab leftover TickFlow refuses public sina unless the route is explicit `public`. Leftover TickFlow prefers tagged extras over same-day untagged extras; unreadable extras no longer mint calendars. After-hours default clock times stay ops schedule.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 已声明自定义分钟源调用失败 | `_try_custom_minute` 返回 `(None, True)` | 具备 minute cap 时静默混入 TickFlow |
| 个股 / 指数 / ETF 维表 | 裸 `**/*.parquet` + 永远 TickFlow 拉取 | 切到自定义日K后 universe 仍是 leftover TickFlow |
| ALL 标的池空维表 | 空 instruments 再扩 TickFlow 池 / DEMO | 自定义日K切源后仍吃 leftover TickFlow 池 |
| quote_snapshot HTTP 覆盖 | 只按 realtime route 选文件 | 自定义日K上叠 leftover TickFlow 快照蜡烛 |
| Lab leftover TickFlow | `_require_lab_public_surface` 放行 tickflow | leftover TickFlow 走 sina / 公开 Lab 写 |
| leftover 同日 extras | untagged + tagged leftover 一起 concat | 未知来源行混进 leftover TickFlow 日历 |
| 不可读 extra | leftover TickFlow 把坏 parquet 当日期 | 坏文件铸出伪日历 |

## 改了什么

1. **分钟**：已声明自定义源调用失败 fail-closed；leftover TickFlow 分钟源仍可走 entitled TickFlow。
2. **维表**：`instrument_route()` 跟随 daily；自定义 / unresolved 不拉、不写 TickFlow 维表；读路径与 DuckDB 按 route 过滤。
3. **标的池**：自定义 / unresolved daily 空维表不再扩 TickFlow `CN_Equity_A` 或 DEMO。
4. **覆盖**：`_overlay_persisted_quote_candles` 要求 daily 与 realtime 同为 leftover TickFlow 或同为 public。
5. **Lab**：仅 `route=public` 可走公开 Lab；leftover TickFlow 409。
6. **untagged extras**：同日有 tagged leftover 时丢掉 untagged；不可读 extra 失败关。

未改：盘后默认时刻（只改 job 是否拉 TickFlow 维表）、leftover TickFlow 单票公开分时 / 自选历史 TDX、leftover TickFlow + free 仍是 `mode=none`、leftover TickFlow 仍可见「只有 untagged」的旧分区、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round28 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_twenty_eight_route_hardening.py \
    tests/test_round_twenty_seven_route_hardening.py \
    tests/test_leftover_route_hardening.py
```

详见 `evidence/test-results.md`。
