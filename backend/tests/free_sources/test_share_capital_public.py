"""东财 F10 股本结构 Adapter 与 PIT 升级测试。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from app.services.financial_pit import filter_as_of
from app.services.free_sources.http_resilience import FetchResult, ResilientHttpClient
from app.services.free_sources.share_capital_public import (
    SHARE_CAPITAL_SOURCE,
    normalize_share_capital,
    sync_share_capital_public,
)
from app.services.reference_derived import build_valuation_daily


def _upstream_row(
    end_date: str,
    notice_date: str | None,
    total: float,
    listed_a: float | None,
) -> dict:
    return {
        "SECUCODE": "600000.SH",
        "SECURITY_NAME_ABBR": "浦发银行",
        "END_DATE": end_date,
        "NOTICE_DATE": notice_date,
        "TOTAL_SHARES": total,
        "LISTED_A_SHARES": listed_a,
        "LIMITED_SHARES": 0,
        "CHANGE_REASON": "债转股上市",
    }


def _payload(rows: list[dict]) -> dict:
    return {
        "success": True,
        "result": {"pages": 1, "count": len(rows), "data": rows},
    }


def test_normalize_keeps_real_announce_and_drops_broken_rows() -> None:
    rows = [
        _upstream_row("2025-10-27 00:00:00", "2025-10-29 00:00:00", 100.0, 90.0),
        # 无公告日的行保留(后续标 pit_unsafe)
        _upstream_row("2020-01-01 00:00:00", None, 80.0, 70.0),
        # 无变动日/无总股本的行丢弃
        {"END_DATE": None, "NOTICE_DATE": "2020-01-01", "TOTAL_SHARES": 1.0},
        {"END_DATE": "2021-01-01", "NOTICE_DATE": "2021-01-02", "TOTAL_SHARES": None},
    ]
    frame = normalize_share_capital("600000.sh", rows)
    assert frame.height == 2
    assert set(frame.get_column("symbol").to_list()) == {"600000.SH"}
    newest = frame.filter(pl.col("effective_date") == date(2025, 10, 27))
    assert newest["announce_date"][0] == date(2025, 10, 29)
    assert float(newest["total_shares"][0]) == 100.0
    assert float(newest["float_shares"][0]) == 90.0
    assert set(frame.get_column("source").to_list()) == {SHARE_CAPITAL_SOURCE}


def _fake_client(monkeypatch, payload_by_symbol: dict[str, dict]) -> ResilientHttpClient:
    client = ResilientHttpClient()

    def fake_get_json(url, **kwargs):
        for symbol, payload in payload_by_symbol.items():
            if symbol.replace(".", "%3D") in url or symbol in url:
                return FetchResult(ok=True, status_code=200, data=payload)
        return FetchResult(ok=False, status_code=502, data=None, error="not found")

    monkeypatch.setattr(client, "get_json", fake_get_json)
    return client


def test_sync_share_capital_makes_valuation_mv_derivable(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    # 既有 instruments_snapshot 行(pit_unsafe)
    shares_path = data / "financials" / "shares" / "part.parquet"
    shares_path.parent.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["600000.SH"],
            "period_end": [date(2026, 7, 17)],
            "announce_date": [date(2026, 7, 17)],
            "effective_date": [date(2026, 7, 17)],
            "total_shares": [999.0],
            "float_shares": [999.0],
            "source": ["instruments_snapshot"],
            "table": ["shares"],
        }
    ).write_parquet(shares_path)

    client = _fake_client(
        monkeypatch,
        {
            "600000.SH": _payload(
                [_upstream_row("2026-06-30 00:00:00", "2026-07-02 00:00:00", 1000.0, 800.0)]
            )
        },
    )
    stats = sync_share_capital_public(["600000.SH"], data, client=client, sleep_s=0)
    assert stats["published"] is True
    assert stats["ok"] == 1
    assert stats["pit_safe_rows_after"] == 1

    merged = pl.read_parquet(shares_path)
    # snapshot 行保留, 权威行加入
    assert set(merged.get_column("source").to_list()) == {
        "instruments_snapshot",
        SHARE_CAPITAL_SOURCE,
    }
    # 严格 PIT: 只有权威行可见
    pit = filter_as_of(merged, date(2026, 7, 21), table="shares", strict=True)
    assert pit.height == 1
    assert pit["source"][0] == SHARE_CAPITAL_SOURCE
    assert float(pit["total_shares"][0]) == 1000.0

    # 估值市值随之可派生
    day = date(2026, 7, 21)
    daily = data / "kline_daily" / f"date={day.isoformat()}" / "part.parquet"
    daily.parent.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["600000.SH"],
            "date": [day],
            "open": [10.0],
            "high": [10.0],
            "low": [10.0],
            "close": [10.0],
            "raw_close": [10.0],
            "volume": [1.0],
            "amount": [1.0],
        }
    ).write_parquet(daily)
    val = build_valuation_daily(data, day)
    assert bool(val["shares_pit_safe"][0]) is True
    assert float(val["total_mv"][0]) == 10.0 * 1000.0
    assert float(val["float_mv"][0]) == 10.0 * 800.0

    # 幂等: 同数据二跑行数不变
    stats2 = sync_share_capital_public(["600000.SH"], data, client=client, sleep_s=0)
    assert stats2["rows_after"] == stats["rows_after"]


def test_sync_share_capital_partial_failure_keeps_going(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    client = _fake_client(
        monkeypatch,
        {
            "600000.SH": _payload(
                [_upstream_row("2026-06-30 00:00:00", "2026-07-02 00:00:00", 1000.0, 800.0)]
            )
        },
    )
    stats = sync_share_capital_public(
        ["600000.SH", "000001.SZ"], data, client=client, sleep_s=0
    )
    assert stats["published"] is True
    assert stats["ok"] == 1
    assert stats["failed"] == 1
    assert stats["failed_symbols"] == ["000001.SZ"]
    merged = pl.read_parquet(data / "financials" / "shares" / "part.parquet")
    assert set(merged.get_column("symbol").to_list()) == {"600000.SH"}
