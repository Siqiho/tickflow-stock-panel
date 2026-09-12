"""Daily quality checks over local kline partitions."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.services.atomic_io import atomic_write_json


def _latest_partition_date(kline_dir: Path) -> str | None:
    from app.services.kline_sync import safe_usable_daily_partition_dates

    dates = safe_usable_daily_partition_dates(kline_dir.parent, table=kline_dir.name)
    if dates:
        return dates[-1].isoformat()
    return None


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
    raw_files = list(part.glob("*.parquet")) if part.exists() else []
    try:
        from app.services.kline_sync import filter_daily_cache, usable_daily_partition_files

        files = usable_daily_partition_files(part)
    except Exception:  # noqa: BLE001
        files = []
    if not raw_files:
        report = {
            "ok": False,
            "date": target,
            "issues": [{"code": "missing_partition", "message": f"no parquet for {target}"}],
            "metrics": metrics,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        _write_report(data_dir, report)
        return report
    if not files:
        report = {
            "ok": False,
            "date": target,
            "issues": [{"code": "unusable_route", "message": f"partition {target} is not the current daily route"}],
            "metrics": metrics,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        _write_report(data_dir, report)
        return report

    try:
        df = filter_daily_cache(
            pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")
        )
    except Exception:
        df = pl.DataFrame()
    if df.is_empty():
        report = {
            "ok": False,
            "date": target,
            "issues": [{"code": "missing_partition", "message": f"no usable parquet for {target}"}],
            "metrics": metrics,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        _write_report(data_dir, report)
        return report
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

    # Canonical unit contract: volume=lots (100 shares), amount=CNY. For a
    # liquid daily bar, amount / (volume * 100 * close) should stay near 1.
    unit_cols = {"symbol", "close", "high", "low", "volume", "amount"}
    if unit_cols.issubset(df.columns):
        valid = df.filter(
            (pl.col("close") > 0)
            & (pl.col("volume") > 0)
            & (pl.col("amount") > 0)
        ).with_columns(
            (pl.col("amount") / (pl.col("volume") * 100 * pl.col("close"))).alias("_unit_ratio"),
            (pl.col("amount") / (pl.col("volume") * 100)).alias("_vwap"),
            pl.when(pl.col("symbol").str.starts_with("68"))
            .then(pl.lit("STAR"))
            .when(pl.col("symbol").str.ends_with(".BJ"))
            .then(pl.lit("BJ"))
            .when(pl.col("symbol").str.ends_with(".SH"))
            .then(pl.lit("SH"))
            .when(pl.col("symbol").str.ends_with(".SZ"))
            .then(pl.lit("SZ"))
            .otherwise(pl.lit("OTHER"))
            .alias("_market"),
        )
        if valid.height:
            ratio_stats = valid.select(
                pl.col("_unit_ratio").median().alias("median"),
                pl.col("_unit_ratio").quantile(0.1).alias("p10"),
                pl.col("_unit_ratio").quantile(0.9).alias("p90"),
            ).row(0, named=True)
            metrics["amount_volume_price_ratio"] = {
                key: float(value) if value is not None else None
                for key, value in ratio_stats.items()
            }
            median_ratio = float(ratio_stats["median"] or 0)
            if median_ratio < 0.001:
                issues.append(
                    {
                        "code": "amount_unit_mismatch",
                        "message": (
                            "median amount/(volume*100*close) is "
                            f"{median_ratio:.6g}; amount may still be in ten-thousand CNY"
                        ),
                    }
                )
            elif not 0.2 <= median_ratio <= 5.0:
                issues.append(
                    {
                        "code": "amount_volume_unit_mismatch",
                        "message": f"median amount/volume/price ratio out of range: {median_ratio:.6g}",
                    }
                )

            market_metrics: dict[str, dict[str, float | int]] = {}
            for market_df in valid.partition_by("_market", maintain_order=True):
                market = str(market_df["_market"][0])
                market_median = float(market_df["_unit_ratio"].median() or 0)
                market_metrics[market] = {"rows": market_df.height, "median": market_median}
                if market_df.height >= 3 and not 0.2 <= market_median <= 5.0:
                    issues.append(
                        {
                            "code": "market_unit_mismatch",
                            "market": market,
                            "count": market_df.height,
                            "message": f"{market} median unit ratio out of range: {market_median:.6g}",
                        }
                    )
            metrics["amount_volume_price_ratio_by_market"] = market_metrics

            bad_vwap = valid.filter(
                (pl.col("_vwap") < pl.col("low") * 0.2)
                | (pl.col("_vwap") > pl.col("high") * 5.0)
            ).height
            metrics["vwap_price_mismatch_rows"] = bad_vwap
            if bad_vwap / valid.height > 0.01:
                issues.append(
                    {
                        "code": "vwap_price_mismatch",
                        "count": bad_vwap,
                        "message": f"{bad_vwap}/{valid.height} rows have VWAP far outside daily price range",
                    }
                )

    # Coverage vs current-route instruments. Leftover TickFlow universe
    # must not mint a false low_coverage after a custom daily switch.
    if "symbol" in df.columns:
        try:
            from app.services.instrument_sync import read_usable_instruments

            idf = read_usable_instruments(data_dir)
        except Exception:  # noqa: BLE001
            idf = pl.DataFrame()
        if not idf.is_empty() and "symbol" in idf.columns:
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

    enriched_part = data_dir / "kline_daily_enriched" / f"date={target}"
    try:
        from app.services.kline_sync import read_usable_daily_partition

        enriched = read_usable_daily_partition(enriched_part)
    except Exception:
        enriched = pl.DataFrame()
        if (
            not enriched.is_empty()
            and "turnover_rate" in enriched.columns
            and enriched.schema["turnover_rate"] != pl.Null
        ):
            extreme_turnover = enriched.filter(pl.col("turnover_rate").cast(pl.Float64) > 100).height
            metrics["turnover_rate_over_100"] = extreme_turnover
            if extreme_turnover:
                issues.append(
                    {
                        "code": "turnover_unit_mismatch",
                        "count": extreme_turnover,
                        "message": f"{extreme_turnover} rows have turnover_rate above 100 percentage points",
                    }
                )

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
    atomic_write_json(report, path, indent=2)
