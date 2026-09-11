# news-policy 交接校验（2026-09-09 16:44）

本文件只做交接校验与最终检查。**不是独立复核，不写 accepted / production。** 未改业务源码、隔离数据、既有交接报告，未启动/重启服务，未再抓官网。

上一轮 **failed** 原状保留：控制器 `protected_input_changed`。根因是主审把从 candidate 复制的旧报告和 `html_extract.cpython-313.pyc` 放进只读 files，同时又要求更新报告/加载新代码。本轮清单已把 pycache 移出只读输入。未改桥或全局设置。

## 保护冲突核对（6 条，无一越界）

冲突路径均为 one-trading 本任务产物，**不是** go-stock / 参考项目 / 无关业务源码。本轮未改它们。

| 路径 | 身份 | 证据 |
| --- | --- | --- |
| `backend/app/services/news_sources/__pycache__/html_extract.cpython-313.pyc` | CPython 3.13 字节码 | magic `f30d0d0a`；header timestamp `1788942439` = 2026-09-09T16:27:19；source_size `15290` 与 `html_extract.py` 完全一致；sha256 `e32579bc608ee30c3b02e9436a75690971090d5c8af9fea3836faa59a6678eac`；`.gitignore:2 __pycache__/`；mtime 16:27:20，`-B` 测试后未变 |
| `docs/cursor-handoffs/news-policy-20260909/README.md` | 已授权交接报告 | sha256 `52a919763201fdda04c1be144ed81ed3607b7b17c44ee672f0e3bcc15d5f2002` mtime 16:28:02 |
| `.../changes.md` | 已授权交接报告 | sha256 `8c38cff16df0b944585a983256fedfff5714b45a834ebff3d46afe8c17054ffb` mtime 16:29:38 |
| `.../feature-matrix.md` | 已授权交接报告 | sha256 `e6ce15d2b5641004f5999eccaa06d3d7ea292fa9800f500ae0a85473f414b0a6` mtime 16:27:57 |
| `.../limitations-rollback.md` | 已授权交接报告 | sha256 `a869920173b50f7d17d4ecc343ac4f8a851f875c3f81b838a522806bd7e967f7` mtime 16:29:37 |
| `.../runtime.json` | 已授权隔离运行面记录 | sha256 `662cb8afb01994f0465e6f1ab4d7642e8e780df1963351f4966f4b0a3bc5840d` mtime 16:29:36 |

## 源文件 hash（本轮前后稳定）

HEAD 仍是 `main@31216dda527cd4ec177b9cbf6fd1c524dbadbe82`。测试前=测试后：

- `html_extract.py` `515cd10590fe0d37dee5fd5fb3392d4673e222d5d54be8d41e15c942d007d2e5` mtime 16:27:19
- `news.py` `a2ab13bae518fe95fabd11c5b390d556af509a9a3ebd27fd74bb1cddcdc80433` mtime 16:24:56
- `policy.py` `156f634ec84a4fb9095c76cb550023ef3b5d918fd8fdfa2a9d4d356799938ce4` mtime 16:00:29（续修声称未改，mtime 早于 provenance 修复）
- 隔离 `items.json` `70e1bd38b03efa14d76055d9576cc366b1dd7c971801460be6de2e291a9be3b0` mtime 16:27:28 size 137725；GET 前后相同

观察：`data-platform-development-log.md` mtime 16:41:10，**本检查未写**。正式 `one-trading/data/news/` 仍只有 `.gitkeep`。go-stock 参考文件 mtime 仍为 12:24:45 / 08-11，未动。

## URL / PID 身份（与 runtime.json 一致，未重启）

- 隔离后端 3048 **PID 53690** PPID 53683 始于 16:28:19：`uvicorn app.main:app --host 127.0.0.1 --port 3048`，env `DATA_DIR=/Users/simon/Trading/one-trading/data/news-isolated-20260909`、`ONE_TRADING_DISABLE_BACKGROUND=1`，无 `--reload`
- 隔离前端 3041 **PID 54763** 始于 16:29:07：vite `--host 127.0.0.1 --port 3041 --strictPort`，env `VITE_API_PROXY_TARGET=http://127.0.0.1:3048`
- 正式面未动：3018 PID **3510**、3011 PID **3528** 始于 05:20:24
- 旧 PID 29024 / 23510 不在

## 只读 API（3048 直连 + 3041 代理，亲眼看到）

两侧 health 200，`version=0.1.68`。政策 GET `total=525` `from_cache=true`；首页日期全是 `2026-09-09`，无 `2026-09-11`。全量 525 条扫描：晚于今天的日期 **0**。`1194319` 仅 1 条，日期 **2026-09-09**，URL `https://www.neac.gov.cn/seac/xwzx/202609/1194319.shtml`。关键词「新能源」**4** 条，`from_cache=true`。部门 82。三栏 cls/sina/foreign 各 20，`ok=true` `from_cache=true`。GET 未改 `items.json`。浏览器由主审负责，本会话未开。

源码对应：`find_date_in_url` 不用宽松 `(20\d{2})[-/]?(\d{2})[-/]?(\d{2})` 发明日期（该正则只留在 `legacy_loose_url_date`）；`/202609/1194319` 测定期望空日期。缓存里 1194319 的 `2026-09-09` 来自续修官网同条列表日 + PubDate，不是月份目录+编号拼接（拼接会得到 `2026-09-11`）。`query_policy` GET 只读；`scrub_unproven_policy_dates` 注释写明 GET 不调用。

## 测试（亲眼看到）

```
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest \
  tests/free_sources/test_news_public.py tests/test_news_service.py tests/test_news_api.py -q
→ 30 passed in 0.30s
```

pycache 与源文件 hash 测试后未变。前端 build 由 controller 跑，本会话未跑。

## 未做 / 未核验

- 独立审查、accepted、浏览器点击
- 供应商模型返回证据：**未核验**（请求面为 Grok 4.6 / Extra High，无实际返回凭证）
- 未改 README/changes/feature-matrix/limitations-rollback/runtime.json
