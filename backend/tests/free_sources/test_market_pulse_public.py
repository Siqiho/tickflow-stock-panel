from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from app.services.free_sources.http_resilience import FetchResult, ResilientHttpClient
from app.services.free_sources.market_pulse_public import (
    MarketPulseQualityError,
    fetch_market_pulse,
    query_market_pulse,
    sync_market_pulse,
)


def _minute_payload(trade_date: date) -> dict:
    encoded = int(trade_date.strftime("%Y%m%d"))
    return {
        "code": 200,
        "data": [
            {
                "date": encoded,
                "minute": 930,
                "last_px": 3943.816,
                "change": 0.001,
                "preclose_px": 3939.966,
                "open_px": 3939.966,
                "business_amount": 494_465_500,
                "business_balance": 11_238_430_879,
            },
            {
                "date": encoded,
                "minute": 931,
                "last_px": 3945.0,
                "change": 0.0013,
                "preclose_px": 3939.966,
                "open_px": 3939.966,
                "business_amount": 12_000_000,
                "business_balance": 500_000_000,
            },
        ],
    }


def _anchor_payload(trade_date: date) -> dict:
    return {
        "errno": 0,
        "data": [
            {
                "symbol_code": "cls80427",
                "symbol_name": "影视",
                "article_id": 2449591,
                "c_time": f"{trade_date.isoformat()} 09:28:51",
                "float": "up",
            },
            {
                "symbol_code": "cls80178",
                "symbol_name": "存储器",
                "article_id": 2449653,
                "c_time": f"{trade_date.isoformat()} 13:08:02",
                "float": "down",
            },
        ],
    }


def _mock_client(monkeypatch, trade_date: date) -> ResilientHttpClient:
    client = ResilientHttpClient()

    def fake_get_json(url, **kwargs):
        if "tline" in url:
            assert kwargs["params"]["date"] == trade_date.strftime("%Y%m%d")
            return FetchResult(ok=True, status_code=200, data=_minute_payload(trade_date))
        assert kwargs["params"]["cdate"] == trade_date.isoformat()
        return FetchResult(ok=True, status_code=200, data=_anchor_payload(trade_date))

    monkeypatch.setattr(client, "get_json", fake_get_json)
    return client


def test_fetch_market_pulse_normalizes_minutes_events_and_units(monkeypatch) -> None:
    trade_date = date.today()
    frame = fetch_market_pulse(trade_date, client=_mock_client(monkeypatch, trade_date))

    assert frame.height == 4
    minute = frame.filter(pl.col("record_type") == "minute").row(0, named=True)
    event = frame.filter(pl.col("record_type") == "sector_event").row(0, named=True)
    assert minute["benchmark_symbol"] == "000001.SH"
    assert minute["amount"] == 11_238_430_879.0
    assert minute["volume"] == 494_465_500
    assert minute["unit_version"] == "market_pulse_v1"
    assert event["sector_name"] == "影视"
    assert event["direction"] == "up"
    assert event["minute"] == 928


def test_fetch_market_pulse_rejects_cross_date_anchor(monkeypatch) -> None:
    trade_date = date.today()
    client = _mock_client(monkeypatch, trade_date)
    wrong = _anchor_payload(trade_date)
    wrong["data"][0]["c_time"] = "2020-01-01 09:30:00"

    def fake_get_json(url, **kwargs):
        if "tline" in url:
            return FetchResult(ok=True, data=_minute_payload(trade_date))
        return FetchResult(ok=True, data=wrong)

    monkeypatch.setattr(client, "get_json", fake_get_json)
    with pytest.raises(MarketPulseQualityError, match="sector event date"):
        fetch_market_pulse(trade_date, client=client)


def test_sync_market_pulse_is_idempotent_and_writes_lineage(tmp_path: Path, monkeypatch) -> None:
    trade_date = date.today()
    client = _mock_client(monkeypatch, trade_date)

    first = sync_market_pulse(trade_date, tmp_path, client=client)
    second = sync_market_pulse(trade_date, tmp_path, client=client)

    assert first.rows_published == 4
    assert second.rows_published == 4
    artifact = tmp_path / "market" / "pulse" / f"date={trade_date.isoformat()}" / "part.parquet"
    stored = pl.read_parquet(artifact)
    assert stored.height == 4
    assert stored.select(pl.struct(["trade_date", "record_type", "event_id"]).n_unique()).item() == 4
    lineage = list((tmp_path / "lineage" / "market_pulse").glob("date=*/*.json"))
    assert len(lineage) == 2

    resolved, queried, updated_at, skipped = query_market_pulse(tmp_path, trade_date)
    assert skipped == []
    assert resolved == trade_date
    assert queried.height == 4
    assert updated_at is not None


def _write_minute_partition(tmp_path: Path, trade_date: date, minute_count: int) -> None:
    from datetime import datetime as _dt

    from app.services.free_sources.market_pulse_public import SCHEMA

    minutes: list[int] = []
    hour, minute = 9, 30
    while len(minutes) < minute_count:
        minutes.append(hour * 100 + minute)
        minute += 1
        if minute == 60:
            hour, minute = hour + 1, 0
        if hour == 11 and minute == 31:
            hour, minute = 13, 0
    rows = [
        {
            "record_type": "minute",
            "event_id": f"minute-{m}",
            "trade_date": trade_date,
            "event_time": _dt(trade_date.year, trade_date.month, trade_date.day, m // 100, m % 100),
            "minute": m,
            "benchmark_symbol": "000001.SH",
            "benchmark_name": "上证指数",
            "last_price": 3900.0,
            "change_ratio": 0.001,
            "preclose": 3890.0,
            "open": 3890.0,
            "volume": 1_000,
            "amount": 1_000_000.0,
            "sector_code": None,
            "sector_name": None,
            "direction": None,
            "article_id": None,
            "source": "cls",
            "unit_version": "market_pulse_v1",
        }
        for m in minutes
    ]
    frame = pl.DataFrame(rows, schema=SCHEMA)
    path = tmp_path / "market" / "pulse" / f"date={trade_date.isoformat()}" / "part.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path)


def test_query_auto_resolve_skips_stale_partial_partition(tmp_path: Path) -> None:
    """盘中同步遗留的部分分区过夜失效后, 自动解析必须跳过并披露, 不得 500。"""
    valid_day = date(2026, 8, 11)
    partial_day = date(2026, 8, 12)
    _write_minute_partition(tmp_path, valid_day, 241)
    _write_minute_partition(tmp_path, partial_day, 199)  # 历史日只有 199 分钟 → 失效

    resolved, frame, updated_at, skipped = query_market_pulse(tmp_path)
    assert resolved == valid_day
    assert frame.height == 241
    assert updated_at is not None
    assert skipped == [partial_day]

    # 显式请求失效日期仍严格抛错(诚实错误, 由前端以文本呈现)
    with pytest.raises(MarketPulseQualityError):
        query_market_pulse(tmp_path, partial_day)


def test_sync_failure_preserves_existing_partition(tmp_path: Path, monkeypatch) -> None:
    trade_date = date.today()
    client = _mock_client(monkeypatch, trade_date)
    sync_market_pulse(trade_date, tmp_path, client=client)
    artifact = tmp_path / "market" / "pulse" / f"date={trade_date.isoformat()}" / "part.parquet"
    before = hashlib.sha256(artifact.read_bytes()).hexdigest()

    monkeypatch.setattr(
        client,
        "get_json",
        lambda *args, **kwargs: FetchResult(ok=False, error="upstream unavailable"),
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        sync_market_pulse(trade_date, tmp_path, client=client)

    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == before
