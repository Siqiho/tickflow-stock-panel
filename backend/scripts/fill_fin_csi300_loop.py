#!/usr/bin/env python3
"""Resume-safe CSI300 financials fill with short batches and hard timeouts."""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutTimeout
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
)
from app.services.free_sources.http_resilience import ResilientHttpClient
from app.services.universe_scope import resolve_symbols


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def coverage(data_dir: Path, pool: set[str]) -> dict[str, int]:
    out = {}
    for t in FINANCIAL_TABLES:
        p = data_dir / "financials" / t / "part.parquet"
        if not p.exists():
            out[t] = 0
            continue
        sy = set(pl.read_parquet(p)["symbol"].unique().to_list())
        out[t] = len(sy & pool)
    return out


def missing_symbols(data_dir: Path, syms: list[str]) -> list[str]:
    present = {t: set() for t in FINANCIAL_TABLES}
    for t in FINANCIAL_TABLES:
        p = data_dir / "financials" / t / "part.parquet"
        if p.exists():
            present[t] = set(pl.read_parquet(p)["symbol"].unique().to_list())
    return [s for s in syms if not all(s in present[t] for t in FINANCIAL_TABLES)]


def main() -> int:
    preferences.save({
        "financial_provider": "public",
        "public_data_scope": "CSI300",
        "adj_factor_provider": "public",
        "pool_provider": "public",
        "pipeline_universe_scope": "ALL",
    })
    data_dir = Path(settings.data_dir)
    syms = resolve_symbols("CSI300", data_dir=data_dir, default="CSI300", refresh_pools_if_missing=True)
    pool = set(syms)
    log(f"start CSI300 n={len(syms)} cov={coverage(data_dir, pool)}")

    batch_size = 8
    workers = 4
    round_id = 0
    stall = 0
    prev_min = -1

    while True:
        miss = missing_symbols(data_dir, syms)
        cov = coverage(data_dir, pool)
        mn = min(cov.values()) if cov else 0
        log(f"round={round_id} missing={len(miss)} cov={cov}")
        if not miss or mn >= 300:
            log("COMPLETE")
            return 0
        if mn == prev_min:
            stall += 1
        else:
            stall = 0
            prev_min = mn
        if stall >= 5:
            # rotate queue to avoid permanent head-of-line blocker
            miss = miss[batch_size:] + miss[:batch_size]
            log(f"stall rotate head, new_head={miss[:3]}")
            stall = 0

        part = miss[:batch_size]
        round_id += 1

        def one(sym: str):
            c = ResilientHttpClient(default_timeout=18.0)
            try:
                return sym, fetch_financials_symbol(sym, max_periods=preferences.get_financial_max_periods(), client=c), None
            except Exception as e:  # noqa: BLE001
                return sym, {}, e

        buckets = {t: [] for t in FINANCIAL_TABLES}
        ok = fail = 0
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(one, s): s for s in part}
            try:
                for fut in as_completed(futs, timeout=90):
                    sym, got, err = fut.result(timeout=1)
                    if err or not got:
                        fail += 1
                        log(f"  fail {sym} {err}")
                        continue
                    anyr = False
                    for t, df in got.items():
                        if df is not None and not df.is_empty():
                            buckets[t].append(df)
                            anyr = True
                    if anyr:
                        ok += 1
                    else:
                        fail += 1
                        log(f"  empty {sym}")
            except FutTimeout:
                log("  batch timeout — merge partial and continue")
                # cancel remaining
                for fut in futs:
                    fut.cancel()

        for t, frames in buckets.items():
            if frames:
                merge_write_financial_table(
                    pl.concat(frames, how="diagonal_relaxed"), data_dir, t
                )
        log(f"  batch ok={ok} fail={fail} sec={time.time()-t0:.1f} cov={coverage(data_dir, pool)}")
        time.sleep(0.15)


if __name__ == "__main__":
    raise SystemExit(main())
