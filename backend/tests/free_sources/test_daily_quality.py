from __future__ import annotations

from pathlib import Path

import polars as pl

from app.services.daily_quality import run_daily_quality_check


def test_quality_flags_negative_volume(tmp_path: Path):
    d = tmp_path / "kline_daily" / "date=2026-07-07"
    d.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["000001.SZ", "000002.SZ"],
            "date": ["2026-07-07", "2026-07-07"],
            "open": [10.0, 6.0],
            "high": [11.0, 6.5],
            "low": [9.5, 5.8],
            "close": [10.5, 6.2],
            "volume": [1000.0, -5.0],
            "amount": [10500.0, 0.0],
        }
    ).write_parquet(d / "part.parquet")
    report = run_daily_quality_check(tmp_path, date="2026-07-07")
    assert report["ok"] is False
    codes = {i["code"] for i in report["issues"]}
    assert "negative_volume" in codes
    assert "zero_amount" in codes
    assert (tmp_path / "user_data" / "daily_quality_latest.json").exists()
