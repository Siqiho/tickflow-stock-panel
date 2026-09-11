#!/usr/bin/env python3
"""Inspect cross-database overlaps without silently picking an undocumented winner."""
import collections
import json
from pathlib import Path
import sys

import duckdb
import stockdb_offline_export as e
from profile_stockdb_export import derived


def main():
    root = Path(sys.argv[1])
    profile = json.loads((root / "quality_profile.json").read_text())
    connection = duckdb.connect()
    connection.execute("SET threads=2")
    connection.execute("SET memory_limit='2GB'")
    overlaps, conflicts = [], []
    for interval in profile["cross_database"]["minute_bars"].get("overlap_intervals", []):
        grouped = connection.execute("""SELECT logical_key,list(source_db),list(source_file),list(source_sequence),list(payload_raw)
            FROM read_parquet(?) WHERE source_db IN (?,?) AND
            (date BETWEEN ? AND ? OR (date IS NULL AND try_cast(split_part(logical_key,':',3) AS BIGINT) BETWEEN ? AND ?))
            GROUP BY logical_key HAVING count(*)>1 ORDER BY logical_key""", [
                str(root / "tables/minute_bars/*.parquet"), interval["left"], interval["right"],
                interval["lower"], interval["upper"], interval["lower"], interval["upper"]]).fetchall()
        for key, dbs, files, sequences, values in grouped:
            same_bytes = all(value == values[0] for value in values[1:])
            decoded = []
            for raw in values:
                try:
                    decoded.append(e.msgpack.unpackb(raw, raw=False, strict_map_key=False))
                except (ValueError, UnicodeError, TypeError):
                    decoded.append({"__undecodable_raw_hex__": raw.hex()})
            same_values = all(value == decoded[0] for value in decoded[1:])
            parts = key.split(":")
            overlaps.append({"logical_key": key, "code": parts[1], "date": int(parts[2]),
                "variant_count": len(values), "byte_equal": same_bytes, "semantic_equal": same_values, "source_dbs": sorted(dbs)})
            if not same_values:
                for db, filename, sequence, raw, value in zip(dbs, files, sequences, values, decoded):
                    conflicts.append({"logical_key": key, "source_db": db, "source_file": filename,
                        "source_sequence": sequence, "payload_raw": raw, "payload_json": e.json_value(value)})
    overlap_schema = e.pa.schema([("logical_key", e.pa.string()), ("code", e.pa.string()), ("date", e.pa.int64()),
        ("variant_count", e.pa.int32()), ("byte_equal", e.pa.bool_()), ("semantic_equal", e.pa.bool_()),
        ("source_dbs", e.pa.list_(e.pa.string()))])
    conflict_schema = e.pa.schema([("logical_key", e.pa.string()), ("source_db", e.pa.string()), ("source_file", e.pa.string()),
        ("source_sequence", e.pa.uint64()), ("payload_raw", e.pa.binary()), ("payload_json", e.pa.string())])
    existing = root / "derived/cross_database_conflicts.parquet"
    if existing.exists():
        # DuckDB list aggregation can change variant order across runs; content
        # equality, not incidental scan order, controls idempotent reuse.
        previous = e.pq.read_table(existing).to_pylist()
        order = lambda row: (row["logical_key"], row["source_db"])
        if sorted(previous, key=order) == sorted(conflicts, key=order):
            conflicts = previous
    result = {"duplicate_minute_keys": len(overlaps), "byte_different_keys": sum(not row["byte_equal"] for row in overlaps),
        "semantic_conflict_keys": sum(not row["semantic_equal"] for row in overlaps),
        "policy": "all variants retained; source_sequence is not a cross-database clock; no winner inferred",
        "overlap_index": derived(root, "cross_database_overlap_keys", overlaps, overlap_schema),
        "conflict_variants": derived(root, "cross_database_conflicts", conflicts, conflict_schema),
        "examples": [{key: value for key, value in row.items() if key != "payload_raw"} for row in conflicts[:10]]}
    e.atomic_json(root / "overlap_report.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
