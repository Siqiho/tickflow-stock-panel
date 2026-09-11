#!/usr/bin/env python3
"""TEST-ONLY: write 5 leftover quote samples into an isolated DATA_DIR.

Never point --data-dir at shared-isolated-runtime-20260911 or one-trading/data.
Restore: delete the temporary directory. No tokens.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "old-quote-5-sample.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="TEST-ONLY leftover quote repro")
    parser.add_argument(
        "--data-dir",
        default="/tmp/ot-overview-scope-repro",
        help="Isolated directory only. Do not use shared DATA_DIR.",
    )
    parser.add_argument("--print-overview", action="store_true")
    args = parser.parse_args()
    data_dir = Path(args.data_dir).resolve()
    if "shared-isolated-runtime" in str(data_dir) or str(data_dir).endswith("/data"):
        raise SystemExit(f"refusing shared/formal data dir: {data_dir}")

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    out = data_dir / "quote_snapshot" / "asset_type=stock" / f"date={payload['as_of']}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(payload["rows"]).write_parquet(out)
    print(f"TEST-ONLY wrote {out}")
    print("restore: rm -rf", data_dir)

    if args.print_overview:
        from types import SimpleNamespace

        from app.services.market_overview_builder import build_market_overview

        class _Date(date):
            @classmethod
            def today(cls):
                return date.fromisoformat(payload["as_of"])

        import app.services.market_overview_builder as mob
        mob.date = _Date  # type: ignore[misc]
        repo = SimpleNamespace(store=SimpleNamespace(data_dir=data_dir))
        repo.get_enriched_latest = lambda: (pl.DataFrame(), None)
        repo.get_instruments = lambda: pl.DataFrame()
        repo.get_enriched_history = lambda *_a, **_k: pl.DataFrame()
        repo.execute_all = lambda *_a, **_k: []
        overview = build_market_overview(repo, as_of=None, default_to_live=True)
        print(json.dumps({
            "as_of": overview.get("as_of"),
            "coverage": overview.get("coverage"),
            "breadth": overview.get("breadth"),
            "amount": overview.get("amount"),
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
