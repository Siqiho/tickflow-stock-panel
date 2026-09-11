# 日期来源续修（2026-09-09）

窄范围修复，不是整项资讯重做。未用旧备份覆盖公共文件。policy.py 未改。

## 变更

- `html_extract.py`：删除宽松 `(20\d{2})[-/]?(\\d{2})[-/]?(\\d{2})` 提取。只接受 `/2026/09/09/`、`t20260909_`、`/2026-09/06/`、`/2026/0907/`。列表日期锁在同一 `<li>/<tr>`，不跨条。
- `news.py`：读/写都 `reconcile_cached_policy_date`；GET 不写盘。`scrub_unproven_policy_dates` 持久化清空拼接/非法/后天之后的日期。
- 隔离缓存：495 条中 46 条拼接日期清空；民委 `1194319` 按官网同条列表日 + 原文 PubDate 记为 2026-09-09。民委单部门有限刷新 +30，合计 525。正式 `one-trading/data` 未写。
- 保留 `live-fetch.json`、`retest-policy-dates.json`。新增 `retest-policy-date-provenance.json`。

## 测试（亲眼看到）

`pytest tests/free_sources/test_news_public.py tests/test_news_service.py tests/test_news_api.py` → 30 passed。

## 运行面

- 3048 PID 53690（旧 29024 已核后只停这一只），无 --reload，`DATA_DIR=news-isolated-20260909`。
- 3011/3018 PID 3528/3510 未动。
- 原 3041 PID 23510 当时已不在；用同一代理命令恢复 54763。
- 经 3041 代理 GET：政策 525、首页无 2026-09-11、1194319=2026-09-09、新能源 4、三栏各 20、GET 未改 items.json。

## 未验证

修后浏览器、独立审查、accepted/production。模型供应商返回证据未核验。
