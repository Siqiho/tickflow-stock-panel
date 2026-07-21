from __future__ import annotations

from datetime import date

import polars as pl

from app.indicators.pipeline import _load_recent_history
from app.services.financial_analyzer import _build_user_prompt


def test_load_recent_history_uses_local_scan_cast_options(tmp_path):
    part = tmp_path / "date=2026-07-17"
    part.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["000001.SZ"],
            "date": [date.today()],
            "open": [10],
            "high": [11],
            "low": [9],
            "close": [10],
            "volume": [1000],
            "amount": [1_000_000],
        }
    ).write_parquet(part / "part.parquet")

    history = _load_recent_history(tmp_path, ["000001.SZ"], days=90)

    assert history.height == 1
    assert history["symbol"].item() == "000001.SZ"


def test_financial_prompt_serializes_date_values():
    fins = {
        "metrics": [
            {
                "symbol": "000001.SZ",
                "period_end": date(2026, 3, 31),
                "announce_date": date(2026, 4, 25),
                "roe": 12.3,
            }
        ]
    }

    prompt = _build_user_prompt(fins, "000001.SZ", "")

    assert '"period_end": "2026-03-31"' in prompt
    assert '"announce_date": "2026-04-25"' in prompt
