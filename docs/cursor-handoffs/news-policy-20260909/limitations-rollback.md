# 已知限制与回滚

## 已知限制

- 用户台 `news_policy_workbench`：`verified`。数据台 `news_market_flash` / `news_policy_items`：保持 `isolated`（隔离实测有 canary 级证据）。**不是** `accepted` / `production`。自动测试 ≠ 用户验收。非正式 `data/news`。禁止写成全 82 源或全部历史完整采集。
- 主审已在 Codex IAB 做完当前 `678x863` `/news` 验收；最终 reload 后 console error 0。宽屏只有源码/`lg:` 复核，本轮无宽屏截图。Nested scroll（`Layout` main + 根 grid + aside + 列表）实际可用，仍是多层 overflow。
- 独立 UI `e18ac0cf` 无浏览器、无截图；jsdom 只锁 class。几何以主审 IAB 为准。
- 政策页关键词是已入库本地搜索，不是国务院政策文件库远端搜索。`gov_policy_lib_api.go` 未接入。
- 上游无真正可见分页。本地「加载更多」只翻缓存。
- 情绪是规则词表，不是 go-stock gse 分词；标签仍为看涨/看跌/中性。
- P2-2 保留：已登录普通用户可 POST 刷新共享快讯/政策缓存。不改 `authorization.py`。
- P2-5 保留：无 TLS1.2 兜底。其他站点失败可见并保留缓存。
- 并发锁是**单进程** `threading.RLock` / 每源 Lock，覆盖 refresh/scrub 与单路 market 替换。确定性线程测试已跑。不宣称跨进程锁。
- 日期证据边界：`date_source=list|pubdate` 且合法、不晚于明天则保留；`url` 只保留有边界 URL 日；旧缓存无 `date_source` 时，只清 `/YYYYMM/` 或 `/YYYY/MM/` + 更长文章编号拼接，不清长连续数字 ID 与真列表日碰撞。空日期保持空，不从长 ID 前 8 位或已清空历史猜日。
- 真实取数失败（未造样本）：国家统计局 SSL handshake timeout；全部门浅抓 7 个部门失败（公安部 521、司法部 too many redirects、海关 412、国新办 521、消防 405、药监 412、卫健委 502）。P2 央行列表页成功，未再刷 82 部门。
- `7d39a518` `failed/read_only_candidate_changed` 与 `c89fcd1c` `failed/protected_input_changed` 保持失败，不得改成 completed。`1eab309c` 超时不是通过。
- 模型请求/配置 Grok 4.6 Extra High；供应商实际返回证据 **未核验**。
- 隔离 `DATA_DIR` 非正式生产数据。正式 `one-trading/data/news` 仍仅 `.gitkeep`。正式 3011/3018 未为本功能手工重启。
- 源码在主项目工作树。运行隔离 ≠ git 工作树隔离。正式 `--reload` / Vite 可能拾取同一源码，不能写「正式环境完全不受影响」。

## 回滚

不要用旧备份整份覆盖公共文件。其他任务已对数据层有合法改动。只回本任务 hunks；若他人已在其后继续修改同一文件，不得覆盖那些后续改动。本轮 closeout 新文件移入废纸篓，不要 `rm -rf` 正式 `one-trading/data`。

1. 本轮文档收口：把 `/Users/simon/备份/codex/news-policy-closeout-20260909-183503/files/` 里六份授权文档拷回原绝对路径；`closeout/` 新文件移入废纸篓。
2. 窄屏 UI class：`/Users/simon/备份/codex/news-policy-ui-fix-20260909-182318/files/` 对应 `PolicyPanel.tsx` / `News.test.tsx` / 当时文档。
3. 本轮 P2：把 `/Users/simon/备份/codex/news-policy-p2-fix-20260909-174907/files/` 里对应源码/测试/隔离 `items.json`/授权文档拷回原绝对路径。
4. 只要撤日期 provenance 续修：用 `news-policy-date-provenance-20260909-162024`，不要从 `154419` 回写 `authorization.py` 或其他公共文件。
5. 隔离进程以 `runtime.json` 当前 PID 为准（3048=`97934`，3041=`97951`）。旧值 94803/94831/53690/54763/29024/23510 已过时。**不要**停 3011/3018（3510/3528）。持续 stdout 在隔离 `DATA_DIR/logs/`，不要写回 p2-fix。
