"""Build the broad market snapshot consumed by industry/concept analysis.

The daily pipeline may intentionally run on a bounded universe (for example
CSI500).  That scope must not silently become the coverage contract of a page
labelled as full-market analysis.  The serving view therefore prefers the
latest persisted stock ``quote_snapshot`` and only uses same-day enriched data
to supplement derived metrics.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

_OUTPUT_FIELDS = (
    "symbol",
    "name",
    "close",
    "change_pct",
    "amount",
    "volume",
    "turnover_rate",
    "vol_ratio_5d",
    "total_shares",
    "float_shares",
    "market_cap",
    "float_market_cap",
    "consecutive_limit_ups",
    "exchange",
    "quote_source",
    "quote_fetched_at",
)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _latest_quote_snapshot(data_dir: Path) -> tuple[date | None, pl.DataFrame]:
    base = data_dir / "quote_snapshot" / "asset_type=stock"
    candidates: list[tuple[date, Path]] = []
    try:
        from app.services.quote_service import usable_quote_snapshot_files
    except Exception:
        return None, pl.DataFrame()
    for child in base.glob("date=*"):
        partition_date = _as_date(child.name.removeprefix("date="))
        if partition_date is None:
            continue
        for path in usable_quote_snapshot_files(child):
            candidates.append((partition_date, path))

    for partition_date, path in sorted(candidates, reverse=True):
        try:
            frame = pl.read_parquet(path)
        except Exception:
            continue
        if not frame.is_empty() and "symbol" in frame.columns and "close" in frame.columns:
            return partition_date, frame
    return None, pl.DataFrame()


def _quote_volume_baselines(
    data_dir: Path,
    as_of: date,
    *,
    lookback: int = 5,
) -> dict[str, float]:
    """Return prior positive-volume means from canonical quote snapshots."""
    base = data_dir / "quote_snapshot" / "asset_type=stock"
    candidates: list[tuple[date, Path]] = []
    try:
        from app.services.quote_service import usable_quote_snapshot_files
    except Exception:
        return {}
    for child in base.glob("date=*"):
        partition_date = _as_date(child.name.removeprefix("date="))
        if partition_date is None or partition_date >= as_of:
            continue
        for path in usable_quote_snapshot_files(child):
            candidates.append((partition_date, path))

    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for _, path in sorted(candidates, reverse=True)[:lookback]:
        try:
            frame = pl.read_parquet(path)
        except Exception:
            continue
        if frame.is_empty() or not {"symbol", "volume"}.issubset(frame.columns):
            continue
        for row in frame.iter_rows(named=True):
            if row.get("unit_version") not in (None, "cn_quote_v1"):
                continue
            symbol = str(row.get("symbol") or "").strip()
            volume = _finite(row.get("volume"))
            if not symbol or volume is None or volume <= 0:
                continue
            totals[symbol] = totals.get(symbol, 0.0) + volume
            counts[symbol] = counts.get(symbol, 0) + 1
    return {symbol: totals[symbol] / counts[symbol] for symbol in totals if counts[symbol] > 0}


def _frame_by_symbol(frame: pl.DataFrame) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or "symbol" not in frame.columns:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in frame.iter_rows(named=True):
        symbol = str(row.get("symbol") or "").strip()
        if symbol:
            rows[symbol] = dict(row)
    return rows


def _instrument_map(repo) -> dict[str, dict[str, Any]]:
    try:
        frame = repo.get_instruments()
    except Exception:
        return {}
    return _frame_by_symbol(frame)


def build_market_snapshot(repo, screener_service) -> dict[str, Any]:
    """Build a date-consistent broad market snapshot with explicit coverage."""
    data_dir = Path(repo.store.data_dir)
    enriched_date = _as_date(screener_service.latest_date())
    enriched = (
        screener_service._load_enriched_for_date(enriched_date)
        if enriched_date is not None
        else pl.DataFrame()
    )
    quote_date, quotes = _latest_quote_snapshot(data_dir)

    dates = [value for value in (enriched_date, quote_date) if value is not None]
    if not dates:
        return {
            "as_of": None,
            "source": "none",
            "fetched_at": None,
            "coverage": {
                "instrument_rows": 0,
                "snapshot_rows": 0,
                "priced_rows": 0,
                "missing_rows": 0,
                "coverage_pct": 0.0,
                "markets": {},
            },
            "rows": [],
        }

    selected_date = max(dates)
    use_enriched = enriched_date == selected_date and not enriched.is_empty()
    use_quotes = quote_date == selected_date and not quotes.is_empty()

    merged: dict[str, dict[str, Any]] = {}
    if use_enriched:
        merged.update(_frame_by_symbol(enriched))

    fetched_at_values: list[str] = []
    quote_scopes: set[str] = set()
    quote_quality: set[str] = set()
    if use_quotes:
        for quote in quotes.iter_rows(named=True):
            symbol = str(quote.get("symbol") or "").strip()
            if not symbol:
                continue
            row = dict(merged.get(symbol, {}))
            for key in ("name", "close", "amount", "volume"):
                if quote.get(key) is not None:
                    row[key] = quote.get(key)
            quote_pct = _finite(quote.get("change_pct"))
            row["change_pct"] = quote_pct / 100.0 if quote_pct is not None else None
            row["symbol"] = symbol
            row["quote_source"] = quote.get("source")
            row["quote_fetched_at"] = quote.get("fetched_at")
            row["_canonical_volume"] = quote.get("unit_version") in (None, "cn_quote_v1")
            merged[symbol] = row

            if quote.get("fetched_at") is not None:
                fetched_at_values.append(str(quote["fetched_at"]))
            if quote.get("scope"):
                quote_scopes.add(str(quote["scope"]))
            if quote.get("quality_status"):
                quote_quality.add(str(quote["quality_status"]))

    instruments = _instrument_map(repo)
    volume_baselines = _quote_volume_baselines(data_dir, selected_date) if use_quotes else {}
    output_rows: list[dict[str, Any]] = []

    for symbol, raw in sorted(merged.items()):
        row = dict(raw)
        instrument = instruments.get(symbol, {})
        row["symbol"] = symbol
        row["name"] = row.get("name") or instrument.get("name")
        row["exchange"] = instrument.get("exchange")

        for key in ("total_shares", "float_shares"):
            if _finite(row.get(key)) is None:
                row[key] = instrument.get(key)

        close = _finite(row.get("close"))
        total_shares = _finite(row.get("total_shares"))
        float_shares = _finite(row.get("float_shares"))
        volume = _finite(row.get("volume"))
        if close is not None and total_shares is not None:
            row["market_cap"] = close * total_shares
        if close is not None and float_shares is not None:
            row["float_market_cap"] = close * float_shares

        canonical_volume = bool(row.pop("_canonical_volume", use_enriched and not use_quotes))
        if _finite(row.get("turnover_rate")) is None and canonical_volume and volume is not None and float_shares and float_shares > 0:
            # canonical volume uses lots; one lot is 100 shares.  UI turnover is percent points.
            row["turnover_rate"] = volume * 10_000.0 / float_shares
        if _finite(row.get("vol_ratio_5d")) is None and canonical_volume and volume is not None:
            baseline = volume_baselines.get(symbol)
            row["vol_ratio_5d"] = volume / baseline if baseline and baseline > 0 else None

        clean: dict[str, Any] = {}
        for key in _OUTPUT_FIELDS:
            value = row.get(key)
            if isinstance(value, (date, datetime)):
                value = value.isoformat()
            if isinstance(value, float) and not math.isfinite(value):
                value = None
            clean[key] = value
        output_rows.append(clean)

    priced_symbols = {
        row["symbol"]
        for row in output_rows
        if _finite(row.get("close")) is not None and _finite(row.get("change_pct")) is not None
    }
    instrument_rows = len(instruments)
    markets: dict[str, dict[str, int | float]] = {}
    for symbol, instrument in instruments.items():
        exchange = str(instrument.get("exchange") or "UNKNOWN")
        item = markets.setdefault(exchange, {"instruments": 0, "priced": 0, "coverage_pct": 0.0})
        item["instruments"] = int(item["instruments"]) + 1
        if symbol in priced_symbols:
            item["priced"] = int(item["priced"]) + 1
    for item in markets.values():
        denominator = int(item["instruments"])
        item["coverage_pct"] = round(int(item["priced"]) / denominator * 100.0, 2) if denominator else 0.0

    if use_quotes and use_enriched:
        source = "quote_snapshot+enriched"
    elif use_quotes:
        source = "quote_snapshot"
    else:
        source = "enriched"

    return {
        "as_of": selected_date.isoformat(),
        "source": source,
        "fetched_at": max(fetched_at_values) if fetched_at_values else None,
        "scope": ",".join(sorted(quote_scopes)) if quote_scopes else None,
        "quality_status": sorted(quote_quality),
        "coverage": {
            "instrument_rows": instrument_rows,
            "snapshot_rows": len(output_rows),
            "priced_rows": len(priced_symbols),
            "missing_rows": max(0, instrument_rows - len(priced_symbols)),
            "coverage_pct": round(len(priced_symbols) / instrument_rows * 100.0, 2) if instrument_rows else 0.0,
            "markets": markets,
        },
        "rows": output_rows,
    }
