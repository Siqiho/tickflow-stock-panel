#!/usr/bin/env python3
"""Reopen every export page and reconcile every raw logical record to its digest."""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import hashlib
import heapq
import json
from pathlib import Path
import struct
import time

import stockdb_offline_export as e
import pyarrow.compute as pc


def validate_task(checkpoint):
    report = json.loads(Path(checkpoint).read_text())
    count = 0
    sample_count = 0
    digest = hashlib.sha256()
    file_reports = []

    def records(output):
        nonlocal sample_count
        path = Path(output["path"])
        if e.sha256_file(path) != output["sha256"]:
            raise ValueError(f"output hash mismatch: {path}")
        parquet = e.pq.ParquetFile(path, page_checksum_verification=True)
        if parquet.metadata.num_rows != output["rows"]:
            raise ValueError(f"output row count mismatch: {path}")
        rows = 0
        last_key = None
        first_key = None
        for batch in parquet.iter_batches(batch_size=65536, use_threads=False):
            # All columns are decoded with page-checksum verification, not just footers.
            keys = batch.column("physical_key")
            if keys.null_count:
                raise ValueError("null physical key")
            if len(keys) > 1 and pc.any(pc.greater_equal(keys.slice(0, len(keys) - 1), keys.slice(1))).as_py():
                raise ValueError(f"duplicate or unsorted key: {path}")
            key0 = keys[0].as_py()
            if last_key is not None and key0 <= last_key:
                raise ValueError(f"key ordering failed across row groups: {path}")
            if first_key is None:
                first_key = key0
            last_key = keys[-1].as_py()
            expected_db = report["task"].rsplit("-", 1)[0]
            if not pc.all(pc.equal(batch.column("source_db"), expected_db)).as_py():
                raise ValueError("source database projection mismatch")
            for position in set((0, len(batch) // 2, len(batch) - 1)):
                row = batch.slice(position, 1).to_pylist()[0]
                if row["payload_encoding"] == "msgpack":
                    native = e.msgpack.unpackb(row["payload_raw"], raw=False, strict_map_key=False)
                    if isinstance(native, dict):
                        for field, value in native.items():
                            if field in row and field not in dict(e.COMMON_FIELDS):
                                actual = row[field]
                                if actual != value and not (isinstance(actual, float) and isinstance(value, float)
                                    and actual != actual and value != value):
                                    raise ValueError(f"typed sample differs from raw: {path} {field}")
                    sample_count += 1
            columns = batch.select(["physical_key", "source_sequence", "payload_raw"]).to_pydict()
            rows += len(batch)
            yield from zip(columns["physical_key"], columns["source_sequence"], columns["payload_raw"])
        if rows != output["rows"]:
            raise ValueError("decoded row count mismatch")
        file_reports.append({"path": str(path), "rows": rows,
            "first_key_hex": first_key.hex() if first_key else None,
            "last_key_hex": last_key.hex() if last_key else None})

    iterators = [records(output) for output in report["outputs"].values()]
    previous_key = None
    for key, seq, raw in heapq.merge(*iterators, key=lambda item: item[0]):
        if previous_key is not None and key <= previous_key:
            raise ValueError("duplicate key across tables")
        previous_key = key
        digest.update(struct.pack("<IQI", len(key), seq, len(raw)))
        digest.update(key)
        digest.update(raw)
        count += 1
    if count != report["audit"].get("live_records", 0) or digest.hexdigest() != report["logical_stream_sha256"]:
        raise ValueError(f"logical source/output digest mismatch: {checkpoint}")
    if file_reports:
        number = int(report["task"].rsplit("-", 1)[1])
        low, high = e.key_ranges()[number]
        for item in file_reports:
            first = bytes.fromhex(item["first_key_hex"])
            last = bytes.fromhex(item["last_key_hex"])
            if (low is not None and first < low) or (high is not None and last >= high):
                raise ValueError("records outside non-overlapping task bounds")
    return {"task": report["task"], "records": count, "typed_samples": sample_count,
        "files": file_reports, "logical_stream_sha256_verified": True}


def validate_source(job):
    snapshot_path, expected, original = job
    if e.sha256_file(Path(snapshot_path)) != expected:
        raise ValueError(f"snapshot changed: {snapshot_path}")
    original_path = Path(original) / Path(snapshot_path).parent.name / Path(snapshot_path).name
    if e.sha256_file(original_path) != expected:
        raise ValueError(f"original active source bytes differ: {original_path}")
    return 1


def cached_validate_task(checkpoint):
    """Allow completed ranges to be checked while later ranges are still exporting."""
    checkpoint = Path(checkpoint)
    cache_dir = checkpoint.parent.parent / "verification_checkpoints"
    cache_dir.mkdir(exist_ok=True)
    cache = cache_dir / checkpoint.name
    identity = hashlib.sha256(checkpoint.read_bytes() + Path(__file__).read_bytes()).hexdigest()
    if cache.exists():
        saved = json.loads(cache.read_text())
        if saved["identity"] == identity:
            report = json.loads(checkpoint.read_text())
            # Reuse the expensive page/record check only after rehashing every output.
            for output in report["outputs"].values():
                if e.sha256_file(Path(output["path"])) != output["sha256"]:
                    raise ValueError("previously verified output was changed")
            return saved["result"]
    result = validate_task(checkpoint)
    e.atomic_json(cache, {"identity": identity, "result": result})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--prevalidate", action="store_true", help="Only cache checks of finished ranges; never publish validation.json")
    args = parser.parse_args()
    started = time.monotonic()
    root = args.output
    if args.prevalidate:
        paths = sorted((root / "checkpoints").glob("*.json"))
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
            total = 0
            for checked in pool.map(cached_validate_task, paths):
                total += checked["records"]
                if checked["records"]:
                    print(json.dumps({"event": "prevalidated", "task": checked["task"], "records": checked["records"]}), flush=True)
        print(json.dumps({"event": "prevalidation_only", "records": total, "tasks": len(paths)}), flush=True)
        return
    complete = json.loads((root / "export_complete.json").read_text())
    if complete["status"] != "exported_pending_validation":
        raise ValueError("full export completion marker missing")
    paths = [root / "checkpoints" / (task + ".json") for task in complete["task_ids"]]
    if set(p.name for p in paths) != set(p.name for p in (root / "checkpoints").glob("*.json")):
        raise ValueError("missing or unexpected task checkpoints")
    if list(root.glob("tables/*/*.partial")):
        raise ValueError("unpublished partial output exists")
    reports = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        for checked in pool.map(cached_validate_task, paths):
            reports.append(checked)
            if checked["records"]:
                print(json.dumps({"event": "validated", "task": checked["task"], "records": checked["records"]}), flush=True)
        sources = json.loads((root / "source_inventory.json").read_text())
        jobs = [(path, digest, str(args.original)) for inv in sources for path, digest in inv["source_checksums"].items()]
        source_files = sum(pool.map(validate_source, jobs))
    counts = collections.Counter()
    coverage = {}
    accounting = collections.Counter()
    for path in paths:
        checkpoint = json.loads(path.read_text())
        accounting.update({key: value for key, value in checkpoint["audit"].items() if isinstance(value, int)})
        for table, out in checkpoint["outputs"].items():
            counts[table] += out["rows"]
            key = table + "/" + checkpoint["task"].rsplit("-", 1)[0]
            entry = coverage.setdefault(key, {"rows": 0, "files": 0, "bytes": 0, "minimum_date": None,
                "maximum_date": None, "codes": set(), "fields_seen": collections.Counter()})
            entry["rows"] += out["rows"]
            entry["files"] += 1
            entry["bytes"] += out["bytes"]
            entry["codes"].update(out["codes"])
            entry["fields_seen"].update(out["fields_seen"])
            if out["minimum_date"] is not None:
                entry["minimum_date"] = min(v for v in (entry["minimum_date"], out["minimum_date"]) if v is not None)
                entry["maximum_date"] = max(v for v in (entry["maximum_date"], out["maximum_date"]) if v is not None)
    for entry in coverage.values():
        entry["codes"] = sorted(entry["codes"])
        entry["code_count"] = len(entry["codes"])
        entry["fields_seen"] = dict(entry["fields_seen"])
    result = {"status": "verified_lossless_isolated_export", "unix_time": time.time(),
        "elapsed_seconds": round(time.monotonic() - started, 3), "records": sum(counts.values()),
        "table_counts": dict(counts), "coverage": coverage, "accounting": dict(accounting),
        "original_and_snapshot_active_files_sha256_verified": source_files,
        "typed_projection_samples": sum(item["typed_samples"] for item in reports),
        "checks": ["all_task_checkpoints_present", "all_parquet_pages_reopened_with_checksums", "all_file_sha256",
            "all_raw_logical_records_reconciled_to_source_stream_sha256", "strict_key_uniqueness_per_source_db",
            "disjoint_partition_ranges", "typed_projection_stratified_samples", "original_and_snapshot_active_files_equal"],
        "not_verified": ["original_market_producer", "data_license", "valuation_PIT", "minute_timestamp_convention",
            "cross_database_precedence", "formal_provider_API_or_UI_integration"], "tasks": reports}
    e.atomic_json(root / "validation.json", result)
    print(json.dumps({"status": result["status"], "rows": result["records"], "tables": result["table_counts"],
        "source_files": source_files, "seconds": result["elapsed_seconds"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
