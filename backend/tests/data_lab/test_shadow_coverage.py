"""Shadow listing/status coverage tests using temp fixtures only."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from app.data_lab.sources.shadow_coverage import (
    build_listing_events_from_instruments,
    build_status_history_shadow,
    compare_calendar_to_kline_partitions,
    summarize_listing_coverage,
)


def test_listing_events_skip_sentinel(tmp_path: Path) -> None:
    inst = tmp_path / "instruments.parquet"
    pl.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "name": "浦发银行",
                "exchange": "SH",
                "listing_date": date(1999, 11, 10),
            },
            {
                "symbol": "301677.SZ",
                "name": "bad",
                "exchange": "SZ",
                "listing_date": date(1970, 1, 1),
            },
        ]
    ).write_parquet(inst)
    events = build_listing_events_from_instruments(inst, as_of=date(2026, 7, 21))
    assert events.height == 1
    assert events.get_column("symbol").to_list() == ["600000.SH"]
    summary = summarize_listing_coverage(inst, events)
    assert summary["sentinel_listing_date_1970"] == 1
    assert summary["delist_events"] == 0
    assert summary["admission"] == "LAB_SHADOW_ONLY"


def test_status_shadow_from_halt_bars(tmp_path: Path) -> None:
    root = tmp_path / "kline_daily"
    day = root / "date=2026-07-20"
    day.mkdir(parents=True)
    pl.DataFrame(
        [
            {"symbol": "600000.SH", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5},
            {"symbol": "000001.SZ", "open": 0.0, "high": 0.0, "low": 0.0, "close": 8.0},
        ]
    ).write_parquet(day / "part.parquet")
    frame = build_status_history_shadow(root, sample_days=3, as_of=date(2026, 7, 21))
    assert frame.height == 1
    assert frame.get_column("symbol").to_list() == ["000001.SZ"]
    assert frame.get_column("status").to_list() == ["suspended"]
    assert frame.get_column("effective_from").to_list() == [date(2026, 7, 20)]
    assert frame.get_column("effective_to").to_list() == [date(2026, 7, 21)]


def test_calendar_kline_compare(tmp_path: Path) -> None:
    root = tmp_path / "kline_daily"
    for d in ["2026-07-01", "2026-07-02"]:
        p = root / f"date={d}"
        p.mkdir(parents=True)
        pl.DataFrame({"symbol": ["600000.SH"], "open": [1.0], "high": [1.0]}).write_parquet(
            p / "part.parquet"
        )
    cal = pl.DataFrame(
        {
            "exchange": ["SH", "SH", "SH"],
            "trade_date": [date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 4)],
            "is_open": [True, True, False],
        }
    )
    # create a closed-day partition smell
    bad = root / "date=2026-07-04"
    bad.mkdir()
    pl.DataFrame({"symbol": ["600000.SH"], "open": [1.0], "high": [1.0]}).write_parquet(
        bad / "part.parquet"
    )
    report = compare_calendar_to_kline_partitions(cal, root, exchange="SH")
    assert report["open_with_partition"] == 2
    assert report["closed_but_partition_exists_count"] == 1


def test_status_shadow_missing_symbol_fallback(tmp_path: Path) -> None:
    root = tmp_path / "kline_daily"
    day = root / "date=2026-07-20"
    day.mkdir(parents=True)
    # only one symbol present; halt bars already stripped
    pl.DataFrame(
        [
            {"symbol": "600000.SH", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0},
        ]
    ).write_parquet(day / "part.parquet")
    inst = tmp_path / "instruments.parquet"
    pl.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "name": "a",
                "exchange": "SH",
                "listing_date": date(1999, 11, 10),
            },
            {
                "symbol": "000001.SZ",
                "name": "b",
                "exchange": "SZ",
                "listing_date": date(1991, 4, 3),
            },
        ]
    ).write_parquet(inst)
    frame = build_status_history_shadow(
        root,
        sample_days=3,
        as_of=date(2026, 7, 21),
        instruments_path=inst,
    )
    assert frame.height == 1
    assert frame.get_column("symbol").to_list() == ["000001.SZ"]
    assert frame.get_column("reason").to_list() == ["missing_from_daily_partition"]
