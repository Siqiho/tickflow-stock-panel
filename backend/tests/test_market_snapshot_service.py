"""Coverage contract tests for the industry-analysis market snapshot."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import polars as pl
import pytest

from app.services.market_snapshot import build_market_snapshot


class _Repo:
    def __init__(self, data_dir, instruments: list[dict]):
        self.store = SimpleNamespace(data_dir=data_dir)
        self._instruments = pl.DataFrame(instruments)

    def get_instruments(self):
        return self._instruments


class _Screener:
    def __init__(self, as_of: date | None, enriched: pl.DataFrame):
        self._as_of = as_of
        self._enriched = enriched

    def latest_date(self):
        return self._as_of

    def _load_enriched_for_date(self, target_date):
        assert target_date == self._as_of
        return self._enriched


def _write_quote(data_dir, day: str, rows: list[dict]) -> None:
    path = data_dir / "quote_snapshot" / "asset_type=stock" / f"date={day}" / "part.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path)


def _instruments() -> list[dict]:
    return [
        {
            "symbol": "000001.SZ",
            "name": "平安银行",
            "exchange": "SZ",
            "total_shares": 20_000.0,
            "float_shares": 10_000.0,
        },
        {
            "symbol": "600000.SH",
            "name": "浦发银行",
            "exchange": "SH",
            "total_shares": 40_000.0,
            "float_shares": 20_000.0,
        },
        {
            "symbol": "920001.BJ",
            "name": "北交样本",
            "exchange": "BJ",
            "total_shares": 5_000.0,
            "float_shares": 4_000.0,
        },
    ]


def test_same_day_full_quote_snapshot_expands_bounded_enriched_scope(tmp_path) -> None:
    _write_quote(
        tmp_path,
        "2026-08-07",
        [
            {"symbol": "000001.SZ", "volume": 100.0, "unit_version": "cn_quote_v1"},
            {"symbol": "600000.SH", "volume": 200.0, "unit_version": "cn_quote_v1"},
        ],
    )
    _write_quote(
        tmp_path,
        "2026-08-10",
        [
            {
                "symbol": "000001.SZ",
                "name": "平安银行",
                "close": 12.0,
                "change_pct": 2.5,
                "amount": 1_200_000.0,
                "volume": 150.0,
                "source": "tencent",
                "unit_version": "cn_quote_v1",
                "scope": "full_market",
                "quality_status": "intraday_partial",
                "fetched_at": "2026-08-10T15:06:00+08:00",
            },
            {
                "symbol": "600000.SH",
                "name": "浦发银行",
                "close": 10.0,
                "change_pct": -1.0,
                "amount": 2_000_000.0,
                "volume": 300.0,
                "source": "tencent",
                "unit_version": "cn_quote_v1",
                "scope": "full_market",
                "quality_status": "intraday_partial",
                "fetched_at": "2026-08-10T15:06:00+08:00",
            },
        ],
    )
    enriched = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "close": 11.8,
                "change_pct": 0.01,
                "consecutive_limit_ups": 2,
            }
        ]
    )

    result = build_market_snapshot(
        _Repo(tmp_path, _instruments()),
        _Screener(date(2026, 8, 10), enriched),
    )

    assert result["source"] == "quote_snapshot+enriched"
    assert result["as_of"] == "2026-08-10"
    assert result["coverage"] == {
        "instrument_rows": 3,
        "snapshot_rows": 2,
        "priced_rows": 2,
        "missing_rows": 1,
        "coverage_pct": 66.67,
        "markets": {
            "SZ": {"instruments": 1, "priced": 1, "coverage_pct": 100.0},
            "SH": {"instruments": 1, "priced": 1, "coverage_pct": 100.0},
            "BJ": {"instruments": 1, "priced": 0, "coverage_pct": 0.0},
        },
    }
    by_symbol = {row["symbol"]: row for row in result["rows"]}
    assert by_symbol["000001.SZ"]["change_pct"] == pytest.approx(0.025)
    assert by_symbol["000001.SZ"]["close"] == 12.0
    assert by_symbol["000001.SZ"]["consecutive_limit_ups"] == 2
    assert by_symbol["000001.SZ"]["turnover_rate"] == pytest.approx(150.0)
    assert by_symbol["000001.SZ"]["vol_ratio_5d"] == pytest.approx(1.5)
    assert by_symbol["000001.SZ"]["float_market_cap"] == pytest.approx(120_000.0)
    assert by_symbol["600000.SH"]["change_pct"] == pytest.approx(-0.01)


def test_newer_enriched_partition_does_not_mix_stale_quote_rows(tmp_path) -> None:
    _write_quote(
        tmp_path,
        "2026-08-07",
        [
            {
                "symbol": "600000.SH",
                "close": 9.0,
                "change_pct": 5.0,
                "volume": 100.0,
                "unit_version": "cn_quote_v1",
            }
        ],
    )
    enriched = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "close": 12.5,
                "change_pct": 0.03,
                "amount": 1_000.0,
                "volume": 100.0,
            }
        ]
    )

    result = build_market_snapshot(
        _Repo(tmp_path, _instruments()),
        _Screener(date(2026, 8, 10), enriched),
    )

    assert result["source"] == "enriched"
    assert [row["symbol"] for row in result["rows"]] == ["000001.SZ"]
    assert result["rows"][0]["change_pct"] == pytest.approx(0.03)
