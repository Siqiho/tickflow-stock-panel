# 隔离验收服务（2026-09-11）

本目录是交接材料，**不是**三台实施权威，也**不是**正式服务恢复或 15:30 管道恢复。

权威仍是：

- 用户台：`/Users/simon/Trading/one-trading/docs/workbench-development-log.md`
- 数据台：`/Users/simon/Trading/one-trading/docs/data-platform-development-log.md`

本任务只准备有界共享隔离验收面，供目录外部两融、市场 5/63/126、资讯 `isolated_preview` 的 Codex IAB 使用。本任务不做 IAB、不改源码、不改 `.env`、不写正式 `DATA_DIR`。

## 当前身份

| 项 | 值 |
| --- | --- |
| 前端 | `http://127.0.0.1:3011/` PID **64159** 2026-09-11 14:51:26 +0800 cwd=`frontend` 当前 Vite 源码 |
| 后端 | `http://127.0.0.1:3018` PID **64083** 2026-09-11 14:50:41 +0800 cwd=`backend` **无 reload** |
| `DATA_DIR` | `/Users/simon/Trading/one-trading/data/shared-isolated-runtime-20260911` |
| 调度 | `ONE_TRADING_DISABLE_BACKGROUND=1`，quote/daily/extpull/financial/minute/depth 全部禁用 |
| 资讯 | `NEWS_CACHE_MODE=isolated_preview` |
| Hermes | 进程环境强制 `false`，未启动 |
| 原包 | 只读 `OFFLINE_QUANTDB_ROOT=/Users/simon/Trading/下载数据/quant_data`（来自现有 `.env`，未改） |

启动前 3011/3018/3041/3048 均无监听，故新起 3011→3018，未复用 3041/3048，未 `dev.sh`，未杀其他进程。

## 认证

隔离库**未设密码**，正式 `identity.sqlite3` **未复制**。本机 GET 走现有「未初始化 + 本机放行」，**不是**绕过认证，也**没有**登录写入。`GET /api/auth/status`：`configured=false`，`authenticated=false`。若 IAB 碰到登录页，需用户自行登录。

## 只读核对（本执行端亲眼看到）

- `/health` 3018 与 3011 代理均为 200，`v0.1.68`
- 资讯：三源各 20、目录 82、政策 56；`cache_identity.mode=isolated_preview`。**没有**把旧隔离 526 当正式实时数据
- 目录本地两融：`GET /api/data/catalog/stock_margin_trading` 200，`local` / `healthy` / 1886 行 / 8 标的 / latest `2026-08-04`
- 外部两融：`external-readonly-sources=configured`；`GET /api/f10/margin-trading?source=offline_quantdb&symbol=300502.SZ&limit=2` → `source=offline_quantdb` / `as_of=2026-08-26`
- 行业窗 5/63/126 均满窗 128/128，截止 `2026-09-10`
- 概念窗 5 满窗 504/504；63 满窗 490/504；126 **不足** 448/504（现有 H5，未伪造）

## 复制与保护

验收输入复制到本次隔离目录（约 4.2MB / 282 文件），**不是备份**。只复制正式资讯 5 JSON、H5 行业/概念快照+日线、交易日历、本地两融 parquet/lineage。未复制 80GB 原包、全日 K、正式 control/identity、旧隔离 526，无软硬链接。

比较范围内 23 个正式/旧隔离文件（含 10 个资讯 JSON、正式 catalog/identity、`.env`、抽样 H5/两融）读写前后 hash **未变**。

## 启动 / 停止

后端命令见 [`runtime.json`](runtime.json) `launch_commands.backend`。前端必须带 `VITE_API_PROXY_TARGET=http://127.0.0.1:3018`。

服务需保持运行。不要为收工停掉。

```
kill 64083   # backend
kill 64159   # frontend
```

不要 `dev.sh`，不要 kill 其他 PID。后续源码改动不会自动更新此后端快照。

## 模型

请求配置：Grok 4.6 Extra High。供应商 actual **未核验**。
