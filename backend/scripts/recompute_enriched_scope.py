#!/usr/bin/env python3
"""Recompute kline_daily_enriched for symbols in a scope (default CSI300 with adj).

Uses existing kline_daily + adj_factor; merges per-date into enriched partitions.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="CSI300")
    ap.add_argument("--only-with-adj", action="store_true", default=True,
                    help="only symbols that have adj_factor rows (default on)")
    ap.add_argument("--all-in-scope", action="store_true",
                    help="recompute all scope symbols even without adj")
    ap.add_argument("--data-dir", default="")
    args = ap.parse_args()

    import polars as pl
    from app.config import settings
    from app.indicators.pipeline import run_pipeline
    from app.services.universe_scope import resolve_symbols, normalize_scope, SCOPE_LABELS

    data_dir = Path(args.data_dir) if args.data_dir else Path(settings.data_dir)
    scope = normalize_scope(args.scope, default="CSI300")
    syms = resolve_symbols(scope, data_dir=data_dir, default="CSI300", refresh_pools_if_missing=True)
    print(f"scope={scope} ({SCOPE_LABELS.get(scope)}) symbols={len(syms)}", flush=True)

    adj_path = data_dir / "adj_factor" / "all.parquet"
    if not adj_path.exists():
        print("adj_factor missing", file=sys.stderr)
        return 2
    adj = pl.read_parquet(adj_path)
    with_adj = set(adj["symbol"].unique().to_list())
    if args.all_in_scope:
        targets = list(syms)
    else:
        targets = [s for s in syms if s in with_adj]
    print(f"targets={len(targets)} (with_adj_in_scope={len(set(syms)&with_adj)})", flush=True)
    if not targets:
        print("nothing to recompute")
        return 0

    # Spot-check before
    def sample_moutai():
        enr = data_dir / "kline_daily_enriched"
        parts = sorted(enr.glob("date=*"))
        if not parts:
            return None
        # find a 2024 partition if any
        for p in parts:
            if p.name.startswith("date=2024-"):
                for f in p.rglob("*.parquet"):
                    df = pl.read_parquet(f)
                    sub = df.filter(pl.col("symbol") == "600519.SH")
                    if sub.height and "raw_close" in sub.columns:
                        r = sub.row(0, named=True)
                        return {"date": str(r["date"]), "close": r["close"], "raw_close": r["raw_close"]}
        # fallback latest
        for f in parts[-1].rglob("*.parquet"):
            df = pl.read_parquet(f)
            sub = df.filter(pl.col("symbol") == "600519.SH")
            if sub.height and "raw_close" in sub.columns:
                r = sub.row(0, named=True)
                return {"date": str(r["date"]), "close": r["close"], "raw_close": r["raw_close"]}
        return None

    before = sample_moutai()
    print("before_sample", before, flush=True)

    t0 = time.time()
    def prog(cur, tot):
        if cur == 1 or cur == tot or cur % 5 == 0:
            print(f"  enriched batch {cur}/{tot}", flush=True)

    written = run_pipeline(data_dir=data_dir, symbols=targets, on_batch_done=prog)
    elapsed = round(time.time() - t0, 1)
    after = sample_moutai()
    print("after_sample", after, flush=True)

    # validate adj effect for moutai if possible
    ok_adj = None
    enr = data_dir / "kline_daily_enriched"
    # Prefer older partitions within available history (this desk often keeps ~1y daily)
    candidates = (
        sorted(enr.glob("date=2025-07-*"))[:8]
        + sorted(enr.glob("date=2025-08-*"))[:5]
        + sorted(enr.glob("date=2025-12-*"))[:5]
    )
    diffs = checked = 0
    sample = None
    for p in candidates:
        f = next(p.rglob("*.parquet"), None)
        if not f:
            continue
        df = pl.read_parquet(f)
        sub = df.filter(pl.col("symbol") == "600519.SH")
        if sub.height and "raw_close" in sub.columns:
            checked += 1
            close_v = float(sub["close"][0])
            raw_v = float(sub["raw_close"][0])
            if abs(close_v - raw_v) > 1e-6:
                diffs += 1
                if sample is None:
                    sample = {"date": str(sub["date"][0]), "close": close_v, "raw_close": raw_v}
    # CSI300-wide check on one historical date
    wide = None
    for p in sorted(enr.glob("date=2025-07-03"))[:1]:
        f = next(p.rglob("*.parquet"), None)
        if f:
            df = pl.read_parquet(f)
            pool = set(targets)
            sub = df.filter(pl.col("symbol").is_in(list(pool)))
            if "raw_close" in sub.columns and sub.height:
                n_diff = sub.filter((pl.col("close") - pl.col("raw_close")).abs() > 1e-6).height
                wide = {"date": "2025-07-03", "csi300_rows": sub.height, "with_adj_diff": n_diff}
    ok_adj = {
        "moutai_checked_parts": checked,
        "moutai_parts_with_diff": diffs,
        "moutai_sample": sample,
        "csi300_wide": wide,
    }

    out = {
        "scope": scope,
        "targets": len(targets),
        "written_rows": written,
        "elapsed_s": elapsed,
        "before_sample": before,
        "after_sample": after,
        "adj_effect_check": ok_adj,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str), flush=True)
    Path("/tmp/one-trading-fill/enriched_recompute.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2, default=str)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
