# P2-1 / P2-3 / P2-4 fix-check

- 执行者：本轮唯一写入 Cursor 会话。不是独立复核。
- 请求/配置模型：Grok 4.6 Extra High。供应商 actual **未核验**。
- 备份：`/Users/simon/备份/codex/news-policy-p2-fix-20260909-174907`
- 前序独立复核：`../review/independent-review.md` 技术 PASS，无 P1。
- `7d39a518` `failed/read_only_candidate_changed` 与 `c89fcd1c` `failed/protected_input_changed` **保持失败**。
- 本增量独立复核仍待完成。不是 accepted/production。不是浏览器验收。

## 改了哪一层

- 数据台：`news.py` / `html_extract.py` / `policy.py` / `news_public.py` / 三份新闻测试 / 隔离 `items.json`
- 用户台：只改授权文档短条（`workbench-development-log.md#news_policy_workbench`、`用户台GitHub项目借鉴记录.md` 2026-09-09 子条）。前端代码未改。
- 未改：go-stock、authorization、3011/3018、正式 `data/news`、P2-2、P2-5

## P2-1 日期 provenance

- `date_source=list|url|pubdate` 贯通 extract / API parser / merge / 存储 / GET。
- 只把 `/YYYYMM/` 或 `/YYYY/MM/` 跨斜杠接到更长文章编号当拼接。
- 长连续数字 ID（央行 `/2026090909080511735/`）不能发明日期，也不能仅因 loose 前 8 位等于存盘日就清空。
- 证据边界：无 `date_source` 的旧缓存，真列表日与长 ID 碰撞时保留；空日期保持空。
- 测试：长 ID + 真列表日、真月份目录拼接、同条碰撞、未知仍未知、GET 零写零外连。

## P2-3 并发

- policy refresh/scrub：`threading.RLock`，fetch 在锁外，写前重新读当前缓存再 merge。
- 失败不把并发成功的最新 items 回滚。
- 单源 market 成功/失败替换各一把 Lock，失败重新读。
- 确定性线程测试已跑。不宣称跨进程锁。用户偏好隔离未改。

## 测试（亲眼看到）

```
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest \
  tests/free_sources/test_news_public.py tests/test_news_service.py tests/test_news_api.py \
  -q -p no:cacheprovider
→ 39 passed
```

前端未重跑；复用既有 32 tests / 当时 build。

## 隔离运行面

| 面 | PID | 说明 |
| --- | --- | --- |
| 3048 当前 | **97934** | 18:02:11，无 --reload，`DATA_DIR=news-isolated-20260909`，`ONE_TRADING_DISABLE_BACKGROUND=1` |
| 3048 已核后停 | 53690 → 93005 → 94803 | 93005 上做了唯一一次央行 POST |
| 3041 当前 | **97951** | 94831 已核后停，按 runtime 命令恢复 |
| 3011/3018 | 3528 / 3510 | 未动 |

持续 stdout：隔离 `DATA_DIR/logs/news-p2-backend.log` 与 `news-p2-frontend.log`。p2-fix 只留静态快照 `startup-log-snapshot.md`，不再放 live 日志。

## 央行一次刷新

- 源：`http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html` → https 200
- fetched=15，`date_source=list`。未用长 ID 猜日，也未走 PubDate 兜底（列表日已足够）。
- 长编号 `2026090909080511735`：空 → `2026-09-09` / list
- 同标题去重曾丢掉外汇局 `https://www.safe.gov.cn/safe/2026/0814/27784.html`；已改为 `(标题,来源)` 去重，并从备份合回。未造数据。
- 磁盘 525 → 526。民委 `1194319` 仍 `2026-09-09`。无 `2026-09-11`。

## GET（3048 直连 + 3041 代理，不是浏览器）

- 政策 total=526，`from_cache=true`
- 央行 15 条全有日期；长编号 list/`2026-09-09`
- 新能源 4；部门 82；三栏各 20
- `items.json` sha256 `bf6a424d87e7437eb3786e0657feba4857ff0c28ea2eafa4ba24078e4a8aa84c` GET 前后不变
- 正式 `one-trading/data/news` 仍仅 `.gitkeep`

紧凑 JSON：`pbc-refresh-evidence.json`
