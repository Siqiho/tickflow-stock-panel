#!/usr/bin/env python3
"""Fill public adj coverage for symbols missing events (identity marker + EM verify)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import polars as pl

from app.config import settings
from app.services.free_sources.adj_factor_public import sync_adj_factor_public, read_adj_coverage
from app.services.universe_scope import resolve_symbols


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="CSI300")
    ap.add_argument("--only-missing", action="store_true", default=True)
    ap.add_argument("--pause", type=float, default=0.05)
    args = ap.parse_args()
    data_dir = Path(settings.data_dir)
    syms = resolve_symbols(args.scope, data_dir=data_dir, default="CSI300")
    adj_path = data_dir / "adj_factor" / "all.parquet"
    if args.only_missing and adj_path.exists():
        have = set(pl.read_parquet(adj_path, columns=["symbol"])["symbol"].unique().to_list())
        need = [s for s in syms if s not in have]
    else:
        need = list(syms)
    print(f"scope={args.scope} need={len(need)}", flush=True)
    if not need:
        print("nothing to do")
        return 0
    res = sync_adj_factor_public(need, data_dir, pause_s=args.pause)
    print(res)
    cov = read_adj_coverage(data_dir)
    print(cov.group_by("status").len() if not cov.is_empty() else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
