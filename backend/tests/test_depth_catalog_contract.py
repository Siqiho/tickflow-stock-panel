from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.services.depth_service import DepthService


def test_tickflow_depth_summary_is_persisted_as_sealed_l1_not_depth5(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = DepthService()
    service._repo = type("Repo", (), {"store": type("Store", (), {"data_dir": tmp_path})()})()
    service._sealed_cache = {
        "600000.SH": {
            "sealed_up": True,
            "sealed_down": False,
            "ask1_vol": 0,
            "bid1_vol": 100,
            "status": "limit_up",
            "fetched_ts": 1_753_084_800.0,
        }
    }
    monkeypatch.setattr(service, "_has_tickflow_depth", lambda: True)
    monkeypatch.setattr(service, "_depth_source", lambda: "tickflow")

    service._persist(date(2026, 7, 21))

    assert (tmp_path / "sealed_l1" / "date=2026-07-21" / "part.parquet").is_file()
    assert not (tmp_path / "depth5").exists()
    lineage_files = list((tmp_path / "lineage" / "sealed_l1").rglob("*.json"))
    assert len(lineage_files) == 1
    lineage = json.loads(lineage_files[0].read_text(encoding="utf-8"))
    assert lineage["unit_version"] == "sealed_l1_v1"
    assert lineage["target_artifact"] == "sealed_l1/date=2026-07-21/part.parquet"
