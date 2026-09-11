# 检查证据（精简）

本执行端亲眼看到，2026-09-11。

## 后端

```
PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -B -m pytest -q \
  backend/tests/test_news_api.py \
  backend/tests/test_news_service.py \
  backend/tests/test_news_metadata.py \
  backend/tests/test_news_permissions.py \
  backend/tests/free_sources/test_news_public.py
```

结果：`57 passed` / exit 0。夹具与 tmp_path，无外网、无正式/隔离 JSON 写入。

## 前端

```
cd frontend && pnpm exec vitest run \
  src/lib/__tests__/news.test.ts \
  src/pages/__tests__/News.test.tsx
```

结果：`16 passed`（7 + 9）/ exit 0。

未跑：全站 pytest、`pnpm build`、Layout.mobile（本轮未改；其中「实时行情 · 全市场」失败与本包无关）。

## 保护缓存

正式政策 `de17d4826c89b72c3990470b3c52316819dba82cb990638a54d737eb9e5bfd1a`、旧隔离政策 `bf6a424d87e7437eb3786e0657feba4857ff0c28ea2eafa4ba24078e4a8aa84c`，读写前后相同。
