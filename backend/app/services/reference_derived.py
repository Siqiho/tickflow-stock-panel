"""本地派生 reference 数据集构建器: valuation_daily / limit_up_events / index_membership_history。

来源: 从分支 codex/data-platform-convergence-v1@7019d03 的 backend/app/data_sync/m6/build.py
移植并按主树风格重写为独立模块。全部输入均为本地 Parquet
(kline_daily / kline_daily_enriched / sealed_l1 / instruments / financials/shares / pools),
构建过程零外部请求。

显式重建入口: scripts/rebuild-reference-derived.py; 不加入自动调度。

与 7019d03 原实现的差异:
  - sealed_l1 封单金额只读取与 trade_date 同日分区, 不再把任意日期的封单套到所有交易日。
  - index_membership_history 支持以既有 members.parquet 为基线做快照差分:
    持续成员保留原 effective_from, 消失成员写 effective_to, 新成员按 snapshot_diff 追加。
  - lineage 记录 coverage_scope / source_daily_rows / source_daily_symbols,
    如实披露该分区是全市场日线还是 CSI500+自选范围日线派生。
"""

from __future__ import annotations

import contextlib
import logging
import re
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.price_limits import is_risk_warning_name, price_limit_pct
from app.services.atomic_io import atomic_write_parquet, write_lineage_record
from app.services.financial_pit import ensure_pit_columns, filter_as_of

logger = logging.getLogger(__name__)

__all__ = [
    "REFERENCE_DERIVED_DATASETS",
    "build_index_membership_from_pools",
    "build_limit_up_events",
    "build_valuation_daily",
    "merge_membership_history",
    "rebuild_reference_derived",
]

REFERENCE_DERIVED_DATASETS = (
    "valuation_daily",
    "limit_up_events",
    "index_membership_history",
)

# 全市场日线分区的最小 symbol 数; 低于该值视为范围采集(CSI500+自选)分区。
FULL_MARKET_SYMBOL_THRESHOLD = 4000

_DATE_DIR_RE = re.compile(r"^date=(\d{4}-\d{2}-\d{2})$")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def list_partition_dates(data_dir: Path, table: str = "kline_daily") -> list[date]:
    if table in {
        "kline_daily",
        "kline_daily_enriched",
        "kline_index_daily",
        "kline_index_enriched",
        "kline_etf_daily",
        "kline_etf_enriched",
    }:
        from app.services.kline_sync import safe_usable_daily_partition_dates

        return safe_usable_daily_partition_dates(data_dir, table=table)
    if table in {"kline_minute", "kline_etf_minute"}:
        from app.services.kline_sync import safe_usable_minute_partition_dates

        asset_type = "etf" if table == "kline_etf_minute" else "stock"
        return safe_usable_minute_partition_dates(data_dir, asset_type=asset_type)
    # Unknown tables used to leftover-glob any date=* parquet. Fail-closed:
    # only routed kline / minute tables are calendars.
    return []


def partition_path(data_dir: Path, day: date, table: str = "kline_daily") -> Path:
    return Path(data_dir) / table / f"date={day.isoformat()}" / "part.parquet"


def _read_usable_daily(data_dir: Path, trade_date: date) -> pl.DataFrame:
    """Read one kline_daily partition only when it matches the current route."""
    try:
        from app.services.kline_sync import read_usable_daily_partition

        return read_usable_daily_partition(
            Path(data_dir) / "kline_daily" / f"date={trade_date.isoformat()}",
        )
    except Exception:  # noqa: BLE001
        return pl.DataFrame()


def _read_instruments(data_dir: Path) -> pl.DataFrame:
    try:
        from app.services.instrument_sync import read_usable_instruments

        return read_usable_instruments(data_dir)
    except Exception:  # noqa: BLE001
        return pl.DataFrame()


def _board_of(symbol: str) -> str:
    s = str(symbol).upper()
    if s.endswith(".BJ"):
        return "BJ"
    code = s.split(".", 1)[0]
    if code.startswith(("688", "689")):
        return "STAR"
    if code.startswith(("300", "301")):
        return "CHINEXT"
    if s.endswith(".SH"):
        return "SH_MAIN"
    if s.endswith(".SZ"):
        return "SZ_MAIN"
    return "OTHER"


