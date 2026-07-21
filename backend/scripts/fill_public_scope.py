#!/usr/bin/env python3
"""Fill public adj_factor + financials for a universe scope (default CSI300)."""
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
    ap.add_argument("--data-dir", default="")
    ap.add_argument("--skip-adj", action="store_true")
    ap.add_argument("--skip-financials", action="store_true")
    ap.add_argument("--max-periods", type=int, default=4)
    ap.add_argument("--adj-pause", type=float, default=0.05)
    ap.add_argument("--fin-pause", type=float, default=0.1)
    ap.add_argument("--set-defaults", action="store_true", help="set public providers + scopes")
    args = ap.parse_args()

    from app.config import settings
    from app.services import preferences
    from app.services.universe_scope import resolve_symbols, SCOPE_LABELS, normalize_scope

    data_dir = Path(args.data_dir) if args.data_dir else Path(settings.data_dir)
    scope = normalize_scope(args.scope, default="CSI300")

    if args.set_defaults:
        preferences.save({
            "adj_factor_provider": "public",
            "financial_provider": "public",
            "pool_provider": "public",
            "public_data_scope": scope,
            "pipeline_universe_scope": preferences.get_pipeline_universe_scope() or "ALL",
        })
        print("defaults:", {
            "adj": preferences.get_adj_factor_provider(),
            "fin": preferences.get_financial_provider(),
            "public_data_scope": preferences.get_public_data_scope(),
            "pipeline_universe_scope": preferences.get_pipeline_universe_scope(),
        })

    syms = resolve_symbols(scope, data_dir=data_dir, default="CSI300", refresh_pools_if_missing=True)
    print(f"scope={scope} ({SCOPE_LABELS.get(scope, scope)}) symbols={len(syms)}")
    if not syms:
        print("no symbols", file=sys.stderr)
        return 2

    out: dict = {"scope": scope, "symbols": len(syms)}

    if not args.skip_adj:
        from app.services.free_sources.adj_factor_public import sync_adj_factor_public

        def prog(i, t, s):
            if i == 1 or i == t or i % 25 == 0:
                print(f"  adj [{i}/{t}] {s}", flush=True)

        t0 = time.time()
        out["adj"] = sync_adj_factor_public(syms, data_dir, pause_s=args.adj_pause, on_progress=prog)
        out["adj"]["elapsed_wall_s"] = round(time.time() - t0, 2)
        print("adj done", out["adj"].get("symbols_affected_n"), "symbols", flush=True)

    if not args.skip_financials:
        from app.services.free_sources.financials_public import sync_financials_public

        def prog2(i, t, s):
            if i == 1 or i == t or i % 10 == 0:
                print(f"  fin [{i}/{t}] {s}", flush=True)

        t0 = time.time()
        out["financials"] = sync_financials_public(
            syms, data_dir, max_periods=args.max_periods, pause_s=args.fin_pause, on_progress=prog2
        )
        out["financials"]["elapsed_wall_s"] = round(time.time() - t0, 2)
        print("fin done", out["financials"].get("symbols_ok_n"), "ok", flush=True)

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
