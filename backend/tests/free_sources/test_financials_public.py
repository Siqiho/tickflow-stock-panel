from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from app.services.free_sources.financials_public import (
    _normalize_statement_rows,
    merge_write_financial_table,
    to_em_report_code,
    to_std_symbol,
)


def test_symbol_helpers():
    assert to_std_symbol("sh600519") == "600519.SH"
    assert to_em_report_code("600519.SH") == "SH600519"
    assert to_em_report_code("000001.SZ") == "SZ000001"


def test_normalize_income_rows():
    raw = [{
        "SECUCODE": "600519.SH",
        "SECURITY_NAME_ABBR": "贵州茅台",
        "REPORT_DATE": "2025-12-31 00:00:00",
        "REPORT_TYPE": "年报",
        "TOTAL_OPERATE_INCOME": 100.0,
        "PARENT_NETPROFIT": 50.0,
        "BASIC_EPS": 1.2,
    }]
    from app.services.free_sources import financials_public as m
    rows = _normalize_statement_rows(raw, symbol="600519.SH", table="income", field_map=m._INCOME_MAP)
    assert len(rows) == 1
    assert rows[0]["period_end"] == date(2025, 12, 31)
    assert rows[0]["total_revenue"] == 100.0
    assert rows[0]["parent_net_profit"] == 50.0


def test_merge_write(tmp_path: Path):
    df1 = pl.DataFrame({
        "symbol": ["600519.SH"],
        "period_end": [date(2025, 12, 31)],
        "total_revenue": [1.0],
        "source": ["eastmoney_hsf10"],
        "table": ["income"],
    })
    n = merge_write_financial_table(df1, tmp_path, "income")
    assert n == 1
    out = tmp_path / "financials" / "income" / "part.parquet"
    assert out.exists()
    df2 = pl.DataFrame({
        "symbol": ["600519.SH"],
        "period_end": [date(2025, 12, 31)],
        "total_revenue": [2.0],
        "source": ["eastmoney_hsf10"],
        "table": ["income"],
    })
    merge_write_financial_table(df2, tmp_path, "income")
    got = pl.read_parquet(out)
    assert got.height == 1
    assert float(got["total_revenue"][0]) == 2.0


def test_sync_resume_and_checkpoint(tmp_path: Path, monkeypatch):
    """Resume skips deep enough symbols; checkpoint flushes mid-run."""
    from app.services.free_sources import financials_public as m

    # Seed local metrics depth for A so resume can skip it.
    seed = pl.DataFrame({
        "symbol": ["000001.SZ"] * 8,
        "period_end": [date(2025, 12, 31) - __import__("datetime").timedelta(days=90 * i) for i in range(8)],
        "roe": [1.0] * 8,
        "source": ["eastmoney_hsf10"] * 8,
        "table": ["metrics"] * 8,
    })
    merge_write_financial_table(seed, tmp_path, "metrics")

    calls: list[str] = []

    def fake_fetch(symbol, tables=("metrics",), max_periods=12, client=None):
        calls.append(symbol)
        pe = date(2026, 3, 31)
        df = pl.DataFrame({
            "symbol": [symbol],
            "period_end": [pe],
            "roe": [2.0],
            "source": ["eastmoney_hsf10"],
            "table": ["metrics"],
        })
        return {"metrics": df}

    monkeypatch.setattr(m, "fetch_financials_symbol", fake_fetch)
    monkeypatch.setattr(m, "sync_shares_snapshot", lambda *a, **k: 0)

    out = m.sync_financials_public(
        ["000001.SZ", "000002.SZ", "600519.SH"],
        tmp_path,
        tables=("metrics",),
        max_periods=12,
        resume=True,
        min_periods=8,
        prefer_fresh_days=None,  # ignore freshness for unit test
        workers=1,
        flush_every=1,
        pause_s=0.0,
    )
    assert out["symbols_skipped_n"] == 1
    assert out["symbols_todo_n"] == 2
    assert set(calls) == {"000002.SZ", "600519.SH"}
    # checkpoint wrote second symbol data
    got = pl.read_parquet(tmp_path / "financials" / "metrics" / "part.parquet")
    assert set(got["symbol"].unique().to_list()) >= {"000001.SZ", "000002.SZ", "600519.SH"}


def test_fetch_metrics_prefers_unfiltered_first(monkeypatch):
    from app.services.free_sources import financials_public as m

    calls: list[str | None] = []

    def fake_chunk(client, *, em_dot, report_type, max_periods):
        calls.append(report_type)
        # Enough unique periods in one unfiltered response.
        rows = []
        for i in range(max_periods):
            rows.append({
                "SECUCODE": em_dot,
                "REPORT_DATE": f"{2025 - i}-12-31 00:00:00",
                "REPORT_TYPE": "年报",
                "ROEJQ": 10.0 + i,
            })
        return rows

    monkeypatch.setattr(m, "_fetch_metrics_chunk", fake_chunk)
    df = m.fetch_metrics("600519.SH", max_periods=4)
    assert calls == [None]
    assert df.height == 4


def test_calendar_freshness():
    from app.services.free_sources.financials_public import _is_fresh_enough, _last_quarter_ends
    ends = _last_quarter_ends(date(2026, 7, 20), n=2)
    assert ends[0] == date(2026, 6, 30)
    assert ends[1] == date(2026, 3, 31)
    # newest at last-1 quarter is still accepted
    assert _is_fresh_enough(date(2026, 3, 31), -1)
    assert not _is_fresh_enough(date(2025, 12, 31), -1)
    assert _is_fresh_enough(date(2026, 6, 30), -1)


def test_financial_sync_retries_transient_symbol_failure(tmp_path: Path, monkeypatch):
    from app.services.free_sources import financials_public as m

    calls = {"n": 0}

    def flaky_fetch(symbol, tables=("metrics",), max_periods=12, client=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("temporary upstream failure")
        return {
            "metrics": pl.DataFrame(
                {
                    "symbol": [symbol],
                    "period_end": [date(2026, 3, 31)],
                    "roe": [8.0],
                    "source": ["eastmoney_hsf10"],
                    "table": ["metrics"],
                }
            )
        }

    monkeypatch.setattr(m, "fetch_financials_symbol", flaky_fetch)
    monkeypatch.setattr(m, "sync_shares_snapshot", lambda *args, **kwargs: 0)

    result = m.sync_financials_public(
        ["600008.SH"],
        tmp_path,
        tables=("metrics",),
        resume=False,
        workers=1,
        max_attempts=2,
        retry_delay_s=0,
    )

    assert calls["n"] == 2
    assert result["symbols_fail"] == []
    assert result["retried_symbols"] == ["600008.SH"]
    assert result["attempts_by_symbol"]["600008.SH"] == 2
