"""Lab runner tests — temp lab_dir + mocked calendar transport."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from app.data_lab import lab_runner as lab_runner_mod
from app.data_lab.lab_runner import LabRunConfig, run_reference_source_lab
from app.data_lab.sources import calendar_probe as cp


def test_run_reference_source_lab_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "prod_ro"
    lab = tmp_path / "lab"
    (source / "instruments").mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "name": "浦发银行",
                "exchange": "SH",
                "listing_date": date(1999, 11, 10),
            },
            {
                "symbol": "000001.SZ",
                "name": "平安银行",
                "exchange": "SZ",
                "listing_date": date(1991, 4, 3),
            },
        ]
    ).write_parquet(source / "instruments" / "instruments.parquet")

    day = source / "kline_daily" / "date=2026-07-20"
    day.mkdir(parents=True)
    pl.DataFrame(
        [
            {"symbol": "600000.SH", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0},
            {"symbol": "000001.SZ", "open": 0.0, "high": 0.0, "low": 0.0, "close": 10.0},
        ]
    ).write_parquet(day / "part.parquet")

    def fake_range(start, end, *, client=None, timeout=10.0):
        assert start <= end
        # two months compressed into few days
        return [
            {"trade_date": "2026-07-01", "is_open_flag": "1", "weekday_code": 3, "month": "2026-07"},
            {"trade_date": "2026-07-02", "is_open_flag": "1", "weekday_code": 4, "month": "2026-07"},
            {"trade_date": "2026-07-04", "is_open_flag": "0", "weekday_code": 6, "month": "2026-07"},
            {"trade_date": "2026-07-06", "is_open_flag": "0", "weekday_code": 1, "month": "2026-07"},
        ]

    monkeypatch.setattr(lab_runner_mod, "fetch_szse_calendar_range", fake_range)
    monkeypatch.setattr(cp, "fetch_szse_calendar_range", fake_range)

    report = run_reference_source_lab(
        LabRunConfig(
            lab_dir=lab,
            source_data_dir=source,
            calendar_start=date(2026, 7, 1),
            calendar_end=date(2026, 7, 10),
            as_of=date(2026, 7, 21),
            fetch_public_calendar=True,
            status_sample_days=3,
        )
    )
    assert report["ok"] is True
    assert report["production_publish"]["status"] == "NO_GO"
    assert (lab / "reference" / "trading_calendar" / "calendar.parquet").exists()
    assert (lab / "reference" / "listing_delisting_events" / "events.parquet").exists()
    assert (lab / "reference" / "instrument_status_history" / "status_history.parquet").exists()
    # production source tree unchanged aside from our fixture setup
    assert list((source / "reference").glob("**/*")) == [] if (source / "reference").exists() else True
    assert report["admission"]["trading_calendar"]["status"] == "LAB_PASS_CANDIDATE"
    assert report["admission"]["listing_delisting_events"]["status"] == "LAB_SHADOW_ONLY"
    assert report["admission"]["instrument_status_history"]["status"] == "LAB_SHADOW_ONLY"


def test_lab_dir_refuses_non_empty_without_marker(tmp_path: Path) -> None:
    lab = tmp_path / "lab"
    lab.mkdir()
    (lab / "stray.txt").write_text("nope", encoding="utf-8")
    with pytest.raises(RuntimeError, match="refusing"):
        run_reference_source_lab(LabRunConfig(lab_dir=lab, fetch_public_calendar=False))
