from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from app.services import kline_sync


class _FakeRepo:
    def __init__(self, tmp_path: Path):
        self.store = type("S", (), {"data_dir": tmp_path})()
        self.flushed = None
        self.db = type("DB", (), {"execute": staticmethod(lambda *a, **k: None)})()

    def flush_live_daily(self, df: pl.DataFrame) -> None:
        self.flushed = df
        out = self.store.data_dir / "kline_daily" / f"date={df['date'][0].isoformat()}" / "part.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(out)


def test_public_quote_records_to_daily_maps_last_and_filters_halt():
    rows = [
        {"symbol": "000001.SZ", "last": 10.5, "open": 10.0, "high": 10.8, "low": 9.9, "volume": 1000, "amount": 1e6},
        {"symbol": "000002.SZ", "last": 5.0, "open": 0, "high": 0, "low": 0, "volume": 0, "amount": 0},  # halt
        {"symbol": "600000.SH", "last_price": 8.1, "open": None, "high": None, "low": None, "volume": 200, "amount": 2e5},
    ]
    df = kline_sync._public_quote_records_to_daily(rows, date(2026, 7, 20))
    assert set(df["symbol"].to_list()) == {"000001.SZ", "600000.SH"}
    row = df.filter(pl.col("symbol") == "600000.SH").to_dicts()[0]
    assert row["close"] == 8.1
    assert row["open"] == 8.1
    assert row["date"] == date(2026, 7, 20)


def test_sync_daily_by_public_quotes_writes_partition(tmp_path, monkeypatch):
    fake_rows = [
        {"symbol": "000001.SZ", "last": 10.5, "open": 10.0, "high": 10.8, "low": 9.9, "volume": 1000, "amount": 1e6},
        {"symbol": "600519.SH", "last": 1600.0, "open": 1590.0, "high": 1610.0, "low": 1580.0, "volume": 50, "amount": 8e7},
    ]
    monkeypatch.setattr(
        "app.services.free_sources.quote_fallback.fetch_public_market_quotes",
        lambda symbols, batch_size=80, pause_s=0.05: fake_rows,
    )
    repo = _FakeRepo(tmp_path)
    result = kline_sync.sync_daily_by_public_quotes(
        ["000001.SZ", "600519.SH"],
        repo,
        trade_date=date(2026, 7, 20),
    )
    assert result["rows"] == 2
    assert result["source"] == "public_quote_eod"
    assert result["date"] == "2026-07-20"
    assert repo.flushed is not None
    out = tmp_path / "kline_daily" / "date=2026-07-20" / "part.parquet"
    assert out.exists()
    df = pl.read_parquet(out)
    assert df.height == 2
    assert set(df["symbol"].to_list()) == {"000001.SZ", "600519.SH"}


def test_sync_daily_by_public_quotes_empty_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.free_sources.quote_fallback.fetch_public_market_quotes",
        lambda symbols, batch_size=80, pause_s=0.05: [],
    )
    repo = _FakeRepo(tmp_path)
    result = kline_sync.sync_daily_by_public_quotes(["000001.SZ"], repo, trade_date=date(2026, 7, 20))
    assert result["rows"] == 0
    assert repo.flushed is None
