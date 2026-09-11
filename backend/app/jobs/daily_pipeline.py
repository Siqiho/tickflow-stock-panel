"""盘后管道 + 盘前维表同步。

调度:
  09:10 盘前 — 同步个股维表 instruments (全量覆盖)
  15:35 盘后 — 日K同步 + 增量除权因子 + enriched 计算 + 刷新视图
  (默认 15:35: 盘后固定价 15:30 终止 + 供应商日线定稿缓冲, 见 preferences)

盘后同步策略:
  日 K: QuoteService 交易时段已实时落盘 → 有数据时跳过 batch,首次拉 1 年区间
  除权因子: 从已有数据最新日期的下一天开始增量获取,避免重复拉取和计算
  财务(public): financial_provider=public 时按 public_data_scope 刷新四表+股本截面
"""
from __future__ import annotations

import logging
import shutil
import threading
from collections.abc import Callable
from datetime import date as Date
from pathlib import Path

import polars as pl
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.indicators.pipeline import fill_enriched_coverage_gap, run_pipeline
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


_INDUSTRY_ROLL_CANCEL = threading.Event()
_CONCEPT_ROLL_CANCEL = threading.Event()


def request_industry_roll_cancel() -> None:
    """Cooperative stop for H5 rolls attached to this process."""
    _INDUSTRY_ROLL_CANCEL.set()
    _CONCEPT_ROLL_CANCEL.set()


def request_concept_roll_cancel() -> None:
    """Cooperative stop for the concept H5 roll attached to this process."""
    _CONCEPT_ROLL_CANCEL.set()


def _run_industry_fund_flow_daily_roll(
    data_dir: Path,
    *,
    cancel_event: threading.Event | None = None,
    time_limit_s: float | None = None,
    on_progress: ProgressCb | None = None,
) -> dict:
    """Attach industry H5 daily continuation. Never raise into the daily-K path."""
    try:
        from app.services.free_sources.fund_flow import roll_industry_daily_from_h5

        return roll_industry_daily_from_h5(
            data_dir,
            cancel_event=cancel_event,
            time_limit_s=time_limit_s,
            on_progress=on_progress,
        )
    except Exception as e:
        logger.warning("industry fund-flow daily roll failed: %s", e)
        return {
            "ok": False,
            "kind": "board",
            "status": "error",
            "error": str(e),
            "note": "行业日线续更失败，不影响已成功日K",
        }


def _run_concept_fund_flow_daily_roll(
    data_dir: Path,
    *,
    cancel_event: threading.Event | None = None,
    time_limit_s: float | None = None,
    on_progress: ProgressCb | None = None,
) -> dict:
    """Attach concept H5 daily continuation. Never raise into the daily-K path."""
    try:
        from app.services.free_sources.fund_flow import roll_concept_daily_from_h5

        return roll_concept_daily_from_h5(
            data_dir,
            cancel_event=cancel_event,
            time_limit_s=time_limit_s,
            on_progress=on_progress,
        )
    except Exception as e:
        logger.warning("concept fund-flow daily roll failed: %s", e)
        return {
            "ok": False,
            "kind": "concept",
            "status": "error",
            "error": str(e),
            "note": "概念日线续更失败，不影响已成功日K",
        }


def _invalidate(table: str | None = None) -> None:
    """stage 写完调用,让 /api/data/status 只重算被影响的那张表。"""
    from app.api.data import invalidate_data_cache
    invalidate_data_cache(table)


def _partition_row_count(part_dir: Path) -> int | None:
    files = [p for p in part_dir.glob("*.parquet") if p.is_file()]
    if not files:
        return None
    try:
        return int(pl.scan_parquet(files).select(pl.len()).collect().item())
    except Exception:  # noqa: BLE001
        return None


def should_use_public_eod_fallback(
    *,
    pull_a_share: bool,
    today_missing: bool,
    weekday: int,
    has_quote_pool: bool,
    daily_is_custom: bool = False,
) -> bool:
    """Synthesize today's official daily bars from public quotes when needed.

    Daily completeness is independent of ``realtime_data_provider``. The old
    ``realtime == public`` gate skipped this path whenever leftover TickFlow
    routing was stored — none/free installs then finished the pipeline with
    no today partition even though Tencent/Sina could fill it.
    Paid ``quote.pool`` already overwrites today, so it stays excluded.
    A declared custom daily source must not be topped up from public quotes.
    """
    return bool(
        pull_a_share
        and today_missing
        and weekday < 5
        and not has_quote_pool
        and not daily_is_custom
    )


