#!/usr/bin/env python3
"""Preserve undecodable native values as an explicitly named, searchable table."""
import argparse
import collections
import json
from pathlib import Path

import duckdb
import stockdb_offline_export as e
from profile_stockdb_export import derived


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.output
    if not (root / "export_complete.json").exists():
        raise ValueError("full export must be finished")
    connection = duckdb.connect()
    connection.execute("SET threads=2")
    connection.execute("SET memory_limit='2GB'")
    records = []
    errors = collections.Counter()
    counts = collections.Counter()
    coverage = {}
    for checkpoint in (root / "checkpoints").glob("*.json"):
        report = json.loads(checkpoint.read_text())
        for table, output in report["outputs"].items():
            if table not in ("daily_bars", "minute_bars"):
                continue
            key = table + "/" + report["task"].rsplit("-", 1)[0]
            entry = coverage.setdefault(key, {"code_set": set(), "minimum_key_date": None, "maximum_key_date": None})
            entry["code_set"].update(output["codes"])
            if output["minimum_date"] is not None:
                entry["minimum_key_date"] = min(v for v in (entry["minimum_key_date"], output["minimum_date"]) if v is not None)
                entry["maximum_key_date"] = max(v for v in (entry["maximum_key_date"], output["maximum_date"]) if v is not None)
    for table in ("daily_bars", "minute_bars"):
        cursor = connection.execute("""SELECT source_db,source_file,source_sequence,logical_key,payload_raw,payload_encoding
            FROM read_parquet(?) WHERE payload_encoding<>'msgpack' ORDER BY source_db,logical_key""", [str(root / "tables" / table / "*.parquet")])
        for source_db, source_file, sequence, key, raw, encoding in cursor.fetchall():
            try:
                e.msgpack.unpackb(raw, raw=False, strict_map_key=False)
                raise AssertionError("record unexpectedly became decodable")
            except (ValueError, TypeError, UnicodeError) as error:
                reason = str(error)
                error_type = type(error).__name__
            parts = key.split(":")
            code = parts[1] if len(parts) > 1 else None
            date = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
            records.append({"source_table": table, "source_db": source_db, "source_file": source_file,
                "source_sequence": sequence, "logical_key": key, "code_from_key": code, "date_from_key": date,
                "payload_raw": raw, "payload_encoding": encoding, "raw_length": len(raw), "error_type": error_type,
                "error_text": reason, "repair_status": "not_repaired_original_preserved"})
            counts[table] += 1
            errors[error_type + ": " + reason] += 1
            entry = coverage[table + "/" + source_db]
            if code:
                entry["code_set"].add(code)
            if date is not None:
                entry["minimum_key_date"] = min(v for v in (entry["minimum_key_date"], date) if v is not None)
                entry["maximum_key_date"] = max(v for v in (entry["maximum_key_date"], date) if v is not None)
    schema = e.pa.schema([(name, e.pa.string()) for name in ("source_table", "source_db", "source_file")] + [
        ("source_sequence", e.pa.uint64()), ("logical_key", e.pa.string()), ("code_from_key", e.pa.string()),
        ("date_from_key", e.pa.int64()), ("payload_raw", e.pa.binary()), ("payload_encoding", e.pa.string()),
        ("raw_length", e.pa.int32()), ("error_type", e.pa.string()), ("error_text", e.pa.string()), ("repair_status", e.pa.string())])
    output = derived(root, "unreadable_native_records", records, schema)
    for entry in coverage.values():
        entry["codes"] = sorted(entry.pop("code_set"))
        entry["code_count"] = len(entry["codes"])
    result = {"status": "quarantined_without_fabrication", "counts": dict(counts), "errors": dict(errors),
        "output": output, "coverage_including_unreadable_keys": coverage,
        "scope": "full source values retained in tables and this searchable quarantine; no prices, dates or volume fabricated"}
    e.atomic_json(root / "quarantine_report.json", result)
    print(json.dumps({"event": "quarantine_complete", "counts": result["counts"], "errors": result["errors"],
        "output": output}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
