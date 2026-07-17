"""Staging writes for custom sources — never write production kline partitions directly."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from app.config import settings


def staging_root(data_dir: Path | None = None) -> Path:
    root = (data_dir or settings.data_dir) / "staging" / "custom"
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_daily_staging(
    provider: str,
    df: pl.DataFrame,
    *,
    data_dir: Path | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Write mapped daily rows into staging only.

    Path: data/staging/custom/{provider}/daily/run={ts}/part.parquet
    """
    if df is None or df.is_empty():
        return {"ok": False, "error": "empty frame", "path": None, "rows": 0}

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = staging_root(data_dir) / provider / "daily" / f"run={ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "part.parquet"
    # enforce source column for lineage
    if "source" not in df.columns:
        df = df.with_columns(pl.lit(provider).alias("source"))
    df.write_parquet(path)
    meta = {
        "provider": provider,
        "dataset": "daily",
        "rows": df.height,
        "columns": df.columns,
        "path": str(path),
        "created_at": ts,
        "note": note,
        "promoted": False,
        "policy": "staging_only_no_auto_promote",
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, **meta}
