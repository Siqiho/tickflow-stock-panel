#!/usr/bin/env python3
"""Independent consumption checks for the isolated StockDB field recovery."""
import argparse
import json
from pathlib import Path

import duckdb
import stockdb_offline_export as e


def verify(root):
    marker = root / "prefix_v1/validation.json"
    report = json.loads(marker.read_text())
    if report["status"] != "verified_isolated_field_recovery":
        raise ValueError("missing successful publication")
    if e.sha256_file(Path(report["source"])) != report["source_sha256"]:
        raise ValueError("source input hash changed")
    if e.sha256_file(Path(__file__).with_name("repair_stockdb_records.py")) != report["script_sha256"]:
        raise ValueError("producer no longer matches its recorded version")
    for artifact in report["outputs"].values():
        path = Path(artifact["path"])
        if e.sha256_file(path) != artifact["sha256"]:
            raise ValueError("artifact hash mismatch")
        reopened = e.pq.ParquetFile(path, page_checksum_verification=True).read()
        if len(reopened) != artifact["rows"]:
            raise ValueError("artifact row-count mismatch")
    c = duckdb.connect()
    c.execute("SET threads=2")
    c.execute("SET memory_limit='2GB'")
    c.execute((root / "read.sql").read_text())
    exact = c.execute("""SELECT count(*),count_if(a.payload_raw=r.payload_raw),
          count_if(a.source_file=r.source_file AND a.source_sequence=r.source_sequence),
          count_if(r.identity_valid),count_if(r.ohlc_consistent)
        FROM read_parquet(?) a FULL JOIN stockdb_recovered_fields r
        USING(source_table,source_db,logical_key)""", [report["source"]]).fetchone()
    if exact != (report["rows"],) * 5:
        raise ValueError("incomplete coverage, raw-byte mismatch or invalid identity")
    examples = []
    for view, key, expected in [
        ("stockdb_daily_with_recovered_fields", "日k:000008:20000926", (6.1, 6.13, 6.01, 6.11, None, None, True)),
        ("stockdb_minute_with_recovered_fields", "分钟k:000001:20260130132500", (10.9, 10.9, 10.89, 10.89, None, None, True)),
        ("stockdb_daily_with_recovered_fields", "日k:000333:20150805", (16.88, 17.11, 16.31, 16.36, 35487734., 1247682320., True)),
        ("stockdb_daily_with_recovered_fields", "日k:000001:20000104", (17.5, 18.55, 17.2, 18.29, 8216000., 147324992., False)),
    ]:
        rows = c.execute(f"""SELECT open,high,low,close,volume,amount,field_recovery_applied
            FROM {view} WHERE logical_key=?""", [key]).fetchall()
        if rows != [expected]:
            raise ValueError("consumption regression: " + key)
        examples.append({"key": key, "view": view, "values": list(rows[0])})
    conflict_counts = c.execute("""SELECT count(*),count(distinct logical_key)
                                  FROM stockdb_minute_conflicts""").fetchone()
    if conflict_counts != (4, 2):
        raise ValueError("conflict variants lost")
    # Diagnostic only: native stock volume/amount are believed to be shares/yuan,
    # but no unit or adjustment correction is authorized by this arithmetic.
    q = c.execute("""SELECT source_db,logical_key,code,date,open,high,low,close,volume,amount,
               amount/volume AS implied_average_price,
               'native_unit_or_adjustment_basis_unverified' AS quality_warning
            FROM stockdb_recovered_core_complete
            WHERE volume>0 AND (amount/volume<low*.99 OR amount/volume>high*1.01)
            ORDER BY logical_key""").to_arrow_table()
    target = root / "repair_verification.json"
    if target.exists():
        raise FileExistsError("verification evidence is immutable")
    quality_path = root / "recovered_core_quality_warnings.parquet"
    from repair_stockdb_records import write_table
    quality = write_table(quality_path, q)
    result = {"status": "verified_exact_fields_only", "rows_reconciled": report["rows"],
              "raw_bytes_and_source_identity_preserved": True, "read_sql_samples": examples,
              "conflict_rows": conflict_counts[0], "conflict_keys": conflict_counts[1],
              "core_complete_native_rows": report["outputs"]["recovered_core_complete"]["rows"],
              "native_price_volume_basis_warning": quality,
              "no_missing_numeric_value_fabricated": True,
              "formal_data_dir_written": False,
              "acceptance": "isolated field recovery only; not backtest or production acceptance",
              "prefix_manifest_sha256": e.sha256_file(marker), "read_sql_sha256": e.sha256_file(root / "read.sql"),
              "verifier_sha256": e.sha256_file(Path(__file__))}
    e.atomic_json(target, result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    args = p.parse_args()
    print(json.dumps(verify(args.root.resolve()), ensure_ascii=False, indent=2))
