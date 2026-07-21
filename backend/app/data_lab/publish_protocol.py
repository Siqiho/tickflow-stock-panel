"""M5.1 universal staging → quality → atomic publish protocol.

Lab-safe: every call requires an explicit data_dir. Never imports settings.data_dir
as a default sink.
"""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from app.services.atomic_io import atomic_write_json, atomic_write_parquet, write_lineage_record

from .quality_reference import CheckResult, quality_passed, run_quality_checks
from .schemas_reference import ReferenceDatasetSchema, get_reference_schema

NormalizeFn = Callable[[pl.DataFrame], pl.DataFrame]


@dataclass(frozen=True)
class PublishRequest:
    dataset_id: str
    data_dir: Path
    frame: pl.DataFrame
    source: str
    run_id: str | None = None
    as_of: date | None = None
    normalize: NormalizeFn | None = None
    allow_status_flip: bool = False
    write_lineage: bool = True
    cleanup_staging_on_success: bool = True


@dataclass(frozen=True)
class PublishResult:
    ok: bool
    dataset_id: str
    run_id: str
    published_path: str | None
    row_count: int
    quality_report_path: str | None
    lineage_path: str | None
    kept_prior: bool
    error: str | None = None
    checks: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    staging_dir: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "dataset_id": self.dataset_id,
            "run_id": self.run_id,
            "published_path": self.published_path,
            "row_count": self.row_count,
            "quality_report_path": self.quality_report_path,
            "lineage_path": self.lineage_path,
            "kept_prior": self.kept_prior,
            "error": self.error,
            "checks": list(self.checks),
            "staging_dir": self.staging_dir,
        }


def staging_root(data_dir: Path, dataset_id: str, run_id: str) -> Path:
    return Path(data_dir) / ".staging" / dataset_id / run_id


def formal_path(data_dir: Path, schema: ReferenceDatasetSchema) -> Path:
    return Path(data_dir) / schema.formal_relpath


def _default_normalize(schema: ReferenceDatasetSchema, frame: pl.DataFrame) -> pl.DataFrame:
    df = frame
    # ensure all required columns exist (nullable fillers for optional-ish fields)
    for col in schema.required_columns:
        if col not in df.columns:
            dtype = schema.dtypes.get(col, pl.Utf8)
            df = df.with_columns(pl.lit(None).cast(dtype).alias(col))
    # cast known dtypes
    casts: list[pl.Expr] = []
    for col, dtype in schema.dtypes.items():
        if col in df.columns:
            casts.append(pl.col(col).cast(dtype, strict=False).alias(col))
    if casts:
        df = df.with_columns(casts)
    # primary-key dedupe: keep last
    pk = list(schema.primary_key)
    sort_cols = pk + [c for c in ("as_of", "source") if c in df.columns and c not in pk]
    if pk and df.height:
        df = df.sort(sort_cols).unique(subset=pk, keep="last", maintain_order=True)
    # stable column order
    ordered = [c for c in schema.required_columns if c in df.columns]
    extra = [c for c in df.columns if c not in ordered]
    return df.select(ordered + extra)


