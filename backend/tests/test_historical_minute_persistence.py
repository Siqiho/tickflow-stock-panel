from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import polars as pl
import pytest

from app.services.kline_sync import persist_historical_minute, validate_historical_minute


def _minute_frame(*, last_close: float = 47.82, volume_total: float = 2_245_847) -> pl.DataFrame:
    morning = [datetime(2026, 6, 29, 9, 30) + timedelta(minutes=i) for i in range(120)]
    afternoon = [datetime(2026, 6, 29, 13, 0) + timedelta(minutes=i) for i in range(120)]
    times = morning + afternoon
    prices = [50.92 - (50.92 - last_close) * i / 239 for i in range(240)]
    base = int(volume_total // 240)
    volumes = [float(base)] * 239
    volumes.append(float(volume_total - base * 239))
    return pl.DataFrame(
        {
            "symbol": ["301526.SZ"] * 240,
            "datetime": times,
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": volumes,
            "amount": [p * v * 100 for p, v in zip(prices, volumes, strict=True)],
        }
    )


def _daily_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": ["301526.SZ"],
            "date": [date(2026, 6, 29)],
            "close": [47.7995422],
            "raw_close": [47.82],
            "low": [45.6804492],
            "raw_low": [45.70],
            "high": [52.2476385],
            "raw_high": [52.27],
            "volume": [2_245_847.0],
            "amount": [10_823_434_410.0],
        }
    )


class _Repo:
    def __init__(self, data_dir):
        self.store = SimpleNamespace(data_dir=data_dir)
        self.refresh_count = 0

    def refresh_minute_views(self):
        self.refresh_count += 1


def test_historical_minute_persist_is_atomic_and_idempotent(tmp_path):
    repo = _Repo(tmp_path)
    frame = _minute_frame()

    first = persist_historical_minute(
        frame,
        repo,
        "301526.SZ",
        date(2026, 6, 29),
        _daily_frame(),
        source="easy_tdx_1.20.6",
    )
    second = persist_historical_minute(
        frame,
        repo,
        "301526.SZ",
        date(2026, 6, 29),
        _daily_frame(),
        source="easy_tdx_1.20.6",
    )

    target = tmp_path / "kline_minute" / "date=2026-06-29" / "part.parquet"
    stored = pl.read_parquet(target)
    assert first["rows_added"] == 240
    assert second["rows_added"] == 0
    assert stored.height == 240
    assert stored["datetime"].n_unique() == 240
    assert repo.refresh_count == 2


def test_historical_minute_close_mismatch_refuses_write(tmp_path):
    repo = _Repo(tmp_path)
    with pytest.raises(ValueError, match="close mismatch"):
        persist_historical_minute(
            _minute_frame(last_close=60.0),
            repo,
            "301526.SZ",
            date(2026, 6, 29),
            _daily_frame(),
            source="easy_tdx_1.20.6",
        )

    assert not (tmp_path / "kline_minute" / "date=2026-06-29" / "part.parquet").exists()


def test_historical_minute_volume_mismatch_refuses_write():
    with pytest.raises(ValueError, match="volume mismatch"):
        validate_historical_minute(
            _minute_frame(volume_total=1_000_000),
            "301526.SZ",
            date(2026, 6, 29),
            _daily_frame(),
        )
