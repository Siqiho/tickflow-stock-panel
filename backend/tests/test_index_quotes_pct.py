from __future__ import annotations

from app.services.quote_service import QuoteService


def test_build_index_quotes_public_already_percent():
    """Public path change_pct is already percentage points; do not *100 again."""
    df = QuoteService._build_index_quotes([
        {
            "symbol": "000001.SH",
            "name": "上证指数",
            "last_price": 3808.39,
            "prev_close": 3764.15,
            "open": 3791.66,
            "high": 3831.66,
            "low": 3780.02,
            "change_pct": 1.175,  # already percent from tencent path
            "change_amount": 44.24,
        }
    ])
    assert df.height == 1
    pct = float(df["change_pct"][0])
    assert 1.0 < pct < 2.0, pct
    assert abs(pct - (3808.39 - 3764.15) / 3764.15 * 100) < 1e-6


def test_build_index_quotes_fraction_without_prices():
    df = QuoteService._build_index_quotes([
        {"symbol": "000001.SH", "change_pct": 0.0123}
    ])
    assert abs(float(df["change_pct"][0]) - 1.23) < 1e-9


def test_as_percent_change_prefers_prices():
    # Even if upstream wrongly sends *100-ed percent, prices win.
    got = QuoteService._as_percent_change(117.5, last=3808.39, prev=3764.15)
    assert 1.0 < float(got) < 2.0
