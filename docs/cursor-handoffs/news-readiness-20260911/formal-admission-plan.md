# 正式资讯缓存接入方案（待授权）

本文件只是方案。**本轮禁止**实际批写、调度改点、production promotion、部署。

## 正式已有 5 个 JSON（as_of 2026-09-11 只读）

| 文件 | 条数 | sha256 |
| --- | --- | --- |
| `data/news/market/cls.json` | 20 | `2640933d509513955b3e95fdc6640310580e9dd107ad9da957409e7718fdec0e` |
| `data/news/market/sina.json` | 20 | `05f739ac296eaf9bbc4c3732fceec8a235e53f0b946ef31b935d95099ff6b4de` |
| `data/news/market/foreign.json` | 20 | `ebd5ce0b75673c06bfb350d00a19d7ca09529c6d099ad21eff4c9c2b330da632` |
| `data/news/policy/departments.json` | 82 | `baedbec137718c65815e2d13d7bd3a7c3e3b0e093cc5ad940a46937b20ed20fd` |
| `data/news/policy/items.json` | 56 | `de17d4826c89b72c3990470b3c52316819dba82cb990638a54d737eb9e5bfd1a` |

旧隔离另有一套（政策 526，`bf6a424d87e7437eb3786e0657feba4857ff0c28ea2eafa4ba24078e4a8aa84c`）。**不得**与正式集合并/覆盖/scrub。

as_of 2026-09-09 收口曾写「正式仅 `.gitkeep`」。那是当时事实。当前不要回填成旧叙事。

## 新抓取范围上限（授权后才执行）

1. 先备份上表 5 个文件的 hash 与副本，写回滚清单。
2. 市场三源分批：先 `cls`，再 `sina`，再 `foreign`。每源一次 POST，失败保旧，不并行打正式盘。
3. 部门目录：仅当需要更新 82 名录时 POST `/policy/departments/refresh`。成功才进入条目刷新。
4. 政策条目：默认单部门或重点部门，每部门 `limit=30`。全部门浅抓必须单独授权，且不得宣称“全部部门已更新”，除非 `last_refresh.scope=all` 且失败列表可解释。
5. 不补全历史、不做 PDF/OCR、不接国务院政策库搜索、不定时调度。
6. 单次正式写入上限建议：市场每源 ≤50 条展示窗口；政策单次新增 ≤100；全库累计上限另议。

## Source 分批

- 批次 A：财联社电报（`www.cls.cn`）
- 批次 B：新浪财经直播（`zhibo.sina.com.cn`）
- 批次 C：TradingView 聚合（`news-mediator.tradingview.com`），供稿媒体因条目而异
- 批次 D：`www.gov.cn` 部门名录
- 批次 E：已核验部委站点，按重点部门再按失败重试名单

仓库 / go-stock 不是权利方或生产者。

## 授权门

- 用户单独授权该批次 POST。
- 登录会话有效；共享刷新仍是现有语义：已登录用户可触发共享缓存刷新，不能绕过认证。
- 重点部门写入保持账号隔离。
- 不改 `authorization.py` 全局规则。
- 失败文案不得带 secret/token/本机路径。

## 备份 hash / 回滚

- 写前复制 5 个正式 JSON 到带时间戳备份目录，记录 size/mtime/sha256。
- 回滚只覆回本批次改动的文件。
- 不要用旧隔离 526 条覆盖正式 56 条。
- 不要用本任务 2026-09-11 源码备份去覆盖他人后续修改。

## 失败保旧

- 单源失败：保留该源上次 items，不改 `last_success_at`。
- 单部门失败：保留其他部门与上次条目；`scope=department`。
- 部分部门失败：可见中文，保留成功部门。
- 空成功、从未抓取、筛选无匹配必须分开。
- GET 永远不写。

## 数据权利 / 新鲜度验收

- 验收只看真实生产者与聚合平台，不看 GitHub 仓库名。
- 新鲜度：最近成功抓取、最后尝试、缓存更新、原文日期四条独立；缺字段写未知。
- 过期阈值当前实现为 24 小时，可在授权后调整，但不能用 mtime 冒充抓取时间。
- 用户验收前最高 `isolated` / 用户台 `implemented`。`accepted` / `production` 必须另开运行面与用户确认。

## 本轮结论

方案待授权。本任务没有批写、没有调度、没有 promotion。
