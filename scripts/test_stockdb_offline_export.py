"""Self-contained fixtures: never open a live StockDB engine or real DATA_DIR."""
import collections
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

import stockdb_offline_export as e
import validate_stockdb_export as validator


def vi(number):
    result = bytearray()
    while number > 127:
        result.append((number & 127) | 128)
        number >>= 7
    result.append(number)
    return bytes(result)


def lp(value):
    return vi(len(value)) + value


def internal(key, sequence=1, kind=1):
    return key + struct.pack("<Q", sequence << 8 | kind)


def entries(rows):
    result = b""
    for key, value in rows:
        result += b"\0" + vi(len(key)) + vi(len(value)) + key + value
    return result + struct.pack("<II", 0, 1)


def block(payload, compressed=True):
    kind = 2 if compressed else 0
    data = e.zstandard.ZstdCompressor(write_content_size=True).compress(payload) if compressed else payload
    return data + bytes([kind]) + struct.pack("<I", e.masked_crc(data + bytes([kind])))


def table_bytes(rows):
    data = block(entries(rows))
    index_payload = entries([(rows[-1][0], vi(0) + vi(len(data) - 5))])
    index = block(index_payload)
    handles = vi(0) + vi(0) + vi(len(data)) + vi(len(index) - 5)
    return data + index + handles.ljust(40, b"\0") + struct.pack("<Q", e.MAGIC)


def log_bytes(payload, kind=1):
    return struct.pack("<IHB", e.masked_crc(bytes([kind]) + payload), len(payload), kind) + payload


