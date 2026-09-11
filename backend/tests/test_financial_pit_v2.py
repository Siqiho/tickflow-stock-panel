from __future__ import annotations

from datetime import date

import polars as pl

from app.services.financial_pit import (
    FINANCIAL_UNIT_VERSION,
    ensure_pit_columns,
    filter_as_of,
    pit_warning_payload,
)


def test_never_fill_announce_date_from_report_date():
    df = pl.DataFrame(
        {
            "symbol": ["000001.SZ"],
            "report_date": [date(2024, 12, 31)],
            "total_revenue": [1.0],
        }
    )
    out = ensure_pit_columns(df, table="income")
    assert out["announce_date"].to_list() == [None]
    assert out["available_at"].to_list() == [None]
    assert out["pit_unsafe"].to_list() == [True]
    assert out["unit_version"].to_list() == [FINANCIAL_UNIT_VERSION]
    assert out["history_guarantee"].to_list() == ["as_collected"]


def test_strict_as_of_excludes_unsafe_and_future_announce():
    df = pl.DataFrame(
        {
            "symbol": ["000001.SZ", "000001.SZ", "000002.SZ"],
            "report_date": [date(2024, 12, 31), date(2024, 12, 31), date(2024, 12, 31)],
            "announce_date": [date(2025, 3, 31), date(2025, 4, 15), None],
            "total_revenue": [100.0, 110.0, 90.0],
            "restatement_id": ["a", "b", "c"],
        }
    )
    out = ensure_pit_columns(df, table="income")
    strict = filter_as_of(out, date(2025, 4, 1), table="income", strict=True)
    # only first restatement available and safe
    assert strict.height == 1
    assert strict["total_revenue"].to_list() == [100.0]
    # non-strict still requires available_at
    nonstrict = filter_as_of(out, date(2025, 4, 1), table="income", strict=False)
    assert nonstrict.height == 1


def test_shares_snapshot_marked_unsafe():
    df = pl.DataFrame(
        {
            "symbol": ["000001.SZ"],
            "effective_date": [date(2026, 7, 22)],
            "announce_date": [date(2026, 7, 22)],
            "total_shares": [1e9],
            "source": ["instruments_snapshot"],
        }
    )
    out = ensure_pit_columns(df, table="shares")
    assert out["pit_unsafe"].to_list() == [True]
    strict = filter_as_of(out, date(2026, 7, 22), table="shares", strict=True)
    assert strict.is_empty()
    warn = pit_warning_payload(out, table="shares")
    assert warn["has_non_pit_rows"] is True
