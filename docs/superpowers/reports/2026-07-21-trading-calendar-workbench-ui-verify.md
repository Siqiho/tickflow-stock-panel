# trading_calendar 工作台可见性隔离验证

- **时间:** 2026-07-21T22:36:52+08:00
- **代码:** `5827e09`
- **隔离后端:** `http://127.0.0.1:3118`（`DATA_DIR` = 生产 data，只读扫描/展示）
- **隔离前端:** `http://127.0.0.1:3111`（代理到 3118）
- **生产端口 3011/3018:** 未占用、未切换

## API

- `GET /api/data/catalog` 含 `trading_calendar`
- title: `Trading calendar`
- quality: `healthy`
- rows: `1701`
- unit_version: `trading_calendar_v1`
- local_materialized: true

## UI（/data）

- 页面 URL: `http://127.0.0.1:3111/data`
- 存在 region **参考数据**
- 存在 heading **Trading calendar**
- 卡片可见信息：健康 / 本地已落库 / 行数 1,701 / 最早 2025-01-01 / 最新 2026-07-21

## 截图

- 全页: `docs/superpowers/reports/assets/2026-07-21-data-page-trading-calendar.png`
- 参考数据区: `docs/superpowers/reports/assets/2026-07-21-data-reference-region.png`

## 范围确认

- 未改业务读取逻辑
- 未部署到 3011/3018
- 未 push
