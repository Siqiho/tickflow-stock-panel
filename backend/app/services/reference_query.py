"""Local-only readers for newly published reference datasets.

These helpers only open already materialized Parquet. They never call an
external producer, never write managed data, and never refresh the catalog.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

_DATASET_SPECS: dict[str, dict[str, Any]] = {
    "valuation_daily": {
        "relpath": "reference/valuation_daily",
        "unit_version": "valuation_daily_v2",
        "date_column": "trade_date",
        "sort": ["trade_date", "symbol"],
        "descending": [True, False],
        "symbol_required_for_unbounded": True,
    },
    "limit_up_events": {
        "relpath": "reference/limit_up_events",
        "unit_version": "limit_up_events_v2",
        "date_column": "trade_date",
        "sort": ["trade_date", "symbol"],
        "descending": [True, False],
        "symbol_required_for_unbounded": False,
    },
    "index_membership_history": {
        "relpath": "reference/index_membership_history/members.parquet",
        "unit_version": "index_membership_history_v2",
        "date_column": "as_of",
        "sort": ["pool_id", "symbol", "effective_from"],
        "descending": [False, False, True],
        "symbol_required_for_unbounded": False,
        "extra_filters": ("pool_id", "index_code"),
    },
    "corporate_actions": {
        "relpath": "reference/corporate_actions/actions.parquet",
        "unit_version": "corporate_actions_v2",
        "date_column": "ex_date",
        "sort": ["ex_date", "announce_date", "action_id"],
        "descending": [True, True, False],
        "symbol_required_for_unbounded": True,
    },
}


def _as_date(value: date | datetime | str | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"日期格式无效: {text}") from exc


def _normalize_symbol(symbol: str | None) -> str | None:
    text = (symbol or "").strip().upper()
    return text or None


def _reference_route_token(dataset_id: str) -> str:
    """Route token used to prefer tagged leftover files in one directory."""
    try:
        if dataset_id in {"valuation_daily", "limit_up_events"}:
            from app.services.kline_sync import daily_route

            return daily_route()
        if dataset_id == "index_membership_history":
            from app.tickflow.pools import pool_route

            return pool_route()
        if dataset_id == "corporate_actions":
            from app.services.kline_sync import adj_route

            return adj_route()
    except Exception:
        return "unresolved"
    return "unresolved"


def _reference_file_usable(dataset_id: str, path: Path) -> bool:
    """Current-route reference parquet only. Leftover TickFlow still sees untagged."""
    try:
        if dataset_id in {"valuation_daily", "limit_up_events"}:
            from app.services.kline_sync import daily_partition_usable

            return daily_partition_usable(path)
        if dataset_id == "index_membership_history":
            from app.services.reference_derived import _pool_snapshot_usable
            from app.tickflow.pools import pool_route

            return _pool_snapshot_usable(pl.read_parquet(path), pool_route())
        if dataset_id == "corporate_actions":
            from app.services.kline_sync import adj_cache_usable, adj_route

            route = adj_route()
            names = pl.read_parquet_schema(path).names()
            if "route" not in names:
                return route in {"tickflow", "public"}
            return adj_cache_usable(pl.read_parquet(path, columns=["route"]), route)
    except Exception:
        return False
    return False


def _scan_dataset(data_dir: Path, relpath: str, dataset_id: str) -> pl.LazyFrame | None:
    target = data_dir / relpath
    if target.is_file():
        if not _reference_file_usable(dataset_id, target):
            return None
        return pl.scan_parquet(target)
    if target.is_dir():
        files = [
            path for path in sorted(target.rglob("*.parquet"))
            if _reference_file_usable(dataset_id, path)
        ]
        from app.services.kline_sync import preferred_readable_route_files_by_dir

        files = preferred_readable_route_files_by_dir(
            files, _reference_route_token(dataset_id),
        )
        if not files:
            return None
        return pl.scan_parquet([str(path) for path in files])
    return None


def _jsonable_rows(frame: pl.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in frame.to_dicts():
        cleaned: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, (date, datetime)):
                cleaned[key] = value.isoformat()
            else:
                cleaned[key] = value
        rows.append(cleaned)
    return rows


def query_reference_dataset(
    data_dir: Path,
    dataset_id: str,
    *,
    symbol: str | None = None,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    pool_id: str | None = None,
    index_code: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    spec = _DATASET_SPECS.get(dataset_id)
    if spec is None:
        raise ValueError(f"未知参考数据集: {dataset_id}")

    try:
        bounded_limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit 必须是整数") from exc
    if bounded_limit < 1 or bounded_limit > 500:
        raise ValueError("limit 必须介于 1 和 500 之间")

    symbol_key = _normalize_symbol(symbol)
    start = _as_date(start_date)
    end = _as_date(end_date)
    if start and end and start > end:
        raise ValueError("start_date 不能晚于 end_date")
    if spec.get("symbol_required_for_unbounded") and not symbol_key and not start and not end:
        raise ValueError(f"{dataset_id} 全表查询必须提供 symbol 或日期窗口")

    scan = _scan_dataset(Path(data_dir), spec["relpath"], dataset_id)
    if scan is None:
        return {
            "data": [],
            "count": 0,
            "source": "local",
            "dataset_id": dataset_id,
            "unit_version": spec["unit_version"],
        }

    date_column = spec["date_column"]
    schema_names = set(scan.collect_schema().names())
    if symbol_key and "symbol" in schema_names:
        scan = scan.filter(pl.col("symbol") == symbol_key)
    if start is not None:
        scan = scan.filter(pl.col(date_column) >= start)
    if end is not None:
        scan = scan.filter(pl.col(date_column) <= end)
    extra_filters = spec.get("extra_filters") or ()
    extras = {"pool_id": (pool_id or "").strip(), "index_code": (index_code or "").strip()}
    for name in extra_filters:
        value = extras.get(name) or ""
        if value:
            scan = scan.filter(pl.col(name) == value)

    sort_cols = [column for column in spec["sort"] if column in schema_names]
    descending = spec["descending"][: len(sort_cols)]
    if sort_cols:
        scan = scan.sort(sort_cols, descending=descending, nulls_last=True)
    frame = scan.limit(bounded_limit).collect()
    return {
        "data": _jsonable_rows(frame),
        "count": frame.height,
        "source": "local",
        "dataset_id": dataset_id,
        "unit_version": spec["unit_version"],
    }
