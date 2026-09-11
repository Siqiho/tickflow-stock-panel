#!/usr/bin/env python3
"""Fixture-only tests for scripts/offline_valuation_query.py.

Never writes the real QuantDB root or formal DATA_DIR. Overlay is not invoked
on the default query path; source nulls stay null.
"""
from __future__ import annotations

import importlib.util
import io
import json
import math
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime
from pathlib import Path

import polars as pl

SCRIPT = Path(__file__).resolve().parent / "offline_valuation_query.py"
SPEC = importlib.util.spec_from_file_location("offline_valuation_query", SCRIPT)
assert SPEC and SPEC.loader
q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(q)


def _write(root: Path, symbol: str, rows: list[dict], *, extra_cols: bool = True) -> Path:
    dest = root / "5_technical_derived" / "valuation" / f"{symbol}.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = []
    for row in rows:
        item = {
            "time": row.get("time"),
            "Symbol": row.get("Symbol", symbol),
            "close": row.get("close"),
            "total_capital": row.get("total_capital"),
            "circulating_capital": row.get("circulating_capital"),
            "total_mv": row.get("total_mv"),
            "float_mv": row.get("float_mv"),
            "pe_ttm": row.get("pe_ttm"),
            "pb": row.get("pb"),
            "ps_ttm": row.get("ps_ttm"),
        }
        if extra_cols:
            item.update(
                {
                    "net_profit_ttm": row.get("net_profit_ttm"),
                    "revenue_ttm": row.get("revenue_ttm"),
                    "equity": row.get("equity"),
                    "annual_net_profit": row.get("annual_net_profit"),
                    "pe_static": row.get("pe_static"),
                    "dividend_rate": row.get("dividend_rate"),
                }
            )
        payload.append(item)
    pl.DataFrame(payload).write_parquet(dest)
    return dest


def _row(
    day: str,
    symbol: str = "000001.SZ",
    *,
    close: float | None = 10.0,
    capital: float | None = 100.0,
    pe: float | None = 8.0,
    **extra: object,
) -> dict:
    payload = {
        "time": datetime.fromisoformat(day),
        "Symbol": symbol,
        "close": close,
        "total_capital": capital,
        "circulating_capital": capital,
        "total_mv": None if close is None or capital is None else close * capital,
        "float_mv": None if close is None or capital is None else close * capital,
        "pe_ttm": pe,
        "pb": 1.2,
        "ps_ttm": 0.8,
    }
    payload.update(extra)
    return payload


class OfflineValuationQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "quant_data"
        self.project = Path(self.tmp.name) / "project_data"
        (self.project / "reference" / "valuation_daily").mkdir(parents=True)
        self.addCleanup(self.tmp.cleanup)

    def test_does_not_import_app_or_datastore(self) -> None:
        imported = [name for name in sys.modules if name == "app" or name.startswith("app.")]
        self.assertEqual(imported, [])

    def test_main_path_query_is_legal_json_and_stable(self) -> None:
        path = _write(
            self.root,
            "000001.SZ",
            [_row("2026-08-12"), _row("2026-08-11", pe=-3.5)],
        )
        before = q.fingerprint(path)
        first = q.query_valuation(
            symbol="000001.SZ",
            start="2026-08-11",
            end="2026-08-12",
            limit=5,
            root=self.root,
        )
        second = q.query_valuation(
            symbol="000001.SZ",
            start="2026-08-11",
            end="2026-08-12",
            limit=5,
            root=self.root,
        )
        after = q.fingerprint(path)
        encoded = q.dumps(first)
        json.loads(encoded)
        self.assertNotRegex(encoded, r":\s*NaN\b")
        self.assertEqual(first, second)
        self.assertEqual(before, after)
        self.assertTrue(first["ok"])
        self.assertEqual(first["source"], "offline_quantdb")
        self.assertEqual(first["dataset"], "5_technical_derived/valuation")
        self.assertEqual(first["layout"], "by_symbol")
        self.assertEqual(first["count"], 2)
        self.assertEqual(first["data"][0]["date"], "2026-08-12")
        self.assertEqual(first["data"][1]["pe_ttm"], -3.5)
        self.assertIsNone(first["data"][0].get("pcf_ttm"))
        self.assertIn("pcf_ttm", first["missing_fields"])
        self.assertFalse(first["overlay"]["project_null_overlay"])
        self.assertFalse(first["overlay"]["stockdb_repair_loaded"])

    def test_empty_window_is_not_missing_file(self) -> None:
        _write(self.root, "000001.SZ", [_row("2026-01-04")])
        result = q.query_valuation(
            symbol="000001.SZ",
            start="2026-07-21",
            end="2026-08-12",
            root=self.root,
        )
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["code"], "valuation_offline_empty_window")
        self.assertEqual(result["count"], 0)

    def test_missing_root_and_file_are_distinct(self) -> None:
        with self.assertRaises(q.ValuationQueryError) as missing_root:
            q.query_valuation(symbol="000001.SZ", root=self.root / "nope")
        self.assertEqual(missing_root.exception.code, "valuation_offline_root_missing")
        self.root.mkdir()
        with self.assertRaises(q.ValuationQueryError) as missing_dataset:
            q.query_valuation(symbol="000001.SZ", root=self.root)
        self.assertEqual(missing_dataset.exception.code, "valuation_offline_dataset_missing")
        (self.root / "5_technical_derived" / "valuation").mkdir(parents=True)
        with self.assertRaises(q.ValuationQueryError) as missing_file:
            q.query_valuation(symbol="000001.SZ", root=self.root)
        self.assertEqual(missing_file.exception.code, "valuation_offline_not_found")
        with self.assertRaises(q.ValuationQueryError) as unconfigured:
            q.resolve_root("")
        self.assertEqual(unconfigured.exception.code, "valuation_offline_unconfigured")

    def test_missing_fields_corrupt_duplicate_permission(self) -> None:
        dest = _write(self.root, "000001.SZ", [_row("2026-08-12")])
        slim = pl.read_parquet(dest).drop("pe_ttm")
        slim.write_parquet(dest)
        with self.assertRaises(q.ValuationQueryError) as schema:
            q.query_valuation(symbol="000001.SZ", root=self.root)
        self.assertEqual(schema.exception.code, "valuation_offline_invalid_schema")

        dest.write_bytes(b"not-a-parquet")
        with self.assertRaises(q.ValuationQueryError) as corrupt:
            q.query_valuation(symbol="000001.SZ", root=self.root)
        self.assertEqual(corrupt.exception.code, "valuation_offline_unreadable")

        _write(
            self.root,
            "000338.SZ",
            [_row("2026-08-12", "000338.SZ"), _row("2026-08-12", "000338.SZ")],
        )
        with self.assertRaises(q.ValuationQueryError) as duplicate:
            q.query_valuation(symbol="000338.SZ", root=self.root)
        self.assertEqual(duplicate.exception.code, "valuation_offline_duplicate_key")

        locked = _write(self.root, "600519.SH", [_row("2026-08-12", "600519.SH")])
        os.chmod(locked, 0)
        self.addCleanup(lambda: os.chmod(locked, stat.S_IRUSR | stat.S_IWUSR))
        with self.assertRaises(q.ValuationQueryError) as denied:
            q.query_valuation(symbol="600519.SH", root=self.root)
        self.assertEqual(denied.exception.code, "valuation_offline_permission")

    def test_invalid_symbol_date_limit_and_symlink_escape(self) -> None:
        _write(self.root, "000001.SZ", [_row("2026-08-12")])
        for symbol in ("../000001.SZ", "000001", "000001.SZ/../../x", "etc/passwd"):
            with self.assertRaises(q.ValuationQueryError) as exc:
                q.query_valuation(symbol=symbol, root=self.root)
            self.assertEqual(exc.exception.code, "valuation_offline_invalid_symbol")
        with self.assertRaises(q.ValuationQueryError) as bad_date:
            q.query_valuation(symbol="000001.SZ", start="2026/08/12", root=self.root)
        self.assertEqual(bad_date.exception.code, "valuation_offline_invalid_date")
        with self.assertRaises(q.ValuationQueryError) as inverted:
            q.query_valuation(
                symbol="000001.SZ",
                start="2026-08-12",
                end="2026-07-21",
                root=self.root,
            )
        self.assertEqual(inverted.exception.code, "valuation_offline_invalid_date")
        with self.assertRaises(q.ValuationQueryError) as bad_limit:
            q.query_valuation(symbol="000001.SZ", limit=0, root=self.root)
        self.assertEqual(bad_limit.exception.code, "valuation_offline_invalid_limit")

        outside = Path(self.tmp.name) / "outside.parquet"
        pl.DataFrame({"x": [1]}).write_parquet(outside)
        link = self.root / "5_technical_derived" / "valuation" / "300750.SZ.parquet"
        link.symlink_to(outside)
        with self.assertRaises(q.ValuationQueryError) as escaped:
            q.query_valuation(symbol="300750.SZ", root=self.root)
        self.assertEqual(escaped.exception.code, "valuation_offline_symlink_escape")

    def test_parent_and_file_symlink_escapes_fail_closed(self) -> None:
        outside_derived = Path(self.tmp.name) / "escape_derived"
        _write(outside_derived, "000001.SZ", [_row("2026-08-12")])
        root_derived = Path(self.tmp.name) / "root_derived"
        root_derived.mkdir()
        (root_derived / "5_technical_derived").symlink_to(
            outside_derived / "5_technical_derived"
        )
        with self.assertRaises(q.ValuationQueryError) as derived_exc:
            q.query_valuation(symbol="000001.SZ", root=root_derived)
        self.assertEqual(derived_exc.exception.code, "valuation_offline_symlink_escape")

        packaged = _write(Path(self.tmp.name) / "escape_pkg", "000001.SZ", [_row("2026-08-12")])
        root_val = Path(self.tmp.name) / "root_valuation"
        (root_val / "5_technical_derived").mkdir(parents=True)
        (root_val / "5_technical_derived" / "valuation").symlink_to(packaged.parent)
        with self.assertRaises(q.ValuationQueryError) as val_exc:
            q.query_valuation(symbol="000001.SZ", root=root_val)
        self.assertEqual(val_exc.exception.code, "valuation_offline_symlink_escape")

        _write(self.root, "000001.SZ", [_row("2026-08-12")])
        outside_file = Path(self.tmp.name) / "outside_file.parquet"
        pl.DataFrame({"x": [1]}).write_parquet(outside_file)
        link = self.root / "5_technical_derived" / "valuation" / "300750.SZ.parquet"
        link.symlink_to(outside_file)
        with self.assertRaises(q.ValuationQueryError) as file_exc:
            q.query_valuation(symbol="300750.SZ", root=self.root)
        self.assertEqual(file_exc.exception.code, "valuation_offline_symlink_escape")

    def test_empty_or_wrong_symbol_is_rejected_not_rewritten(self) -> None:
        _write(self.root, "000001.SZ", [_row("2026-08-12", Symbol="")])
        with self.assertRaises(q.ValuationQueryError) as empty:
            q.query_valuation(symbol="000001.SZ", root=self.root)
        self.assertEqual(empty.exception.code, "valuation_offline_invalid_identity")
        self.assertIn("空", empty.exception.message)

        _write(self.root, "000001.SZ", [_row("2026-08-12", "000338.SZ")])
        with self.assertRaises(q.ValuationQueryError) as wrong:
            q.query_valuation(symbol="000001.SZ", root=self.root)
        self.assertEqual(wrong.exception.code, "valuation_offline_invalid_identity")
        self.assertIn("000338.SZ", wrong.exception.message)

        _write(
            self.root,
            "000001.SZ",
            [_row("2026-08-12", "000001.SZ"), _row("2026-08-11", "000338.SZ")],
        )
        with self.assertRaises(q.ValuationQueryError) as mixed:
            q.query_valuation(symbol="000001.SZ", root=self.root)
        self.assertEqual(mixed.exception.code, "valuation_offline_invalid_identity")

    def test_strict_schema_rejects_bad_types_and_duplicate_null_time(self) -> None:
        dest = self.root / "5_technical_derived" / "valuation" / "000001.SZ.parquet"
        dest.parent.mkdir(parents=True)
        good = {
            "Symbol": ["000001.SZ"],
            "close": [10.0],
            "total_capital": [100.0],
            "circulating_capital": [100.0],
            "total_mv": [1000.0],
            "float_mv": [1000.0],
            "pe_ttm": [8.0],
            "pb": [1.2],
            "ps_ttm": [0.8],
        }
        pl.DataFrame({"time": [date(2026, 8, 12)], **good}).write_parquet(dest)
        dated = q.query_valuation(symbol="000001.SZ", root=self.root)
        self.assertTrue(dated["ok"])
        self.assertEqual(dated["data"][0]["date"], "2026-08-12")

        pl.DataFrame({"time": ["2026-08-12"], **good}).write_parquet(dest)
        with self.assertRaises(q.ValuationQueryError) as bad_time:
            q.query_valuation(symbol="000001.SZ", root=self.root)
        self.assertEqual(bad_time.exception.code, "valuation_offline_invalid_schema")

        numeric_as_str = dict(good)
        numeric_as_str["close"] = ["10.0"]
        pl.DataFrame({"time": [datetime(2026, 8, 12)], **numeric_as_str}).write_parquet(dest)
        with self.assertRaises(q.ValuationQueryError) as bad_num:
            q.query_valuation(symbol="000001.SZ", root=self.root)
        self.assertEqual(bad_num.exception.code, "valuation_offline_invalid_schema")

        two = {key: value * 2 if key != "Symbol" else ["000001.SZ", "000001.SZ"] for key, value in good.items()}
        two["time"] = pl.Series("time", [None, None], dtype=pl.Datetime("ns"))
        pl.DataFrame(two).write_parquet(dest)
        with self.assertRaises(q.ValuationQueryError) as dup_null:
            q.query_valuation(symbol="000001.SZ", root=self.root)
        self.assertIn(
            dup_null.exception.code,
            {"valuation_offline_invalid_identity", "valuation_offline_invalid_schema"},
        )

    def test_strict_string_dates_and_integer_limit(self) -> None:
        _write(self.root, "000001.SZ", [_row("2026-08-12")])
        with self.assertRaises(q.ValuationQueryError) as suffix:
            q.query_valuation(symbol="000001.SZ", start="2026-08-12xxx", root=self.root)
        self.assertEqual(suffix.exception.code, "valuation_offline_invalid_date")
        with self.assertRaises(q.ValuationQueryError) as iso_tail:
            q.query_valuation(
                symbol="000001.SZ",
                start="2026-08-12T00:00:00",
                root=self.root,
            )
        self.assertEqual(iso_tail.exception.code, "valuation_offline_invalid_date")
        from_date = q.query_valuation(
            symbol="000001.SZ",
            start=date(2026, 8, 12),
            end=datetime(2026, 8, 12, 15, 0, 0),
            root=self.root,
        )
        self.assertTrue(from_date["ok"])
        with self.assertRaises(q.ValuationQueryError) as bool_limit:
            q.query_valuation(symbol="000001.SZ", limit=True, root=self.root)
        self.assertEqual(bool_limit.exception.code, "valuation_offline_invalid_limit")
        with self.assertRaises(q.ValuationQueryError) as float_limit:
            q.query_valuation(symbol="000001.SZ", limit=1.9, root=self.root)
        self.assertEqual(float_limit.exception.code, "valuation_offline_invalid_limit")
        with self.assertRaises(q.ValuationQueryError) as one_point_zero:
            q.query_valuation(symbol="000001.SZ", limit=1.0, root=self.root)
        self.assertEqual(one_point_zero.exception.code, "valuation_offline_invalid_limit")

    def test_units_remain_unverified_and_identity_excludes_inf(self) -> None:
        _write(
            self.root,
            "000001.SZ",
            [
                _row("2026-08-12", close=10.0, capital=10.0),
                _row("2026-08-11", close=float("inf"), capital=10.0),
            ],
        )
        info = q.inspect_symbol(self.root, "000001.SZ")
        identity = info["share_market_value"]
        self.assertEqual(identity["units"], "unknown/unverified")
        self.assertEqual(identity["inference"], "unknown")
        self.assertEqual(identity["checked_rows"], 1)
        self.assertEqual(identity["exact_rows"], 1)
        self.assertTrue(identity["identity_consistent_on_checked_rows"])
        self.assertFalse(identity["conversion_applied"])
        encoded = q.dumps(info)
        self.assertNotIn("inferred_share_and_cny", encoded)
        self.assertNotIn("inferred as shares", info["unit_note"])
        self.assertIn("unknown/unverified", info["unit_note"])
        self.assertIn("not confirmed by appearance", info["unit_note"])

    def test_optional_absent_is_not_claimed_in_original_fields(self) -> None:
        _write(self.root, "000001.SZ", [_row("2026-08-12")], extra_cols=False)
        result = q.query_valuation(symbol="000001.SZ", root=self.root)
        original = result["fields"]["original"]
        self.assertIn("close", original)
        self.assertNotIn("dividend_rate", original)
        self.assertNotIn("net_profit_ttm", original)
        self.assertIn("dividend_rate", result["fields"]["optional_absent"])
        self.assertIn("dividend_rate", result["optional_absent"])
        self.assertNotIn("dividend_rate", result["fields"]["optional_present"])
        self.assertIn("pcf_ttm", result["missing_fields"])
        self.assertNotIn("dividend_rate", result["missing_fields"])
        self.assertNotIn("dividend_rate", result["fields"]["missing_versus_project"])
        self.assertEqual(result["fields"]["original"], original)

    def test_nan_is_legal_json_and_keeps_anomaly_mark(self) -> None:
        _write(
            self.root,
            "000001.SZ",
            [_row("2026-08-12", pe=float("nan"), close=11.0, capital=10.0)],
        )
        result = q.query_valuation(symbol="000001.SZ", root=self.root)
        encoded = q.dumps(result)
        json.loads(encoded)
        self.assertIsNone(result["data"][0]["pe_ttm"])
        self.assertEqual(result["data"][0]["value_flags"]["pe_ttm"], "nan")
        kinds = {item["kind"] for item in result["quality"]["anomalies"]}
        self.assertIn("nan", kinds)
        self.assertTrue(math.isnan(float("nan")))

    def test_nulls_are_not_filled_and_overlay_is_not_used(self) -> None:
        _write(
            self.root,
            "000001.SZ",
            [_row("2026-08-12", close=10.0, capital=None, pe=None)],
        )
        called = {"overlay": False}
        original = q.apply_overlay

        def _guard(*args, **kwargs):
            called["overlay"] = True
            return original(*args, **kwargs)

        q.apply_overlay = _guard  # type: ignore[method-assign]
        self.addCleanup(lambda: setattr(q, "apply_overlay", original))
        result = q.query_valuation(symbol="000001.SZ", root=self.root)
        row = result["data"][0]
        self.assertIsNone(row["pe_ttm"])
        self.assertIsNone(row["total_share"])
        self.assertIsNone(row["total_mv"])
        self.assertFalse(called["overlay"])
        with self.assertRaises(RuntimeError):
            q.apply_overlay("must-not-run")

    def test_audit_summary_default_writes_nothing(self) -> None:
        for symbol in q.FIXED_SAMPLES:
            _write(self.root, symbol, [_row("2026-07-21", symbol)])
        artifact = Path(self.tmp.name) / "artifact"
        before = list(self.root.rglob("*"))
        audit = q.audit_valuation(root=self.root, project_data_dir=self.project)
        summary = q.summarize_audit(audit)
        after = list(self.root.rglob("*"))
        self.assertEqual(before, after)
        self.assertFalse(artifact.exists())
        self.assertEqual(audit["reconcile"]["package_keys"], 4)
        self.assertEqual(audit["reconcile"]["project_keys"], 0)
        self.assertEqual(summary["mode"], "summary")
        self.assertFalse(audit["overlay"]["default_overlay"])

    def test_reconcile_does_not_treat_project_null_as_equal_or_zero(self) -> None:
        _write(self.root, "000001.SZ", [_row("2026-07-21", close=10.84, capital=100.0, pe=5.0)])
        part = (
            self.project
            / "reference"
            / "valuation_daily"
            / "date=2026-07-21"
            / "part.parquet"
        )
        part.parent.mkdir(parents=True)
        pl.DataFrame(
            {
                "symbol": ["000001.SZ"],
                "trade_date": [date(2026, 7, 21)],
                "close": [10.84],
                "pe_ttm": [None],
                "pb": [None],
                "ps_ttm": [None],
                "total_mv": [None],
                "float_mv": [None],
                "total_share": [None],
                "float_share": [None],
                "shares_pit_safe": [False],
                "unit_version": ["valuation_daily_v2"],
            }
        ).write_parquet(part)
        report = q.reconcile_project(
            root=self.root,
            project_data_dir=self.project,
            symbols=("000001.SZ",),
        )
        self.assertEqual(report["common_keys"], 1)
        pe = report["comparable_fields"]["pe_ttm"]
        close = report["comparable_fields"]["close"]
        self.assertEqual(close["equal_when_both_present"], 1)
        self.assertEqual(pe["package_present_project_null"], 1)
        self.assertFalse(pe["null_equals_value"])
        self.assertFalse(pe["null_filled_with_zero"])
        self.assertFalse(report["join_boundary"]["direct_concat"])

    def test_write_evidence_rejects_other_paths(self) -> None:
        with self.assertRaises(q.ValuationQueryError) as denied:
            q.write_evidence(Path(self.tmp.name) / "nope", {"audit": {}})
        self.assertEqual(denied.exception.code, "valuation_offline_evidence_path_denied")

    def test_cli_query_and_audit_stdout_only(self) -> None:
        _write(self.root, "000001.SZ", [_row("2026-08-12")])
        for symbol in q.FIXED_SAMPLES[1:]:
            _write(self.root, symbol, [_row("2026-08-12", symbol)])
        with redirect_stdout(io.StringIO()) as stdout:
            code = q.main(
                [
                    "--symbol",
                    "000001.SZ",
                    "--root",
                    str(self.root),
                    "--limit",
                    "1",
                ]
            )
        self.assertEqual(code, 0)
        json.loads(stdout.getvalue())
        with redirect_stdout(io.StringIO()):
            code = q.main(
                [
                    "--audit",
                    "--summary",
                    "--root",
                    str(self.root),
                    "--project-data-dir",
                    str(self.project),
                ]
            )
        self.assertEqual(code, 0)
        self.assertFalse((Path(self.tmp.name) / "docs").exists())


if __name__ == "__main__":
    unittest.main()
