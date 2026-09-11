#!/usr/bin/env python3
"""Backfill official daily/enriched bars for CSI1800 + watchlist from 2026-08-03.

Default is dry-run. Pass --apply to fetch public EOD quotes and merge them
into existing August partitions, then recompute enriched for the same dates.
Does not rewrite 2019-07-05..2026-07-31 history and does not change
financial/adj/minute schedules.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (REPO_ROOT / "backend", REPO_ROOT):
    if (_candidate / "app").is_dir():
        sys.path.insert(0, str(_candidate))
        break

import polars as pl  # noqa: E402

from app.indicators.pipeline import run_pipeline  # noqa: E402
from app.services.atomic_io import atomic_write_parquet  # noqa: E402
from app.services.kline_sync import sync_daily_by_public_quotes  # noqa: E402
from app.services.universe_scope import resolve_symbols  # noqa: E402
from app.tickflow.repository import DataStore, KlineRepository  # noqa: E402

DEFAULT_START = date(2026, 8, 3)


def _partition_dates(data_dir: Path, start: date, end: date | None) -> list[date]:
    daily_dir = data_dir / "kline_daily"
    out: list[date] = []
    if not daily_dir.exists():
        return out
    last = end or date(2099, 1, 1)
    for path in sorted(daily_dir.glob("date=*")):
        try:
            day = date.fromisoformat(path.name[5:])
        except ValueError:
            continue
        if start <= day <= last:
            out.append(day)
    return out


def _symbols_in_partition(data_dir: Path, day: date) -> set[str]:
    path = data_dir / "kline_daily" / f"date={day.isoformat()}" / "part.parquet"
    if not path.exists():
        return set()
    frame = pl.read_parquet(path, columns=["symbol"])
    return {str(s).strip().upper() for s in frame["symbol"].to_list() if s}


def _latest_symbol_date(data_dir: Path, symbol: str) -> str | None:
    matches: list[date] = []
    daily_dir = data_dir / "kline_daily"
    if not daily_dir.exists():
        return None
    for path in daily_dir.glob("date=*"):
        part = path / "part.parquet"
        if not part.exists():
            continue
        try:
            day = date.fromisoformat(path.name[5:])
        except ValueError:
            continue
        frame = pl.read_parquet(part, columns=["symbol"])
        if symbol in {str(s).strip().upper() for s in frame["symbol"].to_list()}:
            matches.append(day)
    return max(matches).isoformat() if matches else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--end", default=None)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir.expanduser().resolve()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else None
    dates = _partition_dates(data_dir, start, end)
    universe = resolve_symbols(
        "CSI1800",
        data_dir=data_dir,
        default="CSI1800",
        include_watchlist=True,
        refresh_pools_if_missing=False,
    )
    plan = []
    missing_total: set[str] = set()
    prior_frames: dict[str, pl.DataFrame] = {}
    for day in dates:
        have = _symbols_in_partition(data_dir, day)
        missing = [symbol for symbol in universe if symbol not in have]
        missing_total.update(missing)
        plan.append({"date": day.isoformat(), "have": len(have), "missing": len(missing)})
        part = data_dir / "kline_daily" / f"date={day.isoformat()}" / "part.parquet"
        if part.exists():
            prior_frames[day.isoformat()] = pl.read_parquet(part)
    preview = {
        "scope": "CSI1800",
        "universe": len(universe),
        "contains": {
            "300750.SZ": "300750.SZ" in universe,
            "600519.SH": "600519.SH" in universe,
            "000001.SZ": "000001.SZ" in universe,
        },
        "dates": plan,
        "unique_missing_symbols": len(missing_total),
        "apply": bool(args.apply),
    }
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    if not args.apply:
        return 0

    repo = KlineRepository(DataStore(data_dir))
    written = []
    for item in plan:
        day = date.fromisoformat(item["date"])
        have = _symbols_in_partition(data_dir, day)
        missing = [symbol for symbol in universe if symbol not in have]
        if not missing:
            written.append({"date": item["date"], "rows": 0, "skipped": True})
            continue
        result = sync_daily_by_public_quotes(missing, repo, trade_date=day)
        part = data_dir / "kline_daily" / f"date={day.isoformat()}" / "part.parquet"
        prior = prior_frames.get(item["date"])
        if prior is not None and part.exists():
            current = pl.read_parquet(part)
            merged = pl.concat([prior, current], how="diagonal_relaxed").unique(
                subset=["symbol", "date"], keep="last"
            ).sort(["symbol", "date"])
            atomic_write_parquet(merged, part)
            current_syms = {str(s).strip().upper() for s in merged["symbol"].to_list()}
            prior_syms = {str(s).strip().upper() for s in prior["symbol"].to_list()}
            if not prior_syms.issubset(current_syms):
                raise RuntimeError(f"{day} backfill overwrote prior symbols")
        written.append({"date": item["date"], **result, "missing_requested": len(missing)})

    if missing_total:
        run_pipeline(data_dir=data_dir, symbols=sorted(missing_total), new_dates_only=False)
    checks = {
        symbol: _latest_symbol_date(data_dir, symbol)
        for symbol in ("300750.SZ", "600519.SH", "000001.SZ")
    }
    print(json.dumps({"written": written, "latest": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
