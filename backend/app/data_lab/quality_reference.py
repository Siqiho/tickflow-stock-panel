"""Dataset-specific quality gates for M5 batch-1 reference data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import polars as pl

from .schemas_reference import ReferenceDatasetSchema, get_reference_schema

_SYMBOL_RE = re.compile(r"^[0-9]{6}\.(SH|SZ|BJ)$")


@dataclass(frozen=True)
class CheckResult:
    code: str
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "passed": self.passed, "detail": self.detail}


def _check_not_empty(df: pl.DataFrame) -> CheckResult:
    ok = df.height > 0
    return CheckResult("not_empty", ok, f"{df.height} rows")


def _check_required_columns(df: pl.DataFrame, schema: ReferenceDatasetSchema) -> CheckResult:
    missing = [c for c in schema.required_columns if c not in df.columns]
    return CheckResult(
        "required_columns",
        not missing,
        "ok" if not missing else f"missing={missing}",
    )


def _check_pk_unique(df: pl.DataFrame, schema: ReferenceDatasetSchema) -> CheckResult:
    if df.height == 0:
        return CheckResult("pk_unique", False, "empty")
    missing = [c for c in schema.primary_key if c not in df.columns]
    if missing:
        return CheckResult("pk_unique", False, f"pk columns missing={missing}")
    n_unique = df.select(pl.struct(list(schema.primary_key)).n_unique()).item()
    ok = n_unique == df.height
    return CheckResult(
        "pk_unique",
        ok,
        f"unique={n_unique} rows={df.height}" if ok else f"duplicates={df.height - n_unique}",
    )


def _check_enums(df: pl.DataFrame, schema: ReferenceDatasetSchema) -> list[CheckResult]:
    results: list[CheckResult] = []
    for col, allowed in schema.enums.items():
        if col not in df.columns:
            results.append(CheckResult(f"enum:{col}", False, "column missing"))
            continue
        values = {
            str(v)
            for v in df.get_column(col).drop_nulls().unique().to_list()
        }
        bad = sorted(values - set(allowed))
        results.append(
            CheckResult(
                f"enum:{col}",
                not bad,
                "ok" if not bad else f"invalid={bad}",
            )
        )
    return results


def _check_calendar_session_consistency(df: pl.DataFrame) -> CheckResult:
    if not {"is_open", "session_type", "open_time", "close_time"}.issubset(df.columns):
        return CheckResult("calendar_session_consistency", False, "columns missing")
    open_bad = df.filter(
        pl.col("is_open")
        & (
            ~pl.col("session_type").is_in(["normal", "half_day", "special"])
            | pl.col("open_time").is_null()
            | pl.col("close_time").is_null()
            | (pl.col("open_time") == "")
            | (pl.col("close_time") == "")
        )
    )
    closed_bad = df.filter(
        (~pl.col("is_open"))
        & (~pl.col("session_type").is_in(["closed", "holiday", "special"]))
    )
    ok = open_bad.height == 0 and closed_bad.height == 0
    detail = (
        "ok"
        if ok
        else f"open_bad={open_bad.height} closed_bad={closed_bad.height}"
    )
    return CheckResult("calendar_session_consistency", ok, detail)


def _check_status_intervals(df: pl.DataFrame) -> CheckResult:
    if not {"effective_from", "effective_to"}.issubset(df.columns):
        return CheckResult("status_intervals", False, "columns missing")
    bad = df.filter(
        pl.col("effective_to").is_not_null()
        & (pl.col("effective_to") < pl.col("effective_from"))
    )
    return CheckResult(
        "status_intervals",
        bad.height == 0,
        "ok" if bad.height == 0 else f"inverted={bad.height}",
    )


def _check_symbols(df: pl.DataFrame, column: str = "symbol") -> CheckResult:
    if column not in df.columns:
        return CheckResult("symbol_pattern", False, f"{column} missing")
    values = [str(v) for v in df.get_column(column).drop_nulls().to_list()]
    bad = sorted({v for v in values if not _SYMBOL_RE.match(v)})
    return CheckResult(
        "symbol_pattern",
        not bad,
        "ok" if not bad else f"invalid_sample={bad[:5]} count={len(bad)}",
    )


def _check_listing_code_change(df: pl.DataFrame) -> CheckResult:
    if not {"event_type", "prior_symbol"}.issubset(df.columns):
        return CheckResult("listing_code_change", False, "columns missing")
    code_change_missing = df.filter(
        (pl.col("event_type") == "code_change")
        & (pl.col("prior_symbol").is_null() | (pl.col("prior_symbol") == ""))
    )
    list_with_prior = df.filter(
        (pl.col("event_type") == "list")
        & pl.col("prior_symbol").is_not_null()
        & (pl.col("prior_symbol") != "")
    )
    ok = code_change_missing.height == 0 and list_with_prior.height == 0
    return CheckResult(
        "listing_code_change",
        ok,
        "ok"
        if ok
        else (
            f"code_change_missing_prior={code_change_missing.height} "
            f"list_with_prior={list_with_prior.height}"
        ),
    )


def run_quality_checks(dataset_id: str, df: pl.DataFrame) -> list[CheckResult]:
    schema = get_reference_schema(dataset_id)
    checks = [
        _check_not_empty(df),
        _check_required_columns(df, schema),
        _check_pk_unique(df, schema),
        *_check_enums(df, schema),
    ]
    if dataset_id == "trading_calendar":
        checks.append(_check_calendar_session_consistency(df))
    elif dataset_id == "instrument_status_history":
        checks.extend([_check_status_intervals(df), _check_symbols(df)])
    elif dataset_id == "listing_delisting_events":
        checks.extend([_check_symbols(df), _check_listing_code_change(df)])
        if "exchange" in df.columns:
            # exchange may be null on some events; only validate non-null via enum check already
            pass
    return checks


def quality_passed(checks: list[CheckResult]) -> bool:
    return all(item.passed for item in checks)
