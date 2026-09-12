# 数据源接线再审计（2026-09-12 round 37 / thirty-seventh round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-thirty-six-e89b` / PR #39 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。

English summary: thirty-seventh-round leftover mix-source / fail-open paths that round 36 left documented. Capability labels for adj / depth / quote / minute no longer advertise live TickFlow after a custom or unresolved daily just because a Cap is present. DepthService lifecycle and `_depth_source` skip leftover TickFlow after custom daily. QuoteService leftover TickFlow `realtime_mode` is `none` after custom daily. Settings route refresh stops leftover TickFlow depth / quote loops. Pool `_find_universe_id` skips leftover TickFlow after custom daily. Catalog instruments no longer leftover-serve after a custom daily switch. Leftover TickFlow still sees untagged-only partitions. Leftover TickFlow + free realtime stays `mode=none`. Leftover TickFlow daily + public realtime still overlays (default install, labeled). Leftover TickFlow single-symbol minute public view stays. Explicit `adj=public` / `depth5=public` stay user-selected. After-hours default clock times stay ops schedule.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| 能力面 adj / depth / quote | Cap 存在就标 `source=tickflow` | 自定义日 K 后把 leftover TickFlow 宣传成 live |
| 分钟能力面 | leftover TickFlow + 分钟 Cap 仍标全市场 TickFlow | 自定义日 K 后 leftover 分钟作业已跳过，标签仍说 live |
| DepthService 生命周期 | `_has_capability` leftover TickFlow 恒 True | 自定义日 K 后 leftover 五档轮询看起来还在跑 |
| `_depth_source` | 自定义日 K 后仍标 tickflow / local_public | leftover 五档落盘标签混源 |
| QuoteService `realtime_mode` | leftover TickFlow starter+ 仍是 `full_market` | 自定义日 K 后 leftover 实时作业已跳过，模式仍说全市场 |
| 设置页 route refresh | 只停 FinancialScheduler | leftover TickFlow 五档 / 行情循环继续跑 |
| 池原语 `_find_universe_id` | 直接 `get_client()` | 外层已门控，直接调用仍打 leftover TickFlow |
| 目录 instruments | 热路径 / 扫描仍把 leftover TickFlow 维表当 current | 自定义日 K 后 leftover 标的覆盖仍显示可服务 |

## 改了什么

1. **能力面**：`feature_availability` 的 adj / depth / quote 与 `minute_availability` 在自定义 / unresolved 日 K 后不再用 Cap 冒充 live TickFlow。分钟单票公开视图仍保留 leftover 合同。
2. **作业生命周期**：DepthService leftover TickFlow 在自定义日 K 后不再具备轮询能力；QuoteService leftover TickFlow `realtime_mode` 变为 `none`；设置页 route refresh 同步停 leftover 五档 / 行情循环。
3. **原语**：池 `_find_universe_id` 跟日 K 走。
4. **目录**：`stock_instruments` / `etf_instruments` / `index_instruments` 跟日 K 走；热路径在自定义日 K 后不再把 leftover TickFlow 维表标成 current。

未改：盘后默认时刻（15:30 / 09:10 / 15:02）、leftover TickFlow 日 K + 公开 realtime 仍 overlay（默认安装，带 `is_quote_snapshot`）、leftover TickFlow 仍可见「只有 untagged」的旧分区、实时 leftover TickFlow + free 仍是 `mode=none`、leftover TickFlow 单票分钟公开视图、显式 `adj=public` / `depth5=public` / `financial=public` / `pool=public`、`.env`、鉴权。Catalog / `/api/data` 存储字节仍看见 leftover 文件（ops leftover，不是行级混源）。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round37 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_thirty_seven_route_hardening.py \
    tests/test_round_thirty_six_route_hardening.py \
    tests/test_leftover_route_hardening.py
```

云环境结果：`1149 passed, 47 warnings`（隔离 `DATA_DIR=/tmp/ot-data-source-wiring-round37`）。详见 `evidence/test-results.md`。
