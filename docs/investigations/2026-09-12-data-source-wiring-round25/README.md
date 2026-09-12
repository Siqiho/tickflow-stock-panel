# 数据源接线再审计（2026-09-12 round 25 / twenty-fifth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-twenty-four-3628` / PR #25 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: twenty-fifth-round leftover mix-source / fail-open paths that round 24 left on the panel-cache / financial-depth / catalog-token / ext-view / derived-warmup side. Backtest PanelCache now keys by daily route so leftover TickFlow panels cannot be reused after a custom switch. Public financial depth probes use the gated income reader, so leftover TickFlow statements cannot pick light mode. Catalog missing tokens (pre-round-23 control DBs) stay visible only while every route is leftover TickFlow / public; a custom or unresolved switch hides last-scan leftover calendars. Regime batch compute and enriched incremental warmup row-filter leftover TickFlow. DuckDB / screener ext timeseries views mount the latest `date=*` partition only. RPS dimension maps cache by daily route. Unknown `list_partition_dates` tables fail-closed. Leftover TickFlow still sees untagged partitions.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 回测 PanelCache | 缓存键不含 daily route | 同进程切日线源后 180s 内仍用 leftover TickFlow 面板 |
| 管道财务深度探测 | 裸读 `financials/income` | 切财务源后 leftover TickFlow 期数把 public 刷新打成 light |
| catalog 缺 token | 无 token 一律当 fresh | 切源后 pre-round-23 控制库仍 serving leftover 日历 |
| regime 分批回填 | 分区门控后无行级过滤 | 混 route 分区万一漏网会把 leftover 行算进环境日 |
| enriched 增量 warmup | 历史前缀不按 route 滤行 | 切源后 leftover TickFlow 前缀并进当前增量 |
| DuckDB / screener ext | `timeseries/**/*.parquet` 全量 union | 历史分区 leftover 混进筛选/自选/DuckDB |
| RPS 维度映射缓存 | 只按 kind 缓存 600s | 切日线源后 leftover 成分映射仍 join 当前涨幅 |
| 未知表日历 | `list_partition_dates` 裸 glob | 未来调用方把 leftover 分区当成当前日历 |

## 改了什么

1. **PanelCache**：`_make_key` 追加 `daily_route()`；偏好不可读用 `unresolved`，不复用 leftover 面板。
2. **财务深度**：`_public_financial_income_median_periods` 走 `get_financial_df`；stale / 失败返回 0（full deepen）。
3. **catalog token**：缺 token 仅当全部 route 是 leftover TickFlow / public 才 fresh；`unresolved` 或 custom 隐藏 leftover serving。
4. **regime / enriched warmup**：collect 后 `filter_daily_cache`。
5. **ext 视图**：timeseries / `kline_ext` 只挂最新 `date=*`；screener 失败回退走 `_read_ext_dataframe`；缺 config 不再查 DuckDB `ext_*`。
6. **RPS 映射**：`_map_cache` 按 `(kind, daily_route)` 分键。
7. **未知日历**：`list_partition_dates` 对非路由表返回 `[]`。

未改：盘后默认时刻、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、leftover TickFlow 单票公开分时 / 自选历史 TDX、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、显式 `adj=public` / `depth5=public`、Lab leftover TickFlow、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round25 \
  .venv/bin/python -B -m pytest -q \
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

云环境结果：`837 passed, 42 warnings`（隔离 `DATA_DIR=/tmp/ot-data-source-wiring-round25`）。详见 `evidence/test-results.md`。
