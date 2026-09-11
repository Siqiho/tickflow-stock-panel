"""Exact-day historical intraday curve from public TDX servers.

This adapter is intentionally single-symbol and single-day.  It does not own
storage; the caller must reconcile the result with the local daily candle
before publishing it to ``kline_minute``.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl


def _split_symbol(symbol: str) -> tuple[str, str]:
    value = str(symbol or "").strip().upper()
    if "." not in value:
        raise ValueError(f"TDX historical minute requires exchange suffix: {symbol}")
    code, exchange = value.split(".", 1)
    if exchange not in {"SH", "SZ"} or not code.isdigit() or len(code) != 6:
        raise ValueError(f"TDX historical minute does not support symbol: {symbol}")
    return code, exchange


def normalize_history_minute(raw: Any, symbol: str, trade_date: date) -> pl.DataFrame:
    """Convert easy_tdx ``datetime/price/vol`` points to the local schema.

    The upstream endpoint is a price curve rather than minute OHLC bars, so the
    same price is used for OHLC. TDX ``vol`` is in lots (100 shares), so
    ``amount`` is an explicit price*volume*100 estimate and is not treated as
    source-reported turnover.
    """
    if raw is None or len(raw) == 0:
        return pl.DataFrame()
    if isinstance(raw, pl.DataFrame):
        df = raw
    else:
        df = pl.from_pandas(raw.reset_index() if hasattr(raw, "reset_index") else raw)
    required = {"datetime", "price", "vol"}
    if not required.issubset(df.columns):
        missing = sorted(required - set(df.columns))
        raise ValueError(f"TDX historical minute missing columns: {missing}")

    df = (
        df.select("datetime", "price", "vol")
        .with_columns(
            pl.col("datetime").cast(pl.Datetime("us"), strict=False),
            pl.col("price").cast(pl.Float64, strict=False),
            pl.col("vol").cast(pl.Float64, strict=False).alias("volume"),
        )
        .drop("vol")
        .filter(pl.col("datetime").is_not_null())
        .filter(pl.col("datetime").dt.date() == trade_date)
        .filter(pl.col("price").is_not_null() & (pl.col("price") > 0))
        .filter(pl.col("volume").is_not_null() & (pl.col("volume") >= 0))
        .unique(subset=["datetime"], keep="last")
        .sort("datetime")
        .with_columns(
            pl.lit(symbol.upper()).alias("symbol"),
            pl.col("price").alias("open"),
            pl.col("price").alias("high"),
            pl.col("price").alias("low"),
            pl.col("price").alias("close"),
            (pl.col("price") * pl.col("volume") * 100).alias("amount"),
        )
        .select("symbol", "datetime", "open", "high", "low", "close", "volume", "amount")
    )
    return df


def fetch_history_minute(symbol: str, trade_date: date) -> pl.DataFrame:
    """Fetch one historical trading day's 240-point intraday curve."""
    code, exchange = _split_symbol(symbol)
    from easy_tdx import Market, TdxClient

    market = Market.SH if exchange == "SH" else Market.SZ
    client = TdxClient.from_best_host()
    try:
        raw = client.get_history_minute_time_data(
            market,
            code,
            int(trade_date.strftime("%Y%m%d")),
        )
    finally:
        client.disconnect()
    return normalize_history_minute(raw, symbol, trade_date)
