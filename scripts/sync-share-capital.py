#!/usr/bin/env python3
"""Explicit share-capital history sync (EastMoney F10 equity structure).

Fetches per-symbol share capital change history with real announce dates and
merges it into financials/shares with PIT columns. Default is a dry-run that
only prints the resolved symbol list; pass --apply to fetch and publish.
Never scheduled automatically.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (REPO_ROOT / "backend", REPO_ROOT):
    # 本地仓库为 <repo>/backend/app; 服务器镜像为 /app/app
    if (_candidate / "app").is_dir():
        sys.path.insert(0, str(_candidate))
        break

import polars as pl  # noqa: E402

from app.services.free_sources.share_capital_public import (  # noqa: E402
    sync_share_capital_public,
)


def resolve_universe(data_dir: Path, universe: str) -> list[str]:
    symbols: set[str] = set()
    if universe in {"pipeline", "csi500"}:
        pool = data_dir / "pools" / "CSI500.parquet"
        if pool.exists():
            symbols.update(
                str(s).upper() for s in pl.read_parquet(pool).get_column("symbol").to_list()
            )
    if universe in {"pipeline", "watchlist"}:
        watchlist = data_dir / "user_data" / "watchlist.parquet"
        if watchlist.exists():
            frame = pl.read_parquet(watchlist)
            if "symbol" in frame.columns:
                symbols.update(str(s).upper() for s in frame.get_column("symbol").to_list())
    return sorted(symbols)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument(
        "--universe",
        choices=("pipeline", "csi500", "watchlist"),
        default="pipeline",
        help="pipeline = CSI500 + watchlist union",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="comma separated explicit symbols; overrides --universe",
    )
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--apply", action="store_true", help="fetch and publish; default dry-run")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir.resolve(strict=True)
    if args.symbols:
        symbols = sorted({s.strip().upper() for s in args.symbols.split(",") if s.strip()})
    else:
        symbols = resolve_universe(data_dir, args.universe)
    if not symbols:
        raise SystemExit("no symbols resolved")
    if not args.apply:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "universe": args.universe if not args.symbols else "explicit",
                    "symbol_count": len(symbols),
                    "sample": symbols[:10],
                    "estimated_requests": len(symbols),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    done = {"n": 0}

    def progress(index: int, total: int, symbol: str) -> None:
        done["n"] = index
        if index % 50 == 0 or index == total:
            print(f"progress: {index}/{total} {symbol}", file=sys.stderr)

    stats = sync_share_capital_public(
        symbols,
        data_dir,
        sleep_s=args.sleep,
        on_progress=progress,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2, default=str))
    return 0 if stats.get("published") else 1


if __name__ == "__main__":
    raise SystemExit(main())
