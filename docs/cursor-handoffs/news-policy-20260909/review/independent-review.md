# 独立复核：资讯/政策页（news-policy-20260909）

- 复核身份：全新独立 Cursor 会话，不是实现者，也不是校验会话 `9de57887-8624-4a94-9cb7-7cf6ef2be611`。
- 复核对象：实现 `27eaa384-683a-41d7-a4f3-60d839107d61` + 日期续修 `c89fcd1c-01b0-4832-8722-2941affea0b8` 之后、由 `9de57887` 封存的最终候选。
- 绑定 fingerprint（controller 声明，本会话未重算整包）：`820bb541b60df374868e6e09639afa1ea226e802ded96de4e475573c06707da0`。
- 前序 fingerprint `b8de02f55c2b0ac009d51a26e8639fa063e9275b5a028932d665b021569f0f09` 只作历史线索。
- **技术结论：PASS。无 P1 拒收项。有 P2，不阻止技术通过。**
- 不是用户 accepted，不是 production，不是 verified 浏览器验收。
- 模型请求面为 Grok 4.6 / Extra High；供应商实际返回证据 **未核验**。

`c89fcd1c` 的 controller `failed/protected_input_changed` **历史保持不变**。根因是旧 candidate 把 pycache 与需更新报告列成只读 inputs，不是测试/运行失败。本复核同时覆盖该保护冲突与最终检查，不把校验会话当作独立复查完成。

`ctb-task.write_report` 在 review/read 任务上被服务器拒绝（`write_report_rejected_for_read_task`）。本文件由复核会话写入授权 artifact 目录，仅为交付独立复查报告。

---

## 1. 进程 / 数据身份（本会话亲眼看到）

| 面 | PID | 启动 | 命令/环境 | 结论 |
| --- | --- | --- | --- | --- |
| 隔离后端 3048 | **53690** PPID 53683 | 2026-09-09 16:28:19 +0800 | `uvicorn app.main:app --host 127.0.0.1 --port 3048`；`DATA_DIR=/Users/simon/Trading/one-trading/data/news-isolated-20260909`；`ONE_TRADING_DISABLE_BACKGROUND=1`；**无 `--reload`** | 与 `runtime.json` 一致 |
| 隔离前端 3041 | **54763** | 2026-09-09 16:29:07 +0800 | vite `--host 127.0.0.1 --port 3041 --strictPort`；`VITE_API_PROXY_TARGET=http://127.0.0.1:3048` | 代理目标正确 |
| 正式后端 3018 | 3510（另有 reload worker 51415） | 05:20:24 | `--reload --host 0.0.0.0 --port 3018` | **未动** |
| 正式前端 3011 | 3528 | 05:20:24 | vite `0.0.0.0:3011` | **未动** |
| 旧 PID 29024 / 23510 | 不在 | — | — | 过时 |

- one-trading HEAD：`main@31216dda527cd4ec177b9cbf6fd1c524dbadbe82`（与交接一致）。
- 正式 `one-trading/data/news/` 仍只有 `.gitkeep`。本复核 GET **未写** 隔离 `items.json`（sha256 始终 `70e1bd38b03efa14d76055d9576cc366b1dd7c971801460be6de2e291a9be3b0`，mtime 16:27:28）。
- GET 会追加隔离目录 `logs/access.log` / `app.log` / `runtime.jsonl`（既有平台访问日志，不是 news 模块落地缓存）。
- `/health`：3048 与 3041 均为 200，`version=0.1.68`。`/api/health` 在 3041 为 404（后端探活路径是 `/health`，不是缺陷）。

关键源文件 hash（测试后未变）：

| 文件 | sha256 | mtime |
| --- | --- | --- |
| `html_extract.py` | `515cd10590fe0d37dee5fd5fb3392d4673e222d5d54be8d41e15c942d007d2e5` | 16:27:19 |
| `news.py` | `a2ab13bae518fe95fabd11c5b390d556af509a9a3ebd27fd74bb1cddcdc80433` | 16:24:56 |
| `policy.py` | `156f634ec84a4fb9095c76cb550023ef3b5d918fd8fdfa2a9d4d356799938ce4` | 16:00:29 |
| `authorization.py` | `e85f5965eca59b0dce4f06aefb935680204c98e7d364391c53b58016215a74cd` | 15:46:19 |
| 隔离 `items.json` | `70e1bd38b03efa14d76055d9576cc366b1dd7c971801460be6de2e291a9be3b0` | 16:27:28 |

---

## 2. 续修 failed 保护冲突：仅生成缓存 / 已授权报告

