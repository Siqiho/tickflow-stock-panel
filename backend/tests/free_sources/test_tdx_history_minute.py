from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from app.services.free_sources.tdx_history_minute import normalize_history_minute


def test_normalize_tdx_history_minute_keeps_exact_day_and_units():
    trade_date = date(2026, 6, 29)
    start = datetime(2026, 6, 29, 9, 30)
    raw = pd.DataFrame(
        {
            "datetime": [start + timedelta(minutes=i) for i in range(3)],
            "price": [50.92, 50.80, 50.70],
            "vol": [89645, 1200, 800],
        }
    )

    result = normalize_history_minute(raw, "301526.SZ", trade_date)

    assert result.height == 3
    assert result.columns == [
        "symbol", "datetime", "open", "high", "low", "close", "volume", "amount"
    ]
    assert result["symbol"].unique().to_list() == ["301526.SZ"]
    assert result["close"].to_list() == [50.92, 50.8, 50.7]
    assert result["volume"].sum() == 91645.0
    assert result["amount"][0] == 50.92 * 89645 * 100


def test_normalize_tdx_history_minute_drops_another_date():
    raw = pd.DataFrame(
        {
            "datetime": [datetime(2026, 6, 30, 9, 30)],
            "price": [47.82],
            "vol": [100],
        }
    )

    result = normalize_history_minute(raw, "301526.SZ", date(2026, 6, 29))

    assert result.is_empty()
