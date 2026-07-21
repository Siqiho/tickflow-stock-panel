"""Deterministic offline fixtures for M5 reference Source Lab."""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl


def make_trading_calendar_frame(
    *,
    start: date = date(2026, 7, 13),
    days: int = 7,
    source: str = "lab_fixture",
    as_of: date | None = None,
    exchanges: tuple[str, ...] = ("SH", "SZ", "BJ"),
) -> pl.DataFrame:
    as_of = as_of or date(2026, 7, 21)
    rows: list[dict] = []
    for offset in range(days):
        d = start + timedelta(days=offset)
        is_weekend = d.weekday() >= 5
        for ex in exchanges:
            rows.append(
                {
                    "exchange": ex,
                    "trade_date": d,
                    "is_open": not is_weekend,
                    "session_type": "closed" if is_weekend else "normal",
                    "open_time": None if is_weekend else "09:30",
                    "close_time": None if is_weekend else "15:00",
                    "source": source,
                    "as_of": as_of,
                }
            )
    return pl.DataFrame(rows)


def make_status_history_frame(
    *,
    source: str = "lab_fixture",
    as_of: date | None = None,
) -> pl.DataFrame:
    as_of = as_of or date(2026, 7, 21)
    return pl.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "status": "trading",
                "effective_from": date(2020, 1, 2),
                "effective_to": None,
                "reason": None,
                "source": source,
                "as_of": as_of,
            },
            {
                "symbol": "000001.SZ",
                "status": "suspended",
                "effective_from": date(2026, 7, 1),
                "effective_to": date(2026, 7, 10),
                "reason": "example_halt",
                "source": source,
                "as_of": as_of,
            },
            {
                "symbol": "000001.SZ",
                "status": "trading",
                "effective_from": date(2026, 7, 10),
                "effective_to": None,
                "reason": "resumed",
                "source": source,
                "as_of": as_of,
            },
        ]
    )


def make_listing_events_frame(
    *,
    source: str = "lab_fixture",
    as_of: date | None = None,
) -> pl.DataFrame:
    as_of = as_of or date(2026, 7, 21)
    return pl.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "event_type": "list",
                "event_date": date(1999, 11, 10),
                "name": "浦发银行",
                "exchange": "SH",
                "prior_symbol": None,
                "source": source,
                "as_of": as_of,
            },
            {
                "symbol": "830799.BJ",
                "event_type": "list",
                "event_date": date(2021, 11, 15),
                "name": "example_bj",
                "exchange": "BJ",
                "prior_symbol": None,
                "source": source,
                "as_of": as_of,
            },
            {
                "symbol": "000002.SZ",
                "event_type": "code_change",
                "event_date": date(2010, 6, 1),
                "name": "example",
                "exchange": "SZ",
                "prior_symbol": "000001.SZ",
                "source": source,
                "as_of": as_of,
            },
        ]
    )