对照备份声明与当前磁盘，下列 6 条 **无一是 go-stock / 无关业务源码越界**。本复核未改它们；测试后 hash 仍与 `check-seal/final-check.md` 一致。

| 路径 | 身份 | 本会话 sha256 / 证据 |
| --- | --- | --- |
| `backend/app/services/news_sources/__pycache__/html_extract.cpython-313.pyc` | CPython 3.13 字节码 | `e32579bc608ee30c3b02e9436a75690971090d5c8af9fea3836faa59a6678eac`；magic `f30d0d0a`；header ts `1788942439` = 2026-09-09T08:27:19Z；source_size `15290` 与 `html_extract.py` 一致；mtime 16:27:20；`-B` 测试后未变 |
| `docs/cursor-handoffs/news-policy-20260909/README.md` | 已授权交接报告 | `52a919763201fdda04c1be144ed81ed3607b7b17c44ee672f0e3bcc15d5f2002` |
| `.../changes.md` | 已授权交接报告 | `8c38cff16df0b944585a983256fedfff5714b45a834ebff3d46afe8c17054ffb` |
| `.../feature-matrix.md` | 已授权交接报告 | `e6ce15d2b5641004f5999eccaa06d3d7ea292fa9800f500ae0a85473f414b0a6` |
| `.../limitations-rollback.md` | 已授权交接报告 | `a869920173b50f7d17d4ecc343ac4f8a851f875c3f81b838a522806bd7e967f7` |
| `.../runtime.json` | 已授权隔离运行面记录 | `662cb8afb01994f0465e6f1ab4d7642e8e780df1963351f4966f4b0a3bc5840d` |

**不因此把 `c89fcd1c` 改写成成功。** 只确认冲突路径不是业务越界。

---

## 3. 范围 / 备份：无非任务业务源码改写

基线：`/Users/simon/备份/codex/news-policy-20260909-154419/`（18 个原文件）。

- `routes.py`、`MenuSettings.tsx`：**与备份完全相同**。
- `authorization.py`：相对备份 **只多一行** `"/api/news"`，位于 `_PERSONAL_MUTATION_PREFIXES`（当前 L56）。管理员前缀、共享读、其他写路由未放宽。主审已授权这一窄范围增量。
- `main.py`：只增加 `news` import 与 `app.include_router(news.router)`（约 L40、L572）。
- 前端 `Layout.tsx` / `navGroups.ts` / `router.tsx` / `api.ts` / `queryKeys.ts` 及对应测试：增量均为 `/news` 导航、图标、API、钉尾顺序。
- 三台文档：资讯/政策短卡、`U-R-01`、`D-R-06`、开发日志 `4.19`/`4.20`/`news_policy_workbench`。

**共享日志并存（不判 FAIL）：** `data-platform-development-log.md` 与 `数据台下一步工程工作计划.md` 在本任务备份之后还写入了并发任务 `D-OFFLINE-MARGIN-API` / `4.21`（mtime 16:41 / 16:16）。这是脏树上另一已授权任务的共享日志，不是本资讯模块业务源码，也不是 go-stock 改动。新闻增量是 `4.19`/`4.20` 与 `D-R-06`。

go-stock 参考文件 mtime 仍为 12:24:45 / 08-11；本复核只读，实现候选也未改它们。

---

## 4. go-stock HEAD vs dirty（不能把工作树新实现归到旧 commit）

本地分支：`codex/upstream-dev-20260831-integration` HEAD **`e96f5d7262fae35698b4bebd4b8650f8bfdf0e71`**。

| 文件 | 工作树 sha256 | 与 HEAD |
| --- | --- | --- |
| `PolicyNewsList.vue` | `4dc45ed4adcadb4e38b7b91e704236f190843a4748ffc524a6e163a9888e0bab` | **未入 HEAD（untracked）** |
| `policy_news_api.go` | `b500037e04a4f032013e809b40ac6002727f11c588cb64b3f1dd052804d0295b` | **未入 HEAD（untracked）** |
| `gov_policy_lib_api.go` | `dac2ef990e490aad0fdfd2f9f94b463ba057df38951325bb1fb469e204c8b10d` | **未入 HEAD（untracked）** |
| `market.vue` | `772ba7e1df0fe465683a0f312caa492c913788ed456b547594d0cb7a965b2310` | **DIRTY**；HEAD=`d26eea85968a5b77df0d4b53f6092a2e579d559c102529a82147c18838bb4f7c`。脏树比 HEAD 多政策页签，以及游资/期指/AI 参数等（本任务明确不扩） |
| `newsList.vue` | `44e689226407492b77ebf0f68cec4b28ce3f2deec92ca05c058e41ada9363c36` | 与 HEAD **相同**（2026-08-11） |
| `market_news_api.go` | `985534cc20cb1bf9a5864c674d81314f0eb61706b1c9ea9c3bbaf40589f4125f` | 与 HEAD **相同**（2026-08-11） |

