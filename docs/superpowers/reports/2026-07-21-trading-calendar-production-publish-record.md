# trading_calendar 生产发布记录

- **状态:** PUBLISHED
- **时间:** 2026-07-21T22:18:36+08:00
- **批准:** 用户确认按清单发布；窗口 2025-01-01..2026-07-21；只发日历；不注册工作台；不部署
- **commit:** `065036f31d35ead046084df32aaffd676e4576f6`
- **run_id:** `cal-prod-20260721T141834Z`
- **as_of:** 2026-07-21
- **source:** `szse_month_list`
- **unit_version:** `trading_calendar_v1`

## 产物

| 项 | 路径/值 |
|---|---|
| 正式文件 | `/Users/simon/Trading/one-trading/data/reference/trading_calendar/calendar.parquet` |
| 行数 | 1701 |
| SH 开市日 | 374 |
| exchanges | BJ, SH, SZ |
| lineage | `/Users/simon/Trading/one-trading/data/lineage/trading_calendar/date=2026-07-21/cal-prod-20260721T141834Z.json` |
| staging/quality | `/Users/simon/Trading/one-trading/data/.staging/trading_calendar/cal-prod-20260721T141834Z` / `/Users/simon/Trading/one-trading/data/.staging/trading_calendar/cal-prod-20260721T141834Z/quality_report.json` |
| 备份 | `/Users/simon/备份/codex/20260721-221745-one-trading-before-trading-calendar-publish` |
| dry-run | `/tmp/one-trading-cal-prod-dryrun-20260721T141834Z` |

## 校验

- 隔离 dry-run 双源 equal：是（SZSE SH == 腾讯 SH == 腾讯 SZ，开市日 374）
- 生产 parquet 可读且 PK 唯一：是
- weekend open rows：0
- 未创建 listing/status 正式集：是
- 相对发布前清单，非目标新增/删除/改 size：无
- 本轮新增文件数：5

## 回滚（首发）

```bash
rm -f /Users/simon/Trading/one-trading/data/reference/trading_calendar/calendar.parquet
rm -rf /Users/simon/Trading/one-trading/data/lineage/trading_calendar/date=2026-07-21
rm -rf /Users/simon/Trading/one-trading/data/.staging/trading_calendar/cal-prod-20260721T141834Z
```

## 明确未做

- 未注册 `DATASET_DEFINITIONS` / 工作台
- 未部署、未切端口
- 未 push / 未 merge origin
- 未发布停复牌/上市退市数据集
