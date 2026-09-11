# 资讯/政策页收口验收（2026-09-09）

主审技术结论：当前实现 + 隔离预览可交用户验收。自动测试 ≠ 用户 `accepted`。

- 用户台 `news_policy_workbench`：`verified`。不是用户 `accepted` / `production`。
- 数据台 `news_market_flash` / `news_policy_items`：保持 `isolated`。隔离实测有 canary 级证据，非正式 `data/news`，不是 `accepted` / `production`，不是全 82 源或全部历史完整采集。

## 当前可用面

- 页面：http://127.0.0.1:3041/news （政策 `?tab=policy`）
- 源码树：`/Users/simon/Trading/one-trading`（主项目工作树）
- 隔离 `DATA_DIR`：`/Users/simon/Trading/one-trading/data/news-isolated-20260909`
- 隔离后端：PID **97934** / `127.0.0.1:3048` / 无 `--reload`
- 隔离前端：PID **97951** / `127.0.0.1:3041` / Vite → 3048
- 正式 3011/PID 3528、3018/PID 3510：本轮未手工重启
- 正式 `one-trading/data/news`：未填充、未验收（仍仅 `.gitkeep`）

运行隔离 ≠ git 工作树隔离。正式 3018 `--reload` 与 3011 Vite 可能拾取同一源树，不能写「正式环境完全不受影响」。

## 功能范围

侧栏「数据」后「资讯」；三路市场快讯（财联社/新浪/外媒）；82 部门政策页（目录、筛选、重点部门、本地关键词、原文、加载更多）。空日期不猜。部分源反爬/SSL 失败可见并保留。P2-2 登录用户共享刷新、P2-5 无 TLS1.2 兜底、单进程锁仍保留。

## 检查（他轮亲眼看到；本收口未重跑）

- 后端 39 passed：独立数据复核 `5613e51d`，526 条真实隔离缓存；`ui-fix/data-review-finish.json`
- 前端 33 passed：独立 UI `e18ac0cf` 亲自跑（News 6 / navGroups 8 / Layout.mobile 19）
- controller build exit 0：`a82d81bd`；fingerprint `2c0c6d396daaead5453b12a93cc64818b09df474df821c9ee299051759cc8fd0`（复核未重算）

## 独立复核与会话分离

- 数据 `5613e51d` Technical PASS。其后附加 UI prompt PING 超时，不在该数据 PASS 范围。
- UI 独立 `e18ac0cf`，全新 session `7f91193c-b466-49db-90ec-2e80a85222d5`，Technical PASS / no P1。
- 原 controller finish.json sha256=`4d628224f80ff517afe87b8cea3f910b3fa2c375a81159b1a6c9932bc0b899ea`。
- 本地语义副本 `closeout/ui-review-finish.json` sha256=`b40b49dea695a85fe4db94a23542dd8f14f511704f3dc19be120f6244d1306ed`（紧凑 JSON 语义原样；**不宣称**与 controller `4d628224…` 字节相同）。`chief-ui.json` 本地 sha256=`951ebd80ce3852b74809ba63795f862b3956cf3da2198505d3e8139a96307fab`。
- 主审 IAB：`closeout/chief-ui.json`（Codex in-app tab 2，不是 Cursor 观察）。
- 历史保持原事实：`c89fcd1c` `protected_input_changed`、`7d39a518` `read_only_candidate_changed`、`1eab309c` completed 但 PING 无结论。不删、不改成成功。

## 主审 IAB（678x863；console error 0）

侧栏资讯在数据后；三栏有真实缓存与原文；CLS 首条可展开。部门 82；政策终态 526；央行 15 条均有日期；长 ID `2026090909080511735`=`2026-09-09`。改后结果区高 381.8046875px（改前 h:2）；可滚到 2026-08-14；关键词「国际清算」1 条后清空恢复 15。Nested scroll 实际可用。宽屏只有源码/`lg:` 复核，本轮无宽屏截图。

## 模型 / 备份回滚

请求/配置：Grok 4.6 Extra High。供应商 actual **未核验**。

文档备份：`/Users/simon/备份/codex/news-policy-closeout-20260909-183503`。更早 UI：`news-policy-ui-fix-20260909-182318`；P2：`news-policy-p2-fix-20260909-174907`。只回本任务 hunks；本轮 closeout 新文件移入废纸篓。不能覆盖他人后续修改。不要停 3011/3018。
