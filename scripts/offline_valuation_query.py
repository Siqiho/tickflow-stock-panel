#!/usr/bin/env python3
"""Read-only QuantDB valuation history query. No App/DataStore/API import.

Default root is the local QuantDB snapshot. Only
``5_technical_derived/valuation/<symbol>.parquet`` is opened. This script never
writes source files, never overlays StockDB repairs or project nulls, and never
applies a silent unit conversion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

SOURCE = "offline_quantdb"
DATASET = "5_technical_derived/valuation"
LAYOUT = "by_symbol"
DATASET_RELATIVE = Path("5_technical_derived") / "valuation"
DEFAULT_ROOT = Path("/Users/simon/Trading/下载数据/quant_data")
DEFAULT_PROJECT_DATA_DIR = Path("/Users/simon/Trading/one-trading/data")
PROJECT_VALUATION_RELATIVE = Path("reference") / "valuation_daily"
ALLOWED_EVIDENCE_DIR = Path(
    "/Users/simon/Trading/one-trading/docs/investigations/2026-09-11-offline-valuation-readonly"
)
FIXED_SAMPLES = ("000001.SZ", "000338.SZ", "600519.SH", "300750.SZ")
OVERLAP_START = date(2026, 7, 21)
OVERLAP_END = date(2026, 8, 12)
DEFAULT_LIMIT = 100
MAX_LIMIT = 5000
SYMBOL_RE = re.compile(r"^\d{6}\.(SZ|SH|BJ)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LIMIT_INT_RE = re.compile(r"^[+-]?\d+$")

REQUIRED_COLUMNS = (
    "time",
    "Symbol",
    "close",
    "total_capital",
    "circulating_capital",
    "total_mv",
    "float_mv",
    "pe_ttm",
    "pb",
    "ps_ttm",
)
OPTIONAL_COLUMNS = (
    "net_profit_ttm",
    "revenue_ttm",
    "equity",
    "annual_net_profit",
    "pe_static",
    "dividend_rate",
)
NUMERIC_COLUMNS = (
    "close",
    "total_capital",
    "circulating_capital",
    "total_mv",
    "float_mv",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "net_profit_ttm",
    "revenue_ttm",
    "equity",
    "annual_net_profit",
    "pe_static",
    "dividend_rate",
)
MAPPED_COLUMNS = (
    "symbol",
    "date",
    "close",
    "total_share",
    "float_share",
    "total_mv",
    "float_mv",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "net_profit_ttm",
    "revenue_ttm",
    "equity",
    "annual_net_profit",
    "pe_static",
    "dividend_rate",
)
FIELD_MAP = {
    "Symbol": "symbol",
    "time": "date",
    "close": "close",
    "total_capital": "total_share",
    "circulating_capital": "float_share",
    "total_mv": "total_mv",
    "float_mv": "float_mv",
    "pe_ttm": "pe_ttm",
    "pb": "pb",
    "ps_ttm": "ps_ttm",
    "net_profit_ttm": "net_profit_ttm",
    "revenue_ttm": "revenue_ttm",
    "equity": "equity",
    "annual_net_profit": "annual_net_profit",
    "pe_static": "pe_static",
    "dividend_rate": "dividend_rate",
}
MISSING_VERSUS_PROJECT_V2 = (
    "pcf_ttm",
    "shares_pit_safe",
    "shares_source",
    "unit_version",
    "unit_note",
    "history_guarantee",
    "fetched_at",
)
HISTORICAL_INVENTORY = {
    "as_of": "2026-09-06",
    "cited_from": (
        "/Users/simon/Trading/下载数据/stockdb_quantdb_integration_review_20260906/"
        "package_sanity.json"
    ),
    "this_round_full_market_scan": False,
    "valuation_by_symbol": {
        "files": 5554,
        "physical_rows": 10_770_127,
        "empty_files": 0,
        "time_min_native": "2016-01-04 00:00:00",
        "time_max_native": "2026-08-27 00:00:00",
        "bytes": 694_488_966,
    },
    "note": (
        "Market-wide coverage is the 2026-09-06 inventory only. This round reads "
        "four by-symbol files and does not rescan the 80G packages."
    ),
}
UNIT_NOTE = (
    "No silent conversion. Daily-bar amount×10000 is not applied to valuation. "
    "Units for total_capital/circulating_capital and total_mv/float_mv remain "
    "unknown/unverified. total_mv == close * total_capital on finite rows is "
    "identity consistency only; it does not prove 股/元 versus 万股/万元 and "
    "is not a unit rewrite. PE/PB/PS formulas are not confirmed. "
    "dividend_rate ratio versus percent is not confirmed by appearance. "
    "Negative PE is kept. NaN/Inf is emitted as JSON null plus an anomaly mark."
)
OVERLAY_CONTRACT = {
    "stockdb_repair_loaded": False,
    "preclose_candidates_loaded": False,
    "project_null_overlay": False,
    "default_overlay": False,
    "note": (
        "Project and package are compared side by side only. Existing repair SQL "
        "keeps exact identity, original-null-only fill, and opt-in preclose. "
        "This reader does not load those views."
    ),
}


class ValuationQueryError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def apply_overlay(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError(
        "valuation overlay is disabled; project and package stay side-by-side"
    )


def dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2)


def fingerprint(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "is_symlink": path.is_symlink(),
        }
    st = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "exists": True,
        "is_symlink": path.is_symlink(),
        "size": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        "mtime_ns": st.st_mtime_ns,
        "mode": oct(stat.S_IMODE(st.st_mode)),
        "sha256": digest.hexdigest(),
    }


def normalize_symbol(symbol: str | None) -> str:
    text = str(symbol or "").strip().upper()
    if not text:
        raise ValuationQueryError(
            "valuation_offline_invalid_symbol",
            "symbol 不能为空",
        )
    if any(part in text for part in ("/", "\\", "..", "\x00")):
        raise ValuationQueryError(
            "valuation_offline_invalid_symbol",
            f"非法 symbol（拒绝路径片段）: {symbol}",
        )
    if not SYMBOL_RE.match(text):
        raise ValuationQueryError(
            "valuation_offline_invalid_symbol",
            f"非法 A 股 symbol: {symbol}",
        )
    return text


def parse_date(value: date | datetime | str | None, *, field: str) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValuationQueryError(
            "valuation_offline_invalid_date",
            f"{field} 必须是 YYYY-MM-DD: {value}",
        )
    text = value.strip()
    if not DATE_RE.fullmatch(text):
        raise ValuationQueryError(
            "valuation_offline_invalid_date",
            f"{field} 必须是 YYYY-MM-DD: {value}",
        )
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValuationQueryError(
            "valuation_offline_invalid_date",
            f"{field} 必须是 YYYY-MM-DD: {value}",
        ) from exc


def parse_limit(value: Any) -> int:
    if isinstance(value, bool):
        raise ValuationQueryError(
            "valuation_offline_invalid_limit",
            "limit 必须是整数，不能是 bool",
        )
    if isinstance(value, int):
        limit = value
    elif isinstance(value, str):
        text = value.strip()
        if not LIMIT_INT_RE.fullmatch(text):
            raise ValuationQueryError(
                "valuation_offline_invalid_limit",
                "limit 必须是整数",
            )
        limit = int(text)
    else:
        raise ValuationQueryError(
            "valuation_offline_invalid_limit",
            "limit 必须是整数",
        )
    if limit < 1 or limit > MAX_LIMIT:
        raise ValuationQueryError(
            "valuation_offline_invalid_limit",
            f"limit 必须介于 1 和 {MAX_LIMIT} 之间",
        )
    return limit


def jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def _finite_kind(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf"
    return None


def _is_date_or_datetime(dtype: pl.DataType) -> bool:
    return dtype == pl.Date or isinstance(dtype, pl.Datetime)


def _is_string_dtype(dtype: pl.DataType) -> bool:
    return dtype == pl.String or dtype == pl.Utf8


def _date_expr(column: str = "time") -> pl.Expr:
    return pl.col(column).cast(pl.Date)


def _as_date(value: Any) -> date:
    if value is None or value == "":
        raise ValuationQueryError(
            "valuation_offline_invalid_identity",
            "估值行 time 为空",
        )
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValuationQueryError(
        "valuation_offline_invalid_schema",
        f"估值行 time 类型不受支持: {type(value).__name__}",
    )


def _assert_resolved_within(path: Path, root: Path, *, label: str) -> Path:
    try:
        resolved = path.resolve()
    except OSError as exc:
        raise ValuationQueryError(
            "valuation_offline_symlink_escape",
            f"估值路径无法解析: {label}",
        ) from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValuationQueryError(
            "valuation_offline_symlink_escape",
            f"估值路径越出 QuantDB root: {label}",
        ) from exc
    return resolved


def _finite_expr(name: str, dtype: pl.DataType) -> pl.Expr:
    expr = pl.col(name).is_not_null()
    if dtype.is_float():
        expr = expr & (~pl.col(name).is_nan()) & (~pl.col(name).is_infinite())
    return expr


def resolve_root(root: Path | str | None) -> Path:
    if root is None or not str(root).strip():
        raise ValuationQueryError(
            "valuation_offline_unconfigured",
            "QuantDB root 未配置",
        )
    path = Path(root)
    if not path.exists():
        raise ValuationQueryError(
            "valuation_offline_root_missing",
            f"QuantDB root 不存在: {path}",
        )
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValuationQueryError(
            "valuation_offline_root_missing",
            f"QuantDB root 不是目录: {path}",
        )
    return resolved


def valuation_dir(root: Path) -> Path:
    resolved_root = Path(root)
    current = resolved_root
    for part in DATASET_RELATIVE.parts:
        current = _assert_resolved_within(current / part, resolved_root, label=part)
    if not current.exists():
        raise ValuationQueryError(
            "valuation_offline_dataset_missing",
            f"估值目录不存在: {current}",
        )
    if not current.is_dir():
        raise ValuationQueryError(
            "valuation_offline_dataset_missing",
            f"估值路径不是目录: {current}",
        )
    return current


def resolve_valuation_path(root: Path | str | None, symbol: str) -> Path:
    canonical = normalize_symbol(symbol)
    resolved_root = resolve_root(root)
    base = valuation_dir(resolved_root)
    candidate = base / f"{canonical}.parquet"
    target = _assert_resolved_within(candidate, resolved_root, label=canonical)
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValuationQueryError(
            "valuation_offline_symlink_escape",
            f"估值文件 symlink 越出数据集目录: {canonical}",
        ) from exc
    if target.name != f"{canonical}.parquet":
        raise ValuationQueryError(
            "valuation_offline_invalid_symbol",
            f"估值文件名与 symbol 不一致: {symbol}",
        )
    return target


def read_valuation_frame(path: Path) -> pl.DataFrame:
    try:
        with path.open("rb"):
            pass
    except PermissionError as exc:
        raise ValuationQueryError(
            "valuation_offline_permission",
            f"估值文件无读权限: {path}",
        ) from exc
    except FileNotFoundError as exc:
        raise ValuationQueryError(
            "valuation_offline_not_found",
            f"估值文件不存在: {path}",
        ) from exc
    try:
        return pl.read_parquet(path)
    except PermissionError as exc:
        raise ValuationQueryError(
            "valuation_offline_permission",
            f"估值文件无读权限: {path}",
        ) from exc
    except Exception as exc:  # noqa: BLE001 — distinguish corrupt from missing
        raise ValuationQueryError(
            "valuation_offline_unreadable",
            f"估值文件损坏或无法解析: {path}",
        ) from exc


def _require_schema(frame: pl.DataFrame) -> None:
    missing = [name for name in REQUIRED_COLUMNS if name not in frame.columns]
    if missing:
        raise ValuationQueryError(
            "valuation_offline_invalid_schema",
            f"估值文件缺少字段: {', '.join(missing)}",
        )
    time_dtype = frame.schema["time"]
    if not _is_date_or_datetime(time_dtype):
        raise ValuationQueryError(
            "valuation_offline_invalid_schema",
            f"time 必须是 Date/Datetime，实际为 {time_dtype}",
        )
    symbol_dtype = frame.schema["Symbol"]
    if not _is_string_dtype(symbol_dtype):
        raise ValuationQueryError(
            "valuation_offline_invalid_schema",
            f"Symbol 必须是字符串，实际为 {symbol_dtype}",
        )
    for name in NUMERIC_COLUMNS:
        if name not in frame.columns:
            continue
        dtype = frame.schema[name]
        if dtype == pl.Null:
            continue
        if not dtype.is_numeric():
            raise ValuationQueryError(
                "valuation_offline_invalid_schema",
                f"{name} 必须是数值类型或 null，实际为 {dtype}",
            )


def _require_identity(frame: pl.DataFrame, *, requested_symbol: str) -> None:
    if frame.height == 0:
        return
    if int(frame["time"].null_count()) > 0:
        raise ValuationQueryError(
            "valuation_offline_invalid_identity",
            "估值文件存在空 time",
        )
    try:
        symbols = frame["Symbol"].cast(pl.Utf8)
    except Exception as exc:  # noqa: BLE001 — fail closed, no raw schema traceback
        raise ValuationQueryError(
            "valuation_offline_invalid_schema",
            "Symbol 无法按字符串读取",
        ) from exc
    if int(symbols.null_count()) > 0:
        raise ValuationQueryError(
            "valuation_offline_invalid_identity",
            "估值文件存在空 Symbol",
        )
    normalized = symbols.str.strip_chars().str.to_uppercase()
    if int((normalized == "").sum()) > 0:
        raise ValuationQueryError(
            "valuation_offline_invalid_identity",
            "估值行 Symbol 为空，拒绝补成 requested_symbol",
        )
    valid = normalized.str.contains(r"^\d{6}\.(SZ|SH|BJ)$")
    if int((~valid).sum()) > 0:
        bad = normalized.filter(~valid)[0]
        raise ValuationQueryError(
            "valuation_offline_invalid_identity",
            f"估值行 Symbol 非法: {bad}",
        )
    mismatched = normalized.filter(normalized != requested_symbol)
    if mismatched.len() > 0:
        raise ValuationQueryError(
            "valuation_offline_invalid_identity",
            f"估值行 Symbol 与请求/文件不一致: {mismatched[0]} != {requested_symbol}",
        )


def _field_report(frame: pl.DataFrame) -> dict[str, Any]:
    original = list(frame.columns)
    return {
        "original": original,
        "mapped": dict(FIELD_MAP),
        "optional_present": [name for name in OPTIONAL_COLUMNS if name in frame.columns],
        "optional_absent": [name for name in OPTIONAL_COLUMNS if name not in frame.columns],
        "missing_versus_project": list(MISSING_VERSUS_PROJECT_V2),
    }


def _duplicate_keys(frame: pl.DataFrame) -> list[dict[str, Any]]:
    try:
        keys = frame.select(
            pl.col("Symbol").cast(pl.Utf8).str.strip_chars().str.to_uppercase().alias("symbol"),
            _date_expr("time").alias("date"),
        )
    except ValuationQueryError:
        raise
    except Exception as exc:  # noqa: BLE001 — avoid .dt.date/isoformat traceback
        raise ValuationQueryError(
            "valuation_offline_invalid_schema",
            "估值文件 time/Symbol 无法用于去重",
        ) from exc
    dup = keys.group_by(["symbol", "date"]).len().filter(pl.col("len") > 1)
    if dup.height == 0:
        return []
    rows: list[dict[str, Any]] = []
    for row in dup.iter_rows(named=True):
        day = row["date"]
        if day is None:
            raise ValuationQueryError(
                "valuation_offline_invalid_identity",
                "重复空 time",
            )
        rows.append(
            {
                "symbol": row["symbol"],
                "date": day.isoformat(),
                "count": int(row["len"]),
            }
        )
    return rows


def _quality_scan(frame: pl.DataFrame, *, requested_symbol: str) -> dict[str, Any]:
    anomalies: list[dict[str, Any]] = []
    null_counts: dict[str, int] = {}
    non_finite_counts: dict[str, int] = {}
    negative_pe = 0
    for column in list(REQUIRED_COLUMNS) + [name for name in OPTIONAL_COLUMNS if name in frame.columns]:
        series = frame[column]
        null_counts[column] = int(series.null_count())
        if series.dtype.is_float():
            nan_count = int(series.is_nan().sum())
            inf_count = int(series.is_infinite().sum())
            if nan_count or inf_count:
                non_finite_counts[column] = nan_count + inf_count
        if column == "pe_ttm" and series.dtype.is_float():
            negative_pe = int((series < 0).sum())
    for row in frame.iter_rows(named=True):
        row_date = _as_date(row.get("time")).isoformat()
        row_symbol = str(row.get("Symbol") or "").upper()
        for column, value in row.items():
            kind = _finite_kind(value)
            if kind:
                anomalies.append(
                    {
                        "symbol": row_symbol,
                        "date": row_date,
                        "field": column,
                        "kind": kind,
                    }
                )
        if row_symbol and row_symbol != requested_symbol:
            anomalies.append(
                {
                    "symbol": row_symbol,
                    "date": row_date,
                    "field": "Symbol",
                    "kind": "symbol_mismatch",
                }
            )
    try:
        dates = frame["time"].cast(pl.Date)
        min_d = dates.min() if frame.height else None
        max_d = dates.max() if frame.height else None
    except ValuationQueryError:
        raise
    except Exception as exc:  # noqa: BLE001 — avoid .dt.date/isoformat traceback
        raise ValuationQueryError(
            "valuation_offline_invalid_schema",
            "time 无法转为 Date",
        ) from exc
    return {
        "row_count": frame.height,
        "min_date": min_d.isoformat() if min_d is not None else None,
        "max_date": max_d.isoformat() if max_d is not None else None,
        "null_counts": null_counts,
        "non_finite_counts": non_finite_counts,
        "negative_pe_ttm": negative_pe,
        "anomalies": anomalies,
        "duplicate_keys": [],
    }


def _map_row(row: dict[str, Any], *, requested_symbol: str) -> dict[str, Any]:
    flags: dict[str, str] = {}
    mapped: dict[str, Any] = {}
    for source_name, dest_name in FIELD_MAP.items():
        if source_name not in row:
            continue
        raw = row[source_name]
        kind = _finite_kind(raw)
        if dest_name == "symbol":
            text = "" if raw is None else str(raw).strip().upper()
            if not text:
                raise ValuationQueryError(
                    "valuation_offline_invalid_identity",
                    "估值行 Symbol 为空，拒绝补成 requested_symbol",
                )
            if not SYMBOL_RE.match(text):
                raise ValuationQueryError(
                    "valuation_offline_invalid_identity",
                    f"估值行 Symbol 非法: {raw}",
                )
            if text != requested_symbol:
                raise ValuationQueryError(
                    "valuation_offline_invalid_identity",
                    f"估值行 Symbol 与请求/文件不一致: {text} != {requested_symbol}",
                )
            mapped[dest_name] = text
            continue
        if dest_name == "date":
            mapped[dest_name] = _as_date(raw).isoformat()
            continue
        if kind:
            flags[dest_name] = kind
            mapped[dest_name] = None
        else:
            mapped[dest_name] = jsonable(raw)
    if flags:
        mapped["value_flags"] = flags
    return mapped


def query_valuation(
    *,
    symbol: str,
    start: date | str | None = None,
    end: date | str | None = None,
    limit: int = DEFAULT_LIMIT,
    root: Path | str | None = DEFAULT_ROOT,
) -> dict[str, Any]:
    canonical = normalize_symbol(symbol)
    start_date = parse_date(start, field="start")
    end_date = parse_date(end, field="end")
    if start_date and end_date and start_date > end_date:
        raise ValuationQueryError(
            "valuation_offline_invalid_date",
            "start 不能晚于 end",
        )
    bounded = parse_limit(limit)
    path = resolve_valuation_path(root, canonical)
    if not path.is_file():
        raise ValuationQueryError(
            "valuation_offline_not_found",
            f"估值文件不存在: {canonical}",
        )
    frame = read_valuation_frame(path)
    _require_schema(frame)
    _require_identity(frame, requested_symbol=canonical)
    duplicates = _duplicate_keys(frame)
    if duplicates:
        raise ValuationQueryError(
            "valuation_offline_duplicate_key",
            f"重复 symbol+date: {duplicates[0]['symbol']} {duplicates[0]['date']}",
        )
    quality = _quality_scan(frame, requested_symbol=canonical)
    fields = _field_report(frame)
    window = frame
    try:
        if start_date is not None:
            window = window.filter(_date_expr("time") >= start_date)
        if end_date is not None:
            window = window.filter(_date_expr("time") <= end_date)
    except ValuationQueryError:
        raise
    except Exception as exc:  # noqa: BLE001 — avoid .dt.date traceback
        raise ValuationQueryError(
            "valuation_offline_invalid_schema",
            "time 无法按日期过滤",
        ) from exc
    window = window.sort(["time", "Symbol"], descending=[True, False]).head(bounded)
    rows = [
        _map_row(row, requested_symbol=canonical) for row in window.iter_rows(named=True)
    ]
    status = "ok" if rows else "empty"
    if status == "empty":
        payload = _envelope(
            status="empty",
            code="valuation_offline_empty_window",
            symbol=canonical,
            start=start_date,
            end=end_date,
            limit=bounded,
            path=path,
            quality=quality,
            fields=fields,
            data=[],
            count=0,
            message="窗口内无估值记录",
        )
        return payload
    return _envelope(
        status="ok",
        symbol=canonical,
        start=start_date,
        end=end_date,
        limit=bounded,
        path=path,
        quality=quality,
        fields=fields,
        data=rows,
        count=len(rows),
    )


def _envelope(
    *,
    status: str,
    symbol: str,
    start: date | None,
    end: date | None,
    limit: int,
    path: Path,
    quality: dict[str, Any],
    fields: dict[str, Any],
    data: list[dict[str, Any]],
    count: int,
    code: str | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": status == "ok",
        "status": status,
        "source": SOURCE,
        "dataset": DATASET,
        "layout": LAYOUT,
        "symbol": symbol,
        "date": {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        },
        "limit": limit,
        "count": count,
        "as_of": quality.get("max_date"),
        "coverage": {
            "file_rows": quality.get("row_count"),
            "file_min_date": quality.get("min_date"),
            "file_max_date": quality.get("max_date"),
            "as_of": quality.get("max_date"),
            "historical_inventory": HISTORICAL_INVENTORY,
        },
        "fields": fields,
        "missing_fields": list(fields.get("missing_versus_project") or MISSING_VERSUS_PROJECT_V2),
        "optional_absent": list(fields.get("optional_absent") or []),
        "quality": quality,
        "unit_note": UNIT_NOTE,
        "overlay": OVERLAY_CONTRACT,
        "source_file": fingerprint(path),
        "data": data,
    }
    if code:
        payload["code"] = code
    if message:
        payload["message"] = message
    return jsonable(payload)


def error_payload(exc: ValuationQueryError, **extra: Any) -> dict[str, Any]:
    payload = {
        "ok": False,
        "status": "error",
        "code": exc.code,
        "error": exc.message,
        "source": SOURCE,
        "dataset": DATASET,
        "layout": LAYOUT,
        "overlay": OVERLAY_CONTRACT,
    }
    payload.update(extra)
    return jsonable(payload)


def _mv_identity(frame: pl.DataFrame) -> dict[str, Any]:
    schema = frame.schema
    checked = frame.filter(
        _finite_expr("close", schema["close"])
        & _finite_expr("total_capital", schema["total_capital"])
        & _finite_expr("total_mv", schema["total_mv"])
    )
    if checked.height == 0:
        return {
            "rule": "total_mv == close * total_capital; float_mv == close * circulating_capital",
            "checked_rows": 0,
            "max_abs_error": None,
            "exact_rows": 0,
            "float_checked_rows": 0,
            "float_max_abs_error": None,
            "conversion_applied": False,
            "units": "unknown/unverified",
            "identity_consistent_on_checked_rows": False,
            "inference": "unknown",
            "note": (
                "Identity consistency is recorded separately from units. "
                "It does not prove 股/元 versus 万股/万元 and is not a rewrite."
            ),
        }
    err = (checked["total_mv"] - checked["close"] * checked["total_capital"]).abs()
    float_checked = frame.filter(
        _finite_expr("close", schema["close"])
        & _finite_expr("circulating_capital", schema["circulating_capital"])
        & _finite_expr("float_mv", schema["float_mv"])
    )
    float_err = (
        (float_checked["float_mv"] - float_checked["close"] * float_checked["circulating_capital"]).abs()
        if float_checked.height
        else None
    )
    max_abs = float(err.max()) if checked.height else None
    exact_rows = int((err == 0).sum())
    return {
        "rule": "total_mv == close * total_capital; float_mv == close * circulating_capital",
        "checked_rows": checked.height,
        "max_abs_error": max_abs,
        "exact_rows": exact_rows,
        "float_checked_rows": float_checked.height,
        "float_max_abs_error": float(float_err.max()) if float_err is not None and float_checked.height else None,
        "conversion_applied": False,
        "units": "unknown/unverified",
        "identity_consistent_on_checked_rows": bool(
            checked.height and exact_rows == checked.height and max_abs == 0.0
        ),
        "inference": "unknown",
        "note": (
            "Identity consistency is recorded separately from units. "
            "It does not prove 股/元 versus 万股/万元 and is not a rewrite."
        ),
    }


def inspect_symbol(root: Path | str | None, symbol: str) -> dict[str, Any]:
    canonical = normalize_symbol(symbol)
    path = resolve_valuation_path(root, canonical)
    if not path.is_file():
        raise ValuationQueryError(
            "valuation_offline_not_found",
            f"估值文件不存在: {canonical}",
        )
    frame = read_valuation_frame(path)
    _require_schema(frame)
    _require_identity(frame, requested_symbol=canonical)
    duplicates = _duplicate_keys(frame)
    if duplicates:
        raise ValuationQueryError(
            "valuation_offline_duplicate_key",
            f"重复 symbol+date: {duplicates[0]['symbol']} {duplicates[0]['date']}",
        )
    quality = _quality_scan(frame, requested_symbol=canonical)
    fields = _field_report(frame)
    return jsonable(
        {
            "symbol": canonical,
            "source": SOURCE,
            "dataset": DATASET,
            "layout": LAYOUT,
            "source_file": fingerprint(path),
            "schema": [frame.columns, [str(dtype) for dtype in frame.dtypes]],
            "columns": frame.columns,
            "dtypes": {name: str(dtype) for name, dtype in zip(frame.columns, frame.dtypes)},
            "fields": fields,
            "quality": quality,
            "share_market_value": _mv_identity(frame),
            "unit_note": UNIT_NOTE,
            "overlay": OVERLAY_CONTRACT,
        }
    )


def _load_project_overlap(
    project_data_dir: Path,
    symbols: tuple[str, ...],
    start: date,
    end: date,
) -> pl.DataFrame:
    root = Path(project_data_dir) / PROJECT_VALUATION_RELATIVE
    if not root.exists():
        return pl.DataFrame()
    frames: list[pl.DataFrame] = []
    for part in sorted(root.glob("date=*/part.parquet")):
        day_name = part.parent.name
        if not day_name.startswith("date="):
            continue
        day = date.fromisoformat(day_name.split("=", 1)[1])
        if day < start or day > end:
            continue
        frame = pl.read_parquet(part)
        if "symbol" not in frame.columns:
            continue
        selected = frame.filter(pl.col("symbol").is_in(list(symbols)))
        if selected.height:
            frames.append(selected)
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def reconcile_project(
    *,
    root: Path | str | None,
    project_data_dir: Path | str | None,
    symbols: tuple[str, ...] = FIXED_SAMPLES,
    start: date | str | None = OVERLAP_START,
    end: date | str | None = OVERLAP_END,
) -> dict[str, Any]:
    start_date = parse_date(start, field="start") or OVERLAP_START
    end_date = parse_date(end, field="end") or OVERLAP_END
    package_rows: list[dict[str, Any]] = []
    for symbol in symbols:
        path = resolve_valuation_path(root, symbol)
        frame = read_valuation_frame(path)
        _require_schema(frame)
        _require_identity(frame, requested_symbol=normalize_symbol(symbol))
        duplicates = _duplicate_keys(frame)
        if duplicates:
            raise ValuationQueryError(
                "valuation_offline_duplicate_key",
                f"重复 symbol+date: {duplicates[0]['symbol']} {duplicates[0]['date']}",
            )
        try:
            window = frame.filter(
                (_date_expr("time") >= start_date) & (_date_expr("time") <= end_date)
            )
        except ValuationQueryError:
            raise
        except Exception as exc:  # noqa: BLE001 — avoid .dt.date traceback
            raise ValuationQueryError(
                "valuation_offline_invalid_schema",
                "time 无法按日期过滤",
            ) from exc
        for row in window.iter_rows(named=True):
            package_rows.append(
                {
                    "symbol": str(row["Symbol"]).upper(),
                    "date": _as_date(row["time"]).isoformat(),
                    "close": row.get("close"),
                    "pe_ttm": row.get("pe_ttm"),
                    "pb": row.get("pb"),
                    "ps_ttm": row.get("ps_ttm"),
                    "total_mv": row.get("total_mv"),
                    "float_mv": row.get("float_mv"),
                    "total_share": row.get("total_capital"),
                    "float_share": row.get("circulating_capital"),
                }
            )
    project = _load_project_overlap(Path(project_data_dir or DEFAULT_PROJECT_DATA_DIR), symbols, start_date, end_date)
    project_rows: list[dict[str, Any]] = []
    for row in project.iter_rows(named=True) if project.height else []:
        project_rows.append(
            {
                "symbol": str(row.get("symbol") or "").upper(),
                "date": _as_date(row.get("trade_date")).isoformat(),
                "close": row.get("close"),
                "pe_ttm": row.get("pe_ttm"),
                "pb": row.get("pb"),
                "ps_ttm": row.get("ps_ttm"),
                "total_mv": row.get("total_mv"),
                "float_mv": row.get("float_mv"),
                "total_share": row.get("total_share"),
                "float_share": row.get("float_share"),
                "shares_pit_safe": row.get("shares_pit_safe"),
                "unit_version": row.get("unit_version"),
            }
        )
    package_keys = {(row["symbol"], row["date"]) for row in package_rows}
    project_keys = {(row["symbol"], row["date"]) for row in project_rows}
    common = sorted(package_keys & project_keys)
    package_only = sorted(package_keys - project_keys)
    project_only = sorted(project_keys - package_keys)
    package_by_key = {(row["symbol"], row["date"]): row for row in package_rows}
    project_by_key = {(row["symbol"], row["date"]): row for row in project_rows}

    def _present(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, float) and math.isnan(value):
            return False
        return True

    comparable = ("close", "pe_ttm", "pb", "ps_ttm", "total_mv", "float_mv", "total_share", "float_share")
    field_stats: dict[str, dict[str, Any]] = {}
    for field in comparable:
        both = 0
        equal = 0
        differ = 0
        package_only_value = 0
        project_only_value = 0
        both_null = 0
        examples: list[dict[str, Any]] = []
        for key in common:
            left = package_by_key[key][field]
            right = project_by_key[key][field]
            left_ok = _present(left)
            right_ok = _present(right)
            if left_ok and right_ok:
                both += 1
                same = left == right
                if isinstance(left, float) and isinstance(right, float):
                    same = math.isclose(left, right, rel_tol=0.0, abs_tol=0.0)
                if same:
                    equal += 1
                else:
                    differ += 1
                    if len(examples) < 8:
                        examples.append(
                            {
                                "symbol": key[0],
                                "date": key[1],
                                "package": jsonable(left),
                                "project": jsonable(right),
                            }
                        )
            elif left_ok and not right_ok:
                package_only_value += 1
            elif right_ok and not left_ok:
                project_only_value += 1
            else:
                both_null += 1
        field_stats[field] = {
            "both_present": both,
            "equal_when_both_present": equal,
            "differ_when_both_present": differ,
            "package_present_project_null": package_only_value,
            "project_present_package_null": project_only_value,
            "both_null": both_null,
            "null_equals_value": False,
            "null_filled_with_zero": False,
            "examples": examples,
        }

    return jsonable(
        {
            "window": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "symbols": list(symbols),
            "package_keys": len(package_keys),
            "project_keys": len(project_keys),
            "common_keys": len(common),
            "package_only_keys": [
                {"symbol": symbol, "date": day} for symbol, day in package_only
            ],
            "project_only_keys": [
                {"symbol": symbol, "date": day} for symbol, day in project_only
            ],
            "project_null_policy": (
                "valuation_daily_v2 PE/PB/PS/PCF stay null without an admitted "
                "historical feed; market value is close * PIT-safe shares only. "
                "Observed project rows for these four symbols have pe/pb/ps/mv/"
                "shares null and shares_pit_safe=false. Null is not equal to a "
                "package value and is not filled with 0. Project null is not "
                "overlaid onto the package."
            ),
            "comparable_fields": field_stats,
            "unit_evidence": {
                "close": (
                    "Project close is raw unadjusted close in CNY. Package close "
                    "matched project close on every common key in this sample; "
                    "still not a claim of market truth."
                ),
                "shares_and_mv": (
                    "Package total_mv == close * total_capital on finite checked "
                    "sample rows is identity consistency only. Units remain "
                    "unknown/unverified and are not rewritten. Identity does not "
                    "prove 股/元 versus 万股/万元. Project total_share/total_mv "
                    "were null here, so they are not directly joinable. "
                    "Daily-bar amount×10000 is not used."
                ),
                "ratios": (
                    "Package PE/PB/PS are present on the overlap window; project "
                    "ratios are null by design. Do not treat two-source presence "
                    "as PIT acceptance."
                ),
            },
            "join_boundary": {
                "side_by_side_only": True,
                "direct_concat": False,
                "two_source_agreement_is_market_truth": False,
                "pit_verified": False,
            },
            "overlay": OVERLAY_CONTRACT,
            "sample_originals": {
                "package": [package_by_key[key] for key in common[:4]],
                "project": [project_by_key[key] for key in common[:4]],
            },
        }
    )


def audit_valuation(
    *,
    root: Path | str | None = DEFAULT_ROOT,
    project_data_dir: Path | str | None = DEFAULT_PROJECT_DATA_DIR,
    symbols: tuple[str, ...] = FIXED_SAMPLES,
) -> dict[str, Any]:
    samples = [inspect_symbol(root, symbol) for symbol in symbols]
    return jsonable(
        {
            "ok": True,
            "status": "ok",
            "mode": "audit",
            "source": SOURCE,
            "dataset": DATASET,
            "layout": LAYOUT,
            "symbols": list(symbols),
            "historical_inventory": HISTORICAL_INVENTORY,
            "samples": samples,
            "reconcile": reconcile_project(
                root=root,
                project_data_dir=project_data_dir,
                symbols=symbols,
            ),
            "overlay": OVERLAY_CONTRACT,
            "unit_note": UNIT_NOTE,
        }
    )


def summarize_audit(audit: dict[str, Any]) -> dict[str, Any]:
    sample_summaries = []
    for sample in audit.get("samples", []):
        quality = sample.get("quality") or {}
        sample_summaries.append(
            {
                "symbol": sample.get("symbol"),
                "rows": quality.get("row_count"),
                "min_date": quality.get("min_date"),
                "max_date": quality.get("max_date"),
                "negative_pe_ttm": quality.get("negative_pe_ttm"),
                "non_finite_counts": quality.get("non_finite_counts"),
                "share_market_value": sample.get("share_market_value"),
            }
        )
    reconcile = audit.get("reconcile") or {}
    return jsonable(
        {
            "ok": True,
            "status": "ok",
            "mode": "summary",
            "source": SOURCE,
            "dataset": DATASET,
            "layout": LAYOUT,
            "historical_inventory": HISTORICAL_INVENTORY,
            "samples": sample_summaries,
            "common_keys": reconcile.get("common_keys"),
            "package_keys": reconcile.get("package_keys"),
            "project_keys": reconcile.get("project_keys"),
            "join_boundary": reconcile.get("join_boundary"),
            "overlay": OVERLAY_CONTRACT,
        }
    )


def _assert_evidence_dir(path: Path | str) -> Path:
    allowed = ALLOWED_EVIDENCE_DIR.resolve()
    resolved = Path(path).expanduser().resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as exc:
        raise ValuationQueryError(
            "valuation_offline_evidence_path_denied",
            f"详细证据只能写到 {allowed}",
        ) from exc
    return resolved


def write_evidence(directory: Path | str, payload: dict[str, Any]) -> dict[str, str]:
    dest = _assert_evidence_dir(directory)
    dest.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    files = {
        "sample_audit.json": payload.get("audit") or payload,
        "overlap_reconcile.json": (payload.get("audit") or payload).get("reconcile")
        or {},
        "summary.json": payload.get("summary") or summarize_audit(payload.get("audit") or payload),
        "usage_examples.json": payload.get("examples") or {},
        "input_hashes.json": payload.get("input_hashes") or {},
    }
    for name, content in files.items():
        path = dest / name
        path.write_text(dumps(content) + "\n", encoding="utf-8")
        written[name] = str(path)
    return written


def collect_input_hashes(
    *,
    root: Path | str | None,
    project_data_dir: Path | str | None,
    symbols: tuple[str, ...] = FIXED_SAMPLES,
) -> dict[str, Any]:
    files = [
        Path("/Users/simon/Trading/下载数据/stockdb_quantdb_bundle_audit_20260905/read.sql"),
        Path("/Users/simon/Trading/下载数据/stockdb_quantdb_bundle_audit_20260905/package_manifest.json"),
        Path("/Users/simon/Trading/下载数据/stockdb_repair_20260905/read.sql"),
        Path("/Users/simon/Trading/下载数据/stockdb_repair_20260905/read_preclose.sql"),
        Path("/Users/simon/Trading/下载数据/stockdb_quantdb_integration_review_20260906/README.md"),
    ]
    resolved_root = resolve_root(root)
    for symbol in symbols:
        files.append(resolve_valuation_path(resolved_root, symbol))
    project_root = Path(project_data_dir or DEFAULT_PROJECT_DATA_DIR) / PROJECT_VALUATION_RELATIVE
    if project_root.exists():
        for part in sorted(project_root.glob("date=*/part.parquet")):
            day = date.fromisoformat(part.parent.name.split("=", 1)[1])
            if OVERLAP_START <= day <= OVERLAP_END:
                files.append(part)
    return {
        "captured_at_note": "mtime/size/sha only; files are not rewritten by this reader",
        "files": [fingerprint(path) for path in files],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only QuantDB valuation query")
    parser.add_argument("--symbol")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--limit", default=DEFAULT_LIMIT)
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--project-data-dir", default=str(DEFAULT_PROJECT_DATA_DIR))
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument(
        "--write-evidence",
        metavar="DIR",
        help=f"only {ALLOWED_EVIDENCE_DIR} is accepted",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.audit or args.summary:
            audit = audit_valuation(root=args.root, project_data_dir=args.project_data_dir)
            summary = summarize_audit(audit)
            payload = summary if args.summary and not args.audit else audit
            if args.summary and args.audit:
                payload = {"audit": audit, "summary": summary}
            if args.write_evidence:
                examples = {
                    "query": [
                        "backend/.venv/bin/python -B scripts/offline_valuation_query.py "
                        "--symbol 000001.SZ --start 2026-07-21 --end 2026-08-12 --limit 5",
                        "backend/.venv/bin/python -B scripts/offline_valuation_query.py --audit --summary",
                    ],
                    "note": "Default --audit/--summary is stdout only and writes no files.",
                }
                bundle = {
                    "audit": audit,
                    "summary": summary,
                    "examples": examples,
                    "input_hashes": collect_input_hashes(
                        root=args.root,
                        project_data_dir=args.project_data_dir,
                    ),
                }
                write_evidence(args.write_evidence, bundle)
            print(dumps(payload if not (args.audit and args.summary) else {"audit": audit, "summary": summary}))
            return 0
        if not args.symbol:
            raise ValuationQueryError(
                "valuation_offline_invalid_symbol",
                "查询模式必须提供 --symbol",
            )
        result = query_valuation(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            limit=args.limit,
            root=args.root,
        )
        print(dumps(result))
        return 0 if result.get("status") in {"ok", "empty"} else 2
    except ValuationQueryError as exc:
        print(dumps(error_payload(exc, symbol=args.symbol)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