class ReaderTests(unittest.TestCase):
    def test_varints_and_truncation(self):
        for number in (0, 127, 128, 8192, (1 << 64) - 1):
            self.assertEqual(e.varint(vi(number)), (number, len(vi(number))))
        for malformed in (b"\x80", b"\xff" * 10, vi(1 << 64)):
            with self.assertRaises(ValueError):
                e.varint(malformed)

    def test_prefix_block(self):
        rows = [(b"abc", b"one"), (b"xyz", b"two")]
        self.assertEqual(list(e.block_entries(entries(rows))), rows)
        with self.assertRaises(ValueError):
            list(e.block_entries(b"bad"))

    def test_sst_crc_bounds_and_index_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "000001.ldb"
            rows = [(internal(b"kidx:abc"), b""), (internal(b"ka", 3), b"v"), (internal(b"kb", 2), b"z")]
            path.write_bytes(table_bytes(rows))
            sst = e.SST(path)
            self.assertEqual(list(sst.records(lower_bound=b"ka", upper_bound=b"kb")), [(b"ka", 3, 1, b"v")])
            sst.close()
            broken = bytearray(path.read_bytes())
            broken[5] ^= 1
            path.write_bytes(broken)
            sst = e.SST(path)
            with self.assertRaisesRegex(ValueError, "CRC"):
                list(sst.records())
            sst.close()

    def test_manifest_replay_deletion_and_empty_db(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = table_bytes([(internal(b"ka"), b"x")])
            (root / "000002.ldb").write_bytes(raw)
            record = b"\x01" + lp(b"leveldb.BytewiseComparator") + b"\x02\x03\x04\x07"
            record += b"\x07\x01\x01" + vi(len(raw)) + lp(internal(b"ka")) + lp(internal(b"ka"))
            record += b"\x06\x01\x01"
            record += b"\x07\x01\x02" + vi(len(raw)) + lp(internal(b"ka")) + lp(internal(b"ka"))
            (root / "CURRENT").write_text("MANIFEST-000004\n")
            (root / "MANIFEST-000004").write_bytes(log_bytes(record))
            inv = e.inventory(root)
            self.assertEqual([f["number"] for f in inv["files"]], [2])
            self.assertEqual(inv["last_sequence"], 7)

    def test_wal_and_incomplete_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "000003.log"
            batch = struct.pack("<QI", 20, 2) + b"\x01" + lp(b"ka") + lp(b"x") + b"\0" + lp(b"kb")
            path.write_bytes(log_bytes(batch) + b"\1\2")
            audit = {}
            self.assertEqual(list(e.wal_records(path, audit)), [(b"ka", 20, 1, b"x"), (b"kb", 21, 0, b"")])
            self.assertTrue(audit["incomplete_tails"])

    def test_fragmented_wal_and_bad_crc_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "000003.log"
            value = b"x" * 40000
            batch = struct.pack("<QI", 25, 1) + b"\1" + lp(b"ka") + lp(value)
            cut = e.BLOCK_SIZE - 7
            path.write_bytes(log_bytes(batch[:cut], 2) + log_bytes(batch[cut:], 4))
            self.assertEqual(list(e.wal_records(path, {})), [(b"ka", 25, 1, value)])
            corrupted = bytearray(path.read_bytes())
            corrupted[-1] ^= 1
            path.write_bytes(corrupted)
            with self.assertRaisesRegex(ValueError, "CRC"):
                list(e.wal_records(path, {}))

    def test_pure_secondary_index_block_is_skipped_but_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "000001.ldb"
            chunks = [block(entries([(internal(b"ka"), b"business")])),
                block(entries([(internal(b"kidx:a"), b"")])),
                block(entries([(internal(b"kidx:b"), b"")])),
                block(entries([(internal(b"kz"), b"last")]))]
            offset = 0
            index_rows = []
            for chunk, key in zip(chunks, (b"ka", b"kidx:a", b"kidx:b", b"kz")):
                index_rows.append((internal(key), vi(offset) + vi(len(chunk) - 5)))
                offset += len(chunk)
            index = block(entries(index_rows))
            footer = (vi(0) + vi(0) + vi(offset) + vi(len(index) - 5)).ljust(40, b"\0") + struct.pack("<Q", e.MAGIC)
            path.write_bytes(b"".join(chunks) + index + footer)
            sst = e.SST(path)
            self.assertEqual([r[0] for r in sst.records()], [b"ka", b"kz"])
            self.assertEqual(sst.audit["secondary_index_blocks_skipped"], 1)
            self.assertEqual(sst.audit["crc_verified_blocks"], 5)
            sst.close()

    def test_latest_sequence_tombstone_and_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p1, p2 = root / "000001.ldb", root / "000002.ldb"
            p1.write_bytes(table_bytes([(internal(b"ka", 2), b"old"), (internal(b"kb", 5), b"x")]))
            p2.write_bytes(table_bytes([(internal(b"ka", 3), b"new"), (internal(b"kb", 6, 0), b"")]))
            task = {"files": [{"path": str(p1)}, {"path": str(p2)}], "low_hex": None, "high_hex": None, "wal_files": []}
            audit = collections.Counter()
            self.assertEqual([(k, s, v) for k, s, v, _ in e.task_records(task, audit)], [(b"ka", 3, b"new")])
            self.assertEqual(audit["older_or_duplicate_versions_removed"], 2)
            self.assertEqual(audit["latest_tombstones_removed"], 1)
            p2.write_bytes(table_bytes([(internal(b"ka", 2), b"different")]))
            with self.assertRaisesRegex(ValueError, "conflicting"):
                list(e.task_records(task, collections.Counter()))

    def test_parquet_roundtrip_unknown_fields_resume_and_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "checkpoints").mkdir()
            path = root / "000001.ldb"
            native = {"code": "000001", "date": 20260825103000, "open": 10.0, "close": 10.1,
                "high": 10.2, "low": 9.9, "volume": 123, "amount": 1234, "unknown": 27}
            raw = e.msgpack.packb(native, use_bin_type=True)
            path.write_bytes(table_bytes([(internal("k分钟k:000001:20260825103000".encode(), 99), raw)]))
            task = {"files": [{"path": str(path)}], "low_hex": None, "high_hex": None, "wal_files": [],
                "id": "fixture", "fingerprint": "fixture-v1", "source_db": "fixture", "output": str(root)}
            e.export_task(task)
            parquet = root / "tables/minute_bars/fixture.parquet"
            rows = e.pq.read_table(parquet).to_pylist()
            self.assertEqual(rows[0]["payload_raw"], raw)
            self.assertEqual(rows[0]["trade_date"], 20260825)
            self.assertEqual(rows[0]["volume"], 123)
            self.assertEqual(rows[0]["extra_json"], '{"unknown":27}')
            self.assertTrue(e.export_task(task)["resumed"])
            with parquet.open("ab") as stream:
                stream.write(b"tamper")
            with self.assertRaisesRegex(ValueError, "checksum"):
                e.export_task(task)

    def test_ranges_partition_universe(self):
        ranges = e.key_ranges()
        self.assertIsNone(ranges[0][0])
        self.assertIsNone(ranges[-1][1])
        for left, right in zip(ranges, ranges[1:]):
            self.assertEqual(left[1], right[0])

    def test_independent_validator_digest_and_page_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "checkpoints").mkdir()
            source = root / "000001.ldb"
            raw = e.msgpack.packb({"code": "000001", "date": 20260825103000,
                "open": 10.0, "close": 10.1, "high": 10.2, "low": 10.0, "volume": 200, "amount": 2010})
            source.write_bytes(table_bytes([(internal("k分钟k:000001:20260825103000".encode(), 99), raw)]))
            task = {"files": [{"path": str(source)}], "wal_files": [], "low_hex": None, "high_hex": None,
                "source_db": "fixture", "id": "fixture-001", "fingerprint": "v1", "output": str(root)}
            e.export_task(task)
            checkpoint = root / "checkpoints/fixture-001.json"
            checked = validator.validate_task(checkpoint)
            self.assertEqual(checked["records"], 1)
            self.assertTrue(checked["logical_stream_sha256_verified"])
            damaged = e.json.loads(checkpoint.read_text())
            damaged["logical_stream_sha256"] = "0" * 64
            checkpoint.write_text(e.json.dumps(damaged))
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                validator.validate_task(checkpoint)


if __name__ == "__main__":
    unittest.main()
