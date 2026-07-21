"""Public trading-calendar probes for M5 Source Lab.

Primary producer in this slice:
  SZSE month calendar JSON
  GET http://www.szse.cn/api/report/exchange/onepersistenthour/monthList?month=YYYY-MM

Fields:
  jyrq: trade_date YYYY-MM-DD
  jybz: "1" open / "0" closed
  zrxh: weekday number from source (informational)

A-share cash equities on SH/SZ/BJ share the same regular session calendar in
normal conditions. Lab expands each SZSE day into SH/SZ/BJ rows and labels
source as ``szse_month_list`` with ``session_note=expanded_a_share``.
This is an explicit Lab hypothesis, not a silent invention of three independent
exchange feeds.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
import polars as pl

SZSE_MONTH_LIST_URL = (
    "http://www.szse.cn/api/report/exchange/onepersistenthour/monthList"
)
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": "http://www.szse.cn/",
}


class CalendarProbeError(RuntimeError):
    """Raised when a public calendar probe fails closed."""


def _parse_month(month: str) -> str:
    # Accept YYYY-MM or YYYY-M
    parts = month.split("-")
    if len(parts) != 2:
        raise ValueError(f"month must be YYYY-MM, got {month!r}")
    year = int(parts[0])
    mon = int(parts[1])
    if year < 1990 or mon < 1 or mon > 12:
        raise ValueError(f"invalid month {month!r}")
    return f"{year:04d}-{mon:02d}"


def month_range(start: date, end: date) -> list[str]:
    if end < start:
        raise ValueError("end before start")
    out: list[str] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y += 1
            m = 1
    return out


def fetch_szse_month_calendar(
    month: str,
    *,
    client: httpx.Client | None = None,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """Fetch one month of SZSE calendar rows (raw dicts)."""
    month_s = _parse_month(month)
    url = f"{SZSE_MONTH_LIST_URL}?{urlencode({'month': month_s})}"
    owns = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=True, headers=DEFAULT_HEADERS)
    try:
        resp = http.get(url)
        if resp.status_code >= 400:
            raise CalendarProbeError(f"SZSE HTTP {resp.status_code} for {month_s}")
        payload = resp.json()
    except CalendarProbeError:
        raise
    except Exception as exc:  # network/parse
        raise CalendarProbeError(f"SZSE fetch failed for {month_s}: {exc}") from exc
    finally:
        if owns:
            http.close()

    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise CalendarProbeError(f"SZSE empty/invalid calendar payload for {month_s}")
    cleaned: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        jyrq = str(item.get("jyrq") or "").strip()
        jybz = str(item.get("jybz") or "").strip()
        if not jyrq:
            continue
        cleaned.append(
            {
                "trade_date": jyrq,
                "is_open_flag": jybz,
                "weekday_code": item.get("zrxh"),
                "month": month_s,
            }
        )
    if not cleaned:
        raise CalendarProbeError(f"SZSE produced zero parseable rows for {month_s}")
    return cleaned


def fetch_szse_calendar_range(
    start: date,
    end: date,
    *,
    client: httpx.Client | None = None,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    owns = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=True, headers=DEFAULT_HEADERS)
    try:
        all_rows: list[dict[str, Any]] = []
        for month in month_range(start, end):
            all_rows.extend(fetch_szse_month_calendar(month, client=http, timeout=timeout))
        return all_rows
    finally:
        if owns:
            http.close()


def build_trading_calendar_from_szse(
    raw_rows: list[dict[str, Any]],
    *,
    as_of: date | None = None,
    exchanges: tuple[str, ...] = ("SH", "SZ", "BJ"),
    source: str = "szse_month_list",
) -> pl.DataFrame:
    """Normalize SZSE month rows into canonical trading_calendar frame."""
    as_of = as_of or date.today()
    if not raw_rows:
        return pl.DataFrame(
            schema={
                "exchange": pl.Utf8,
                "trade_date": pl.Date,
                "is_open": pl.Boolean,
                "session_type": pl.Utf8,
                "open_time": pl.Utf8,
                "close_time": pl.Utf8,
                "source": pl.Utf8,
                "as_of": pl.Date,
            }
        )

    base_rows: list[dict[str, Any]] = []
    for item in raw_rows:
        d = date.fromisoformat(str(item["trade_date"])[:10])
        is_open = str(item.get("is_open_flag")) == "1"
        session_type = "normal" if is_open else ("closed" if d.weekday() >= 5 else "holiday")
        for ex in exchanges:
            base_rows.append(
                {
                    "exchange": ex,
                    "trade_date": d,
                    "is_open": is_open,
                    "session_type": session_type,
                    "open_time": "09:30" if is_open else None,
                    "close_time": "15:00" if is_open else None,
                    "source": source,
                    "as_of": as_of,
                }
            )
    df = pl.DataFrame(base_rows)
    return (
        df.sort(["exchange", "trade_date"])
        .unique(subset=["exchange", "trade_date"], keep="last", maintain_order=True)
    )


def calendar_probe_meta(
    *,
    months: list[str],
    row_count: int,
    open_days: int,
    source: str = "szse_month_list",
) -> dict[str, Any]:
    return {
        "producer": source,
        "producer_kind": "exchange_public_http",
        "endpoint": SZSE_MONTH_LIST_URL,
        "rights_note": (
            "SZSE public website JSON used for Lab only; production rights/ToS "
            "still require explicit admission before formal publish."
        ),
        "expansion": "SH/SZ/BJ rows expanded from SZSE open flag",
        "months": months,
        "raw_day_count": row_count,
        "open_day_count": open_days,
        "fetched_at": datetime.now().astimezone().isoformat(),
    }
