"""#294: board 领涨 must treat 0.00% as a real print, not a missing value."""
from __future__ import annotations

from app.services.market_overview_builder import _leader_sort_key


def test_flat_print_ranks_above_missing_and_below_gain():
    down = {"symbol": "DOWN", "change_pct": -1.5}
    flat = {"symbol": "FLAT", "change_pct": 0.0}
    missing = {"symbol": "NA", "change_pct": None}
    up = {"symbol": "UP", "change_pct": 2.0}

    leader = max([down, flat, missing], key=_leader_sort_key)
    assert leader["symbol"] == "FLAT"

    leader = max([down, flat, up], key=_leader_sort_key)
    assert leader["symbol"] == "UP"


def test_all_flat_board_keeps_a_zero_leader():
    stocks = [
        {"symbol": "A", "change_pct": 0.0},
        {"symbol": "B", "change_pct": 0.00},
    ]
    leader = max(stocks, key=_leader_sort_key)
    assert leader["change_pct"] == 0.0
    assert _leader_sort_key(leader) == 0.0