def resolve_adj_sync_universe(
    pipeline_universe: list[str],
    capset: CapabilitySet,
) -> list[str] | None:
    """Symbols for adj sync, or None to skip (public-adapter fail-closed).

    TickFlow / declared custom adj keep the pipeline universe. The public sina
    adapter must stay inside ``public_data_scope``; empty or failed resolve
    does not widen back to ALL / CN_Equity_A.
    """
    if not adj_sync_uses_public_adapter(capset):
        return list(pipeline_universe)
    from app.services.universe_scope import resolve_symbols

    pub_scope = _prefs.get_public_data_scope()
    scoped = resolve_symbols(
        pub_scope,
        data_dir=Path(settings.data_dir),
        default="CSI300",
        refresh_pools_if_missing=True,
    )
    if not scoped:
        logger.warning(
            "public adj universe empty for scope=%s, fail-closed (no pipeline-universe widen)",
            pub_scope,
        )
        return None
    return scoped


def adj_sync_uses_public_adapter(capset: CapabilitySet) -> bool:
    """Whether adj sync will write via the public sina adapter.

    Explicit public/sina* prefs use it. Leftover TickFlow no longer
    silent-mixes sina when Cap.ADJ_FACTOR is missing.
    Declared custom / undeclared custom / unresolved must not be scoped
    as a public adapter.
    """
    try:
        if _prefs.is_public_adj_factor_provider():
            return True
        name = _prefs.get_adj_factor_provider()
        _, fate = kline_sync._try_custom_adj_provider(name)
        if fate in {"custom", "skip"}:
            return False
    except Exception:  # noqa: BLE001
        # Prefs unreadable: do not shrink universe to public_data_scope.
        return False
    return False


def _prune_partial_enriched_partitions(daily_dir: Path, enriched_dir: Path) -> list[str]:
    """Delete watchlist-only enriched dates so the next increment rebuilds the full day."""
    pruned: list[str] = []
    if not enriched_dir.exists():
        return pruned
    for part in sorted(p for p in enriched_dir.glob("date=*") if p.is_dir()):
        day = part.name.removeprefix("date=")
        daily_part = daily_dir / f"date={day}"
        if not daily_part.exists():
            continue
        daily_n = _partition_row_count(daily_part)
        enriched_n = _partition_row_count(part)
        if daily_n is None or enriched_n is None:
            continue
        if enriched_n < daily_n:
            shutil.rmtree(part)
            pruned.append(day)
    return pruned


def _prune_stale_price_partitions(daily_dir: Path, enriched_dir: Path) -> list[str]:
    """Delete enriched dates whose raw_close diverges from official daily close."""
    pruned: list[str] = []
    if not enriched_dir.exists():
        return pruned
    from app.services.kline_sync import daily_partition_usable, filter_daily_cache

    for part in sorted(p for p in enriched_dir.glob("date=*") if p.is_dir()):
        day = part.name.removeprefix("date=")
        daily_part = daily_dir / f"date={day}"
        if not daily_part.exists():
            continue
        daily_file = daily_part / "part.parquet"
        enriched_file = part / "part.parquet"
        if daily_file.exists() and not daily_partition_usable(daily_file):
            continue
        if enriched_file.exists() and not daily_partition_usable(enriched_file):
            continue
        try:
            daily = filter_daily_cache(pl.read_parquet(list(daily_part.glob("*.parquet"))))
            enriched = filter_daily_cache(pl.read_parquet(list(part.glob("*.parquet"))))
        except Exception:  # noqa: BLE001
            continue
        if "raw_close" not in enriched.columns or "symbol" not in enriched.columns:
            continue
        if "close" not in daily.columns or "symbol" not in daily.columns:
            continue
        joined = daily.select(["symbol", "close"]).join(
            enriched.select(["symbol", "raw_close"]),
            on="symbol",
            how="inner",
        )
        if joined.is_empty():
            continue
        stale = joined.filter((pl.col("close") - pl.col("raw_close")).abs() > 1e-6)
        if stale.height > 0:
            shutil.rmtree(part)
            pruned.append(day)
    return pruned


