# 数据源接线再审计（2026-09-12 round 24 / twenty-fourth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-twenty-three-7ae5` / PR #24 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: twenty-fourth-round leftover mix-source / fail-open paths that round 23 left on the catalog-rescan / reference / quote-snapshot side. Catalog rescan no longer writes leftover TickFlow calendars as current coverage after a provider switch. Catalog list/get hide leftover serving after a daily / adj / depth / realtime switch (prefs token now includes those routes). Leftover-only financial bytes no longer become a current calendar. Membership history refuses leftover rewrite after a pool switch. Reference query skips leftover valuation / membership / corporate-actions. Quote snapshots tag and filter by realtime route so leftover TickFlow cannot fill market snapshot, watchlist, overview, or daily overlay after a realtime switch. Corporate-actions prior merge skips leftover after an adj switch. Daily quality skips leftover TickFlow enriched turnover after a daily switch. Leftover TickFlow still sees untagged partitions.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| catalog rescan | 全量扫 leftover 分区再盖 token | 切源后第一次 rescan 把 TickFlow 日历写成当前覆盖 |
| catalog list / compatibility token | 只键 daily/minute/financial/pool；list 仍 serving leftover | 切 adj/depth/realtime 后未 rescan 仍显示 TickFlow 覆盖 |
| 财务 compatibility | leftover-only bytes 仍当已落地 | 切财务源再 rescan 后 0 行仍显示财务日历 |
| 成分历史合并 | 空 seed 仍 rewrite leftover members | 切 pool 源后 leftover 成分被洗成当前文件 |
| reference 查询 | 裸 glob valuation / membership / actions | 切源后 leftover 估值/成分/分红仍进 API |
| quote_snapshot 写/读 | 不按 realtime route 分键 | 切实时源后 leftover TickFlow 快照仍进总览/自选/overlay |
| 估值派生落盘 | 不打 daily route | 切源后 leftover 估值分区无法按源过滤 |
| 公司行为 prior | 无条件 merge leftover | 切复权源后 TickFlow 分红并进当前表 |
| daily quality enriched | 同日 leftover TickFlow enriched 裸读 | 切日线源后 leftover 换手率仍进质量报告 |

## 改了什么

1. **catalog rescan**：扫描只把当前 route 可用 parquet 算进 coverage / artifacts / serving bytes；物理存储仍数 leftover。
2. **catalog list / token**：`catalog_route_token` 含 adj / depth / realtime；切源后 list/get 热路径清空 leftover coverage 且 `serving_ready=False`。个股维表仍 leftover TickFlow。
3. **财务 compatibility**：leftover-only bytes 不再当成当前财务日历（要有当前 route 行）。
4. **成分历史**：`rebuild_reference_derived` 跳过 stale leftover members；写入打 pool route。
5. **reference 查询**：valuation / limit_up / membership / corporate_actions 只读当前 route。
6. **quote_snapshot**：写入打 realtime route；偏好不可读拒绝落盘。总览 / 自选 / overlay / market snapshot 跳过 leftover。
7. **估值派生**：`valuation_daily` / `limit_up_events` 写入打 daily route。
8. **公司行为**：正式发布跳过 leftover prior；打 adj route。Lab leftover TickFlow 仍按声明合同保留。
9. **daily quality**：同日 leftover TickFlow enriched 不进换手率检查。

未改：盘后默认时刻、已声明分钟源调用失败且具备 TickFlow minute cap 时的回退、leftover TickFlow 单票公开分时 / 自选历史 TDX、实时 leftover TickFlow + free 仍是 `mode=none`、个股/指数/ETF 维表仍固定 TickFlow（无 `instrument_provider`）、quote_snapshot 响应覆盖（带 `is_quote_snapshot`）、显式 `adj=public` / `depth5=public`、`.env`、鉴权。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round24 \
  .venv/bin/python -B -m pytest -q \
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
    tests/test_leftover_route_hardening.py \
    tests/test_quote_snapshot_persistence.py \
    tests/test_kline_daily_quote_overlay.py \
    tests/test_market_snapshot_service.py \
    tests/test_reference_derived.py \
    tests/data_catalog/test_service.py \
    tests/data_catalog/test_scanner.py
```

云环境结果：`816 passed, 42 warnings`（隔离 `DATA_DIR=/tmp/ot-data-source-wiring-round24`）。详见 `evidence/test-results.md`。
