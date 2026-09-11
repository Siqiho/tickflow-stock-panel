#!/usr/bin/env python3
"""Recover only complete MessagePack pairs into a new, isolated repair overlay.

No engine, network, native archive rewrite, inferred prices, or missing-byte
padding. A complete OHLCV record is not a claim of backtest/production quality.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

import stockdb_offline_export as e
from msgpack import fallback

CORE = ("open", "high", "low", "close", "volume", "amount")
NUMERIC = CORE + tuple(name for name, dtype in e.DAILY_FIELDS if e.pa.types.is_floating(dtype))
SOURCE_FIELDS = [
    ("source_table", e.pa.string()), ("source_db", e.pa.string()), ("source_file", e.pa.string()),
    ("source_sequence", e.pa.uint64()), ("logical_key", e.pa.string()),
    ("payload_raw", e.pa.binary()), ("payload_sha256", e.pa.string()),
]
SCHEMA = e.pa.schema(SOURCE_FIELDS + e.BAR_FIELDS + e.DAILY_FIELDS + [
    ("recovered_pairs_msgpack", e.pa.binary()), ("recovered_json", e.pa.string()),
    ("recovered_fields", e.pa.list_(e.pa.string())), ("missing_core_fields", e.pa.list_(e.pa.string())),
    ("declared_pairs", e.pa.int32()), ("complete_pairs", e.pa.int32()),
    ("complete_prefix_bytes", e.pa.int32()), ("pending_key", e.pa.string()),
    ("source_truncated", e.pa.bool_()), ("identity_valid", e.pa.bool_()),
    ("ohlc_consistent", e.pa.bool_()), ("core_fields_complete", e.pa.bool_()),
    ("eligible_overlay", e.pa.bool_()), ("repair_status", e.pa.string()),
    ("validation_errors", e.pa.list_(e.pa.string())), ("repair_method", e.pa.string()),
])


def decode_prefix(raw: bytes, implementation=e.msgpack):
    """A failed key/value is not included; the last committed offset is explicit."""
    u = implementation.Unpacker(raw=False, strict_map_key=False, max_map_len=256,
                                max_buffer_size=1_000_000)
    u.feed(raw)
    try:
        declared = u.read_map_header()
    except Exception as exc:
        raise ValueError("missing or invalid map header") from exc
    fields, pending, offset = {}, None, u.tell()
    truncated = False
    for _ in range(declared):
        try:
            pending = u.unpack()
            if not isinstance(pending, str) or pending in fields:
                raise ValueError("non-string or duplicate map key")
            value = u.unpack()
        except implementation.OutOfData:
            truncated = True
            break
        except (TypeError, UnicodeError, implementation.FormatError, implementation.StackError) as exc:
            raise ValueError("invalid map pair") from exc
        fields[pending] = value
        pending, offset = None, u.tell()
    if not truncated and offset != len(raw):
        raise ValueError("trailing bytes after declared map")
    return {"fields": fields, "pending_key": pending, "declared_pairs": declared,
            "complete_prefix_bytes": offset, "source_truncated": truncated}


def numeric(value):
    if type(value) not in (int, float):
        return None
    try:
        converted = float(value)
        if not math.isfinite(converted) or (type(value) is int and int(converted) != value):
            return None
        return converted
    except (ValueError, OverflowError):
        return None


def repair_record(source):
    raw = source["payload_raw"]
    out = {name: source.get(name) for name, _ in SOURCE_FIELDS}
    out["payload_sha256"] = hashlib.sha256(raw).hexdigest()
    errors = []
    try:
        prefix = decode_prefix(raw)
    except ValueError as exc:
        errors.append(str(exc))
        prefix = {"fields": {}, "pending_key": None, "declared_pairs": None,
                  "complete_prefix_bytes": 0, "source_truncated": None}
    fields = prefix.pop("fields")
    out.update(prefix)
    out.update({"complete_pairs": len(fields), "recovered_fields": list(fields),
                "recovered_pairs_msgpack": e.msgpack.packb(fields, use_bin_type=True),
                "recovered_json": e.json_value(fields), "repair_method": "complete_msgpack_prefix_v1"})
    identity = False
    try:
        domain, code, date_string = source["logical_key"].split(":")
        minute = source["source_table"] == "minute_bars"
        expected_domain = "分钟k" if minute else "日k"
        if source["source_table"] not in ("minute_bars", "daily_bars"):
            raise ValueError("unsupported source table")
        datetime.strptime(date_string, "%Y%m%d%H%M%S" if minute else "%Y%m%d")
        identity = (domain == expected_domain and len(code) == 6 and code.isdigit()
                    and len(date_string) == (14 if minute else 8)
                    and fields.get("code") == code and type(fields.get("code")) is str
                    and type(fields.get("date")) is int and fields["date"] == int(date_string)
                    and source.get("code_from_key", code) == code
                    and source.get("date_from_key", int(date_string)) == int(date_string))
    except (KeyError, ValueError, TypeError):
        pass
    if not identity:
        errors.append("identity_or_date_not_verified")
    out["identity_valid"] = identity
    out["code"] = fields.get("code") if identity else None
    out["date"] = fields.get("date") if identity else None
    out["trade_date"] = int(str(out["date"])[:8]) if identity else None
    for name in NUMERIC:
        value = fields.get(name)
        out[name] = numeric(value)
        if name in fields and value is not None and out[name] is None:
            errors.append("invalid_numeric:" + name)
    out["name"] = fields.get("name") if type(fields.get("name")) is str else None
    out["is_st"] = fields.get("is_st") if type(fields.get("is_st")) is bool else None
    out["missing_core_fields"] = [name for name in CORE if out[name] is None]
    prices = [out[name] for name in ("open", "high", "low", "close")]
    ohlc = (all(v is not None and v > 0 for v in prices)
            and out["high"] >= max(prices) and out["low"] <= min(prices))
    if not ohlc:
        errors.append("invalid_or_missing_ohlc")
    if any(out[name] is not None and out[name] < 0 for name in ("volume", "amount")):
        errors.append("negative_volume_or_amount")
    out["ohlc_consistent"] = ohlc
    out["eligible_overlay"] = not errors
    out["core_fields_complete"] = not errors and not out["missing_core_fields"]
    out["repair_status"] = ("rejected" if errors else "exact_prefix_core_complete"
                            if out["core_fields_complete"] else "exact_prefix_partial_core")
    out["validation_errors"] = errors
    return out


def write_table(path, table):
    temporary = path.with_suffix(".parquet.partial")
    if path.exists() or temporary.exists():
        raise FileExistsError(path)
    e.pq.write_table(table, temporary, compression="zstd", write_page_checksum=True)
    with temporary.open("rb") as stream:
        os.fsync(stream.fileno())
    reopened = e.pq.ParquetFile(temporary, page_checksum_verification=True).read()
    if not reopened.equals(table):
        raise ValueError("Parquet reopen mismatch")
    temporary.rename(path)
    return {"path": str(path), "rows": len(table), "sha256": e.sha256_file(path)}


def run(source: Path, output: Path, dry_run=False):
    source, output = source.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError("choose a fresh output directory; old results are immutable")
    source_hash = e.sha256_file(source)
    original = e.pq.ParquetFile(source, page_checksum_verification=True).read().to_pylist()
    seen, rows, counts, missing, pending = set(), [], Counter(), Counter(), Counter()
    alternate_checked = 0
    for item in original:
        key = (item["source_table"], item["source_db"], item["logical_key"])
        if key in seen:
            raise ValueError("duplicate source table/database/key")
        seen.add(key)
        row = repair_record(item)
        if row["eligible_overlay"]:
            independent = decode_prefix(item["payload_raw"], implementation=fallback)
            if (independent["fields"] != e.msgpack.unpackb(row["recovered_pairs_msgpack"], raw=False)
                    or independent["complete_prefix_bytes"] != row["complete_prefix_bytes"]
                    or independent["pending_key"] != row["pending_key"]):
                raise ValueError("C and pure-Python decoders disagree")
            alternate_checked += 1
        counts[item["source_table"] + "/" + row["repair_status"]] += 1
        missing[item["source_table"] + "/" + ",".join(row["missing_core_fields"])] += 1
        pending[str(row["pending_key"])] += 1
        rows.append(row)
    if e.sha256_file(source) != source_hash:
        raise ValueError("source changed while repairing")
    report = {"status": "dry_run" if dry_run else "verified_isolated_field_recovery",
              "created_at": datetime.now(timezone.utc).isoformat(), "source": str(source),
              "source_sha256": source_hash, "script_sha256": e.sha256_file(Path(__file__)),
              "rows": len(rows), "unique_source_keys": len(seen), "counts": dict(counts),
              "missing_core": dict(missing), "truncation_at": dict(pending),
              "alternate_decoder_verified_rows": alternate_checked,
              "scope": "exact complete original fields only; no missing values filled or source files changed",
              "production_status": "isolated_not_backtest_accepted", "outputs": {}}
    if dry_run:
        return report
    output.mkdir(parents=True, exist_ok=False)
    table = e.pa.Table.from_pylist(rows, schema=SCHEMA)
    report["outputs"]["recovered_bar_fields"] = write_table(output / "recovered_bar_fields.parquet", table)
    complete = table.filter(table["core_fields_complete"])
    report["outputs"]["recovered_core_complete"] = write_table(output / "recovered_core_complete.parquet", complete)
    unresolved = e.pa.Table.from_pylist([row for row in rows if not row["core_fields_complete"]], schema=SCHEMA)
    unresolved = unresolved.select(["source_table", "source_db", "logical_key", "payload_sha256",
                                    "missing_core_fields", "validation_errors", "repair_status"])
    report["outputs"]["unresolved_core"] = write_table(output / "unresolved_core.parquet", unresolved)
    if e.sha256_file(source) != source_hash:
        raise ValueError("source changed before publication")
    # A consumer requires this final marker; an interrupted directory is not published.
    e.atomic_json(output / "validation.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.output, args.dry_run), ensure_ascii=False, indent=2))
