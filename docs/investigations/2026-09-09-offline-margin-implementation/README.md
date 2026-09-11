# D-OFFLINE-MARGIN-API 实现（2026-09-09）

主台：数据台。本轮是功能实现，不是全市场数据验收，也不是 accepted/production。

## 改动

- `GET /api/f10/margin-trading` 默认仍读自有 local；增加 `source=offline_quantdb`。只读 `2_base_sector/margin_trading/<标准symbol>.parquet`，不扫其他布局、不写盘、不联网。
- 配置键 `OFFLINE_QUANTDB_ROOT`：源码默认关闭；本机 `.env` 已开启并指向 `quant_data`。HTTP 不能传文件路径。
- 候选映射：`finance_balance/buy/net` 与 `slo_sell_amount×10000`；`finance_repay`→融券卖出量；`slo_volume`/`slo_repay`。源无 `securities_lending_balance`、`margin_balance`，保持 null。缺文件/缺列/损坏与合法空窗可分辨。
- `user_console_data.stock_margin_trading` 可传 `source`，不是新查询页。
- K 线：`_scan_daily_symbol` / `get_minute` 无文件仍空；损坏抛 `KlineReadError`。对应 GET 返回 503，不触发 TickFlow/TDX。

## 检查

- 相关 pytest 一次：`38 passed`。`test_repository_index` 与一条 `daily_latest` 失败是脏树既有问题，本轮未改那些接口。
- 实施当时 3018 `--reload` 监督 PID `3510`，worker `36813` 于 16:12:35 拉起。当时对 `300502.SZ` 的 local/offline GET 均为 HTTP 401（未登录），只作历史。
- 同 venv 只读真实文件：local 5 行 `as_of=2026-08-04`；offline 5 行 `as_of=2026-08-26`，两列 null。源文件与自有 `part.parquet` hash 未变。

## 最终结论

Codex IAB（约 16:24 +08）在已登录的 `3011`（代理 3018）同源 GET local / `offline_quantdb` 均为 HTTP 200：count=5，as_of 分别为 2026-08-04 / 2026-08-26。独立 review `2f6bf8b8-878e-452d-9a05-45222c04efeb` PASS，无必改 P1/P2。小样本功能可收；不是全市场 `accepted` / `production`。未重跑 38 项，禁止写成全仓通过。

## 回滚

`/Users/simon/备份/codex/20260909-160932-offline-margin-kline-read`；从 `.env` 删除 `OFFLINE_QUANTDB_ROOT`。
