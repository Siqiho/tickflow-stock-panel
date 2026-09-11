#!/usr/bin/env python3
"""Backfill industry or concept daily fund-flow from Eastmoney H5.

Merges by date+code. Does not refresh the ranking snapshot and does not write
go-stock, TickFlow, HiThink, or 20G stockdb rows.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (REPO_ROOT / "backend", REPO_ROOT):
    if (_candidate / "app").is_dir():
        sys.path.insert(0, str(_candidate))
        break

from app.services.free_sources.fund_flow import (  # noqa: E402
    aggregate_board_window,
    backfill_industry_daily_from_h5,
    load_board_snapshot_items,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(REPO_ROOT / "data"))
    parser.add_argument("--codes", default="", help="comma-separated BK codes; default is the industry snapshot")
    parser.add_argument("--kind", choices=("board", "concept"), default="board")
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--min-days", type=int, default=63)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--pause-s", type=float, default=0.35)
    parser.add_argument("--pause-code-s", type=float, default=0.0)
    parser.add_argument("--skip-gate", action="store_true", help="do not require full requested window")
    args = parser.parse_args()

    os.environ["FUND_FLOW_HISTORY_PREFER_LOCAL"] = "0"
    data_dir = Path(args.data_dir)
    kind = args.kind
    codes = [c.strip().upper() for c in args.codes.split(",") if c.strip()] or None
    snapshot = load_board_snapshot_items(data_dir, kind=kind)

    def coverage(days: int) -> dict:
        window = aggregate_board_window(data_dir, kind=kind, days=days, top=200)
        items = window.get("items") or []
        ge = sum(1 for item in items if int(item.get("days") or 0) >= days)
        return {
            "requested_days": days,
            "trading_days": window.get("trading_days"),
            "start": window.get("start"),
            "end": window.get("end"),
            "snapshot_count": window.get("snapshot_count"),
            "covered_count": window.get("covered_count"),
            "full_count": window.get("full_count"),
            "ge_requested": ge,
            "window_complete": window.get("window_complete"),
            "window_note": window.get("window_note"),
            "short": (window.get("short") or [])[:12],
        }

    print(json.dumps({
        "phase": "before",
        "kind": kind,
        "snapshot_count": len(snapshot),
        "coverage63": coverage(63),
        "coverage5": coverage(5),
    }, ensure_ascii=False, indent=2))

    result = backfill_industry_daily_from_h5(
        data_dir,
        codes=codes,
        limit=args.limit,
        batch_size=args.batch_size,
        pause_s=args.pause_s,
        pause_code_s=args.pause_code_s,
        min_days=args.min_days,
        kind=kind,
    )
    print(json.dumps({"phase": "backfill", **result}, ensure_ascii=False, indent=2))
    after = {
        "phase": "after",
        "kind": kind,
        "coverage63": coverage(63),
        "coverage5": coverage(5),
    }
    print(json.dumps(after, ensure_ascii=False, indent=2))
    complete = bool(after["coverage63"]["window_complete"]) and int(after["coverage63"]["full_count"] or 0) == int(after["coverage63"]["snapshot_count"] or 0)
    if args.skip_gate:
        return 0 if result.get("failed") == [] and result.get("history_codes") else 2
    return 0 if result.get("ok") and complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
