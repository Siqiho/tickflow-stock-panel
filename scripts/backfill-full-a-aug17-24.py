#!/usr/bin/env python3
"""Backfill official daily/enriched bars for full A-share from 2026-08-17 to 2026-08-24.

Merges TickFlow free historical daily bars into existing CSI1800 partitions
without dropping prior symbols. Enriched is recomputed only for the window
and merged back. Does not rewrite 2019-07-05..2026-08-14 history and does
not change financial/adj/minute schedules by itself.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (REPO_ROOT / "backend", REPO_ROOT):
    if (_candidate / "app").is_dir():
        sys.path.insert(0, str(_candidate))
        break

import polars as pl

from app.indicators.pipeline import (
    compute_enriched,
    _load_factors,
    _select_storage_cols,
    _write_enriched_lineage,
)
from app.services.atomic_io import atomic_write_parquet, write_lineage_record
from app.services.kline_sync import sync_daily_batch
from app.tickflow.client import current_endpoint, current_mode
from app.tickflow.repository import DataStore, KlineRepository

SHANGHAI = timezone(timedelta(hours=8))
DEFAULT_START = date(2026, 8, 17)
DEFAULT_END = date(2026, 8, 24)
WINDOW_DATES = [
    date(2026, 8, 17),
    date(2026, 8, 18),
    date(2026, 8, 19),
    date(2026, 8, 20),
    date(2026, 8, 21),
    date(2026, 8, 24),
]
BATCH_SIZE = 100
RPM = 60
WARMUP_DAYS = 180


def _partition_path(data_dir: Path, table: str, day: date) -> Path:
    return data_dir / table / f"date={day.isoformat()}" / "part.parquet"


def _symbols_in_partition(data_dir: Path, table: str, day: date) -> set[str]:
    path = _partition_path(data_dir, table, day)
    if not path.exists():
        return set()
    frame = pl.read_parquet(path, columns=["symbol"])
    return {str(s).strip().upper() for s in frame["symbol"].to_list() if s}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--end", default=DEFAULT_END.isoformat())
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--rpm", type=int, default=RPM)
    parser.add_argument("--limit-batches", type=int, default=0)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--skip-enrich", action="store_true")
    parser.add_argument("--log", type=Path, default=None)
    return parser.parse_args()


def _log(path: Path, rec: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False), flush=True)


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir.expanduser().resolve()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    window = [day for day in WINDOW_DATES if start <= day <= end]
    stamp = datetime.now(SHANGHAI).strftime("%Y%m%d-%H%M%S")
    log_path = args.log or (data_dir / "logs" / f"tickflow-full-a-aug17-24-{stamp}.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    inst = pl.read_parquet(data_dir / "instruments" / "instruments.parquet", columns=["symbol"])
    instruments = sorted({str(s).strip().upper() for s in inst["symbol"].to_list() if s})
    progress_day = window[0] if window else end
    already = _symbols_in_partition(data_dir, "kline_daily", progress_day)
    targets = sorted(set(instruments) - already)
    chunks = [targets[i:i + args.batch_size] for i in range(0, len(targets), args.batch_size)]
    if args.limit_batches:
        chunks = chunks[: args.limit_batches]
    prior_counts = {
        day.isoformat(): len(_symbols_in_partition(data_dir, "kline_daily", day))
        for day in window
    }
    preview = {
        "event": "preview",
        "started_at": datetime.now(SHANGHAI).isoformat(),
        "mode": current_mode(),
        "endpoint": current_endpoint(),
        "instruments": len(instruments),
        "window": [d.isoformat() for d in window],
        "prior_counts": prior_counts,
        "targets": len(targets),
        "batch_size": args.batch_size,
        "rpm": args.rpm,
        "batches": len(chunks),
        "apply": bool(args.apply),
        "skip_fetch": bool(args.skip_fetch),
        "skip_enrich": bool(args.skip_enrich),
        "log": str(log_path),
    }
    log_path.write_text(json.dumps(preview, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(preview, ensure_ascii=False, indent=2), flush=True)
    if not args.apply:
        return 0

    repo = KlineRepository(DataStore(data_dir))
    start_time = datetime(start.year, start.month, start.day, 0, 0, tzinfo=SHANGHAI)
    end_time = datetime(end.year, end.month, end.day, 23, 59, tzinfo=SHANGHAI)
    interval = 60.0 / max(1, args.rpm)
    wall0 = time.perf_counter()
    all_ok: set[str] = set()
    if not args.skip_fetch:
        for i, chunk in enumerate(chunks, start=1):
            t0 = time.perf_counter()
            err = None
            rows = 0
            dates: list[str] = []
            try:
                df = sync_daily_batch(
                    chunk,
                    batch_size=len(chunk),
                    rpm=None,
                    start_time=start_time,
                    end_time=end_time,
                )
                if not df.is_empty():
                    df = df.filter((pl.col("date") >= start) & (pl.col("date") <= end))
                    rows = int(df.height)
                    dates = sorted({d.isoformat() for d in df["date"].to_list() if d})
                    if rows:
                        prior = {
                            day: _symbols_in_partition(data_dir, "kline_daily", day)
                            for day in window
                        }
                        repo.append_daily(df)
                        for day, before in prior.items():
                            after = _symbols_in_partition(data_dir, "kline_daily", day)
                            if not before.issubset(after):
                                raise RuntimeError(f"{day} backfill dropped prior symbols")
                        all_ok.update(str(s).strip().upper() for s in df["symbol"].to_list() if s)
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {exc}"
            rec = {
                "event": "batch",
                "batch": i,
                "batches": len(chunks),
                "symbols": len(chunk),
                "sample": chunk[:3],
                "rows": rows,
                "dates": dates,
                "seconds": round(time.perf_counter() - t0, 3),
                "error": err,
                "at": datetime.now(SHANGHAI).isoformat(),
            }
            _log(log_path, rec)
            if i < len(chunks):
                sleep_for = max(0.0, interval - rec["seconds"])
                if sleep_for:
                    time.sleep(sleep_for)

    if not args.skip_fetch and date.today() in window:
        snap_path = data_dir / "quote_snapshot" / "asset_type=stock" / f"date={date.today().isoformat()}" / "part.parquet"
        today = date.today()
        if snap_path.exists():
            have = _symbols_in_partition(data_dir, "kline_daily", today)
            snap = pl.read_parquet(snap_path)
            need = set(instruments) - have
            extra = snap.filter(pl.col("symbol").is_in(list(need)))
            keep = [c for c in ["symbol", "date", "open", "high", "low", "close", "volume", "amount"] if c in extra.columns]
            extra = extra.select(keep)
            if "date" in extra.columns:
                extra = extra.with_columns(pl.lit(today).alias("date"))
            extra = extra.filter(pl.col("close").is_not_null() & (pl.col("close") > 0))
            if not extra.is_empty():
                prior = _symbols_in_partition(data_dir, "kline_daily", today)
                repo.append_daily(extra)
                after = _symbols_in_partition(data_dir, "kline_daily", today)
                if not prior.issubset(after):
                    raise RuntimeError("today snapshot merge dropped prior symbols")
                rec = {
                    "event": "today_snapshot_merge",
                    "date": today.isoformat(),
                    "added": len(after) - len(prior),
                    "after": len(after),
                    "snapshot_rows": extra.height,
                }
                _log(log_path, rec)

    enrich_seconds = None
    enrich_written = 0
    if not args.skip_enrich:
        t1 = time.perf_counter()
        factors = _load_factors(data_dir / "adj_factor" / "all.parquet")
        instruments_df = pl.read_parquet(data_dir / "instruments" / "instruments.parquet")
        warmup_start = start - timedelta(days=WARMUP_DAYS)
        daily_glob = str(data_dir / "kline_daily" / "**" / "*.parquet")
        raw = (
            pl.scan_parquet(daily_glob)
            .filter((pl.col("date") >= warmup_start) & (pl.col("date") <= end))
            .select([c for c in ["symbol", "date", "open", "high", "low", "close", "volume", "amount"] ])
            .sort(["symbol", "date"])
            .collect()
        )
        enriched = compute_enriched(raw, factors=factors, instruments=instruments_df)
        window_df = enriched.filter(pl.col("date").is_in(window))
        for day in window:
            part = _partition_path(data_dir, "kline_daily_enriched", day)
            incoming = _select_storage_cols(window_df.filter(pl.col("date") == day))
            if incoming.is_empty():
                continue
            prior_syms = _symbols_in_partition(data_dir, "kline_daily_enriched", day)
            if part.exists():
                existing = pl.read_parquet(part)
                merged = pl.concat([existing, incoming], how="diagonal_relaxed").unique(
                    subset=["symbol", "date"], keep="last"
                ).sort(["symbol", "date"])
            else:
                merged = incoming.sort(["symbol", "date"])
            after_syms = {str(s).strip().upper() for s in merged["symbol"].to_list() if s}
            if prior_syms and not prior_syms.issubset(after_syms):
                raise RuntimeError(f"{day} enriched merge dropped prior symbols")
            part.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_parquet(merged, part)
            _write_enriched_lineage(
                data_dir,
                part,
                row_count=merged.height,
                scope="ALL",
                calculation_mode="window_merge_full_a",
                quality="pending_gate",
            )
            write_lineage_record(
                data_dir,
                "kline_daily",
                {
                    "date": day.isoformat(),
                    "source": "tickflow_free_hist_daily_merged",
                    "unit_version": "canonical_daily_v1",
                    "quality": "pending_gate",
                    "row_count": len(_symbols_in_partition(data_dir, "kline_daily", day)),
                    "unique_symbol_count": len(_symbols_in_partition(data_dir, "kline_daily", day)),
                    "scope": "ALL",
                    "target_artifact": f"kline_daily/date={day.isoformat()}/part.parquet",
                },
            )
            enrich_written += int(merged.height)
        enrich_seconds = round(time.perf_counter() - t1, 3)

    after_counts = {
        day.isoformat(): {
            "daily": len(_symbols_in_partition(data_dir, "kline_daily", day)),
            "enriched": len(_symbols_in_partition(data_dir, "kline_daily_enriched", day)),
        }
        for day in window
    }
    summary = {
        "event": "summary",
        "finished_at": datetime.now(SHANGHAI).isoformat(),
        "wall_seconds": round(time.perf_counter() - wall0, 3),
        "symbols_written": len(all_ok),
        "enrich_seconds": enrich_seconds,
        "enrich_written": enrich_written,
        "after_counts": after_counts,
        "log": str(log_path),
    }
    _log(log_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
