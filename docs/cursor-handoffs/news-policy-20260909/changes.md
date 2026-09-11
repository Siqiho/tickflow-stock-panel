# 变更、基线、测试

## 当前状态（as_of 2026-09-09 收口）

- 仓库：`/Users/simon/Trading/one-trading`。源码在主项目；运行隔离 ≠ git 工作树隔离。
- 窄屏政策正文：`frontend/src/components/news/PolicyPanel.tsx` 仅 class（根 `grid-rows-[minmax(0,auto)_minmax(20rem,1fr)]` + `max-lg:overflow-y-auto` + `lg:grid-rows-none`；侧栏 `max-lg:max-h-[min(22rem,40vh)]`；结果 `min-h-[20rem]` + `lg:min-h-0`）。`News.tsx` 未改 props/API。
- 前端针对性 vitest：**33 passed**（News 6 / navGroups 8 / Layout.mobile 19）。独立 UI `e18ac0cf` 亲眼看到。controller build exit 0（`a82d81bd`）。
- 后端 39 passed 仍是数据复核 `5613e51d` 证据；本收口未重跑、未再取数。
- 备份：文档收口 `/Users/simon/备份/codex/news-policy-closeout-20260909-183503`；UI `/Users/simon/备份/codex/news-policy-ui-fix-20260909-182318`。更早不要覆盖：`news-policy-p2-fix-20260909-174907`、`news-policy-date-provenance-20260909-162024`、`news-policy-20260909-154419`。
- 未改：go-stock / `authorization.py` / 3011 / 3018 / 正式 `data/news` / `runtime.json`。
- 收口证据：`closeout/acceptance.md`。

下面 P2 段是 as_of P2-fix 历史。**不要**把「前端未改 / 32 passed」读成当前。

## 基线（as_of P2-fix）

- 分支/HEAD：`main@31216dda527cd4ec177b9cbf6fd1c524dbadbe82`（基线，不是本轮政策 commit）
- 工作区在本轮开始时已很脏。只做本轮增量，未 reset/checkout/stash/stage/commit。
- 备份：`/Users/simon/备份/codex/news-policy-p2-fix-20260909-174907/`。更早备份不要覆盖：`news-policy-20260909-154419`、`news-policy-date-provenance-20260909-162024`。
- 未改 go-stock / 前端样式 / authorization / 全局配置 / 3011 / 3018 / 正式 `data/news`。

## 本轮修改（P2-1 / P2-3 / P2-4，as_of P2-fix）

- `backend/app/services/news_sources/html_extract.py`：`date_source`；只把 `/YYYYMM/` 或 `/YYYY/MM/` + 更长文章编号当拼接；长连续数字 ID 不发明、不误清。
- `backend/app/services/news_sources/policy.py`：parser/merge 贯通 `date_source`；同标题跨部门不去掉另一来源。
- `backend/app/services/news.py`：存储/GET 贯通 `date_source`；policy refresh/scrub 与单源 market 替换加进程内锁并重新读当前缓存。
- `backend/app/services/free_sources/news_public.py`：列表无日期时才用本条原文 PubDate。
- 三份 backend 新闻测试：日期回归 + 确定性并发。
- 隔离 `items.json`：只 merge 央行刷新 + 恢复被同标题去重误丢的外汇局原条。
- 授权交接与三台文档的资讯/政策短条。

## 未改（as_of P2-fix；随后已有窄屏 UI class 增量）

- `authorization.py`（P2-2 保留）
- 前端页面/测试/build（**当时**未改；当前已有 `PolicyPanel` class + 第 33 条 vitest，见上文「当前状态」）
- `live-fetch.json` / `retest-policy-dates.json` / `retest-policy-date-provenance.json` / `review/independent-review.md`

## 测试（亲眼看到）

- 后端：`PYTHONDONTWRITEBYTECODE=1 python -B -m pytest tests/free_sources/test_news_public.py tests/test_news_service.py tests/test_news_api.py -q -p no:cacheprovider` → **39 passed**（`5613e51d`；本收口未重跑）
- 前端：as_of P2-fix 未重跑、复用既有 **32 passed** / 当时 build。as_of UI/`e18ac0cf`：**33 passed**（新增 class 契约）。controller `a82d81bd` build exit 0。
- 未跑无关全仓。本收口未重跑构建或测试。

## 隔离运行面

- 核验旧 3048 PID `53690` 后停；`93005` 做央行刷新；`94803` 加载同标题去重修法。为避免 p2-fix live 日志被后续 GET 追加，再起当前 **3048=`97934`**（无 `--reload`），stdout 写入隔离 `DATA_DIR/logs/news-p2-backend.log`。
- 3041：`54763` 已不在 → `94831` → 当前 **`97951`**，stdout 写入 `DATA_DIR/logs/news-p2-frontend.log`。
- 3011/3018（3528/3510）未动。
- 央行一次刷新：列表页 200，15 条 `date_source=list`，长编号 `2026090909080511735=2026-09-09`。磁盘 526。GET 未写 `items.json`。
- p2-fix 只放终态静态报告/快照；live 日志不在候选 artifact 目录。