def resolve_universe(capset: CapabilitySet) -> list[str]:
    """解析标的池。

    优先使用 preferences.pipeline_universe_scope：
      ALL / CSI300 / CSI500 / SSE50 / WATCHLIST
    - ALL + leftover TickFlow pool + TickFlow daily + batch → CN_Equity_A
    - ALL + public / custom pool or custom daily → instruments + watchlist + demo
    - CSI* → data/pools 缓存(缺则按 pool_route 刷新) + 用户自选
    """
    from app.services.universe_scope import (
        SCOPE_ALL,
        SCOPE_LABELS,
        normalize_scope,
        resolve_symbols,
        tickflow_all_a_expansion_allowed,
    )

    try:
        scope = normalize_scope(_prefs.get_pipeline_universe_scope(), default=SCOPE_ALL)
        allow_tickflow_all = tickflow_all_a_expansion_allowed(capset, scope=scope)
    except Exception:
        # Unreadable universe prefs: do not fail-open to TickFlow CN_Equity_A.
        scope = SCOPE_ALL
        allow_tickflow_all = False
    logger.info("resolve_universe scope=%s (%s)", scope, SCOPE_LABELS.get(scope, scope))

    # TickFlow universe only when pool_provider is explicitly TickFlow and
    # daily is not a declared custom source. Public / custom pool or custom
    # daily must not silently expand ALL via quote.pool / CN_Equity_A.
    if allow_tickflow_all:
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
        # 自选股是用户明确要求持续跟踪的标的, 必须叠加到任何配置范围。
        # resolve_symbols 会去重, WATCHLIST 范围本身也不会重复追加。
        include_watchlist=True,
        refresh_pools_if_missing=True,
    )
    if syms:
        return syms

    from app.tickflow.pools import pool_route

    route = pool_route()
    if route in {"custom", "unresolved"}:
        logger.warning(
            "resolve_universe empty under pool route=%s, fail-closed (no DEMO mix)",
            route,
        )
        return []

    # Last-resort free fallback for leftover public / TickFlow
    base: set[str] = set(DEMO_SYMBOLS)
    try:
        base.update(get_pool("watchlist") or [])
    except Exception:
        pass
    return sorted(base)


def _resolve_universe(capset: CapabilitySet) -> list[str]:
    """向后兼容旧内部入口; 新调用使用公开的 resolve_universe。"""
    return resolve_universe(capset)


def run_instruments_sync(repo: KlineRepository) -> dict:
    """盘前同步个股维表。"""
    outcome = instrument_sync.sync_instruments_result(repo.store.data_dir)
    if outcome.ok:
        _refresh_instruments_view(repo)
        _invalidate("instruments")
    current_rows = outcome.rows_published if outcome.ok else outcome.prior_rows
    issue = (
        None
        if outcome.ok
        else {
            "code": outcome.error_code,
            "message": outcome.error_message,
            "failed_exchanges": list(outcome.failed_exchanges),
        }
    )
    return {
        "instruments_rows": current_rows,
        "published_rows": outcome.rows_published,
        "outcome": outcome.outcome,
        "market_counts": outcome.market_counts,
        "prior_market_counts": outcome.prior_market_counts,
        "error_code": outcome.error_code,
        "error_message": outcome.error_message,
        "quality": {"ok": outcome.ok, "issues": [issue] if issue else []},
    }