def _coverage_scope(symbol_count: int) -> str:
    if symbol_count >= FULL_MARKET_SYMBOL_THRESHOLD:
        return "full_market_daily"
    return "pipeline_scope_daily"


# ---------------------------------------------------------------- valuation


def _load_pit_safe_shares(data_dir: Path, trade_date: date) -> pl.DataFrame:
    """可用于历史估值的股本: 严格 PIT 且非快照来源。"""
    try:
        from app.services.financial_sync import get_financial_df

        raw = get_financial_df(Path(data_dir), "shares")
    except Exception:  # noqa: BLE001
        return pl.DataFrame()
    if raw is None or raw.is_empty():
        return pl.DataFrame()
    pit = ensure_pit_columns(raw, table="shares")
    safe = filter_as_of(pit, trade_date, table="shares", strict=True)
    if safe.is_empty():
        return pl.DataFrame()
    cols = [
        c
        for c in ("symbol", "total_shares", "float_shares", "effective_date", "source")
        if c in safe.columns
    ]
    out = safe.select(cols).unique(subset=["symbol"], keep="last")
    return out.with_columns(pl.lit(True).alias("shares_pit_safe"))


def build_valuation_daily(
    data_dir: Path,
    trade_date: date,
    *,
    source: str = "raw_daily_x_pit_safe_shares",
) -> pl.DataFrame:
    """同日未复权日线 x 严格 PIT 股本; 无权威历史估值源时 PE/PB 保持 null。

    instruments 快照股本不用于历史估值。
    """
    data_dir = Path(data_dir)
    daily = _read_usable_daily(data_dir, trade_date)
    if daily.is_empty():
        return pl.DataFrame()
    price_col = "raw_close" if "raw_close" in daily.columns else "close"
    if price_col not in daily.columns or "symbol" not in daily.columns:
        return pl.DataFrame()

    shares = _load_pit_safe_shares(data_dir, trade_date)
    df = daily.select(
        [
            pl.col("symbol").cast(pl.Utf8),
            pl.col(price_col).cast(pl.Float64, strict=False).alias("close"),
        ]
    )
    if shares.is_empty():
        df = df.with_columns(
            [
                pl.lit(None).cast(pl.Float64).alias("total_share"),
                pl.lit(None).cast(pl.Float64).alias("float_share"),
                pl.lit(False).alias("shares_pit_safe"),
                pl.lit(None).cast(pl.Utf8).alias("shares_source"),
            ]
        )
    else:
        sel: list[pl.Expr] = [pl.col("symbol")]
        if "total_shares" in shares.columns:
            sel.append(pl.col("total_shares").cast(pl.Float64, strict=False).alias("total_share"))
        else:
            sel.append(pl.lit(None).cast(pl.Float64).alias("total_share"))
        if "float_shares" in shares.columns:
            sel.append(pl.col("float_shares").cast(pl.Float64, strict=False).alias("float_share"))
        else:
            sel.append(pl.lit(None).cast(pl.Float64).alias("float_share"))
        sel.append(pl.lit(True).alias("shares_pit_safe"))
        if "source" in shares.columns:
            sel.append(pl.col("source").cast(pl.Utf8).alias("shares_source"))
        else:
            sel.append(pl.lit(None).cast(pl.Utf8).alias("shares_source"))
        df = df.join(shares.select(sel), on="symbol", how="left")
        df = df.with_columns(pl.col("shares_pit_safe").fill_null(False))

    fetched = _utc_now()
    df = df.with_columns(
        [
            pl.lit(trade_date).alias("trade_date"),
            pl.lit(None).cast(pl.Float64).alias("pe_ttm"),
            pl.lit(None).cast(pl.Float64).alias("pb"),
            pl.lit(None).cast(pl.Float64).alias("ps_ttm"),
            pl.lit(None).cast(pl.Float64).alias("pcf_ttm"),
            pl.lit(source).alias("source"),
            pl.lit(fetched).alias("fetched_at"),
            pl.lit(
                "mv=raw_close*pit_safe_shares CNY when shares_pit_safe; pe/pb null without historical feed"
            ).alias("unit_note"),
            pl.lit("as_collected").alias("history_guarantee"),
            pl.lit("valuation_daily_v2").alias("unit_version"),
        ]
    )
    df = df.with_columns(
        [
            pl.when(pl.col("shares_pit_safe") & pl.col("total_share").is_not_null())
            .then(pl.col("close") * pl.col("total_share"))
            .otherwise(None)
            .alias("total_mv"),
            pl.when(pl.col("shares_pit_safe") & pl.col("float_share").is_not_null())
            .then(pl.col("close") * pl.col("float_share"))
            .otherwise(None)
            .alias("float_mv"),
        ]
    )
    cols = [
        "symbol",
        "trade_date",
        "pe_ttm",
        "pb",
        "ps_ttm",
        "pcf_ttm",
        "total_mv",
        "float_mv",
        "total_share",
        "float_share",
        "close",
        "shares_pit_safe",
        "shares_source",
        "source",
        "fetched_at",
        "unit_note",
        "history_guarantee",
        "unit_version",
    ]
    return df.select([c for c in cols if c in df.columns]).drop_nulls(
        subset=["symbol", "trade_date"]
    )


