# 2026-09-09 行业资金流文档P2收尾回执

- as_of：2026-09-09 14:29 +0800
- 阶段：fix / 文档P2收尾。禁止重做主实现、交付修复、独立产品复核。
- 执行端：本会话 Cursor。要求 Grok 4.6 Extra High。供应商/模型/effort 回执 **未核验**。
- 主台：数据台。次台：用户台。
- 本文件是根据桥接 `finish_report` 由执行端归档的摘要，**不是**原独立 review 全文复制。
- 只改三份文档 + 本回执。未改六源码、正式 data、preferences、调度、服务、测试逻辑；未重跑 H5 / pytest。

## 独立技术复核

- task `9cd3cd22-b5e1-4262-950d-29300d799fed`
- 全新 session `75c6b767-3e2c-422d-ab3b-fcba37faf477`
- 产品 P1 无。P2 仅权威日志（本阶段已改）。

## 本阶段 P2 两处修复

1. 数据台 `ext_fund_flow_bk_daily_industry_roll_live_20260909`：过时句「已登录 Codex 浏览器未做」改为总工 IAB 05:26:04 UTC + 已登录 HTTP 05:37:04 UTC 完成 5/63 窗；401 是未登录事实。回滚改为相对脏树起点 diff 反向 dry-run，冲突/漂移停；行业分区只逆本轮增量，保护后续写入，不整文件覆盖源码或 data 目录。状态记 `accepted`（仅当前受控续更+5/63 窗，不是 production；自然盘后调度仍待观察）。
2. 用户台 `industry_fundflow_daily_roll_live_20260909` 与 `implementation.md`：附独立结论/任务ID/当前范围；`accepted` 仅当下可见窗。整台、概念、日历未完成不可混写。

调度句：三份文档不再把「保留 15:35 / 默认 15:35」写成实际调度。改为保留现有调度逻辑；配置默认 15:30（`preferences.py:419-422`，`_server_path()` → `data/user_data/preferences.json`）/ `daily_pipeline.py:5,6,1347` 注释 15:35 不一致；未观察真实自然触发。未改偏好、源码注释或运行调度。已知后续核对点。计划 `D-R-05` 不改。

文档P2本阶段修正待独立定点复查。

## 核验（本阶段只核文档 diff + 六源码 SHA）

- 核心 24 项金额：独立复核直接 Parquet 逐日求和与总工 HTTP200 12+12 项 `main_net` 全部精确相等（不复制原表）。
- 真实页面/接口：总工 IAB 05:26:04 UTC 已登录 `http://127.0.0.1:3011/` 5/63 满窗；已登录 HTTP 05:37:04 UTC 同端点 200。
- 控制器 `ecf15990-52f4-48f8-ba7f-1d949aba4285` `checks.log`：`14 passed in 4.20s`，exit 0。原 `evidence/pytest.txt` 14 passed in 4.88s / `tsc_exit=0` 仍在。无单独 vitest 日志，不冒充实测。独立 review 未重跑不是漏测。
- 六源码 sha 仍等于已审版本（`evidence/SHA256-six-files.txt`）：

| 文件 | sha256 |
| --- | --- |
| `fund_flow.py` | `304ec3ff2d0a5a6d0175c641ff64d334e50f412d5ad670b1dcb9fa4b2100aa4c` |
| `daily_pipeline.py` | `4a7f7085c034d9f9043b5ba0b9e44dcf9cbb074da570582d1ce3eaef8a011652` |
| `pipeline.py` | `aaa2e1cd391144bb5baa4f8f70aeb5f611e94c67540286d30a5c408b3d239be7` |
| `ext_data.py` | `1fb7425545c5f980633afe5cdb8d4bbef65b1f0a6889659701212503c9c3a6de` |
| `SectorFundFlowPanel.tsx` | `f79dd28a35f38a7e94d909a6bfed93dbde51a65f0f87eb0f5b9e98468ad13f28` |
| `api.ts` | `1d21603da3698d7542e7f2f6c6b254d59408d216e657e8597eb4037e896d5db2` |

- 文档P2改前备份：`/Users/simon/备份/codex/20260909-142907-industry-fflow-docs-p2`

## 剩余

- 自然盘后调度未观察（配置默认 15:30 / 注释 15:35 不一致）。
- 概念正式写入、日历扩修、长周期不在本轮。
- 不是 production。
- 模型配置回执未核验。
