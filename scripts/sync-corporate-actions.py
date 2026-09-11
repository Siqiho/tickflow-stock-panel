#!/usr/bin/env python3
"""Explicit corporate_actions sync (EastMoney share-bonus report + adj cross-check).

Fetches the full-market dividend/bonus detail report, merges with prior local
actions and adj-derived verification signals, cross-checks against adj factors,
quarantines mismatches, then atomically publishes
reference/corporate_actions/actions.parquet. Default is a zero-network dry-run
summary; pass --apply to fetch and publish. Never scheduled automatically.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (REPO_ROOT / "backend", REPO_ROOT):
    # 本地仓库为 <repo>/backend/app; 服务器镜像为 /app/app
    if (_candidate / "app").is_dir():
        sys.path.insert(0, str(_candidate))
        break

import polars as pl  # noqa: E402

from app.services.corporate_actions_sync import (  # noqa: E402
    load_adj_factor_frame,
    run_corporate_actions_loop,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    parser.add_argument("--max-pages", type=int, default=None, help="safety cap on report pages")
    parser.add_argument("--apply", action="store_true", help="fetch and publish; default dry-run")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir.resolve(strict=True)
    if not args.apply:
        prior_path = data_dir / "reference" / "corporate_actions" / "actions.parquet"
        prior = pl.read_parquet(prior_path) if prior_path.exists() else pl.DataFrame()
        adj = load_adj_factor_frame(data_dir)
        summary = {
            "dry_run": True,
            "prior_action_rows": int(prior.height),
            "prior_sources": (
                sorted(prior.get_column("source").unique().to_list())
                if "source" in prior.columns and prior.height
                else []
            ),
            "adj_rows": int(adj.height),
            "plan": (
                "fetch RPT_SHAREBONUS_DET all pages -> parse formal facts -> merge prior + "
                "adj-derived signals -> cross-check vs adj -> quarantine mismatches -> "
                "atomic publish + verification markers + catalog rescan"
            ),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    report = run_corporate_actions_loop(
        data_dir,
        as_of=args.as_of,
        fetch_sharebonus=True,
        sharebonus_max_pages=args.max_pages,
        publish_actions=True,
    )
    publish = report.get("publish") or {}
    compact = {
        key: report.get(key)
        for key in (
            "as_of",
            "adj_rows",
            "adj_symbols",
            "derived_signal_rows",
            "sharebonus",
            "sourced_event_rows",
            "action_rows",
            "crosscheck",
            "verification_counts",
            "unit_version",
        )
    }
    compact["publish"] = publish

    ok = bool(publish.get("ok"))
    if ok:
        from app.data_catalog.control_db import CatalogControlDB
        from app.data_catalog.service import CatalogService

        control_db = CatalogControlDB(data_dir)
        service = CatalogService(data_dir, control_db)
        rescan: dict[str, dict[str, str | None]] = {}
        for dataset_id in ("corporate_actions", "stock_adj_factor"):
            service.rescan(dataset_id)
            runs = [
                run
                for run in control_db.list_sync_runs(dataset_id=dataset_id, limit=50)
                if run.operation == "catalog_rescan"
            ]
            latest = max(runs, key=lambda run: run.started_at or "") if runs else None
            rescan[dataset_id] = {
                "run_status": latest.status if latest else "unknown",
                "error": (latest.error_message or None) if latest else None,
            }
            if latest is None or latest.status not in {"succeeded", "degraded"}:
                ok = False
        compact["catalog_rescan"] = rescan

    print(json.dumps(compact, ensure_ascii=False, indent=2, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
