# 资讯 readiness 增量（2026-09-11）

本目录是交接材料，**不是**三台实施权威。权威仍是：

- 用户台：`/Users/simon/Trading/one-trading/docs/workbench-development-log.md#news_policy_workbench`
- 数据台：`/Users/simon/Trading/one-trading/docs/data-platform-development-log.md#news_market_flash` 与 `#news_policy_items`
- A-P1-04 只整理 input/output：[`dsa-input-output.md`](dsa-input-output.md)。**未改** `stock_analyzer`，Agent 日志不写已实现。

## 本轮做了什么

现有 `/news` 增量收口：GET 返回向后兼容的可解释元数据；页面显示来源、时效、失败保旧/空数据、隔离数据身份；整理正式接入前置。保留三路快讯、82 部门目录、筛选/搜索/重点部门/原文/本地分页。

未做：启动/停止任何服务；写正式或旧隔离 10 个 JSON；真实外源抓取；全站权限/主题/调度/Agent；daisyUI / Tailwind 升级。

## 当前状态

- 用户台 2026-09-11 增量：`implemented`。IAB pending。
- 数据台：`isolated`。正式 `data/news` 已有 9/10 五份 JSON，不是 accepted/production。
- 9/9 closeout 的 `verified` / 3041/3048 PID 只作历史。主审再次实查 3011/3018/3041/3048 均未监听。

## 文件

- [`implementation.md`](implementation.md)：改了什么、检查、源码 hash
- [`runtime.json`](runtime.json)：未由本任务启动；负责人确认待回填
- [`formal-admission-plan.md`](formal-admission-plan.md)：正式接入方案，待另行授权
- [`dsa-input-output.md`](dsa-input-output.md)：A-P1-04 独立 input/output，未实施

## 保护缓存（本轮只读，hash 未变）

| 路径 | 条数 | sha256 |
| --- | --- | --- |
| `data/news/policy/items.json` | 56 | `de17d4826c89b72c3990470b3c52316819dba82cb990638a54d737eb9e5bfd1a` |
| `data/news-isolated-20260909/news/policy/items.json` | 526 | `bf6a424d87e7437eb3786e0657feba4857ff0c28ea2eafa4ba24078e4a8aa84c` |
| 正式三源 / 目录 | 20 / 20 / 20 / 82 | 见 implementation.md |
| 旧隔离三源 / 目录 | 20 / 20 / 20 / 82 | 见 implementation.md |

## 备份

`/Users/simon/备份/codex/news-readiness-20260911-20260911-142548`
