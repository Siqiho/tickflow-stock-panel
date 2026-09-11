#!/usr/bin/env python3
"""Build a secret-free, checksummed one-trading server data bundle.

The bundle deliberately contains only release-compatible datasets that cannot
be reconstructed cheaply by the current server pipeline. Large stock/index
history stays out of this bundle and is backfilled by the server itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pyarrow.parquet as pq


@dataclass(frozen=True)
class Selection:
    dataset_id: str
    pattern: str
    lineage_required: bool = False


SELECTIONS = (
    Selection("stock_adj_factor", "adj_factor/all.parquet", True),
    Selection("financial_balance_sheet", "financials/balance_sheet/part.parquet", True),
    Selection("financial_cash_flow", "financials/cash_flow/part.parquet", True),
    Selection("financial_income", "financials/income/part.parquet", True),
    Selection("financial_metrics", "financials/metrics/part.parquet", True),
    Selection("trading_calendar", "reference/trading_calendar/calendar.parquet"),
    Selection("pools", "pools/**/*.parquet"),
    Selection("ext_data", "ext_data/**/*.parquet"),
    Selection("stock_margin_trading", "f10/stock_margin_trading/part.parquet", True),
    Selection("stock_minute", "kline_minute/**/*.parquet", True),
)

LINEAGE_IDS = {
    "stock_adj_factor": ("stock_adj_factor",),
    "financial_balance_sheet": ("financial_balance_sheet",),
    "financial_cash_flow": ("financial_cash_flow",),
    "financial_income": ("financial_income",),
    "financial_metrics": ("financial_metrics",),
    "trading_calendar": ("trading_calendar",),
    "stock_margin_trading": ("stock_margin_trading",),
    "stock_minute": ("kline_minute", "stock_minute"),
}

FORBIDDEN_PARTS = {
    "user_data",
    "control",
    "job_store",
    "logs",
    "quote_snapshot",
    "sealed_l1",
    "depth5",
    "ai_cache",
    "backtest_results",
    "screener_results",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-data", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--release-sha", required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_file(path: Path, root: Path) -> PurePosixPath:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"not a regular file: {path}")
    resolved = path.resolve(strict=True)
    try:
        relative = PurePosixPath(resolved.relative_to(root).as_posix())
    except ValueError as error:
        raise ValueError(f"file escapes source data root: {path}") from error
    if FORBIDDEN_PARTS.intersection(relative.parts):
        raise ValueError(f"forbidden path selected: {relative}")
    return relative


def canonical_artifact(value: object, source_root: Path) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value.strip())
    if path.is_absolute():
        try:
            return path.resolve(strict=False).relative_to(source_root).as_posix()
        except ValueError:
            return None
    normalized = PurePosixPath(value.strip()).as_posix().lstrip("./")
    if normalized.startswith("data/"):
        normalized = normalized[5:]
    return normalized


def parquet_record(path: Path, relative: PurePosixPath, dataset_id: str) -> dict:
    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    return {
        "dataset_id": dataset_id,
        "path": relative.as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "rows": parquet.metadata.num_rows,
        "schema": [{"name": field.name, "type": str(field.type)} for field in schema],
    }


def copy_selected(
    source_root: Path, stage_data: Path
) -> tuple[list[dict], dict[str, set[str]]]:
    records: list[dict] = []
    selected_by_dataset: dict[str, set[str]] = {}
    for selection in SELECTIONS:
        files = sorted(source_root.glob(selection.pattern))
        if not files:
            raise FileNotFoundError(
                f"selection {selection.dataset_id} matched no files: {selection.pattern}"
            )
        selected_by_dataset[selection.dataset_id] = set()
        for source in files:
            relative = relative_file(source, source_root)
            destination = stage_data.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            record = parquet_record(destination, relative, selection.dataset_id)
            records.append(record)
            selected_by_dataset[selection.dataset_id].add(relative.as_posix())
    return records, selected_by_dataset


def copy_matching_lineage(
    source_root: Path,
    stage_data: Path,
    selected_by_dataset: dict[str, set[str]],
) -> tuple[list[dict], dict[str, set[str]]]:
    records: list[dict] = []
    matched: dict[str, set[str]] = {
        dataset_id: set() for dataset_id in selected_by_dataset
    }
    for dataset_id, artifact_paths in selected_by_dataset.items():
        for lineage_id in LINEAGE_IDS.get(dataset_id, ()):
            lineage_root = source_root / "lineage" / lineage_id
            if not lineage_root.exists():
                continue
            for source in sorted(lineage_root.rglob("*.json")):
                relative = relative_file(source, source_root)
                payload = json.loads(source.read_text(encoding="utf-8"))
                target = canonical_artifact(
                    payload.get("target_artifact")
                    or payload.get("artifact_path")
                    or payload.get("artifact"),
                    source_root,
                )
                if target not in artifact_paths:
                    continue
                if (
                    not isinstance(payload.get("source"), str)
                    or not payload["source"].strip()
                ):
                    raise ValueError(f"lineage source missing: {relative}")
                if (
                    not isinstance(payload.get("unit_version"), str)
                    or not payload["unit_version"].strip()
                ):
                    raise ValueError(f"lineage unit_version missing: {relative}")
                destination = stage_data.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                records.append(
                    {
                        "dataset_id": dataset_id,
                        "path": relative.as_posix(),
                        "target_artifact": target,
                        "bytes": destination.stat().st_size,
                        "sha256": sha256(destination),
                    }
                )
                matched[dataset_id].add(target)
    return records, matched


def assert_required_lineage(
    selected_by_dataset: dict[str, set[str]], matched: dict[str, set[str]]
) -> None:
    required = {
        selection.dataset_id for selection in SELECTIONS if selection.lineage_required
    }
    errors: list[str] = []
    for dataset_id in sorted(required):
        missing = sorted(
            selected_by_dataset[dataset_id] - matched.get(dataset_id, set())
        )
        if missing:
            errors.append(
                f"{dataset_id}: missing matching lineage for {', '.join(missing)}"
            )
    if errors:
        raise ValueError("; ".join(errors))


def verify_archive_members(archive: Path) -> None:
    zstd = subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE)
    assert zstd.stdout is not None
    listing = subprocess.run(
        ["tar", "-tf", "-"],
        stdin=zstd.stdout,
        capture_output=True,
        text=True,
        check=False,
    )
    zstd.stdout.close()
    zstd_code = zstd.wait()
    if zstd_code != 0 or listing.returncode != 0:
        raise RuntimeError(
            f"archive listing failed: zstd={zstd_code}, tar={listing.returncode}"
        )
    unsafe: list[str] = []
    for member in listing.stdout.splitlines():
        path = PurePosixPath(member)
        if (
            path.is_absolute()
            or ".." in path.parts
            or any(part.startswith("._") or part == ".DS_Store" for part in path.parts)
        ):
            unsafe.append(member)
    if unsafe:
        raise ValueError(f"unsafe archive members: {', '.join(unsafe[:20])}")


def write_archive(output_dir: Path, stage_root: Path) -> tuple[Path, str]:
    archive = output_dir / "one-trading-server-data.tar.zst"
    environment = os.environ.copy()
    # macOS bsdtar otherwise emits AppleDouble `._*` members for xattrs. Those
    # look like corrupt Parquet/JSON files to Linux scanners.
    environment["COPYFILE_DISABLE"] = "1"
    tar = subprocess.Popen(
        [
            "tar",
            "--no-xattrs",
            "-C",
            str(stage_root),
            "-cf",
            "-",
            "data",
            "manifest.json",
        ],
        stdout=subprocess.PIPE,
        env=environment,
    )
    assert tar.stdout is not None
    zstd = subprocess.run(
        ["zstd", "-T0", "-10", "-q", "-o", str(archive)],
        stdin=tar.stdout,
        check=False,
    )
    tar.stdout.close()
    tar_code = tar.wait()
    if tar_code != 0 or zstd.returncode != 0:
        raise RuntimeError(
            f"archive creation failed: tar={tar_code}, zstd={zstd.returncode}"
        )
    os.chmod(archive, 0o600)
    verify_archive_members(archive)
    digest = sha256(archive)
    checksum = output_dir / f"{archive.name}.sha256"
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    os.chmod(checksum, 0o600)
    return archive, digest


def main() -> int:
    args = parse_args()
    source_root = args.source_data.resolve(strict=True)
    output_dir = args.output_dir.resolve(strict=False)
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True, mode=0o700)
    stage_root = output_dir / "stage"
    stage_data = stage_root / "data"
    stage_data.mkdir(parents=True)

    parquet_records, selected = copy_selected(source_root, stage_data)
    lineage_records, matched = copy_matching_lineage(source_root, stage_data, selected)
    assert_required_lineage(selected, matched)

    manifest = {
        "format_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source": "one-trading-development-data",
        "release_sha": args.release_sha,
        "policy": {
            "large_history": "server_backfill",
            "derived_stock_enriched": "server_rebuild",
            "control_database": "never_migrate",
            "secrets_and_user_data": "never_migrate",
        },
        "parquet_files": sorted(parquet_records, key=lambda item: item["path"]),
        "lineage_files": sorted(lineage_records, key=lambda item: item["path"]),
    }
    manifest_path = stage_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.chmod(manifest_path, 0o600)

    archive, archive_sha = write_archive(output_dir, stage_root)
    summary = {
        "archive": str(archive),
        "archive_sha256": archive_sha,
        "parquet_files": len(parquet_records),
        "lineage_files": len(lineage_records),
        "parquet_bytes": sum(item["bytes"] for item in parquet_records),
        "parquet_rows": sum(item["rows"] for item in parquet_records),
        "datasets": sorted(selected),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
