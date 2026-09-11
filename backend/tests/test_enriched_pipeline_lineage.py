from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from app.data_catalog.scanner import CatalogScanner
from app.indicators.pipeline import run_pipeline
from app.services import preferences


def test_run_pipeline_publishes_catalog_admissible_enriched_partitions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preferences, "get_pipeline_universe_scope", lambda: "CSI300")
    daily = pl.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "date": date(2026, 8, 6),
                "open": 10.0,
                "high": 10.8,
                "low": 9.8,
                "close": 10.5,
                "volume": 100.0,
                "amount": 105_000.0,
            },
            {
                "symbol": "600000.SH",
                "date": date(2026, 8, 7),
                "open": 10.5,
                "high": 11.2,
                "low": 10.2,
                "close": 11.0,
                "volume": 120.0,
                "amount": 132_000.0,
            },
        ]
    )
    for date_df in daily.partition_by("date"):
        ds = date_df["date"][0].isoformat()
        out = tmp_path / "kline_daily" / f"date={ds}" / "part.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        date_df.write_parquet(out)

    assert run_pipeline(data_dir=tmp_path) == 2

    result = CatalogScanner(tmp_path).scan_dataset(
        "stock_enriched",
        "run-enriched-lineage",
    )
    assert result.state.quality_status == "healthy"
    assert result.state.unit_version == "canonical_daily_v1"
    assert result.state.row_count == 2
    assert [artifact.path for artifact in result.artifacts] == [
        "kline_daily_enriched/date=2026-08-06/part.parquet",
        "kline_daily_enriched/date=2026-08-07/part.parquet",
    ]

    lineage_files = sorted((tmp_path / "lineage" / "kline_daily_enriched").rglob("*.json"))
    assert len(lineage_files) == 2
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in lineage_files]
    assert {payload["target_artifact"] for payload in payloads} == {
        "kline_daily_enriched/date=2026-08-06/part.parquet",
        "kline_daily_enriched/date=2026-08-07/part.parquet",
    }
    assert {payload["source"] for payload in payloads} == {"derived_indicators_pipeline"}
    assert {payload["scope"] for payload in payloads} == {"CSI300"}
    assert {payload["calculation_mode"] for payload in payloads} == {"full_market"}
    assert {payload["quality"] for payload in payloads} == {"healthy"}
