"""Normalize local/public financial rows to TickFlow-compatible field names.

Local free source (East Money) uses different column names than TickFlow SDK
generated_model. Frontend StockFinancialDetail / StockInfoBar expect TickFlow
canonical names. We keep original keys and add aliases so both work.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

# local_or_public_name -> TickFlow canonical name
# Only add when names differ; exact matches need no alias.
_ALIASES: dict[str, dict[str, str]] = {
    "income": {
        "total_revenue": "revenue",
        "operate_revenue": "operating_revenue",  # extra; TF uses revenue
        "operate_cost": "operating_cost",
        "operate_profit": "operating_profit",
        "net_profit": "net_income",
        "parent_net_profit": "net_income_attributable",
        "deduct_parent_net_profit": "net_income_deducted",
        "notice_date": "announce_date",
        # expense lines if later mapped from EM
        "admin_expense": "admin_expense",
        "selling_expense": "selling_expense",
        "rd_expense": "rd_expense",
        "financial_expense": "financial_expense",
        "non_operating_income": "non_operating_income",
        "non_operating_expense": "non_operating_expense",
    },
    "balance_sheet": {
        "monetary_funds": "cash_and_equivalents",
        "total_parent_equity": "equity_attributable",
        "short_loan": "short_term_borrowing",
        "long_loan": "long_term_borrowing",
        "total_current_liab": "total_current_liabilities",
        "total_noncurrent_liab": "total_non_current_liabilities",
        "total_noncurrent_assets": "total_non_current_assets",
        "fixed_assets": "fixed_assets",
        "notice_date": "announce_date",
        "goodwill": "goodwill",
        "intangible_assets": "intangible_assets",
        "retained_earnings": "retained_earnings",
        "minority_interest": "minority_interest",
        "share_capital": "share_capital",
        "capital_reserve": "capital_reserve",
        "surplus_reserve": "surplus_reserve",
    },
    "cash_flow": {
        "netcash_operate": "net_operating_cash_flow",
        "netcash_invest": "net_investing_cash_flow",
        "netcash_finance": "net_financing_cash_flow",
        "cce_add": "net_cash_change",
        "construct_long_asset": "capex",
        "notice_date": "announce_date",
    },
    "shares": {
        # already TickFlow names when built from instruments snapshot
        "notice_date": "announce_date",
    },
    "metrics": {
        "basic_eps": "eps_basic",
        "diluted_eps": "eps_diluted",
        "asset_liab_ratio": "debt_to_asset_ratio",
        "total_revenue_yoy": "revenue_yoy",
        "parent_net_profit_yoy": "net_income_yoy",
        "oper_cf_ps": "ocfps",
        "oper_cf_to_rev": "operating_cash_to_revenue",
        "inv_turn_rate": "inventory_turnover",
        "roe_non_gaap": "roe_diluted",
        "notice_date": "announce_date",
    },
}


def _jsonable(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def normalize_financial_record(table: str, row: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with TickFlow aliases filled (without removing originals)."""
    out = {k: _jsonable(v) for k, v in row.items()}
    aliases = _ALIASES.get(table) or {}
    for src, dst in aliases.items():
        if src in out and out[src] is not None and (dst not in out or out[dst] is None):
            out[dst] = out[src]
    # period_end always string for frontend localeCompare
    if "period_end" in out and out["period_end"] is not None:
        out["period_end"] = str(out["period_end"])[:10]
    return out


def normalize_financial_rows(table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_financial_record(table, r) for r in rows]


def local_financials_ready(data_dir) -> bool:
    """True if a route-usable financial table has at least one row."""
    from pathlib import Path

    from app.services.financial_sync import get_financial_df

    base = Path(data_dir)
    for table in ("metrics", "income", "balance_sheet", "cash_flow"):
        try:
            df = get_financial_df(base, table)
            if df is not None and getattr(df, "height", 0) > 0:
                return True
        except Exception:
            continue
    return False


def local_adj_factor_ready(data_dir) -> bool:
    from pathlib import Path

    from app.services.kline_sync import get_adj_factor_df

    try:
        df = get_adj_factor_df(Path(data_dir), asset_type="stock")
        return df is not None and getattr(df, "height", 0) > 0
    except Exception:
        return False
