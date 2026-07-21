"""盘后管道 + 盘前维表同步。

调度:
  09:10 盘前 — 同步个股维表 instruments (全量覆盖)
  15:30 盘后 — 日K同步 + 增量除权因子 + enriched 计算 + 刷新视图

盘后同步策略:
  日 K: QuoteService 交易时段已实时落盘 → 有数据时跳过 batch,首次拉 1 年区间
  除权因子: 从已有数据最新日期的下一天开始增量获取,避免重复拉取和计算
  财务(public): financial_provider=public 时按 public_data_scope 刷新四表+股本截面
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import polars as pl
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.indicators.pipeline import run_pipeline
from app.services import index_sync, instrument_sync, kline_sync
from app.services import preferences as _prefs
from app.services.daily_quality import run_daily_quality_check
from app.tickflow.capabilities import Cap, CapabilitySet
from app.tickflow.pools import DEMO_SYMBOLS, get_pool
from app.tickflow.repository import KlineRepository

logger = logging.getLogger(__name__)

ProgressCb = Callable[..., None]


def _noop(stage: str, pct: int, msg: str, **kwargs) -> None:
    pass


def _invalidate(table: str | None = None) -> None:
    """stage 写完调用,让 /api/data/status 只重算被影响的那张表。"""
    from app.api.data import invalidate_data_cache
    invalidate_data_cache(table)


def _resolve_universe(capset: CapabilitySet) -> list[str]:
    """解析标的池。

    优先使用 preferences.pipeline_universe_scope：
      ALL / CSI300 / CSI500 / SSE50 / WATCHLIST
    - ALL + 有 batch → TickFlow CN_Equity_A（若可用）
    - ALL + free → instruments + watchlist + demo
    - CSI* → data/pools 缓存（缺则 public 刷新）
    """
    from app.services.universe_scope import (
        SCOPE_ALL,
        SCOPE_LABELS,
        normalize_scope,
        resolve_symbols,
    )

    scope = normalize_scope(_prefs.get_pipeline_universe_scope(), default=SCOPE_ALL)
    logger.info("resolve_universe scope=%s (%s)", scope, SCOPE_LABELS.get(scope, scope))

    # Paid batch + ALL: prefer live CN_Equity_A universe when available
    if scope == SCOPE_ALL and capset.has(Cap.KLINE_DAILY_BATCH):
        try:
            all_a = get_pool("CN_Equity_A", refresh=True)
            if all_a:
                return sorted({str(s).strip().upper() for s in all_a if s})
        except Exception as e:
            logger.warning("CN_Equity_A pool unavailable, fallback instruments: %s", e)

    syms = resolve_symbols(
        scope,
        data_dir=Path(settings.data_dir),
        default=SCOPE_ALL,
        include_watchlist=(scope == SCOPE_ALL),
        refresh_pools_if_missing=True,
    )
    if syms:
        return syms

    # Last-resort free fallback
    base: set[str] = set(DEMO_SYMBOLS)
    try:
        base.update(get_pool("watchlist") or [])
    except Exception:
        pass
    return sorted(base)


def run_instruments_sync(repo: KlineRepository) -> dict:
    """盘前同步个股维表。"""
    rows = instrument_sync.sync_instruments(repo.store.data_dir)
    _refresh_instruments_view(repo)
    _invalidate("instruments")
    return {"instruments_rows": rows}


def run_now(
    repo: KlineRepository,
    capset: CapabilitySet,
    on_progress: ProgressCb | None = None,
) -> dict:
    """立即执行一次盘后管道,支持进度回调。

    跳过的 stage **不 emit**,避免前端把"无 capability"的卡片错误标记为 active/done。
    result 里带 skipped_stages 列表供前端展示。
    """
    emit = on_progress or _noop
    skipped: list[str] = []

    # Step 0: 先同步个股维表, 再解析标的池 — 确保标的池基于最新 instruments
    emit("sync_instruments", 2, "同步个股维表…")
    inst_rows = instrument_sync.sync_instruments(repo.store.data_dir)
    if inst_rows > 0:
        _refresh_instruments_view(repo)
    emit("sync_instruments", 8, f"个股维表同步完成,{inst_rows} 只标的")
    _invalidate("instruments")

    emit("resolve_universe", 9, "解析标的池…")
    universe = _resolve_universe(capset)
    try:
        from app.services.universe_scope import SCOPE_LABELS, normalize_scope
        _sc = normalize_scope(_prefs.get_pipeline_universe_scope(), default="ALL")
        _lab = SCOPE_LABELS.get(_sc, _sc)
    except Exception:
        _sc, _lab = "ALL", "全A"
    emit("resolve_universe", 10, f"标的池[{_lab}] 规模:{len(universe)} 只")

    # Step 1: 日 K 同步
    #   付费档 + 今天有数据 → 实时行情接口拉一次覆写（1请求全市场）
    #   有历史数据 → batch K-line API 补齐缺口
    #   无任何数据 → batch K-line API 拉首次 1 年
    from datetime import date as _date
    from datetime import datetime as _dt
    from datetime import timedelta as _td
    latest_daily = repo.latest_daily_date()
    today = _date.today()
    today_exists = latest_daily and latest_daily >= today
    new_daily_days = 0
    # 日K范围拉取的起点(分支3补缺口/分支4首次); 实时增量/跳过时为 None。
    # 供 Step 1.5 除权因子回溯范围对齐: 范围拉取→用日K范围, 非范围→最近N天兜底。
    daily_range_start: _date | None = None

    # A 股日K拉取开关(默认开);关闭时跳过日K同步,保留已有数据
    pull_a_share = _prefs.get_pipeline_pull_a_share()
    daily_source = None
    public_eod_result = None
    latest_before = latest_daily

    def _daily_partition_dates() -> list[_date]:
        daily_dir = repo.store.data_dir / "kline_daily"
        if not daily_dir.exists():
            return []
        out: list[_date] = []
        for p in daily_dir.glob("date=*"):
            if not p.is_dir():
                continue
            try:
                out.append(_date.fromisoformat(p.name[5:]))
            except ValueError:
                continue
        return sorted(out)

    def _count_new_daily_days(before: _date | None) -> int:
        """按真实 date= 分区统计新增交易日数,避免 (today-start).days 误报。"""
        dates = _daily_partition_dates()
        if not dates:
            return 0
        if before is None:
            return len(dates)
        return sum(1 for d in dates if d > before)

    # batch 结束时间用当天末尾,避免 end=today 00:00 把当日 bar 排除在外
    batch_end = _dt.combine(today, _dt.max.time().replace(microsecond=0))

    if not pull_a_share:
        emit("sync_daily", 45, "已跳过 A 股日K同步(拉取内容未勾选)")
        logger.info("sync_daily: skipped (pipeline_pull_a_share=False)")
    elif today_exists and capset.has(Cap.QUOTE_POOL):
        # 付费档:今天有数据(QuoteService 已落盘)→ 实时行情覆写,确保最新。
        # free/none 档无 quote.pool 能力,即便今天已有数据(如从 expert 降级),
        # 也降级到下方 batch 路径刷新,避免调用无权限的实时行情接口。
        emit("sync_daily", 12, f"获取日K [{today} ~ {today}] 实时行情…")
        written_daily = kline_sync.sync_daily_by_quotes(repo)
        daily_source = "tickflow_quotes"
        new_daily_days = 1 if written_daily else 0
        emit("sync_daily", 45, f"日K 完成,{written_daily} 只标的")
        logger.info("sync_daily: [%s ~ %s] live quotes, %d symbols", today, today, written_daily)
    elif latest_daily:
        # 有历史 → batch 补齐缺口。
        # 也覆盖"今天已有数据但无实时行情权限(free/none)"的降级场景:
        #   此时 start_date = latest_daily = today,batch 刷新当天日K。
        start_date = latest_daily
        daily_range_start = start_date
        emit("sync_daily", 12, f"获取日K [{start_date} ~ {today}]…")
        logger.info("sync_daily: [%s ~ %s] %s", start_date, today,
                    "refresh today" if today_exists else "gap fill")

        def _daily_chunk_progress(cur: int, tot: int) -> None:
            emit("sync_daily", 12 + int(33 * cur / tot),
                 f"日K 批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)
        written_daily = kline_sync.sync_and_persist_daily_batch(
            universe, repo, capset,
            start_date=_dt.combine(start_date, _dt.min.time()),
            end_date=batch_end,
            on_chunk_done=_daily_chunk_progress,
        )
        daily_source = "tickflow_batch"
        new_daily_days = _count_new_daily_days(latest_before)
        emit("sync_daily", 42, f"日K batch 完成,新增 {new_daily_days} 个交易日分区")
        logger.info(
            "sync_daily: [%s ~ %s] done, rows=%s new_days=%s",
            start_date, today, written_daily, new_daily_days,
        )
    else:
        # 首次：无任何数据 → batch 拉 1 年
        start_date = today - _td(days=365)
        daily_range_start = start_date
        emit("sync_daily", 12, f"获取日K [{start_date} ~ {today}]…")
        logger.info("sync_daily: [%s ~ %s] initial fetch", start_date, today)

        def _daily_chunk_progress(cur: int, tot: int) -> None:
            emit("sync_daily", 12 + int(33 * cur / tot),
                 f"日K 批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)
        written_daily = kline_sync.sync_and_persist_daily_batch(
            universe, repo, capset,
            start_date=_dt.combine(start_date, _dt.min.time()),
            end_date=batch_end,
            on_chunk_done=_daily_chunk_progress,
        )
        daily_source = "tickflow_batch"
        new_daily_days = _count_new_daily_days(latest_before)
        emit("sync_daily", 42, f"日K batch 完成,新增 {new_daily_days} 个交易日分区")
        logger.info(
            "sync_daily: [%s ~ %s] done, rows=%s new_days=%s",
            start_date, today, written_daily, new_daily_days,
        )

    # None/Free 兜底: free 历史日K若尚未提供 today, 用公开行情合成当日日K。
    # 仅在工作日尝试; 周末/已有 today / 用户关闭 A 股日K 时跳过。
    latest_after_batch = repo.latest_daily_date()
    today_missing = (latest_after_batch is None) or (latest_after_batch < today)
    want_public_eod = (
        pull_a_share
        and today_missing
        and today.weekday() < 5
        and not capset.has(Cap.QUOTE_POOL)
    )
    if want_public_eod:
        try:
            rt_provider = _prefs.get_realtime_data_provider()
        except Exception:
            rt_provider = "public"
        if rt_provider == "public":
            emit("sync_daily", 43, f"free 日K未含今日,改用公开行情合成 {today}…")
            logger.info(
                "sync_daily: public eod fallback for %s (latest_after_batch=%s)",
                today, latest_after_batch,
            )
            public_eod_result = kline_sync.sync_daily_by_public_quotes(universe, repo, trade_date=today)
            pub_rows = int((public_eod_result or {}).get("rows") or 0)
            if pub_rows > 0:
                daily_source = "public_quote_eod"
                # 以兜底前最新日为 baseline 重算新增天数
                new_daily_days = _count_new_daily_days(latest_before)
                emit("sync_daily", 45, f"公开行情合成完成,{pub_rows} 只 · {today}")
                logger.info("sync_daily: public eod wrote %d rows for %s", pub_rows, today)
            else:
                emit("sync_daily", 45, f"公开行情合成未写入今日分区(latest={latest_after_batch})")
                logger.warning(
                    "sync_daily: public eod fallback produced 0 rows (latest_after_batch=%s)",
                    latest_after_batch,
                )
        else:
            emit("sync_daily", 45, f"今日日K仍缺(latest={latest_after_batch}); realtime provider={rt_provider},跳过 public 合成")
            logger.info(
                "sync_daily: skip public eod (provider=%s, latest=%s)",
                rt_provider, latest_after_batch,
            )
    elif pull_a_share:
        # 统一收尾文案
        latest_now = latest_after_batch or repo.latest_daily_date()
        emit("sync_daily", 45, f"日K 完成,最新 {latest_now},新增 {new_daily_days} 日")

    _invalidate("daily")

    # Step 1.5: 同步除权因子 — 范围与日K拉取方式对齐
    #   日K范围拉取(补缺口/首次) → 除权用日K范围 [daily_range_start, now]
    #     首次会覆盖整个日K区间内的历史除权事件; 补缺口天然只增量(起点=latest_daily≈昨天)
    #   日K实时增量/跳过(分支2/分支1) → 除权兜底拉最近 30 天, 补可能遗漏的新除权
    #     (这两类分支不拉历史日K, 除权不能用日K范围, 只能兜底最近几日)
    written_adj = 0
    affected_symbols: list[str] = []
    from app.services import preferences as _pref_adj
    _public_adj = False
    try:
        _public_adj = _pref_adj.is_public_adj_factor_provider()
    except Exception:
        _public_adj = False
    if capset.has(Cap.ADJ_FACTOR) or _public_adj:
        from datetime import datetime, timedelta
        adj_end = datetime.now()
        if daily_range_start is not None:
            adj_start = datetime.combine(daily_range_start, datetime.min.time())
        else:
            # 日K实时增量/跳过时, 除权兜底拉最近 N 天, 覆盖周末/长假/停机期间的新除权事件。
            # 15 天: 覆盖春节/国庆最长约10天长假 + 故障恢复缓冲; sync_adj_factor 内部 merge+unique 幂等, 多拉无副作用。
            adj_start = adj_end - timedelta(days=15)
        adj_start_str = adj_start.strftime("%Y-%m-%d")
        adj_end_str = adj_end.strftime("%Y-%m-%d")
        emit("sync_adj", 50, f"获取除权因子 [{adj_start_str} ~ {adj_end_str}]…")
        logger.info("sync_adj: [%s ~ %s] start", adj_start_str, adj_end_str)

        def _adj_chunk_progress(cur: int, tot: int) -> None:
            emit("sync_adj", 50 + int(10 * cur / tot),
                 f"除权因子批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)
        adj_universe = list(universe)
        try:
            if _prefs.is_public_adj_factor_provider():
                from app.services.universe_scope import resolve_symbols
                # public adj 默认跟 public_data_scope（CSI300），避免 ALL 时盘后被拖死
                pub_scope = _prefs.get_public_data_scope()
                adj_universe = resolve_symbols(
                    pub_scope,
                    data_dir=Path(settings.data_dir),
                    default="CSI300",
                    refresh_pools_if_missing=True,
                ) or adj_universe
                emit("sync_adj", 50, f"获取除权因子(public/{pub_scope}) {len(adj_universe)} 只…")
        except Exception as e:
            logger.warning("public adj universe resolve failed: %s", e)
        written_adj, affected_symbols = kline_sync.sync_adj_factor(
            adj_universe, repo, capset,
            start_time=adj_start, end_time=adj_end,
            on_chunk_done=_adj_chunk_progress,
        )
        if affected_symbols:
            _refresh_single_view(repo, "adj_factor")
            emit("sync_adj", 60, f"除权因子完成,新增 {len(affected_symbols)} 只个股")
            logger.info("sync_adj: [%s ~ %s] done, %d symbols", adj_start_str, adj_end_str, len(affected_symbols))
        else:
            emit("sync_adj", 60, "除权因子完成,无新增")
            logger.info("sync_adj: [%s ~ %s] no new factors", adj_start_str, adj_end_str)
        _invalidate("adj_factor")
    else:
        skipped.append("sync_adj")
        logger.info("sync_adj skipped: no ADJ_FACTOR capability and adj_factor_provider is not public")

    # Step 1.5: public 财务刷新（不阻断日K/复权主路径）
    financial_result: dict | None = None
    try:
        if _prefs.is_public_financial_provider():
            from app.data_providers.registry import get_provider
            from app.services.free_sources.financials_public import FINANCIAL_TABLES
            from app.services.universe_scope import resolve_symbols

            pub_scope = _prefs.get_public_data_scope()
            fin_syms = resolve_symbols(
                pub_scope,
                data_dir=repo.store.data_dir,
                default="CSI300",
                refresh_pools_if_missing=True,
            )
            mp = _prefs.get_financial_max_periods()

            # Light vs full: statement body is expensive (EM ~5 periods/call).
            # Full deepen only when local depth is below target; otherwise metrics+shares.
            median_periods = 0.0
            try:
                inc_path = repo.store.data_dir / "financials" / "income" / "part.parquet"
                if inc_path.exists():
                    idf = pl.read_parquet(inc_path)
                    if not idf.is_empty() and "symbol" in idf.columns:
                        g = idf.group_by("symbol").len()
                        # restrict to current scope when possible
                        g = g.filter(pl.col("symbol").is_in(fin_syms)) if fin_syms else g
                        if g.height:
                            median_periods = float(g["len"].median())
            except Exception as e:
                logger.debug("financial depth probe failed: %s", e)

            full = median_periods < max(4.0, float(mp) * 0.8)
            tables = FINANCIAL_TABLES if full else ("metrics", "shares")
            mode = "full" if full else "light"
            # Light daily refresh: skip symbols that already have enough fresh metrics.
            # Full deepen: resume by local depth so interrupted runs do not restart from 0.
            fin_min_periods = max(4, int(float(mp) * 0.8)) if full else max(4, min(int(mp), 8))
            fin_fresh_days = None if full else -1  # calendar: within last ~2 quarter-ends
            fin_workers = 2 if full else 4
            emit(
                "sync_financials",
                62,
                f"刷新财务(public/{pub_scope}/{mode}) {len(fin_syms)} 只 · {mp}期…",
            )
            logger.info(
                "sync_financials public scope=%s n=%d max_periods=%d mode=%s median_periods=%s "
                "min_periods=%s fresh_days=%s workers=%s",
                pub_scope, len(fin_syms), mp, mode, median_periods,
                fin_min_periods, fin_fresh_days, fin_workers,
            )

            def _fin_progress(cur: int, tot: int, sym: str = "") -> None:
                # Keep overall progress in the 62→64 band; stage bar shows real coverage.
                tot = max(int(tot or 0), 1)
                cur = max(0, min(int(cur or 0), tot))
                pct = 62 + int(2 * cur / tot)
                label = f"{cur}/{tot}"
                if sym:
                    label = f"{label} · {sym}"
                emit(
                    "sync_financials",
                    pct,
                    f"财务批次 {label}",
                    stage_pct=int(100 * cur / tot),
                    skip_log=True,
                )

            public_provider = get_provider("public")
            financial_result = public_provider.sync_financials(
                fin_syms,
                repo.store.data_dir,
                tables=tables,
                max_periods=mp,
                pause_s=0.0,
                on_progress=_fin_progress,
                resume=True,
                min_periods=fin_min_periods,
                prefer_fresh_days=fin_fresh_days,
                workers=fin_workers,
                flush_every=15 if full else 25,
                skip_checked_within_hours=18.0,
            )
            # shares always refreshed even if tables omitted somehow
            try:
                public_provider.sync_shares_snapshot(repo.store.data_dir, symbols=fin_syms)
            except Exception as e:
                logger.debug("shares snapshot in pipeline skipped: %s", e)
            # touch financial_scheduler last_sync markers when available
            try:
                from app.services.financial_sync import financial_scheduler, _refresh_financials_views
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc).isoformat()
                for table in ("metrics", "income", "balance_sheet", "cash_flow", "shares"):
                    financial_scheduler._last_sync[table] = now  # noqa: SLF001
                _refresh_financials_views(repo.store.data_dir)
            except Exception as e:
                logger.debug("financial last_sync/view refresh skipped: %s", e)
            ok_n = int((financial_result or {}).get("symbols_ok_n") or 0)
            fail_n = int((financial_result or {}).get("symbols_fail_n") or 0)
            skip_n = int((financial_result or {}).get("symbols_skipped_n") or 0)
            todo_n = int((financial_result or {}).get("symbols_todo_n") or 0)
            emit(
                "sync_financials",
                64,
                f"财务完成 ok={ok_n} fail={fail_n} skip={skip_n} todo={todo_n}",
            )
            _invalidate("financials")
            logger.info("sync_financials done ok=%s fail=%s rows=%s", ok_n, fail_n, (financial_result or {}).get("rows"))
        else:
            skipped.append("sync_financials")
            logger.info("sync_financials skipped: financial_provider is not public")
    except Exception as e:
        logger.warning("sync_financials failed (non-fatal): %s", e)
        skipped.append("sync_financials")
        emit("sync_financials", 64, f"财务刷新失败(已跳过): {e}")

    # Step 2: 计算 enriched
    #   判断策略:
    #     - 首次 (enriched 目录不存在) → 全量
    #     - 往前扩展历史 (新日期 < enriched 已有最早日期) → 全量
    #       前面的除权因子会改变累积因子链,影响后面所有日期的复权价格
    #     - 往后新增日期 (新日期 > enriched 已有最晚日期)
    #       → 增量补新区块(所有标的) + 受除权影响个股全日期重算
    #     - 无新日期 + 有新除权因子 → 增量: 只重算受影响个股的全部日期
    #     - 无新日期 + 无变化 → 跳过
    enriched_dir = repo.store.data_dir / "kline_daily_enriched"
    enriched_exists = enriched_dir.exists() and any(enriched_dir.glob("date=*"))
    daily_dir = repo.store.data_dir / "kline_daily"
    daily_days = len(list(daily_dir.glob("date=*"))) if daily_dir.exists() else 0
    prev_enriched_days = len(list(enriched_dir.glob("date=*"))) if enriched_exists else 0

    # 判断新日期方向: 找 daily 和 enriched 的日期集合做比较
    forward_incremental = False
    backward_extension = False

    if daily_days > prev_enriched_days and enriched_exists:
        daily_dates = sorted(d.stem.split("=")[1] for d in daily_dir.glob("date=*"))
        enriched_dates = sorted(d.stem.split("=")[1] for d in enriched_dir.glob("date=*"))
        earliest_enriched = enriched_dates[0]
        latest_enriched = enriched_dates[-1]
        new_dates = set(daily_dates) - set(enriched_dates)
        if new_dates:
            # 有新日期早于 enriched 最早日期 → 往前扩展
            if any(d < earliest_enriched for d in new_dates):
                backward_extension = True
            # 有新日期晚于 enriched 最晚日期 → 往后新增
            if any(d > latest_enriched for d in new_dates):
                forward_incremental = True

    def _enriched_batch_progress(cur: int, tot: int) -> None:
        emit("compute_enriched", 65 + int(23 * cur / tot),
             f"计算指标 批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)

    if not enriched_exists or backward_extension:
        # 首次 或 往前扩展 → 全量
        emit("compute_enriched", 65, "全量计算 enriched…")
        logger.info("compute_enriched: full rebuild (first=%s, backward=%s, daily=%d, enriched=%d)",
                    not enriched_exists, backward_extension, daily_days, prev_enriched_days)
        written_enriched = run_pipeline(on_batch_done=_enriched_batch_progress)
        new_enriched_days = len(list(enriched_dir.glob("date=*")))
        emit("compute_enriched", 88, f"enriched 完成,覆盖 {new_enriched_days} 天")
        logger.info("compute_enriched: full rebuild done, %d days", new_enriched_days)
    elif forward_incremental:
        # 往后新增日期: 增量补新区块 + 受影响个股全日期重算
        symbols_to_recompute = list(set(affected_symbols)) if affected_symbols else []
        emit("compute_enriched", 65,
             f"增量计算 enriched (新日期 + {len(symbols_to_recompute)} 只个股重算)…"
             if symbols_to_recompute else "增量计算 enriched (新日期)…")
        logger.info("compute_enriched: forward incremental, %d symbols to recompute",
                    len(symbols_to_recompute))
        written_enriched = run_pipeline(
            new_dates_only=True,
            symbols=symbols_to_recompute or None,
            on_batch_done=_enriched_batch_progress,
        )
        new_enriched_days = len(list(enriched_dir.glob("date=*")))
        emit("compute_enriched", 88, f"enriched 完成,覆盖 {new_enriched_days} 天")
        logger.info("compute_enriched: forward incremental done, %d days", new_enriched_days)
    elif affected_symbols:
        # 无新日期,仅除权因子变更 → 只重算受影响个股的全部日期
        emit("compute_enriched", 65, f"增量计算 enriched ({len(affected_symbols)} 只个股)…")
        logger.info("compute_enriched: adj_factor incremental, %d symbols", len(affected_symbols))
        written_enriched = run_pipeline(symbols=affected_symbols, on_batch_done=_enriched_batch_progress)
        emit("compute_enriched", 88, f"enriched 完成,{len(affected_symbols)} 只个股")
    else:
        written_enriched = 0
        logger.info("compute_enriched: skip (no new daily, no adj_factor changes)")
    _refresh_single_view(repo, "kline_enriched")
    _invalidate("enriched")

    # Step 2.3: 指数 / ETF 同步 — 物理分开存储；ETF 可复权，指数不复权。
    written_index_daily = 0
    written_etf_daily = 0
    index_count = 0
    etf_count = 0
    etf_adj_symbols = 0
    pull_index = _prefs.get_pipeline_pull_index()
    pull_etf = _prefs.get_pipeline_pull_etf()

    if capset.has(Cap.KLINE_DAILY_BATCH) and (pull_index or pull_etf):
        _types = []
        if pull_index:
            _types.append("指数")
        if pull_etf:
            _types.append("ETF")
        emit("sync_index", 88, f"同步{'+'.join(_types)}日K…")
        # 子阶段进度分配: 88.0(开始) → 89.0(完成), 指数占前半, ETF 占后半
        try:
            if pull_index:
                emit("sync_index", 88, "同步指数维表…")
                index_count = index_sync.sync_index_instruments(repo, pull_index=True, pull_etf=False)
                emit("sync_index", 88, f"指数维表完成,{index_count} 只")
                index_dir = repo.store.data_dir / "kline_index_enriched"
                index_dates = sorted(
                    d.name[5:] for d in index_dir.glob("date=*")
                    if d.is_dir() and d.name.startswith("date=")
                ) if index_dir.exists() else []
                index_start = _date.fromisoformat(index_dates[-1]) if index_dates else today - _td(days=365)

                def _index_chunk(cur: int, tot: int) -> None:
                    emit("sync_index", 88, f"指数日K批次 {cur}/{tot}",
                         stage_pct=int(100 * cur / tot) if tot else 100, skip_log=cur < tot)

                written_index_daily = index_sync.sync_and_persist_index_daily(
                    repo,
                    capset,
                    start_date=_dt.combine(index_start, _dt.min.time()),
                    end_date=_dt.combine(today, _dt.min.time()),
                    on_chunk_done=_index_chunk,
                )
                emit("sync_index", 88, f"指数日K完成,{written_index_daily} 行")
                _invalidate("index_instruments")
                _invalidate("index_daily")
                _invalidate("index_enriched")

            if pull_etf:
                emit("sync_index", 88, "同步 ETF 维表…")
                etf_count = index_sync.sync_etf_instruments(repo)
                emit("sync_index", 88, f"ETF 维表完成,{etf_count} 只")
                etf_symbols: list[str] = []
                etf_inst = repo.get_etf_instruments()
                if not etf_inst.is_empty() and "symbol" in etf_inst.columns:
                    etf_symbols = sorted(set(etf_inst["symbol"].to_list()))
                if etf_symbols and capset.has(Cap.ADJ_FACTOR):
                    try:
                        emit("sync_index", 88, "同步 ETF 除权因子…")
                        from datetime import datetime, timedelta
                        adj_end = datetime.now()
                        adj_path = repo.store.data_dir / "adj_factor_etf" / "all.parquet"
                        fallback_start = adj_end - timedelta(days=30)
                        adj_start = fallback_start
                        if adj_path.exists():
                            max_date = pl.scan_parquet(adj_path).select(pl.col("trade_date").max()).collect().item()
                            if max_date is not None:
                                if isinstance(max_date, str):
                                    adj_start = datetime.combine(_date.fromisoformat(max_date), datetime.min.time())
                                elif isinstance(max_date, datetime):
                                    adj_start = datetime.combine(max_date.date(), datetime.min.time())
                                else:
                                    adj_start = datetime.combine(max_date, datetime.min.time())
                        _, affected_etfs = index_sync.sync_etf_adj_factor(
                            etf_symbols,
                            repo,
                            capset,
                            start_time=adj_start,
                            end_time=adj_end,
                        )
                        etf_adj_symbols = len(affected_etfs)
                        emit("sync_index", 88, f"ETF 除权因子完成,{etf_adj_symbols} 只")
                    except Exception as e:
                        logger.warning("ETF adj_factor skipped: %s", e)
                etf_dir = repo.store.data_dir / "kline_etf_enriched"
                etf_dates = sorted(
                    d.name[5:] for d in etf_dir.glob("date=*")
                    if d.is_dir() and d.name.startswith("date=")
                ) if etf_dir.exists() else []
                etf_start = _date.fromisoformat(etf_dates[-1]) if etf_dates else today - _td(days=365)

                def _etf_chunk(cur: int, tot: int) -> None:
                    emit("sync_index", 88, f"ETF 日K批次 {cur}/{tot}",
                         stage_pct=int(100 * cur / tot) if tot else 100, skip_log=cur < tot)

                written_etf_daily = index_sync.sync_and_persist_etf_daily(
                    repo,
                    capset,
                    start_date=_dt.combine(etf_start, _dt.min.time()),
                    end_date=_dt.combine(today, _dt.min.time()),
                    on_chunk_done=_etf_chunk,
                )
                emit("sync_index", 88, f"ETF 日K完成,{written_etf_daily} 行")
                _invalidate("etf_instruments")
                _invalidate("etf_daily")

            repo.refresh_index_views()
            emit(
                "sync_index",
                89,
                f"同步完成,指数 {index_count} 只/{written_index_daily} 行, ETF {etf_count} 只/{written_etf_daily} 行"
                + (f", ETF复权 {etf_adj_symbols} 只" if etf_adj_symbols else ""),
            )
        except Exception as e:
            logger.warning("sync_index/etf failed: %s", e)
            emit("sync_index", 89, f"指数/ETF同步失败:{e}")
    else:
        skipped.append("sync_index")

    # Step 2.5: 分钟 K 同步(可选) — 无能力/用户关闭时明确记录原因（可观测，不造假数据）
    from app.services import preferences
    from app.tickflow.capabilities import minute_availability

    minute_on = preferences.get_minute_sync_enabled()
    minute_days = preferences.get_minute_sync_days()
    written_minute = 0
    minute_info = minute_availability(capset, user_enabled=minute_on)
    minute_sync_result: dict = {
        "status": minute_info["status"],
        "reason": minute_info.get("reason"),
        "reason_code": minute_info.get("reason_code"),
        "user_enabled": minute_on,
        "days_requested": minute_days,
        "rows": 0,
        "full_market_sync_allowed": minute_info.get("full_market_sync_allowed"),
        "fallback_hint": minute_info.get("fallback_hint"),
    }

    if minute_on and capset.has(Cap.KLINE_MINUTE_BATCH):
        minute_start = today - _td(days=minute_days)
        emit("sync_minute", 90, f"获取分钟K [{minute_start} ~ {today}]…")
        logger.info("sync_minute: [%s ~ %s] start", minute_start, today)
        minute_symbols = _resolve_minute_symbols(capset)
        def _minute_chunk_progress(cur: int, tot: int) -> None:
            emit("sync_minute", 90 + int(3 * cur / tot),
                 f"分钟K 批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)
        written_minute = kline_sync.sync_and_persist_minute(
            minute_symbols, repo, capset, days=minute_days,
            on_chunk_done=_minute_chunk_progress,
        )
        minute_dir = repo.store.data_dir / "kline_minute"
        minute_cover_days = len(list(minute_dir.glob("date=*"))) if minute_dir.exists() else 0
        emit("sync_minute", 93, f"分钟K完成,覆盖 {minute_cover_days} 天")
        logger.info("sync_minute: [%s ~ %s] done, %d days", minute_start, today, minute_cover_days)
        _invalidate("minute")
        minute_sync_result.update({
            "status": "synced",
            "reason": None,
            "reason_code": "ok",
            "rows": written_minute,
            "cover_days": minute_cover_days,
        })
    else:
        skipped.append("sync_minute")
        # Do not create fake kline_minute success state; only log + structured result.
        if not minute_info.get("available"):
            msg = minute_info.get("reason") or "无分钟K权限"
            emit("sync_minute", 90, f"分钟K不可用: {msg}")
            logger.info("sync_minute skipped: %s", minute_info.get("reason_code"))
        elif not minute_on:
            emit("sync_minute", 90, "分钟K已关闭（用户未启用自动同步）")
            logger.info("sync_minute skipped: user disabled")
            minute_sync_result["status"] = "disabled_by_user"
            minute_sync_result["reason_code"] = "user_disabled"
            minute_sync_result["reason"] = "用户关闭了分钟自动同步"
        else:
            # has by_symbol only, no batch — refuse full-market sync
            emit("sync_minute", 90, "分钟K仅有按标的能力，全市场同步未启用")
            logger.info("sync_minute skipped: no batch capability")
            minute_sync_result["status"] = "unavailable"
            minute_sync_result["reason_code"] = "no_batch_capability"
            minute_sync_result["reason"] = "仅有 kline.minute.by_symbol，无 batch，跳过全市场同步"

    # Step 3: 刷新视图
    emit("refresh_views", 95, "刷新 DuckDB 视图…")
    _refresh_views(repo)

    # Quality gate is terminal-state authoritative: completed processing with
    # failed quality is degraded, never silently succeeded.
    quality_report = None
    try:
        emit("quality", 97, "运行日线质量门禁…")
        quality_report = run_daily_quality_check(repo.store.data_dir)
        emit(
            "quality",
            98,
            f"质量门禁 ok={quality_report.get('ok')} issues={len(quality_report.get('issues') or [])}",
        )
    except Exception as e:
        logger.warning("quality gate failed: %s", e)
        quality_report = {
            "ok": False,
            "issues": [{"code": "quality_gate_exception", "message": str(e)}],
        }
        emit("quality", 99, f"质量门禁失败: {e}")

    quality_ok = bool(quality_report and quality_report.get("ok") is True)
    emit("done", 100, "完成" if quality_ok else "完成，但质量门禁未通过")
    _invalidate(None)  # 兜底:全清

    return {
        "universe_size": len(universe),
        "daily_days": new_daily_days,
        "daily_source": daily_source,
        "public_eod": public_eod_result,
        "adj_factor_symbols": len(affected_symbols),
        "financials": {
            "ok": int((financial_result or {}).get("symbols_ok_n") or 0),
            "fail": int((financial_result or {}).get("symbols_fail_n") or 0),
            "rows": (financial_result or {}).get("rows"),
            "scope": (financial_result or {}).get("scope") or (
                _prefs.get_public_data_scope() if _prefs.is_public_financial_provider() else None
            ),
        } if financial_result is not None else None,
        "enriched_days": written_enriched,
        "index_count": index_count,
        "index_daily_rows": written_index_daily,
        "etf_count": etf_count,
        "etf_daily_rows": written_etf_daily,
        "etf_adj_factor_symbols": etf_adj_symbols,
        "minute_rows": written_minute,
        "minute_sync": minute_sync_result,
        "skipped_stages": skipped,
        "quality": quality_report,
    }


def _refresh_views(repo: KlineRepository) -> None:
    """刷新所有 DuckDB 视图。"""
    d = repo.store.data_dir.as_posix()
    views = {
        "kline_daily": f"{d}/kline_daily/**/*.parquet",
        "kline_enriched": f"{d}/kline_daily_enriched/**/*.parquet",
        "kline_index_daily": f"{d}/kline_index_daily/**/*.parquet",
        "kline_index_enriched": f"{d}/kline_index_enriched/**/*.parquet",
        "kline_etf_daily": f"{d}/kline_etf_daily/**/*.parquet",
        "kline_etf_enriched": f"{d}/kline_etf_enriched/**/*.parquet",
        "kline_etf_minute": f"{d}/kline_etf_minute/**/*.parquet",
        "kline_minute": f"{d}/kline_minute/**/*.parquet",
        "adj_factor": f"{d}/adj_factor/**/*.parquet",
        "adj_factor_etf": f"{d}/adj_factor_etf/**/*.parquet",
        "instruments": f"{d}/instruments/**/*.parquet",
        "instruments_index": f"{d}/instruments_index/**/*.parquet",
        "instruments_etf": f"{d}/instruments_etf/**/*.parquet",
    }
    for name, path in views.items():
        try:
            repo.db.execute(
                f"CREATE OR REPLACE VIEW {name} AS "
                f"SELECT * FROM read_parquet('{path}', union_by_name=true)"
            )
        except Exception as e:
            logger.warning("refresh view %s failed: %s", name, e)
    repo.store._register_unified_views()


def _refresh_single_view(repo: KlineRepository, name: str) -> None:
    """刷新单个 DuckDB 视图。"""
    d = repo.store.data_dir.as_posix()
    paths = {
        "kline_daily": f"{d}/kline_daily/**/*.parquet",
        "kline_enriched": f"{d}/kline_daily_enriched/**/*.parquet",
        "kline_index_daily": f"{d}/kline_index_daily/**/*.parquet",
        "kline_index_enriched": f"{d}/kline_index_enriched/**/*.parquet",
        "kline_etf_daily": f"{d}/kline_etf_daily/**/*.parquet",
        "kline_etf_enriched": f"{d}/kline_etf_enriched/**/*.parquet",
        "kline_etf_minute": f"{d}/kline_etf_minute/**/*.parquet",
        "kline_minute": f"{d}/kline_minute/**/*.parquet",
        "adj_factor": f"{d}/adj_factor/**/*.parquet",
        "adj_factor_etf": f"{d}/adj_factor_etf/**/*.parquet",
        "instruments": f"{d}/instruments/**/*.parquet",
        "instruments_index": f"{d}/instruments_index/**/*.parquet",
        "instruments_etf": f"{d}/instruments_etf/**/*.parquet",
    }
    path = paths.get(name)
    if not path:
        return
    try:
        repo.db.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_parquet('{path}', union_by_name=true)"
        )
    except Exception as e:
        logger.warning("refresh view %s failed: %s", name, e)


def _resolve_minute_symbols(capset: CapabilitySet) -> list[str]:
    """分钟 K 同步标的 — 与日K共用同一标的池。"""
    return _resolve_universe(capset)


def _refresh_instruments_view(repo: KlineRepository) -> None:
    """单独刷新 instruments 视图。"""
    d = repo.store.data_dir.as_posix()
    try:
        repo.db.execute(
            f"CREATE OR REPLACE VIEW instruments AS "
            f"SELECT * FROM read_parquet('{d}/instruments/**/*.parquet', union_by_name=true)"
        )
    except Exception as e:
        logger.warning("refresh instruments view failed: %s", e)


def _run_tracked(fn, job_label: str) -> None:
    """调度触发时包装 JobStore 跟踪，确保同步历史有记录。"""
    from app.services.pipeline_jobs import job_store

    job_id = job_store.create()
    job_store.start(job_id)

    def progress(stage: str, pct: int, msg: str, stage_pct: int | None = None,
                 skip_log: bool = False) -> None:
        job_store.progress(job_id, stage, pct, msg, stage_pct=stage_pct, skip_log=skip_log)

    try:
        result = fn(on_progress=progress)
        job_store.complete(job_id, result)
        logger.info("scheduled %s completed: job_id=%s", job_label, job_id)
    except Exception:
        logger.exception("scheduled %s failed: job_id=%s", job_label, job_id)
        job_store.fail(job_id, f"scheduled {job_label} failed")


# ================================================================
# 定时复盘 (AI 大盘复盘报告)
# ================================================================

REVIEW_JOB_ID = "scheduled_review"


async def _run_scheduled_review(repo) -> None:
    """定时复盘 job: 流式生成复盘 → 实时推 SSE(开着页面可见) → 落盘归档 → 推飞书。

    与手动「生成复盘」体验一致: 流式事件经 quote_service.push_review_event →
    /api/intraday/stream 的 review_progress 事件 → 前端 reviewStore, 用户开着复盘页
    即可看到报告边生成边显示, 切走再回来也能看到生成中/已生成。
    LLM 偶发断流(peer closed connection)时自动重试最多 2 次。
    任何异常都吞掉只记日志, 绝不影响调度器主循环。
    """
    import json

    try:
        from app import secrets_store as ss
        from app.services import market_recap_reports

        # AI Key 未配置时跳过(避免每日报错刷日志)
        if not ss.get_ai_key():
            logger.info("scheduled review skipped: AI key not configured")
            return

        app_state = _get_app_state()
        quote_service = getattr(app_state, "quote_service", None) if app_state else None
        depth_service = getattr(app_state, "depth_service", None) if app_state else None

        content, meta = await _stream_review_with_retry(repo, quote_service, depth_service)
        if not content:
            logger.warning("scheduled review produced no content (meta=%s)", meta)
            # 通知前端进入 error 态(若有页面在听)
            if quote_service:
                quote_service.push_review_event(json.dumps(
                    {"type": "error", "message": "复盘生成失败,请稍后手动重试"},
                    ensure_ascii=False))
            return

        # 落盘: 与手动生成完全相同的归档格式
        market_recap_reports.save_report({
            "as_of": meta.get("as_of"),
            "focus": "",
            "content": content,
            "summary": meta.get("summary", ""),
            "emotion_score": meta.get("emotion_score"),
            "emotion_label": meta.get("emotion_label", ""),
        })
        logger.info("scheduled review saved: as_of=%s", meta.get("as_of"))

        # 通知前端: 生成完成且已归档(archived=true 让前端只刷新列表, 不重复归档)
        if quote_service:
            quote_service.push_review_event(json.dumps(
                {"type": "done", "archived": True}, ensure_ascii=False))

        # 推送到飞书(可选): 运行时读取配置, 用户改设置下次触发即生效。
        # 失败静默降级, 不影响已归档的报告。
        _maybe_push_review(content, meta)
    except Exception as e:
        logger.exception("scheduled review failed: %s", e)
        # 兜底: 异常时通知前端停止「生成中」状态, 避免页面卡在 streaming
        try:
            app_state = _get_app_state()
            qs = getattr(app_state, "quote_service", None) if app_state else None
            if qs:
                import json as _json
                qs.push_review_event(_json.dumps(
                    {"type": "error", "message": "复盘生成异常,请稍后手动重试"},
                    ensure_ascii=False))
        except Exception:
            pass


async def _stream_review_with_retry(repo, quote_service, depth_service) -> tuple[str, dict]:
    """流式生成复盘, 每个事件推 SSE + 累积内容。LLM 断流时最多重试 2 次。

    返回 (content, meta)。重试时推一个 retry 事件让前端清空已累积内容重新开始。
    成功(收到 done/无 error)或耗尽重试后返回。
    """
    import asyncio
    import json

    from app.services.market_recap import recap_market_stream

    max_attempts = 3  # 初次 + 2 次重试
    last_meta: dict = {}
    content_parts: list[str] = []

    for attempt in range(1, max_attempts + 1):
        content_parts = []  # 每次重试重新累积
        failed = False
        try:
            async for evt_json in recap_market_stream(repo, quote_service, depth_service):
                evt = json.loads(evt_json)
                t = evt.get("type")

                # 推给前端(让开着页面的用户实时看到, 与手动一致)
                if quote_service:
                    quote_service.push_review_event(evt_json)

                if t == "meta":
                    last_meta = evt
                elif t == "delta" and evt.get("content"):
                    content_parts.append(evt["content"])
                elif t == "error":
                    failed = True
                    logger.warning("scheduled review stream error (attempt %d/%d): %s",
                                   attempt, max_attempts, evt.get("message"))
                    break  # 触发重试
                elif t == "done":
                    # 正常完成
                    return "".join(content_parts), last_meta
            # 流自然结束(无 done 事件)且有内容, 视为成功
            if content_parts and not failed:
                return "".join(content_parts), last_meta
        except Exception as e:
            # LLM 断流等异常(httpx.RemoteProtocolError)落到这里
            failed = True
            logger.warning("scheduled review stream exception (attempt %d/%d): %s",
                           attempt, max_attempts, e)

        # 失败: 决定是否重试
        if attempt < max_attempts:
            logger.info("scheduled review retrying in 3s (attempt %d → %d)", attempt, attempt + 1)
            # 通知前端: 即将重试, 清空已累积内容重新开始
            if quote_service:
                quote_service.push_review_event(json.dumps(
                    {"type": "retry", "attempt": attempt + 1}, ensure_ascii=False))
            await asyncio.sleep(3)

    # 耗尽重试, 返回已累积内容(可能为空)和最后 meta
    return "".join(content_parts), last_meta


def _maybe_push_review(content: str, meta: dict) -> None:
    """复盘报告归档后, 按 review_push_channels 选定的外部工具逐个推送完整报告。

    定时生成与手动生成共用本函数 (手动归档端点 POST /api/market-recap/reports 也会调用)。
    channels 为空则不推送; 'feishu' 复用监控中心的全局飞书 Webhook 通道。
    推送失败静默降级 (Webhook 是辅助通道), 不影响已归档的报告。
    """
    try:
        from app.services import preferences, webhook_adapter

        channels = preferences.get_review_push_channels()
        if not channels:
            return

        emotion = f"{meta.get('emotion_label') or ''}".strip()
        as_of = meta.get("as_of") or ""
        subtitle = as_of + (f" · 情绪 {emotion}" if emotion else "")

        for ch in channels:
            if ch == "feishu":
                url = preferences.get_feishu_webhook_url()
                if not url:
                    logger.info("review push(feishu) skipped: webhook not configured")
                    continue
                secret = preferences.get_feishu_webhook_secret()
                ok = webhook_adapter.send_feishu_card(
                    url, "TickFlow · 每日复盘", subtitle, content, secret
                )
                logger.info("review push(feishu) %s", "sent" if ok else "failed")
            # 未来更多渠道在此追加分支
    except Exception as e:
        logger.warning("review push error: %s", e)


def _register_review_job(scheduler, repo, hour: int, minute: int) -> None:
    """注册/更新定时复盘 job(工作日 mon-fri, Asia/Shanghai)。

    供 start_scheduler(启动时) 和 settings API(改时间时) 共用。
    用 replace_existing=True, 重复注册只更新 trigger。

    注意: _run_scheduled_review 是协程函数, 必须把函数对象本身(配合 args)传给
    add_job, 而非用 lambda 包裹 —— 否则 APScheduler 会把 lambda 当同步函数在线程池
    执行, 仅得到一个未 await 的协程对象, 复盘实际不会运行。
    """
    scheduler.add_job(
        _run_scheduled_review,
        args=[repo],
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=hour, minute=minute,
                            timezone="Asia/Shanghai"),
        id=REVIEW_JOB_ID,
        misfire_grace_time=7200,  # 复盘非关键, 允许 2 小时内补跑
        replace_existing=True,
    )


def start_scheduler(repo: KlineRepository, capset: CapabilitySet) -> AsyncIOScheduler:
    """启动调度器。

    工作日 09:10 — 同步个股维表
    工作日 HH:MM — 盘后管道（时间由用户偏好决定，默认 15:30）
    """
    from app.services import preferences
    sched = preferences.get_pipeline_schedule()
    inst_sched = preferences.get_instruments_schedule()

    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

    # 盘前: 同步 instruments（时间由偏好决定）
    def _instruments_task(on_progress=None):
        emit = on_progress or _noop
        emit("sync_instruments", 0, "同步个股维表…")
        result = run_instruments_sync(repo)
        emit("done", 100, f"个股维表同步完成,{result.get('instruments_rows', 0)} 只标的")
        return result

    scheduler.add_job(
        lambda: _run_tracked(_instruments_task, "instruments_sync"),
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=inst_sched["hour"], minute=inst_sched["minute"],
                            timezone="Asia/Shanghai"),
        id="pre_market_instruments",
        misfire_grace_time=1800,
        replace_existing=True,
    )

    # 盘后: 日 K + enriched（时间由偏好决定）
    def _pipeline_then_refresh(on_progress=None):
        # 与手动触发 (/api/pipeline/run) 对齐: 管道落盘后重建 Polars 内存缓存,
        # 否则 live_agg 的昨日连板数等基准列会停留在旧交易日, 次日开盘连板梯队
        # 整体少算一档 (仅手动触发或重启才会刷缓存, cron 调度路径此前漏了这步)。
        result = run_now(repo, capset, on_progress=on_progress)
        repo.refresh_cache()
        return result

    scheduler.add_job(
        lambda: _run_tracked(_pipeline_then_refresh, "daily_pipeline"),
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=sched["hour"], minute=sched["minute"],
                            timezone="Asia/Shanghai"),
        id="daily_pipeline",
        misfire_grace_time=3600,
        replace_existing=True,
    )

    # 盘后: 五档盘口 sealed 定版(时间由偏好决定, 默认15:02, 范围15:01~18:00)
    depth_sched = preferences.get_depth_finalize_time()

    def _depth_finalize():
        depth_svc = getattr(_get_app_state(), "depth_service", None) if _get_app_state() else None
        if depth_svc:
            depth_svc.finalize()

    scheduler.add_job(
        _depth_finalize,
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=depth_sched["hour"], minute=depth_sched["minute"],
                            timezone="Asia/Shanghai"),
        id="depth_finalize",
        misfire_grace_time=3600,
        replace_existing=True,
    )

    # 定时复盘 (AI 大盘复盘报告): 工作日到点自动生成并归档。
    # 默认关闭 —— 仅当用户在复盘页开启时才注册 job。
    # 复用 recap_market_once(非流式) + market_recap_reports.save_report(落盘)。
    # quote_service / depth_service 通过 _get_app_state() 延迟取用。
    review_sched = preferences.get_review_schedule()
    if review_sched["enabled"]:
        _register_review_job(scheduler, repo, review_sched["hour"], review_sched["minute"])
        logger.info("scheduled_review enabled @%02d:%02d mon-fri",
                    review_sched["hour"], review_sched["minute"])

    scheduler.start()
    logger.info("scheduler started; instruments@%02d:%02d, pipeline@%02d:%02d, depth@%02d:%02d mon-fri",
                inst_sched["hour"], inst_sched["minute"], sched["hour"], sched["minute"],
                depth_sched["hour"], depth_sched["minute"])
    return scheduler


# app_state 延迟引用(start_scheduler 在 lifespan 早期调用, app.state 可能还没就绪)
_app_state_ref = None


def set_app_state(app_state) -> None:
    """lifespan 注册 app.state 引用, 供 scheduled job 访问 depth_service 等单例。"""
    global _app_state_ref
    _app_state_ref = app_state


def _get_app_state():
    return _app_state_ref
