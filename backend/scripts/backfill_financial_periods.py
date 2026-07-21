#!/usr/bin/env python3
"""Deepen financial statement periods for a public scope (default CSI300).

Root cause fixed in fetch_statement_table: EM body returns ~5 periods/call;
chunked fetch now honors max_periods. This script re-pulls symbols whose local
period count is below target.
"""
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
    fetch_financials_symbol,
    merge_write_financial_table,
    sync_shares_snapshot,
)
from app.services.free_sources.http_resilience import ResilientHttpClient
from app.services.universe_scope import resolve_symbols

TABLES = ("income", "balance_sheet", "cash_flow", "metrics")


def _period_counts(data_dir: Path, table: str = "income") -> dict[str, int]:
    path = data_dir / "financials" / table / "part.parquet"
    if not path.exists():
        return {}
    df = pl.read_parquet(path)
    if df.is_empty() or "symbol" not in df.columns:
        return {}
    g = df.group_by("symbol").len()
    return {r["symbol"]: int(r["len"]) for r in g.to_dicts()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="CSI300")
    ap.add_argument("--min-periods", type=int, default=0, help="0=use financial_max_periods")
    ap.add_argument("--max-periods", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--flush-every", type=int, default=5)
    args = ap.parse_args()

    data_dir = Path(settings.data_dir)
    target = args.min_periods or preferences.get_financial_max_periods()
    mp = args.max_periods or preferences.get_financial_max_periods()
    syms = resolve_symbols(args.scope, data_dir=data_dir, default="CSI300")
    counts = _period_counts(data_dir, "income")
    # also check balance depth
    bcounts = _period_counts(data_dir, "balance_sheet")
    need = []
    for s in syms:
        if counts.get(s, 0) < target or bcounts.get(s, 0) < target:
            need.append(s)
    if args.limit:
        need = need[: args.limit]
    print(
        f"scope={args.scope} target_periods>={target} max_periods={mp} need={len(need)}/{len(syms)} flush_every={args.flush_every}",
        flush=True,
    )
    if not need:
        print("nothing to deepen", flush=True)
        return 0

    def one(sym: str):
        c = ResilientHttpClient(default_timeout=30)
        try:
            got = fetch_financials_symbol(sym, tables=TABLES, max_periods=mp, client=c)
            return sym, got, None
        except Exception as e:  # noqa: BLE001
            return sym, {}, e

    buckets = {t: [] for t in TABLES}
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
                            n = merge_write_financial_table(pl.concat(frames, how="diagonal_relaxed"), data_dir, t)
                            print(f" flush {t} rows={n}", flush=True)
                            frames.clear()
                    pending = 0
            if done % 10 == 0 or done == len(need):
                elapsed = time.perf_counter() - t0
                print(
                    f" progress {done}/{len(need)} ok={ok} fail={fail} elapsed={elapsed:.0f}s rate={done/elapsed if elapsed else 0:.2f}/s",
                    flush=True,
                )
    if pending:
        for t, frames in buckets.items():
            if frames:
                n = merge_write_financial_table(pl.concat(frames, how="diagonal_relaxed"), data_dir, t)
                print(f" flush final {t} rows={n}", flush=True)
    sync_shares_snapshot(data_dir, symbols=syms)
    counts2 = _period_counts(data_dir, "income")
    still = [s for s in syms if counts2.get(s, 0) < target]
    vals = list(counts2.values()) or [0]
    import statistics
    print(
        f"done ok={ok} fail={fail} income_periods median={statistics.median(vals)} min={min(vals)} max={max(vals)} still_below={len(still)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
