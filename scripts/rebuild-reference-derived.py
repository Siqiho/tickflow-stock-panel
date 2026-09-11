#!/usr/bin/env python3
"""Explicit rebuild entry for locally derived reference datasets.

Datasets: valuation_daily / limit_up_events / index_membership_history.
All inputs are local Parquet under --data-dir; this tool performs zero external
requests and is never scheduled automatically. Default is a dry-run plan;
pass --apply to write partitions, lineage, and refresh the catalog rows.
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

from app.services.reference_derived import (  # noqa: E402
    REFERENCE_DERIVED_DATASETS,
    rebuild_reference_derived,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--start", type=date.fromisoformat, default=None)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument(
        "--datasets",
        default=",".join(REFERENCE_DERIVED_DATASETS),
        help="comma separated subset of: " + ", ".join(REFERENCE_DERIVED_DATASETS),
    )
    parser.add_argument("--apply", action="store_true", help="write outputs; default dry-run")
    parser.add_argument(
        "--no-rescan",
        action="store_true",
        help="skip catalog rescan of touched datasets after apply",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    datasets = tuple(part.strip() for part in args.datasets.split(",") if part.strip())
    partitioned = {"valuation_daily", "limit_up_events"} & set(datasets)
    if partitioned and (args.start is None or args.end is None):
        raise SystemExit(
            "--start and --end are required when building "
            + "/".join(sorted(partitioned))
            + " (guards against unbounded historical backfill)"
        )
    data_dir = args.data_dir.resolve(strict=True)
    report = rebuild_reference_derived(
        data_dir,
        start=args.start,
        end=args.end,
        datasets=datasets,
        dry_run=not args.apply,
    )
    failed_rescans: list[str] = []
    if args.apply and not args.no_rescan:
        from app.data_catalog.control_db import CatalogControlDB
        from app.data_catalog.service import CatalogService

        control_db = CatalogControlDB(data_dir)
        service = CatalogService(data_dir, control_db)
        rescan: dict[str, dict[str, str | None]] = {}
        for dataset_id in datasets:
            service.rescan(dataset_id)
            # 以真实 sync_run 结果为准, 不读可能保留旧值的 dataset_state
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
                failed_rescans.append(dataset_id)
        report["catalog_rescan"] = rescan
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 1 if failed_rescans else 0


if __name__ == "__main__":
    raise SystemExit(main())
