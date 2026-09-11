import json
from datetime import date, datetime, timedelta

import polars as pl

from app.services import ai_provider, stock_analyzer


class _FakeRepo:
    def __init__(self, daily: pl.DataFrame) -> None:
        self._daily = daily

    def get_daily(self, symbol: str, start: date, end: date) -> pl.DataFrame:
        return self._daily


async def test_stock_analysis_stream_serializes_financial_dates_before_ai(tmp_path, monkeypatch):
    metrics_dir = tmp_path / "financials" / "metrics"
    metrics_dir.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["300274.SZ"],
            "period_end": [date(2026, 3, 31)],
            "fetched_at": [datetime(2026, 4, 28, 15, 30)],
            "roe": [12.3],
        }
    ).write_parquet(metrics_dir / "part.parquet")

    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(30)]
    closes = [100.0 + i * 0.1 for i in range(30)]
    daily = pl.DataFrame(
        {
            "date": dates,
            "open": [value - 0.2 for value in closes],
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
            "close": closes,
            "volume": [1_000_000.0 + i * 1_000 for i in range(30)],
        }
    )

    captured_messages: list[dict] = []

    async def fake_stream_ai_text(messages, **kwargs):
        captured_messages.extend(messages)
        yield "分析片段"

    monkeypatch.setattr(ai_provider, "stream_ai_text", fake_stream_ai_text)

    events = [
        json.loads(chunk)
        async for chunk in stock_analyzer.analyze_stock_stream(
            _FakeRepo(daily), tmp_path, "300274.SZ"
        )
    ]

    assert [event["type"] for event in events] == ["meta", "delta", "done"]
    assert events[1]["content"] == "分析片段"
    assert captured_messages[1]["role"] == "user"
    assert '"period_end": "2026-03-31"' in captured_messages[1]["content"]
    assert '"fetched_at": "2026-04-28T15:30:00"' in captured_messages[1]["content"]