# ------------------------------------------------------------- limit events


def _prev_trade_date(data_dir: Path, trade_date: date) -> date | None:
    parts = list_partition_dates(data_dir, "kline_daily")
    prev = [d for d in parts if d < trade_date]
    return prev[-1] if prev else None


def _limit_state_from_prices(
    close: float | None,
    high: float | None,
    low: float | None,
    limit_up: float | None,
    limit_down: float | None,
    *,
    tick: float = 0.005,
) -> str:
    if close is None:
        return "unknown"
    if limit_up is not None and close >= limit_up - tick:
        return "limit_up_final"
    if limit_down is not None and close <= limit_down + tick:
        return "limit_down_final"
    if (
        limit_up is not None
        and high is not None
        and high >= limit_up - tick
        and close < limit_up - tick
    ):
        return "broken_limit_up"
    if (
        limit_down is not None
        and low is not None
        and low <= limit_down + tick
        and close > limit_down + tick
    ):
        return "broken_limit_down"
    return "normal"


def _rule_limit_price(prev_close: float, pct: float, *, up: bool) -> float:
    """交易所整分 half-up 取整的涨跌停价。"""
    sign = 1 if up else -1
    numerator = round((1 + sign * pct) * 100)
    cents = int((prev_close * 100) + 0.5)
    return ((cents * numerator + 50) // 100) / 100.0


def _seal_fund_map(data_dir: Path, trade_date: date) -> dict[str, float]:
    """封单金额只取与 trade_date 同日且当前 depth route 可用的 sealed_l1。"""
    part = data_dir / "sealed_l1" / f"date={trade_date.isoformat()}"
    out: dict[str, float] = {}
    if not part.exists():
        return out
    try:
        from app.services.depth_service import depth_cache_usable, depth_route

        route = depth_route()
    except Exception:  # noqa: BLE001
        return out
    for path in sorted(part.glob("*.parquet")):
        try:
            sdf = pl.read_parquet(path)
        except Exception:
            continue
        if not depth_cache_usable(sdf, route):
            continue
        if not {"symbol", "sealed_up", "bid1_vol"}.issubset(sdf.columns):
            continue
        for row in sdf.filter(pl.col("sealed_up") == True).select(  # noqa: E712
            ["symbol", "bid1_vol"]
        ).to_dicts():
            with contextlib.suppress(TypeError, ValueError):
                out[str(row["symbol"]).upper()] = float(row["bid1_vol"])
    return out


def build_limit_up_events(
    data_dir: Path,
    trade_date: date,
    *,
    source: str = "raw_daily_board_rules",
) -> pl.DataFrame:
    """基于未复权日线 + 板块/ST/北交所规则的 EOD 涨跌停事件。

    涨跌停价按前收盘 x 规则比例推算, 不使用 instruments 快照里的
    limit_up/limit_down(可能过期)。无历史 ST 名称路径, st_history_guarantee
    只能保证当前名称快照。
    """
    data_dir = Path(data_dir)
    daily = _read_usable_daily(data_dir, trade_date)
    if daily.is_empty():
        return pl.DataFrame()
    close_c = "raw_close" if "raw_close" in daily.columns else "close"
    high_c = "raw_high" if "raw_high" in daily.columns else "high"
    low_c = "raw_low" if "raw_low" in daily.columns else "low"
    if close_c not in daily.columns or "symbol" not in daily.columns:
        return pl.DataFrame()

    select_exprs = [
        pl.col("symbol").cast(pl.Utf8),
        pl.col(close_c).cast(pl.Float64, strict=False).alias("close"),
        pl.col(high_c).cast(pl.Float64, strict=False).alias("high")
        if high_c in daily.columns
        else pl.lit(None).cast(pl.Float64).alias("high"),
        pl.col(low_c).cast(pl.Float64, strict=False).alias("low")
        if low_c in daily.columns
        else pl.lit(None).cast(pl.Float64).alias("low"),
    ]
    inst = _read_instruments(data_dir)
    if not inst.is_empty() and "name" in inst.columns:
        names = inst.select(["symbol", "name"]).unique(subset=["symbol"], keep="last")
        df = daily.select(select_exprs).join(names, on="symbol", how="left")
    else:
        df = daily.select(select_exprs).with_columns(pl.lit(None).cast(pl.Utf8).alias("name"))

    prev_day = _prev_trade_date(data_dir, trade_date)
    prev_map: dict[str, float] = {}
    if prev_day is not None:
        prev = _read_usable_daily(data_dir, prev_day)
        if not prev.is_empty():
            pc = "raw_close" if "raw_close" in prev.columns else "close"
            if pc in prev.columns:
                for row in prev.select(["symbol", pc]).to_dicts():
                    with contextlib.suppress(TypeError, ValueError):
                        prev_map[str(row["symbol"]).upper()] = float(row[pc])

    height_map: dict[str, int] = {}
    enr_path = partition_path(data_dir, trade_date, table="kline_daily_enriched")
    if enr_path.exists():
        try:
            from app.services.kline_sync import daily_partition_usable, filter_daily_cache

            if daily_partition_usable(enr_path):
                enr = filter_daily_cache(pl.read_parquet(enr_path))
            else:
                enr = pl.DataFrame()
        except Exception:  # noqa: BLE001
            enr = pl.DataFrame()
        if not enr.is_empty() and "consecutive_limit_ups" in enr.columns:
            for row in enr.select(["symbol", "consecutive_limit_ups"]).to_dicts():
                try:
                    if row["consecutive_limit_ups"] is not None:
                        height_map[str(row["symbol"]).upper()] = int(row["consecutive_limit_ups"])
                except (TypeError, ValueError):
                    pass

    seal_map = _seal_fund_map(data_dir, trade_date)

    seen = _utc_now()
    rows: list[dict[str, Any]] = []
    for item in df.to_dicts():
        sym = str(item["symbol"]).upper()
        st = is_risk_warning_name(item.get("name"))
        prev_close = prev_map.get(sym)
        if prev_close is None or prev_close <= 0:
            # 无前收盘无法诚实判定, 跳过
            continue
        pct = price_limit_pct(sym, trade_date, is_risk_warning=st)
        limit_up = _rule_limit_price(prev_close, pct, up=True)
        limit_down = _rule_limit_price(prev_close, pct, up=False)

        state = _limit_state_from_prices(
            item.get("close"),
            item.get("high"),
            item.get("low"),
            limit_up,
            limit_down,
        )
        if state == "normal":
            continue
        rows.append(
            {
                "symbol": sym,
                "trade_date": trade_date,
                "state": state,
                "board": _board_of(sym),
                "is_st": st,
                "st_history_guarantee": "name_asof_snapshot_only",
                "limit_pct": pct,
                "prev_close": prev_close,
                "limit_up": limit_up,
                "limit_down": limit_down,
                "close": item.get("close"),
                "high": item.get("high"),
                "low": item.get("low"),
                "first_seal": None,
                "last_seal": None,
                "break_count": None,
                "seal_fund": seal_map.get(sym),
                "board_height": height_map.get(sym),
                "reason": state,
                "reason_text": None,
                "intraday_vs_final": "final_eod",
                "price_basis": "raw_unadjusted",
                "limit_basis": "prev_close_rule",
                "history_guarantee": "eod_final_only; st_from_current_name_snapshot",
                "unit_version": "limit_up_events_v2",
                "source_published_at": seen,
                "first_seen_at": seen,
                "source": source,
            }
        )
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).sort(["state", "board", "symbol"])


