#!/usr/bin/env python3
"""Re-fetch income/balance for symbols missing expense/detail fields.

Incremental: merges every --flush-every symbols so a kill does not lose progress.

Done criteria (industry-aware):
  income detail: selling_expense OR admin_expense OR non_operating_income OR interest_income
  balance detail: retained_earnings OR share_capital
  symbol done iff both sides satisfied (or income-only if balance file absent)
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
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

INCOME_DETAIL_ANY = (
    "selling_expense",
    "admin_expense",
    "rd_expense",
    "financial_expense",
    "non_operating_income",
    "interest_income",
)
BALANCE_DETAIL_ANY = (
    "retained_earnings",
    "share_capital",
    "intangible_assets",
    "minority_interest",
)


def _symbols_with_any(path: Path, cols: tuple[str, ...]) -> set[str]:
    if not path.exists():
        return set()
    df = pl.read_parquet(path)
    have: set[str] = set()
    for c in cols:
        if c in df.columns:
            have |= set(df.filter(pl.col(c).is_not_null())["symbol"].unique().to_list())
    return have


def _need_symbols(scope: str, data_dir: Path) -> list[str]:
    syms = resolve_symbols(scope, data_dir=data_dir, default="CSI300")
    inc_have = _symbols_with_any(data_dir / "financials" / "income" / "part.parquet", INCOME_DETAIL_ANY)
    bal_path = data_dir / "financials" / "balance_sheet" / "part.parquet"
    if bal_path.exists():
        bal_have = _symbols_with_any(bal_path, BALANCE_DETAIL_ANY)
        done = inc_have & bal_have
    else:
        done = inc_have
    return [s for s in syms if s not in done]


def _flush(buckets: dict[str, list[pl.DataFrame]], data_dir: Path) -> dict[str, int]:
    rows: dict[str, int] = {}
    for t, frames in buckets.items():
        if not frames:
            continue
        n = merge_write_financial_table(pl.concat(frames, how="diagonal_relaxed"), data_dir, t)
        rows[t] = n
        frames.clear()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="CSI300")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-periods", type=int, default=0)
    ap.add_argument("--flush-every", type=int, default=5, help="merge to parquet every N ok symbols")
    args = ap.parse_args()

    data_dir = Path(settings.data_dir)
    need = _need_symbols(args.scope, data_dir)
    if args.limit:
        need = need[: args.limit]
    mp = args.max_periods or preferences.get_financial_max_periods()
    flush_every = max(1, int(args.flush_every))
    print(
        f"scope={args.scope} need={len(need)} max_periods={mp} flush_every={flush_every} workers={args.workers}",
        flush=True,
    )
    if not need:
        print("nothing to backfill", flush=True)
        n = sync_shares_snapshot(
            data_dir, symbols=resolve_symbols(args.scope, data_dir=data_dir, default="CSI300")
        )
        print(f"shares={n}", flush=True)
        return 0

    def one(sym: str):
        c = ResilientHttpClient(default_timeout=25)
        try:
            got = fetch_financials_symbol(
                sym,
                tables=("income", "balance_sheet", "cash_flow", "metrics"),
                max_periods=mp,
                client=c,
            )
            return sym, got, None
        except Exception as e:  # noqa: BLE001
            return sym, {}, e

    ok = fail = 0
    buckets: dict[str, list[pl.DataFrame]] = {
        t: [] for t in ("income", "balance_sheet", "cash_flow", "metrics")
    }
    pending_ok = 0
    t0 = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            futs = [ex.submit(one, s) for s in need]
            done = 0
            for fut in as_completed(futs):
                try:
                    sym, got, err = fut.result()
                except Exception as e:  # noqa: BLE001
                    done += 1
                    fail += 1
                    print(f" fail <future> {e}", flush=True)
                    continue
                done += 1
                if err or not got:
                    fail += 1
                    print(f" fail {sym} {err}", flush=True)
                else:
                    ok += 1
                    pending_ok += 1
                    for t, df in got.items():
                        if df is not None and not df.is_empty() and t in buckets:
                            buckets[t].append(df)
                    if pending_ok >= flush_every:
                        rows = _flush(buckets, data_dir)
                        print(f" flush ok_batch={pending_ok} rows={rows}", flush=True)
                        pending_ok = 0
                if done % 10 == 0 or done == len(need):
                    elapsed = time.perf_counter() - t0
                    rate = done / elapsed if elapsed > 0 else 0
                    print(
                        f" progress {done}/{len(need)} ok={ok} fail={fail} "
                        f"elapsed={elapsed:.0f}s rate={rate:.2f}/s",
                        flush=True,
                    )
        if pending_ok:
            rows = _flush(buckets, data_dir)
            print(f" flush final ok_batch={pending_ok} rows={rows}", flush=True)
    except Exception:
        # emergency flush whatever we have
        print("FATAL during backfill:", flush=True)
        traceback.print_exc()
        try:
            if pending_ok:
                rows = _flush(buckets, data_dir)
                print(f" emergency flush rows={rows}", flush=True)
        except Exception:
            traceback.print_exc()
        return 2

    scope_syms = resolve_symbols(args.scope, data_dir=data_dir, default="CSI300")
    n = sync_shares_snapshot(data_dir, symbols=scope_syms)
    # final coverage report
    remaining = _need_symbols(args.scope, data_dir)
    print(
        f"shares={n} done ok={ok} fail={fail} remaining_need={len(remaining)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
