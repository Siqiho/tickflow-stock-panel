from __future__ import annotations

from pathlib import Path

import polars as pl

from app.config import settings
from app.services.financial_normalize import normalize_financial_record
from app.services.free_sources.financials_public import (
    FINANCIAL_TABLES,
    build_shares_from_instruments,
    sync_shares_snapshot,
)
from app.services import preferences


def test_financial_tables_include_shares():
    assert "shares" in FINANCIAL_TABLES


def test_shares_snapshot_from_instruments():
    d = Path(settings.data_dir)
    df = build_shares_from_instruments(d, symbols=["600519.SH", "000001.SZ"])
    assert df.height >= 1
    assert {"symbol", "period_end", "total_shares", "float_shares"}.issubset(set(df.columns))
    n = sync_shares_snapshot(d, symbols=["600519.SH"])
    assert n >= 1
    got = pl.read_parquet(d / "financials" / "shares" / "part.parquet")
    assert "600519.SH" in got["symbol"].to_list()


def test_expense_and_balance_aliases():
    income = normalize_financial_record(
        "income",
        {
            "selling_expense": 1.0,
            "admin_expense": 2.0,
            "rd_expense": 3.0,
            "financial_expense": -4.0,
            "non_operating_income": 5.0,
            "total_revenue": 100.0,
            "period_end": "2025-12-31",
        },
    )
    assert income["selling_expense"] == 1.0
    assert income["revenue"] == 100.0
    bal = normalize_financial_record(
        "balance_sheet",
        {
            "retained_earnings": 9.0,
            "intangible_assets": 8.0,
            "monetary_funds": 7.0,
            "period_end": "2025-12-31",
        },
    )
    assert bal["retained_earnings"] == 9.0
    assert bal["cash_and_equivalents"] == 7.0


def test_max_periods_pref_bounds():
    old = preferences.get_financial_max_periods()
    assert preferences.set_financial_max_periods(3) == 4  # min clamp
    assert preferences.set_financial_max_periods(100) == 40  # max clamp
    assert preferences.set_financial_max_periods(12) == 12
    preferences.set_financial_max_periods(old)


def test_repository_registers_financials_shares_sql():
    """Source-level guard: DuckDB bootstrap includes financials_shares view."""
    src = Path(__file__).resolve().parents[1] / "app" / "tickflow" / "repository.py"
    text = src.read_text(encoding="utf-8")
    assert "financials_shares" in text
    assert "financials/shares/*.parquet" in text


def test_backfill_script_is_incremental():
    src = Path(__file__).resolve().parents[1] / "scripts" / "backfill_financial_expenses.py"
    text = src.read_text(encoding="utf-8")
    assert "flush-every" in text
    assert "_flush" in text


def test_statement_fetch_chunks_dates():
    from app.services.free_sources import financials_public as fp
    assert getattr(fp, "_EM_STATEMENT_DATE_CHUNK", 0) == 5
    src = Path(fp.__file__).read_text(encoding="utf-8")
    assert "range(0, len(dates), chunk_size)" in src


def test_financial_status_exposes_period_depth_code():
    src = Path(__file__).resolve().parents[1] / "app" / "api" / "financials.py"
    text = src.read_text(encoding="utf-8")
    assert "period_depth" in text
    assert "periods_median" in text


def test_pipeline_has_public_financial_stage():
    src = Path(__file__).resolve().parents[1] / "app" / "jobs" / "daily_pipeline.py"
    text = src.read_text(encoding="utf-8")
    assert "sync_financials" in text
    assert "is_public_financial_provider" in text