# --------------------------------------------------------------- membership


def _pool_snapshot_usable(df: pl.DataFrame, route: str) -> bool:
    """Whether a pools parquet may seed membership for the current pool route.

    Custom / unresolved never reuse leftover TickFlow or public CSI caches.
    Leftover TickFlow / public still see untagged snapshots.
    """
    expected = (route or "").strip().lower()
    if not expected or expected in {"custom", "unresolved"}:
        if "route" not in df.columns:
            return False
        stored = [str(v or "").strip().lower() for v in df["route"].to_list()]
        nonempty = [s for s in stored if s]
        return bool(nonempty) and all(s == expected for s in nonempty)
    if "route" not in df.columns:
        return expected in {"tickflow", "public"}
    stored = [str(v or "").strip().lower() for v in df["route"].to_list()]
    nonempty = [s for s in stored if s]
    if not nonempty:
        return expected in {"tickflow", "public"}
    return all(s == expected for s in nonempty)


def build_index_membership_from_pools(
    data_dir: Path,
    *,
    as_of: date | None = None,
    source_default: str = "pools_snapshot_seed",
) -> pl.DataFrame:
    """从当前 pools 快照生成成分种子行。

    membership_basis=snapshot_seed / history_guarantee=as_collected;
    这不是官方修订历史。
    """
    data_dir = Path(data_dir)
    pools_dir = data_dir / "pools"
    if not pools_dir.exists():
        return pl.DataFrame()
    frames: list[pl.DataFrame] = []
    seen = _utc_now()
    try:
        from app.tickflow.pools import pool_route
        route = pool_route()
    except Exception:  # noqa: BLE001
        return pl.DataFrame()
    for path in sorted(pools_dir.glob("*.parquet")):
        try:
            df = pl.read_parquet(path)
        except Exception:
            continue
        if "symbol" not in df.columns:
            continue
        if not _pool_snapshot_usable(df, route):
            continue
        pool_id = path.stem
        if "pool_id" in df.columns and df.height:
            pool_id = str(df.get_column("pool_id")[0] or pool_id)
        index_code = None
        if "index_code" in df.columns and df.height:
            index_code = str(df.get_column("index_code")[0] or "")
        index_symbol = f"{index_code.zfill(6)}.SH" if index_code else None
        asof = as_of
        if asof is None and "as_of" in df.columns and df.height:
            v = df.get_column("as_of")[0]
            if isinstance(v, date):
                asof = v
            else:
                try:
                    asof = date.fromisoformat(str(v)[:10])
                except ValueError:
                    asof = None
        asof = asof or date.today()
        src = source_default
        if "source" in df.columns and df.height:
            src = f"{source_default}:{df.get_column('source')[0]}"
        part = df.select([pl.col("symbol").cast(pl.Utf8)]).unique()
        part = part.with_columns(
            [
                pl.lit(index_code or pool_id).alias("index_code"),
                pl.lit(index_symbol).alias("index_symbol"),
                pl.lit(asof).alias("effective_from"),
                pl.lit(None).cast(pl.Date).alias("effective_to"),
                pl.lit(src).alias("source"),
                pl.lit(asof).alias("as_of"),
                pl.lit(seen).alias("first_seen_at"),
                pl.lit(pool_id).alias("pool_id"),
                pl.lit("snapshot_seed").alias("membership_basis"),
                pl.lit("as_collected").alias("history_guarantee"),
                pl.lit("index_membership_history_v2").alias("unit_version"),
            ]
        )
        frames.append(part)
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed").sort(["index_code", "symbol"])


