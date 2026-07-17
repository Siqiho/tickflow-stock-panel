# Free Ext Data P0/P1 落地状态

> 日期：2026-07-17  
> 分支：`feature/free-ext-data-p0p1`  
> Worktree：`/Users/simon/Trading/one-trading/.worktrees/free-ext-data-p0p1`  
> 计划：`docs/superpowers/plans/2026-07-17-free-ext-data-p0p1.md`

## 已完成

| 能力 | 落点 | 验证 |
|---|---|---|
| HTTP 韧性（timeout/cooldown/dedupe/partial） | `backend/app/services/free_sources/http_resilience.py` | unit tests PASS |
| 近似筹码分布 | `chip_distribution.py` + `GET /api/free/chips/{symbol}` | unit + 真实 `000001.SZ` 60 日计算 PASS |
| 日线质量门禁 | `daily_quality.py` + pipeline `quality` 阶段 + `/api/free/quality/*` | unit + 最新分区 `2026-07-07` report PASS |
| 个股/板块/概念资金流 | `fund_flow.py` + `/api/free/fund-flow/*` | unit normalize/persist PASS；live HTTP 视网络 |
| Watchlist 免费实时 fallback | `quote_service._fetch_watchlist_quotes` + `quote_fallback.py` | unit parse PASS；无 TickFlow key 时走腾讯/新浪 |
| 单票分时 on-demand | `intraday_public.py` + `/api/free/intraday/{symbol}` | 代码落地；live 视网络 |
| 盘口异动 / F10 摘要 | `stock_changes.py` / `f10_snapshot.py` + API | 代码落地；on-demand |
| 同花顺概念行业手动刷新 | `POST /api/free/ths/refresh` → `fetch_preset` | 代码落地；不自动开 pull.enabled |

## 测试

```bash
cd backend && uv run pytest tests/free_sources -v
# 13 passed
```

## 真实数据烟测

- `run_daily_quality_check(data)`：`ok=True`，`date=2026-07-07`，`rows=5417`，volume 单位启发式 ≈ 100（手）
- `chips_for_symbol(..., 000001.SZ, days=60)`：`avg_cost≈10.37`，`profit_ratio≈0.94`，约 0.4s

## 边界

- 不启用 TickFlow 付费分钟/财务/深度
- 不接 Tushare / easy_tdx 生产主源
- 筹码为近似算法，API 含 disclaimer
- 公开源失败应 502/降级，不污染核心 `kline_*`

## 合并建议

在 worktree 审阅通过后：

```bash
cd /Users/simon/Trading/one-trading
git merge feature/free-ext-data-p0p1
# 或 cherry-pick / PR
```

注意：main 工作区本身有大量无关 dirty 改动，建议只合并本分支提交。
