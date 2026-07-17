"""Daily quality checks over local kline partitions."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl


def _latest_partition_date(kline_dir: Path) -> str | None:
    parts = sorted([p.name for p in kline_dir.iterdir() if p.is_dir() and p.name.startswith("date=")])
    if not parts:
        return None
    return parts[-1].removeprefix("date=")


def run_daily_quality_check(data_dir: Path | str, date: str | None = None) -> dict[str, Any]:
    data_dir = Path(data_dir)
    kline_dir = data_dir / "kline_daily"
    issues: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}

    if not kline_dir.exists():
        report = {
            "ok": False,
            "date": date,
            "issues": [{"code": "missing_kline_daily", "message": "kline_daily directory missing"}],
            "metrics": metrics,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        _write_report(data_dir, report)
        return report

    target = date or _latest_partition_date(kline_dir)
    if not target:
        report = {
            "ok": False,
            "date": None,
            "issues": [{"code": "no_partitions", "message": "no date partitions"}],
            "metrics": metrics,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        _write_report(data_dir, report)
        return report

    part = kline_dir / f"date={target}"
    files = list(part.glob("*.parquet")) if part.exists() else []
    if not files:
        report = {
            "ok": False,
            "date": target,
            "issues": [{"code": "missing_partition", "message": f"no parquet for {target}"}],
            "metrics": metrics,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        _write_report(data_dir, report)
        return report

    df = pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")
    metrics["rows"] = df.height
    metrics["symbols"] = df["symbol"].n_unique() if "symbol" in df.columns else 0

    if "volume" in df.columns:
        neg_v = df.filter(pl.col("volume") < 0).height
        if neg_v:
            issues.append({"code": "negative_volume", "count": neg_v, "message": f"{neg_v} rows with volume < 0"})
    if "amount" in df.columns:
        zero_a = df.filter(pl.col("amount") == 0).height
        if zero_a:
            issues.append({"code": "zero_amount", "count": zero_a, "message": f"{zero_a} rows with amount == 0"})
        neg_a = df.filter(pl.col("amount") < 0).height
        if neg_a:
            issues.append({"code": "negative_amount", "count": neg_a, "message": f"{neg_a} rows with amount < 0"})

    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            n = df.filter(pl.col(col).is_null()).height
            if n:
                issues.append({"code": f"null_{col}", "count": n, "message": f"{n} null {col}"})

    if all(c in df.columns for c in ("high", "low")):
        bad = df.filter(pl.col("high") < pl.col("low")).height
        if bad:
            issues.append({"code": "high_lt_low", "count": bad, "message": f"{bad} rows high < low"})

    # Coverage vs instruments
    inst = data_dir / "instruments" / "instruments.parquet"
    if inst.exists() and "symbol" in df.columns:
        idf = pl.read_parquet(inst)
        metrics["instruments"] = idf.height
        missing = set(idf["symbol"].to_list()) - set(df["symbol"].to_list())
        metrics["missing_vs_instruments"] = len(missing)
        if idf.height and len(missing) / idf.height > 0.05:
            issues.append(
                {
                    "code": "low_coverage",
                    "count": len(missing),
                    "message": f"missing {len(missing)}/{idf.height} instruments on {target}",
                }
            )

    # Unit heuristic sample
    if all(c in df.columns for c in ("symbol", "high", "low", "volume", "amount")):
        sample = df.filter(pl.col("symbol") == "000001.SZ")
        if sample.height:
            row = sample.row(0, named=True)
            hi, lo, vol, amt = row["high"], row["low"], row["volume"], row["amount"]
            if hi and lo and vol and amt:
                mid = (float(hi) + float(lo)) / 2
                if mid > 0 and float(vol) > 0:
                    ratio = float(amt) / (mid * float(vol))
                    metrics["unit_heuristic_000001"] = {
                        "amount_over_mid_volume": ratio,
                        "guess": "volume_lot_100shares" if 50 < ratio < 150 else "unknown",
                    }

    report = {
        "ok": len(issues) == 0,
        "date": target,
        "issues": issues,
        "metrics": metrics,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "source": "local_kline_daily",
    }
    _write_report(data_dir, report)
    return report


def _write_report(data_dir: Path, report: dict) -> None:
    out_dir = data_dir / "user_data"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "daily_quality_latest.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