def _overlap_conflicts(
    dataset_id: str,
    schema: ReferenceDatasetSchema,
    candidate: pl.DataFrame,
    prior: pl.DataFrame,
    *,
    allow_status_flip: bool,
) -> tuple[int, list[str]]:
    pk = list(schema.primary_key)
    if candidate.is_empty() or prior.is_empty():
        return 0, []
    # join on PK
    left = candidate.select(pk + [c for c in candidate.columns if c not in pk]).rename(
        {c: f"new__{c}" for c in candidate.columns if c not in pk}
    )
    right = prior.select(pk + [c for c in prior.columns if c not in pk]).rename(
        {c: f"old__{c}" for c in prior.columns if c not in pk}
    )
    joined = left.join(right, on=pk, how="inner")
    if joined.is_empty():
        return 0, []

    conflicts: list[str] = []
    if dataset_id == "trading_calendar" and not allow_status_flip:
        if "new__is_open" in joined.columns and "old__is_open" in joined.columns:
            bad = joined.filter(pl.col("new__is_open") != pl.col("old__is_open"))
            if bad.height:
                conflicts.append(f"is_open_flip={bad.height}")
    elif dataset_id == "instrument_status_history":
        # conflicting payload on same PK already implies status identity in PK;
        # flag reason/source flips only as soft — hard conflict if effective_to disagrees
        if "new__effective_to" in joined.columns and "old__effective_to" in joined.columns:
            bad = joined.filter(pl.col("new__effective_to") != pl.col("old__effective_to"))
            # null-safe: both null is ok
            bad = bad.filter(
                ~(pl.col("new__effective_to").is_null() & pl.col("old__effective_to").is_null())
            )
            if bad.height:
                conflicts.append(f"effective_to_conflict={bad.height}")
    else:
        # generic: any non-pk column disagreement
        new_cols = [c for c in joined.columns if c.startswith("new__")]
        for nc in new_cols:
            oc = "old__" + nc.removeprefix("new__")
            if oc not in joined.columns:
                continue
            bad = joined.filter(
                (pl.col(nc) != pl.col(oc))
                & ~(pl.col(nc).is_null() & pl.col(oc).is_null())
            )
            if bad.height:
                conflicts.append(f"{nc.removeprefix('new__')}={bad.height}")
                break
    return joined.height, conflicts