def run_now(
    repo: KlineRepository,
    capset: CapabilitySet,
    on_progress: ProgressCb | None = None,
    override_start_date: Date | None = None,
    industry_time_limit_s: float | None = None,
    concept_time_limit_s: float | None = None,
) -> dict:
    """立即执行一次盘后管道,支持进度回调。

    跳过的 stage **不 emit**,避免前端把"无 capability"的卡片错误标记为 active/done。
    result 里带 skipped_stages 列表供前端展示。

    override_start_date 仅给日K修复入口使用: 传入后跳过"今天已有数据只刷实时行情"捷径,
    日K / 除权 / 指数 / ETF 统一从该日期拉到今天。日常盘后调度不传,行为不变。
    """
    emit = on_progress or _noop
    skipped: list[str] = []

    # Step 0: 先同步个股维表, 再解析标的池 — 确保标的池基于最新 instruments
    emit("sync_instruments", 2, "同步个股维表…")
    instruments_result = instrument_sync.sync_instruments_result(repo.store.data_dir)
    inst_rows = (
        instruments_result.rows_published
        if instruments_result.ok
        else instruments_result.prior_rows
    )
    if instruments_result.ok:
        _refresh_instruments_view(repo)
        _invalidate("instruments")
        emit("sync_instruments", 8, f"个股维表同步完成,{inst_rows} 只标的")
    else:
        skipped.append("sync_instruments_kept_prior")
        emit(
            "sync_instruments",
            8,
            f"个股维表同步降级，保留旧目录 {inst_rows} 只：{instruments_result.error_code}",
        )

    emit("resolve_universe", 9, "解析标的池…")
    universe = resolve_universe(capset)
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
    if override_start_date is not None and override_start_date > today:
        override_start_date = today

    def _daily_partition_dates() -> list[_date]:
        from app.services.kline_sync import usable_daily_partition_dates

        return usable_daily_partition_dates(repo.store.data_dir)

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
    elif override_start_date is not None:
        # 日K修复: 用户指定起点后必须走 batch, 不能因今天已有数据而只刷当日实时行情。
        start_date = override_start_date
        daily_range_start = start_date
        emit("sync_daily", 12, f"获取日K [{start_date} ~ {today}] (指定起点)…")
        logger.info("sync_daily: [%s ~ %s] override_start_date", start_date, today)

        def _daily_chunk_progress(cur: int, tot: int) -> None:
            emit("sync_daily", 12 + int(33 * cur / tot),
                 f"日K 批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)
        written_daily = kline_sync.sync_and_persist_daily_batch(
            universe, repo, capset,
            start_date=_dt.combine(start_date, _dt.min.time()),
            end_date=batch_end,
            on_chunk_done=_daily_chunk_progress,
        )
        daily_source = kline_sync.routed_daily_source_label()
        new_daily_days = _count_new_daily_days(latest_before)
        emit("sync_daily", 42, f"日K batch 完成,新增 {new_daily_days} 个交易日分区")
        logger.info(
            "sync_daily: [%s ~ %s] override done, rows=%s new_days=%s",
            start_date, today, written_daily, new_daily_days,
        )
    elif (
        today_exists
        and capset.has(Cap.QUOTE_POOL)
        and not kline_sync.daily_provider_is_custom()
    ):
        # 付费档 + TickFlow 日K:今天有数据(QuoteService 已落盘)→ 实时行情覆写。
        # 自定义日K 不得因 Cap.QUOTE_POOL 被 TickFlow quotes 静默换源。
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
        daily_source = kline_sync.routed_daily_source_label()
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
        daily_source = kline_sync.routed_daily_source_label()
        new_daily_days = _count_new_daily_days(latest_before)
        emit("sync_daily", 42, f"日K batch 完成,新增 {new_daily_days} 个交易日分区")
        logger.info(
            "sync_daily: [%s ~ %s] done, rows=%s new_days=%s",
            start_date, today, written_daily, new_daily_days,
        )

    # None/Free 兜底: free 历史日K若尚未提供 today, 用公开行情合成当日日K。
    # 仅在工作日尝试; 周末/已有 today / 用户关闭 A 股日K / 付费 quote.pool 时跳过。
    # 不读取 realtime_data_provider — 日K完整性与实时路由解耦。
    latest_after_batch = repo.latest_daily_date()
    today_missing = (latest_after_batch is None) or (latest_after_batch < today)
    want_public_eod = should_use_public_eod_fallback(
        pull_a_share=pull_a_share,
        today_missing=today_missing,
        weekday=today.weekday(),
        has_quote_pool=capset.has(Cap.QUOTE_POOL),
        daily_is_custom=kline_sync.daily_provider_is_custom(),
    )
    if want_public_eod:
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
    # Always attempt adj. TickFlow Starter+ uses Cap.ADJ_FACTOR; leftover
    # tickflow / healed same_as_daily on none/free is handled inside
    # sync_adj_factor via the public sina adapter. The old
    # `has(ADJ_FACTOR) or is_public` gate left that fallback dead.
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
        resolved = resolve_adj_sync_universe(universe, capset)
    except Exception as e:
        logger.warning("public adj universe resolve failed: %s", e)
        try:
            resolved = None if adj_sync_uses_public_adapter(capset) else list(universe)
        except Exception:  # noqa: BLE001
            resolved = None
    if resolved is None:
        written_adj, affected_symbols = 0, []
    else:
        adj_universe = resolved
        if adj_sync_uses_public_adapter(capset):
            emit(
                "sync_adj", 50,
                f"获取除权因子(public/{_prefs.get_public_data_scope()}) {len(adj_universe)} 只…",
            )
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

    # 部分分区修复 (#223) + 收盘价过期分区修复: 删除被实时合并提前创建、覆盖不全
    # 或收盘价停留在竞价前快照的 enriched 分区, 让下方计数比较与增量计算把它们
    # 重新当新日期处理 (值级比对以官方日线为准, 实时源不纠错也能自愈)
    if enriched_exists:
        partial_pruned = _prune_partial_enriched_partitions(daily_dir, enriched_dir)
        stale_pruned = _prune_stale_price_partitions(daily_dir, enriched_dir)
        pruned_dates = sorted(set(partial_pruned) | set(stale_pruned))
        if pruned_dates:
            logger.warning(
                "compute_enriched: 发现 %d 个异常 enriched 分区 (覆盖不全 %d / 收盘价过期 %d), "
                "已删除待重算: %s",
                len(pruned_dates), len(partial_pruned), len(stale_pruned),
                ", ".join(pruned_dates[:10]),
            )
            enriched_exists = enriched_dir.exists() and any(enriched_dir.glob("date=*"))
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
        written_enriched = fill_enriched_coverage_gap()
        if written_enriched:
            emit("compute_enriched", 88, f"enriched 覆盖缺口补齐 {written_enriched} 行")
            logger.info("compute_enriched: coverage gap fill %d rows", written_enriched)
        else:
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

    if (capset.has(Cap.KLINE_DAILY_BATCH) or kline_sync.daily_provider_is_custom()) and (
        pull_index or pull_etf
    ):
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
                default_index_start = _date.fromisoformat(index_dates[-1]) if index_dates else today - _td(days=365)
                index_start = override_start_date if override_start_date is not None else default_index_start
                if override_start_date is not None and index_start > today:
                    index_start = today

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
                if etf_symbols and kline_sync.adj_live_fetch_allowed(capset):
                    try:
                        emit("sync_index", 88, "同步 ETF 除权因子…")
                        from datetime import datetime, timedelta
                        adj_end = datetime.now()
                        fallback_start = adj_end - timedelta(days=30)
                        adj_start = kline_sync.adj_coverage_start(
                            repo.store.data_dir,
                            "etf",
                            fallback_start,
                        )
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
                default_etf_start = _date.fromisoformat(etf_dates[-1]) if etf_dates else today - _td(days=365)
                etf_start = override_start_date if override_start_date is not None else default_etf_start
                if override_start_date is not None and etf_start > today:
                    etf_start = today

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

    if minute_on and kline_sync.minute_sync_allowed(capset):
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

    if not instruments_result.ok:
        quality_report = dict(quality_report or {})
        quality_report["ok"] = False
        quality_report.setdefault("issues", []).append(
            {
                "code": instruments_result.error_code,
                "message": instruments_result.error_message,
                "failed_exchanges": list(instruments_result.failed_exchanges),
            }
        )

    quality_ok = bool(quality_report and quality_report.get("ok") is True)

    # Industry then concept continuation after quality is decided and before done.
    # Failure here must not flip quality_ok or rewrite daily_days.
    # Mutual exclusion stays on the existing job slot / _run_tracked path.
    # Industry failure/timeout does not skip concept.
    _INDUSTRY_ROLL_CANCEL.clear()
    _CONCEPT_ROLL_CANCEL.clear()
    emit("industry_fund_flow", 98, "行业资金流日线续更…")
    industry_fund_flow_daily = _run_industry_fund_flow_daily_roll(
        repo.store.data_dir,
        cancel_event=_INDUSTRY_ROLL_CANCEL,
        time_limit_s=industry_time_limit_s,
        on_progress=emit,
    )
    emit("concept_fund_flow", 99, "概念资金流日线续更…")
    concept_fund_flow_daily = _run_concept_fund_flow_daily_roll(
        repo.store.data_dir,
        cancel_event=_CONCEPT_ROLL_CANCEL,
        time_limit_s=concept_time_limit_s,
        on_progress=emit,
    )
    emit("done", 100, "完成" if quality_ok else "完成，但质量门禁未通过")
    _invalidate(None)  # 兜底:全清

    return {
        "universe_size": len(universe),
        "daily_days": new_daily_days,
        "daily_source": daily_source,
        "override_start_date": override_start_date.isoformat() if override_start_date else None,
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
        "instruments_sync": instruments_result.as_dict(),
        "skipped_stages": skipped,
        "quality": quality_report,
        "industry_fund_flow_daily": industry_fund_flow_daily,
        "concept_fund_flow_daily": concept_fund_flow_daily,
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
    try:
        repo.store._register_gated_catalog_views()
    except Exception as e:  # noqa: BLE001
        logger.warning("re-gate catalog views after pipeline refresh failed: %s", e)
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
    try:
        repo.store._register_gated_catalog_views()
    except Exception as e:  # noqa: BLE001
        logger.warning("re-gate catalog views after %s refresh failed: %s", name, e)


def _resolve_minute_symbols(capset: CapabilitySet) -> list[str]:
    """分钟 K 同步标的 — 与日K共用同一标的池。"""
    return resolve_universe(capset)


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

    from app.services.pipeline_jobs import is_cancelled, release_run_slot, try_acquire_run_slot

    operation = "instruments" if job_label == "instruments_sync" else "daily_pipeline"
    created = job_store.create(
        mirror={"dataset_id": "daily_pipeline", "operation": operation}
    )
    job_id = str(created)
    if not created.is_new:
        logger.info("scheduled %s reused active job %s", job_label, job_id)
        return
    if is_cancelled(job_id):
        return
    if not try_acquire_run_slot(job_id):
        job_store.fail(job_id, "已有数据任务在运行(或上一次任务卡死未结束),请稍后再试")
        return

    def progress(stage: str, pct: int, msg: str, stage_pct: int | None = None,
                 skip_log: bool = False) -> None:
        job_store.progress(job_id, stage, pct, msg, stage_pct=stage_pct, skip_log=skip_log)

    try:
        job_store.start(job_id)
        result = fn(on_progress=progress)
        job_store.complete(job_id, result)
        logger.info("scheduled %s completed: job_id=%s", job_label, job_id)
    except Exception:
        logger.exception("scheduled %s failed: job_id=%s", job_label, job_id)
        job_store.fail(job_id, f"scheduled {job_label} failed")
    finally:
        release_run_slot(job_id)


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

        # 推送门控: review_push_mode=manual 时定时复盘只归档不推送,
        # 由用户对当日报告显式确认后才推; auto 时保持既有自动推送行为。
        # 失败静默降级, 不影响已归档的报告。
        from app.services import preferences as _prefs
        if _prefs.get_review_push_mode() == "auto":
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
    channels 为空则不推送; 复用监控中心的全局外部渠道配置。
    推送失败静默降级 (Webhook 是辅助通道), 不影响已归档的报告。
    """
    try:
        from app import secrets_store
        from app.services import email_adapter, preferences, webhook_adapter

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
                    url, "每日复盘", subtitle, content, secret
                )
                logger.info("review push(feishu) %s", "sent" if ok else "failed")
            elif ch == "wecom":
                url = preferences.get_wecom_webhook_url()
                if not url:
                    logger.info("review push(wecom) skipped: webhook not configured")
                    continue
                full_body = (f"**{subtitle}**\n\n{content}" if subtitle else content)
                ok = webhook_adapter.send_wecom_markdown(
                    url, "每日复盘", full_body
                )
                logger.info("review push(wecom) %s", "sent" if ok else "failed")
            elif ch == "custom":
                url = preferences.get_custom_webhook_url()
                if not url:
                    logger.info("review push(custom) skipped: webhook not configured")
                    continue
                ok = webhook_adapter.send_custom(
                    url,
                    "每日复盘",
                    content,
                    "market_review",
                    meta,
                    secrets_store.get_custom_webhook_secret(),
                )
                logger.info("review push(custom) %s", "sent" if ok else "failed")
            elif ch == "email":
                config = preferences.get_email_smtp_config()
                if not email_adapter.is_configured(config):
                    logger.info("review push(email) skipped: SMTP not configured")
                    continue
                email_body = (f"{subtitle}\n\n{content}" if subtitle else content)
                ok = email_adapter.send_email(
                    config,
                    secrets_store.get_email_smtp_password(),
                    "每日复盘",
                    email_body,
                )
                logger.info("review push(email) %s", "sent" if ok else "failed")
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
    工作日 HH:MM — 盘后管道（时间由用户偏好决定，默认 15:35）
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
        if result.get("outcome") == "published":
            message = f"个股维表同步完成,{result.get('instruments_rows', 0)} 只标的"
        else:
            message = (
                f"个股维表同步降级，保留旧目录 {result.get('instruments_rows', 0)} 只："
                f"{result.get('error_code') or 'unknown'}"
            )
        emit("done", 100, message)
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
