# 实现说明（2026-09-11）

协调来源：`01a08eff-a837-7103-82fd-860c84b2fbec`。工作树 `/Users/simon/Trading/one-trading`，基线 `main@31216dda527cd4ec177b9cbf6fd1c524dbadbe82`，脏改保留，未 git add/commit。

## 代码

| 文件 | sha256 |
| --- | --- |
| `backend/app/api/news.py` | `ef7e2340de1e3ef3e648d22760b9b42f58188aae813b5c0c1e70f8829de92492` |
| `backend/app/services/news.py` | `49b5cd14573128de95c82f9a7b45417bfc5b8666c5953c4ba362c3b9f04c4d81` |
| `backend/app/services/news_metadata.py` | `f82696859793d5c63c28dea6239c0ebcfdfddb1b3ccc679e015586d8c62139e6` |
| `frontend/src/lib/news.ts` | `cb0ae5f77c21c41a1dce4c170c827691aaeb2bf75f5295c619b624cea09c26eb` |
| `frontend/src/pages/News.tsx` | `eb6f450aa42b0d1493c4eec8cc3bbcb586ef7aea79b1f6bc70864651ad2d85da` |
| `frontend/src/components/news/NewsColumn.tsx` | `9131086c411a0a48357af886c1d19f156267f9f8be6d5500d1d1cf3a6e2e557d` |
| `frontend/src/components/news/NewsMetadata.tsx` | `f1bcd320f0391611da991200d9b51584e4160a13c004163a099849196e42b13c` |
| `frontend/src/components/news/PolicyPanel.tsx` | `5449daf82ce97f538fb1ef57a3387fa659c04a564ded3d397a8a13e779456da8` |

未改：`authorization.py`、`main.py` 中间件、`config.py`、调度、Agent、`stock_analyzer`。`NEWS_CACHE_MODE` 只读进程环境，不进 Settings。

## 行为

- GET `/api/news/*` 叠加只读元数据：生产者/聚合平台、最近成功抓取、最后尝试、缓存更新时间、原文时间独立、中文 `status`/`status_detail`。
- 外媒：`aggregator=TradingView`，`producer=null`，说明不是 go-stock。
- 历史缺字段明确未知；不用文件 mtime 或页面加载时间伪造抓取日；不从 URL 文章编号猜日期。
- 状态：从未抓取、成功空数据、过期（最近成功 ≥24h）、刷新失败保旧、失败无数据、部分部门失败、缓存损坏、401/403/网络、筛选无匹配。
- 失败不刷新 `last_success_at` / `fetched_at`。单部门 `last_refresh.scope=department` 带 `scope_note`。
- GET 零抓取零写。Refresh 仍用进程内锁。无效 `source` → HTTP 400。
- 失败文案去掉 token/路径。原文链接只允许 http(s)。
- 页面：Query/Mutation 错误可见；快讯首日有日期；政策无日期有说明；刷新失败按源/部门；请求错误 ≠ 无记录。移动端结果区 class 契约未改。

## 检查（本执行端亲眼看到）

```
PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -B -m pytest -q \
  backend/tests/test_news_api.py \
  backend/tests/test_news_service.py \
  backend/tests/test_news_metadata.py \
  backend/tests/test_news_permissions.py \
  backend/tests/free_sources/test_news_public.py
# 57 passed

cd frontend && pnpm exec vitest run \
  src/lib/__tests__/news.test.ts \
  src/pages/__tests__/News.test.tsx
# 16 passed
```

未跑全站、未 `pnpm build`、未启动服务。`Layout.mobile.test.tsx` 本轮未改；其中「实时行情 · 全市场」失败与本包无关。

## 保护 JSON（读写前后 hash 相同）

- 正式政策 `de17d4826c89b72c3990470b3c52316819dba82cb990638a54d737eb9e5bfd1a`
- 旧隔离政策 `bf6a424d87e7437eb3786e0657feba4857ff0c28ea2eafa4ba24078e4a8aa84c`
- 正式 cls/sina/foreign/departments：`2640933d…` / `05f739ac…` / `ebd5ce0b…` / `baedbec1…`
- 旧隔离 cls/sina/foreign/departments：`ed12c33a…` / `693b2c30…` / `cf00c754…` / `3f1b5c2b…`

## 负责人运行面（本任务不启动）

需要负责人 `01a07a79-1c8e-73e0-af8f-85939177bb8b` 另行准备：

- `NEWS_CACHE_MODE=isolated_preview`
- `ONE_TRADING_DISABLE_BACKGROUND=1`
- 独立 `DATA_DIR`（不要写正式 `data/news` 或旧隔离）
- 读接口：`GET /api/news/market`、`GET /api/news/policy`、`GET /api/news/policy/departments`、`GET /api/news/policy/key-departments`
- 页面：`/news`、`/news?tab=policy`
- 本轮不要对正式/旧隔离 POST

## 模型

请求配置：Grok 4.6 Extra High（任务声明）。供应商 actual **未核验**。
