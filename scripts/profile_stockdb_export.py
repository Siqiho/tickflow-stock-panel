#!/usr/bin/env python3
"""Full-column market QC and small, traceable flattened reference tables."""
import argparse
import collections
import json
from pathlib import Path

import duckdb
import stockdb_offline_export as e


def query_dicts(connection, sql, params=()):
    cursor = connection.execute(sql, params)
    names = [field[0] for field in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def parquet_rows(root, table):
    for path in sorted((root / "tables" / table).glob("*.parquet")):
        yield from e.pq.read_table(path).to_pylist()


def derived(root, name, rows, schema):
    directory = root / "derived"
    directory.mkdir(exist_ok=True)
    path = directory / (name + ".parquet")
    table = e.pa.Table.from_pylist(rows, schema=schema)
    if path.exists():
        if not e.pq.read_table(path).equals(table):
            raise ValueError(f"refusing to overwrite a different derived file: {path}")
    else:
        temporary = path.with_suffix(".parquet.partial")
        if temporary.exists():
            raise FileExistsError(temporary)
        e.pq.write_table(table, temporary, compression="zstd", write_page_checksum=True)
        if not e.pq.read_table(temporary).equals(table):
            raise ValueError("derived Parquet roundtrip mismatch")
        temporary.rename(path)
    return {"path": str(path), "rows": len(rows), "sha256": e.sha256_file(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.output
    if not (root / "export_complete.json").exists():
        raise ValueError("wait for full export before profiling")
    connection = duckdb.connect()
    connection.execute("SET threads=2")
    connection.execute("SET memory_limit='2GB'")
    result = {"quality_policy": "flag_and_preserve_originals_not_silent_repair", "bars": {}, "cross_database": {},
        "notes": ["stock samples volume in shares and amount in yuan; other asset units not individually certified",
            "minute timestamps not shifted or normalized to another vendor",
            "pre_close and market capitalization arithmetic warnings are not auto-corrected",
            "current sector membership has no historical as_of; delisting list includes fund products"]}
    base = """SELECT source_db,count(*) AS row_count,count(distinct code) AS code_count,
        min(date) AS minimum_date,max(date) AS maximum_date,
        count_if(code IS NULL OR code!=split_part(logical_key,':',2)) AS code_key_mismatch,
        count_if(date IS NULL OR date!=try_cast(split_part(logical_key,':',3) AS BIGINT)) AS date_key_mismatch,
        count_if(open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL OR volume IS NULL OR amount IS NULL) AS null_core_fields,
        count_if(NOT isfinite(open) OR NOT isfinite(high) OR NOT isfinite(low) OR NOT isfinite(close)
            OR NOT isfinite(volume) OR NOT isfinite(amount)) AS nonfinite_core_fields,
        count_if(high<greatest(open,close,low) OR low>least(open,close,high)) AS invalid_ohlc_order,
        count_if(volume<0 OR amount<0) AS negative_volume_amount,count_if(volume=0) AS zero_volume_rows,
        max(volume) AS maximum_volume,max(amount) AS maximum_amount {extra}
        FROM read_parquet(?) GROUP BY source_db"""
    for table in ("daily_bars", "minute_bars"):
        extra = ""
        if table == "daily_bars":
            extra = """,count_if(pre_close>0 AND abs((close/pre_close-1)*100-pct_chg)>0.2) AS pre_close_return_disagreement,
                count_if(total_share>0 AND total_mv>0 AND close>0
                    AND abs(total_mv/total_share/close-1)>0.01) AS market_cap_price_share_disagreement"""
        glob = str(root / "tables" / table / "*.parquet")
        result["bars"][table] = query_dicts(connection, base.format(extra=extra), [glob])
        print(json.dumps({"event": "market_qc", "table": table, "results": result["bars"][table]}), flush=True)
        spans = sorted(result["bars"][table], key=lambda item: item["minimum_date"])
        disjoint = all(a["maximum_date"] < b["minimum_date"] for a, b in zip(spans, spans[1:]))
        if disjoint:
            result["cross_database"][table] = {"duplicate_keys": 0, "proof": "source date intervals are disjoint"}
        else:
            # Only overlapping date intervals can contain cross-DB duplicates.
            # Hash-grouping all 640M minute keys is unnecessary and exceeds RAM.
            overlap_reports = []
            for number, left in enumerate(spans):
                for right in spans[number + 1:]:
                    lower = max(left["minimum_date"], right["minimum_date"])
                    upper = min(left["maximum_date"], right["maximum_date"])
                    if lower > upper:
                        continue
                    overlap = query_dicts(connection, """SELECT count(*) AS duplicate_keys,
                            count_if(distinct_values>1) AS conflicting_values FROM (
                        SELECT logical_key,count(distinct payload_raw) AS distinct_values
                        FROM read_parquet(?) WHERE source_db IN (?,?) AND
                        (date BETWEEN ? AND ? OR (date IS NULL AND
                            try_cast(split_part(logical_key,':',3) AS BIGINT) BETWEEN ? AND ?))
                        GROUP BY logical_key HAVING count(*)>1)
                        """, [glob, left["source_db"], right["source_db"], lower, upper, lower, upper])[0]
                    overlap_reports.append({"left": left["source_db"], "right": right["source_db"],
                        "lower": lower, "upper": upper, **overlap})
            result["cross_database"][table] = {"overlap_intervals": overlap_reports,
                "duplicate_keys": sum(item["duplicate_keys"] for item in overlap_reports),
                "conflicting_values": sum(item["conflicting_values"] for item in overlap_reports)}
    daily = str(root / "tables/daily_bars/*.parquet")
    result["daily_ohlc_anomalies"] = query_dicts(connection, """SELECT source_db,logical_key,code,date,open,high,low,close
        FROM read_parquet(?) WHERE high<greatest(open,close,low) OR low>least(open,close,high) ORDER BY date,code""", [daily])
    result["pre_close_warning_examples"] = query_dicts(connection, """SELECT source_db,logical_key,code,date,close,pre_close,pct_chg
        FROM read_parquet(?) WHERE code='000001' AND pre_close>0 AND abs((close/pre_close-1)*100-pct_chg)>0.2
        ORDER BY date LIMIT 10""", [daily])
    for table in ("adjustment_factors", "sector_snapshots", "instrument_lists", "market_mapping", "delisting_records", "auxiliary_records"):
        glob = str(root / "tables" / table / "*.parquet")
        result["cross_database"][table] = query_dicts(connection, """SELECT logical_key,count(*) AS record_count,
            count(distinct payload_raw) AS distinct_values FROM read_parquet(?) GROUP BY logical_key HAVING count(*)>1""", [glob])
    parents = [("source_db", e.pa.string()), ("parent_logical_key", e.pa.string()), ("source_sequence", e.pa.uint64())]
    sectors = []
    for row in parquet_rows(root, "sector_snapshots"):
        payload = json.loads(row["payload_json"])
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            raise ValueError("unexpected sector shape; do not silently omit")
        for ordinal, symbol in enumerate(payload["symbols"]):
            sectors.append({"source_db": row["source_db"], "parent_logical_key": row["logical_key"],
                "source_sequence": row["source_sequence"], "sector_code": payload.get("code"), "sector_name": payload.get("name"),
                "provider_hint": payload.get("source"), "category": payload.get("category"), "sector_type": payload.get("type"),
                "group": payload.get("group"), "member_code": symbol, "member_ordinal": ordinal, "as_of": None})
    sector_schema = e.pa.schema(parents + [(name, e.pa.string()) for name in (
        "sector_code", "sector_name", "provider_hint", "category", "sector_type", "group", "member_code")] + [
        ("member_ordinal", e.pa.int32()), ("as_of", e.pa.date32())])
    market = {row["source_db"]: json.loads(row["payload_json"]) for row in parquet_rows(root, "market_mapping")}
    codes = []
    for row in parquet_rows(root, "instrument_lists"):
        for group, symbols in json.loads(row["payload_json"]).items():
            for symbol in symbols:
                codes.append({"source_db": row["source_db"], "parent_logical_key": row["logical_key"],
                    "source_sequence": row["source_sequence"], "code_group": group, "code": symbol,
                    "exchange_hint": market.get(row["source_db"], {}).get(group), "asset_type": None})
    code_schema = e.pa.schema(parents + [(name, e.pa.string()) for name in ("code_group", "code", "exchange_hint", "asset_type")])
    delisted = []
    for row in parquet_rows(root, "delisting_records"):
        if row["logical_key"].startswith("退市:seq:"):
            value = json.loads(row["payload_json"])
            if not isinstance(value, str):
                raise ValueError("unexpected delisting item type")
            delisted.append({"source_db": row["source_db"], "parent_logical_key": row["logical_key"],
                "source_sequence": row["source_sequence"], "code": value, "delisting_date": None})
    delist_schema = e.pa.schema(parents + [("code", e.pa.string()), ("delisting_date", e.pa.date32())])
    result["derived"] = {
        "sector_memberships": derived(root, "sector_memberships", sectors, sector_schema),
        "instrument_codes": derived(root, "instrument_codes", codes, code_schema),
        "delisting_items": derived(root, "delisting_items", delisted, delist_schema)}
    e.atomic_json(root / "quality_profile.json", result)
    print(json.dumps({"event": "profile_complete", "derived": result["derived"]}), flush=True)


if __name__ == "__main__":
    main()
