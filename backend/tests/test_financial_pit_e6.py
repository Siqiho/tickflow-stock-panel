"""E6 point-in-time financial_pit 模块测试(移植自 7019d03 并按主树边界裁剪)。

只测试移植的 app.services.financial_pit 纯模块行为。分支上把
financials_public.merge_write_financial_table / financial_sync.get_financial_df
改造为 PIT 写读路径, 以及 financial_* 目录契约升级到 financial_cn_v2,
均属于未来财务 PIT 迁移工作包, 不在本文件断言。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import polars as pl

from app.services.financial_pit import (
    append_shares_history,
    ensure_pit_columns,
    filter_as_of,
    latest_as_of_per_symbol,
    merge_financial_pit,
    migrate_existing_financials_to_pit,
    staging_atomic_replace_financial_table,
)


def _stmt_row(symbol: str, period_end: date, announce: date, revenue: float, source: str = "t") -> dict:
    return {
        "symbol": symbol,
        "period_end": period_end,
        "notice_date": announce,
        "revenue": revenue,
        "source": source,
        "table": "income",
    }


def test_ensure_pit_and_restatement_ids_differ_on_revision() -> None:
    r1 = pl.DataFrame(
        [_stmt_row("600000.SH", date(2024, 12, 31), date(2025, 3, 1), 100.0)]
    )
    r2 = pl.DataFrame(
        [_stmt_row("600000.SH", date(2024, 12, 31), date(2025, 4, 15), 110.0)]  # restatement
    )
    a = ensure_pit_columns(r1, table="income")
    b = ensure_pit_columns(r2, table="income")
    assert "restatement_id" in a.columns
    assert a["restatement_id"][0] != b["restatement_id"][0]
    assert a["report_date"][0] == date(2024, 12, 31)
    assert a["announce_date"][0] == date(2025, 3, 1)
    assert a["period_type"][0] == "annual"


def test_merge_financial_pit_retains_restatements() -> None:
    first = pl.DataFrame(
        [_stmt_row("600000.SH", date(2024, 12, 31), date(2025, 3, 1), 100.0)]
    )
    second = pl.DataFrame(
        [_stmt_row("600000.SH", date(2024, 12, 31), date(2025, 4, 15), 110.0)]
    )
    merged = merge_financial_pit(first, second, table="income")
    assert merged.height == 2  # both restatements kept
    assert set(merged.get_column("announce_date").to_list()) == {
        date(2025, 3, 1),
        date(2025, 4, 15),
    }
    # 同一 restatement 再并一次不重复
    again = merge_financial_pit(merged, second, table="income")
    assert again.height == 2


def test_as_of_filter_hides_future_announcements() -> None:
    df = pl.DataFrame(
        [
            _stmt_row("600000.SH", date(2023, 12, 31), date(2024, 3, 1), 90.0),
            _stmt_row("600000.SH", date(2024, 12, 31), date(2025, 3, 1), 100.0),
            _stmt_row("600000.SH", date(2024, 12, 31), date(2025, 4, 15), 110.0),
        ]
    )
    # as_of before second restatement → first version of 2024 annual only
    pit = filter_as_of(df, date(2025, 3, 10), table="income")
    assert pit.height == 2  # 2023 + first 2024 version
    ann = set(pit.get_column("announce_date").to_list())
    assert date(2025, 4, 15) not in ann
    assert date(2025, 3, 1) in ann
    latest = latest_as_of_per_symbol(df, date(2025, 3, 10), table="income")
    assert latest.height == 1
    assert float(latest["revenue"][0]) == 100.0
    # after restatement
    latest2 = latest_as_of_per_symbol(df, date(2025, 5, 1), table="income")
    assert float(latest2["revenue"][0]) == 110.0


def test_shares_history_append_not_overwrite(tmp_path: Path) -> None:
    data = tmp_path / "data"
    day1 = pl.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "period_end": date(2026, 7, 1),
                "announce_date": date(2026, 7, 1),
                "total_shares": 1e9,
                "float_shares": 8e8,
                "source": "exchange_share_capital",
                "table": "shares",
            }
        ]
    )
    merged = append_shares_history(data, day1, effective_date=date(2026, 7, 1))
    staging_atomic_replace_financial_table(data, "shares", merged)
    day2 = pl.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "period_end": date(2026, 7, 22),
                "announce_date": date(2026, 7, 22),
                "total_shares": 1.1e9,
                "float_shares": 9e8,
                "source": "exchange_share_capital",
                "table": "shares",
            }
        ]
    )
    merged2 = append_shares_history(data, day2, effective_date=date(2026, 7, 22))
    staging_atomic_replace_financial_table(data, "shares", merged2)
    got = pl.read_parquet(data / "financials" / "shares" / "part.parquet")
    assert got.height == 2
    # as_of mid: 只能看到第一条股本
    pit = latest_as_of_per_symbol(got, date(2026, 7, 10), table="shares")
    assert pit.height == 1
    assert float(pit["total_shares"][0]) == 1e9


def test_migrate_existing(tmp_path: Path) -> None:
    data = tmp_path / "data"
    # legacy-like rows
    legacy = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "period_end": date(2024, 6, 30),
                "notice_date": date(2024, 8, 1),
                "net_profit": 1.0,
                "source": "eastmoney_hsf10",
                "table": "income",
            }
        ]
    )
    path = data / "financials" / "income" / "part.parquet"
    path.parent.mkdir(parents=True)
    legacy.write_parquet(path)
    report = migrate_existing_financials_to_pit(data, tables=["income"])
    assert report["ok"] is True
    got = pl.read_parquet(path)
    assert "restatement_id" in got.columns
    assert "report_date" in got.columns
    assert got["announce_date"][0] == date(2024, 8, 1)
    lineage_files = list((data / "lineage" / "financial_income").rglob("*.json"))
    assert len(lineage_files) == 1
    lineage = json.loads(lineage_files[0].read_text(encoding="utf-8"))
    assert lineage["source"] == "eastmoney_hsf10"
    assert lineage["unit_version"] == "financial_cn_v2"
    assert lineage["target_artifact"] == "financials/income/part.parquet"
    # 注: 主树 financial_income 目录契约仍为 financial_cn_v1, 真正执行该迁移
    # 需连同目录契约升级一起进入独立财务 PIT 工作包; 本测试不做 scanner 断言。
