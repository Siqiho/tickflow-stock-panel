"""Reference quality gate unit tests."""

from __future__ import annotations

from datetime import date

import polars as pl

from app.data_lab.fixtures import make_trading_calendar_frame
from app.data_lab.quality_reference import quality_passed, run_quality_checks


def test_calendar_open_requires_times() -> None:
    df = make_trading_calendar_frame(days=1).with_columns(
        pl.lit(None).alias("open_time"),
        pl.lit(None).alias("close_time"),
        pl.lit(True).alias("is_open"),
        pl.lit("normal").alias("session_type"),
    )
    # keep only weekday row if any
    df = df.filter(pl.col("trade_date") == date(2026, 7, 13))
    checks = run_quality_checks("trading_calendar", df)
    assert quality_passed(checks) is False
    assert any(c.code == "calendar_session_consistency" and not c.passed for c in checks)


def test_status_inverted_interval() -> None:
    df = pl.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "status": "trading",
                "effective_from": date(2026, 7, 10),
                "effective_to": date(2026, 7, 1),
                "reason": None,
                "source": "lab",
                "as_of": date(2026, 7, 21),
            }
        ]
    )
    checks = run_quality_checks("instrument_status_history", df)
    assert any(c.code == "status_intervals" and not c.passed for c in checks)
