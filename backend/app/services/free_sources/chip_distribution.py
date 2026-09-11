"""Approximate chip distribution from local daily bars.

Ported algorithm idea from go-stock chip_distribution.go (myhhub-style):
turnover decay + VWAP/typical-price Gaussian kernel. Not exchange official chips.
"""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Any

from app.services.free_sources.kline_loader import load_daily_bars_for_symbol

_DISCLAIMER = (
    "Approximate chip distribution derived from local daily OHLCV + turnover decay. "
    "Not exchange official chip peak data."
)
_METHOD = "approx_turnover_decay_vwap_kernel"


def _finite(x: float) -> bool:
    return not (math.isnan(x) or math.isinf(x))


def _clamp(x: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, x))


def _round(v: float, digits: int) -> float:
    p = 10**digits
    return round(v * p) / p


def _parse_turnover(v: Any) -> float:
    """Return turnover as 0~1 fraction."""
    if v is None:
        return 0.0
    if isinstance(v, str):
        s = v.strip().rstrip("%")
        if not s or s in {"-", "null"}:
            return 0.0
        try:
            v = float(s)
        except ValueError:
            return 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    # values like 2.5 mean 2.5%; values like 0.025 mean fraction
    if f > 1.0:
        f = f / 100.0
    return _clamp(f, 0.0, 0.98)


def _bar_cost_center(low: float, high: float, open_: float, close: float, vol: float, amount: float) -> float:
    if low <= 0 or high <= 0 or high < low or not _finite(low) or not _finite(high):
        if _finite(low) and _finite(high):
            return (low + high) / 2
        return 0.0
    if amount > 0 and vol > 0:
        vwap = amount / vol
        # TickFlow volume often in 手(100 shares). If amount is 元 and volume is 手,
        # amount/volume already ≈ 元/手 = 元/(100股)*100? Heuristic: if vwap outside
        # [low, high] by large margin, try amount/(vol*100).
        if _finite(vwap) and vwap > 0:
            if low <= vwap <= high:
                return vwap
            vwap100 = amount / (vol * 100.0)
            if _finite(vwap100) and low <= vwap100 <= high:
                return vwap100
            return _clamp(vwap if abs(vwap - (low + high) / 2) < abs(vwap100 - (low + high) / 2) else vwap100, low, high)
    if close > 0 and _finite(close):
        tp = (high + low + close) / 3
        if _finite(tp):
            return _clamp(tp, low, high)
    if open_ > 0 and close > 0 and _finite(open_) and _finite(close):
        tp = (high + low + open_ + close) / 4
        if _finite(tp):
            return _clamp(tp, low, high)
    return (high + low) / 2


def _add_kernel(dist: list[float], bins: int, min_p: float, width: float, low: float, high: float, vol: float, center: float) -> None:
    if vol <= 0 or low <= 0 or high <= 0:
        return
    lo, hi = (high, low) if high < low else (low, high)
    span = hi - lo
    lo_idx = int(math.floor((lo - min_p) / width))
    hi_idx = int(math.floor((hi - min_p) / width))
    lo_idx = max(0, min(bins - 1, lo_idx))
    hi_idx = max(0, min(bins - 1, hi_idx))
    if hi_idx < lo_idx:
        return
    if span < 1e-9 * max(1.0, hi):
        mid = (lo + hi) / 2
        i = int(math.floor((mid - min_p) / width))
        i = max(0, min(bins - 1, i))
        dist[i] += vol
        return
    m = center if _finite(center) else (lo + hi) / 2
    m = _clamp(m, lo, hi)
    sigma = max(span * 0.18, max(hi * 1e-6, 1e-6))
    wsum = 0.0
    weights: list[tuple[int, float]] = []
    for i in range(lo_idx, hi_idx + 1):
        bc = min_p + (i + 0.5) * width
        if bc < lo or bc > hi:
            continue
        d = (bc - m) / sigma
        w = math.exp(-0.5 * d * d)
        weights.append((i, w))
        wsum += w
    if wsum <= 0:
        cnt = float(hi_idx - lo_idx + 1)
        add = vol / cnt
        for i in range(lo_idx, hi_idx + 1):
            dist[i] += add
        return
    for i, w in weights:
        dist[i] += vol * w / wsum


