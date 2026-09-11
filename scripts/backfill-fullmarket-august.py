#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (REPO_ROOT / "backend", REPO_ROOT):
    if (_candidate / "app").is_dir():
        sys.path.insert(0, str(_candidate))
        break

import polars as pl

from app.indicators.pipeline import run_pipeline
from app.services.atomic_io import atomic_write_parquet, write_lineage_record
from app.services.universe_scope import resolve_symbols
from app.tickflow.repository import DataStore, KlineRepository

DEFAULT_START = date(2026, 8, 3)
SINA_URL = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"


def _to_sina_code(symbol: str) -> str:
    symbol = symbol.strip().upper()
    code, _, exch = symbol.partition(".")
    code = code.zfill(6)
    if exch == "SH":
        return "sh" + code
    if exch == "BJ":
        return "bj" + code
    return "sz" + code


def _partition_dates(data_dir: Path, start: date, end: date | None) -> list[date]:
    out: list[date] = []
    last = end or date(2099, 1, 1)
    for path in sorted((data_dir / "kline_daily").glob("date=*")):
        try:
            day = date.fromisoformat(path.name[5:])
        except ValueError:
            continue
        if start <= day <= last:
            out.append(day)
    return out


def _symbols_in_partition(data_dir: Path, day: date) -> set[str]:
    path = data_dir / "kline_daily" / f"date={day.isoformat()}" / "part.parquet"
    if not path.exists():
        return set()
    frame = pl.read_parquet(path, columns=["symbol"])
    return {str(s).strip().upper() for s in frame["symbol"].to_list() if s}


def fetch_sina_daily(symbol: str, *, datalen: int = 20, timeout: float = 20.0) -> list[dict]:
    url = SINA_URL + "?" + urllib.parse.urlencode({
        "symbol": _to_sina_code(symbol),
        "scale": 240,
        "ma": "no",
        "datalen": datalen,
    })
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn/",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8", "replace"))
    if not isinstance(payload, list):
        return []
    rows: list[dict] = []
    for item in payload:
        try:
            day = date.fromisoformat(str(item.get("day")))
            close = float(item["close"])
            volume_shares = float(item.get("volume") or 0)
        except (TypeError, ValueError, KeyError):
            continue
        if close <= 0:
            continue
        close_f = close
        open_ = float(item.get("open") or close_f)
        high = float(item.get("high") or close_f)
        low = float(item.get("low") or close_f)
        rows.append({
            "symbol": symbol,
            "date": day,
            "open": open_,
            "high": high,
            "low": low,
            "close": close_f,
            "volume": volume_shares / 100.0,
            "amount": None,
        })
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--end", default="2026-08-14")
    parser.add_argument("--pause", type=float, default=0.05)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir.expanduser().resolve()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    dates = _partition_dates(data_dir, start, end)
    if not dates:
        raise SystemExit("no August daily partitions in range")
    universe = set(resolve_symbols(
        "CSI1800",
        data_dir=data_dir,
        default="CSI1800",
        include_watchlist=True,
        refresh_pools_if_missing=False,
    ))
    jul = _symbols_in_partition(data_dir, date(2026, 7, 31))
    latest = _symbols_in_partition(data_dir, dates[-1])
    stuck = sorted(jul - latest)
    if args.limit:
        stuck = stuck[: args.limit]
    preview = {
        "scope_unchanged": "CSI1800+watchlist",
        "universe": len(universe),
        "jul31": len(jul),
        "latest_partition": dates[-1].isoformat(),
        "latest_rows": len(latest),
        "stuck": len(stuck),
        "dates": [day.isoformat() for day in dates],
        "sample": stuck[:12],
        "apply": bool(args.apply),
        "source": "sina_hist_daily",
    }
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    if not args.apply:
        return 0

    fetched: dict[str, list[dict]] = {}
    failed: list[str] = []
    for index, symbol in enumerate(stuck, start=1):
        try:
            rows = fetch_sina_daily(symbol, datalen=20)
        except Exception as exc:
            failed.append(f"{symbol}: {type(exc).__name__}: {exc}")
            rows = []
        fetched[symbol] = [row for row in rows if start <= row["date"] <= end]
        if index % 50 == 0 or index == len(stuck):
            print(json.dumps({
                "progress": index,
                "total": len(stuck),
                "ok": sum(1 for rows in fetched.values() if rows),
                "failed": len(failed),
            }, ensure_ascii=False), flush=True)
        if args.pause > 0:
            time.sleep(args.pause)

    written = []
    for day in dates:
        part = data_dir / "kline_daily" / f"date={day.isoformat()}" / "part.parquet"
        prior = pl.read_parquet(part)
        prior_syms = {str(s).strip().upper() for s in prior["symbol"].to_list()}
        extra_rows = [
            row for symbol, rows in fetched.items() for row in rows
            if row["date"] == day and symbol not in prior_syms
        ]
        if extra_rows:
            extra = pl.DataFrame(extra_rows).with_columns(pl.col("date").cast(pl.Date))
            merged = pl.concat([prior, extra], how="diagonal_relaxed").unique(
                subset=["symbol", "date"], keep="last"
            ).sort(["symbol", "date"])
        else:
            merged = prior
        current_syms = {str(s).strip().upper() for s in merged["symbol"].to_list()}
        if not prior_syms.issubset(current_syms):
            raise RuntimeError(f"{day} backfill overwrote prior symbols")
        if extra_rows:
            atomic_write_parquet(merged, part)
            write_lineage_record(data_dir, "kline_daily", {
                "date": day.isoformat(),
                "source": "sina_hist_daily_merged",
                "unit_version": "canonical_daily_v1",
                "quality": "pending_gate",
                "row_count": int(merged.height),
                "unique_symbol_count": len(current_syms),
                "scope": "JUL31_PLUS_CSI1800_WATCHLIST",
                "added": len(extra_rows),
                "target_artifact": f"kline_daily/date={day.isoformat()}/part.parquet",
            })
        written.append({
            "date": day.isoformat(),
            "prior": len(prior_syms),
            "added": len(extra_rows),
            "rows": int(merged.height),
        })

    added_symbols = sorted({
        symbol for symbol, rows in fetched.items()
        if any(start <= row["date"] <= end for row in rows)
    })
    if added_symbols:
        run_pipeline(data_dir=data_dir, symbols=added_symbols, new_dates_only=False)
    print(json.dumps({
        "written": written,
        "added_symbols": len(added_symbols),
        "failed": failed[:20],
        "failed_count": len(failed),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
