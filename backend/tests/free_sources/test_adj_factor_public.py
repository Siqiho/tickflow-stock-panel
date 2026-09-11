from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from app.services.free_sources.adj_factor_public import (
    cumulative_to_event_ex_factors,
    fetch_adj_factors_symbol,
    merge_write_adj_factor,
    parse_sina_qfq_text,
    to_sina_code,
)
from app.services.free_sources.http_resilience import FetchResult, ResilientHttpClient

SAMPLE_QFQ = (
    'var sz000001qfq={"total":4,"data":['
    '{"d":"2026-06-12", "f":"1.0000000000000000"},'
    '{"d":"2025-10-15", "f":"1.0329067641682000"},'
    '{"d":"2025-06-12", "f":"1.0544142634044000"},'
    '{"d":"1900-01-01", "f":"150.0"}'
    "]};\n"
)


def test_to_sina_code():
    assert to_sina_code("000001.SZ") == "sz000001"
    assert to_sina_code("600000.SH") == "sh600000"
    assert to_sina_code("sh600519") == "sh600519"


def test_parse_and_convert_event_factors():
    cum = parse_sina_qfq_text(SAMPLE_QFQ)
    assert cum[0][0] == date(2025, 6, 12)
    assert cum[-1][0] == date(2026, 6, 12)
    assert abs(cum[-1][1] - 1.0) < 1e-12
    # sentinel dropped
    assert all(d.year != 1900 for d, _ in cum)

    events = cumulative_to_event_ex_factors(cum)
    assert len(events) == 2
    # last event ex = prev_C / 1.0
    assert events[-1][0] == date(2026, 6, 12)
    assert abs(events[-1][1] - 1.0329067641682) < 1e-9
    # product equals oldest C
    prod = 1.0
    for _, ex in events:
        prod *= ex
    assert abs(prod - cum[0][1]) < 1e-9


def test_fetch_symbol_with_mock_client(monkeypatch):
    client = ResilientHttpClient()

    def fake_get_text(url, **kwargs):
        assert "sz000001" in url
        return FetchResult(ok=True, text=SAMPLE_QFQ, status_code=200)

    monkeypatch.setattr(client, "get_text", fake_get_text)
    df = fetch_adj_factors_symbol("000001.SZ", client=client)
    assert not df.is_empty()
    assert set(df.columns) == {"symbol", "trade_date", "ex_factor"}
    assert df["symbol"].unique().to_list() == ["000001.SZ"]
    assert df.height == 2


def test_merge_write(tmp_path: Path, monkeypatch):
    from app.services import kline_sync

    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "public")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: True)
    df1 = pl.DataFrame(
        {
            "symbol": ["000001.SZ", "000001.SZ"],
            "trade_date": [date(2024, 1, 1), date(2025, 1, 1)],
            "ex_factor": [1.1, 1.2],
        }
    )
    added, affected = merge_write_adj_factor(df1, tmp_path)
    assert added == 2
    assert affected == ["000001.SZ"]
    out = tmp_path / "adj_factor" / "all.parquet"
    assert out.exists()

    df2 = pl.DataFrame(
        {
            "symbol": ["000001.SZ"],
            "trade_date": [date(2025, 1, 1)],
            "ex_factor": [1.25],
        }
    )
    delta, _ = merge_write_adj_factor(df2, tmp_path)
    merged = pl.read_parquet(out).sort("trade_date")
    assert merged.height == 2
    assert abs(merged.filter(pl.col("trade_date") == date(2025, 1, 1))["ex_factor"][0] - 1.25) < 1e-9
    assert delta == 0  # same key replaced, height unchanged


def test_pipeline_formula_matches_cumulative():
    """Event ex product path must reproduce raw/C for oldest bar."""
    import sys
    from datetime import timedelta

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.indicators.pipeline import _apply_adj_factor

    cum = parse_sina_qfq_text(SAMPLE_QFQ)
    events = cumulative_to_event_ex_factors(cum)
    factors = pl.DataFrame(
        {
            "symbol": ["000001.SZ"] * len(events),
            "trade_date": [d for d, _ in events],
            "ex_factor": [ex for _, ex in events],
        }
    )
    oldest = cum[0][0]
    latest = cum[-1][0]
    raw = pl.DataFrame(
        {
            "symbol": ["000001.SZ", "000001.SZ"],
            "date": [oldest - timedelta(days=1), latest + timedelta(days=1)],
            "open": [10.0, 10.0],
            "high": [10.0, 10.0],
            "low": [10.0, 10.0],
            "close": [10.0, 10.0],
            "volume": [1, 1],
            "amount": [1.0, 1.0],
        }
    )
    out = _apply_adj_factor(raw, factors).sort("date")
    assert abs(out["close"][0] - 10.0 / cum[0][1]) < 1e-9
    assert abs(out["close"][1] - 10.0) < 1e-9