def _write_quality_report(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _prior_fingerprint(path: Path) -> tuple[bool, int | None, str | None]:
    if not path.exists():
        return False, None, None
    stat = path.stat()
    return True, stat.st_size, f"{stat.st_mtime_ns}:{stat.st_size}"


def publish_dataset(request: PublishRequest) -> PublishResult:
    """Run M5.1 protocol for one reference dataset frame."""
    data_dir = Path(request.data_dir)
    if not str(data_dir):
        raise ValueError("data_dir is required")

    schema = get_reference_schema(request.dataset_id)
    run_id = request.run_id or uuid.uuid4().hex
    as_of = request.as_of or date.today()
    stage = staging_root(data_dir, request.dataset_id, run_id)
    stage.mkdir(parents=True, exist_ok=True)

    target = formal_path(data_dir, schema)
    prior_exists, prior_size, prior_fp = _prior_fingerprint(target)

    meta = {
        "dataset_id": request.dataset_id,
        "run_id": run_id,
        "source": request.source,
        "as_of": as_of.isoformat(),
        "unit_version": schema.unit_version,
        "created_at": datetime.now().astimezone().isoformat(),
        "prior_exists": prior_exists,
    }
    atomic_write_json(meta, stage / "meta.json", indent=2)

    try:
        normalize = request.normalize or (lambda frame: _default_normalize(schema, frame))
        normalized = normalize(request.frame)
        needs_source = "source" in schema.required_columns and (
            "source" not in normalized.columns
            or normalized.filter(pl.col("source").is_null() | (pl.col("source") == "")).height
        )
        if needs_source:
            normalized = normalized.with_columns(pl.lit(request.source).alias("source"))
        if "as_of" in schema.required_columns and (
            "as_of" not in normalized.columns or normalized.get_column("as_of").null_count()
        ):
            normalized = normalized.with_columns(pl.lit(as_of).cast(pl.Date).alias("as_of"))
        normalized = _default_normalize(schema, normalized)

        atomic_write_parquet(normalized, stage / "normalized.parquet")

        checks = run_quality_checks(request.dataset_id, normalized)
        overlap_intersection = 0
        overlap_conflicts: list[str] = []
        if prior_exists:
            prior_df = pl.read_parquet(target)
            overlap_intersection, overlap_conflicts = _overlap_conflicts(
                request.dataset_id,
                schema,
                normalized,
                prior_df,
                allow_status_flip=request.allow_status_flip,
            )
            if overlap_conflicts:
                checks = [
                    *checks,
                    CheckResult(
                        "overlap_conflicts",
                        False,
                        ",".join(overlap_conflicts),
                    ),
                ]
            else:
                checks = [
                    *checks,
                    CheckResult(
                        "overlap_conflicts",
                        True,
                        f"intersection={overlap_intersection}",
                    ),
                ]

        passed = quality_passed(list(checks))
        report = {
            "dataset_id": request.dataset_id,
            "run_id": run_id,
            "row_count": normalized.height,
            "passed": passed,
            "checks": [c.as_dict() for c in checks],
            "overlap": {
                "prior_rows": int(prior_size or 0),
                "intersection": overlap_intersection,
                "conflicts": len(overlap_conflicts),
                "conflict_details": overlap_conflicts,
            },
            "unit_version": schema.unit_version,
        }
        report_path = stage / "quality_report.json"
        _write_quality_report(report_path, report)

        if not passed:
            return PublishResult(
                ok=False,
                dataset_id=request.dataset_id,
                run_id=run_id,
                published_path=str(target) if prior_exists else None,
                row_count=normalized.height,
                quality_report_path=str(report_path),
                lineage_path=None,
                kept_prior=prior_exists,
                error="quality_gates_failed",
                checks=tuple(report["checks"]),
                staging_dir=str(stage),
            )

        # Atomic publish
        atomic_write_parquet(normalized, target)
        new_exists, new_size, new_fp = _prior_fingerprint(target)
        if not new_exists or new_size == 0:
            raise RuntimeError("publish produced missing or empty formal artifact")

        lineage_path: str | None = None
        if request.write_lineage:
            lp = write_lineage_record(
                data_dir,
                request.dataset_id,
                {
                    "source": request.source,
                    "unit_version": schema.unit_version,
                    "date": as_of.isoformat(),
                    "dataset_id": request.dataset_id,
                    "row_count": normalized.height,
                    "artifact_path": str(Path(schema.formal_relpath)),
                    "run_id": run_id,
                },
                run_id=run_id,
            )
            lineage_path = str(lp)

        if request.cleanup_staging_on_success:
            # keep quality report by moving minimal breadcrumb? Spec says delete staging.
            shutil.rmtree(stage, ignore_errors=True)
            stage_out = None
        else:
            stage_out = str(stage)

        # prior fingerprint retained only for debugging identity; publish success
        _ = prior_fp, new_fp

        return PublishResult(
            ok=True,
            dataset_id=request.dataset_id,
            run_id=run_id,
            published_path=str(target),
            row_count=normalized.height,
            quality_report_path=str(report_path) if stage_out else None,
            lineage_path=lineage_path,
            kept_prior=False,
            error=None,
            checks=tuple(report["checks"]),
            staging_dir=stage_out,
        )
    except Exception as exc:
        # ensure prior untouched
        still_exists, still_size, still_fp = _prior_fingerprint(target)
        kept = False
        if prior_exists:
            kept = still_exists and still_fp == prior_fp and still_size == prior_size
        fail_report = {
            "dataset_id": request.dataset_id,
            "run_id": run_id,
            "row_count": int(getattr(request.frame, "height", 0) or 0),
            "passed": False,
            "checks": [{"code": "protocol_exception", "passed": False, "detail": str(exc)}],
            "unit_version": schema.unit_version,
        }
        report_path = stage / "quality_report.json"
        try:
            _write_quality_report(report_path, fail_report)
        except Exception:
            report_path = None  # type: ignore[assignment]
        return PublishResult(
            ok=False,
            dataset_id=request.dataset_id,
            run_id=run_id,
            published_path=str(target) if prior_exists else None,
            row_count=int(getattr(request.frame, "height", 0) or 0),
            quality_report_path=str(report_path) if report_path else None,
            lineage_path=None,
            kept_prior=kept if prior_exists else False,
            error=str(exc),
            checks=tuple(fail_report["checks"]),
            staging_dir=str(stage),
        )
