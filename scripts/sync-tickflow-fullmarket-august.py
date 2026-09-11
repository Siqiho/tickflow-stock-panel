#!/usr/bin/env python3
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

from app.indicators.pipeline import run_pipeline
from app.services.kline_sync import sync_daily_batch
from app.services.universe_scope import resolve_symbols
from app.tickflow.client import current_endpoint, current_mode
from app.tickflow.repository import DataStore, KlineRepository

SHANGHAI = timezone(timedelta(hours=8))
DEFAULT_START = date(2026, 8, 3)
DEFAULT_END = date(2026, 8, 14)
BATCH_SIZE = 100
RPM = 60


def _symbols_in_partition(data_dir: Path, day: date) -> set[str]:
    path = data_dir / "kline_daily" / f"date={day.isoformat()}" / "part.parquet"
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
    parser.add_argument("--log", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir.expanduser().resolve()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    stamp = datetime.now(SHANGHAI).strftime("%Y%m%d-%H%M%S")
    log_path = args.log or (data_dir / "logs" / f"tickflow-fullmarket-august-{stamp}.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    inst = pl.read_parquet(data_dir / "instruments" / "instruments.parquet", columns=["symbol"])
    instruments = sorted({str(s).strip().upper() for s in inst["symbol"].to_list() if s})
    universe = set(resolve_symbols("CSI1800", data_dir=data_dir, include_watchlist=True, refresh_pools_if_missing=False))
    latest = _symbols_in_partition(data_dir, end)
    jul = _symbols_in_partition(data_dir, date(2026, 7, 31))
    targets = sorted((set(instruments) | jul) - latest)
    chunks = [targets[i:i + args.batch_size] for i in range(0, len(targets), args.batch_size)]
    if args.limit_batches:
        chunks = chunks[: args.limit_batches]
    preview = {
        "started_at": datetime.now(SHANGHAI).isoformat(),
        "mode": current_mode(),
        "endpoint": current_endpoint(),
        "pipeline_scope_unchanged": "CSI1800+watchlist",
        "instruments": len(instruments),
        "jul31": len(jul),
        "latest_date": end.isoformat(),
        "latest_rows": len(latest),
        "universe_kept": len(universe),
        "targets": len(targets),
        "batch_size": args.batch_size,
        "rpm": args.rpm,
        "batches": len(chunks),
        "window": [start.isoformat(), end.isoformat()],
        "apply": bool(args.apply),
        "log": str(log_path),
    }
    print(json.dumps(preview, ensure_ascii=False, indent=2), flush=True)
    log_path.write_text(json.dumps({"event": "preview", **preview}, ensure_ascii=False) + "\n", encoding="utf-8")
    if not args.apply:
        return 0

    repo = KlineRepository(DataStore(data_dir))
    start_time = datetime(start.year, start.month, start.day, 0, 0, tzinfo=SHANGHAI)
    end_time = datetime(end.year, end.month, end.day, 23, 59, tzinfo=SHANGHAI)
    interval = 60.0 / max(1, args.rpm)
    wall0 = time.perf_counter()
    batch_stats = []
    all_ok: set[str] = set()
    for i, chunk in enumerate(chunks, start=1):
        t0 = time.perf_counter()
        err = None
        rows = 0
        dates = []
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
                    repo.append_daily(df)
                    all_ok.update(str(s).strip().upper() for s in df["symbol"].to_list() if s)
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
        elapsed = time.perf_counter() - t0
        rec = {
            "event": "batch",
            "batch": i,
            "batches": len(chunks),
            "symbols": len(chunk),
            "sample": chunk[:3],
            "rows": rows,
            "dates": dates,
            "seconds": round(elapsed, 3),
            "error": err,
            "at": datetime.now(SHANGHAI).isoformat(),
        }
        batch_stats.append(rec)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        if i < len(chunks):
            sleep_for = max(0.0, interval - elapsed)
            if sleep_for:
                time.sleep(sleep_for)

    enrich_seconds = None
    if all_ok:
        t1 = time.perf_counter()
        run_pipeline(data_dir=data_dir, symbols=sorted(all_ok), new_dates_only=False)
        enrich_seconds = round(time.perf_counter() - t1, 3)
    summary = {
        "event": "summary",
        "finished_at": datetime.now(SHANGHAI).isoformat(),
        "wall_seconds": round(time.perf_counter() - wall0, 3),
        "batches_ok": sum(1 for r in batch_stats if not r["error"] and r["rows"] > 0),
        "batches_failed": sum(1 for r in batch_stats if r["error"]),
        "symbols_written": len(all_ok),
        "rows_written": sum(r["rows"] for r in batch_stats),
        "enrich_seconds": enrich_seconds,
        "latest_after": len(_symbols_in_partition(data_dir, end)),
        "log": str(log_path),
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(summary, ensure_ascii=False) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
