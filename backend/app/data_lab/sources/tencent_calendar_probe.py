"""Tencent index daily open-day probe as a secondary calendar cross-check.

This is NOT an official SSE calendar API. It uses the Shanghai Composite
(`sh000001`) daily bar dates from Tencent finance as an open-day series that
historically tracks the SH cash-equity session calendar.

Use only for Lab cross-check against SZSE monthList (or cached SZSE frames).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from urllib.parse import quote

import httpx

TENCENT_FQKLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.qq.com/",
    "Accept": "*/*",
}


class TencentCalendarProbeError(RuntimeError):
    """Raised when the Tencent open-day probe fails closed."""


def fetch_tencent_open_days(
    *,
    code: str = "sh000001",
    start: date,
    end: date,
    limit: int = 2000,
    client: httpx.Client | None = None,
    timeout: float = 10.0,
    retries: int = 2,
) -> list[date]:
    """Return sorted unique open days implied by Tencent daily bars."""
    if end < start:
        raise ValueError("end before start")
    param = f"{code},day,{start.isoformat()},{end.isoformat()},{int(limit)},qfq"
    url = f"{TENCENT_FQKLINE_URL}?param={quote(param, safe=',')}"

    owns = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=True, headers=DEFAULT_HEADERS)
    payload: dict[str, Any] | None = None
    try:
        for attempt in range(max(1, retries + 1)):
            try:
                resp = http.get(url)
                if resp.status_code >= 400:
                    raise TencentCalendarProbeError(
                        f"Tencent HTTP {resp.status_code} for {code} {start}..{end}"
                    )
                payload = resp.json()
                break
            except TencentCalendarProbeError:
                raise
            except Exception as exc:  # network/parse
                if attempt >= retries:
                    raise TencentCalendarProbeError(
                        f"Tencent fetch failed for {code}: {exc}"
                    ) from exc
        assert payload is not None
    finally:
        if owns:
            http.close()

    if str(payload.get("code")) not in {"0", "0.0"} and payload.get("code") not in {0, None}:
        # Tencent uses code=0 on success; some errors still 200 with msg.
        msg = payload.get("msg") or payload.get("message") or "unknown"
        # empty data with param error
        data = payload.get("data")
        if not data:
            raise TencentCalendarProbeError(f"Tencent error for {code}: {msg}")

    rows = _extract_day_rows(payload, code)
    if not rows:
        raise TencentCalendarProbeError(
            f"Tencent returned zero day rows for {code} {start}..{end}"
        )

    days: list[date] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or not row:
            continue
        ds = str(row[0])[:10]
        try:
            d = date.fromisoformat(ds)
        except ValueError:
            continue
        if start <= d <= end:
            days.append(d)
    out = sorted(set(days))
    if not out:
        raise TencentCalendarProbeError(
            f"Tencent produced no parseable dates in range for {code}"
        )
    return out


def _extract_day_rows(payload: dict[str, Any], code: str) -> list[Any]:
    data = payload.get("data")
    if isinstance(data, dict):
        block = data.get(code)
        if isinstance(block, dict):
            rows = block.get("day") or block.get("qfqday") or block.get("hfqday") or []
            return rows if isinstance(rows, list) else []
        if isinstance(block, list):
            return block
        # sometimes single key
        for value in data.values():
            if isinstance(value, dict):
                rows = value.get("day") or value.get("qfqday") or []
                if isinstance(rows, list) and rows:
                    return rows
            if isinstance(value, list) and value:
                return value
        return []
    if isinstance(data, list):
        return data
    return []


def tencent_probe_meta(
    *,
    code: str,
    start: date,
    end: date,
    open_days: list[date],
) -> dict[str, Any]:
    return {
        "producer": "tencent_index_daily_open_days",
        "producer_kind": "secondary_open_day_series",
        "not_official_sse_api": True,
        "code": code,
        "endpoint": TENCENT_FQKLINE_URL,
        "window": [start.isoformat(), end.isoformat()],
        "open_day_count": len(open_days),
        "first": open_days[0].isoformat() if open_days else None,
        "last": open_days[-1].isoformat() if open_days else None,
        "rights_note": (
            "Tencent public quote API used as Lab cross-check only; "
            "not a substitute for exchange-official calendar rights admission."
        ),
        "fetched_at": datetime.now().astimezone().isoformat(),
    }
