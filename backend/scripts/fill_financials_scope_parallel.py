#!/usr/bin/env python3
"""Parallel public financials fill for a scope (only symbols missing or shallow)."""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import polars as pl

from app.config import settings
from app.services import preferences
from app.services.free_sources.financials_public import (
    FINANCIAL_TABLES,
    fetch_financials_symbol,
    merge_write_financial_table,
    sync_shares_snapshot,
)
from app.services.free_sources.http_resilience import ResilientHttpClient
from app.services.universe_scope import resolve_symbols


def _counts(data_dir: Path, table: str = "income") -> dict[str, int]:
    path = data_dir / "financials" / table / "part.parquet"
    if not path.exists():
        return {}
    df = pl.read_parquet(path)
    if df.is_empty() or "symbol" not in df.columns:
        return {}
    return {r["symbol"]: int(r["len"]) for r in df.group_by("symbol").len().to_dicts()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="CSI500")
    ap.add_argument("--min-periods", type=int, default=0)
    ap.add_argument("--max-periods", type=int, default=0)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--flush-every", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-missing", action="store_true", default=True)
    args = ap.parse_args()

    data_dir = Path(settings.data_dir)
    target = args.min_periods or preferences.get_financial_max_periods()
    mp = args.max_periods or preferences.get_financial_max_periods()
    syms = resolve_symbols(args.scope, data_dir=data_dir, default="CSI500")
    counts = _counts(data_dir, "income")
    bcounts = _counts(data_dir, "balance_sheet")
    need = [s for s in syms if counts.get(s, 0) < target or bcounts.get(s, 0) < target]
    if args.limit:
        need = need[: args.limit]
    print(
        f"scope={args.scope} target>={target} max_periods={mp} need={len(need)}/{len(syms)} workers={args.workers}",
        flush=True,
    )
    if not need:
        print("nothing to fill", flush=True)
        sync_shares_snapshot(data_dir, symbols=syms)
        return 0

    tables = ("income", "balance_sheet", "cash_flow", "metrics")

    def one(sym: str):
        c = ResilientHttpClient(default_timeout=30)
        try:
            return sym, fetch_financials_symbol(sym, tables=tables, max_periods=mp, client=c), None
        except Exception as e:  # noqa: BLE001
            return sym, {}, e

    buckets = {t: [] for t in tables}
    ok = fail = pending = 0
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = [ex.submit(one, s) for s in need]
        done = 0
        for fut in as_completed(futs):
            sym, got, err = fut.result()
            done += 1
            if err or not got:
                fail += 1
                print(f" fail {sym} {err}", flush=True)
            else:
                ok += 1
                pending += 1
                for t, df in got.items():
                    if df is not None and not df.is_empty() and t in buckets:
                        buckets[t].append(df)
                if pending >= args.flush_every:
                    for t, frames in buckets.items():
                        if frames:
                            n = merge_write_financial_table(
                                pl.concat(frames, how="diagonal_relaxed"), data_dir, t
                            )
                            print(f" flush {t} rows={n}", flush=True)
                            frames.clear()
                    pending = 0
            if done % 10 == 0 or done == len(need):
                elapsed = time.perf_counter() - t0
                print(
                    f" progress {done}/{len(need)} ok={ok} fail={fail} "
                    f"elapsed={elapsed:.0f}s rate={done/elapsed if elapsed else 0:.2f}/s",
                    flush=True,
                )
    if pending:
        for t, frames in buckets.items():
            if frames:
                n = merge_write_financial_table(pl.concat(frames, how="diagonal_relaxed"), data_dir, t)
                print(f" flush final {t} rows={n}", flush=True)
    sync_shares_snapshot(data_dir, symbols=syms)
    counts2 = _counts(data_dir, "income")
    still = [s for s in syms if counts2.get(s, 0) < target]
    vals = [counts2.get(s, 0) for s in syms] or [0]
    import statistics

    print(
        f"done ok={ok} fail={fail} income_med={statistics.median(vals)} "
        f"min={min(vals)} max={max(vals)} still_below={len(still)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
