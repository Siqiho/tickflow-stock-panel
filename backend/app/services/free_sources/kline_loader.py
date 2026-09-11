"""Load local daily bars for free derived features."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl


def load_daily_bars_for_symbol(
    data_dir: Path,
    symbol: str,
    *,
    days: int = 120,
    as_of: date | str | None = None,
) -> list[dict]:
    """Load last `days` daily bars for one symbol.

    Prefer kline_daily_enriched (has turnover_rate); fallback to kline_daily.
    """
    data_dir = Path(data_dir)
    enriched = data_dir / "kline_daily_enriched"
    raw = data_dir / "kline_daily"
    source = enriched if enriched.exists() and any(enriched.rglob("*.parquet")) else raw
    if not source.exists():
        raise FileNotFoundError(f"daily kline dir missing: {source}")

    # Scan all partitions then filter — dataset is ~1 year / manageable for single symbol.
    files = sorted(source.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no parquet under {source}")

    from app.services.kline_sync import daily_partition_usable, filter_daily_cache

    # Read in batches to avoid huge memory if needed; for one symbol polars filter is fine.
    dfs: list[pl.DataFrame] = []
    for f in files:
        try:
            if not daily_partition_usable(f):
                continue
            df = filter_daily_cache(pl.read_parquet(f))
        except Exception:  # noqa: BLE001
            continue
        if "symbol" not in df.columns:
            continue
        sub = df.filter(pl.col("symbol") == symbol)
        if sub.height:
            dfs.append(sub)
    if not dfs:
        raise ValueError(f"no daily bars for {symbol}")

    out = pl.concat(dfs, how="diagonal_relaxed")
    if "date" in out.columns:
        out = out.sort("date")
        if as_of is not None:
            as_of_text = as_of.isoformat() if isinstance(as_of, date) else str(as_of)[:10]
            out = out.filter(
                pl.col("date").cast(pl.Utf8).str.slice(0, 10) <= as_of_text
            )
    if out.is_empty():
        raise ValueError(f"no daily bars for {symbol} on or before {as_of}")
    if days > 0 and out.height > days:
        out = out.tail(days)

    # Ensure expected columns
    for col in ("open", "high", "low", "close", "volume", "amount"):
        if col not in out.columns:
            out = out.with_columns(pl.lit(None).alias(col))
    if "turnover_rate" not in out.columns:
        out = out.with_columns(pl.lit(0.0).alias("turnover_rate"))

    return out.select(
        [c for c in ["date", "open", "high", "low", "close", "volume", "amount", "turnover_rate"] if c in out.columns]
    ).to_dicts()
