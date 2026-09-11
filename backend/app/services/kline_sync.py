"""日 K 同步服务(§7.7 Step 1)。

调度器在 capability 允许下,把符号集合的日 K 批量同步到本地 Parquet。
策略:
  - 日 K 仅使用 `kline.daily.batch`
  - 除权因子仅使用 `adj_factor`
"""
from __future__ import annotations

import contextlib
import logging
import shutil
import threading
import time
import uuid
from collections.abc import Callable
from datetime import date, datetime, timedelta

import polars as pl

from app.indicators.pipeline import filter_halt_days
from app.market_time import CN_TZ
from app.services import preferences
from app.services.atomic_io import atomic_write_parquet, optimistic_upsert_parquet
from app.tickflow.capabilities import Cap, CapabilitySet
from app.tickflow.client import get_client
from app.tickflow.rate_limits import resolve_limit
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


def _resolve_daily_provider(
    provider_name: str,
) -> tuple[object | None, bool, str | None]:
    """解析自定义日K源。返回 (provider, should_fallback_to_tickflow, error_msg)。"""
    if provider_name == "tickflow":
        return (None, True, None)
    from app.data_providers import custom as custom_sources
    try:
        if not custom_sources.provider_has_dataset(provider_name, "daily"):
            logger.info(
                "daily provider %s 未声明 daily, fail-closed (no TickFlow mix)",
                provider_name,
            )
            return (None, False, f"{provider_name} did not declare daily")
        provider = custom_sources.get_provider(provider_name)
        return (provider, False, None)
    except Exception as e:  # noqa: BLE001
        # Declared-or-unknown resolve failure: fail-closed. Do not TickFlow-mix.
        return (None, False, str(e))


def daily_provider_is_custom() -> bool:
    """True when daily_data_provider resolves to a declared custom/plugin source.

    Resolve failure of a non-TickFlow selection also returns True so callers
    refuse TickFlow overwrite / public EOD mix. Unreadable prefs are treated
    the same way — do not fail-open to leftover TickFlow.
    """
    try:
        name = preferences.get_daily_data_provider()
    except Exception:  # noqa: BLE001
        return True
    _, fallback, _ = _resolve_daily_provider(name)
    return not fallback


def routed_daily_source_label() -> str:
    """Pipeline ``daily_source`` for the batch path."""
    try:
        if daily_provider_is_custom():
            name = (preferences.get_daily_data_provider() or "").strip().lower()
            return name if name and name != "tickflow" else "custom"
        return "tickflow_batch"
    except Exception:  # noqa: BLE001
        return "none"


def live_daily_persist_allowed() -> bool:
    """Whether TickFlow/custom realtime may write canonical ``kline_daily``.

    Leftover TickFlow daily keeps the live-quote persist path. Declared custom
    daily and unreadable prefs must not be overwritten by a different live
    source — persist a quote snapshot instead.
    """
    try:
        return not daily_provider_is_custom()
    except Exception:  # noqa: BLE001
        return False


def daily_route() -> str:
    """Effective daily write/read route: tickflow | <custom name> | unresolved.

    Explicit leftover TickFlow stays tickflow. Undeclared custom names,
    resolve failures, and unreadable prefs are unresolved.
    """
    try:
        name = (preferences.get_daily_data_provider() or "").strip().lower()
    except Exception:  # noqa: BLE001
        return "unresolved"
    _, fallback, err = _resolve_daily_provider(name)
    if err is not None:
        return "unresolved"
    if fallback:
        return "tickflow"
    return name or "custom"


def daily_cache_usable(df: pl.DataFrame | None, route: str) -> bool:
    """Whether a same-date daily/enriched partition may be used for ``route``.

    Write/merge, status, pipeline, derived writers, and historical HTTP /
    screener reads share this partition-level check. A custom (or leftover
    TickFlow) path must not concat-mix the other source's bars, and must
    not treat leftover parquet as current. Untagged legacy files stay
    valid for leftover TickFlow / public.
    """
    if df is None or getattr(df, "is_empty", lambda: True)():
        return False
    expected = (route or "").strip().lower()
    if not expected or expected == "unresolved":
        return False
    if "route" not in df.columns:
        return expected in {"tickflow", "public"}
    stored = [str(v or "").strip().lower() for v in df["route"].to_list()]
    nonempty = [s for s in stored if s]
    if not nonempty:
        return expected in {"tickflow", "public"}
    if any(s != expected for s in nonempty):
        return False
    if len(nonempty) != len(stored):
        return expected in {"tickflow", "public"}
    return True


def _tag_daily_route(df: pl.DataFrame) -> pl.DataFrame:
    route = daily_route()
    if df is None or getattr(df, "is_empty", lambda: True)():
        return df
    if not route or route == "unresolved":
        return df
    if "route" not in df.columns:
        return df.with_columns(pl.lit(route).alias("route"))
    tokens = pl.col("route").cast(pl.Utf8).fill_null("").str.strip_chars()
    return df.with_columns(
        pl.when(tokens == "").then(pl.lit(route)).otherwise(pl.col("route")).alias("route")
    )


def _incoming_daily_route(df: pl.DataFrame) -> str:
    if df is not None and "route" in df.columns:
        stored = [str(v or "").strip().lower() for v in df["route"].to_list()]
        nonempty = {s for s in stored if s}
        if len(nonempty) == 1:
            return next(iter(nonempty))
    return daily_route()


def daily_partition_usable(path, route: str | None = None) -> bool:
    """Whether one daily/enriched date partition matches the current daily route."""
    from pathlib import Path

    expected = (route if route is not None else daily_route()).strip().lower()
    part = Path(path)
    if not part.is_file():
        return False
    try:
        names = pl.read_parquet_schema(part).names()
        if "route" not in names:
            return expected in {"tickflow", "public"}
        df = pl.read_parquet(part, columns=["route"])
    except Exception as exc:  # noqa: BLE001
        logger.debug("daily partition probe failed %s: %s", part, exc)
        # Leftover TickFlow still sees unreadable date markers; custom does not.
        return expected in {"tickflow", "public"}
    return daily_cache_usable(df, expected)


def usable_daily_partition_dates(
    data_dir,
    route: str | None = None,
    *,
    table: str = "kline_daily",
):
    """Date partitions that belong to the current daily route.

    Status / pipeline / derived writers / HTTP / screener must not treat
    leftover TickFlow partitions as current after a custom switch.
    Leftover TickFlow still sees untagged partitions.
    """
    from pathlib import Path

    expected = route if route is not None else daily_route()
    root = Path(data_dir) / table
    if not root.exists():
        return []
    dates: list[date] = []
    for child in root.iterdir():
        if not child.is_dir() or not child.name.startswith("date="):
            continue
        try:
            day = date.fromisoformat(child.name[5:])
        except ValueError:
            continue
        files = [child / "part.parquet"] if (child / "part.parquet").is_file() else sorted(child.glob("*.parquet"))
        if any(daily_partition_usable(part, expected) for part in files):
            dates.append(day)
    dates.sort()
    return dates


def safe_usable_daily_partition_dates(
    data_dir,
    route: str | None = None,
    *,
    table: str = "kline_daily",
):
    """Like :func:`usable_daily_partition_dates`, but never fail-open.

    Callers that used to ``except: glob date=*`` were serving leftover
    TickFlow calendars after a custom switch. An empty list is the
    fail-closed answer. Leftover TickFlow still sees untagged partitions
    through the happy path.
    """
    try:
        return usable_daily_partition_dates(data_dir, route, table=table)
    except Exception as exc:  # noqa: BLE001
        logger.debug("usable daily dates failed for %s: %s", table, exc)
        return []


def usable_daily_partition_paths(
    data_dir,
    route: str | None = None,
    *,
    table: str = "kline_daily",
):
    """Parquet paths for :func:`safe_usable_daily_partition_dates`.

    Probe / prefs failures return no paths (fail-closed). Callers that
    used to let ``usable_daily_partition_dates`` raise would then except
    and leftover-glob. Leftover TickFlow still sees untagged partitions
    through the happy path.
    """
    from pathlib import Path

    root = Path(data_dir) / table
    paths = []
    for day in safe_usable_daily_partition_dates(data_dir, route, table=table):
        part = root / f"date={day.isoformat()}"
        preferred = part / "part.parquet"
        if preferred.is_file():
            paths.append(preferred)
            continue
        extras = sorted(part.glob("*.parquet"))
        if extras:
            paths.append(extras[0])
    return paths


def scan_usable_daily(
    data_dir,
    route: str | None = None,
    *,
    table: str = "kline_daily",
):
    """Lazy scan of route-usable daily/enriched partitions, or ``None``.

    Backtest / live-agg / mainline / overlay must not glob leftover TickFlow
    files after a custom switch. Leftover TickFlow still sees untagged
    partitions via :func:`usable_daily_partition_paths`.
    """
    paths = usable_daily_partition_paths(data_dir, route, table=table)
    if not paths:
        return None
    return pl.scan_parquet([p.as_posix() for p in paths])


def adj_public_write_allowed() -> bool:
    """Public sina adj / coverage writers may run only for an explicit public adj route."""
    return adj_route() == "public"


