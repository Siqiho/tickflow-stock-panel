from __future__ import annotations

from app.config import settings
from app.services.financial_normalize import (
    local_financials_ready,
    normalize_financial_record,
    normalize_financial_rows,
)


def test_income_aliases():
    row = {
        "symbol": "600519.SH",
        "period_end": "2025-12-31",
        "total_revenue": 100.0,
        "net_profit": 10.0,
        "parent_net_profit": 9.0,
        "operate_profit": 12.0,
        "operate_cost": 50.0,
        "deduct_parent_net_profit": 8.5,
    }
    out = normalize_financial_record("income", row)
    assert out["revenue"] == 100.0
    assert out["net_income"] == 10.0
    assert out["net_income_attributable"] == 9.0
    assert out["operating_profit"] == 12.0
    assert out["operating_cost"] == 50.0
    assert out["net_income_deducted"] == 8.5
    assert out["total_revenue"] == 100.0  # original kept


def test_cash_and_metrics_aliases():
    cash = normalize_financial_record(
        "cash_flow",
        {
            "netcash_operate": 1,
            "netcash_invest": 2,
            "netcash_finance": 3,
            "cce_add": 4,
            "construct_long_asset": 5,
            "period_end": "2025-12-31",
        },
    )
    assert cash["net_operating_cash_flow"] == 1
    assert cash["capex"] == 5
    m = normalize_financial_record(
        "metrics",
        {
            "basic_eps": 1.2,
            "asset_liab_ratio": 33.0,
            "total_revenue_yoy": 10.0,
            "parent_net_profit_yoy": 8.0,
            "period_end": "2025-12-31",
        },
    )
    assert m["eps_basic"] == 1.2
    assert m["debt_to_asset_ratio"] == 33.0
    assert m["revenue_yoy"] == 10.0
    assert m["net_income_yoy"] == 8.0


def test_local_ready_and_rows():
    assert local_financials_ready(settings.data_dir) is True
    rows = normalize_financial_rows(
        "balance_sheet",
        [{"monetary_funds": 9.0, "total_assets": 100.0, "period_end": "2025-12-31"}],
    )
    assert rows[0]["cash_and_equivalents"] == 9.0
