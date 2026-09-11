from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import polars as pl

from app.data_catalog.scanner import CatalogScanner


def _load_reconciler():
    path = Path(__file__).resolve().parents[3] / "scripts" / "reconcile-legacy-market-lineage.py"
    spec = importlib.util.spec_from_file_location("legacy_lineage_reconciler", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reconciler_uses_scanner_artifacts_and_is_idempotent(tmp_path: Path) -> None:
    artifact = tmp_path / "kline_daily" / "date=2026-08-12" / "part.parquet"
    artifact.parent.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["600000.SH"],
            "date": [date(2026, 8, 12)],
            "open": [10.0],
            "high": [11.0],
            "low": [9.0],
            "close": [10.5],
            "volume": [100.0],
            "amount": [1050.0],
        }
    ).write_parquet(artifact)
    module = _load_reconciler()

    dry_run = module.reconcile(tmp_path, apply=False)
    applied = module.reconcile(tmp_path, apply=True)
    repeated = module.reconcile(tmp_path, apply=False)

    assert dry_run["by_dataset_id"] == {"stock_daily": 1}
    assert applied["planned"] == applied["written"] == 1
    assert repeated["planned"] == 0
    result = CatalogScanner(tmp_path).scan_dataset("stock_daily", "verify")
    assert result.state.quality_status == "healthy"
    assert result.state.unit_version == "canonical_daily_v1"
    assert result.state.payload["scan_errors"] == []
    assert result.lineage[0].source == "legacy_local_artifact"


def test_reconciler_refuses_non_lineage_scan_errors(tmp_path: Path) -> None:
    artifact = tmp_path / "kline_daily" / "date=2026-08-12" / "part.parquet"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"not parquet")
    module = _load_reconciler()

    try:
        module.reconcile(tmp_path, apply=True)
    except RuntimeError as error:
        assert "non-lineage scan errors" in str(error)
    else:
        raise AssertionError("corrupt Parquet must stop reconciliation")

    assert not list((tmp_path / "lineage").glob("**/legacy-*.json"))


def test_reconciler_does_not_rewrite_already_aligned_current_record(tmp_path: Path) -> None:
    artifact = tmp_path / "kline_daily" / "date=2026-08-12" / "part.parquet"
    artifact.parent.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["600000.SH"],
            "date": [date(2026, 8, 12)],
            "open": [10.0],
            "high": [11.0],
            "low": [9.0],
            "close": [10.5],
            "volume": [100.0],
            "amount": [1050.0],
        }
    ).write_parquet(artifact)
    current = tmp_path / "lineage" / "kline_daily" / "date=2026-08-12" / "current.json"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text(
        __import__("json").dumps(
            {
                "source": "public_quote_eod_merged",
                "unit_version": "canonical_daily_v1",
                "quality": "pending_gate",
                "row_count": 1,
                "target_artifact": "kline_daily/date=2026-08-12/part.parquet",
            }
        ),
        encoding="utf-8",
    )
    module = _load_reconciler()
    plan = module.reconcile(tmp_path, apply=True)
    assert plan["planned"] == 0
    assert plan["written"] == 0
    assert list((tmp_path / "lineage" / "stock_daily").glob("**/legacy-*.json")) == []