def _cost_at_ratio(items: list[dict], target: float) -> float:
    if not items:
        return 0.0
    if target <= 0:
        return float(items[0]["price"])
    if target >= 1:
        return float(items[-1]["price"])
    acc = 0.0
    for item in items:
        acc += float(item["ratio"])
        if acc >= target:
            return float(item["price"])
    return float(items[-1]["price"])


def _cost_range(items: list[dict], ratio: float) -> dict:
    ratio = _clamp(ratio, 0.0, 1.0)
    low = _cost_at_ratio(items, (1 - ratio) / 2)
    high = _cost_at_ratio(items, (1 + ratio) / 2)
    concentration = 0.0
    if low + high > 0:
        concentration = (high - low) / (low + high)
    return {
        "low_price": _round(low, 4),
        "high_price": _round(high, 4),
        "concentration": _round(concentration, 6),
    }


def calculate_chip_distribution(symbol: str, bars: list[dict], bins: int = 80) -> dict:
    if not bars:
        raise ValueError("K线数据为空")
    if bins <= 0:
        bins = 80
    bins = min(bins, 300)

    min_p = math.inf
    max_p = 0.0
    for b in bars:
        lo = float(b.get("low") or 0)
        hi = float(b.get("high") or 0)
        if lo > 0:
            min_p = min(min_p, lo)
        if hi > 0:
            max_p = max(max_p, hi)
    if not math.isfinite(min_p) or max_p <= 0 or max_p < min_p:
        raise ValueError("无法从K线推导价格区间")
    if max_p == min_p:
        max_p = min_p * 1.001
    width = (max_p - min_p) / bins
    if width <= 0:
        raise ValueError("价格分箱宽度无效")

    dist = [0.0] * bins
    for b in bars:
        turn = _parse_turnover(b.get("turnover_rate"))
        remain = 1.0 - turn
        for i in range(bins):
            dist[i] *= remain
        low = float(b.get("low") or 0)
        high = float(b.get("high") or 0)
        vol = float(b.get("volume") or 0)
        if vol <= 0 or low <= 0 or high <= 0:
            continue
        if high < low:
            low, high = high, low
        open_ = float(b.get("open") or 0)
        close = float(b.get("close") or 0)
        amount = float(b.get("amount") or 0)
        center = _bar_cost_center(low, high, open_, close, vol, amount)
        _add_kernel(dist, bins, min_p, width, low, high, vol, center)

    total = sum(dist)
    last = bars[-1]
    cur = float(last.get("close") or 0) or float(last.get("high") or 0)
    last_date = last.get("date")
    as_of = str(last_date)[:10] if last_date is not None else None
    items: list[dict] = []
    avg_cost = 0.0
    profit_vol = 0.0
    for i in range(bins):
        center = min_p + (i + 0.5) * width
        vol = dist[i]
        ratio = (vol / total) if total > 0 else 0.0
        items.append({"price": _round(center, 4), "vol": _round(vol, 4), "ratio": _round(ratio, 6)})
        avg_cost += vol * center
        if center <= cur:
            profit_vol += vol
    if total > 0:
        avg_cost /= total
    profit_ratio = (profit_vol / total) if total > 0 else 0.0

    return {
        "symbol": symbol,
        "as_of": as_of,
        "days": len(bars),
        "bins": bins,
        "current": _round(cur, 4),
        "avg_cost": _round(avg_cost, 4),
        "median_cost": _round(_cost_at_ratio(items, 0.5), 4),
        "profit_ratio": _round(profit_ratio, 6),
        "min_price": _round(min_p, 4),
        "max_price": _round(max_p, 4),
        "sum_vol": _round(total, 4),
        "cost70": _cost_range(items, 0.7),
        "cost90": _cost_range(items, 0.9),
        "items": items,
        "method": _METHOD,
        "disclaimer": _DISCLAIMER,
        "source": "local_daily_derived",
    }


def chips_for_symbol(
    data_dir: Path,
    symbol: str,
    *,
    days: int = 120,
    bins: int = 80,
    as_of: date | None = None,
) -> dict:
    bars = load_daily_bars_for_symbol(data_dir, symbol, days=days, as_of=as_of)
    return calculate_chip_distribution(symbol, bars, bins=bins)
