from __future__ import annotations

import pytest

from app.services.free_sources.chip_distribution import calculate_chip_distribution


def test_chip_distribution_basic_shape():
    bars = [
        {"open": 10, "high": 11, "low": 9.5, "close": 10.5, "volume": 1000, "amount": 10500, "turnover_rate": 2.0},
        {"open": 10.5, "high": 12, "low": 10.2, "close": 11.5, "volume": 1200, "amount": 13500, "turnover_rate": 3.0},
        {"open": 11.5, "high": 11.8, "low": 11.0, "close": 11.2, "volume": 800, "amount": 9000, "turnover_rate": 1.5},
    ]
    result = calculate_chip_distribution("000001.SZ", bars, bins=40)
    assert result["symbol"] == "000001.SZ"
    assert result["bins"] == 40
    assert result["days"] == 3
    assert abs(sum(i["ratio"] for i in result["items"]) - 1.0) < 1e-6
    assert 0.0 <= result["profit_ratio"] <= 1.0
    assert result["cost70"]["low_price"] <= result["cost70"]["high_price"]
    assert result["avg_cost"] > 0
    assert result["method"] == "approx_turnover_decay_vwap_kernel"
    assert "disclaimer" in result


def test_chip_distribution_empty_raises():
    with pytest.raises(ValueError):
        calculate_chip_distribution("x", [], bins=10)
