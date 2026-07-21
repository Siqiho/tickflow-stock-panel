"""Single-symbol public intraday.

Primary: Tencent minute/query
Fallback: East Money trends2

Does not write full-market kline_minute parquet.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from app.services.free_sources.http_resilience import ResilientHttpClient, get_shared_client
from app.services.free_sources.quote_fallback import _to_tencent_code

logger = logging.getLogger(__name__)


def _to_em_secid(symbol: str) -> str | None:
    s = str(symbol or "").strip().upper()
    if not s:
        return None
    if "." in s:
        code, ex = s.split(".", 1)
    else:
        code, ex = s, ""
    code = code.zfill(6) if code.isdigit() else code
    if ex == "SH" or code.startswith(("5", "6", "9")):
        return f"1.{code}"
    if ex == "BJ" or code.startswith(("4", "8")):
        return f"0.{code}"
    return f"0.{code}"


def _parse_hhmm(raw: str) -> str | None:
    t = str(raw or "").strip()
    if not t:
        return None
    if ":" in t:
        # "09:30" / "09:30:00" / "2026-07-20 09:30"
        if " " in t:
            t = t.split()[-1]
        parts = t.split(":")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        return None
    digits = "".join(ch for ch in t if ch.isdigit())
    if len(digits) >= 12:  # yyyymmddHHMM...
        return f"{digits[8:10]}:{digits[10:12]}"
    if len(digits) >= 4:
        return f"{digits[:2]}:{digits[2:4]}"
    return None


def fetch_tencent_intraday(symbol: str, client: ResilientHttpClient | None = None) -> dict:
    client = client or get_shared_client()
    code = _to_tencent_code(symbol)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={code}"
    res = client.get_json(url, source_key="tencent_intraday", headers={"Referer": "https://gu.qq.com/"})
    if not res.ok:
        raise RuntimeError(res.error or "tencent intraday failed")
    data = res.data or {}
    node = ((data.get("data") or {}).get(code) or {}).get("data") or {}
    points_raw = node.get("data") or []
    points = []
    for item in points_raw:
        parts = str(item).split()
        if len(parts) < 2:
            continue
        try:
            price = float(parts[1])
        except ValueError:
            continue
        vol = None
        if len(parts) >= 3:
            try:
                vol = float(parts[2])
            except ValueError:
                vol = None
        amount = None
        if len(parts) >= 4:
            try:
                amount = float(parts[3])
            except ValueError:
                amount = None
        hhmm = _parse_hhmm(parts[0])
        if not hhmm:
            continue
        points.append({"time": hhmm, "price": price, "volume": vol, "amount": amount})
    day_raw = node.get("date") or node.get("date_str")
    trade_date = None
    if day_raw:
        try:
            s = str(day_raw).replace("-", "")[:8]
            trade_date = f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
        except Exception:
            trade_date = None
    return {
        "symbol": symbol.upper() if "." in symbol else symbol,
        "code": code,
        "points": points,
        "count": len(points),
        "trade_date": trade_date,
        "source": "tencent_minute",
        "persisted": False,
    }


def fetch_eastmoney_intraday(symbol: str, client: ResilientHttpClient | None = None) -> dict:
    """East Money trends2 (1-min session curve). Good backup when Tencent is thin/empty."""
    client = client or get_shared_client()
    secid = _to_em_secid(symbol)
    if not secid:
        raise RuntimeError("invalid symbol for eastmoney intraday")
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "secid": secid,
        "ndays": "1",
        "iscr": "0",
        "iscca": "0",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    from urllib.parse import urlencode
    hosts = (
        "https://push2.eastmoney.com/api/qt/stock/trends2/get",
        "https://push2delay.eastmoney.com/api/qt/stock/trends2/get",
        "https://push2his.eastmoney.com/api/qt/stock/trends2/get",
    )
    headers = {
        "Referer": "https://quote.eastmoney.com/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
    }
    payload = None
    errors: list[str] = []
    for base in hosts:
        full = f"{base}?{urlencode(params)}"
        res = client.get_json(
            full,
            source_key="em_intraday_trends2",
            headers=headers,
            timeout=12.0,
        )
        if res.ok and res.data is not None:
            payload = res.data
            break
        errors.append(f"{base}:{res.error or 'empty'}")
    if payload is None:
        raise RuntimeError("eastmoney trends2 failed: " + "; ".join(errors[-3:]))
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return {
            "symbol": symbol.upper(),
            "code": secid,
            "points": [],
            "count": 0,
            "trade_date": None,
            "source": "eastmoney_trends2",
            "persisted": False,
        }
    trends = data.get("trends") or []
    # each: "2026-07-20 09:30,price,open,high,low,close,volume,amount,avg"
    points = []
    trade_date = None
    for item in trends:
        parts = str(item).split(",")
        if len(parts) < 2:
            continue
        hhmm = _parse_hhmm(parts[0])
        if not hhmm:
            continue
        if trade_date is None:
            # leading yyyy-mm-dd
            head = parts[0].strip().split(" ")[0].replace("/", "-")
            if len(head) >= 10 and head[4] == "-":
                trade_date = head[:10]
        try:
            # prefer close (parts[5]) then price/open fields
            price = None
            for idx in (5, 1, 2):
                if len(parts) > idx and parts[idx] not in ("", "-"):
                    price = float(parts[idx])
                    break
            if price is None:
                continue
        except ValueError:
            continue
        vol = None
        amount = None
        try:
            if len(parts) > 6 and parts[6] not in ("", "-"):
                vol = float(parts[6])
        except ValueError:
            vol = None
        try:
            if len(parts) > 7 and parts[7] not in ("", "-"):
                amount = float(parts[7])
        except ValueError:
            amount = None
        points.append({"time": hhmm, "price": price, "volume": vol, "amount": amount})
    return {
        "symbol": symbol.upper() if "." in symbol else symbol,
        "code": secid,
        "points": points,
        "count": len(points),
        "trade_date": trade_date,
        "source": "eastmoney_trends2",
        "persisted": False,
    }


def fetch_public_intraday(symbol: str, client: ResilientHttpClient | None = None) -> dict:
    """Tencent first, East Money trends2 fallback."""
    client = client or get_shared_client()
    errors: list[str] = []
    try:
        out = fetch_tencent_intraday(symbol, client=client)
        if (out.get("count") or 0) >= 10:
            return out
        if (out.get("count") or 0) > 0:
            # thin but non-empty: still try EM and keep the richer one
            try:
                em = fetch_eastmoney_intraday(symbol, client=client)
                if (em.get("count") or 0) > (out.get("count") or 0):
                    return em
            except Exception as e:  # noqa: BLE001
                errors.append(f"em:{e}")
            return out
        errors.append("tencent:empty")
    except Exception as e:  # noqa: BLE001
        errors.append(f"tencent:{e}")
    try:
        return fetch_eastmoney_intraday(symbol, client=client)
    except Exception as e:  # noqa: BLE001
        errors.append(f"em:{e}")
        logger.warning("public intraday failed for %s: %s", symbol, "; ".join(errors))
        return {
            "symbol": symbol.upper() if "." in symbol else symbol,
            "code": _to_tencent_code(symbol),
            "points": [],
            "count": 0,
            "trade_date": None,
            "source": "none",
            "persisted": False,
            "errors": errors,
        }


def public_intraday_to_minute_rows(
    symbol: str,
    trade_date: date | None = None,
    client: ResilientHttpClient | None = None,
) -> list[dict[str, Any]]:
    """Convert public cumulative/session points into OHLC minute-like rows.

    Sources may send cumulative or per-minute volume/amount. We always emit
    non-negative deltas so chart volume bars stay sane.
    """
    payload = fetch_public_intraday(symbol, client=client)
    points = payload.get("points") or []
    if not points:
        return []

    day = trade_date or date.today()
    if payload.get("trade_date"):
        try:
            day = date.fromisoformat(str(payload["trade_date"]))
        except ValueError:
            pass
    # If caller asks a specific historical day and source only has another day,
    # still return rows (public sources rarely keep multi-day free minute).
    # StockIntradayChart will show whatever session arrived.

    sym = str(payload.get("symbol") or symbol).upper()
    rows: list[dict[str, Any]] = []
    prev_vol = 0.0
    prev_amt = 0.0
    for p in points:
        hhmm = _parse_hhmm(str(p.get("time") or ""))
        if not hhmm:
            continue
        try:
            dt = datetime.strptime(f"{day.isoformat()} {hhmm}", "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        price = p.get("price")
        if price is None:
            continue
        try:
            px = float(price)
        except (TypeError, ValueError):
            continue
        vol_raw = p.get("volume")
        amt_raw = p.get("amount")
        try:
            vol_c = float(vol_raw) if vol_raw is not None else prev_vol
        except (TypeError, ValueError):
            vol_c = prev_vol
        try:
            amt_c = float(amt_raw) if amt_raw is not None else prev_amt
        except (TypeError, ValueError):
            amt_c = prev_amt
        # cumulative -> delta; if source already delta and drops, fall back to raw
        if vol_c >= prev_vol:
            d_vol = vol_c - prev_vol
            prev_vol = vol_c
        else:
            d_vol = max(0.0, vol_c)
            prev_vol = vol_c
        if amt_c >= prev_amt:
            d_amt = amt_c - prev_amt
            prev_amt = amt_c
        else:
            d_amt = max(0.0, amt_c)
            prev_amt = amt_c
        rows.append(
            {
                "symbol": sym,
                "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "open": px,
                "high": px,
                "low": px,
                "close": px,
                "volume": d_vol,
                "amount": d_amt,
                "source": payload.get("source") or "public",
            }
        )
    return rows


def fetch_public_depth_l1(symbols: list[str], client: ResilientHttpClient | None = None) -> dict[str, dict]:
    """L1 depth via Tencent quotes: ask1_vol / bid1_vol for sealed judgment."""
    from app.services.free_sources.quote_fallback import fetch_tencent_quotes

    rows = fetch_tencent_quotes(symbols, client=client)
    out: dict[str, dict] = {}
    for r in rows:
        sym = r.get("symbol")
        if not sym:
            continue
        out[str(sym)] = {
            "symbol": sym,
            "ask1_vol": r.get("ask1_vol"),
            "bid1_vol": r.get("bid1_vol"),
            "ask1": r.get("ask1"),
            "bid1": r.get("bid1"),
            "last": r.get("last"),
            "source": r.get("source") or "tencent",
        }
    return out