`feature-matrix.md` L3–10 已正确写明：`e96f5d` 是合流基线，**不是** 2026-09 政策页引入点；政策/三栏权威是 **dirty 工作树 hash**。工作树 hash 与 matrix 声称值一致。

文档误差（P2，不拒收）：`workbench-development-log.md` 仍写「功能权威是本地 go-stock HEAD `e96f5d…`」；`用户台GitHub项目借鉴记录.md` 2026-09-09 子条同样把 `PolicyNewsList.vue` / `policy_news_api.go` 归到该 HEAD。这两份文件在 HEAD 中不存在。

---

## 5. 日期来源疑点：独立无网络复现

当前 `find_date_in_url`（`html_extract.py` L165–185）**不再**用宽松 `(20\d{2})[-/]?(\d{2})[-/]?(\d{2})` 发明日期。该正则只留在 `LEGACY_LOOSE_URL_DATE_RE`（L24、L188–199），供缓存 provenance 检测。

本会话 `python -B` 复现（today=`2026-09-09`）：

| path | `find_date_in_url` | `legacy_loose_url_date` |
| --- | --- | --- |
| `/202609/1194319.shtml` | `""` | `2026-09-11` |
| `/seac/xwzx/202609/1194319.shtml` | `""` | `2026-09-11` |
| `/202607/1200abc.shtml` | `""` | `2026-07-12` |
| `/t20260909_123.html` | `2026-09-09` | `2026-09-09` |
| `/2026/09/09/` | `2026-09-09` | `2026-09-09` |
| `/2026/09/1194319.shtml` | `""` | `2026-09-11` |
| `/2026090909080511735/index.html` | `""` | `2026-09-09` |

`reconcile_cached_policy_date`：

- NEAC + 存储 `2026-09-11` → `""`（拼接未来日被清）。
- NEAC + 存储 `2026-09-09` → `2026-09-09`（与 legacy `2026-09-11` 不等，保留；不是月份目录+编号）。
- **PBC 长编号** `.../2026090909080511735/index.html` + 存储 `2026-09-09` → `""`。这是剩余 P2：loose 匹配到长数字串前 8 位，就把真实列表日当成拼接清掉。

邻条：用与测试相同的 6 条 `<li>` HTML 跑 `extract_policy_list_items`。无列表日的 `/202609/1194319` 与 `/202607/1200abc` **不会入库**（不从邻条借 `2026-09-08`）；带 `<span>2026-09-08</span>` 的本条得到 `2026-09-08`；`t20260909_` 与 `/2026/09/09/` 用自身 URL 日期。`find_publish_hint_date` 对 `<meta name="PubDate" content="2026-09-09 14:50:53"/>` 得到 `2026-09-09`。

隔离缓存磁盘：525 条；`2026-09-11` **0** 条；晚于明天 **0** 条；`1194319` 仅 1 条，日期 **2026-09-09**，URL `https://www.neac.gov.cn/seac/xwzx/202609/1194319.shtml`。磁盘空/非法日期 54（含已 scrub 的拼接日 + 后续空日期条目）。缓存修正对「月份目录+文章编号 → 未来日」足够；**不能**只看 YYYY-MM-DD 合法。

---

## 6. 只读 API（3048 直连 + 3041 代理）

禁止远端全量抓取；本会话只 GET。

| 检查 | 3048 | 3041 代理 |
| --- | --- | --- |
| 政策 `total` / `from_cache` | 525 / true | 525 / true |
| 首页日期 | 全 `2026-09-09` | 首条 `2026-09-09` |
| 全量 525 扫描 `2026-09-11` / 后天之后 | 0 / 0 | — |
| `1194319` | 1 条，`2026-09-09` | — |
| 关键词「新能源」 | 4，`from_cache=true` | — |
| 能源局+新能源 | 4（同 4 条公告） | — |
| 部门 | 82，`ok=true`，`from_cache=true` | — |
| 三栏 cls/sina/foreign | 各 20，`ok=true`，`from_cache=true` | 各 20 |
| `items.json` GET 前后 | hash/mtime 不变 | 同左 |

财联社缓存 `fetched_at=2026-09-09T16:35:53+08:00`，首条时间 `16:34:33`、id `cls:2478286`。这是 **API/文件** 证据，不是本会话 UI 点击。

