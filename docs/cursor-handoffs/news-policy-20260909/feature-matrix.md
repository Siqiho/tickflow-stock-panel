# 上游功能 → 本地实现 → 验证

功能权威：本地 go-stock 分支 `codex/upstream-dev-20260831-integration` HEAD `e96f5d7262fae35698b4bebd4b8650f8bfdf0e71`（该 commit 是合流基线，**不是** 2026-09 政策页引入点）。当前 dirty 工作树文件 hash 才是政策/三栏功能权威：

- `PolicyNewsList.vue` sha256 `4dc45ed4adcadb4e38b7b91e704236f190843a4748ffc524a6e163a9888e0bab`
- `policy_news_api.go` sha256 `b500037e04a4f032013e809b40ac6002727f11c588cb64b3f1dd052804d0295b`
- `gov_policy_lib_api.go` sha256 `dac2ef990e490aad0fdfd2f9f94b463ba057df38951325bb1fb469e204c8b10d`
- `market_news_api.go` sha256 `985534cc20cb1bf9a5864c674d81314f0eb61706b1c9ea9c3bbaf40589f4125f`
- `newsList.vue` sha256 `44e689226407492b77ebf0f68cec4b28ce3f2deec92ca05c058e41ada9363c36`
- `market.vue` sha256 `772ba7e1df0fe465683a0f312caa492c913788ed456b547594d0cb7a965b2310`

许可证仍为上游 GPL-3.0；数据权利仍属各官网 / 财联社 / 新浪 / TradingView，仓库不是权利方。`gov_policy_lib_api.go` 只服务 AI 工具，不是本政策页入口。

| 上游 | 本地 one-trading | 验证 |
| --- | --- | --- |
| 侧栏资讯入口（本轮要求：数据后新增） | `navGroups` `/news`「资讯」；`Layout` Newspaper；设置排序/隐藏走既有 `builtinMenuCatalog`；管理员钉尾 `/admin/users`→`/data`→`/news`；量化/交易分组保留 | 当前 vitest **33 passed**（News 6 含窄屏 class 契约 + navGroups 8 + Layout.mobile 19；as_of P2-fix 曾为 32）。主审 IAB：侧栏「资讯」在「数据」后。宽屏只有源码 `lg:` 复核，本轮无宽屏截图 |
| 市场快讯三栏：财联社/新浪/外媒 | `/news` 默认页签；`NewsColumn` 独立刷新、时间、标题/正文、题材、原文、重要(is_red)、规则情绪、展开、新标记；单源失败横幅「本源失败，仍显示上次数据」 | 真实 POST：三源各 20 条成功。失败不覆盖：pytest。GET `/api/news/market` 读缓存各 20。主审 IAB：三栏真实缓存与原文；CLS 首条可展开；单源刷新只动该栏 |
| 政策页完整部门目录 | `POST /api/news/policy/departments/refresh` 抓 `www.gov.cn` 部门列表页；GET 只读 | 真实解析 **82** 个部门，`source-verified` |
| 全部部门按日期倒序 | 本地 store 按 date desc；GET 默认 page_size=100 | 隔离 GET `total=526`（P2 央行刷新后；此前复核 525），`has_more=true` |
| 部门筛选/搜索选择 | 左侧全部部门 + 搜索框；换部门保留关键词 | vitest「keeps the stored-search keyword」。主审 IAB：能源局「新能源」4 条；切央行保留关键词得 0；「国际清算」1 条后清空恢复 15 |
| 默认/自定义重点部门增删保存恢复 | `GET/POST /api/news/policy/key-departments`；空列表恢复默认；`user_path` 账号隔离 | pytest 隔离 alice/bob；磁盘已有 `key_departments.json` 时 `is_default=false`。主审 IAB：加外交部后刷新仍第 13 项，随后删回 12 |
| 官网 / 日期 / 来源 / 标题 / 原文 | `PolicyPanel` 行内字段；只渲染 http(s)。内部 `date_source=list\|url\|pubdate` 贯通缓存/GET | 央行长编号条列表日 `2026-09-09`；民委 `1194319=2026-09-09`；月份目录+编号仍不能拼日。主审 IAB 678x863：改后结果区高 381.8046875px（改前 h:2）；可滚到 2026-08-14 同标题央行/外汇局。Nested scroll 实际可用 |
| 已入库历史关键词搜索 / 退出搜索 | `GetStoredPolicyNews` 语义：`GET /api/news/policy?keyword=`，不联网 | 真实「新能源」4 条，`from_cache=true`；vitest 搜索不调用 POST |
| 刷新：全部=`GetAllDeptPolicyNews` 浅抓；单部门=`GetPolicyNews` limit 30 | `POST /api/news/policy/refresh`；空部门=全目录浅抓；指定部门=深抓 30 | 全部门 fetched=302、added=247、7 部门失败仍保留其他。重点部门 11/12 成功；统计局 SSL timeout 如实记录 |
| 上游无真正可见分页，仅 100/200 限额 | GET 本地分页/加载更多；不宣称上游已分页 | pytest 130 条入库、首页 100、`has_more` |
| `gov_policy_lib_api.go` / `sousuo.www.gov.cn` | **不接入政策页** | 无对应 API/UI |
| GET 零外连 / POST 才抓 | service GET 只读 JSON；刷新显式 POST | pytest monkeypatch boom；隔离 GET 读到上次 POST 缓存 |
| SSRF：只允许静态已核验源 + 官方部门目录 | `allowlist.py`；拒绝非 http(s)/private/回环；重定向再校验 | pytest `test_ssrf_rejects_private_and_non_http` |
| 不执行源 HTML/JS | stdlib HTMLParser；新浪只剥 JSONP 再 `json.loads` | pytest JSONP |
| 不依赖 go-stock HTTP/SQLite/GPL Runtime | 原生 Python + 本地 JSON + lineage | 代码审阅 |
