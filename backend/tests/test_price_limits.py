"""app.price_limits 规则测试(移植自 7019d03, 裁剪为纯规则断言)。

分支上的回测矩阵/分钟接口/管道集成断言依赖未移植的模块, 不在本文件范围。
"""

from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl
import pytest

from app.price_limits import (
    numpy_limit_price,
    numpy_price_limit_matrix,
    polars_is_risk_warning_name,
    polars_limit_price,
    polars_price_limit_pct,
    price_limit_pct,
)


@pytest.mark.parametrize(
    ("symbol", "trade_date", "is_st", "expected"),
    [
        ("600001.SH", date(2026, 7, 3), True, 0.05),
        ("600001.SH", date(2026, 7, 6), True, 0.10),
        ("000001.SZ", date(2026, 7, 3), False, 0.10),
        ("300001.SZ", date(2026, 7, 3), True, 0.20),
        ("688001.SH", date(2026, 7, 3), True, 0.20),
        ("689001.SH", date(2026, 7, 3), True, 0.20),
        ("830001.BJ", date(2026, 7, 3), True, 0.30),
    ],
)
def test_scalar_price_limit_rules(symbol, trade_date, is_st, expected):
    assert price_limit_pct(
        symbol,
        trade_date,
        is_risk_warning=is_st,
    ) == pytest.approx(expected)


def test_polars_and_numpy_price_limit_rules_match():
    dates = [date(2026, 7, 3), date(2026, 7, 6)]
    symbols = ["600001.SH", "300001.SZ", "689001.SH", "830001.BJ"]
    names = ["*st主板", "*ST创业", "科创ST", "北交ST"]
    panel = pl.DataFrame({
        "date": [value for value in dates for _ in symbols],
        "symbol": symbols * len(dates),
        "name": names * len(dates),
    }).with_columns(
        polars_is_risk_warning_name(pl.col("name")).alias("is_st")
    ).with_columns(
        polars_price_limit_pct(
            pl.col("symbol"), pl.col("date"), pl.col("is_st"),
        ).alias("limit_pct")
    )
    polars_values = panel["limit_pct"].to_numpy().reshape(len(dates), len(symbols))
    numpy_values = numpy_price_limit_matrix(dates, symbols, names)
    np.testing.assert_allclose(polars_values, numpy_values)


def test_polars_and_numpy_limit_prices_use_identical_half_up_rounding():
    previous = np.array([18.90, 10.00], dtype=np.float64)
    limits = np.array([0.05, 0.10], dtype=np.float64)
    frame = pl.DataFrame({"previous": previous, "limit": limits})

    for up in (True, False):
        polars_values = frame.select(
            polars_limit_price(
                pl.col("previous"), pl.col("limit"), up=up,
            ).alias("price")
        )["price"].to_numpy()
        numpy_values = numpy_limit_price(previous, limits, up=up)
        np.testing.assert_allclose(polars_values, numpy_values)
    assert numpy_limit_price(previous, limits, up=False)[0] == pytest.approx(17.96)
