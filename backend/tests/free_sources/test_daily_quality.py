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


def test_quality_rejects_ten_thousand_cny_amount_units(tmp_path: Path):
    d = tmp_path / "kline_daily" / "date=2026-07-20"
    d.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["000001.SZ", "600000.SH", "688549.SH"],
            "date": ["2026-07-20"] * 3,
            "open": [10.0, 10.0, 10.0],
            "high": [10.5, 10.5, 10.5],
            "low": [9.5, 9.5, 9.5],
            "close": [10.0, 10.0, 10.0],
            "volume": [1_000_000.0, 2_000_000.0, 3_000_000.0],
            # Tencent raw field 37: ten-thousand CNY, incorrectly stored as CNY.
            "amount": [100_000.0, 200_000.0, 300_000.0],
        }
    ).write_parquet(d / "part.parquet")

    report = run_daily_quality_check(tmp_path, date="2026-07-20")

    assert report["ok"] is False
    assert "amount_unit_mismatch" in {issue["code"] for issue in report["issues"]}
    assert report["metrics"]["amount_volume_price_ratio"]["median"] < 0.001
