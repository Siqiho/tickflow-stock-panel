"""Calendar second-source cross-check tests (no live network)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from app.data_lab.sources import calendar_crosscheck as cc
from app.data_lab.sources import tencent_calendar_probe as tcp
from app.data_lab.sources.calendar_crosscheck import (
    CalendarCrosscheckConfig,
    run_calendar_second_source_crosscheck,
)


def _szse_frame() -> pl.DataFrame:
    # 4 calendar days, 2 open
    rows = []
    for ex in ("SH", "SZ", "BJ"):
        for d, is_open, session in [
            (date(2026, 7, 1), True, "normal"),
            (date(2026, 7, 2), True, "normal"),
            (date(2026, 7, 4), False, "closed"),
            (date(2026, 7, 6), False, "holiday"),
        ]:
            rows.append(
                {
                    "exchange": ex,
                    "trade_date": d,
                    "is_open": is_open,
                    "session_type": session,
                    "open_time": "09:30" if is_open else None,
                    "close_time": "15:00" if is_open else None,
                    "source": "szse_month_list",
                    "as_of": date(2026, 7, 21),
                }
            )
    return pl.DataFrame(rows)


def test_crosscheck_equal_second_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "szse_cache.parquet"
    _szse_frame().write_parquet(cache)
    lab = tmp_path / "lab"

    def fake_tx(*, code="sh000001", start=None, end=None, **kwargs):
        # open days match szse
        return [date(2026, 7, 1), date(2026, 7, 2)]

    monkeypatch.setattr(tcp, "fetch_tencent_open_days", fake_tx)
    monkeypatch.setattr(cc, "fetch_tencent_open_days", fake_tx)

    report = run_calendar_second_source_crosscheck(
        CalendarCrosscheckConfig(
            lab_dir=lab,
            start=date(2026, 7, 1),
            end=date(2026, 7, 10),
            as_of=date(2026, 7, 21),
            fetch_live_szse=False,
            szse_cache_parquet=cache,
            fetch_tencent=True,
        )
    )
    assert report["ok"] is True
    assert report["comparisons"]["szse_sh_vs_tencent_sh"]["equal"] is True
    assert report["comparisons"]["tencent_sh_vs_tencent_sz"]["equal"] is True
    assert report["admission"]["trading_calendar"]["status"] == "LAB_PASS_CANDIDATE_SECOND_SOURCE_OK"
    assert report["admission"]["trading_calendar"]["discuss_standalone_production_publish"] == "DISCUSS_ONLY"
    assert report["production_publish"]["status"] == "NO_GO"
    assert (lab / "lab_reports" / "calendar_second_source_crosscheck.json").exists()


def test_crosscheck_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "szse_cache.parquet"
    _szse_frame().write_parquet(cache)

    def fake_tx(*, code="sh000001", start=None, end=None, **kwargs):
        return [date(2026, 7, 1), date(2026, 7, 3)]  # 7-3 not in szse open

    monkeypatch.setattr(tcp, "fetch_tencent_open_days", fake_tx)
    monkeypatch.setattr(cc, "fetch_tencent_open_days", fake_tx)

    report = run_calendar_second_source_crosscheck(
        CalendarCrosscheckConfig(
            lab_dir=tmp_path / "lab2",
            start=date(2026, 7, 1),
            end=date(2026, 7, 10),
            as_of=date(2026, 7, 21),
            fetch_live_szse=False,
            szse_cache_parquet=cache,
        )
    )
    assert report["ok"] is False
    assert report["admission"]["trading_calendar"]["status"] == "LAB_FAIL_MISMATCH"
    assert report["admission"]["trading_calendar"]["discuss_standalone_production_publish"] == "NO"
