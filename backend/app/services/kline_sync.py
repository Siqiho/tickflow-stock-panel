"""日 K 同步服务(§7.7 Step 1)。

调度器在 capability 允许下,把符号集合的日 K 批量同步到本地 Parquet。
策略:
  - 日 K 仅使用 `kline.daily.batch`
  - 除权因子仅使用 `adj_factor`
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta

import polars as pl

from app.indicators.pipeline import filter_halt_days
from app.services.atomic_io import atomic_write_parquet
from app.tickflow.capabilities import Cap, CapabilitySet
from app.tickflow.client import get_client
from app.tickflow.repository import KlineRepository

logger = logging.getLogger(__name__)


# 标准列(无论 SDK 返回什么形状,我们把它规范成这套)
CANONICAL_DAILY_COLS = [
    "symbol", "date", "open", "high", "low", "close", "volume", "amount",
]


def _normalize_daily(df_in, default_symbol: str | None = None) -> pl.DataFrame:
    """把 SDK 返回的 pandas/任意 DataFrame 规范成 canonical 列。"""
    if df_in is None or len(df_in) == 0:
        return pl.DataFrame()

    if not isinstance(df_in, pl.DataFrame):
        df = pl.from_pandas(df_in.reset_index() if hasattr(df_in, "reset_index") else df_in)
    else:
        df = df_in

    # 兼容字段名差异
    rename_map = {
        "ts_code": "symbol",
        "trade_date": "date",
        "vol": "volume",
        "amt": "amount",
        "datetime": "date",
    }
    df = df.rename({k: v for k, v in rename_map.items() if k in df.columns})

    if "symbol" not in df.columns and default_symbol is not None:
        df = df.with_columns(pl.lit(default_symbol).alias("symbol"))

    # 类型规范
    if "date" in df.columns and df.schema["date"] != pl.Date:
        df = df.with_columns(pl.col("date").cast(pl.Date, strict=False))

    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Float64, strict=False))
    for col in ("volume", "amount"):
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Float64, strict=False))

    # 过滤停牌日 (open/high 为 0; close 可能被填充为前收盘价, 不能用全零判断)
    df = filter_halt_days(df)

    # 只保留 canonical 列
    keep = [c for c in CANONICAL_DAILY_COLS if c in df.columns]
    return df.select(keep)


def sync_daily_batch(symbols: list[str],
                     count: int | None = None,
                     batch_size: int | None = None,
                     rpm: int | None = None,
                     start_time: datetime | None = None,
                     end_time: datetime | None = None,
                     on_chunk_done: Callable[[int, int], None] | None = None) -> pl.DataFrame:
    """批量拉取多股日 K。

    优先使用 start_time / end_time 区间 + count=10000,确保覆盖完整时间段。
    仅传 count 时按条数回溯。
    """
    tf = get_client()
    out: list[pl.DataFrame] = []
    interval = (60.0 / rpm) if rpm else 0

    if batch_size is None:
        chunks = [symbols]
    else:
        chunks = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]

    for i, chunk in enumerate(chunks):
        if i > 0 and interval > 0 and len(chunks) > rpm:
            time.sleep(interval)
        try:
            if start_time and end_time:
                raw = tf.klines.batch(
                    chunk, period="1d", adjust="none",
                    start_time=_datetime_to_ms(start_time),
                    end_time=_datetime_to_ms(end_time),
                    count=10000,
                    as_dataframe=True, show_progress=False,
                )
            else:
                raw = tf.klines.batch(chunk, period="1d", count=count or 250, adjust="none",
                                      as_dataframe=True, show_progress=False)
        except Exception as e:  # noqa: BLE001
            logger.warning("batch fetch failed for %d symbols: %s", len(chunk), e)
            continue

        # 兼容两种形态:dict[sym → df] 和扁平 df
        if isinstance(raw, dict):
            for sym, sub in raw.items():
                if sub is None or len(sub) == 0:
                    continue
                out.append(_normalize_daily(sub, default_symbol=sym))
        elif raw is not None and len(raw) > 0:
            out.append(_normalize_daily(raw))

        if on_chunk_done:
            on_chunk_done(i + 1, len(chunks))

    if not out:
        return pl.DataFrame()
    return pl.concat(out, how="diagonal_relaxed")


def sync_and_persist_daily_batch(
    symbols: list[str],
    repo: KlineRepository,
    capset: CapabilitySet,
    count: int | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    on_chunk_done: Callable[[int, int], None] | None = None,
) -> int:
    """批量同步日 K 并落到 Parquet。返回写入的行数。

    start_date/end_date: 外部传入的时间范围(由 pipeline 根据已有数据计算)。
    未传入时默认拉最近 1 年。
    """
    if not symbols or not capset.has(Cap.KLINE_DAILY_BATCH):
        return 0

    lim = capset.limits(Cap.KLINE_DAILY_BATCH)
    batch_size = lim.batch if lim and lim.batch else 100
    rpm = lim.rpm if lim else None

    end_time = end_date or datetime.now()
    start_time = start_date or (end_time - timedelta(days=365))

    df = sync_daily_batch(
        symbols, count=count, batch_size=batch_size, rpm=rpm,
        start_time=start_time, end_time=end_time,
        on_chunk_done=on_chunk_done,
    )

    if df.is_empty():
        return 0

    repo.append_daily(df)

    try:
        d = repo.store.data_dir.as_posix()
        repo.db.execute(
            f"""CREATE OR REPLACE VIEW kline_daily AS
                SELECT * FROM read_parquet('{d}/kline_daily/**/*.parquet', union_by_name=true)"""
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("refresh view failed: %s", e)

    return df.height


def sync_daily_by_quotes(repo: KlineRepository) -> int:
    """用实时行情接口拉全市场当日数据,覆写 kline_daily 今天分区。

    一个请求覆盖 ~5500 只股票,比 batch K-line 快几个数量级。
    返回写入的行数。
    """
    from datetime import date as _date

    from app.tickflow.client import get_client

    tf = get_client()
    try:
        resp = tf.quotes.get_by_universes(universes=["CN_Equity_A"])
    except Exception as e:
        logger.warning("get_by_universes failed: %s", e)
        return 0

    if not resp:
        logger.warning("get_by_universes returned empty")
        return 0

    records = []
    for q in resp:
        records.append({
            "symbol": q.get("symbol"),
            "open": q.get("open"),
            "high": q.get("high"),
            "low": q.get("low"),
            "close": q.get("last_price"),
            "volume": q.get("volume"),
            "amount": q.get("amount"),
        })

    df = pl.DataFrame(records)
    if df.is_empty():
        return 0

    today = _date.today()
    daily_df = df.with_columns(pl.lit(today).cast(pl.Date).alias("date"))

    # 过滤停牌 (open/high 为 0; close 可能被填充为前收盘价, 不能用全零判断)
    daily_df = filter_halt_days(daily_df)

    repo.flush_live_daily(daily_df)
    logger.info("sync_daily_by_quotes: %d symbols flushed for %s", daily_df.height, today)
    return daily_df.height


def _public_quote_records_to_daily(records: list[dict], trade_date: date) -> pl.DataFrame:
    """把腾讯/新浪公开行情快照规范成 canonical 日K行。"""
    if not records:
        return pl.DataFrame()

    rows: list[dict] = []
    for q in records:
        symbol = str(q.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        close = q.get("last")
        if close is None:
            close = q.get("last_price")
        if close is None:
            close = q.get("close")
        open_ = q.get("open")
        high = q.get("high")
        low = q.get("low")
        # 先按原始 open/high 识别停牌，再做 0/null 填充，避免把停牌日填成假蜡烛。
        if open_ in (0, 0.0) and high in (0, 0.0):
            continue
        # 非交易时段偶发 open/high/low 为 0/null，用 close 兜底，避免脏蜡烛。
        if open_ in (None, 0) and close not in (None, 0):
            open_ = close
        if high in (None, 0) and close not in (None, 0):
            high = close
        if low in (None, 0) and close not in (None, 0):
            low = close
        rows.append({
            "symbol": symbol,
            "date": trade_date,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": q.get("volume"),
            "amount": q.get("amount"),
        })

    if not rows:
        return pl.DataFrame()

    df = pl.DataFrame(rows)
    for col in ("open", "high", "low", "close", "volume", "amount"):
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Float64, strict=False))
    if "date" in df.columns and df.schema["date"] != pl.Date:
        df = df.with_columns(pl.col("date").cast(pl.Date, strict=False))

    keep = [c for c in CANONICAL_DAILY_COLS if c in df.columns]
    df = df.select(keep)
    df = filter_halt_days(df)
    if "close" in df.columns:
        df = df.filter(pl.col("close").is_not_null() & (pl.col("close") > 0))
    if "symbol" in df.columns:
        df = df.unique(subset=["symbol"], keep="last").sort("symbol")
    return df


def sync_daily_by_public_quotes(
    symbols: list[str],
    repo: KlineRepository,
    *,
    trade_date: date | None = None,
    batch_size: int = 80,
    pause_s: float = 0.05,
) -> dict:
    """None/Free 兜底: 用腾讯/新浪公开行情合成当日日K并覆写 kline_daily 分区。

    只补“今天”这一天，不替代 TickFlow free 历史日K。
    返回 {rows, date, source}；失败时 rows=0。
    """
    from app.services.atomic_io import write_lineage_record
    from app.services.free_sources.quote_fallback import fetch_public_market_quotes

    today = trade_date or date.today()
    if not symbols:
        return {"rows": 0, "date": today.isoformat(), "source": "public_quote_eod"}

    try:
        records = fetch_public_market_quotes(
            list(symbols),
            batch_size=batch_size,
            pause_s=pause_s,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("sync_daily_by_public_quotes fetch failed: %s", e)
        return {"rows": 0, "date": today.isoformat(), "source": "public_quote_eod", "error": str(e)}

    daily_df = _public_quote_records_to_daily(records, today)
    if daily_df.is_empty():
        logger.warning("sync_daily_by_public_quotes: empty after normalize (%d raw)", len(records or []))
        return {"rows": 0, "date": today.isoformat(), "source": "public_quote_eod"}

    repo.flush_live_daily(daily_df)

    # flush_live_daily 本身不写 lineage；这里补一条，便于区分 free 历史 vs public 合成。
    try:
        ds = today.isoformat()
        out = repo.store.data_dir / "kline_daily" / f"date={ds}" / "part.parquet"
        scope = None
        try:
            from app.services import preferences
            scope = preferences.get_pipeline_universe_scope()
        except Exception:  # noqa: BLE001
            scope = None
        write_lineage_record(
            repo.store.data_dir,
            "kline_daily",
            {
                "date": ds,
                "source": "public_quote_eod",
                "unit_version": "canonical_daily_v1",
                "row_count": daily_df.height,
                "scope": scope,
                "quality": "pending_gate",
                "target_artifact": str(out.relative_to(repo.store.data_dir)) if out.exists() else None,
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("public eod lineage write skipped: %s", e)

    # 刷新 DuckDB 日K视图，确保后续 latest_daily_date / enriched 能看到今天。
    try:
        d = repo.store.data_dir.as_posix()
        repo.db.execute(
            f"""CREATE OR REPLACE VIEW kline_daily AS
                SELECT * FROM read_parquet('{d}/kline_daily/**/*.parquet', union_by_name=true)"""
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("refresh kline_daily view after public eod failed: %s", e)

    logger.info(
        "sync_daily_by_public_quotes: %d symbols flushed for %s (raw=%d)",
        daily_df.height, today, len(records or []),
    )
    return {
        "rows": int(daily_df.height),
        "date": today.isoformat(),
        "source": "public_quote_eod",
    }


def _normalize_adj_factor(raw) -> pl.DataFrame:
    """Normalize SDK ex_factors response to symbol/trade_date/ex_factor."""
    if raw is None or len(raw) == 0:
        return pl.DataFrame()
    if isinstance(raw, dict):
        rows: list[dict] = []
        for sym, values in raw.items():
            for item in values or []:
                row = dict(item or {})
                row.setdefault("symbol", sym)
                rows.append(row)
        df = pl.DataFrame(rows) if rows else pl.DataFrame()
    elif isinstance(raw, pl.DataFrame):
        df = raw
    else:
        df = pl.from_pandas(raw.reset_index() if hasattr(raw, "reset_index") else raw)
    if df.is_empty():
        return df
    # rename: timestamp/date → trade_date, adj_factor → ex_factor
    # 注意: 新版 SDK 可能同时返回 timestamp 和 trade_date (或 adj_factor 和 ex_factor),
    # 直接 rename 会产生重复列报错。仅当目标列不存在时才 rename。
    rename_map: dict[str, str] = {}
    for src, dst in (("timestamp", "trade_date"), ("date", "trade_date"), ("adj_factor", "ex_factor")):
        if src in df.columns and dst not in df.columns:
            rename_map[src] = dst
    df = df.rename(rename_map)
    if "trade_date" in df.columns:
        if df.schema["trade_date"] in {pl.Int64, pl.Int32, pl.UInt64, pl.UInt32, pl.Float64, pl.Float32}:
            df = df.with_columns(
                pl.from_epoch(pl.col("trade_date").cast(pl.Int64), time_unit="ms").dt.date().alias("trade_date")
            )
        else:
            df = df.with_columns(pl.col("trade_date").cast(pl.Date, strict=False))
    if "ex_factor" in df.columns:
        df = df.with_columns(pl.col("ex_factor").cast(pl.Float64, strict=False))
    cols = [c for c in ["symbol", "trade_date", "ex_factor"] if c in df.columns]
    if len(cols) < 3:
        return pl.DataFrame()
    return df.select(cols).drop_nulls()


def sync_adj_factor(symbols: list[str], repo: KlineRepository,
                    capset: CapabilitySet,
                    start_time: datetime | None = None,
                    end_time: datetime | None = None,
                    on_chunk_done: Callable[[int, int], None] | None = None,
                    asset_type: str = "stock") -> tuple[int, list[str]]:
    """同步除权因子。

    - 默认 TickFlow Starter+：`tf.klines.ex_factors`（需 Cap.ADJ_FACTOR）
    - 当 preferences.adj_factor_provider ∈ {public,sina,sina_qfq,free} 时：
      走 free_sources.adj_factor_public（新浪 qfq.js），**不依赖** Cap.ADJ_FACTOR

    支持增量: 传 start_time/end_time 只保留该时间范围内的新除权事件。
    返回 (写入行数, 受影响的 symbol 列表) — 供 enriched 局部重算使用。
    """
    if not symbols:
        return 0, []

    # Public free path (no TickFlow subscription)
    try:
        from app.services import preferences as _prefs
        use_public = _prefs.is_public_adj_factor_provider()
    except Exception:  # noqa: BLE001
        use_public = False

    if use_public:
        from app.data_providers.registry import get_provider

        def _prog(cur: int, tot: int, _sym: str = "") -> None:
            if on_chunk_done:
                on_chunk_done(cur, tot)

        result = get_provider("public").sync_adj_factors(
            symbols,
            repo.store.data_dir,
            asset_type=asset_type,
            start=start_time,
            end=end_time,
            on_progress=_prog,
            workers=4,
            flush_every=25,
            skip_checked_within_hours=18.0,
            pause_s=0.0,
        )
        return int(result.get("rows_delta") or 0), list(result.get("symbols_affected") or [])

    if not capset.has(Cap.ADJ_FACTOR):
        return 0, []

    tf = get_client()
    lim = capset.limits(Cap.ADJ_FACTOR)
    batch_size = lim.batch if lim and lim.batch else 50
    rpm = lim.rpm if lim else 30
    interval = 60.0 / rpm if rpm else 0

    # 构建 SDK 参数
    sdk_kwargs: dict = {"as_dataframe": True, "batch_size": batch_size, "show_progress": False}
    if start_time:
        sdk_kwargs["start_time"] = _datetime_to_ms(start_time)
    if end_time:
        sdk_kwargs["end_time"] = _datetime_to_ms(end_time)

    chunks = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
    all_dfs: list[pl.DataFrame] = []

    for i, chunk in enumerate(chunks):
        if i > 0 and interval > 0 and len(chunks) > rpm:
            time.sleep(interval)
        try:
            raw = tf.klines.ex_factors(chunk, **sdk_kwargs)
            normalized = _normalize_adj_factor(raw)
            if not normalized.is_empty():
                all_dfs.append(normalized)
            logger.debug("adj_factor chunk %d/%d: %d symbols", i + 1, len(chunks), len(chunk))
        except Exception as e:  # noqa: BLE001
            logger.warning("adj_factor chunk %d failed: %s", i + 1, e)

        if on_chunk_done:
            on_chunk_done(i + 1, len(chunks))

    if not all_dfs:
        return 0, []

    new_data = pl.concat(all_dfs, how="diagonal_relaxed") if len(all_dfs) > 1 else all_dfs[0]

    # 提取受影响的 symbol 列表(合并前)
    affected = new_data["symbol"].unique().to_list()

    factor_dir = "adj_factor_etf" if asset_type == "etf" else "adj_factor"
    out = repo.store.data_dir / factor_dir / "all.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.exists():
        existing = pl.read_parquet(out)
        before = existing.height
        merged = pl.concat([existing, new_data]).unique(
            subset=["symbol", "trade_date"], keep="last",
        ).sort(["symbol", "trade_date"])
        atomic_write_parquet(merged, out)
        added = merged.height - before
        logger.info("adj_factor merged: %d total (+%d new), %d/%d symbols",
                     merged.height, added, new_data.height, len(symbols))
        return added, affected
    else:
        atomic_write_parquet(new_data.sort(["symbol", "trade_date"]), out)
        logger.info("adj_factor synced: %d rows (%d symbols)", new_data.height, len(symbols))
        return new_data.height, affected


# ===== 分钟 K 同步 =====

CANONICAL_MINUTE_COLS = [
    "symbol", "datetime", "open", "high", "low", "close", "volume", "amount",
]


def _normalize_minute(df_in, default_symbol: str | None = None) -> pl.DataFrame:
    """把 SDK 返回的分钟 K 数据规范成 canonical 列。"""
    if df_in is None or len(df_in) == 0:
        return pl.DataFrame()

    if not isinstance(df_in, pl.DataFrame):
        df = pl.from_pandas(df_in.reset_index() if hasattr(df_in, "reset_index") else df_in)
    else:
        df = df_in

    rename_map = {
        "ts_code": "symbol",
        "vol": "volume",
        "amt": "amount",
    }
    df = df.rename({k: v for k, v in rename_map.items() if k in df.columns})

    # datetime 列:优先用 timestamp(毫秒精度),其次 trade_time
    if "timestamp" in df.columns:
        df = df.with_columns(
            pl.from_epoch("timestamp", time_unit="ms").alias("datetime"),
        ).drop("timestamp")
        for drop_col in ("trade_time", "trade_date"):
            if drop_col in df.columns:
                df = df.drop(drop_col)
    elif "trade_time" in df.columns:
        df = df.rename({"trade_time": "datetime"})
        if "trade_date" in df.columns:
            df = df.drop("trade_date")
    elif "trade_date" in df.columns:
        df = df.rename({"trade_date": "datetime"})

    if "symbol" not in df.columns and default_symbol is not None:
        df = df.with_columns(pl.lit(default_symbol).alias("symbol"))

    # 类型规范:统一转 Datetime('us')
    if "datetime" in df.columns:
        dt_type = df.schema["datetime"]
        if not isinstance(dt_type, pl.Datetime) or dt_type.time_unit != "us":
            df = df.with_columns(pl.col("datetime").cast(pl.Datetime("us"), strict=False))

    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Float64, strict=False))
    for col in ("volume", "amount"):
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Float64, strict=False))

    keep = [c for c in CANONICAL_MINUTE_COLS if c in df.columns]
    return df.select(keep)


def _datetime_to_ms(dt: datetime) -> int:
    """datetime → 毫秒时间戳 (供 SDK start_time / end_time 使用)。"""
    return int(dt.timestamp() * 1000)


def sync_minute_batch(
    symbols: list[str],
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    count: int | None = None,
    batch_size: int | None = None,
    rpm: int | None = None,
    on_chunk_done: Callable[[int, int], None] | None = None,
) -> pl.DataFrame:
    """批量拉取多股分钟 K。

    优先使用 start_time / end_time 区间, 确保所有标的覆盖同一时间段。
    count 仅作为 fallback 保留。
    on_chunk_done(current, total) 每个 chunk 完成后回调。
    """
    tf = get_client()
    out: list[pl.DataFrame] = []
    interval = (60.0 / rpm) if rpm else 0

    if batch_size is None:
        chunks = [symbols]
    else:
        chunks = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]

    for i, chunk in enumerate(chunks):
        if i > 0 and interval > 0 and len(chunks) > rpm:
            time.sleep(interval)
        try:
            if start_time and end_time:
                raw = tf.klines.batch(
                    chunk, period="1m",
                    start_time=_datetime_to_ms(start_time),
                    end_time=_datetime_to_ms(end_time),
                    count=10000,
                    as_dataframe=True, show_progress=False,
                )
            else:
                raw = tf.klines.batch(chunk, period="1m", count=count or 1200,
                                      as_dataframe=True, show_progress=False)
        except Exception as e:  # noqa: BLE001
            logger.warning("minute batch fetch failed for %d symbols: %s", len(chunk), e)
            continue

        if isinstance(raw, dict):
            for sym, sub in raw.items():
                if sub is None or len(sub) == 0:
                    continue
                out.append(_normalize_minute(sub, default_symbol=sym))
        elif raw is not None and len(raw) > 0:
            out.append(_normalize_minute(raw))

        if on_chunk_done:
            on_chunk_done(i + 1, len(chunks))

    if not out:
        return pl.DataFrame()
    return pl.concat(out, how="diagonal_relaxed")


def fetch_minute_single(symbol: str, trade_date: date) -> pl.DataFrame:
    """拉取单股单日分钟 K（不写入本地）。

    优先 TickFlow；失败或无权限时回退公开分时（仅适合当日/最近交易日视图）。
    """
    from datetime import datetime

    start_time = datetime(trade_date.year, trade_date.month, trade_date.day, 9, 25, 0)
    end_time = datetime(trade_date.year, trade_date.month, trade_date.day, 15, 5, 0)
    try:
        tf = get_client()
        raw = tf.klines.batch(
            [symbol], period="1m",
            start_time=_datetime_to_ms(start_time),
            end_time=_datetime_to_ms(end_time),
            count=10000,
            as_dataframe=True, show_progress=False,
        )
        if isinstance(raw, dict):
            sub = raw.get(symbol)
            if sub is not None and len(sub) > 0:
                return _normalize_minute(sub)
        elif raw is not None and len(raw) > 0:
            return _normalize_minute(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_minute_single(%s, %s) TickFlow failed: %s", symbol, trade_date, e)

    # Public fallback (Tencent cumulative minute -> OHLC-like rows)
    try:
        from app.services.free_sources.intraday_public import public_intraday_to_minute_rows
        rows = public_intraday_to_minute_rows(symbol, trade_date=trade_date)
        if not rows:
            return pl.DataFrame()
        df = pl.DataFrame(rows)
        # datetime may be string; normalize helper expects proper types
        if "datetime" in df.columns and df["datetime"].dtype == pl.Utf8:
            df = df.with_columns(pl.col("datetime").str.to_datetime(strict=False))
        return _normalize_minute(df, default_symbol=symbol)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_minute_single(%s, %s) public fallback failed: %s", symbol, trade_date, e)
        return pl.DataFrame()


def fetch_adj_factor_single(symbol: str) -> pl.DataFrame:
    """从 TickFlow 实时拉取单股除权因子(不写入本地), 用于单股 K 线即时前复权。

    返回结构: symbol, trade_date, ex_factor (空 DataFrame 表示无除权事件或拉取失败)。
    与 _apply_adj_factor / compute_enriched 的 factors 参数格式一致。
    """
    tf = get_client()
    try:
        raw = tf.klines.ex_factors([symbol], as_dataframe=True, show_progress=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_adj_factor_single(%s) failed: %s", symbol, e)
        return pl.DataFrame()
    return _normalize_adj_factor(raw)


def _latest_minute_datetime(repo: KlineRepository) -> datetime | None:
    """本地分钟 K 数据的最新时间。"""
    try:
        res = repo.execute_one("SELECT max(datetime) FROM kline_minute")
        if res and res[0]:
            d = res[0]
            if isinstance(d, datetime):
                return d
            return datetime.fromisoformat(str(d))
    except Exception:  # noqa: BLE001
        pass
    return None


def _cleanup_null_datetime_minute(repo: KlineRepository) -> None:
    """检测并清除 datetime 全为 null 的旧版分钟 K 数据(迁移用)。"""
    minute_dir = repo.store.data_dir / "kline_minute"
    if not minute_dir.exists():
        return
    try:
        row = repo.execute_one(
            "SELECT count(*) AS total, count(datetime) AS non_null FROM kline_minute"
        )
        if row and row[0] > 0 and (row[1] is None or row[1] == 0):
            # 全部 datetime 为 null — 清除所有分钟 K parquet
            n = 0
            for f in minute_dir.rglob("*.parquet"):
                f.unlink()
                n += 1
            logger.info("cleaned %d corrupted minute-K parquet files (null datetime)", n)
    except Exception as e:  # noqa: BLE001
        logger.debug("minute cleanup check failed: %s", e)


def _migrate_symbol_to_date_partition(repo: KlineRepository) -> None:
    """将旧版 symbol= 分区迁移为 date= 分区。迁移完成后删除旧目录。"""
    minute_dir = repo.store.data_dir / "kline_minute"
    if not minute_dir.exists():
        return

    old_dirs = [d for d in minute_dir.iterdir() if d.is_dir() and d.name.startswith("symbol=")]
    if not old_dirs:
        return

    logger.info("migrating %d symbol-partitioned minute-K dirs to date partition…", len(old_dirs))

    all_frames: list[pl.DataFrame] = []
    for sym_dir in old_dirs:
        for pq in sym_dir.glob("*.parquet"):
            try:
                df = pl.read_parquet(pq)
                if "datetime" in df.columns:
                    df = df.filter(pl.col("datetime").is_not_null())
                if not df.is_empty():
                    all_frames.append(df)
            except Exception:  # noqa: BLE001
                pass

    if not all_frames:
        # 数据全部不可用，直接删旧目录
        for d in old_dirs:
            d.mkdir(parents=True, exist_ok=True)
            for f in d.rglob("*"):
                if f.is_file():
                    f.unlink()
            d.rmdir()
        return

    combined = pl.concat(all_frames, how="diagonal_relaxed")
    combined = combined.unique(subset=["symbol", "datetime"], keep="last")

    # 按日期写新分区
    combined = combined.with_columns(pl.col("datetime").dt.date().alias("_trade_date"))
    for day_df in combined.partition_by("_trade_date"):
        trade_date = day_df["_trade_date"][0]
        out = minute_dir / f"date={trade_date}" / "part.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        day_df = day_df.drop("_trade_date").sort("symbol", "datetime")
        day_df.write_parquet(out)

    # 删旧目录
    for d in old_dirs:
        for f in d.rglob("*"):
            if f.is_file():
                f.unlink()
        # 移除空目录
        try:
            d.rmdir()
        except OSError:
            pass

    logger.info("minute-K migration done: %d rows migrated", combined.height)


def sync_and_persist_minute(
    symbols: list[str],
    repo: KlineRepository,
    capset: CapabilitySet,
    days: int = 5,
    on_chunk_done: Callable[[int, int], None] | None = None,
) -> int:
    """同步分钟 K 并存到 Parquet(仅 raw,不前复权)。返回写入行数。

    使用 start_time / end_time 区间拉取, 确保所有标的覆盖同一时间段。
    on_chunk_done(current, total) 每个 chunk 完成后回调。
    """
    if not symbols or not capset.has(Cap.KLINE_MINUTE_BATCH):
        return 0

    # 迁移:旧版 _normalize_minute 未转换 timestamp→datetime,导致全部 datetime 为 null
    # 检测到后直接清除(这些数据无法使用)
    _cleanup_null_datetime_minute(repo)

    # 迁移:旧版按 symbol= 分区转为 date= 分区
    _migrate_symbol_to_date_partition(repo)

    now = datetime.now()

    # 计算时间区间: 首次拉取回溯 N 天, 增量从最后数据时间开始
    last_dt = _latest_minute_datetime(repo)
    if last_dt:
        start_time = last_dt
    else:
        start_time = now - timedelta(days=days)
    end_time = now

    lim = capset.limits(Cap.KLINE_MINUTE_BATCH)
    batch_size = lim.batch if lim and lim.batch else 100
    rpm = lim.rpm if lim else 30

    df = sync_minute_batch(symbols, start_time=start_time, end_time=end_time,
                           batch_size=batch_size, rpm=rpm,
                           on_chunk_done=on_chunk_done)
    if df.is_empty():
        return 0

    # 按日期分区写: data/kline_minute/date={YYYY-MM-DD}/part.parquet
    df = df.with_columns(
        pl.col("datetime").dt.date().alias("_trade_date")
    )
    written = 0
    for day_df in df.partition_by("_trade_date"):
        trade_date = day_df["_trade_date"][0]
        out = repo.store.data_dir / "kline_minute" / f"date={trade_date}" / "part.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            existing = pl.read_parquet(out)
            if "datetime" in existing.columns:
                existing = existing.filter(pl.col("datetime").is_not_null())
            day_df = pl.concat([existing, day_df.drop("_trade_date")]).unique(
                subset=["symbol", "datetime"], keep="last",
            )
        else:
            day_df = day_df.drop("_trade_date")
        day_df = day_df.sort("symbol", "datetime")
        day_df.write_parquet(out)
        written += day_df.height

    # 刷新视图
    try:
        d = repo.store.data_dir.as_posix()
        repo.db.execute(
            f"""CREATE OR REPLACE VIEW kline_minute AS
                SELECT * FROM read_parquet('{d}/kline_minute/**/*.parquet', union_by_name=true)"""
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("refresh kline_minute view failed: %s", e)

    logger.info("minute K synced: %d rows (%d symbols)", written, len(symbols))
    return written