重点部门 GET：12 个默认名，`is_default=false`（磁盘已有 `user_data/news/key_departments.json`，内容即这 12 个；空文件才会 `is_default=true`）。本复核 **不做** 主审「加外交部再恢复」的 UI 复述。

央行部门过滤：14 条，其中 **13 条 date 为空**。与上面 PBC reconcile 误伤一致，见 P2-1。

`query_policy`（`news.py` L444–478）只读 JSON + 内存 reconcile，**不**调用 `scrub_unproven_policy_dates`（L396–397 注释与代码一致）。GET 零外连：service 层无 fetch；本机 GET 未改 news 缓存文件。

---

## 7. 安全 / 并发 / 权限

- Allowlist + 官方目录 host：`allowlist.py`。拒绝非 http(s)、userinfo、localhost/private/link-local/reserved；redirect 逐跳 `validate_http_url` + `resolve_public`（L178–201）。pytest `test_ssrf_rejects_private_and_non_http` 覆盖字面量。
- HTML：stdlib `HTMLParser`，不执行源 JS。新浪只剥 JSONP 再 `json.loads`（`sina.py` L28–41）。
- 前端链接：`isSafeHttpUrl` 仅 http(s)；政策/快讯标题为文本节点，无 `dangerouslySetInnerHTML`。
- 公共缓存 vs 个人偏好：market/policy/departments 在共享 `DATA_DIR/news/`；重点部门走 `user_path` → `tenants/<id>/user_data` 或 legacy `user_data`（`user_context.py` L45–80，`news.py` L76–77）。pytest alice/bob 隔离通过。
- `/api/news` 列入个人写前缀后，**已登录普通用户可以对共享快讯/政策缓存 POST 刷新**（不只写重点部门）。这是已授权设计，不是管理员边界被放宽到其他旧路由。残留：任意登录用户可触发全部门抓取（P2-2）。
- 写盘：`atomic_write_json` 临时文件 + `os.replace`（`atomic_io.py` L81–93）。**news 模块没有** 读-改-写锁；两并发 POST 可能丢更新（P2-3）。
- `user_path(..., create=True)`：GET 重点部门可能 `mkdir` 用户目录。本次目录/文件已存在，未新建 `key_departments.json`。
- DNS 解析后仍按 hostname 发请求：常见 TOCTOU 残留，不升 P1。

---

## 8. 对照 go-stock 的真实功能差异（不扩 AI/通知/行情）

已覆盖且契约对齐的：侧栏数据后「资讯」；市场三栏财联社/新浪/外媒（时间、标题/正文展开、题材、股票、原文、is_red、情绪、独立刷新）；政策完整部门目录、按日倒序、部门筛选/搜索、重点部门增删保存恢复、官网、已入库关键词搜索、换部门保留关键词、刷新（全目录浅抓 / 单部门 30）、失败保留历史、本地分页说明。`gov_policy_lib_api.go` / `sousuo.www.gov.cn` **未接入**（正确）。

应如实列出的差异（多数为有意收紧或非目标）：

1. **首次空缓存**：go-stock `PolicyNewsList.vue` L299–310 读库为空会自动 `fetchLatest()`（联网）。one-trading GET 保持空，UI「请点击刷新」。符合「GET 零外连」。
2. **后台 `EventsOn("policyNewsUpdated")`**（go-stock L385–388）：未做。符合禁止全局定时。
3. **URL 日期**：go-stock `policy_news_api.go` L717–718 仍是宽松 `(20\d{2})[-/]?(\d{2})[-/]?(\d{2})`，会把 `/202609/1194319` 收成 `2026-09-11`。one-trading 已收紧。功能复刻在日期上 **严于** 上游脏树。
4. **情绪**：规则词表，不是 gse 分词。标签仍看涨/看跌/中性。
5. **TLS1.2 / 双重试**：go-stock `fetchGovPageRobust`（L530–546）。one-trading 仅 httpx 默认。与交接中统计局 SSL timeout、部分部门 4xx/5xx 同类，失败可见且不覆盖其他源。
6. **市场页其余页签**（全球股指、AI 摘要、期指、游资等）：按要求不搬。go-stock 外媒栏在空列表时缩成两栏；one-trading 固定三栏。
7. **单部门空态文案**：go-stock 有「可能为动态渲染站点」；one-trading 通用「暂无数据」。
8. **本地「加载更多」**：上游无可见分页；one-trading 多了缓存翻页（已声明）。
9. 无日期条目：两边解析都丢弃（go-stock L647–649；`html_extract.py` L372–373）。无列表日的月份目录文不会仅凭 URL 入库；历史靠 merge 保留。

