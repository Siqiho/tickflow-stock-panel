#!/usr/bin/env python3
"""Sample/full sync of public financials into data/financials/*/part.parquet."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="")
    ap.add_argument("--scope", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--data-dir", default="")
    ap.add_argument("--max-periods", type=int, default=4)
    ap.add_argument("--set-provider", default="")
    ap.add_argument("--pause", type=float, default=0.1)
    args = ap.parse_args()

    from app.config import settings
    from app.services.free_sources.financials_public import sync_financials_public

    data_dir = Path(args.data_dir) if args.data_dir else Path(settings.data_dir)
    if args.set_provider:
        from app.services import preferences
        preferences.save({"financial_provider": args.set_provider})
        print("financial_provider=", preferences.get_financial_provider())

    if args.symbols.strip():
        syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        from app.services import preferences
        from app.services.universe_scope import resolve_symbols
        scope = args.scope.strip() or preferences.get_public_data_scope()
        syms = resolve_symbols(scope, data_dir=data_dir, default="CSI300", refresh_pools_if_missing=True)
        print(f"scope={scope} symbols={len(syms)}")
    if args.limit and args.limit > 0:
        syms = syms[: args.limit]

    def prog(cur, tot, sym):
        if cur == 1 or cur == tot or cur % 10 == 0:
            print(f"  [{cur}/{tot}] {sym}", flush=True)

    print(f"sync {len(syms)} symbols -> {data_dir}/financials")
    result = sync_financials_public(
        syms, data_dir, max_periods=args.max_periods, pause_s=args.pause, on_progress=prog
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
