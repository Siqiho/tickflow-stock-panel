from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import polars as pl
import pytest

from app.api import data as data_api
from app.indicators import pipeline
from app.services import financial_sync
from app.tickflow.capabilities import CapabilitySet
from app.tickflow.repository import DataStore, KlineRepository


def _write_instruments(data_dir, symbols: list[str]) -> None:
    path = data_dir / "instruments" / "instruments.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"symbol": symbols}).write_parquet(path)


def _limit_bars(dates: list[date], volume: float = 10_000.0) -> pl.DataFrame:
    """Local compute_limit_signals requires OHLCV + raw/change columns."""
    n = len(dates)
    close = [10.0] * n
    return pl.DataFrame({
        "symbol": ["600000.SH"] * n,
        "date": dates,
        "open": close,
        "high": [10.1] * n,
        "low": [9.9] * n,
        "close": close,
        "raw_close": close,
        "raw_high": [10.1] * n,
        "volume": [volume] * n,
        "change_pct": [0.0] * n,
        "vol_ratio_5d": [1.0] * n,
    })


def test_sync_shares_calls_local_sync_table(tmp_path, monkeypatch):
    _write_instruments(tmp_path, ["600000.SH"])
    calls: list[tuple[str, list[str], bool]] = []

    def fake_sync(table, symbols, data_dir, capset, latest_only=True):
        calls.append((table, list(symbols), latest_only))
        out = data_dir / "financials" / table
        out.mkdir(parents=True, exist_ok=True)
        pl.DataFrame({
            "symbol": ["600000.SH"],
            "period_end": ["2024-06-30"],
            "float_shares": [12.0],
        }).write_parquet(out / "part.parquet")
        return 1

    monkeypatch.setattr(financial_sync, "_sync_table", fake_sync)
    rows = financial_sync.sync_shares(tmp_path, CapabilitySet())

    assert rows == 1
    assert calls == [("shares", ["600000.SH"], True)]
    stored = pl.read_parquet(tmp_path / "financials" / "shares" / "part.parquet")
    assert stored["float_shares"].to_list() == [12.0]


def test_sync_shares_overwrites_existing_parquet(tmp_path, monkeypatch):
    _write_instruments(tmp_path, ["600000.SH", "000001.SZ"])
    path = tmp_path / "financials" / "shares" / "part.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({
        "symbol": ["600000.SH"],
        "period_end": ["2024-06-30"],
        "float_shares": [10.0],
    }).write_parquet(path)

    def fake_sync(table, symbols, data_dir, capset, latest_only=True):
        assert table == "shares"
        assert set(symbols) == {"600000.SH", "000001.SZ"}
        assert latest_only is True
        out = data_dir / "financials" / table / "part.parquet"
        pl.DataFrame({
            "symbol": ["600000.SH", "000001.SZ"],
            "period_end": ["2024-06-30", "2024-06-30"],
            "float_shares": [11.0, 21.0],
        }).write_parquet(out)
        return 2

    monkeypatch.setattr(financial_sync, "_sync_table", fake_sync)
    rows = financial_sync.sync_shares(tmp_path, CapabilitySet())
    stored = pl.read_parquet(path).sort("symbol")
    assert rows == 2
    assert stored["float_shares"].to_list() == [21.0, 11.0]


def test_public_financial_path_uses_shares_snapshot(tmp_path, monkeypatch):
    _write_instruments(tmp_path, ["600000.SH"])
    received: list[list[str]] = []

    def fake_snapshot(data_dir, symbols=None):
        received.append(list(symbols or []))
        out = data_dir / "financials" / "shares"
        out.mkdir(parents=True, exist_ok=True)
        pl.DataFrame({
            "symbol": ["600000.SH"],
            "period_end": ["2024-06-30"],
            "float_shares": [10.0],
        }).write_parquet(out / "part.parquet")
        return 1

    monkeypatch.setattr(financial_sync, "_use_public_financials", lambda: True)
    monkeypatch.setattr(
        "app.services.free_sources.financials_public.sync_shares_snapshot",
        fake_snapshot,
    )
    rows = financial_sync._sync_table(
        "shares",
        ["600000.SH"],
        tmp_path,
        CapabilitySet(),
        latest_only=True,
    )
    assert rows == 1
    assert received == [["600000.SH"]]


def test_historical_turnover_uses_only_available_share_capital(monkeypatch):
    monkeypatch.setattr(pipeline, "cn_today", lambda: date(2026, 7, 18))
    bars = _limit_bars([
        date(2024, 3, 31),
        date(2024, 4, 14),
        date(2024, 4, 15),
        date(2024, 6, 30),
        date(2026, 7, 18),
    ])
    instruments = pl.DataFrame({
        "symbol": ["600000.SH"],
        "float_shares": [200_000_000.0],
    })
    shares = pl.DataFrame({
        "symbol": ["600000.SH", "600000.SH"],
        "period_end": ["2023-12-31", "2024-06-30"],
        "announce_date": ["2024-04-15", None],
        "float_shares": [100_000_000.0, 50_000_000.0],
    })

    result = pipeline.compute_limit_signals(
        bars,
        instruments,
        historical_shares=shares,
    )
    assert result["turnover_rate"].to_list() == pytest.approx([0.5, 0.5, 1.0, 2.0, 0.5])


def test_turnover_without_share_history_keeps_existing_behavior(monkeypatch):
    monkeypatch.setattr(pipeline, "cn_today", lambda: date(2026, 7, 18))
    bars = _limit_bars([date(2024, 4, 15)])
    instruments = pl.DataFrame({
        "symbol": ["600000.SH"],
        "float_shares": [200_000_000.0],
    })
    result = pipeline.compute_limit_signals(bars, instruments)
    assert result["turnover_rate"][0] == pytest.approx(0.5)


def test_repository_get_historical_shares_empty_and_cached(tmp_path):
    repo = KlineRepository(DataStore(tmp_path))
    empty = repo.get_historical_shares()
    assert empty.is_empty()

    path = tmp_path / "financials" / "shares" / "part.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({
        "symbol": ["600000.SH"],
        "period_end": ["2024-06-30"],
        "float_shares": [12.0],
    }).write_parquet(path)
    loaded = repo.get_historical_shares()
    assert loaded.height == 1
    assert loaded["float_shares"][0] == pytest.approx(12.0)
    again = repo.get_historical_shares()
    assert again.height == 1


def test_data_status_excludes_shares_from_statement_aggregate(tmp_path):
    """Local _safe_aggregate_financials only counts statement tables, not shares."""
    path = tmp_path / "financials" / "shares" / "part.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({
        "symbol": ["600000.SH", "600000.SH", "000001.SZ"],
        "period_end": ["2023-12-31", "2024-06-30", "2024-06-30"],
    }).write_parquet(path)

    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    assert data_api._safe_aggregate_financials(repo) is None

    metrics = tmp_path / "financials" / "metrics" / "part.parquet"
    metrics.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"symbol": ["600000.SH", "000001.SZ"]}).write_parquet(metrics)
    result = data_api._safe_aggregate_financials(repo)
    assert result is not None
    assert result["rows"] == 2
    assert "shares" not in result["tables"]
    assert result["tables"]["metrics"] == {"rows": 2, "symbols": 2}
