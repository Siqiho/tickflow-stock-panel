"""Crash-safe local artifact writers."""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl


def parquet_file_stamp(path: Path) -> tuple[int, int] | None:
    """Return (mtime_ns, size) for optimistic publish, or None if missing."""
    try:
        st = Path(path).stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def optimistic_upsert_parquet(
    incoming: pl.DataFrame,
    target: Path,
    *,
    keys: list[str],
    sort_by: list[str] | str,
    lock: threading.Lock,
    max_retries: int = 64,
    prepare_existing: Callable[[pl.DataFrame], pl.DataFrame] | None = None,
) -> int:
    """Concat/unique outside ``lock``; publish with ``atomic_write_parquet`` if stamp is unchanged.

    Callers must not already hold ``lock`` (it is not re-entrant). A failed
    ``atomic_write_parquet`` leaves the original target in place.
    """
    target = Path(target)
    if incoming is None or incoming.is_empty():
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    sort_cols = [sort_by] if isinstance(sort_by, str) else list(sort_by)
    for _ in range(max_retries):
        stamp = parquet_file_stamp(target)
        if target.exists():
            existing = pl.read_parquet(target)
            if prepare_existing is not None:
                existing = prepare_existing(existing)
            if existing is None or existing.is_empty():
                merged = incoming
            else:
                merged = pl.concat([existing, incoming], how="diagonal_relaxed").unique(
                    subset=keys, keep="last",
                )
        else:
            merged = incoming
        merged = merged.sort(sort_cols)
        with lock:
            if parquet_file_stamp(target) != stamp:
                continue
            atomic_write_parquet(merged, target)
            return merged.height
    raise RuntimeError(f"optimistic parquet upsert exhausted retries: {target}")


def atomic_write_parquet(df: pl.DataFrame, target: Path) -> None:
    """Write a Parquet file beside its target and publish it with os.replace."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp-{uuid.uuid4().hex}")
    try:
        df.write_parquet(tmp)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_write_json(value: Any, target: Path, *, indent: int | None = None) -> None:
    """Write a complete UTF-8 JSON document and atomically publish it."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp-{uuid.uuid4().hex}")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=indent, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def write_lineage_record(
    data_dir: Path,
    dataset: str,
    record: dict[str, Any],
    *,
    run_id: str | None = None,
) -> Path:
    """Persist one immutable provenance sidecar for a produced data artifact."""
    payload = dict(record)
    unit_version = payload.get("unit_version")
    if not isinstance(unit_version, str) or not unit_version.strip():
        raise ValueError("lineage record requires a non-empty unit_version")
    payload.setdefault("fetched_at", datetime.now().astimezone().isoformat())
    ds = str(payload.get("date") or "unknown")
    rid = run_id or uuid.uuid4().hex
    target = Path(data_dir) / "lineage" / dataset / f"date={ds}" / f"{rid}.json"
    atomic_write_json(payload, target, indent=2)
    return target
