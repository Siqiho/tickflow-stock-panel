"""Calendar probe unit tests with httpx mock; optional live test marked."""

from __future__ import annotations

from datetime import date

import httpx
import polars as pl
import pytest

from app.data_lab.sources.calendar_probe import (
    CalendarProbeError,
    build_trading_calendar_from_szse,
    fetch_szse_month_calendar,
    month_range,
)


def test_month_range_basic() -> None:
    assert month_range(date(2026, 6, 15), date(2026, 7, 2)) == ["2026-06", "2026-07"]


def test_build_trading_calendar_expands_exchanges() -> None:
    raw = [
        {"trade_date": "2026-07-01", "is_open_flag": "1", "weekday_code": 4},
        {"trade_date": "2026-07-04", "is_open_flag": "0", "weekday_code": 7},
        {"trade_date": "2026-07-06", "is_open_flag": "0", "weekday_code": 2},
    ]
    df = build_trading_calendar_from_szse(raw, as_of=date(2026, 7, 21))
    assert df.height == 9
    assert set(df.get_column("exchange").unique().to_list()) == {"SH", "SZ", "BJ"}
    assert df.filter(pl.col("is_open")).height == 3
    holiday = df.filter(pl.col("trade_date") == date(2026, 7, 6))
    assert set(holiday.get_column("session_type").unique().to_list()) == {"holiday"}
    weekend = df.filter(pl.col("trade_date") == date(2026, 7, 4))
    assert set(weekend.get_column("session_type").unique().to_list()) == {"closed"}


def test_fetch_szse_month_calendar_parses_mock_transport() -> None:
    payload = {
        "data": [
            {"zrxh": 4, "jybz": "1", "jyrq": "2026-07-01"},
            {"zrxh": 7, "jybz": "0", "jyrq": "2026-07-04"},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "month=2026-07" in str(request.url)
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        rows = fetch_szse_month_calendar("2026-07", client=client)
    assert len(rows) == 2
    assert rows[0]["is_open_flag"] == "1"


def test_fetch_szse_month_calendar_empty_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client, pytest.raises(CalendarProbeError):
        fetch_szse_month_calendar("2026-07", client=client)


@pytest.mark.integration
def test_live_szse_month_optional() -> None:
    try:
        rows = fetch_szse_month_calendar("2026-07", timeout=10.0)
    except CalendarProbeError as exc:
        pytest.skip(f"SZSE live endpoint unavailable: {exc}")
    assert len(rows) >= 28
    assert any(r["is_open_flag"] == "1" for r in rows)
