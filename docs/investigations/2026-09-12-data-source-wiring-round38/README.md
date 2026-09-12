# 数据源接线再审计（2026-09-12 round 38 / thirty-eighth round）

- 性质：实现 + 自动检查。不读 `.env`，不改密钥，不弱化鉴权。
- 坐标：接在 `cursor/harden-round-thirty-seven-e1e4` / PR #40 之后。
- 不是 `accepted` / `production`。正式 `DATA_DIR` 与用户 Mac 运行面不在本环境。
- 本会话最后一轮：关完剩余 fail-open / silent mix，保留 intentional leftover TickFlow 合同。

English summary: thirty-eighth-round leftover mix-source / fail-open paths that round 37 left documented. Leftover TickFlow minute / adj / depth / quote / financial / pool / daily files no longer leftover-serve after a custom or unresolved daily. WebSocket capability no longer advertises live TickFlow after a custom daily just because Cap.WEBSOCKET is present. TickFlow provider primitives skip leftover TickFlow after custom daily. MinuteRefresh leftover TickFlow capability and settings route refresh leftover full-minute loops stop after custom daily. Catalog leftover TickFlow-routed datasets hide after custom daily. ALL expansion also follows leftover_tickflow_follow_daily. Data-lab leftover-glob fallback stays fail-closed. Leftover TickFlow still sees untagged-only partitions. Leftover TickFlow + free realtime stays `mode=none`. Leftover TickFlow daily + public realtime still overlays (default install, labeled). Leftover TickFlow single-symbol minute public view stays. Explicit `adj=public` / `depth5=public` stay user-selected. After-hours default clock times stay ops schedule.

## 还剩什么错

| 故障 | 旧行为 | 后果 |
| --- | --- | --- |
| leftover TickFlow 文件面 | 分钟 / 复权 / 五档 / 行情 / 财务 / 池 cache_usable 在自定义日 K 后仍认 leftover TickFlow | 作业已跳过、标签已说 none，行级仍 leftover-serve |
| 能力面 websocket | Cap.WEBSOCKET 存在就标 `source=tickflow` | 自定义日 K 后把 leftover TickFlow 宣传成 live |
| TickFlow 原语 | `TickFlowProvider` 直接 `get_client()` | 外层已门控，直接调用仍打 leftover TickFlow |
| MinuteRefresh 生命周期 | leftover TickFlow 全量分钟循环仍 `_running` | 自定义日 K 后 leftover 全量分钟看起来还在跑 |
| 设置页 route refresh | 只停财务 / 五档 / 行情 | leftover TickFlow 全量分钟循环继续跑 |
| 目录 leftover 面 | 分钟等 leftover TickFlow 覆盖仍 current | 自定义日 K 后 leftover 分钟 / 复权仍显示可服务 |
| ALL 扩池 | 只看 `daily_provider_is_custom` | unresolved 日 K 仍可能扩 leftover TickFlow 全 A |
| data_lab leftover-glob | import 失败回落 `*.parquet` | 不可读 extra 被 leftover-glob |

## 改了什么

1. **文件面**：`leftover_tickflow_files_allowed` — leftover TickFlow 日 K 仍可见 untagged-only；自定义 / unresolved 日 K 后 leftover TickFlow 文件不再 leftover-serve。显式 public / custom 仍服务。
2. **能力面**：`feature_availability` websocket 在自定义 / unresolved 日 K 后不再用 Cap 冒充 live TickFlow。
3. **原语**：`TickFlowProvider` 日 K / 维表 / 复权 / 实时 / 五档跟日 K 走。
4. **作业生命周期**：MinuteRefresh leftover TickFlow 在自定义日 K 后不再具备轮询能力；设置页 route refresh 同步停 leftover 全量分钟循环。
5. **目录**：已知 leftover TickFlow 路由数据集跟日 K 走；扩展 extras 仍可见。
6. **扩池 / lab**：ALL 扩池同时看 leftover daily；data_lab import 失败 fail-closed。

未改：盘后默认时刻（15:30 / 09:10 / 15:02）、leftover TickFlow 日 K + 公开 realtime 仍 overlay（默认安装，带 `is_quote_snapshot`）、leftover TickFlow 仍可见「只有 untagged」的旧分区、实时 leftover TickFlow + free 仍是 `mode=none`、leftover TickFlow 单票分钟公开视图、显式 `adj=public` / `depth5=public` / `financial=public` / `pool=public`、`.env`、鉴权。Catalog / `/api/data` 存储字节仍看见 leftover 文件（ops leftover，不是行级混源）。

## 怎么验证

在 `backend/` 隔离 `DATA_DIR` 下跑（不触网、不写正式数据）：

```
PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/tmp/ot-data-source-wiring-round38 \
  .venv/bin/python -B -m pytest -q \
    tests/test_round_thirty_eight_route_hardening.py \
    tests/test_round_thirty_seven_route_hardening.py \
    tests/test_leftover_route_hardening.py
```

云环境结果：`1167 passed, 47 warnings`（隔离 `DATA_DIR=/tmp/ot-data-source-wiring-round38`）。详见 `evidence/test-results.md`。
