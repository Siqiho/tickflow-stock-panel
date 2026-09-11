# 资讯三项 P2 修补（2026-09-11）

协调：`01a08eff-a837-7103-82fd-860c84b2fbec`。不重做原实现。原 workflow `wf-bb9c0f1c-efe0-4c8c-86c7-34318de7de9a` failed/verification_failed 与独立审计 `bcc3ee1b-5c6f-44df-8edd-0deda29f30e6` partial/changes_requested 保留，不是 PASS。

备份：`/Users/simon/备份/codex/news-p2-20260911-20260911-172138`

## 三项

### P2-01 政策 24h 新鲜度

`classify_policy_status` 不再用 `cache_updated_at`/`updated_at` 回退判断成功抓取新旧。`last_success_at` 未知时保持 `value=null` / `known=false` / `status=unknown`，明确不能确认新鲜度；不宣布 ok 或 stale。可验证的 `last_refresh.ok is True` + `fetched_at`（或显式 `last_success_at`）仍可推导。GET 字段兼容，不迁移正式缓存。

### P2-02 政策失败写

失败分支不再用 `updated_at` 补造 `last_success_at`。已知旧成功保留（含能由旧 `last_refresh.ok=true`/`fetched_at` 可靠推导的历史）。未知成功在失败写后仍未知。`last_attempt_at` 是本次失败尝试。`cache_updated_at` 只表示本次写缓存，不证明成功。旧条目、单部门 scope、并发较新成功保护保留。

### P2-03 `<xl` 市场栏正文高度

`News.tsx` 单列网格 `max-xl:overflow-y-auto`；`NewsColumn` `min-h-[20rem] xl:min-h-0`，`ul` `min-h-[10rem] xl:min-h-0`。大屏仍三栏。政策页既有 `min-h-[20rem]` / 搜索 / 筛选 / 滚动未改。jsdom class 断言 ≠ IAB 几何。修后几何待主审。

未改：`api/news.py`、`news.ts`、`NewsMetadata.tsx`、`PolicyPanel.tsx`、共享 Layout / `Layout.mobile`、Agent/DSA、正式与旧隔离 10 个 JSON。

## 针对性测试（本执行端看见）

```
PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -B -m pytest -q \
  backend/tests/test_news_api.py \
  backend/tests/test_news_service.py \
  backend/tests/test_news_metadata.py \
  backend/tests/test_news_permissions.py \
  backend/tests/free_sources/test_news_public.py
# 62 passed / exit 0
# 新增：test_policy_unknown_success_does_not_use_cache_times_for_freshness
#       test_policy_freshness_uses_verifiable_last_refresh_or_explicit_success
#       test_policy_failure_updated_at_does_not_invent_success
#       test_policy_failure_old_or_new_cache_times_keep_unknown
#       test_policy_failure_keeps_explicit_and_legacy_success
# 夹具 / tmp_path + mock，无外网，无正式/旧隔离 JSON 写

cd frontend && pnpm exec vitest run \
  src/lib/__tests__/news.test.ts \
  src/pages/__tests__/News.test.tsx \
  src/lib/__tests__/navGroups.test.ts
# 25 passed（7 + 10 + 8）/ exit 0
# News.test.tsx 新增市场栏 class 契约；政策 min-h-[20rem] 契约仍在
```

`pnpm run build`：exit 1。失败点是既有 `Layout.mobile.test.tsx` `mode` 与无关 `Review.tsx` null，不在本包写入范围。本包不改 Layout，不伪称旧组合门变绿。未跑全库 pytest。

## 源 hash

| 文件 | 改前 | 改后 |
| --- | --- | --- |
| `backend/app/services/news.py` | `49b5cd14573128de95c82f9a7b45417bfc5b8666c5953c4ba362c3b9f04c4d81` | `4d737e41b977bd53107aeb8b753e1e80ef44de8f31a237c8775566473832f358` |
| `backend/app/services/news_metadata.py` | `f82696859793d5c63c28dea6239c0ebcfdfddb1b3ccc679e015586d8c62139e6` | `15ce9c9bc64a27cda960c4ddbd747f8a84d49907e2069af59412439e8dfd0817` |
| `frontend/src/components/news/NewsColumn.tsx` | `9131086c411a0a48357af886c1d19f156267f9f8be6d5500d1d1cf3a6e2e557d` | `920836671bac543727b14f30798087a82bf19d3774d987f6b269c984cc592362` |
| `frontend/src/pages/News.tsx` | `eb6f450aa42b0d1493c4eec8cc3bbcb586ef7aea79b1f6bc70864651ad2d85da` | `c2a376a0a10384dfba5c262f538020758dc1919c1b8f74a225887db0ad9a0140` |
| `backend/app/api/news.py` | `ef7e2340de1e3ef3e648d22760b9b42f58188aae813b5c0c1e70f8829de92492` | 未改 |

## 保护 JSON（读写后相同）

正式：cls/sina/foreign/departments/items = 20/20/20/82/56，`de17d482…` 政策未变。  
旧隔离：20/20/20/82/526，`bf6a424d…` 政策未变。不得合并成正式准入。

## 运行面 / IAB

真实运行面由 `01a07a79-1c8e-73e0-af8f-85939177bb8b` 持有：3011 PID64159 Vite → 3018 PID64083 uvicorn **无 reload**，`DATA_DIR=data/shared-isolated-runtime-20260911`，`NEWS_CACHE_MODE=isolated_preview`。本任务未起停进程、未复制缓存、未改运行配置。

后端源码已变。3018 仍加载旧 `news.py` / `news_metadata.py`。**需要 owner 刷新 3018 后再做新 IAB**。不能把旧 PID 旧模块当新代码。前端 Vite 读当前源码，刷新页面可见 P2-03 class；几何仍待主审。

已发生 IAB 只作修前事实：390×844 市场三栏各约 222px，ul 33/33/17px。修后几何未经验收。本执行端未做浏览器验收。

## 生命周期

用户台 `news_policy_workbench`：仍 `implemented`，IAB pending。  
数据台 `news_market_flash` / `news_policy_items`：仍 `isolated`。  
不是 accepted / production。9/9 `verified` 只作历史。

## 模型

请求配置：Grok 4.6 Extra High（任务声明）。供应商 actual **未核验**。