def merge_membership_history(existing: pl.DataFrame, seed: pl.DataFrame) -> pl.DataFrame:
    """把新快照种子并入既有成员历史(快照差分, 非官方修订历史)。

    - 两边都有的未关闭成员: 保留原行(原 effective_from 不变)。
    - 只在旧表且未关闭的成员: 视为已移出, effective_to 置为新快照 as_of。
    - 只在新快照的成员: 追加, membership_basis=snapshot_diff。
    - 旧表中已关闭(effective_to 非空)的行: 原样保留为历史。
    """
    if existing is None or existing.is_empty():
        return seed
    if seed is None or seed.is_empty():
        return existing
    key = ["pool_id", "symbol"]
    new_as_of = seed.get_column("as_of").max()

    closed = existing.filter(pl.col("effective_to").is_not_null())
    open_rows = existing.filter(pl.col("effective_to").is_null())

    continued = open_rows.join(seed.select(key).unique(), on=key, how="semi")
    removed = open_rows.join(seed.select(key).unique(), on=key, how="anti").with_columns(
        pl.lit(new_as_of).cast(pl.Date).alias("effective_to")
    )
    open_keys = open_rows.select(key).unique()
    added = seed.join(open_keys, on=key, how="anti").with_columns(
        pl.lit("snapshot_diff").alias("membership_basis")
    )
    merged = pl.concat([closed, continued, removed, added], how="diagonal_relaxed")
    return merged.sort(["pool_id", "symbol", "effective_from"])


