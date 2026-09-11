#!/usr/bin/env python3
"""Build a complete, secret-free shared-market-data bundle for Zeabur.

This is intentionally separate from ``build-server-data-bundle.py``.  The
older bundle is a small bootstrap set; this bundle is for an owner-authorized
full synchronization.  Only explicitly listed shared market datasets are
copied.  Identity, tenant workspaces, Hermes homes, secrets, jobs, logs, and
other user/runtime state can never enter the archive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pyarrow.parquet as pq


MARKET_DATA_DIRS = (
    "adj_factor",
    "adj_factor_etf",
    "depth5",
    "ext_data",
    "f10",
    "financials",
    "instruments",
    "instruments_etf",
    "instruments_ext",
    "instruments_index",
    "kline_daily",
    "kline_daily_enriched",
    "kline_etf_daily",
    "kline_etf_enriched",
    "kline_etf_minute",
    "kline_ext",
    "kline_index_daily",
    "kline_index_enriched",
    "kline_minute",
    "lineage",
    "market",
    "pools",
    "quote_snapshot",
    "reference",
    "sealed_l1",
)

FORBIDDEN_TOP_LEVEL = {
    ".staging",
    "ai_cache",
    "backtest_results",
    "control",
    "data_sources",
    "hermes",
    "job_store",
    "logs",
    "screener_results",
    "tenants",
    "user_data",
}

ALLOWED_SUFFIXES = {".json", ".parquet"}


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


def safe_relative_file(path: Path, source_root: Path) -> PurePosixPath:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"not a regular file: {path}")
    resolved = path.resolve(strict=True)
    try:
        relative = PurePosixPath(resolved.relative_to(source_root).as_posix())
    except ValueError as error:
        raise ValueError(f"file escapes source data root: {path}") from error
    if not relative.parts or relative.parts[0] not in MARKET_DATA_DIRS:
        raise ValueError(f"path is outside the market-data allowlist: {relative}")
    if FORBIDDEN_TOP_LEVEL.intersection(relative.parts):
        raise ValueError(f"forbidden path selected: {relative}")
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError(f"unsupported market-data file type: {relative}")
    return relative


def parquet_record(path: Path, relative: PurePosixPath) -> dict[str, object]:
    parquet = pq.ParquetFile(path)
    return {
        "path": relative.as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "rows": parquet.metadata.num_rows,
        "schema": [
            {"name": field.name, "type": str(field.type)}
            for field in parquet.schema_arrow
        ],
    }


def json_record(path: Path, relative: PurePosixPath) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": relative.as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "json_type": type(payload).__name__,
    }


def copy_market_data(
    source_root: Path,
    stage_data: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, dict[str, int]]]:
    parquet_records: list[dict[str, object]] = []
    json_records: list[dict[str, object]] = []
    datasets: dict[str, dict[str, int]] = {}

    for dataset in MARKET_DATA_DIRS:
        source_dir = source_root / dataset
        destination_dir = stage_data / dataset
        destination_dir.mkdir(parents=True, exist_ok=True)
        summary = {"files": 0, "bytes": 0, "parquet_rows": 0}
        datasets[dataset] = summary
        if not source_dir.exists():
            continue
        if source_dir.is_symlink() or not source_dir.is_dir():
            raise ValueError(f"market-data selection is not a directory: {source_dir}")

        for source in sorted(path for path in source_dir.rglob("*") if path.is_file()):
            relative = safe_relative_file(source, source_root)
            destination = stage_data.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if destination.suffix.lower() == ".parquet":
                record = parquet_record(destination, relative)
                parquet_records.append(record)
                summary["parquet_rows"] += int(record["rows"])
            else:
                record = json_record(destination, relative)
                json_records.append(record)
            summary["files"] += 1
            summary["bytes"] += int(record["bytes"])

    if not parquet_records:
        raise ValueError("market-data allowlist produced no Parquet files")
    return parquet_records, json_records, datasets


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
    forbidden: list[str] = []
    for member in listing.stdout.splitlines():
        path = PurePosixPath(member)
        if (
            path.is_absolute()
            or ".." in path.parts
            or any(part.startswith("._") or part == ".DS_Store" for part in path.parts)
        ):
            unsafe.append(member)
        if len(path.parts) >= 2 and path.parts[0] == "data":
            if path.parts[1] not in MARKET_DATA_DIRS:
                forbidden.append(member)
            if FORBIDDEN_TOP_LEVEL.intersection(path.parts):
                forbidden.append(member)
    if unsafe:
        raise ValueError(f"unsafe archive members: {', '.join(unsafe[:20])}")
    if forbidden:
        raise ValueError(f"forbidden archive members: {', '.join(forbidden[:20])}")


def write_archive(output_dir: Path, stage_root: Path) -> tuple[Path, str]:
    archive = output_dir / "one-trading-full-market-data.tar.zst"
    environment = os.environ.copy()
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
    if FORBIDDEN_TOP_LEVEL.intersection(MARKET_DATA_DIRS):
        raise AssertionError("market-data allowlist overlaps the forbidden list")

    output_dir.mkdir(parents=True, mode=0o700)
    stage_root = output_dir / "stage"
    stage_data = stage_root / "data"
    stage_data.mkdir(parents=True)
    parquet_records, json_records, datasets = copy_market_data(source_root, stage_data)
    manifest = {
        "format_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source": "one-trading-development-shared-market-data",
        "release_sha": args.release_sha,
        "apply_policy": "overlay_local_files_and_preserve_remote_only_files",
        "market_data_dirs": list(MARKET_DATA_DIRS),
        "forbidden_top_level": sorted(FORBIDDEN_TOP_LEVEL),
        "excluded_root_files": ["capabilities.json", ".matrix_generation_etf.json"],
        "datasets": datasets,
        "parquet_files": sorted(parquet_records, key=lambda item: str(item["path"])),
        "json_files": sorted(json_records, key=lambda item: str(item["path"])),
    }
    manifest_path = stage_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.chmod(manifest_path, 0o600)
    archive, archive_sha = write_archive(output_dir, stage_root)
    summary = {
        "archive": str(archive),
        "archive_sha256": archive_sha,
        "parquet_files": len(parquet_records),
        "json_files": len(json_records),
        "parquet_rows": sum(int(item["rows"]) for item in parquet_records),
        "bytes": sum(int(item["bytes"]) for item in parquet_records + json_records),
        "datasets": datasets,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
