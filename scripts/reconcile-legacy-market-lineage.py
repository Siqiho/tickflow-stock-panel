#!/usr/bin/env python3
"""Add honest lineage sidecars for current market artifacts missing provenance.

The catalog scanner remains the authority for dataset ownership, schema checks,
artifact row counts, and the current-lineage selection contract.  This script
never rewrites Parquet files or existing lineage.  It adds a degraded
``legacy_local_artifact`` record only when the scanner cannot match the current
artifact version to the dataset's declared unit contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (REPO_ROOT / "backend", REPO_ROOT):
    # 本地仓库为 <repo>/backend/app; 服务器镜像为 /app/app
    if (_candidate / "app").is_dir():
        sys.path.insert(0, str(_candidate))
        break

from app.data_catalog.models import ArtifactRecord, LineageSummary  # noqa: E402
from app.data_catalog.scanner import CatalogScanner  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _current_by_artifact(
    scanner: CatalogScanner,
    artifacts: tuple[ArtifactRecord, ...],
    lineage: tuple[LineageSummary, ...],
) -> dict[str, LineageSummary]:
    return {
        item.artifact_path: item
        for item in scanner._current_artifact_lineage(artifacts, lineage)
        if item.artifact_path is not None
    }


def _partition(artifact_path: str) -> str:
    for part in Path(artifact_path).parts:
        if "=" in part:
            key, value = part.split("=", 1)
            if key and value:
                return part
    return "unpartitioned"


def _record_id(dataset_id: str, artifact: ArtifactRecord, unit_version: str) -> str:
    identity = f"{dataset_id}\0{artifact.path}\0{artifact.row_count}\0{unit_version}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _assert_artifact_unchanged(data_dir: Path, artifact: ArtifactRecord) -> None:
    path = data_dir / artifact.path
    metadata = pq.read_metadata(path)
    if metadata.num_rows != artifact.row_count or sha256(path) != artifact.sha256:
        raise RuntimeError(f"artifact changed during reconciliation: {artifact.path}")


def reconcile(data_dir: Path, *, apply: bool) -> dict[str, object]:
    data_dir = data_dir.resolve(strict=True)
    scanner = CatalogScanner(data_dir)
    planned: list[dict[str, object]] = []
    written: list[str] = []
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    for definition in scanner.definitions:
        if definition.unit_policy == "reference":
            continue
        dataset_id = definition.descriptor.dataset_id
        unit_version = definition.descriptor.unit_version
        result = scanner.scan_dataset(dataset_id, f"legacy-lineage-audit-{dataset_id}")
        unexpected_errors = [
            error
            for error in result.state.payload.get("scan_errors", [])
            if "matching lineage is missing" not in error
            and "unit_version mismatch" not in error
        ]
        if unexpected_errors:
            raise RuntimeError(
                f"{dataset_id} has non-lineage scan errors: {'; '.join(unexpected_errors)}"
            )
        current = _current_by_artifact(scanner, result.artifacts, result.lineage)

        for artifact in result.artifacts:
            selected = current.get(artifact.path)
            if selected is not None and selected.unit_version == unit_version:
                continue
            record_id = _record_id(dataset_id, artifact, unit_version)
            destination = (
                data_dir
                / "lineage"
                / dataset_id
                / _partition(artifact.path)
                / f"legacy-{record_id}.json"
            )
            payload = {
                "run_id": f"legacy-lineage-reconcile-{record_id}",
                "dataset_id": dataset_id,
                "source": "legacy_local_artifact",
                "unit_version": unit_version,
                "quality_status": "degraded",
                "row_count": artifact.row_count,
                "target_artifact": artifact.path,
                "artifact_sha256": artifact.sha256,
                "artifact_published_at": artifact.published_at,
                "fetched_at": now,
                "reconciliation": (
                    "Original producer lineage was not captured for the current artifact version; "
                    "the scanner-admitted path, unit contract, row count, digest, and file time "
                    "were reconciled without rewriting the artifact."
                ),
            }
            planned.append(
                {
                    "dataset_id": dataset_id,
                    "target_artifact": artifact.path,
                    "destination": destination.relative_to(data_dir).as_posix(),
                    "rows": artifact.row_count,
                    "unit_version": unit_version,
                }
            )
            if not apply:
                continue
            _assert_artifact_unchanged(data_dir, artifact)
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            descriptor = os.open(destination, flags, 0o600)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    descriptor = -1
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            written.append(destination.relative_to(data_dir).as_posix())

    counts = Counter(str(item["dataset_id"]) for item in planned)
    return {
        "apply": apply,
        "planned": len(planned),
        "written": len(written),
        "by_dataset_id": dict(sorted(counts.items())),
        "sample": planned[:10],
    }


def main() -> int:
    args = parse_args()
    print(json.dumps(reconcile(args.data_dir, apply=args.apply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