def live_enriched_overlay_allowed() -> bool:
    """Whether in-memory live enriched may overlay charts / screener / latest.

    Same gate as live canonical persist: leftover TickFlow daily keeps the
    live overlay. Custom daily and unreadable prefs must not mix a different
    realtime source into ``get_enriched_latest`` consumers.
    """
    return live_daily_persist_allowed()


def _refresh_daily_view(repo: KlineRepository) -> None:
    try:
        d = repo.store.data_dir.as_posix()
        repo.db.execute(
            f"""CREATE OR REPLACE VIEW kline_daily AS
                SELECT * FROM read_parquet('{d}/kline_daily/**/*.parquet', union_by_name=true)"""
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("refresh view failed: %s", e)
    try:
        repo.store.re_gate_catalog_views()
    except Exception as e:  # noqa: BLE001
        logger.warning("re-gate catalog views after daily refresh failed: %s", e)


def _iter_custom_daily_chunks(
    provider: object,
    symbols: list[str],
    start_time: datetime,
    end_time: datetime,
    on_chunk_done: Callable[[int, int], None] | None,
    asset_type: str = "stock",
):
    """Yield normalized daily frames from a custom/plugin provider."""
    kwargs: dict = {
        "symbols": symbols,
        "start_time": start_time,
        "end_time": end_time,
        "asset_type": asset_type,
    }
    if on_chunk_done is not None:
        kwargs["on_chunk_done"] = on_chunk_done
    if hasattr(provider, "iter_daily"):
        chunks = provider.iter_daily(**kwargs)
    else:
        df = provider.get_daily(**kwargs)
        chunks = [df] if df is not None else []
    for raw in chunks:
        if raw is None or getattr(raw, "is_empty", lambda: False)():
            continue
        normalized = _normalize_daily(raw)
        if not normalized.is_empty():
            yield normalized


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

    自定义/插件日K源（``daily_data_provider``）优先于 TickFlow。流式
    ``iter_daily`` 经 staging 落盘，避免全市场结果堆在内存。
    """
    if not symbols:
        return 0

    end_time = end_date or datetime.now()
    start_time = start_date or (end_time - timedelta(days=365))

    try:
        provider_name = preferences.get_daily_data_provider()
    except Exception as e:  # noqa: BLE001
        logger.warning("daily prefs unreadable, fail-closed (no TickFlow mix): %s", e)
        return 0
    provider, fallback, err = _resolve_daily_provider(provider_name)
    if err is not None:
        logger.warning(
            "custom daily provider %s resolution failed, fail-closed (no TickFlow mix): %s",
            provider_name, err,
        )
        return 0
    if not fallback and provider is not None:
        written = _persist_daily_chunks(
            _iter_custom_daily_chunks(
                provider, symbols, start_time, end_time, on_chunk_done,
                asset_type="stock",
            ),
            repo,
        )
        if written:
            _refresh_daily_view(repo)
        return written

    if not capset.has(Cap.KLINE_DAILY_BATCH):
        return 0

    lim = capset.limits(Cap.KLINE_DAILY_BATCH)
    batch_size = lim.batch if lim and lim.batch else 100
    rpm = lim.rpm if lim else None

    df = sync_daily_batch(
        symbols, count=count, batch_size=batch_size, rpm=rpm,
        start_time=start_time, end_time=end_time,
        on_chunk_done=on_chunk_done,
    )

    if df.is_empty():
        return 0

    repo.append_daily(df)
    _refresh_daily_view(repo)
    return df.height


def fetch_routed_daily(
    symbols: list[str],
    *,
    start_time: datetime,
    end_time: datetime,
    asset_type: str = "stock",
    capset: CapabilitySet | None = None,
    count: int | None = None,
    batch_size: int | None = None,
    rpm: int | None = None,
    on_chunk_done: Callable[[int, int], None] | None = None,
) -> pl.DataFrame:
    """Daily bars from ``daily_data_provider`` for stock / index / ETF.

    A custom/plugin source that declares daily is fail-closed: empty or
    stock-only adapters (e.g. Fuyao) must not silently call TickFlow.
    TickFlow still requires ``KLINE_DAILY_BATCH`` when *capset* is given.
    """
    if not symbols:
        return pl.DataFrame()

    try:
        provider_name = preferences.get_daily_data_provider()
    except Exception as e:  # noqa: BLE001
        logger.warning("daily prefs unreadable, fail-closed (no TickFlow mix): %s", e)
        return pl.DataFrame()
    provider, fallback, err = _resolve_daily_provider(provider_name)
    if err is not None:
        logger.warning(
            "custom daily provider %s resolution failed, fail-closed (no TickFlow mix): %s",
            provider_name, err,
        )
        return pl.DataFrame()
    if not fallback and provider is not None:
        frames = list(
            _iter_custom_daily_chunks(
                provider, symbols, start_time, end_time, on_chunk_done,
                asset_type=asset_type,
            )
        )
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="diagonal_relaxed")

    if capset is not None and not capset.has(Cap.KLINE_DAILY_BATCH):
        return pl.DataFrame()
    return sync_daily_batch(
        symbols,
        count=count,
        batch_size=batch_size,
        rpm=rpm,
        start_time=start_time,
        end_time=end_time,
        on_chunk_done=on_chunk_done,
    )


def _persist_daily_chunks(chunks, repo: KlineRepository) -> int:
    """先把流式 provider 结果写入私有 staging,完整取数后再提交正式分区。"""
    staging_base = repo.store.data_dir / ".daily_sync_staging"
    _sweep_stale_daily_staging(staging_base)
    root = staging_base / uuid.uuid4().hex
    written = 0
    try:
        for index, df in enumerate(chunks):
            if df.is_empty():
                continue
            for date_df in df.partition_by("date"):
                dt = date_df["date"][0]
                ds = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
                out = root / f"date={ds}" / f"part-{index}.parquet"
                out.parent.mkdir(parents=True, exist_ok=True)
                date_df.write_parquet(out)
                written += date_df.height

        for date_dir in sorted(root.glob("date=*")):
            files = sorted(date_dir.glob("*.parquet"))
            if files:
                repo.append_daily(pl.scan_parquet(files).collect(engine="streaming"))
    finally:
        shutil.rmtree(root, ignore_errors=True)
        with contextlib.suppress(OSError):
            root.parent.rmdir()

    return written


def _sweep_stale_daily_staging(staging_base, max_age_s: int = 24 * 60 * 60) -> None:
    """清理崩溃遗留的旧同步目录,不碰仍可能活跃的新目录。"""
    if not staging_base.exists():
        return
    cutoff = time.time() - max_age_s
    for run_dir in staging_base.iterdir():
        try:
            if run_dir.is_dir() and run_dir.stat().st_mtime < cutoff:
                shutil.rmtree(run_dir)
        except OSError:
            logger.warning("failed to clean stale daily staging: %s", run_dir)


def sync_daily_by_quotes(repo: KlineRepository) -> int:
    """用实时行情接口拉全市场当日数据,覆写 kline_daily 今天分区。

    一个请求覆盖 ~5500 只股票,比 batch K-line 快几个数量级。
    返回写入的行数。
    Custom / unresolved daily must not be TickFlow-quote overwritten.
    """
    from datetime import date as _date

    from app.tickflow.client import get_client

    if not live_daily_persist_allowed():
        logger.warning(
            "sync_daily_by_quotes skipped: custom/unresolved daily must not TickFlow-mix",
        )
        return 0

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
        if daily_provider_is_custom():
            logger.warning(
                "sync_daily_by_public_quotes skipped: custom/unresolved daily must not public-mix",
            )
            return {"rows": 0, "date": today.isoformat(), "source": "public_quote_eod"}
    except Exception as e:  # noqa: BLE001
        logger.warning("sync_daily_by_public_quotes prefs unreadable, fail-closed: %s", e)
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
    # Re-gate immediately so leftover TickFlow partitions do not become the
    # current SQL surface after a custom daily switch.
    _refresh_daily_view(repo)

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


_BUILTIN_ADJ_PROVIDERS = {"tickflow", "public", "sina", "sina_qfq", "free", ""}


def _try_custom_adj_provider(provider_name: str) -> tuple[object | None, str]:
    """Resolve a plugin/custom adj source.

    Returns (provider, fate):
      - custom: declared adj_factor, use get_adj_factors (fail-closed)
      - skip: undeclared custom name or resolve failure — do not mix
      - builtin: tickflow / public aliases
    """
    name = (provider_name or "").strip().lower()
    if name in _BUILTIN_ADJ_PROVIDERS:
        return None, "builtin"
    from app.data_providers import custom as custom_sources
    try:
        if not custom_sources.provider_has_dataset(name, "adj_factor"):
            logger.info(
                "adj provider %s 未声明 adj_factor, fail-closed (no TickFlow/public mix)",
                name,
            )
            return None, "skip"
        return custom_sources.get_provider(name), "custom"
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "adj provider %s 解析失败, 跳过 (不回退混源): %s", name, e,
        )
        return None, "skip"


def adj_live_fetch_allowed(capset: CapabilitySet | None) -> bool:
    """Whether live HTTP daily may fetch adj factors for the configured source."""
    try:
        provider_name = preferences.get_adj_factor_provider()
        if preferences.is_public_adj_factor_provider(provider_name):
            return True
        custom, fate = _try_custom_adj_provider(provider_name)
        if fate == "custom" and custom is not None:
            return True
        if fate == "skip":
            return False
        # leftover TickFlow: TickFlow only when entitled. No silent sina qfq.
        return bool(capset and capset.has(Cap.ADJ_FACTOR))
    except Exception:  # noqa: BLE001
        # Prefs unreadable: do not assume leftover TickFlow / public sina.
        return False


def adj_route() -> str:
    """Effective adj write/read route: public | tickflow | <custom name> | unresolved.

    Explicit leftover TickFlow / public aliases stay those tokens.
    Undeclared custom names, resolve failures, and unreadable prefs are unresolved.
    """
    try:
        name = (preferences.get_adj_factor_provider() or "").strip().lower()
    except Exception:  # noqa: BLE001
        return "unresolved"
    try:
        if preferences.is_public_adj_factor_provider(name):
            return "public"
    except Exception:  # noqa: BLE001
        return "unresolved"
    custom, fate = _try_custom_adj_provider(name)
    if fate == "skip":
        return "unresolved"
    if fate == "custom":
        return name or "custom"
    return "tickflow"


def adj_cache_usable(df: pl.DataFrame | None, route: str) -> bool:
    """Whether on-disk adj factors may be served for the current route.

    Custom / unresolved never reuse untagged TickFlow or public files.
    Tagged files must match the current route — leftover TickFlow no
    longer serves public-sina tags. Untagged legacy files stay valid
    for leftover TickFlow / public only.
    """
    if df is None or getattr(df, "is_empty", lambda: True)():
        return False
    expected = (route or "").strip().lower()
    if not expected or expected == "unresolved":
        return False
    if "route" not in df.columns:
        return expected in {"tickflow", "public"}
    stored = [str(v or "").strip().lower() for v in df["route"].to_list()]
    nonempty = [s for s in stored if s]
    if not nonempty:
        return expected in {"tickflow", "public"}
    allowed = {expected}
    if any(s not in allowed for s in nonempty):
        return False
    if len(nonempty) != len(stored):
        return expected in {"tickflow", "public"}
    return True


def _tag_adj_route(df: pl.DataFrame) -> pl.DataFrame:
    route = adj_route()
    if df is None or getattr(df, "is_empty", lambda: True)():
        return df
    if not route or route == "unresolved" or "route" in df.columns:
        return df
    return df.with_columns(pl.lit(route).alias("route"))


def adj_coverage_start(data_dir, asset_type: str, fallback: datetime) -> datetime:
    """Incremental adj window start from gated local coverage.

    Stale TickFlow/public files under a custom/unresolved route must not
    advance the start date (that would skip a full custom backfill).
    """
    df = get_adj_factor_df(data_dir, asset_type=asset_type)
    if df is None or getattr(df, "is_empty", lambda: True)() or "trade_date" not in df.columns:
        return fallback
    max_date = df["trade_date"].max()
    if max_date is None:
        return fallback
    if isinstance(max_date, str):
        try:
            max_date = date.fromisoformat(max_date)
        except ValueError:
            return fallback
    if isinstance(max_date, datetime):
        max_date = max_date.date()
    if not isinstance(max_date, date):
        return fallback
    return datetime.combine(max_date, datetime.min.time())


def get_adj_factor_df(data_dir, asset_type: str = "stock") -> pl.DataFrame:
    """Read local adj parquet, refusing stale files after an adj-source switch."""
    from pathlib import Path

    factor_dir = "adj_factor_etf" if asset_type == "etf" else "adj_factor"
    path = Path(data_dir) / factor_dir / "all.parquet"
    empty = pl.DataFrame(
        schema={"symbol": pl.Utf8, "trade_date": pl.Date, "ex_factor": pl.Float64}
    )
    if not path.exists():
        return empty
    try:
        df = pl.read_parquet(path)
    except Exception as e:  # noqa: BLE001
        logger.warning("读取 %s 失败: %s", factor_dir, e)
        return empty
    if "trade_date" in df.columns and df.schema["trade_date"] != pl.Date:
        df = df.with_columns(pl.col("trade_date").cast(pl.Date, strict=False))
    route = adj_route()
    if not adj_cache_usable(df, route):
        logger.info("skip stale %s for route=%s", factor_dir, route)
        return empty
    if "route" in df.columns:
        return df.drop("route")
    return df


def _persist_adj_factor_df(
    new_data: pl.DataFrame,
    repo: KlineRepository,
    asset_type: str,
) -> tuple[int, list[str]]:
    if new_data.is_empty():
        return 0, []
    new_data = _tag_adj_route(new_data)
    affected = new_data["symbol"].unique().to_list()
    factor_dir = "adj_factor_etf" if asset_type == "etf" else "adj_factor"
    out = repo.store.data_dir / factor_dir / "all.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.exists():
        existing = pl.read_parquet(out)
        if not adj_cache_usable(existing, adj_route()):
            existing = new_data.head(0)
        before = existing.height
        merged = pl.concat([existing, new_data], how="diagonal_relaxed").unique(
            subset=["symbol", "trade_date"], keep="last",
        ).sort(["symbol", "trade_date"])
        atomic_write_parquet(merged, out)
        added = merged.height - before
        logger.info(
            "adj_factor merged: %d total (+%d new), %d/%d symbols",
            merged.height, added, new_data.height, len(affected),
        )
        return added, affected
    atomic_write_parquet(new_data.sort(["symbol", "trade_date"]), out)
    logger.info("adj_factor synced: %d rows (%d symbols)", new_data.height, len(affected))
    return new_data.height, affected


def _sync_public_adj_factor(
    symbols: list[str],
    repo: KlineRepository,
    start_time: datetime | None,
    end_time: datetime | None,
    on_chunk_done: Callable[[int, int], None] | None,
    asset_type: str,
) -> tuple[int, list[str]]:
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


def sync_adj_factor(symbols: list[str], repo: KlineRepository,
                    capset: CapabilitySet,
                    start_time: datetime | None = None,
                    end_time: datetime | None = None,
                    on_chunk_done: Callable[[int, int], None] | None = None,
                    asset_type: str = "stock") -> tuple[int, list[str]]:
    """同步除权因子。

    - 声明了 adj_factor 的自定义/插件源：``get_adj_factors``，fail-closed
    - 默认 TickFlow Starter+：`tf.klines.ex_factors`（需 Cap.ADJ_FACTOR）
    - 当 preferences.adj_factor_provider ∈ {public,sina,sina_qfq,free} 时：
      走 free_sources.adj_factor_public（新浪 qfq.js），**不依赖** Cap.ADJ_FACTOR
    - leftover TickFlow 且无 Cap.ADJ_FACTOR：空结果（不再静默公开新浪 qfq）
    - 未声明自定义 adj：fail-closed，不混 TickFlow / 公开新浪

    支持增量: 传 start_time/end_time 只保留该时间范围内的新除权事件。
    返回 (写入行数, 受影响的 symbol 列表) — 供 enriched 局部重算使用。
    """
    if not symbols:
        return 0, []

    try:
        provider_name = preferences.get_adj_factor_provider()
        use_public = preferences.is_public_adj_factor_provider()
    except Exception:  # noqa: BLE001
        logger.warning("adj prefs unreadable, fail-closed (no TickFlow/public mix)")
        return 0, []

    if use_public:
        return _sync_public_adj_factor(
            symbols, repo, start_time, end_time, on_chunk_done, asset_type,
        )

    custom, fate = _try_custom_adj_provider(provider_name)
    if fate == "skip":
        return 0, []
    if fate == "custom" and custom is not None:
        try:
            try:
                raw = custom.get_adj_factors(
                    symbols, start_time, end_time, asset_type,
                    on_chunk_done=on_chunk_done,
                )
            except TypeError:
                raw = custom.get_adj_factors(symbols, start_time, end_time, asset_type)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "custom adj provider %s 调用失败, fail-closed: %s", provider_name, e,
            )
            return 0, []
        return _persist_adj_factor_df(_normalize_adj_factor(raw), repo, asset_type)

    if not capset.has(Cap.ADJ_FACTOR):
        # Leftover TickFlow none/free cannot serve factors. Silent public
        # sina qfq is closed; explicit public/sina* is handled above.
        logger.info("leftover TickFlow adj without Cap.ADJ_FACTOR, fail-closed (no sina mix)")
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
    return _persist_adj_factor_df(new_data, repo, asset_type)


# ===== 分钟 K 同步 =====

CANONICAL_MINUTE_COLS = [
    "symbol", "datetime", "open", "high", "low", "close", "volume", "amount",
]

_minute_partition_lock = threading.Lock()


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


def _drop_null_datetime(existing: pl.DataFrame) -> pl.DataFrame:
    if "datetime" in existing.columns:
        return existing.filter(pl.col("datetime").is_not_null())
    return existing


def _incoming_minute_route(df: pl.DataFrame) -> str:
    if df is not None and "route" in df.columns:
        stored = [str(v or "").strip().lower() for v in df["route"].to_list()]
        nonempty = {s for s in stored if s}
        if len(nonempty) == 1:
            return next(iter(nonempty))
    return minute_route()


def _prepare_existing_minute(existing: pl.DataFrame, incoming_route: str) -> pl.DataFrame:
    existing = _drop_null_datetime(existing)
    if existing is None or getattr(existing, "is_empty", lambda: True)():
        return existing
    if not minute_cache_usable(existing, incoming_route):
        logger.info("replace stale minute partition for route=%s", incoming_route)
        return existing.head(0)
    return existing


def filter_minute_cache(df: pl.DataFrame | None, route: str | None = None) -> pl.DataFrame:
    """Return ``df`` only when it matches the current minute route."""
    if df is None or getattr(df, "is_empty", lambda: True)():
        return df if df is not None else pl.DataFrame()
    expected = (route if route is not None else minute_route()).strip().lower()
    if not minute_cache_usable(df, expected):
        return df.head(0)
    return df


def filter_daily_cache(df: pl.DataFrame | None, route: str | None = None) -> pl.DataFrame:
    """Keep daily/enriched rows that match the current daily route.

    HTTP / screener / in-memory cache reads use row-level filtering so a
    mixed-date scan can drop leftover TickFlow partitions after a custom
    switch without failing the whole frame. Untagged rows stay visible
    only for leftover TickFlow / public.
    """
    if df is None or getattr(df, "is_empty", lambda: True)():
        return df if df is not None else pl.DataFrame()
    expected = (route if route is not None else daily_route()).strip().lower()
    if not expected or expected == "unresolved":
        return df.head(0)
    if "route" not in df.columns:
        return df if expected in {"tickflow", "public"} else df.head(0)
    tokens = pl.col("route").cast(pl.Utf8).fill_null("").str.strip_chars().str.to_lowercase()
    if expected in {"tickflow", "public"}:
        return df.filter((tokens == expected) | (tokens == ""))
    return df.filter(tokens == expected)


def _with_minute_route(df: pl.DataFrame, route: str | None = None) -> pl.DataFrame:
    """Stamp ``route`` on a minute frame before persist. Signature of
    ``_write_minute_partition`` stays ``(df, dir)`` so existing test mocks
    keep working.
    """
    if df is None or getattr(df, "is_empty", lambda: True)():
        return df
    token = (route or "").strip().lower()
    if not token or token == "unresolved" or "route" in df.columns:
        return df
    return df.with_columns(pl.lit(token).alias("route"))


def _write_minute_partition(df: pl.DataFrame, minute_dir) -> int:
    """按 _trade_date 分区落盘分钟 K (读旧→concat→unique→原子写)。返回写入行数。

    persist_historical_minute 与 minute-batch 共用本函数 + atomic_write_parquet,
    发布侧统一走模块级 _minute_partition_lock 的乐观重试, 不另开写链。
    Callers stamp ``route`` via ``_with_minute_route`` so a later provider
    switch does not serve stale TickFlow/public/custom parquet.
    """
    from pathlib import Path

    if df is None or df.is_empty():
        return 0
    minute_dir = Path(minute_dir)
    if "datetime" not in df.columns:
        return 0
    df = df.with_columns(pl.col("datetime").dt.date().alias("_trade_date"))
    written = 0
    for day_df in df.partition_by("_trade_date"):
        trade_date = day_df["_trade_date"][0]
        incoming = day_df.drop("_trade_date")
        expected = _incoming_minute_route(incoming)
        out = minute_dir / f"date={trade_date}" / "part.parquet"
        written += optimistic_upsert_parquet(
            incoming,
            out,
            keys=["symbol", "datetime"],
            sort_by=["symbol", "datetime"],
            lock=_minute_partition_lock,
            prepare_existing=lambda existing, route=expected: _prepare_existing_minute(
                existing, route,
            ),
        )
    return written


def _emit_chunk_done(cb, current: int, total: int, label: str = "") -> None:
    """兼容 2 参 / 3 参进度回调。"""
    if not cb:
        return
    try:
        cb(current, total, label)
    except TypeError:
        cb(current, total)


def _allow_tickflow_minute_batch(capset: CapabilitySet | None) -> bool:
    """是否允许构造/请求 TickFlow 批量分钟。

    capset is None: 旧内部直接调用，保持兼容。
    HTTP 必须传入 CapabilitySet（缺 capset 时为空集），不得借 None 绕过。
    """
    return capset is None or capset.has(Cap.KLINE_MINUTE_BATCH)


def sync_minute_batch(
    symbols: list[str],
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    count: int | None = None,
    batch_size: int | None = None,
    rpm: int | None = None,
    on_chunk_done: Callable[..., None] | None = None,
    segment_trading_days: int = 20,
    on_segment: Callable[[pl.DataFrame], None] | None = None,
    asset_type: str = "stock",
    capset: CapabilitySet | None = None,
) -> pl.DataFrame:
    """批量拉取多股分钟 K。

    优先自定义分钟源。自定义成功且传了 on_segment 时走流式落盘并返回空 df;
    未传 on_segment 时原样返回 df (实时补拉)。
    自定义失败后，仅当 capset 具有 KLINE_MINUTE_BATCH（或内部调用 capset=None）
    才回退 TickFlow；空 CapabilitySet / 无资格不得隐式兜底。
    """
    df, fallback = _try_custom_minute(
        symbols, start_time=start_time, end_time=end_time,
        asset_type=asset_type, freq="1m", on_chunk_done=on_chunk_done,
    )
    if not fallback:
        df = df if df is not None else pl.DataFrame()
        if on_segment and not df.is_empty():
            on_segment(df)
            return pl.DataFrame()
        return df

    if not _allow_tickflow_minute_batch(capset):
        return pl.DataFrame()

    tf = get_client()
    out: list[pl.DataFrame] = []
    interval = (60.0 / rpm) if rpm else 0

    if batch_size is None:
        chunks = [symbols]
    else:
        chunks = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]

    for i, chunk in enumerate(chunks):
        if i > 0 and interval > 0 and rpm and len(chunks) > rpm:
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

        seg_out: list[pl.DataFrame] = []
        if isinstance(raw, dict):
            for sym, sub in raw.items():
                if sub is None or len(sub) == 0:
                    continue
                seg_out.append(_normalize_minute(sub, default_symbol=sym))
        elif raw is not None and len(raw) > 0:
            seg_out.append(_normalize_minute(raw))

        if seg_out:
            seg_df = pl.concat(seg_out, how="diagonal_relaxed")
            if on_segment:
                on_segment(seg_df)
            else:
                out.append(seg_df)

        _emit_chunk_done(on_chunk_done, i + 1, len(chunks), "")

    if on_segment or not out:
        return pl.DataFrame()
    return pl.concat(out, how="diagonal_relaxed")


def intraday_monitor_support(capset: CapabilitySet | None) -> dict[str, object]:
    """返回分时信号监控可用的数据能力和单轮标的上限。"""
    try:
        provider_name = preferences.get_minute_data_provider()
    except Exception as e:  # noqa: BLE001
        logger.warning("minute prefs unreadable while checking monitor support: %s", e)
        return {
            "available": False, "source": None, "max_symbols": 0,
            "reason": "分钟数据源偏好不可读",
        }
    _, fallback, error = _resolve_minute_provider(provider_name)
    if error is not None:
        logger.warning("minute provider resolution failed while checking monitor support: %s", error)
        return {
            "available": False, "source": None, "max_symbols": 0,
            "reason": "分钟数据源解析失败",
        }
    if not fallback:
        return {
            "available": True, "source": "custom_minute", "max_symbols": 100,
            "reason": "使用已配置的分钟数据插件",
        }
    if capset is None:
        return {
            "available": False, "source": None, "max_symbols": 0,
            "reason": "需要分钟 K 或日内分时数据权限",
        }
    for cap, source in (
        (Cap.INTRADAY_BATCH, "intraday_batch"),
        (Cap.KLINE_MINUTE_BATCH, "minute_batch"),
    ):
        if capset.has(cap):
            limits = capset.limits(cap)
            return {
                "available": True, "source": source,
                "max_symbols": max(1, int(limits.batch or 100)) if limits else 100,
                "reason": "日内分时数据可用" if cap == Cap.INTRADAY_BATCH else "分钟 K 数据可用",
            }
    for cap, source in (
        (Cap.INTRADAY, "intraday_single"),
        (Cap.KLINE_MINUTE_BY_SYMBOL, "minute_single"),
    ):
        if capset.has(cap):
            return {
                "available": True, "source": source, "max_symbols": 1,
                "reason": "当前权限仅支持单标的分时监控",
            }
    return {
        "available": False, "source": None, "max_symbols": 0,
        "reason": "需要分钟 K 或日内分时数据权限",
    }


def _normalize_intraday_monitor_payload(raw, default_symbol: str | None = None) -> pl.DataFrame:
    """Normalize TickFlow CompactKlineData / DataFrame into canonical minute cols."""
    if raw is None:
        return pl.DataFrame()
    if isinstance(raw, dict) and "timestamp" in raw:
        raw = pl.DataFrame(raw)
    return _normalize_minute(raw, default_symbol=default_symbol)


def fetch_intraday_monitor_batch(
    symbols: list[str],
    capset: CapabilitySet | None,
    *,
    now: datetime | None = None,
) -> pl.DataFrame:
    """Fetch today's minute bars for monitor-signal symbols.

    Custom minute (declared) is first. Call failure still falls back to TickFlow
    when the capset entitles INTRADAY_BATCH / minute batch — existing contract.
    Leftover TickFlow + free (no cap) returns empty; no public mix.
    """
    if not symbols:
        return pl.DataFrame()

    clock = now or datetime.now(tz=CN_TZ)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=CN_TZ)
    trade_date = clock.astimezone(CN_TZ).date()
    start_time = datetime(
        trade_date.year, trade_date.month, trade_date.day, 9, 25, 0, tzinfo=CN_TZ,
    )
    end_time = datetime(
        trade_date.year, trade_date.month, trade_date.day, 15, 5, 0, tzinfo=CN_TZ,
    )

    df, fallback = _try_custom_minute(
        list(symbols),
        start_time=start_time,
        end_time=end_time,
        asset_type="stock",
        freq="1m",
    )
    if not fallback:
        out = df if df is not None else pl.DataFrame()
        return filter_minute_trade_date(out, trade_date) if not out.is_empty() else out

    allow_intraday = capset is not None and capset.has(Cap.INTRADAY_BATCH)
    allow_minute = capset is None or capset.has(Cap.KLINE_MINUTE_BATCH)
    if not allow_intraday and not allow_minute:
        return pl.DataFrame()

    tf = get_client()
    frames: list[pl.DataFrame] = []
    if allow_intraday:
        limits = capset.limits(Cap.INTRADAY_BATCH) if capset is not None else None
        batch_size = max(1, int(limits.batch or 100)) if limits else 100
        raw = tf.klines.intraday_batch(
            list(symbols),
            count=300,
            as_dataframe=False,
            show_progress=False,
            batch_size=batch_size,
        )
        if isinstance(raw, dict):
            for sym, payload in raw.items():
                normalized = _normalize_intraday_monitor_payload(payload, default_symbol=sym)
                if not normalized.is_empty():
                    frames.append(normalized)
        elif raw is not None:
            normalized = _normalize_intraday_monitor_payload(raw)
            if not normalized.is_empty():
                frames.append(normalized)
    else:
        raw = tf.klines.batch(
            list(symbols),
            period="1m",
            start_time=_datetime_to_ms(start_time),
            end_time=_datetime_to_ms(end_time),
            count=10000,
            as_dataframe=True,
            show_progress=False,
        )
        if isinstance(raw, dict):
            for sym, payload in raw.items():
                normalized = _normalize_minute(payload, default_symbol=sym)
                if not normalized.is_empty():
                    frames.append(normalized)
        elif raw is not None:
            normalized = _normalize_minute(raw)
            if not normalized.is_empty():
                frames.append(normalized)

    if not frames:
        return pl.DataFrame()
    out = pl.concat(frames, how="diagonal_relaxed")
    keep = [c for c in CANONICAL_MINUTE_COLS if c in out.columns]
    out = out.select(keep)
    return filter_minute_trade_date(out, trade_date) if "datetime" in out.columns else out


def filter_minute_trade_date(df: pl.DataFrame, trade_date: date) -> pl.DataFrame:
    """Keep only rows that can be proven to belong to ``trade_date``."""
    if df.is_empty():
        return df
    if "datetime" not in df.columns:
        logger.warning("minute rows missing datetime; discard for requested date %s", trade_date)
        return df.head(0)

    wanted = trade_date.isoformat()
    date_text = pl.col("datetime").cast(pl.Utf8).str.slice(0, 10)
    filtered = df.filter(date_text == wanted)
    if filtered.height != df.height:
        actual_dates = (
            df.select(date_text.alias("date"))
            .unique()
            .sort("date")
            .get_column("date")
            .to_list()
        )
        logger.warning(
            "discard minute rows from unexpected trade date: requested=%s actual=%s",
            wanted,
            actual_dates,
        )
    return filtered


def _resolve_minute_provider(
    provider_name: str,
) -> tuple[object | None, bool, str | None]:
    """解析自定义分钟源。返回 (provider, should_fallback_to_tickflow, error_msg)。"""
    if provider_name == "tickflow":
        return (None, True, None)
    from app.data_providers import custom as custom_sources
    try:
        if not custom_sources.provider_has_dataset(provider_name, "minute"):
            logger.info(
                "minute provider %s 未声明 minute, fail-closed (no TickFlow mix)",
                provider_name,
            )
            return (None, False, f"{provider_name} did not declare minute")
        provider = custom_sources.get_provider(provider_name)
        return (provider, False, None)
    except Exception as e:  # noqa: BLE001
        # Declared-or-unknown resolve failure: fail-closed. Do not TickFlow-mix.
        return (None, False, str(e))


def minute_provider_is_custom() -> bool:
    """True when minute_data_provider resolves to a declared custom/plugin source."""
    try:
        name = preferences.get_minute_data_provider()
    except Exception:  # noqa: BLE001
        return True
    _, fallback, err = _resolve_minute_provider(name)
    return (not fallback) and err is None


def minute_may_use_leftover_public() -> bool:
    """Leftover TickFlow / undeclared minute may use public or TDX single-symbol view.

    Declared custom (including resolve failure) and unreadable prefs must not.
    """
    try:
        name = preferences.get_minute_data_provider()
    except Exception:  # noqa: BLE001
        return False
    _, fallback, err = _resolve_minute_provider(name)
    return bool(fallback) and err is None


def minute_route() -> str:
    """Effective minute write/read route: public | tickflow | <custom name> | unresolved.

    Explicit leftover TickFlow stays tickflow. Undeclared custom names,
    resolve failures, and unreadable prefs are unresolved — never serve
    stale cache as if it belonged to the current source.
    """
    try:
        name = (preferences.get_minute_data_provider() or "").strip().lower()
    except Exception:  # noqa: BLE001
        return "unresolved"
    if name == "public":
        return "public"
    _, fallback, err = _resolve_minute_provider(name)
    if err is not None:
        return "unresolved"
    if fallback:
        return "tickflow"
    return name or "custom"


def full_minute_route() -> str:
    """Effective full-minute write/read route (same tokens as ``minute_route``)."""
    try:
        name = (preferences.get_full_minute_data_provider() or "").strip().lower()
    except Exception:  # noqa: BLE001
        return "unresolved"
    if name == "public":
        return "public"
    _, fallback, err = _resolve_full_minute_provider(name)
    if err is not None:
        return "unresolved"
    if fallback:
        return "tickflow"
    return name or "custom"


def full_minute_may_use_minute_fallback() -> bool:
    """Leftover TickFlow / undeclared full_minute may fall back to minute batch.

    Declared custom full_minute and unreadable prefs must not mix
    ``minute_data_provider`` (including TickFlow) into monitor signals.
    """
    try:
        name = preferences.get_full_minute_data_provider()
    except Exception:  # noqa: BLE001
        return False
    _, fallback, err = _resolve_full_minute_provider(name)
    return bool(fallback) and err is None


def minute_cache_usable(df: pl.DataFrame | None, route: str) -> bool:
    """Whether on-disk minute bars may be served for the current route.

    Tagged files must match ``route``. Untagged legacy files are only valid
    for leftover TickFlow / public. Custom / unresolved never reuse a
    previous source's parquet.
    """
    if df is None or getattr(df, "is_empty", lambda: True)():
        return False
    expected = (route or "").strip().lower()
    if not expected or expected == "unresolved":
        return False
    if "route" not in df.columns:
        return expected in {"tickflow", "public"}
    stored = [str(v or "").strip().lower() for v in df["route"].to_list()]
    nonempty = [s for s in stored if s]
    if not nonempty:
        return expected in {"tickflow", "public"}
    if any(s != expected for s in nonempty):
        return False
    if len(nonempty) != len(stored):
        return expected in {"tickflow", "public"}
    return True


def minute_partition_usable(path, route: str | None = None) -> bool:
    """Whether one minute date partition matches the current minute route."""
    from pathlib import Path

    expected = (route if route is not None else minute_route()).strip().lower()
    part = Path(path)
    if not part.is_file():
        return False
    try:
        names = pl.read_parquet_schema(part).names()
        if "route" not in names:
            return expected in {"tickflow", "public"}
        df = pl.read_parquet(part, columns=["route"])
    except Exception as exc:  # noqa: BLE001
        logger.debug("minute partition probe failed %s: %s", part, exc)
        return False
    return minute_cache_usable(df, expected)


def usable_minute_partition_dates(data_dir, route: str | None = None, *, asset_type: str = "stock"):
    """Date partitions that belong to the current minute route.

    Stale TickFlow/public files after a custom switch are omitted so coverage
    / incremental start / HTTP extend cannot treat leftover parquet as current.
    Leftover TickFlow still sees untagged partitions.
    """
    from pathlib import Path

    expected = route if route is not None else minute_route()
    subdir = "kline_etf_minute" if asset_type == "etf" else "kline_minute"
    root = Path(data_dir) / subdir
    if not root.exists():
        return []
    dates: list[date] = []
    for child in root.iterdir():
        if not child.is_dir() or not child.name.startswith("date="):
            continue
        try:
            day = date.fromisoformat(child.name[5:])
        except ValueError:
            continue
        part = child / "part.parquet"
        if minute_partition_usable(part, expected):
            dates.append(day)
    dates.sort()
    return dates


def safe_usable_minute_partition_dates(
    data_dir,
    route: str | None = None,
    *,
    asset_type: str = "stock",
):
    """Like :func:`usable_minute_partition_dates`, but never fail-open."""
    try:
        return usable_minute_partition_dates(data_dir, route, asset_type=asset_type)
    except Exception as exc:  # noqa: BLE001
        logger.debug("usable minute dates failed: %s", exc)
        return []


def latest_usable_minute_datetime(data_dir, route: str | None = None, *, asset_type: str = "stock"):
    """Newest datetime in a route-usable minute partition, or None."""
    from pathlib import Path

    expected = route if route is not None else minute_route()
    dates = safe_usable_minute_partition_dates(data_dir, expected, asset_type=asset_type)
    if not dates:
        return None
    subdir = "kline_etf_minute" if asset_type == "etf" else "kline_minute"
    part = Path(data_dir) / subdir / f"date={dates[-1].isoformat()}" / "part.parquet"
    try:
        df = pl.read_parquet(part, columns=["datetime"])
    except Exception as exc:  # noqa: BLE001
        logger.debug("usable minute datetime read failed %s: %s", part, exc)
        return None
    if df.is_empty() or "datetime" not in df.columns:
        return None
    mx = df["datetime"].max()
    if mx is None:
        return None
    if isinstance(mx, datetime):
        return mx
    try:
        return datetime.fromisoformat(str(mx))
    except ValueError:
        return None


def persist_routed_minute_bars(
    df: pl.DataFrame,
    repo: KlineRepository,
    *,
    asset_type: str = "stock",
) -> int:
    """Persist minute bars with route tags and re-gate DuckDB views.

    HTTP extend-history used to concat into the date partition and
    ``CREATE VIEW`` without the catalog gate — custom minute then mixed
    leftover TickFlow bars and SQL saw the stale files again.
    """
    if df is None or getattr(df, "is_empty", lambda: True)():
        return 0
    minute_dir = repo.store.data_dir / (
        "kline_etf_minute" if asset_type == "etf" else "kline_minute"
    )
    write_lock = getattr(repo, "_write_lock", None) or _minute_partition_lock
    with write_lock:
        written = _write_minute_partition(_with_minute_route(df, minute_route()), minute_dir)
    if written:
        repo.refresh_minute_views()
    return written


def minute_sync_allowed(capset: CapabilitySet | None) -> bool:
    """Whether pipeline / HTTP may start a minute pull for the configured source.

    Declared custom resolve failure is fail-closed even when TickFlow has
    minute batch. Leftover TickFlow still requires ``KLINE_MINUTE_BATCH``.
    """
    try:
        name = preferences.get_minute_data_provider()
    except Exception:  # noqa: BLE001
        return False
    _, fallback, error = _resolve_minute_provider(name)
    if error is not None:
        return False
    if not fallback:
        return True
    return capset is not None and capset.has(Cap.KLINE_MINUTE_BATCH)


def _resolve_full_minute_provider(
    provider_name: str,
) -> tuple[object | None, bool, str | None]:
    """解析全量分钟源。返回 (provider, should_fallback_to_tickflow, error_msg)。

    未声明 full_minute fail-closed，不混 TickFlow。
    解析异常同样 fail-closed。
    """
    if provider_name == "tickflow":
        return (None, True, None)
    from app.data_providers import custom as custom_sources
    try:
        if not custom_sources.provider_has_dataset(provider_name, "full_minute"):
            logger.info(
                "full_minute provider %s 未声明 full_minute, fail-closed (no TickFlow mix)",
                provider_name,
            )
            return (None, False, f"{provider_name} did not declare full_minute")
        provider = custom_sources.get_provider(provider_name)
        return (provider, False, None)
    except Exception as e:  # noqa: BLE001
        return (None, False, str(e))


_BURST_SYSTEMIC_FAIL_CHUNKS = 4


def _frames_from_intraday_payload(raw) -> list[pl.DataFrame]:
    """Normalize TickFlow CompactKlineData / {symbol: payload} / DataFrame."""
    frames: list[pl.DataFrame] = []
    if raw is None:
        return frames
    if isinstance(raw, dict):
        values = list(raw.values())
        looks_like_symbol_map = bool(values) and all(
            v is None or isinstance(v, (dict, pl.DataFrame)) or hasattr(v, "columns")
            for v in values
        ) and "timestamp" not in raw
        if looks_like_symbol_map:
            for sym, payload in raw.items():
                normalized = _normalize_intraday_monitor_payload(payload, default_symbol=sym)
                if not normalized.is_empty():
                    frames.append(normalized)
            return frames
        normalized = _normalize_intraday_monitor_payload(raw)
        if not normalized.is_empty():
            frames.append(normalized)
        return frames
    normalized = _normalize_intraday_monitor_payload(raw)
    if not normalized.is_empty():
        frames.append(normalized)
    return frames


def fetch_intraday_full_market_burst(
    symbols: list[str],
    capset: CapabilitySet | None,
    *,
    count: int = 300,
) -> tuple[pl.DataFrame, int]:
    """TickFlow full-market repair pulse with per-chunk isolation.

    A failed chunk is retried once unless more than four chunks failed
    (systemic overload — skip retries). No public mix.
    """
    if not symbols:
        return pl.DataFrame(), 0
    if capset is not None and not capset.has(Cap.INTRADAY_BATCH):
        return pl.DataFrame(), 0

    limits = capset.limits(Cap.INTRADAY_BATCH) if capset is not None else None
    batch_size = max(1, int(limits.batch or 100)) if limits else 100
    chunks = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
    tf = get_client()
    frames: list[pl.DataFrame] = []
    requests = 0
    failed: list[list[str]] = []

    def _pull(chunk: list[str]) -> None:
        nonlocal requests
        requests += 1
        raw = tf.klines.intraday_batch(
            list(chunk),
            count=count,
            as_dataframe=False,
            show_progress=False,
            batch_size=len(chunk),
        )
        frames.extend(_frames_from_intraday_payload(raw))

    for chunk in chunks:
        try:
            _pull(chunk)
        except Exception as e:  # noqa: BLE001
            logger.warning("intraday burst chunk failed (%d symbols): %s", len(chunk), e)
            failed.append(chunk)

    if failed and len(failed) <= _BURST_SYSTEMIC_FAIL_CHUNKS:
        for chunk in failed:
            try:
                _pull(chunk)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "intraday burst retry failed (%d symbols): %s", len(chunk), e,
                )

    if not frames:
        return pl.DataFrame(), requests
    out = pl.concat(frames, how="diagonal_relaxed")
    keep = [c for c in CANONICAL_MINUTE_COLS if c in out.columns]
    return out.select(keep), requests


def fetch_intraday_universe_increment(*, count: int = 3) -> tuple[pl.DataFrame, int]:
    """TickFlow universe increment: latest N bars, one request. No public mix."""
    try:
        tf = get_client()
    except Exception as e:  # noqa: BLE001
        logger.warning("intraday universe increment: no client: %s", e)
        return pl.DataFrame(), 0
    fn = getattr(getattr(tf, "klines", None), "intraday_universe", None)
    if not callable(fn):
        logger.warning("TickFlow klines.intraday_universe missing, skip increment")
        return pl.DataFrame(), 0
    try:
        raw = fn(count=count, as_dataframe=True, show_progress=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("intraday universe increment failed: %s", e)
        return pl.DataFrame(), 1
    frames = _frames_from_intraday_payload(raw)
    if frames:
        out = pl.concat(frames, how="diagonal_relaxed")
        keep = [c for c in CANONICAL_MINUTE_COLS if c in out.columns]
        return out.select(keep), 1
    if isinstance(raw, pl.DataFrame) and not raw.is_empty():
        return _normalize_minute(raw), 1
    return pl.DataFrame(), 1


def _coerce_intraday_frame(raw) -> pl.DataFrame:
    if raw is None or getattr(raw, "is_empty", lambda: False)():
        return pl.DataFrame()
    if isinstance(raw, pl.DataFrame) and "datetime" in raw.columns:
        keep = [c for c in CANONICAL_MINUTE_COLS if c in raw.columns]
        return raw.select(keep) if keep else raw
    frames = _frames_from_intraday_payload(raw)
    if frames:
        out = pl.concat(frames, how="diagonal_relaxed")
        keep = [c for c in CANONICAL_MINUTE_COLS if c in out.columns]
        return out.select(keep)
    return _normalize_minute(raw)


def fetch_intraday_custom_batch(
    provider: object,
    provider_name: str,
    symbols: list[str],
    *,
    count: int = 300,
) -> tuple[pl.DataFrame, int]:
    """Custom full_minute repair round. Fail-closed: no TickFlow / public mix.

    Prefer ``get_intraday_batch``; otherwise today's ``get_minute`` window.
    """
    if not symbols:
        return pl.DataFrame(), 0
    batch_fn = getattr(provider, "get_intraday_batch", None)
    if callable(batch_fn):
        try:
            try:
                raw = batch_fn(symbols, count=count, asset_type="stock")
            except TypeError:
                raw = batch_fn(symbols)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "custom full_minute %s get_intraday_batch failed, fail-closed: %s",
                provider_name, e,
            )
            return pl.DataFrame(), 1
        return _coerce_intraday_frame(raw), 1

    minute_fn = getattr(provider, "get_minute", None)
    if not callable(minute_fn):
        logger.warning(
            "custom full_minute %s has neither get_intraday_batch nor get_minute",
            provider_name,
        )
        return pl.DataFrame(), 0

    clock = datetime.now(tz=CN_TZ)
    trade_date = clock.astimezone(CN_TZ).date()
    start_time = datetime(
        trade_date.year, trade_date.month, trade_date.day, 9, 25, 0, tzinfo=CN_TZ,
    )
    end_time = datetime(
        trade_date.year, trade_date.month, trade_date.day, 15, 5, 0, tzinfo=CN_TZ,
    )
    requests_box = [0]

    def _cb(cur: int, tot: int) -> None:
        requests_box[0] = max(requests_box[0], int(tot or cur or 1))

    try:
        try:
            raw = minute_fn(
                symbols,
                start_time=start_time,
                end_time=end_time,
                asset_type="stock",
                freq="1m",
                on_chunk_done=_cb,
            )
        except TypeError:
            raw = minute_fn(symbols, start_time, end_time, "stock")
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "custom full_minute %s get_minute failed, fail-closed: %s",
            provider_name, e,
        )
        return pl.DataFrame(), max(requests_box[0], 1)
    return _coerce_intraday_frame(raw), max(requests_box[0], 1)


def fetch_intraday_custom_latest(
    provider: object,
    provider_name: str,
    *,
    count: int = 3,
) -> tuple[pl.DataFrame, int] | None:
    """Custom full_minute increment. None = hook not implemented (repair-only)."""
    fn = getattr(provider, "get_intraday_latest", None)
    if not callable(fn):
        return None
    try:
        try:
            raw = fn(symbols=None, count=count)
        except TypeError:
            raw = fn(count)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "custom full_minute %s get_intraday_latest failed, fail-closed: %s",
            provider_name, e,
        )
        return pl.DataFrame(), 1
    return _coerce_intraday_frame(raw), 1


def _try_custom_minute(
    symbols: list[str],
    start_time: datetime | None,
    end_time: datetime | None,
    asset_type: str = "stock",
    freq: str = "1m",
    on_chunk_done: Callable[[int, int, str], None] | None = None,
) -> tuple[pl.DataFrame | None, bool]:
    """尝试自定义分钟源。 (None, True) 回退 TickFlow；(df, False) 直接用。"""
    try:
        provider_name = preferences.get_minute_data_provider()
    except Exception as e:  # noqa: BLE001
        logger.warning("minute prefs unreadable, fail-closed (no TickFlow mix): %s", e)
        return (None, False)
    provider, fallback, err = _resolve_minute_provider(provider_name)
    if err is not None:
        logger.warning(
            "custom minute provider %s resolution failed, fail-closed (no TickFlow mix): %s",
            provider_name, err,
        )
        return (None, False)
    if fallback:
        return (None, True)

    wrapped_cb: Callable[[int, int], None] | None = None
    if on_chunk_done is not None:
        def _wrapped_cb(cur: int, total: int) -> None:
            on_chunk_done(cur, total, "custom")
        wrapped_cb = _wrapped_cb

    try:
        kwargs: dict = {
            "start_time": start_time,
            "end_time": end_time,
            "asset_type": asset_type,
            "freq": freq,
        }
        if wrapped_cb is not None:
            kwargs["on_chunk_done"] = wrapped_cb
        try:
            df = provider.get_minute(symbols, **kwargs)
        except TypeError:
            kwargs.pop("freq", None)
            try:
                df = provider.get_minute(symbols, **kwargs)
            except TypeError:
                kwargs.pop("on_chunk_done", None)
                df = provider.get_minute(symbols, **kwargs)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "custom minute provider %s call failed, falling back to TickFlow: %s",
            provider_name, e,
        )
        return (None, True)
    return (df, False)


def _public_minute_fallback(symbol: str, trade_date: date) -> pl.DataFrame:
    """本地公开分时兜底（仅适合当日/最近交易日视图）。"""
    try:
        from app.services.free_sources.intraday_public import public_intraday_to_minute_rows
        rows = public_intraday_to_minute_rows(symbol, trade_date=trade_date)
        if not rows:
            return pl.DataFrame()
        df = pl.DataFrame(rows)
        if "datetime" in df.columns and df["datetime"].dtype == pl.Utf8:
            df = df.with_columns(pl.col("datetime").str.to_datetime(strict=False))
        return filter_minute_trade_date(
            _normalize_minute(df, default_symbol=symbol),
            trade_date,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "fetch_minute_single(%s, %s) public fallback failed: %s",
            symbol,
            trade_date,
            e,
        )
        return pl.DataFrame()


def fetch_minute_single(
    symbol: str,
    trade_date: date,
    asset_type: str = "stock",
    *,
    capset: CapabilitySet | None = None,
) -> pl.DataFrame:
    """拉取单股单日分钟 K（不写入本地）。

    本地签名保持 (symbol, trade_date)；asset_type / capset 为 9a4 增量可选层。
    优先自定义分钟源。仅当 TickFlow 原生单股分钟能力存在（或未传入 capset）
    时才回退 TickFlow；无权限或 TickFlow 失败时保留公开分时兜底。
    """
    start_time = datetime(trade_date.year, trade_date.month, trade_date.day, 9, 25, 0, tzinfo=CN_TZ)
    end_time = datetime(trade_date.year, trade_date.month, trade_date.day, 15, 5, 0, tzinfo=CN_TZ)

    df, fallback = _try_custom_minute(
        [symbol], start_time=start_time, end_time=end_time,
        asset_type=asset_type, freq="1m",
    )
    if not fallback:
        return df if df is not None else pl.DataFrame()

    allow_tickflow = capset is None or capset.has(Cap.KLINE_MINUTE_BY_SYMBOL)
    if allow_tickflow:
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
                    return filter_minute_trade_date(_normalize_minute(sub), trade_date)
            elif raw is not None and len(raw) > 0:
                return filter_minute_trade_date(_normalize_minute(raw), trade_date)
        except Exception as e:  # noqa: BLE001
            logger.warning("fetch_minute_single(%s, %s) TickFlow failed: %s", symbol, trade_date, e)

    # Leftover TickFlow / undeclared: single-symbol public view (does not persist).
    # Declared custom / prefs-unreadable / resolve failure must not mix public bars.
    if not minute_may_use_leftover_public():
        return pl.DataFrame()
    return _public_minute_fallback(symbol, trade_date)


def validate_historical_minute(
    df: pl.DataFrame,
    symbol: str,
    trade_date: date,
    daily_df: pl.DataFrame,
) -> tuple[pl.DataFrame, dict]:
    """Validate an exact-day minute curve against the owned daily candle."""
    clean = filter_minute_trade_date(df, trade_date)
    required = set(CANONICAL_MINUTE_COLS)
    if clean.is_empty() or not required.issubset(clean.columns):
        raise ValueError("historical minute payload is empty or missing canonical columns")
    clean = (
        clean.filter(pl.col("symbol") == symbol)
        .unique(subset=["symbol", "datetime"], keep="last")
        .sort("datetime")
    )
    if not 216 <= clean.height <= 242:
        raise ValueError(f"historical minute row count out of range: {clean.height}")
    if any(value > 0 for value in clean.null_count().row(0)):
        raise ValueError("historical minute payload contains nulls")
    if clean.filter((pl.col("close") <= 0) | (pl.col("volume") < 0)).height:
        raise ValueError("historical minute payload contains invalid price or volume")

    session_rows = clean.filter(
        (
            (pl.col("datetime").dt.hour() == 9)
            & (pl.col("datetime").dt.minute() >= 30)
        )
        | ((pl.col("datetime").dt.hour() >= 10) & (pl.col("datetime").dt.hour() < 12))
        | ((pl.col("datetime").dt.hour() >= 13) & (pl.col("datetime").dt.hour() < 15))
    )
    if session_rows.height != clean.height:
        raise ValueError("historical minute payload contains rows outside A-share sessions")

    if daily_df.is_empty():
        raise ValueError("local daily candle is missing; refuse minute publish")
    daily = daily_df.sort("date").tail(1)

    def _daily_number(primary: str, fallback: str | None = None) -> float | None:
        for column in (primary, fallback):
            if column and column in daily.columns:
                value = daily[column][0]
                if value is not None:
                    return float(value)
        return None

    daily_close = _daily_number("raw_close", "close")
    daily_volume = _daily_number("volume")
    if not daily_close or not daily_volume or daily_volume <= 0:
        raise ValueError("local daily candle lacks raw close or volume")

    last_close = float(clean["close"][-1])
    minute_volume = float(clean["volume"].sum())
    minute_amount = float(clean["amount"].sum())
    close_diff = abs(last_close - daily_close) / daily_close
    volume_diff = abs(minute_volume - daily_volume) / daily_volume
    if close_diff > 0.005:
        raise ValueError(
            f"minute/daily close mismatch: minute={last_close} daily={daily_close}"
        )
    if volume_diff > 0.01:
        raise ValueError(
            f"minute/daily volume mismatch: minute={minute_volume} daily={daily_volume}"
        )

    daily_amount = _daily_number("amount")
    amount_diff = None
    if daily_amount and daily_amount > 0:
        amount_diff = abs(minute_amount - daily_amount) / daily_amount
        if amount_diff > 0.05:
            raise ValueError(
                f"minute/daily amount mismatch: minute={minute_amount} daily={daily_amount}"
            )

    daily_low = _daily_number("raw_low", "low")
    daily_high = _daily_number("raw_high", "high")
    if daily_low and float(clean["close"].min()) < daily_low * 0.995:
        raise ValueError("minute price falls below the daily raw low")
    if daily_high and float(clean["close"].max()) > daily_high * 1.005:
        raise ValueError("minute price rises above the daily raw high")

    return clean, {
        "row_count": clean.height,
        "last_close": last_close,
        "daily_raw_close": daily_close,
        "volume_sum": minute_volume,
        "daily_volume": daily_volume,
        "amount_sum": minute_amount,
        "daily_amount": daily_amount,
        "close_diff_ratio": close_diff,
        "volume_diff_ratio": volume_diff,
        "amount_diff_ratio": amount_diff,
    }


def persist_historical_minute(
    df: pl.DataFrame,
    repo: KlineRepository,
    symbol: str,
    trade_date: date,
    daily_df: pl.DataFrame,
    *,
    source: str,
    adapter: str | None = None,
) -> dict:
    """Validate and atomically upsert one selected stock/day minute payload."""
    from app.services.atomic_io import write_lineage_record

    clean, quality = validate_historical_minute(df, symbol, trade_date, daily_df)
    minute_dir = repo.store.data_dir / "kline_minute"
    out = minute_dir / f"date={trade_date}" / "part.parquet"
    before = 0
    if out.exists():
        try:
            before = pl.read_parquet(out).height
        except Exception:  # noqa: BLE001
            before = 0
    written = _write_minute_partition(_with_minute_route(clean, minute_route()), minute_dir)
    added = max(0, written - before)

    repo.refresh_minute_views()
    try:
        write_lineage_record(
            repo.store.data_dir,
            "kline_minute",
            {
                "date": trade_date.isoformat(),
                "symbol": symbol,
                "source": source,
                "adapter": adapter,
                "unit_version": "canonical_minute_v1",
                "row_count": clean.height,
                "quality": "healthy",
                "quality_gate": "exact_day_daily_reconciled",
                "quality_metrics": quality,
                "scope": "watchlist_on_demand",
                "target_artifact": str(out.relative_to(repo.store.data_dir)),
                "amount_semantics": "estimated_price_times_volume_lots_times_100",
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("historical minute lineage write failed: %s", exc)
    return {
        **quality,
        "rows_added": added,
        "path": str(out),
        "source": source,
        "adapter": adapter,
    }


def fetch_adj_factor_single(
    symbol: str,
    capset: CapabilitySet | None = None,
) -> pl.DataFrame:
    """按 adj_factor_provider 拉单股除权因子(不写入本地), 用于单股 K 线即时前复权。

    返回结构: symbol, trade_date, ex_factor (空 DataFrame 表示无除权事件或拉取失败)。
    与 _apply_adj_factor / compute_enriched 的 factors 参数格式一致。
    声明了 adj_factor 的自定义源 fail-closed；未声明同样 fail-closed。
    leftover TickFlow 有 cap 走 TickFlow，无 cap 不再静默公开新浪 qfq。
    """
    try:
        provider_name = preferences.get_adj_factor_provider()
    except Exception:  # noqa: BLE001
        logger.warning("fetch_adj_factor_single prefs unreadable, fail-closed")
        return pl.DataFrame()

    if preferences.is_public_adj_factor_provider(provider_name):
        try:
            from app.services.free_sources.adj_factor_public import fetch_adj_factors_symbol
            return fetch_adj_factors_symbol(symbol)
        except Exception as e:  # noqa: BLE001
            logger.warning("fetch_adj_factor_single(%s) public failed: %s", symbol, e)
            return pl.DataFrame()

    custom, fate = _try_custom_adj_provider(provider_name)
    if fate == "skip":
        return pl.DataFrame()
    if fate == "custom" and custom is not None:
        try:
            raw = custom.get_adj_factors([symbol], None, None, "stock")
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "fetch_adj_factor_single(%s) custom %s failed, fail-closed: %s",
                symbol, provider_name, e,
            )
            return pl.DataFrame()
        return _normalize_adj_factor(raw)

    if not (capset and capset.has(Cap.ADJ_FACTOR)):
        logger.info(
            "fetch_adj_factor_single(%s) leftover TickFlow without ADJ cap, fail-closed",
            symbol,
        )
        return pl.DataFrame()

    tf = get_client()
    try:
        raw = tf.klines.ex_factors([symbol], as_dataframe=True, show_progress=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_adj_factor_single(%s) failed: %s", symbol, e)
        return pl.DataFrame()
    return _normalize_adj_factor(raw)


def _latest_minute_datetime(repo: KlineRepository) -> datetime | None:
    """Newest local minute bar that matches the current minute route.

    DuckDB ``kline_minute`` can be temporarily ungated by a raw view refresh.
    File-level provenance is the source of truth so incremental start cannot
    treat leftover TickFlow/public parquet as custom coverage.
    """
    try:
        return latest_usable_minute_datetime(repo.store.data_dir)
    except Exception:  # noqa: BLE001
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
        atomic_write_parquet(day_df, out)

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
    on_chunk_done: Callable[..., None] | None = None,
    extend_backward: bool = False,
    force_full_days: bool = False,
) -> int:
    """同步分钟 K 并存到 Parquet。返回写入行数。

    自定义源成功时走 on_segment 流式落盘; resolver 异常 fail-closed, 不混 TickFlow。
    读-改-写持仓库 _write_lock, 实际写盘走 _write_minute_partition / atomic_write_parquet。
    """
    try:
        minute_provider = preferences.get_minute_data_provider()
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "minute prefs unreadable at sync_and_persist_minute, fail-closed: %s", e,
        )
        return 0
    _, fallback, resolve_err = _resolve_minute_provider(minute_provider)
    minute_is_custom = not fallback and resolve_err is None
    if resolve_err is not None:
        logger.warning(
            "custom minute provider %s resolution failed at sync_and_persist_minute, fail-closed: %s",
            minute_provider, resolve_err,
        )
        return 0
    if not symbols:
        return 0
    if not minute_is_custom and not capset.has(Cap.KLINE_MINUTE_BATCH):
        return 0

    _cleanup_null_datetime_minute(repo)
    _migrate_symbol_to_date_partition(repo)

    now = datetime.now()
    last_dt = _latest_minute_datetime(repo)
    if force_full_days:
        calendar_days = int(days * 7 / 5) + 5
        start_time = now - timedelta(days=calendar_days)
    elif last_dt:
        start_time = last_dt
    else:
        start_time = now - timedelta(days=days)
    end_time = now
    if extend_backward:
        start_time = now - timedelta(days=max(days, 5))
        end_time = last_dt or now

    limit = resolve_limit(
        capset,
        Cap.KLINE_MINUTE_BATCH,
        default_batch=100,
        default_rpm=30,
        default_rpm_when_unset=False,
    )

    minute_dir = repo.store.data_dir / "kline_minute"
    written_box = [0]
    write_lock = getattr(repo, "_write_lock", None) or _minute_partition_lock

    def _persist(seg_df: pl.DataFrame) -> None:
        with write_lock:
            written_box[0] += _write_minute_partition(
                _with_minute_route(seg_df, minute_route()), minute_dir,
            )

    segment_days = preferences.get_minute_sync_segment_days()
    sync_minute_batch(
        symbols, start_time=start_time, end_time=end_time,
        batch_size=limit.batch, rpm=limit.rpm,
        on_chunk_done=on_chunk_done,
        segment_trading_days=segment_days,
        on_segment=_persist,
        asset_type="stock",
        capset=capset,
    )

    if written_box[0] == 0:
        return 0
    written = written_box[0]
    repo.refresh_minute_views()
    logger.info("minute K synced: %d rows (%d symbols)", written, len(symbols))
    return written