---

## 9. 本会话测试（亲眼看到，`-B` / `PYTHONDONTWRITEBYTECODE=1`）

后端：

```
.venv/bin/python -B -m pytest \
  tests/free_sources/test_news_public.py tests/test_news_service.py tests/test_news_api.py \
  -q -p no:cacheprovider
→ 30 passed in 0.42s
```

前端：

```
pnpm exec vitest run --no-cache \
  src/pages/__tests__/News.test.tsx \
  src/lib/__tests__/navGroups.test.ts \
  src/components/__tests__/Layout.mobile.test.tsx
→ 3 files, 32 passed in 2.05s
```

Layout.mobile 仍有既有 stderr：`["data-sources"]` 无 queryFn。不是本轮失败。

未重跑 frontend build（controller / `9de57887` 已跑）。未跑无关全仓。pycache 与受保护报告测试后未变。

---

## 10. P1 / P2

### P1 拒收项

**无。** 原 P1（`/202609/1194319` 被拼成 `2026-09-11` 并当最新）在当前代码与隔离缓存/GET 上已消除。

### P2（不拒收；精确修法，本会话不改代码）

**P2-1 长编号 URL 与真实列表日撞车时被 reconcile 清空**

- 证据：`html_extract.py` L202–224；本机 `reconcile_cached_policy_date(pbc_url, "2026-09-09") == ""`；隔离 GET 央行 14 条中 13 条 date 空。
- 最小复现：`python -B` 对  
  `http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/2026090909080511735/index.html`  
  存盘日期 `2026-09-09` 调用 `reconcile_cached_policy_date`。
- 修法：只把「`/YYYYMM/` + 文章编号前两位」这种 **跨斜杠拼接** 当 splice；不要把「更长连续数字串的前 8 位恰好等于存盘日」清掉。更好是给条目加 `date_source`（list/url/pubdate），只 scrub url 拼接。GET 仍不写盘。

**P2-2 共享缓存 POST 对普通登录用户开放**

- `authorization.py` L56：`/api/news` 整前缀可写。重点部门隔离正确；market/policy JSON 是共享的。
- 修法（若产品要收紧）：拆前缀——`/api/news/policy/key-departments` 个人写；`/refresh` 仅 admin 或单独授权。

**P2-3 无读改写锁**

- `refresh_policy` / `refresh_market_source` 读-合并-`atomic_write_json`，无 `Lock`。
- 修法：模块级 lock 包住 refresh 临界区。原子替换保留。

**P2-4 文档仍把政策页权威写成 HEAD `e96f5d`；工作台日志仍写 23 passed / 495**

- `workbench-development-log.md` 约 L93、L108、L113；`用户台GitHub项目借鉴记录.md` 约 L248。
- 修法：与 `feature-matrix.md` 对齐 dirty hash；续修后测试 30、缓存 525。

**P2-5 相对 go-stock 缺 TLS1.2 兜底**

- 不造样本；失败已可见。若要逼近上游成功率，只对目录内 host 加 TLS1.2/有限重试，仍走 allowlist。

---

## 11. 审查覆盖 / 未验证

**已覆盖：** AGENTS 分层与交接材料；go-stock 脏树/HEAD hash；18 文件备份 diff；authorization 一行；日期无网络复现与邻条；隔离缓存扫描；3048/3041 只读 API 与 GET 不写 `items.json`；allowlist/HTML/链接；用户隔离代码+测试；三份后端测试 + 三份前端测试；保护冲突 6 路径；正式 `data/news` 未写。

**未验证 / 不做：**

- Codex 内置浏览器页面点击（本 Cursor 会话无该浏览器；禁止系统 Chrome / 临时 Playwright）。**不以主审 UI 观察冒充本会话 UI 证据。**
- 远端全量/单源 POST 抓取。
- 正式 3011/3018 资讯页。
- 整包 candidate fingerprint 重算。
- 供应商模型返回证据。
- 用户验收、accepted、production、部署。
- `9de57887` 的 seal 只作交接，不替代本复查。

---

## 12. 结论

技术 **PASS**。日期拼接 P1 已在当前候选与隔离运行面上独立确认修复；保护冲突仅为 pycache/交接报告；18 文件增量没有越界改 go-stock 或其他业务模块。剩余是 P2（央行类长编号日期误清、共享刷新权限、无写锁、文档 HEAD/计数过时、TLS 兜底）。状态最多保持 `implemented` / 数据台 `isolated`（目录 `source-verified`）。
