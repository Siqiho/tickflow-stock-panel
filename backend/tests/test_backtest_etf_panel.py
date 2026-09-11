"""ETF backtest panel uses kline_etf_enriched without replacing stock cache."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from app.backtest.engine import BacktestEngine


class _Repo:
    def __init__(self, data_dir: Path) -> None:
        self.store = type("Store", (), {"data_dir": data_dir})()
        self.stock_hits = 0

    def get_enriched_range(self, start, end, symbols=None, columns=None):
        self.stock_hits += 1
        return pl.DataFrame(
            {
                "symbol": ["600000.SH"],
                "date": [date(2026, 7, 15)],
                "open": [10.0], "high": [11.0], "low": [9.0],
                "close": [10.5], "volume": [100.0], "amount": [1000.0],
            }
        )

    def get_instruments(self) -> pl.DataFrame:
        return pl.DataFrame({"symbol": ["600000.SH"], "name": ["stock"]})

    def get_instruments_asset(self, asset_type: str) -> pl.DataFrame:
        if asset_type == "etf":
            return pl.DataFrame({"symbol": ["510300.SH"], "name": ["etf"]})
        return self.get_instruments()


def test_etf_panel_reads_etf_dir_and_keeps_stock_cache(tmp_path: Path) -> None:
    etf_dir = tmp_path / "kline_etf_enriched" / "date=2026-07-15"
    etf_dir.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["510300.SH"],
            "date": [date(2026, 7, 15)],
            "open": [4.0], "high": [4.2], "low": [3.9],
            "close": [4.1], "volume": [50.0], "amount": [200.0],
        }
    ).write_parquet(etf_dir / "part.parquet")
    repo = _Repo(tmp_path)
    engine = BacktestEngine(repo)

    stock = engine.load_panel(None, date(2026, 7, 15), date(2026, 7, 15), asset_type="stock")
    etf = engine.load_panel(None, date(2026, 7, 15), date(2026, 7, 15), asset_type="etf")

    assert stock["symbol"].to_list() == ["600000.SH"]
    assert etf["symbol"].to_list() == ["510300.SH"]
    assert repo.stock_hits >= 1
    stock_again = engine.load_panel(None, date(2026, 7, 15), date(2026, 7, 15), asset_type="stock")
    assert stock_again["symbol"].to_list() == ["600000.SH"]


def test_strategy_backtest_service_passes_asset_type_to_load_panel() -> None:
    from types import SimpleNamespace

    from app.backtest.strategy import StrategyBacktestConfig, StrategyBacktestService

    seen: dict[str, str] = {}

    def load_panel(symbols, start, end, columns=None, asset_type="stock"):
        seen["asset_type"] = asset_type
        return pl.DataFrame()

    strategy = SimpleNamespace(
        lookback_days=20,
        entry_signals=[],
        exit_signals=[],
        stop_loss=None,
        take_profit=None,
        trailing_stop=None,
        trailing_take_profit_activate=None,
        trailing_take_profit_drawdown=None,
        max_hold_days=None,
        basic_filter={},
        meta={},
        source="test",
    )
    svc = StrategyBacktestService(
        SimpleNamespace(load_panel=load_panel),
        SimpleNamespace(get=lambda _sid: strategy),
    )
    result = svc.run(StrategyBacktestConfig(
        strategy_id="fixture",
        symbols=["510300.SH"],
        start=date(2026, 7, 1),
        end=date(2026, 7, 15),
        asset_type="etf",
    ))
    assert seen["asset_type"] == "etf"
    assert result.error == "无数据，请检查日期范围或先运行盘后管道"
