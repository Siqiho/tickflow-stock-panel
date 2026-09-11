"""Dashboard default date selection must not write snapshots as official bars."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import polars as pl
import pytest

from app.services.market_overview_builder import (
    build_market_overview,
    resolve_overview_as_of,
)


class _Repo:
    def __init__(self, data_dir):
        self.store = SimpleNamespace(data_dir=data_dir)
        self._live = pl.DataFrame()
        self._live_date = None
        self._instruments = pl.DataFrame(
            [{"symbol": "000001.SZ", "name": "平安银行", "total_shares": 20_000.0, "float_shares": 10_000.0}]
        )

    def get_enriched_latest(self):
        return self._live, self._live_date

    def get_instruments(self):
        return self._instruments

    def get_enriched_history(self, *_args, **_kwargs):
        return pl.DataFrame()

    def execute_all(self, *_args, **_kwargs):
        return []


def _write_parquet(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path)


def _write_official(data_dir, day: str, rows: list[dict]) -> None:
    _write_parquet(data_dir / "kline_daily_enriched" / f"date={day}" / "part.parquet", rows)


def _write_quote(data_dir, day: str, rows: list[dict]) -> None:
    _write_parquet(
        data_dir / "quote_snapshot" / "asset_type=stock" / f"date={day}" / "part.parquet",
        rows,
    )


def _official_row(day: str) -> dict:
    return {
        "symbol": "000001.SZ",
        "date": date.fromisoformat(day),
        "open": 11.0,
        "high": 11.2,
        "low": 10.8,
        "close": 11.1,
        "volume": 100.0,
        "amount": 1_000_000.0,
        "raw_close": 11.1,
        "raw_high": 11.2,
        "raw_low": 10.8,
        "turnover_rate": 1.2,
        "consecutive_limit_ups": 0,
        "consecutive_limit_downs": 0,
    }


def _quote_row(change_pct: float = 2.5) -> dict:
    return {
        "symbol": "000001.SZ",
        "name": "平安银行",
        "close": 12.0,
        "prev_close": 11.7,
        "change_pct": change_pct,
        "amount": 2_000_000.0,
        "volume": 150.0,
    }


def test_unspecified_date_uses_today_snapshot_after_restart(tmp_path, monkeypatch) -> None:
    today = date(2026, 8, 18)
    from app.services import market_overview_builder as mob

    class _Date(date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr(mob, "date", _Date)
    _write_official(tmp_path, "2026-08-17", [_official_row("2026-08-17")])
    _write_quote(tmp_path, "2026-08-18", [_quote_row(2.5)])
    repo = _Repo(tmp_path)

    selection = resolve_overview_as_of(repo, None, default_to_live=True, today=today)
    assert selection["as_of"] == today
    assert selection["official_as_of"] == date(2026, 8, 17)
    assert selection["snapshot_as_of"] == today

    overview = build_market_overview(repo, as_of=None, default_to_live=True)
    assert overview["as_of"] == "2026-08-18"
    assert overview["data_mode"] == "intraday_snapshot"
    assert overview["breadth"]["total"] == 1
    assert overview["breadth"]["up"] == 1
    assert overview["amount"]["total"] == 2_000_000.0
    assert overview["trend"]["above_ma5"] == 0
    assert overview["limit"]["limit_up"] == 0
    assert overview["indicators_source"] == "intraday_approx"
    assert overview["indicators_approx"] is True
    assert overview["activity"]["vol_ratio"] is None
    assert overview["activity"]["vol_ready"] is False
    assert overview["activity"]["high_vol_ratio"] is None
    assert overview["trend"]["ready"] is False
    assert overview["trend"]["extremes_ready"] is False
    assert overview["limit"]["ready"] is True
    assert overview["limit"]["seal_rate"] is None
    money = next(item for item in overview["radar"] if item["key"] == "money")
    assert money["ready"] is False
    assert money["value"] is None
    ready_scores = [item["value"] for item in overview["radar"] if item["ready"]]
    assert ready_scores
    assert overview["emotion"]["score"] == round(sum(ready_scores) / len(ready_scores))
    assert overview["emotion"]["partial"] is True
    assert overview["emotion"]["note"] == "盘中部分维度不可用"
    assert not (tmp_path / "kline_daily" / "date=2026-08-18" / "part.parquet").exists()
    assert not (tmp_path / "kline_daily_enriched" / "date=2026-08-18" / "part.parquet").exists()


def test_pinned_history_stays_on_official_day(tmp_path, monkeypatch) -> None:
    today = date(2026, 8, 18)
    from app.services import market_overview_builder as mob

    class _Date(date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr(mob, "date", _Date)
    _write_official(tmp_path, "2026-08-17", [_official_row("2026-08-17")])
    _write_quote(tmp_path, "2026-08-18", [_quote_row(8.0)])

    overview = build_market_overview(_Repo(tmp_path), as_of=date(2026, 8, 17), default_to_live=False)
    assert overview["as_of"] == "2026-08-17"
    assert overview["data_mode"] == "official"
    assert overview["amount"]["total"] == 1_000_000.0
    assert overview["breadth"]["up"] == 0


def test_same_day_official_partition_wins_over_snapshot(tmp_path, monkeypatch) -> None:
    today = date(2026, 8, 18)
    from app.services import market_overview_builder as mob

    class _Date(date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr(mob, "date", _Date)
    _write_official(tmp_path, "2026-08-18", [_official_row("2026-08-18")])
    _write_quote(tmp_path, "2026-08-18", [_quote_row(9.0)])

    overview = build_market_overview(_Repo(tmp_path), as_of=None, default_to_live=True)
    assert overview["as_of"] == "2026-08-18"
    assert overview["data_mode"] == "official"
    assert overview["amount"]["total"] == 1_000_000.0


def test_intraday_active_leaders_use_derived_turnover(tmp_path, monkeypatch) -> None:
    today = date(2026, 8, 18)
    from app.services import market_overview_builder as mob

    class _Date(date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr(mob, "date", _Date)
    _write_official(tmp_path, "2026-08-17", [_official_row("2026-08-17")])
    _write_quote(
        tmp_path,
        "2026-08-18",
        [
            {**_quote_row(1.0), "symbol": "000001.SZ", "name": "平安银行", "volume": 150.0},
            {
                "symbol": "600186.SH",
                "name": "莲花控股",
                "close": 8.0,
                "prev_close": 7.5,
                "change_pct": 6.6,
                "amount": 3_000_000.0,
                "volume": 500.0,
            },
        ],
    )
    repo = _Repo(tmp_path)
    repo._instruments = pl.DataFrame(
        [
            {"symbol": "000001.SZ", "name": "平安银行", "float_shares": 10_000.0, "total_shares": 20_000.0},
            {"symbol": "600186.SH", "name": "莲花控股", "float_shares": 8_000.0, "total_shares": 9_000.0},
        ]
    )
    overview = build_market_overview(repo, as_of=None, default_to_live=True)
    leaders = overview["active_leaders"]
    assert overview["data_mode"] == "intraday_snapshot"
    assert [row["symbol"] for row in leaders] == ["600186.SH", "000001.SZ"]
    assert leaders[0]["turnover_rate"] == 625.0
    assert leaders[1]["turnover_rate"] == 150.0
    assert not (tmp_path / "kline_daily_enriched" / "date=2026-08-18" / "part.parquet").exists()


def _patch_today(monkeypatch, today: date) -> None:
    from app.services import market_overview_builder as mob

    class _Date(date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr(mob, "date", _Date)


def test_intraday_approx_fills_volume_ratio_limit_and_ma(tmp_path, monkeypatch) -> None:
    today = date(2026, 8, 18)
    _patch_today(monkeypatch, today)
    for offset, close in enumerate((10.0, 10.2, 10.4, 10.6, 10.8), start=13):
        day = f"2026-08-{offset}"
        shared = {
            "close": close,
            "raw_close": close,
            "consecutive_limit_ups": 2 if day == "2026-08-17" else 0,
        }
        _write_official(
            tmp_path,
            day,
            [
                {**_official_row(day), **shared},
                {**_official_row(day), **shared, "symbol": "300001.SZ"},
            ],
        )
    _write_quote(
        tmp_path,
        "2026-08-15",
        [{**_quote_row(1.0), "volume": 100.0, "unit_version": "cn_quote_v1"}],
    )
    _write_quote(
        tmp_path,
        "2026-08-18",
        [
            {
                "symbol": "000001.SZ",
                "name": "平安银行",
                "close": 12.87,
                "high": 12.87,
                "low": 11.8,
                "prev_close": 11.7,
                "change_pct": 10.0,
                "amount": 2_000_000.0,
                "volume": 180.0,
                "unit_version": "cn_quote_v1",
            },
            {
                "symbol": "300001.SZ",
                "name": "特锐德",
                "close": 11.90,
                "high": 12.00,
                "low": 11.50,
                "prev_close": 10.0,
                "change_pct": 19.0,
                "amount": 1_000_000.0,
                "volume": 80.0,
                "unit_version": "cn_quote_v1",
            },
        ],
    )

    overview = build_market_overview(_Repo(tmp_path), as_of=None, default_to_live=True)
    assert overview["data_mode"] == "intraday_snapshot"
    assert overview["indicators_source"] == "intraday_approx"
    assert overview["limit"]["limit_up"] == 1
    assert overview["limit"]["broken"] == 1
    assert overview["limit"]["max_boards"] == 3
    assert overview["limit"]["tiers"] == [{"boards": 3, "count": 1}]
    assert overview["activity"]["vol_ratio"] == 1.8
    assert overview["activity"]["vol_ready"] is True
    assert overview["trend"]["above_ma5"] == 2
    assert overview["trend"]["above_ma5_pct"] == 100.0
    assert overview["trend"]["ready"] is True
    assert overview["limit"]["ready"] is True
    assert overview["limit"]["source"] == "intraday_approx"
    assert overview["limit"]["source_as_of"] is None
    assert overview["limit"]["seal_rate"] == 50.0
    money = next(item for item in overview["radar"] if item["key"] == "money")
    assert money["ready"] is True
    assert money["value"] is not None
    assert overview["emotion"]["partial"] is True
    assert overview["emotion"]["note"] == "盘中部分维度不可用"
    assert not (tmp_path / "kline_daily_enriched" / "date=2026-08-18" / "part.parquet").exists()


def test_intraday_approx_uses_st_rule_not_stale_instrument_limit(tmp_path, monkeypatch) -> None:
    today = date(2026, 8, 18)
    _patch_today(monkeypatch, today)
    _write_official(tmp_path, "2026-08-17", [_official_row("2026-08-17")])
    _write_quote(
        tmp_path,
        "2026-08-18",
        [
            {
                "symbol": "000010.SZ",
                "name": "*ST美丽",
                "close": 1.61,
                "high": 1.61,
                "low": 1.50,
                "prev_close": 1.53,
                "change_pct": 5.23,
                "amount": 800_000.0,
                "volume": 40.0,
            }
        ],
    )
    repo = _Repo(tmp_path)
    repo._instruments = pl.DataFrame(
        [
            {
                "symbol": "000010.SZ",
                "name": "*ST美丽",
                "float_shares": 10_000.0,
                "total_shares": 20_000.0,
                "limit_up": 1.80,
                "limit_down": 1.20,
            }
        ]
    )
    overview = build_market_overview(repo, as_of=None, default_to_live=True)
    assert overview["limit"]["limit_up"] == 1
    assert overview["limit"]["broken"] == 0


def _write_hithink_pool(data_dir, day: str, rows: list[dict]) -> None:
    from app.services.free_sources.hithink_finance import normalize_limit_pool

    trade_date = date.fromisoformat(day)
    frames = []
    for kind in ("limit_up", "limit_down", "limit_break"):
        kind_rows = [row for row in rows if row.get("pool_kind") == kind]
        if not kind_rows:
            continue
        frames.append(normalize_limit_pool(kind, kind_rows, trade_date, timestamp_ms=1))
    if not frames:
        return
    _write_parquet(
        data_dir / "reference" / "hithink_limit_pool" / f"date={day}" / "part.parquet",
        pl.concat(frames, how="vertical").to_dicts(),
    )


def test_intraday_kpi_uses_same_day_hithink_pool_not_yesterday(tmp_path, monkeypatch) -> None:
    today = date(2026, 8, 18)
    _patch_today(monkeypatch, today)
    _write_official(tmp_path, "2026-08-17", [_official_row("2026-08-17")])
    _write_quote(tmp_path, "2026-08-18", [{**_quote_row(2.5), "high": 12.0, "volume": 150.0}])
    _write_hithink_pool(
        tmp_path,
        "2026-08-17",
        [
            {"pool_kind": "limit_up", "thscode": f"{600000 + index:06d}.SH", "name": "昨日冒充", "continue_day_cnt": 6}
            for index in range(65)
        ],
    )
    _write_hithink_pool(
        tmp_path,
        "2026-08-18",
        [
            {"pool_kind": "limit_up", "thscode": "600519.SH", "name": "贵州茅台", "continue_day_cnt": 4},
            {"pool_kind": "limit_up", "thscode": "000002.SZ", "name": "万科A", "continue_day_cnt": 1},
            {"pool_kind": "limit_down", "thscode": "000001.SZ", "name": "平安银行"},
            {"pool_kind": "limit_break", "thscode": "300001.SZ", "name": "特锐德", "open_times": 2},
        ],
    )

    overview = build_market_overview(_Repo(tmp_path), as_of=None, default_to_live=True)
    assert overview["data_mode"] == "intraday_snapshot"
    assert overview["indicators_source"] == "intraday_approx"
    assert overview["limit"]["source"] == "hithink_official_pool"
    assert overview["limit"]["source_as_of"] == "2026-08-18"
    assert overview["limit"]["limit_up"] == 2
    assert overview["limit"]["limit_down"] == 1
    assert overview["limit"]["broken"] == 1
    assert overview["limit"]["max_boards"] == 4
    assert overview["limit"]["tiers"] == [{"boards": 4, "count": 1}, {"boards": 1, "count": 1}]
    assert overview["limit"]["seal_rate"] == pytest.approx(66.666, rel=1e-3)


def test_intraday_kpi_keeps_approx_when_today_hithink_pool_missing(tmp_path, monkeypatch) -> None:
    today = date(2026, 8, 18)
    _patch_today(monkeypatch, today)
    _write_official(tmp_path, "2026-08-17", [_official_row("2026-08-17")])
    _write_quote(
        tmp_path,
        "2026-08-18",
        [{
            "symbol": "000001.SZ",
            "name": "平安银行",
            "close": 12.87,
            "high": 12.87,
            "low": 11.8,
            "prev_close": 11.7,
            "change_pct": 10.0,
            "amount": 2_000_000.0,
            "volume": 150.0,
        }],
    )
    _write_hithink_pool(
        tmp_path,
        "2026-08-17",
        [
            {"pool_kind": "limit_up", "thscode": f"{600000 + index:06d}.SH", "name": "昨日冒充", "continue_day_cnt": 6}
            for index in range(65)
        ],
    )

    overview = build_market_overview(_Repo(tmp_path), as_of=None, default_to_live=True)
    assert overview["data_mode"] == "intraday_snapshot"
    assert overview["limit"]["source"] == "intraday_approx"
    assert overview["limit"]["source_as_of"] is None
    assert overview["limit"]["limit_up"] == 1
    assert overview["limit"]["limit_up"] != 65


def test_official_day_ignores_same_day_hithink_pool(tmp_path, monkeypatch) -> None:
    today = date(2026, 8, 18)
    _patch_today(monkeypatch, today)
    _write_official(tmp_path, "2026-08-18", [_official_row("2026-08-18")])
    _write_quote(tmp_path, "2026-08-18", [_quote_row(9.0)])
    _write_hithink_pool(
        tmp_path,
        "2026-08-18",
        [
            {"pool_kind": "limit_up", "thscode": f"{600519 + index:06d}.SH", "name": "贵州茅台", "continue_day_cnt": 5}
            for index in range(8)
        ],
    )

    overview = build_market_overview(_Repo(tmp_path), as_of=None, default_to_live=True)
    assert overview["data_mode"] == "official"
    assert overview["limit"]["source"] == "official"
    assert overview["limit"]["source_as_of"] is None
    assert overview["limit"]["limit_up"] == 0
