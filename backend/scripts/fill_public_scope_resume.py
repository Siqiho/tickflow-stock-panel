#!/usr/bin/env python3
"""Resume-friendly fill of public adj/financials for a scope (default CSI300)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="CSI300")
    ap.add_argument("--chunk", type=int, default=25)
    ap.add_argument("--max-symbols", type=int, default=0, help="0=all remaining")
    ap.add_argument("--only", choices=["adj", "financials", "both"], default="both")
    ap.add_argument("--max-periods", type=int, default=4)
    ap.add_argument("--adj-pause", type=float, default=0.03)
    ap.add_argument("--fin-pause", type=float, default=0.08)
    args = ap.parse_args()

    import polars as pl
    from app.config import settings
    from app.services import preferences
    from app.services.universe_scope import resolve_symbols, normalize_scope, SCOPE_LABELS
    from app.services.free_sources.adj_factor_public import sync_adj_factor_public
    from app.services.free_sources.financials_public import sync_financials_public
    from app.services.free_sources.http_resilience import ResilientHttpClient

    preferences.save({
        "adj_factor_provider": "public",
        "financial_provider": "public",
        "pool_provider": "public",
        "public_data_scope": normalize_scope(args.scope, default="CSI300"),
    })

    data_dir = Path(settings.data_dir)
    scope = normalize_scope(args.scope, default="CSI300")
    syms = resolve_symbols(scope, data_dir=data_dir, default="CSI300", refresh_pools_if_missing=True)
    print(f"scope={scope} ({SCOPE_LABELS.get(scope)}) total={len(syms)}", flush=True)
    client = ResilientHttpClient(default_timeout=20.0)
    summary: dict = {"scope": scope, "total": len(syms)}

    if args.only in ("adj", "both"):
        adj_path = data_dir / "adj_factor" / "all.parquet"
        have: set[str] = set()
        if adj_path.exists():
            have = set(pl.read_parquet(adj_path)["symbol"].unique().to_list())
        todo = [s for s in syms if s not in have]
        if args.max_symbols > 0:
            todo = todo[: args.max_symbols]
        print(f"adj have={len(have & set(syms))} todo_this_run={len(todo)}", flush=True)
        t0 = time.time()
        for i in range(0, len(todo), args.chunk):
            part = todo[i : i + args.chunk]
            res = sync_adj_factor_public(part, data_dir, pause_s=args.adj_pause, client=client)
            print(
                f"  adj {i + len(part)}/{len(todo)} affected={res.get('symbols_affected_n')}",
                flush=True,
            )
        if adj_path.exists():
            adj = pl.read_parquet(adj_path)
            asy = set(adj["symbol"].unique().to_list())
            summary["adj"] = {
                "covered": len(asy & set(syms)),
                "rows": adj.height,
                "elapsed_s": round(time.time() - t0, 2),
            }
            print("ADJ", summary["adj"], flush=True)

    if args.only in ("financials", "both"):
        fin_path = data_dir / "financials" / "income" / "part.parquet"
        have_f: set[str] = set()
        if fin_path.exists():
            have_f = set(pl.read_parquet(fin_path)["symbol"].unique().to_list())
        # require all 4 tables ideally; use income as progress proxy, refetch missing any table
        missing = []
        tables = ["metrics", "income", "balance_sheet", "cash_flow"]
        present = {t: set() for t in tables}
        for t in tables:
            p = data_dir / "financials" / t / "part.parquet"
            if p.exists():
                present[t] = set(pl.read_parquet(p)["symbol"].unique().to_list())
        for s in syms:
            if not all(s in present[t] for t in tables):
                missing.append(s)
        if args.max_symbols > 0:
            missing = missing[: args.max_symbols]
        print(f"fin complete_proxy_have={len(have_f & set(syms))} missing_this_run={len(missing)}", flush=True)
        t0 = time.time()
        for i in range(0, len(missing), max(1, args.chunk // 2)):
            part = missing[i : i + max(1, args.chunk // 2)]
            res = sync_financials_public(
                part, data_dir, max_periods=args.max_periods, pause_s=args.fin_pause, client=client
            )
            print(
                f"  fin {i + len(part)}/{len(missing)} ok={res.get('symbols_ok_n')} fail={res.get('symbols_fail_n')}",
                flush=True,
            )
        cov = {}
        for t in tables:
            p = data_dir / "financials" / t / "part.parquet"
            n = 0
            if p.exists():
                n = len(set(pl.read_parquet(p)["symbol"].unique().to_list()) & set(syms))
            cov[t] = n
        summary["financials"] = {"covered": cov, "elapsed_s": round(time.time() - t0, 2)}
        print("FIN", summary["financials"], flush=True)

    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
