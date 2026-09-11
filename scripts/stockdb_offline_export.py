#!/usr/bin/env python3
"""Read a paused StockDB LevelDB snapshot without loading its native engine.

This is an isolated archival exporter, not a one-trading provider. Source files
are always opened rb. See docs/runbooks/stockdb-offline-export.md for boundaries.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import hashlib
import heapq
import json
import os
from pathlib import Path
import struct
import sys
import time
import shutil

DEPS = Path(__file__).resolve().parents[1] / ".stockdb-export-deps"
if DEPS.is_dir():
    sys.path.insert(0, str(DEPS))
import google_crc32c
import msgpack
import pyarrow as pa
import pyarrow.parquet as pq
import zstandard

MAGIC = 0xDB4775248B80FB57
BLOCK_SIZE = 32768
INDEX_PREFIX = b"kidx:"


def varint(buf: bytes, pos: int = 0) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if pos >= len(buf):
            raise ValueError("truncated varint")
        byte = buf[pos]
        pos += 1
        value |= (byte & 127) << shift
        if byte < 128:
            if value >= 1 << 64:
                raise ValueError("varint overflow")
            return value, pos
    raise ValueError("varint too long")


def length_prefixed(buf: bytes, pos: int) -> tuple[bytes, int]:
    size, pos = varint(buf, pos)
    end = pos + size
    if end > len(buf):
        raise ValueError("truncated length-prefixed value")
    return buf[pos:end], end


def masked_crc(buf: bytes) -> int:
    crc = google_crc32c.value(buf)
    return (((crc >> 15) | (crc << 17)) + 0xA282EAD8) & 0xFFFFFFFF


def log_records(path: Path, audit: dict):
    """LevelDB WAL/MANIFEST physical log, including incomplete final-tail audit."""
    fragments = None
    with path.open("rb") as stream:
        while chunk := stream.read(BLOCK_SIZE):
            pos = 0
            while pos + 7 <= len(chunk):
                crc, size, kind = struct.unpack_from("<IHB", chunk, pos)
                if (crc, size, kind) == (0, 0, 0):
                    if any(chunk[pos:]):
                        raise ValueError(f"nonzero log padding: {path}")
                    break
                pos += 7
                if pos + size > len(chunk):
                    if len(chunk) == BLOCK_SIZE:
                        raise ValueError(f"record crosses physical block: {path}")
                    audit.setdefault("incomplete_tails", []).append(str(path))
                    return
                payload = chunk[pos:pos + size]
                pos += size
                if masked_crc(bytes([kind]) + payload) != crc:
                    raise ValueError(f"log CRC mismatch: {path}")
                if kind == 1:
                    if fragments is not None:
                        raise ValueError("FULL log record inside fragmented record")
                    yield payload
                elif kind == 2:
                    if fragments is not None:
                        raise ValueError("nested FIRST log record")
                    fragments = bytearray(payload)
                elif kind in (3, 4):
                    if fragments is None:
                        raise ValueError("orphan fragmented log record")
                    fragments.extend(payload)
                    if kind == 4:
                        yield bytes(fragments)
                        fragments = None
                else:
                    raise ValueError(f"unknown log record kind {kind}")
            if len(chunk) < BLOCK_SIZE and any(chunk[pos:]):
                audit.setdefault("incomplete_tails", []).append(str(path))
    if fragments is not None:
        audit.setdefault("incomplete_tails", []).append(str(path))


def inventory(db: Path) -> dict:
    manifest_name = (db / "CURRENT").read_text().strip()
    if not manifest_name.startswith("MANIFEST-") or Path(manifest_name).name != manifest_name:
        raise ValueError("invalid CURRENT")
    state = {"source_db": db.name, "path": str(db), "manifest": manifest_name,
             "log_number": 0, "prev_log_number": 0, "last_sequence": 0}
    active = {}
    edits = 0
    for record in log_records(db / manifest_name, state):
        edits += 1
        pos = 0
        while pos < len(record):
            tag, pos = varint(record, pos)
            if tag == 1:
                value, pos = length_prefixed(record, pos)
                state["comparator"] = value.decode("ascii")
                if value != b"leveldb.BytewiseComparator":
                    raise ValueError(f"unsupported comparator: {value!r}")
            elif tag in (2, 3, 4, 9):
                value, pos = varint(record, pos)
                state[{2: "log_number", 3: "next_file_number", 4: "last_sequence", 9: "prev_log_number"}[tag]] = value
            elif tag == 5:
                _, pos = varint(record, pos)
                _, pos = length_prefixed(record, pos)
            elif tag == 6:
                level, pos = varint(record, pos)
                number, pos = varint(record, pos)
                active.pop((level, number), None)
            elif tag == 7:
                level, pos = varint(record, pos)
                number, pos = varint(record, pos)
                size, pos = varint(record, pos)
                smallest, pos = length_prefixed(record, pos)
                largest, pos = length_prefixed(record, pos)
                active[level, number] = {"level": level, "number": number, "size": size,
                    "smallest_hex": smallest.hex(), "largest_hex": largest.hex()}
            else:
                raise ValueError(f"unknown VersionEdit tag {tag} in {db}")
    files = []
    for item in sorted(active.values(), key=lambda x: (x["level"], x["number"])):
        path = db / f"{item['number']:06d}.ldb"
        if not path.exists():
            path = path.with_suffix(".sst")
        if path.stat().st_size != item["size"]:
            raise ValueError(f"manifest size mismatch: {path}")
        files.append({**item, "path": str(path)})
    state["files"] = files
    state["manifest_edits"] = edits
    state["active_bytes"] = sum(item["size"] for item in files)
    state["wal_files"] = [str(path) for path in sorted(db.glob("*.log"))
        if int(path.stem) >= state["log_number"] or int(path.stem) == state["prev_log_number"]]
    state["physical_sst_files"] = len(list(db.glob("*.ldb"))) + len(list(db.glob("*.sst")))
    return state


def block_entries(buf: bytes):
    if len(buf) < 8:
        raise ValueError("short restart block")
    count = struct.unpack_from("<I", buf, len(buf) - 4)[0]
    end = len(buf) - 4 * (count + 1)
    if count < 1 or end < 0:
        raise ValueError("invalid restart count")
    restarts = struct.unpack_from(f"<{count}I", buf, end)
    if restarts[0] != 0 or any(a > b for a, b in zip(restarts, restarts[1:])) or restarts[-1] > end:
        raise ValueError("invalid restart offsets")
    pos, previous = 0, b""
    while pos < end:
        shared, pos = varint(buf, pos)
        fresh, pos = varint(buf, pos)
        size, pos = varint(buf, pos)
        if shared > len(previous) or pos + fresh + size > end:
            raise ValueError("invalid prefix-compressed entry")
        key = previous[:shared] + buf[pos:pos + fresh]
        pos += fresh
        yield key, buf[pos:pos + size]
        pos += size
        previous = key
    if pos != end:
        raise ValueError("entry does not end at restart array")


def split_internal(key: bytes) -> tuple[bytes, int, int]:
    if len(key) < 8:
        raise ValueError("short internal key")
    tag = int.from_bytes(key[-8:], "little")
    kind = tag & 255
    if kind not in (0, 1):
        raise ValueError(f"unsupported value type {kind}")
    return key[:-8], tag >> 8, kind


class SST:
    def __init__(self, path: Path):
        self.path = path
        self.stream = path.open("rb")
        self.size = path.stat().st_size
        self.zstd = zstandard.ZstdDecompressor()
        self.audit = collections.Counter()
        self.stream.seek(-48, os.SEEK_END)
        footer = self.stream.read(48)
        if struct.unpack_from("<Q", footer, 40)[0] != MAGIC:
            raise ValueError(f"unknown table magic: {path}")
        _, pos = varint(footer)
        _, pos = varint(footer, pos)
        offset, pos = varint(footer, pos)
        size, _ = varint(footer, pos)
        self.index = list(block_entries(self.block(offset, size)))

    def block(self, offset: int, size: int, *, decode=True) -> bytes:
        if offset < 0 or size < 0 or offset + size + 5 > self.size - 48:
            raise ValueError(f"invalid block handle: {self.path}")
        self.stream.seek(offset)
        raw = self.stream.read(size + 5)
        if len(raw) != size + 5 or masked_crc(raw[:-4]) != struct.unpack_from("<I", raw, size + 1)[0]:
            raise ValueError(f"SST CRC mismatch: {self.path} offset={offset}")
        self.audit["crc_verified_blocks"] += 1
        self.audit["crc_verified_bytes"] += len(raw)
        if not decode:
            return b""
        kind, payload = raw[size], raw[:size]
        self.audit[f"compression_{kind}_blocks"] += 1
        if kind == 0:
            return payload
        if kind == 2 and payload.startswith(b"\x28\xb5\x2f\xfd"):
            return self.zstd.decompress(payload, max_output_size=64 * 1024 * 1024)
        raise ValueError(f"unsupported compression {kind}, magic {payload[:4].hex()}")

    def records(self, *, skip_indexes=True, lower_bound=None, upper_bound=None):
        lower = b""
        for separator, handle in self.index:
            upper, _, _ = split_internal(separator)
            if upper < lower:
                raise ValueError("unsorted SST index")
            if lower_bound is not None and upper < lower_bound:
                lower = upper
                continue
            if upper_bound is not None and lower >= upper_bound:
                break
            offset, pos = varint(handle)
            size, pos = varint(handle, pos)
            if pos != len(handle):
                raise ValueError("unexpected index handle suffix")
            internal_only = skip_indexes and lower.startswith(INDEX_PREFIX) and upper.startswith(INDEX_PREFIX)
            block = self.block(offset, size, decode=not internal_only)
            self.audit["data_blocks"] += 1
            if internal_only:
                self.audit["secondary_index_blocks_skipped"] += 1
            else:
                for key, value in block_entries(block):
                    user_key, sequence, kind = split_internal(key)
                    self.audit["physical_entries_decoded"] += 1
                    if skip_indexes and user_key.startswith(INDEX_PREFIX):
                        self.audit["secondary_index_boundary_entries_skipped"] += 1
                        continue
                    if lower_bound is not None and user_key < lower_bound:
                        continue
                    if upper_bound is not None and user_key >= upper_bound:
                        continue
                    yield user_key, sequence, kind, value
            lower = upper

    def close(self):
        self.stream.close()


def wal_records(path: Path, audit: dict):
    for record in log_records(path, audit):
        if len(record) < 12:
            raise ValueError("short WriteBatch")
        sequence, count = struct.unpack_from("<QI", record)
        pos = 12
        for index in range(count):
            if pos >= len(record):
                raise ValueError("WriteBatch count exceeds payload")
            kind = record[pos]
            pos += 1
            key, pos = length_prefixed(record, pos)
            value = b""
            if kind == 1:
                value, pos = length_prefixed(record, pos)
            elif kind != 0:
                raise ValueError(f"unknown WriteBatch tag {kind}")
            yield key, sequence + index, kind, value
        if pos != len(record):
            raise ValueError("WriteBatch trailing bytes")


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_json(path: Path, payload):
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


COMMON_FIELDS = [("source_db", pa.string()), ("source_file", pa.string()),
    ("source_sequence", pa.uint64()), ("physical_key", pa.binary()),
    ("logical_key", pa.string()), ("payload_encoding", pa.string()),
    ("payload_raw", pa.binary())]
BAR_FIELDS = [("code", pa.string()), ("date", pa.int64()), ("trade_date", pa.int32())] + [
    (name, pa.float64()) for name in ("open", "high", "low", "close", "volume", "amount")]
DAILY_FIELDS = [(name, pa.float64()) for name in ("pre_close", "amplitude", "pct_chg", "turnover",
    "vol_ratio", "pe_ttm", "pb", "total_mv", "float_mv", "total_share", "float_share")] + [
    ("name", pa.string()), ("is_st", pa.bool_())]
SCHEMAS = {
    "minute_bars": pa.schema(COMMON_FIELDS + BAR_FIELDS + [("extra_json", pa.string())]),
    "daily_bars": pa.schema(COMMON_FIELDS + BAR_FIELDS + DAILY_FIELDS + [("extra_json", pa.string())]),
    "adjustment_factors": pa.schema(COMMON_FIELDS + [("code", pa.string()), ("date", pa.int64())] + [
        (name, pa.float64()) for name in ("div", "give", "trans", "mult", "cum")] + [("payload_json", pa.string())]),
}
JSON_SCHEMA = pa.schema(COMMON_FIELDS + [("payload_json", pa.string())])
TABLES = {"分钟k": "minute_bars", "日k": "daily_bars", "复权": "adjustment_factors",
    "板块": "sector_snapshots", "股票代码": "instrument_lists", "市场": "market_mapping", "退市": "delisting_records"}


def json_value(value):
    """Readable projection; original bytes remain authoritative for exotic types."""
    def fallback(obj):
        if isinstance(obj, bytes):
            return {"__bytes_hex__": obj.hex()}
        if isinstance(obj, msgpack.ExtType):
            return {"__msgpack_ext__": obj.code, "data_hex": obj.data.hex()}
        return {"__type__": type(obj).__name__, "repr": repr(obj)}
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=fallback)
    except (TypeError, ValueError, UnicodeError):
        return json.dumps({"__projection_unavailable__": repr(value)}, ensure_ascii=True)


def overlaps(item, low, high):
    first = bytes.fromhex(item["smallest_hex"])[:-8]
    last = bytes.fromhex(item["largest_hex"])[:-8]
    if first.startswith(INDEX_PREFIX) and last.startswith(INDEX_PREFIX):
        return False
    return (low is None or last >= low) and (high is None or first < high)


def key_ranges():
    boundaries = []
    for domain in ("分钟k", "日k"):
        prefix = ("k" + domain + ":").encode()
        boundaries += [prefix] + [prefix + f"{n:02d}".encode() for n in range(1, 100)] + [prefix[:-1] + b";"]
    boundaries.sort()
    return list(zip([None] + boundaries, boundaries + [None]))


def task_records(task, audit):
    low = bytes.fromhex(task["low_hex"]) if task["low_hex"] else None
    high = bytes.fromhex(task["high_hex"]) if task["high_hex"] else None
    tables = []
    iterators = []
    try:
        for item in task["files"]:
            sst = SST(Path(item["path"]))
            tables.append(sst)
            # The bound values are captured per iterator, not by a late-binding generator.
            def attach(reader, filename):
                for key, seq, kind, value in reader.records(lower_bound=low, upper_bound=high):
                    yield key, seq, kind, value, filename
            iterators.append(attach(sst, Path(item["path"]).name))
        wal = []
        for path_string in task["wal_files"]:
            path = Path(path_string)
            if path.stat().st_size > 256 * 1024 * 1024:
                raise ValueError("WAL exceeds bounded reader limit; no partial export published")
            for key, seq, kind, value in wal_records(path, audit):
                if not key.startswith(INDEX_PREFIX) and (low is None or key >= low) and (high is None or key < high):
                    wal.append((key, seq, kind, value, path.name))
        if wal:
            iterators.append(iter(sorted(wal, key=lambda r: (r[0], -r[1]))))
        previous_key, previous_seq, previous_value, previous_kind = None, None, None, None
        for key, seq, kind, value, filename in heapq.merge(*iterators, key=lambda r: (r[0], -r[1])):
            audit["input_business_versions"] += 1
            if key == previous_key:
                audit["older_or_duplicate_versions_removed"] += 1
                if seq == previous_seq and (value != previous_value or kind != previous_kind):
                    raise ValueError(f"conflicting identical internal sequence: {key!r}")
                previous_seq, previous_value, previous_kind = seq, value, kind
                continue
            if previous_key is not None and key <= previous_key:
                raise ValueError("merged keys are not strictly ordered")
            previous_key, previous_seq, previous_value, previous_kind = key, seq, value, kind
            if kind == 0:
                audit["latest_tombstones_removed"] += 1
                continue
            audit["live_records"] += 1
            yield key, seq, value, filename
    finally:
        for table in tables:
            for key, value in table.audit.items():
                audit[key] += value
            table.close()


class TableWriter:
    def __init__(self, root, table, task_id):
        self.schema = SCHEMAS.get(table, JSON_SCHEMA)
        self.path = root / "tables" / table / (task_id + ".parquet")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.temporary = self.path.with_suffix(".parquet.partial")
        if self.path.exists() or self.temporary.exists():
            raise FileExistsError(f"refusing unverified overwrite: {self.path}")
        self.writer = pq.ParquetWriter(self.temporary, self.schema, compression="zstd", compression_level=3,
            use_dictionary=["source_db", "source_file", "payload_encoding", "code", "name"],
            write_page_checksum=True, write_statistics=True)
        self.columns = {field.name: [] for field in self.schema}
        self.column_names = self.schema.names
        self.is_bar = table in ("minute_bars", "daily_bars")
        self.is_factor = table == "adjustment_factors"
        self.projection_names = [name for name in self.column_names if name not in {
            name for name, _ in COMMON_FIELDS} | {"trade_date", "extra_json"}]
        self.known = set(self.projection_names)
        self.rows = 0
        self.minimum_date = None
        self.maximum_date = None
        self.codes = set()
        self.fields_seen = collections.Counter()

    def append(self, base, decoded, audit):
        values = dict(base)
        if self.is_bar:
            if not isinstance(decoded, dict):
                audit["invalid_bar_payload"] += 1
                decoded = {}
            for name in self.projection_names:
                values[name] = decoded.get(name)
            date = values.get("date")
            values["trade_date"] = (date // 1000000 if date > 99999999 else date) if isinstance(date, int) else None
            extras = {k: v for k, v in decoded.items() if k not in self.known}
            values["extra_json"] = json_value(extras) if extras else None
        elif self.is_factor:
            parts = (base["logical_key"] or "").split(":")
            values["code"] = parts[1] if len(parts) > 1 else None
            values["date"] = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
            if isinstance(decoded, dict):
                for name in ("div", "give", "trans", "mult", "cum"):
                    value = decoded.get(name)
                    if value is not None and not isinstance(value, (int, float)):
                        audit["typed_projection_type_mismatch"] += 1
                        value = None
                    values[name] = value
            values["payload_json"] = json_value(decoded)
        else:
            values["payload_json"] = json_value(decoded)
        if isinstance(decoded, dict):
            self.fields_seen.update(str(k) for k in decoded)
        if values.get("code"):
            self.codes.add(values["code"])
        if values.get("date") is not None:
            date = values["date"]
            self.minimum_date = date if self.minimum_date is None else min(self.minimum_date, date)
            self.maximum_date = date if self.maximum_date is None else max(self.maximum_date, date)
        for name, column in self.columns.items():
            column.append(values.get(name))
        self.rows += 1
        if len(self.columns["physical_key"]) >= 65536:
            self.flush()

    def flush(self):
        if self.columns["physical_key"]:
            if shutil.disk_usage(self.path.parent).free < 30 * 1024 ** 3:
                raise OSError("stopped safely: less than 30 GiB free disk")
            table = pa.Table.from_pydict(self.columns, schema=self.schema)
            self.writer.write_table(table, row_group_size=65536)
            self.columns = {field.name: [] for field in self.schema}

    def finish(self):
        self.flush()
        self.writer.close()
        with self.temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        if pq.ParquetFile(self.temporary).metadata.num_rows != self.rows:
            raise ValueError("Parquet footer row-count mismatch")
        os.replace(self.temporary, self.path)
        return {"path": str(self.path), "rows": self.rows, "bytes": self.path.stat().st_size,
            "sha256": sha256_file(self.path), "minimum_date": self.minimum_date, "maximum_date": self.maximum_date,
            "codes": sorted(self.codes), "fields_seen": dict(self.fields_seen), "schema": str(self.schema)}


def export_task(task):
    started = time.monotonic()
    root = Path(task["output"])
    done = root / "checkpoints" / (task["id"] + ".json")
    if done.exists():
        saved = json.loads(done.read_text())
        if saved["task_fingerprint"] != task["fingerprint"]:
            raise ValueError("checkpoint is for another source snapshot or code version")
        for output in saved["outputs"].values():
            if sha256_file(Path(output["path"])) != output["sha256"]:
                raise ValueError("checkpoint output checksum mismatch")
        return {"task": task["id"], "resumed": True, "live_records": saved["audit"]["live_records"]}
    audit = collections.Counter()
    writers = {}
    digest = hashlib.sha256()
    for key, seq, raw, filename in task_records(task, audit):
        digest.update(struct.pack("<IQI", len(key), seq, len(raw)))
        digest.update(key)
        digest.update(raw)
        logical_bytes = key[1:] if key.startswith(b"k") else key
        try:
            logical = logical_bytes.decode("utf-8")
        except UnicodeError:
            logical = None
            audit["non_utf8_key"] += 1
        family = logical.split(":", 1)[0] if logical else ""
        table = TABLES.get(family, "auxiliary_records")
        try:
            decoded = msgpack.unpackb(raw, raw=False, strict_map_key=False)
            encoding = "msgpack"
        except (ValueError, TypeError, UnicodeError):
            try:
                decoded = raw.decode("utf-8")
                encoding = "utf8"
            except UnicodeError:
                decoded = {"__bytes_hex__": raw.hex()}
                encoding = "binary"
            audit["non_msgpack_values_preserved"] += 1
        base = {"source_db": task["source_db"], "source_file": filename, "source_sequence": seq,
            "physical_key": key, "logical_key": logical, "payload_encoding": encoding, "payload_raw": raw}
        if table not in writers:
            writers[table] = TableWriter(root, table, task["id"])
        writers[table].append(base, decoded, audit)
    outputs = {name: writer.finish() for name, writer in writers.items()}
    if audit["input_business_versions"] != audit["live_records"] + audit["older_or_duplicate_versions_removed"] + audit["latest_tombstones_removed"]:
        raise ValueError("source accounting does not reconcile")
    report = {"task": task["id"], "task_fingerprint": task["fingerprint"], "audit": dict(audit), "outputs": outputs,
        "logical_stream_sha256": digest.hexdigest(), "elapsed_seconds": round(time.monotonic() - started, 3)}
    report["audit"].setdefault("live_records", 0)
    atomic_json(done, report)
    return {"task": task["id"], "live_records": audit["live_records"], "seconds": report["elapsed_seconds"]}


def run_export(inventories, output, workers, limit_tasks):
    output = output.resolve()
    source = Path(inventories[0]["path"]).parent.resolve()
    formal = Path(__file__).resolve().parents[1] / "data"
    if output == source or source in output.parents or output == formal or formal in output.parents:
        raise ValueError("output must be isolated from snapshot and formal DATA_DIR")
    output.mkdir(parents=True, exist_ok=True)
    (output / "checkpoints").mkdir(exist_ok=True)
    inventory_path = output / "source_inventory.json"
    if not inventory_path.exists():
        for inv in inventories:
            paths = [Path(inv["path"]) / "CURRENT", Path(inv["path"]) / inv["manifest"]] + [
                Path(f["path"]) for f in inv["files"]] + [Path(p) for p in inv["wal_files"]]
            inv["source_checksums"] = {str(path): sha256_file(path) for path in paths}
        atomic_json(inventory_path, inventories)
    else:
        saved = json.loads(inventory_path.read_text())
        for old, current in zip(saved, inventories, strict=True):
            if {k: v for k, v in old.items() if k != "source_checksums"} != current:
                raise ValueError("snapshot inventory changed")
            for path, expected in old["source_checksums"].items():
                if sha256_file(Path(path)) != expected:
                    raise ValueError(f"snapshot bytes changed: {path}")
        inventories = saved
    identity = hashlib.sha256(inventory_path.read_bytes() + Path(__file__).read_bytes()).hexdigest()
    tasks = []
    for inv in inventories:
        for number, (low, high) in enumerate(key_ranges()):
            files = [f for f in inv["files"] if overlaps(f, low, high)]
            wals = [p for p in inv["wal_files"] if Path(p).stat().st_size]
            if not files and not wals:
                continue
            task_id = f"{inv['source_db']}-{number:03d}"
            tasks.append({"id": task_id, "source_db": inv["source_db"], "files": files, "wal_files": wals,
                "low_hex": low.hex() if low is not None else None, "high_hex": high.hex() if high is not None else None,
                "output": str(output), "fingerprint": identity + ":" + task_id})
    # Small metadata/daily tasks first: early verification and useful partial outputs.
    tasks.sort(key=lambda t: (b"\xe5\x88\x86" in bytes.fromhex(t["low_hex"] or ""), sum(f["size"] for f in t["files"])))
    print(json.dumps({"event": "start", "tasks": len(tasks), "workers": workers, "output": str(output)}, ensure_ascii=False), flush=True)
    selected = tasks[:limit_tasks] if limit_tasks else tasks
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(export_task, task) for task in selected]
        for future in concurrent.futures.as_completed(futures):
            print(json.dumps({"event": "task_completed", **future.result()}, ensure_ascii=False), flush=True)
    atomic_json(output / ("export_complete.json" if not limit_tasks else "sample_complete.json"),
        {"status": "exported_pending_validation" if not limit_tasks else "sample_only", "snapshot_identity": identity,
         "task_ids": [t["id"] for t in selected], "total_tasks": len(tasks), "unix_time": time.time()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inventory", "sample", "export"])
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit-tasks", type=int, default=0)
    args = parser.parse_args()
    inventories = [inventory(args.snapshot / name) for name in ("data", "data1", "mydb")]
    if args.command == "inventory":
        print(json.dumps(inventories, ensure_ascii=False, indent=2))
    elif args.command == "export":
        if args.output is None:
            parser.error("export requires --output")
        run_export(inventories, args.output, args.workers, args.limit_tasks)
    else:
        for inv in inventories:
            print(inv["source_db"], "active_files", len(inv["files"]), "bytes", inv["active_bytes"], "wal", inv["wal_files"])
            if not inv["files"]:
                continue
            for item in (inv["files"][0], inv["files"][-1]):
                sst = SST(Path(item["path"]))
                for n, (key, seq, kind, value) in enumerate(sst.records()):
                    if n >= args.limit:
                        break
                    try:
                        decoded = msgpack.unpackb(value, raw=False, strict_map_key=False) if kind else None
                    except Exception as error:
                        decoded = f"{type(error).__name__}: {error}; hex={value[:80].hex()}"
                    print(item["path"], key, seq, kind, str(decoded)[:2000])
                print(dict(sst.audit))
                sst.close()


if __name__ == "__main__":
    main()
