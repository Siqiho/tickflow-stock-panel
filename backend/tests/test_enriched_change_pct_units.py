"""enriched 今日帧涨跌幅单位: 报价百分点 → 小数契约。"""

from __future__ import annotations

from datetime import date

import polars as pl

from app.indicators.pipeline import compute_enriched_today


def _live_state() -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": ["600001.SH"],
        "ema5": [10.0],
        "ema10": [10.0],
        "ema20": [10.0],
        "ema30": [10.0],
        "ema60": [10.0],
        "macd_dea": [0.0],
        "kdj_k": [50.0],
        "kdj_d": [50.0],
        "atr_14": [0.2],
        "close": [17.28],
        "high": [17.5],
        "low": [17.0],
        "annual_vol_20d": [0.1],
        "_ema12": [10.0],
        "_ema26": [10.0],
        "_adj_factor": [1.0],
        "_vol_19d_pct_sum": [0.0],
        "_vol_19d_pct_sq_sum": [0.0],
        "_prev_consec_up": pl.Series([0], dtype=pl.UInt32),
        "_prev_consec_down": pl.Series([0], dtype=pl.UInt32),
        "_ma5_partial_sum": [40.0],
        "_ma10_partial_sum": [90.0],
        "_ma20_partial_sum": [190.0],
        "_ma30_partial_sum": [290.0],
        "_ma60_partial_sum": [590.0],
        "_boll_partial_sum": [190.0],
        "_boll_partial_sq_sum": [1900.0],
        "_high_59d": [17.5],
        "_low_59d": [17.0],
        "_close_5d_ago": [17.0],
        "_close_10d_ago": [16.5],
        "_close_20d_ago": [16.0],
        "_close_30d_ago": [15.5],
        "_close_60d_ago": [15.0],
        "_vol_ma5_partial_sum": [4000.0],
        "_vol_ma10_partial_sum": [9000.0],
        "_vol_ma5_prev_sum": [5000.0],
        "_kdj_8d_low": [17.0],
        "_kdj_8d_high": [17.5],
        "_window_len": [59],
        "_rsi_avg_gain_6": [0.01],
        "_rsi_avg_loss_6": [0.01],
        "_rsi_avg_gain_14": [0.01],
        "_rsi_avg_loss_14": [0.01],
        "_rsi_avg_gain_24": [0.01],
        "_rsi_avg_loss_24": [0.01],
    })


def test_compute_enriched_today_converts_quote_percent_change_pct():
    today = date(2026, 7, 30)
    today_rows = pl.DataFrame({
        "symbol": ["600001.SH"],
        "date": [today],
        "open": [17.28],
        "high": [20.74],
        "low": [17.28],
        "close": [20.74],
        "volume": [1200.0],
        "amount": [24888.0],
        "prev_close": [17.28],
        "change_pct": [20.023148],
        "amplitude": [20.023148],
    })
    instruments = pl.DataFrame({
        "symbol": ["600001.SH"],
        "name": ["报价百分点"],
        "float_shares": [1_000_000.0],
        "limit_up": [20.74],
        "limit_down": [15.55],
        "as_of": [today],
    })
    result = compute_enriched_today(
        _live_state(),
        pl.DataFrame({
            "symbol": ["600001.SH"],
            "close": [17.28],
            "ma5": [17.0],
            "ma20": [16.8],
            "ma60": [16.0],
            "macd_dif": [0.0],
            "macd_dea": [0.0],
            "boll_upper": [18.0],
            "boll_lower": [16.0],
        }),
        today_rows,
        instruments,
    )
    row = result.row(0, named=True)
    assert abs(row["change_pct"] - 0.20023148) < 1e-6
    assert abs(row["amplitude"] - 0.20023148) < 1e-6