# -------------------------------------------------------------- orchestration


def _write_dataset(
    data_dir: Path,
    dataset_id: str,
    relpath: str,
    frame: pl.DataFrame,
    *,
    run_id: str,
    source: str,
    unit_version: str,
    partition_date: date | None = None,
    lineage_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data_dir = Path(data_dir)
    target = data_dir / relpath
    if frame is None or frame.is_empty():
        return {
            "dataset_id": dataset_id,
            "ok": False,
            "rows": 0,
            "path": str(target),
            "error": "empty",
        }
    try:
        if dataset_id in {"valuation_daily", "limit_up_events"}:
            from app.services.kline_sync import daily_route

            route = daily_route()
            if route == "unresolved":
                return {
                    "dataset_id": dataset_id,
                    "ok": False,
                    "rows": 0,
                    "path": str(target),
                    "error": "unresolved",
                }
            if "route" not in frame.columns:
                frame = frame.with_columns(pl.lit(route).alias("route"))
        elif dataset_id == "index_membership_history":
            from app.tickflow.pools import pool_route

            route = pool_route()
            if route == "unresolved":
                return {
                    "dataset_id": dataset_id,
                    "ok": False,
                    "rows": 0,
                    "path": str(target),
                    "error": "unresolved",
                }
            if "route" not in frame.columns:
                frame = frame.with_columns(pl.lit(route).alias("route"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("skip %s write: route resolve failed: %s", dataset_id, exc)
        return {
            "dataset_id": dataset_id,
            "ok": False,
            "rows": 0,
            "path": str(target),
            "error": "unresolved",
        }
    atomic_write_parquet(frame, target)
    payload: dict[str, Any] = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "source": source,
        "unit_version": unit_version,
        "quality_status": "healthy",
        "row_count": int(frame.height),
        "date": (partition_date or date.today()).isoformat(),
        "target_artifact": relpath,
        "fetched_at": _utc_iso(),
    }
    if lineage_extra:
        payload.update(lineage_extra)
    try:
        write_lineage_record(data_dir, dataset_id, payload, run_id=run_id)
    except Exception as exc:
        logger.warning("lineage write failed for %s: %s", dataset_id, exc)
    return {
        "dataset_id": dataset_id,
        "ok": True,
        "rows": int(frame.height),
        "path": str(target),
        "unit_version": unit_version,
        "symbols": int(frame.get_column("symbol").n_unique()) if "symbol" in frame.columns else None,
    }


def rebuild_reference_derived(
    data_dir: Path,
    *,
    start: date | None = None,
    end: date | None = None,
    datasets: Sequence[str] | None = None,
    run_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """按日期窗口重建本地派生 reference 数据集。

    valuation_daily / limit_up_events 逐 kline_daily 分区日构建;
    index_membership_history 与日期窗口无关, 每次调用只做一次快照差分合并。
    """
    data_dir = Path(data_dir)
    run_id = run_id or f"refderived-{_utc_now().strftime('%Y%m%d%H%M%S')}"
    want = set(datasets) if datasets else set(REFERENCE_DERIVED_DATASETS)
    unknown = want - set(REFERENCE_DERIVED_DATASETS)
    if unknown:
        raise ValueError(f"unknown datasets: {sorted(unknown)}")

    all_dates = list_partition_dates(data_dir, "kline_daily")
    dates = [d for d in all_dates if (start is None or d >= start) and (end is None or d <= end)]

    report: dict[str, Any] = {
        "run_id": run_id,
        "dry_run": dry_run,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "dates": [d.isoformat() for d in dates],
        "datasets": {},
    }

    for dataset_id, builder in (
        ("valuation_daily", build_valuation_daily),
        ("limit_up_events", build_limit_up_events),
    ):
        if dataset_id not in want:
            continue
        if (dataset_id in want) and not dates and (start or end):
            report["datasets"][dataset_id] = {"error": "no kline_daily partitions in window"}
            continue
        entries: list[dict[str, Any]] = []
        for day in dates:
            src = _read_usable_daily(data_dir, day)
            src_rows = 0
            src_symbols = 0
            if not src.is_empty() and "symbol" in src.columns:
                src_rows = int(src.height)
                src_symbols = int(src.get_column("symbol").n_unique())
            scope = _coverage_scope(src_symbols)
            if dry_run:
                entries.append(
                    {
                        "date": day.isoformat(),
                        "planned": True,
                        "source_daily_rows": src_rows,
                        "source_daily_symbols": src_symbols,
                        "coverage_scope": scope,
                    }
                )
                continue
            frame = builder(data_dir, day)
            rel = f"reference/{dataset_id}/date={day.isoformat()}/part.parquet"
            info = _write_dataset(
                data_dir,
                dataset_id,
                rel,
                frame,
                run_id=run_id,
                source=(
                    "raw_daily_x_pit_safe_shares"
                    if dataset_id == "valuation_daily"
                    else "raw_daily_board_rules"
                ),
                unit_version=f"{dataset_id}_v2",
                partition_date=day,
                lineage_extra={
                    "coverage_scope": scope,
                    "source_daily_rows": src_rows,
                    "source_daily_symbols": src_symbols,
                    "scope_note": (
                        "derived from local kline_daily partition; pipeline_scope_daily "
                        "partitions only cover the configured pipeline universe "
                        "(CSI500 + watchlist), not the full market"
                    ),
                },
            )
            info["date"] = day.isoformat()
            info["coverage_scope"] = scope
            if not info["ok"] and dataset_id == "limit_up_events":
                # 无事件是合法结果, 不写空分区
                info["note"] = "no limit events for this date"
            entries.append(info)
        report["datasets"][dataset_id] = {
            "partitions": entries,
            "written": sum(1 for e in entries if e.get("ok")),
            "empty": sum(1 for e in entries if e.get("error") == "empty"),
        }

    if "index_membership_history" in want:
        seed = build_index_membership_from_pools(data_dir)
        target = data_dir / "reference" / "index_membership_history" / "members.parquet"
        try:
            from app.tickflow.pools import pool_route

            route = pool_route()
        except Exception:  # noqa: BLE001
            route = "unresolved"
        existing = pl.read_parquet(target) if target.exists() else pl.DataFrame()
        if not existing.is_empty() and not _pool_snapshot_usable(existing, route):
            existing = pl.DataFrame()
        merged = merge_membership_history(existing, seed)
        pools_as_of = str(seed.get_column("as_of").max()) if not seed.is_empty() else None
        if dry_run:
            report["datasets"]["index_membership_history"] = {
                "planned": True,
                "existing_rows": int(existing.height),
                "seed_rows": int(seed.height),
                "merged_rows": int(merged.height),
                "pools_as_of": pools_as_of,
            }
        else:
            info = _write_dataset(
                data_dir,
                "index_membership_history",
                "reference/index_membership_history/members.parquet",
                merged,
                run_id=run_id,
                source="pools_snapshot_seed",
                unit_version="index_membership_history_v2",
                lineage_extra={
                    "pools_as_of": pools_as_of,
                    "existing_rows": int(existing.height),
                    "seed_rows": int(seed.height),
                    "membership_basis": "snapshot_seed_plus_diff",
                    "scope_note": (
                        "seeded/diffed from local pools snapshots (csindex/sina); "
                        "as_collected observation history, not official index revision history"
                    ),
                },
            )
            report["datasets"]["index_membership_history"] = info
    return report
