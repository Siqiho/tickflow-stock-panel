#!/usr/bin/env python3
"""Sync public index constituent pools into data/pools/*.parquet."""
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
    ap.add_argument("--pools", default="CSI300,CSI500,SSE50")
    ap.add_argument("--data-dir", default="")
    ap.add_argument("--set-provider", default="")
    args = ap.parse_args()

    from app.config import settings
    from app.services.free_sources.pools_public import sync_pools_public

    data_dir = Path(args.data_dir) if args.data_dir else Path(settings.data_dir)
    if args.set_provider:
        from app.services import preferences
        preferences.save({"pool_provider": args.set_provider})
        print("pool_provider=", preferences.get_pool_provider())

    ids = [p.strip().upper() for p in args.pools.split(",") if p.strip()]

    def prog(cur, tot, pid):
        print(f"  [{cur}/{tot}] {pid}", flush=True)

    print(f"sync pools {ids} -> {data_dir}/pools")
    result = sync_pools_public(data_dir, pool_ids=ids, on_progress=prog)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
