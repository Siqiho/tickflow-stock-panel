from datetime import date

from app.services.intraday_overview import (
    board_limit_pct,
    classify_intraday_limit,
    load_official_trend_overlay,
    theoretical_limit_price,
)


def test_theoretical_limit_price_matches_exchange_rounding() -> None:
    assert theoretical_limit_price(11.59, 0.10, up=True) == 12.75
    assert theoretical_limit_price(11.59, 0.10, up=False) == 10.43
    assert theoretical_limit_price(1.53, 0.05, up=True) == 1.61


def test_board_limit_pct_uses_name_st_and_board_prefix() -> None:
    assert board_limit_pct("000001.SZ", "平安银行") == 0.10
    assert board_limit_pct("000010.SZ", "*ST美丽") == 0.05
    assert board_limit_pct("300001.SZ", "特锐德") == 0.20
    assert board_limit_pct("688001.SH", "华兴源创") == 0.20
    assert board_limit_pct("830799.BJ", "艾融软件") == 0.30


def test_classify_broken_board_is_high_touch_without_close_seal() -> None:
    flags = classify_intraday_limit(
        symbol="300001.SZ",
        name="特锐德",
        close=11.90,
        high=12.00,
        prev_close=10.0,
    )
    assert flags["limit_up_price"] == 12.00
    assert flags["signal_limit_up"] is False
    assert flags["signal_broken_limit_up"] is True


def test_official_trend_overlay_ma5_uses_sorted_history(tmp_path) -> None:
    from tests.test_market_overview_as_of import _official_row, _write_official

    for offset, close in enumerate((10.0, 10.2, 10.4, 10.6, 10.8), start=13):
        day = f"2026-08-{offset}"
        _write_official(tmp_path, day, [{**_official_row(day), "close": close, "raw_close": close}])

    overlay = load_official_trend_overlay(tmp_path, date(2026, 8, 17))
    assert overlay["000001.SZ"]["ma5"] == 10.4
