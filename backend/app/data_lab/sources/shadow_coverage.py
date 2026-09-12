"""Shadow coverage builders for listing/status using local owned snapshots.

These are intentionally labeled shadow / seed — not formal producers.
They never write to the provided source data_dir; callers pass isolated sinks.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

_SYMBOL_RE = re.compile(r"^[0-9]{6}\.(SH|SZ|BJ)$")
_SENTINEL_LISTING = date(1970, 1, 1)


def _read_instruments(path: Path) -> pl.DataFrame:
    try:
        from app.services.instrument_sync import filter_instruments, instrument_route

        df = filter_instruments(pl.read_parquet(path), instrument_route())
    except Exception:
        df = pl.DataFrame()
    need = {"symbol", "name", "exchange", "listing_date"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"instruments missing columns: {sorted(missing)}")
    out = df.select(
        [
            pl.col("symbol").cast(pl.Utf8),
            pl.col("name").cast(pl.Utf8),
            pl.col("exchange").cast(pl.Utf8),
            pl.col("listing_date").cast(pl.Date, strict=False),
        ]
    )
    return out


def build_listing_events_from_instruments(
    instruments_path: Path,
    *,
    as_of: date | None = None,
    source: str = "local_instruments_snapshot_shadow",
) -> pl.DataFrame:
    """Seed listing events from current instruments snapshot.

    Limitations (recorded in summarize_listing_coverage):
    - no delist/relist/code_change history
    - only currently listed names present in snapshot
    - listing_date==1970-01-01 treated as invalid/missing
    """
    as_of = as_of or date.today()
    df = _read_instruments(instruments_path)
    df = df.filter(pl.col("symbol").map_elements(lambda s: bool(_SYMBOL_RE.match(str(s))), return_dtype=pl.Boolean))
    valid = df.filter(pl.col("listing_date").is_not_null() & (pl.col("listing_date") > _SENTINEL_LISTING))
    events = valid.select(
        [
            pl.col("symbol"),
            pl.lit("list").alias("event_type"),
            pl.col("listing_date").alias("event_date"),
            pl.col("name"),
            pl.col("exchange"),
            pl.lit(None).cast(pl.Utf8).alias("prior_symbol"),
            pl.lit(source).alias("source"),
            pl.lit(as_of).cast(pl.Date).alias("as_of"),
        ]
    )
    return events.unique(subset=["symbol", "event_type", "event_date"], keep="last")


def summarize_listing_coverage(
    instruments_path: Path,
    events: pl.DataFrame,
) -> dict[str, Any]:
    inst = _read_instruments(instruments_path)
    total = inst.height
    bad_symbol = inst.filter(
        ~pl.col("symbol").map_elements(lambda s: bool(_SYMBOL_RE.match(str(s))), return_dtype=pl.Boolean)
    ).height
    sentinel = inst.filter(pl.col("listing_date") <= _SENTINEL_LISTING).height
    null_list = inst.filter(pl.col("listing_date").is_null()).height
    by_ex = (
        inst.group_by("exchange")
        .len()
        .sort("exchange")
        .to_dicts()
    )
    event_by_ex = (
        events.group_by("exchange").len().sort("exchange").to_dicts() if events.height else []
    )
    return {
        "kind": "listing_delisting_events_shadow",
        "instruments_total": total,
        "events_built": events.height,
        "invalid_symbol_rows": bad_symbol,
        "sentinel_listing_date_1970": sentinel,
        "null_listing_date": null_list,
        "coverage_ratio_vs_instruments": (events.height / total) if total else 0.0,
        "delist_events": int((events.filter(pl.col("event_type") == "delist").height) if events.height else 0),
        "relist_events": int((events.filter(pl.col("event_type") == "relist").height) if events.height else 0),
        "code_change_events": int(
            (events.filter(pl.col("event_type") == "code_change").height) if events.height else 0
        ),
        "instruments_by_exchange": by_ex,
        "events_by_exchange": event_by_ex,
        "gaps": [
            "no_delist_history_in_snapshot",
            "no_relist_history",
            "no_code_change_history",
            "bj_and_star_coverage_depends_on_snapshot_freshness",
            *(["sentinel_listing_dates_present"] if sentinel else []),
        ],
        "admission": "LAB_SHADOW_ONLY",
    }


def _iter_daily_partitions(kline_root: Path) -> list[tuple[date, list[Path]]]:
    out: list[tuple[date, list[Path]]] = []
    if not kline_root.exists():
        return out
    try:
        from app.services.kline_sync import usable_daily_partition_files
    except Exception:
        usable_daily_partition_files = None
    for part in sorted(kline_root.glob("date=*")):
        day_s = part.name.removeprefix("date=")
        try:
            d = date.fromisoformat(day_s)
        except ValueError:
            continue
        if usable_daily_partition_files is not None:
            try:
                files = usable_daily_partition_files(part)
            except Exception:
                files = []
        else:
            files = sorted(part.glob("*.parquet"))
        files = [path for path in files if path.is_file()]
        if not files:
            continue
        out.append((d, files))
    return out


def _read_daily_partition(files: list[Path]) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for path in files:
        try:
            frames.append(pl.read_parquet(path))
        except Exception:
            continue
    if not frames:
        return pl.DataFrame()
    return frames[0] if len(frames) == 1 else pl.concat(frames, how="diagonal_relaxed")


def build_status_history_shadow(
    kline_root: Path,
    *,
    sample_days: int = 5,
    as_of: date | None = None,
    source: str = "local_kline_halt_heuristic_shadow",
    max_symbols: int | None = 500,
    instruments_path: Path | None = None,
) -> pl.DataFrame:
    """Infer short suspended intervals from recent daily bars.

    Primary heuristic: open==0 and high==0 bars.
    Fallback (common when production already strips halt bars): symbols listed
    on/before the day in instruments snapshot but missing from that day's
    partition are marked suspended with reason ``missing_from_daily_partition``.

    This is a shadow, not an exchange status feed.
    """
    as_of = as_of or date.today()
    empty = pl.DataFrame(
        schema={
            "symbol": pl.Utf8,
            "status": pl.Utf8,
            "effective_from": pl.Date,
            "effective_to": pl.Date,
            "reason": pl.Utf8,
            "source": pl.Utf8,
            "as_of": pl.Date,
        }
    )
    parts = _iter_daily_partitions(kline_root)
    if not parts:
        return empty
    chosen = parts[-sample_days:]
    frames: list[pl.DataFrame] = []
    for d, files in chosen:
        df = _read_daily_partition(files)
        if "symbol" not in df.columns:
            continue
        cols = set(df.columns)
        if {"open", "high"}.issubset(cols):
            halted = df.filter(
                (pl.col("open").fill_null(0) == 0) & (pl.col("high").fill_null(0) == 0)
            ).select([pl.col("symbol").cast(pl.Utf8)])
            if not halted.is_empty():
                halted = halted.with_columns(
                    pl.lit("suspended").alias("status"),
                    pl.lit(d).cast(pl.Date).alias("effective_from"),
                    pl.lit(d + timedelta(days=1)).cast(pl.Date).alias("effective_to"),
                    pl.lit("open_high_zero_bar_heuristic").alias("reason"),
                    pl.lit(source).alias("source"),
                    pl.lit(as_of).cast(pl.Date).alias("as_of"),
                )
                frames.append(halted)

    # Fallback missing-symbol shadow when halt bars were stripped upstream.
    if not frames and instruments_path is not None and Path(instruments_path).exists():
        inst = _read_instruments(Path(instruments_path)).filter(
            pl.col("symbol").map_elements(lambda s: bool(_SYMBOL_RE.match(str(s))), return_dtype=pl.Boolean)
            & pl.col("listing_date").is_not_null()
            & (pl.col("listing_date") > _SENTINEL_LISTING)
        )
        for d, files in chosen:
            day_df = _read_daily_partition(files)
            if "symbol" not in day_df.columns:
                continue
            present = set(day_df.get_column("symbol").cast(pl.Utf8).to_list())
            expected = inst.filter(pl.col("listing_date") <= d)
            missing = expected.filter(~pl.col("symbol").is_in(sorted(present)))
            if missing.is_empty():
                continue
            row = missing.select([pl.col("symbol").cast(pl.Utf8)]).with_columns(
                pl.lit("suspended").alias("status"),
                pl.lit(d).cast(pl.Date).alias("effective_from"),
                pl.lit(d + timedelta(days=1)).cast(pl.Date).alias("effective_to"),
                pl.lit("missing_from_daily_partition").alias("reason"),
                pl.lit(source).alias("source"),
                pl.lit(as_of).cast(pl.Date).alias("as_of"),
            )
            frames.append(row)

    if not frames:
        return empty
    out = pl.concat(frames, how="vertical_relaxed")
    out = out.filter(
        pl.col("symbol").map_elements(lambda s: bool(_SYMBOL_RE.match(str(s))), return_dtype=pl.Boolean)
    )
    out = out.unique(subset=["symbol", "effective_from", "status"], keep="last")
    if max_symbols is not None and out.height:
        symbols = (
            out.select("symbol").unique().sort("symbol").head(max_symbols).get_column("symbol").to_list()
        )
        out = out.filter(pl.col("symbol").is_in(symbols))
    return out.sort(["symbol", "effective_from"])


def summarize_status_shadow(
    frame: pl.DataFrame,
    *,
    sample_days: int,
    kline_root: Path,
) -> dict[str, Any]:
    parts = _iter_daily_partitions(kline_root)
    return {
        "kind": "instrument_status_history_shadow",
        "rows": frame.height,
        "symbols": int(frame.select(pl.col("symbol").n_unique()).item()) if frame.height else 0,
        "sample_days_requested": sample_days,
        "kline_partitions_available": len(parts),
        "date_min": str(frame.get_column("effective_from").min()) if frame.height else None,
        "date_max": str(frame.get_column("effective_from").max()) if frame.height else None,
        "gaps": [
            "not_exchange_status_feed",
            "open_high_zero_often_empty_because_prod_strips_halt_bars",
            "missing_symbol_fallback_confounds_halt_with_incomplete_universe_or_delist",
            "no_st_star_st_transition_timeline",
            "no_delisted_terminal_state_from_bars_alone",
            "point_day_intervals_only",
        ],
        "admission": "LAB_SHADOW_ONLY",
        "built_at": datetime.now().astimezone().isoformat(),
    }


def compare_calendar_to_kline_partitions(
    calendar: pl.DataFrame,
    kline_root: Path,
    *,
    exchange: str = "SH",
) -> dict[str, Any]:
    """Compare open days from calendar against local daily partition names.

    K-line presence is a shadow check only — missing partition != non-trading day
    if backfill incomplete; extra partition on calendar-closed day is a stronger smell.
    """
    parts = {d for d, _ in _iter_daily_partitions(kline_root)}
    if calendar.is_empty():
        return {
            "exchange": exchange,
            "calendar_open_days": 0,
            "kline_partitions": len(parts),
            "open_with_partition": 0,
            "open_missing_partition": [],
            "closed_but_partition_exists": [],
            "coverage_open_with_data": 0.0,
            "note": "empty_calendar",
        }
    cal = calendar.filter(pl.col("exchange") == exchange)
    open_days = {
        d for d in cal.filter(pl.col("is_open")).get_column("trade_date").to_list()
    }
    closed_days = {
        d for d in cal.filter(~pl.col("is_open")).get_column("trade_date").to_list()
    }
    all_cal_days = open_days | closed_days
    # Restrict comparison to calendar range ∩ observed partition span when possible.
    # Use full calendar dates (open+closed) so closed-day partition smells are visible.
    if parts and all_cal_days:
        lo = max(min(parts), min(all_cal_days))
        hi = min(max(parts), max(all_cal_days))
        open_in_span = {d for d in open_days if lo <= d <= hi}
        closed_in_span = {d for d in closed_days if lo <= d <= hi}
        parts_in_span = {d for d in parts if lo <= d <= hi}
    else:
        open_in_span = open_days
        closed_in_span = closed_days
        parts_in_span = parts
        lo = hi = None

    missing = sorted(open_in_span - parts_in_span)
    extra = sorted(parts_in_span & closed_in_span)
    covered = sorted(open_in_span & parts_in_span)
    ratio = (len(covered) / len(open_in_span)) if open_in_span else 0.0
    return {
        "exchange": exchange,
        "compare_span": [str(lo) if lo else None, str(hi) if hi else None],
        "calendar_open_days_in_span": len(open_in_span),
        "kline_partitions_in_span": len(parts_in_span),
        "open_with_partition": len(covered),
        "open_missing_partition": [str(d) for d in missing[:30]],
        "open_missing_partition_count": len(missing),
        "closed_but_partition_exists": [str(d) for d in extra[:30]],
        "closed_but_partition_exists_count": len(extra),
        "coverage_open_with_data": ratio,
        "note": (
            "shadow_only; missing partitions may mean incomplete backfill, "
            "not calendar error"
        ),
    }
