"""Repair contracts: incomplete bytes must never become a guessed value."""
import tempfile
import unittest
from pathlib import Path

import stockdb_offline_export as e
import repair_stockdb_records as r


def record(raw, key="分钟k:000001:20260130132500", table="minute_bars"):
    parts = key.split(":")
    return {"source_table": table, "source_db": "data", "source_file": "test.ldb",
            "source_sequence": 1, "logical_key": key, "code_from_key": parts[1],
            "date_from_key": int(parts[2]), "payload_raw": raw}


BAR = {"code": "000001", "date": 20260130132500, "open": 10.9,
       "close": 10.89, "high": 10.9, "low": 10.89}


class RepairTests(unittest.TestCase):
    def test_real_truncated_numeric(self):
        raw = bytes.fromhex("88a4636f6465a6303030303031a464617465cf0000126d2ddc1214a46f70656ecb4025cccccccccccda5636c6f7365cb4025c7ae147ae148a468696768cb4025cccccccccccda36c6f77cb4025c7ae147ae148a6766f6c756d65ce")
        with self.assertRaises(ValueError):
            e.msgpack.unpackb(raw)
        out = r.repair_record(record(raw))
        self.assertEqual(out["repair_status"], "exact_prefix_partial_core")
        self.assertEqual(out["close"], 10.89)
        self.assertIsNone(out["volume"])
        self.assertIsNone(out["amount"])
        self.assertEqual(out["missing_core_fields"], ["volume", "amount"])
        self.assertEqual(out["pending_key"], "volume")
        self.assertEqual(out["payload_raw"], raw)

    def test_complete_map(self):
        raw = e.msgpack.packb({**BAR, "volume": 0, "amount": 0})
        out = r.repair_record(record(raw))
        self.assertTrue(out["core_fields_complete"])
        self.assertFalse(out["source_truncated"])
        self.assertEqual(out["volume"], 0)

    def test_incomplete_key_and_value(self):
        complete = e.msgpack.packb({**BAR, "volume": 500000})
        for n in (1, 2, 3, 4, 6):
            out = r.repair_record(record(complete[:-n]))
            self.assertNotIn("volume", e.msgpack.unpackb(out["recovered_pairs_msgpack"]))
            self.assertIsNone(out["volume"])

    def test_daily_core_complete_but_optional_tail_lost(self):
        bar = {**BAR, "date": 20260130, "volume": 300, "amount": 3000, "pb": 10000}
        out = r.repair_record(record(e.msgpack.packb(bar)[:-1], "日k:000001:20260130", "daily_bars"))
        self.assertEqual(out["repair_status"], "exact_prefix_core_complete")
        self.assertTrue(out["source_truncated"])
        self.assertIsNone(out["pb"])

    def test_duplicate_and_nonstring_keys_rejected(self):
        for raw in (b'\x82\xa1x\x01\xa1x\x02', e.msgpack.packb({1: "bad"})):
            with self.assertRaises(ValueError):
                r.decode_prefix(raw)

    def test_wrong_container_trailing_bytes_rejected(self):
        for raw in (e.msgpack.packb([1, 2]), e.msgpack.packb(BAR) + b'\x00', b'\xc1'):
            with self.assertRaises(ValueError):
                r.decode_prefix(raw)

    def test_identity_type_and_date_guard(self):
        for change in ({"code": 1}, {"code": "000002"}, {"date": True}, {"date": 20260130132600}):
            self.assertFalse(r.repair_record(record(e.msgpack.packb({**BAR, **change})))["eligible_overlay"])

    def test_invalid_numeric_ohlc_and_precision_guard(self):
        for change in ({"close": True}, {"close": float("nan")}, {"high": 1},
                       {"volume": -1}, {"volume": 2**53 + 1}, {"low": float("inf")}):
            out = r.repair_record(record(e.msgpack.packb({**BAR, **change})))
            self.assertFalse(out["eligible_overlay"])

    def test_preserve_unknown_complete_fields(self):
        out = r.repair_record(record(e.msgpack.packb({**BAR, "unknown": [1, "x"]})))
        self.assertEqual(e.msgpack.unpackb(out["recovered_pairs_msgpack"])["unknown"], [1, "x"])

    def test_every_byte_cut_never_invents_value(self):
        fields = {**BAR, "volume": 12345678, "amount": 134567890.75,
                  "unknown": ["longer value", 1234567890]}
        raw = e.msgpack.packb(fields, use_bin_type=True)
        for end in range(1, len(raw) + 1):
            partial = r.decode_prefix(raw[:end])
            self.assertLessEqual(partial["complete_prefix_bytes"], end)
            for key, value in partial["fields"].items():
                self.assertEqual(value, fields[key])
            self.assertEqual(list(partial["fields"]), list(fields)[:len(partial["fields"])])
            self.assertEqual(partial["source_truncated"], end < len(raw))

    def test_atomic_roundtrip_and_overwrite_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "input.parquet"
            e.pq.write_table(e.pa.Table.from_pylist([record(e.msgpack.packb({**BAR, "volume": 10000})[:-1])]), source)
            before = e.sha256_file(source)
            result = r.run(source, Path(d) / "out")
            self.assertEqual(result["rows"], 1)
            self.assertEqual(e.sha256_file(source), before)
            with self.assertRaises(FileExistsError):
                r.run(source, Path(d) / "out")
            self.assertEqual(e.pq.ParquetFile(Path(d) / "out/recovered_bar_fields.parquet").metadata.num_rows, 1)

    def test_duplicate_source_key_refused(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "input.parquet"
            row = record(e.msgpack.packb(BAR))
            e.pq.write_table(e.pa.Table.from_pylist([row, row]), source)
            with self.assertRaises(ValueError):
                r.run(source, Path(d) / "out")


if __name__ == "__main__":
    unittest.main()
