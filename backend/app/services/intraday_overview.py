"""盘中看板近似指标：只读本地快照 + 昨日正式日，不写正式日 K。"""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import polars as pl

_LIMIT_TOLERANCE = 0.005
_OVERLAY_LOOKBACK_DAYS = 150
_overlay_cache: tuple[str, int, dict[str, dict[str, Any]]] | None = None


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_date(value: Any) -> date | None:
    if isinstance(value, date) and not hasattr(value, "hour"):
        return value
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def board_limit_pct(symbol: str, name: str | None = None) -> float:
    """板块默认涨跌停比例；ST 名称覆盖为 5%。不使用维表旧涨跌停价。"""
    text = str(name or "")
    if "ST" in text:
        return 0.05
    code = str(symbol or "").split(".", 1)[0]
    if str(symbol or "").endswith(".BJ"):
        return 0.30
    if code.startswith(("300", "301", "688", "689")):
        return 0.20
    return 0.10


def theoretical_limit_price(prev_close: float, limit_pct: float, *, up: bool) -> float:
    """交易所四舍五入到分：round(prev × (1 ± limit), 2)。"""
    sign = 1 if up else -1
    num = int(round((1 + sign * limit_pct) * 100))
    cents = int(math.floor(prev_close * 100 + 0.5))
    return ((cents * num + 50) // 100) / 100.0


def classify_intraday_limit(
    *,
    symbol: str,
    name: str | None,
    close: float | None,
    high: float | None,
    prev_close: float | None,
) -> dict[str, Any]:
    prev = _finite(prev_close)
    last = _finite(close)
    peak = _finite(high)
    if prev is None or prev <= 0 or last is None or last <= 0:
        return {
            "signal_limit_up": False,
            "signal_limit_down": False,
            "signal_broken_limit_up": False,
            "limit_up_price": None,
            "limit_down_price": None,
        }

    pct = board_limit_pct(symbol, name)
    up_price = theoretical_limit_price(prev, pct, up=True)
    down_price = theoretical_limit_price(prev, pct, up=False)
    limit_up = abs(last - up_price) < _LIMIT_TOLERANCE
    limit_down = abs(last - down_price) < _LIMIT_TOLERANCE
    touched_up = peak is not None and peak > 0 and peak >= up_price - _LIMIT_TOLERANCE
    return {
        "signal_limit_up": limit_up,
        "signal_limit_down": limit_down,
        "signal_broken_limit_up": (not limit_up) and bool(touched_up),
        "limit_up_price": up_price,
        "limit_down_price": down_price,
    }


def _partition_mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def load_official_trend_overlay(data_dir: Path, official_as_of: date) -> dict[str, dict[str, Any]]:
    """昨日正式日的均线/60 日高低/连板高度。不含今日快照，避免写成正式日。"""
    global _overlay_cache
    root = Path(data_dir) / "kline_daily_enriched"
    official_path = root / f"date={official_as_of.isoformat()}" / "part.parquet"
    cache_key = f"{Path(data_dir).resolve()}|{official_as_of.isoformat()}"
    stamp = _partition_mtime_ns(official_path)
    if _overlay_cache and _overlay_cache[0] == cache_key and _overlay_cache[1] == stamp:
        return _overlay_cache[2]
    if not official_path.exists():
        _overlay_cache = (cache_key, stamp, {})
        return {}

    from app.services.kline_sync import daily_partition_usable, filter_daily_cache

    if not daily_partition_usable(official_path):
        _overlay_cache = (cache_key, stamp, {})
        return {}

    start = official_as_of - timedelta(days=_OVERLAY_LOOKBACK_DAYS)
    frames: list[pl.DataFrame] = []
    for child in root.glob("date=*"):
        day = _as_date(child.name.removeprefix("date="))
        part = child / "part.parquet"
        if day is None or day < start or day > official_as_of or not part.exists():
            continue
        if not daily_partition_usable(part):
            continue
        try:
            frame = filter_daily_cache(pl.read_parquet(part))
        except Exception:
            continue
        keep = [col for col in ("symbol", "date", "close", "consecutive_limit_ups") if col in frame.columns]
        if "symbol" not in keep or "close" not in keep:
            continue
        frames.append(frame.select(keep))
    if not frames:
        _overlay_cache = (cache_key, stamp, {})
        return {}

    history = pl.concat(frames, how="vertical_relaxed")
    history = history.with_columns(pl.col("date").cast(pl.Date, strict=False))
    history = history.filter(
        pl.col("symbol").is_not_null()
        & pl.col("date").is_not_null()
        & (pl.col("date") >= start)
        & (pl.col("date") <= official_as_of)
    )
    if history.is_empty():
        _overlay_cache = (cache_key, stamp, {})
        return {}

    history = (
        history.sort(["symbol", "date"])
        .unique(subset=["symbol", "date"], keep="last")
        .sort(["symbol", "date"])
        .with_columns(
            [
                pl.col("close").rolling_mean(5).over("symbol").alias("ma5"),
                pl.col("close").rolling_mean(20).over("symbol").alias("ma20"),
                pl.col("close").rolling_mean(60).over("symbol").alias("ma60"),
                pl.col("close").rolling_max(60).over("symbol").alias("high_60d"),
                pl.col("close").rolling_min(60).over("symbol").alias("low_60d"),
            ]
        )
        .filter(pl.col("date") == official_as_of)
    )

    overlay: dict[str, dict[str, Any]] = {}
    for raw in history.to_dicts():
        symbol = str(raw.get("symbol") or "").strip()
        if not symbol:
            continue
        overlay[symbol] = {
            "ma5": _finite(raw.get("ma5")),
            "ma20": _finite(raw.get("ma20")),
            "ma60": _finite(raw.get("ma60")),
            "high_60d": _finite(raw.get("high_60d")),
            "low_60d": _finite(raw.get("low_60d")),
            "consecutive_limit_ups": int(_finite(raw.get("consecutive_limit_ups")) or 0),
        }
    _overlay_cache = (cache_key, stamp, overlay)
    return overlay


def apply_intraday_snapshot_overlay(
    rows: list[dict[str, Any]],
    *,
    official_overlay: dict[str, dict[str, Any]] | None = None,
    volume_baselines: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """给盘中快照行补量比、涨跌停近似和昨日均线。"""
    overlay = official_overlay or {}
    baselines = volume_baselines or {}
    for row in rows:
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        volume = _finite(row.get("volume"))
        if _finite(row.get("vol_ratio_5d")) is None and volume is not None:
            baseline = baselines.get(symbol)
            row["vol_ratio_5d"] = volume / baseline if baseline and baseline > 0 else None

        flags = classify_intraday_limit(
            symbol=symbol,
            name=str(row.get("name") or "") or None,
            close=_finite(row.get("close")),
            high=_finite(row.get("high")),
            prev_close=_finite(row.get("prev_close")),
        )
        row["signal_limit_up"] = bool(flags["signal_limit_up"])
        row["signal_limit_down"] = bool(flags["signal_limit_down"])
        row["signal_broken_limit_up"] = bool(flags["signal_broken_limit_up"])
        prior_boards = int(_finite((overlay.get(symbol) or {}).get("consecutive_limit_ups")) or 0)
        row["consecutive_limit_ups"] = prior_boards + 1 if flags["signal_limit_up"] else 0

        prior = overlay.get(symbol) or {}
        for key in ("ma5", "ma20", "ma60", "high_60d", "low_60d"):
            if _finite(row.get(key)) is None and _finite(prior.get(key)) is not None:
                row[key] = prior.get(key)
    return rows
