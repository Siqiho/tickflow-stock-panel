"""Normalize provider responses into internal Polars schemas."""

from __future__ import annotations

import polars as pl

from app.data_providers.base import ProviderDatasetManifest
from app.data_providers.unit_contracts import (
    canonicalize_amount,
    canonicalize_ratio,
    canonicalize_volume,
    ensure_publishable_units,
)
from app.indicators.pipeline import filter_halt_days

DAILY_COLS = [
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "change_pct",
    "turnover_rate",
]
ADJ_FACTOR_COLS = ["symbol", "trade_date", "ex_factor"]
INSTRUMENT_COLS = ["symbol", "name", "code", "exchange", "asset_type", "source"]


def to_polars(data) -> pl.DataFrame:
    if data is None:
        return pl.DataFrame()
    if isinstance(data, pl.DataFrame):
        return data
    if isinstance(data, dict):
        rows: list[dict] = []
        for sym, values in data.items():
            for item in values or []:
                row = dict(item or {})
                row.setdefault("symbol", sym)
                rows.append(row)
        return pl.DataFrame(rows) if rows else pl.DataFrame()
    if hasattr(data, "reset_index"):
        return pl.from_pandas(data.reset_index())
    try:
        return pl.DataFrame(data)
    except Exception:
        return pl.DataFrame()


def normalize_daily(
    data,
    default_symbol: str | None = None,
    source: str = "tickflow",
    *,
    manifest: ProviderDatasetManifest | None = None,
    market: str = "CN",
    for_publication: bool = False,
) -> pl.DataFrame:
    if for_publication:
        if manifest is None:
            raise ValueError("a provider manifest is required for publication")
        ensure_publishable_units(manifest, required_fields={"volume", "amount"}, market=market)
    df = to_polars(data)
    if df.is_empty():
        return df
    rename_map = {
        "ts_code": "symbol",
        "trade_date": "date",
        "datetime": "date",
        "vol": "volume",
        "amt": "amount",
    }
    df = df.rename({k: v for k, v in rename_map.items() if k in df.columns})
    if "symbol" not in df.columns and default_symbol:
        df = df.with_columns(pl.lit(default_symbol).alias("symbol"))
    if "date" in df.columns and df.schema["date"] != pl.Date:
        df = df.with_columns(pl.col("date").cast(pl.Date, strict=False))
    for col in ("open", "high", "low", "close", "volume", "amount"):
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Float64, strict=False))
    if for_publication and manifest is not None:
        if "volume" in df.columns:
            df = df.with_columns(
                pl.col("volume")
                .map_elements(
                    lambda value: canonicalize_volume(
                        value, manifest.source_units["volume"], market=market
                    ),
                    return_dtype=pl.Float64,
                )
                .alias("volume")
            )
        if "amount" in df.columns:
            df = df.with_columns(
                pl.col("amount")
                .map_elements(
                    lambda value: canonicalize_amount(
                        value, manifest.source_units["amount"], market=market
                    ),
                    return_dtype=pl.Float64,
                )
                .alias("amount")
            )
        for column in ("change_pct", "turnover_rate"):
            if column in df.columns:
                df = df.with_columns(
                    pl.col(column)
                    .cast(pl.Float64, strict=False)
                    .map_elements(
                        lambda value: canonicalize_ratio(
                            value,
                            manifest.source_units.get("ratio", "unknown"),
                            target_scale=manifest.canonical_units.get("ratio", "percentage_point"),
                        ),
                        return_dtype=pl.Float64,
                    )
                    .alias(column)
                )
    df = filter_halt_days(df)
    keep = [c for c in DAILY_COLS if c in df.columns]
    return df.select(keep) if keep else pl.DataFrame()


def normalize_adj_factors(data, source: str = "tickflow") -> pl.DataFrame:
    df = to_polars(data)
    if df.is_empty():
        return df
    rename_map = {
        "timestamp": "trade_date",
        "date": "trade_date",
        "adj_factor": "ex_factor",
    }
    df = df.rename({k: v for k, v in rename_map.items() if k in df.columns})
    if "trade_date" in df.columns:
        if df.schema["trade_date"] in {
            pl.Int64,
            pl.Int32,
            pl.UInt64,
            pl.UInt32,
            pl.Float64,
            pl.Float32,
        }:
            df = df.with_columns(
                pl.from_epoch(pl.col("trade_date").cast(pl.Int64), time_unit="ms")
                .dt.date()
                .alias("trade_date")
            )
        else:
            df = df.with_columns(pl.col("trade_date").cast(pl.Date, strict=False))
    if "ex_factor" in df.columns:
        df = df.with_columns(pl.col("ex_factor").cast(pl.Float64, strict=False))
    keep = [c for c in ADJ_FACTOR_COLS if c in df.columns]
    return df.select(keep).drop_nulls() if len(keep) == len(ADJ_FACTOR_COLS) else pl.DataFrame()


def normalize_instruments(
    rows: list[dict], asset_type: str, source: str = "tickflow"
) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame()
    out: list[dict] = []
    for item in rows:
        symbol = item.get("symbol")
        if not symbol:
            continue
        out.append(
            {
                "symbol": str(symbol),
                "name": item.get("name") or str(symbol),
                "code": item.get("code") or str(symbol).split(".")[0],
                "exchange": item.get("exchange"),
                "asset_type": asset_type,
                "source": source,
            }
        )
    if not out:
        return pl.DataFrame()
    return (
        pl.DataFrame(out)
        .select(INSTRUMENT_COLS)
        .unique(subset=["symbol"], keep="last")
        .sort("symbol")
    )
