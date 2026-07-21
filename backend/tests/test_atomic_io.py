from __future__ import annotations

import json
from datetime import date

import polars as pl
import pytest

from app.services.atomic_io import atomic_write_json, atomic_write_parquet, write_lineage_record


def test_atomic_parquet_failure_preserves_existing_target(tmp_path, monkeypatch):
    target = tmp_path / "part.parquet"
    pl.DataFrame({"value": [1]}).write_parquet(target)

    def fail_write(self, path, *args, **kwargs):
        raise OSError("simulated interruption")

    monkeypatch.setattr(pl.DataFrame, "write_parquet", fail_write)
    with pytest.raises(OSError, match="simulated interruption"):
        atomic_write_parquet(pl.DataFrame({"value": [2]}), target)

    assert pl.read_parquet(target)["value"].item() == 1
    assert not list(tmp_path.glob(".*.tmp-*"))


def test_atomic_json_replaces_complete_document(tmp_path):
    target = tmp_path / "state.json"

    atomic_write_json({"status": "degraded", "date": date(2026, 7, 20)}, target)

    assert json.loads(target.read_text("utf-8")) == {
        "status": "degraded",
        "date": "2026-07-20",
    }
    assert not list(tmp_path.glob(".*.tmp-*"))


def test_lineage_record_contains_required_provenance(tmp_path):
    path = write_lineage_record(
        tmp_path,
        "kline_daily",
        {
            "date": "2026-07-17",
            "source": "tickflow",
            "unit_version": "canonical_daily_v1",
            "row_count": 5522,
            "scope": "ALL",
            "quality": "passed",
            "target_artifact": "kline_daily/date=2026-07-17/part.parquet",
        },
        run_id="unit-test",
    )

    record = json.loads(path.read_text("utf-8"))
    assert path == tmp_path / "lineage" / "kline_daily" / "date=2026-07-17" / "unit-test.json"
    assert record["source"] == "tickflow"
    assert record["row_count"] == 5522
    assert record["fetched_at"]
