from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl

from app.data_catalog.definitions import DATASET_DEFINITIONS
from app.data_catalog.scanner import CatalogScanner


def _write_parquet(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path)
    return path


def _write_lineage(
    data_dir: Path,
    dataset_root: str,
    artifact: Path,
    *,
    unit_version: str = "canonical_daily_v1",
    source: str = "test-writer",
) -> Path:
    path = (
        data_dir
        / "lineage"
        / dataset_root
        / f"{artifact.stem}-{len(list((data_dir / 'lineage').rglob('*.json'))) if (data_dir / 'lineage').exists() else 0}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source": source,
                "unit_version": unit_version,
                "quality": "success",
                "target_artifact": artifact.relative_to(data_dir).as_posix(),
            }
        ),
        encoding="utf-8",
    )
    return path


def _bar(symbol: str, day: date = date(2026, 7, 21)) -> dict:
    return {
        "symbol": symbol,
        "date": day,
        "open": 10.0,
        "high": 11.0,
        "low": 9.0,
        "close": 10.5,
        "volume": 12.0,
        "amount": 1_200.0,
        "change_pct": 1.0,
    }


def _instrument(symbol: str, name: str, asset_type: str) -> dict:
    return {
        "symbol": symbol,
        "name": name,
        "code": symbol.rsplit(".", 1)[0],
        "exchange": symbol.rsplit(".", 1)[-1],
        "region": "CN",
        "type": asset_type,
        "listing_date": date(2020, 1, 1),
        "total_shares": 1_000.0,
        "float_shares": 900.0,
        "tick_size": 0.01,
        "limit_up": 11.0,
        "limit_down": 9.0,
        "as_of": date(2026, 7, 21),
    }


def test_full_scan_is_one_walk_exact_bytes_and_assigns_every_file_once(
    tmp_path: Path, tmp_path_factory, monkeypatch
) -> None:
    _write_parquet(
        tmp_path / "instruments" / "part.parquet", [_instrument("600000.SH", "浦发", "stock")]
    )
    _write_parquet(
        tmp_path / "kline_daily" / "date=2026-07-21" / "part.parquet", [_bar("600000.SH")]
    )
    (tmp_path / "kline_daily" / "notes.txt").write_text("owned non-parquet", encoding="utf-8")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "runtime.log").write_bytes(b"log-bytes")
    (tmp_path / "misc").mkdir()
    (tmp_path / "misc" / "unknown.bin").write_bytes(b"other")
    symlink = tmp_path / "misc" / "link.bin"
    symlink.symlink_to(tmp_path / "misc" / "unknown.bin")
    outside = tmp_path_factory.mktemp("catalog-full-outside")
    (outside / "escaped.bin").write_bytes(b"must-not-be-scanned")
    (tmp_path / "misc" / "outside-dir").symlink_to(outside, target_is_directory=True)

    import app.data_catalog.scanner as scanner_module

    original_walk = os.walk
    walked: list[Path] = []

    def counting_walk(path, *args, **kwargs):
        walked.append(Path(path))
        return original_walk(path, *args, **kwargs)

    monkeypatch.setattr(scanner_module.os, "walk", counting_walk)
    run_ids = {
        definition.descriptor.dataset_id: f"run-{definition.descriptor.dataset_id}"
        for definition in DATASET_DEFINITIONS
    }

    snapshot = CatalogScanner(tmp_path).scan_all(run_ids)

    regular_files = [
        path for path in tmp_path.rglob("*") if path.is_file() and not path.is_symlink()
    ]
    assert walked == [tmp_path]
    assert snapshot.storage.total_bytes == sum(path.stat().st_size for path in regular_files)
    assert snapshot.storage.total_bytes == (
        snapshot.storage.managed_data_bytes + snapshot.storage.operational_bytes
    )
    assert (
        sum(category.bytes for category in snapshot.storage.categories)
        == snapshot.storage.total_bytes
    )
    assert sum(category.files for category in snapshot.storage.categories) == len(regular_files)
    artifact_paths = [
        artifact.path for result in snapshot.datasets.values() for artifact in result.artifacts
    ]
    assert len(artifact_paths) == len(set(artifact_paths))
    assert snapshot.datasets["stock_daily"].state.managed_bytes == sum(
        path.stat().st_size for path in (tmp_path / "kline_daily").rglob("*") if path.is_file()
    )
    assert {category.key for category in snapshot.storage.categories} >= {
        "stocks",
        "etfs",
        "indices",
        "quote_snapshot",
        "sealed_l1",
        "depth5",
        "pools",
        "financials",
        "ext_data",
        "lineage",
        "job_store",
        "logs",
        "user_data",
        "control",
        "operational_other",
    }


def test_dataset_and_lineage_symlink_roots_never_escape_data_dir(
    tmp_path: Path, tmp_path_factory
) -> None:
    outside_data = tmp_path_factory.mktemp("catalog-dataset-outside")
    _write_parquet(outside_data / "part.parquet", [_bar("600000.SH")])
    (tmp_path / "kline_daily").symlink_to(outside_data, target_is_directory=True)

    outside_lineage = tmp_path_factory.mktemp("catalog-lineage-outside")
    (outside_lineage / "failed.json").write_text(
        json.dumps(
            {
                "source": "outside",
                "unit_version": "cn_market_v1",
                "quality": "failed",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "lineage").mkdir()
    (tmp_path / "lineage" / "stock_daily").symlink_to(outside_lineage, target_is_directory=True)

    result = CatalogScanner(tmp_path).scan_dataset("stock_daily", "run-stock")

    assert result.state.row_count == 0
    assert result.state.managed_bytes == 0
    assert result.state.payload["file_count"] == 0
    assert result.state.payload["scan_errors"] == []
    assert result.state.quality_status == "unknown"
    assert result.artifacts == ()
    assert result.lineage == ()


def test_full_scan_separates_stock_index_etf_and_all_five_financial_tables(tmp_path: Path) -> None:
    _write_parquet(tmp_path / "kline_daily" / "part.parquet", [_bar("600000.SH")])
    _write_parquet(tmp_path / "kline_index_daily" / "part.parquet", [_bar("000001.SH")])
    _write_parquet(tmp_path / "kline_etf_daily" / "part.parquet", [_bar("510300.SH")])
    for table, field in {
        "metrics": ("roe", 12.0),
        "income": ("revenue", 100.0),
        "balance_sheet": ("total_assets", 200.0),
        "cash_flow": ("net_operating_cash_flow", 50.0),
        "shares": ("total_shares", 1_000.0),
    }.items():
        name, value = field
        _write_parquet(
            tmp_path / "financials" / table / "part.parquet",
            [{"symbol": "600000.SH", "period_end": date(2026, 6, 30), name: value}],
        )

    run_ids = {
        definition.descriptor.dataset_id: f"run-{definition.descriptor.dataset_id}"
        for definition in DATASET_DEFINITIONS
    }
    snapshot = CatalogScanner(tmp_path).scan_all(run_ids)

    assert snapshot.datasets["stock_daily"].state.row_count == 1
    assert snapshot.datasets["index_daily"].state.row_count == 1
    assert snapshot.datasets["etf_daily"].state.row_count == 1
    assert [artifact.path for artifact in snapshot.datasets["stock_daily"].artifacts] == [
        "kline_daily/part.parquet"
    ]
    assert [artifact.path for artifact in snapshot.datasets["index_daily"].artifacts] == [
        "kline_index_daily/part.parquet"
    ]
    assert [artifact.path for artifact in snapshot.datasets["etf_daily"].artifacts] == [
        "kline_etf_daily/part.parquet"
    ]
    assert {
        dataset_id: snapshot.datasets[dataset_id].state.row_count
        for dataset_id in (
            "financial_metrics",
            "financial_income",
            "financial_balance_sheet",
            "financial_cash_flow",
            "financial_shares",
        )
    } == {
        "financial_metrics": 1,
        "financial_income": 1,
        "financial_balance_sheet": 1,
        "financial_cash_flow": 1,
        "financial_shares": 1,
    }


def test_depth_files_require_schema_proof_and_ambiguous_files_default_to_sealed_l1(
    tmp_path: Path,
) -> None:
    timestamp = datetime(2026, 7, 21, 7, 0, tzinfo=UTC)
    l1 = _write_parquet(
        tmp_path / "depth5" / "date=2026-07-21" / "l1.parquet",
        [
            {
                "symbol": "600000.SH",
                "sealed_up": True,
                "sealed_down": False,
                "ask1_vol": 0,
                "bid1_vol": 100,
                "status": "limit_up",
                "fetched_at": timestamp.timestamp(),
            }
        ],
    )
    level5 = _write_parquet(
        tmp_path / "depth5" / "date=2026-07-21" / "level5.parquet",
        [
            {
                "symbol": "000001.SZ",
                "timestamp": timestamp,
                "bid_price_1": 10.0,
                "bid_price_5": 9.5,
                "ask_price_1": 10.1,
                "ask_price_5": 10.5,
                "bid_volume_5": 100,
                "ask_volume_5": 200,
            }
        ],
    )
    lists = _write_parquet(
        tmp_path / "depth5" / "date=2026-07-21" / "lists.parquet",
        [
            {
                "symbol": "430001.BJ",
                "name": "depth row with optional metadata",
                "timestamp": timestamp,
                "bid_prices": [10.0] * 5,
                "ask_prices": [10.1] * 5,
            }
        ],
    )
    lineage_path = tmp_path / "lineage" / "depth5" / "date=2026-07-21" / "ambiguous.json"
    lineage_path.parent.mkdir(parents=True)
    lineage_path.write_text(
        json.dumps({"source": "tickflow", "unit_version": "depth5_v1", "quality": "success"}),
        encoding="utf-8",
    )
    _write_lineage(tmp_path, "sealed_l1", l1, unit_version="sealed_l1_v1")
    _write_lineage(tmp_path, "depth5", level5, unit_version="depth5_v1")
    _write_lineage(tmp_path, "depth5", lists, unit_version="depth5_v1")

    run_ids = {
        definition.descriptor.dataset_id: f"run-{definition.descriptor.dataset_id}"
        for definition in DATASET_DEFINITIONS
    }
    snapshot = CatalogScanner(tmp_path).scan_all(run_ids)

    assert [artifact.path for artifact in snapshot.datasets["sealed_l1"].artifacts] == [
        "depth5/date=2026-07-21/l1.parquet"
    ]
    assert [artifact.path for artifact in snapshot.datasets["depth5"].artifacts] == [
        "depth5/date=2026-07-21/level5.parquet",
        "depth5/date=2026-07-21/lists.parquet",
    ]
    assert snapshot.datasets["sealed_l1"].depth5_available is False
    assert snapshot.datasets["depth5"].depth5_available is True
    assert snapshot.datasets["depth5"].state.payload["depth5_available"] is True
    assert snapshot.datasets["sealed_l1"].state.symbol_count == 1
    assert snapshot.datasets["depth5"].state.symbol_count == 2


def test_healthy_lineage_without_materialized_parquet_remains_unknown(tmp_path: Path) -> None:
    lineage_path = tmp_path / "lineage" / "stock_daily" / "run.json"
    lineage_path.parent.mkdir(parents=True)
    lineage_path.write_text(
        json.dumps(
            {
                "source": "public",
                "unit_version": "canonical_daily_v1",
                "quality": "success",
            }
        ),
        encoding="utf-8",
    )

    result = CatalogScanner(tmp_path).scan_dataset("stock_daily", "run-stock")

    assert result.state.quality_status == "unknown"


def test_market_coverage_has_sh_sz_bj_other_and_full_scan_uses_instrument_expectations(
    tmp_path: Path,
) -> None:
    instruments = [
        _instrument("600000.SH", "SH", "stock"),
        _instrument("000001.SZ", "SZ", "stock"),
        _instrument("430001.BJ", "BJ", "stock"),
        _instrument("UNKNOWN", "Other", "stock"),
    ]
    _write_parquet(tmp_path / "instruments" / "part.parquet", instruments)
    daily = _write_parquet(
        tmp_path / "kline_daily" / "date=2026-07-21" / "part.parquet",
        [_bar("600000.SH"), _bar("000001.SZ"), _bar("430001.BJ")],
    )
    _write_lineage(tmp_path, "kline_daily", daily)

    run_ids = {
        definition.descriptor.dataset_id: f"run-{definition.descriptor.dataset_id}"
        for definition in DATASET_DEFINITIONS
    }
    result = CatalogScanner(tmp_path).scan_all(run_ids).datasets["stock_daily"]

    assert [item.market for item in result.coverage] == ["SH", "SZ", "BJ", "OTHER"]
    assert {item.market: item.symbol_count for item in result.coverage} == {
        "SH": 1,
        "SZ": 1,
        "BJ": 1,
        "OTHER": 0,
    }
    assert {item.market: item.expected_symbol_count for item in result.coverage} == {
        "SH": 1,
        "SZ": 1,
        "BJ": 1,
        "OTHER": 1,
    }
    assert result.state.expected_symbol_count == 4


def test_corrupt_parquet_fails_only_its_dataset_with_bounded_deterministic_errors(
    tmp_path: Path,
) -> None:
    corrupt_dir = tmp_path / "kline_daily"
    corrupt_dir.mkdir()
    for index in range(30):
        (corrupt_dir / f"bad-{index:02d}.parquet").write_bytes(b"not parquet")
    index = _write_parquet(tmp_path / "kline_index_daily" / "part.parquet", [_bar("000001.SH")])
    _write_lineage(tmp_path, "kline_index_daily", index)

    run_ids = {
        definition.descriptor.dataset_id: f"run-{definition.descriptor.dataset_id}"
        for definition in DATASET_DEFINITIONS
    }
    snapshot = CatalogScanner(tmp_path).scan_all(run_ids)

    stock = snapshot.datasets["stock_daily"]
    assert stock.state.quality_status == "failed"
    assert 1 <= len(stock.state.payload["scan_errors"]) <= 20
    assert stock.state.payload["scan_errors"] == sorted(stock.state.payload["scan_errors"])
    assert all(str(tmp_path) not in error for error in stock.state.payload["scan_errors"])
    assert snapshot.datasets["index_daily"].state.quality_status == "healthy"


def test_scan_dataset_only_walks_owned_root_and_accepts_cached_expected_counts(
    tmp_path: Path, tmp_path_factory, monkeypatch
) -> None:
    _write_parquet(tmp_path / "kline_daily" / "part.parquet", [_bar("600000.SH")])
    _write_parquet(tmp_path / "kline_index_daily" / "part.parquet", [_bar("000001.SH")])
    outside = tmp_path_factory.mktemp("catalog-nested-outside")
    _write_parquet(outside / "escaped.parquet", [_bar("000001.SZ")])
    (tmp_path / "kline_daily" / "outside-dir").symlink_to(outside, target_is_directory=True)

    import app.data_catalog.scanner as scanner_module

    original_walk = os.walk
    walked: list[Path] = []

    def guarded_walk(path, *args, **kwargs):
        resolved = Path(path)
        walked.append(resolved)
        assert resolved == tmp_path / "kline_daily"
        return original_walk(path, *args, **kwargs)

    monkeypatch.setattr(scanner_module.os, "walk", guarded_walk)

    result = CatalogScanner(tmp_path).scan_dataset(
        "stock_daily",
        "run-stock",
        expected_by_market={"SH": 2, "SZ": 3, "BJ": 4, "OTHER": 0},
    )

    assert walked == [tmp_path / "kline_daily"]
    assert result.state.row_count == 1
    assert result.state.payload["file_count"] == 1
    assert result.state.expected_symbol_count == 9
    assert {item.market: item.expected_symbol_count for item in result.coverage} == {
        "SH": 2,
        "SZ": 3,
        "BJ": 4,
        "OTHER": 0,
    }


def test_dataset_payload_keys_artifact_metadata_and_lineage_are_stable(tmp_path: Path) -> None:
    parquet = _write_parquet(
        tmp_path / "kline_daily" / "date=2026-07-21" / "part.parquet",
        [_bar("600000.SH"), _bar("000001.SZ")],
    )
    lineage = tmp_path / "lineage" / "kline_daily" / "date=2026-07-21" / "run.json"
    lineage.parent.mkdir(parents=True)
    lineage.write_text(
        json.dumps(
            {
                "source": "public_quote_eod",
                "fetched_at": "2026-07-21T15:00:00+08:00",
                "unit_version": "canonical_daily_v1",
                "quality_status": "degraded",
                "scope": "CSI800",
                "row_count": 2,
                "target_artifact": "kline_daily/date=2026-07-21/part.parquet",
            }
        ),
        encoding="utf-8",
    )

    result = CatalogScanner(tmp_path).scan_dataset("stock_daily", "run-stock")

    assert set(result.state.payload) == {
        "file_count",
        "field_count",
        "trading_days",
        "named_count",
        "coverage",
        "lineage",
        "scan_errors",
        "depth5_available",
    }
    assert result.state.quality_status == "degraded"
    assert result.lineage[0].source == "public_quote_eod"
    assert result.lineage[0].artifact_path == "kline_daily/date=2026-07-21/part.parquet"
    artifact = result.artifacts[0]
    assert artifact.path == "kline_daily/date=2026-07-21/part.parquet"
    assert artifact.bytes == parquet.stat().st_size
    assert len(artifact.sha256) == 64
    assert artifact.row_count == 2
    assert artifact.partition_value == "2026-07-21"
    assert artifact.published_at.endswith("Z")


def test_real_writer_shapes_are_admitted_and_legacy_depth_summary_stays_sealed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.services import instrument_sync
    from app.services.free_sources.pools_public import write_pool_parquet

    class Exchanges:
        def get_instruments(self, exchange, instrument_type):
            if exchange != "SH":
                return []
            return [
                {
                    "symbol": "600000.SH",
                    "name": "浦发银行",
                    "code": "600000",
                    "exchange": "SH",
                    "region": "CN",
                    "type": instrument_type,
                    "ext": {
                        "listing_date": "1999-11-10",
                        "total_shares": 1_000,
                        "float_shares": 900,
                        "tick_size": 0.01,
                        "limit_up": 11.0,
                        "limit_down": 9.0,
                    },
                }
            ]

    monkeypatch.setattr(
        instrument_sync, "get_client", lambda: type("Client", (), {"exchanges": Exchanges()})()
    )
    assert instrument_sync.sync_instruments(tmp_path) == 1
    write_pool_parquet(
        pl.DataFrame({"symbol": ["600000.SH"], "name": ["浦发银行"], "pool_id": ["CSI300"]}),
        tmp_path,
        "CSI300",
    )
    sealed_root = _write_parquet(
        tmp_path / "sealed_l1" / "date=2026-07-21" / "part.parquet",
        [
            {
                "symbol": "600000.SH",
                "sealed_up": True,
                "sealed_down": False,
                "ask1_vol": 0,
                "bid1_vol": 100,
                "status": "limit_up",
                "fetched_at": 1_753_084_800.0,
            }
        ],
    )
    legacy_root = _write_parquet(
        tmp_path / "depth5" / "date=2026-07-20" / "part.parquet",
        [
            {
                "symbol": "000001.SZ",
                "sealed_up": False,
                "sealed_down": True,
                "ask1_vol": 100,
                "bid1_vol": 0,
                "status": "limit_down",
                "fetched_at": 1_752_998_400.0,
            }
        ],
    )
    _write_lineage(tmp_path, "sealed_l1", sealed_root, unit_version="sealed_l1_v1")
    _write_lineage(tmp_path, "sealed_l1", legacy_root, unit_version="sealed_l1_v1")

    run_ids = {
        definition.descriptor.dataset_id: f"run-{definition.descriptor.dataset_id}"
        for definition in DATASET_DEFINITIONS
    }
    snapshot = CatalogScanner(tmp_path).scan_all(run_ids)

    assert snapshot.datasets["stock_instruments"].state.quality_status == "healthy"
    assert snapshot.datasets["stock_instruments"].state.latest_time == str(date.today())
    assert snapshot.datasets["pools"].state.quality_status == "healthy"
    assert snapshot.datasets["pools"].state.latest_time == str(date.today())
    assert {item.path for item in snapshot.datasets["sealed_l1"].artifacts} == {
        "sealed_l1/date=2026-07-21/part.parquet",
        "depth5/date=2026-07-20/part.parquet",
    }
    assert snapshot.datasets["sealed_l1"].state.quality_status == "healthy"
    assert snapshot.datasets["depth5"].artifacts == ()
    assert snapshot.datasets["depth5"].depth5_available is False


def test_readable_parquet_missing_required_columns_is_failed_and_not_admitted(
    tmp_path: Path,
) -> None:
    _write_parquet(
        tmp_path / "kline_daily" / "part.parquet",
        [{"symbol": "600000.SH", "date": date(2026, 7, 21), "close": 10.0}],
    )

    result = CatalogScanner(tmp_path).scan_dataset("stock_daily", "run-stock")

    assert result.state.quality_status == "failed"
    assert result.state.row_count == 0
    assert result.state.unit_version == "unknown"
    assert result.artifacts == ()
    assert any("missing required columns" in error for error in result.state.payload["scan_errors"])


def test_unit_lineage_must_match_the_exact_artifact_and_descriptor_contract(
    tmp_path: Path,
) -> None:
    artifact = _write_parquet(tmp_path / "kline_daily" / "part.parquet", [_bar("600000.SH")])
    unrelated = tmp_path / "kline_daily" / "other.parquet"
    _write_lineage(tmp_path, "kline_daily", unrelated, unit_version="canonical_daily_v1")

    missing = CatalogScanner(tmp_path).scan_dataset("stock_daily", "run-missing")
    assert missing.state.quality_status == "unknown"
    assert missing.state.unit_version == "unknown"
    assert any("matching lineage" in error for error in missing.state.payload["scan_errors"])

    lineage = next((tmp_path / "lineage").rglob("*.json"))
    lineage.unlink()
    _write_lineage(tmp_path, "kline_daily", artifact, unit_version="wrong-unit-v1")
    mismatch = CatalogScanner(tmp_path).scan_dataset("stock_daily", "run-mismatch")
    assert mismatch.state.quality_status == "failed"
    assert mismatch.state.unit_version == "unknown"
    assert any("unit_version mismatch" in error for error in mismatch.state.payload["scan_errors"])

    next((tmp_path / "lineage").rglob("*.json")).unlink()
    _write_lineage(tmp_path, "kline_daily", artifact, unit_version="canonical_daily_v1")
    admitted = CatalogScanner(tmp_path).scan_dataset("stock_daily", "run-admitted")
    assert admitted.state.quality_status == "healthy"
    assert admitted.state.unit_version == "canonical_daily_v1"
    assert [item.artifact_path for item in admitted.lineage] == ["kline_daily/part.parquet"]


def test_parquet_replacement_during_scan_fails_consistency_instead_of_mixing_versions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app.data_catalog.scanner as scanner_module

    target = _write_parquet(tmp_path / "kline_daily" / "part.parquet", [_bar("600000.SH")])
    replacement = _write_parquet(
        tmp_path / "replacement.parquet",
        [_bar("600000.SH"), _bar("000001.SZ")],
    )
    original = scanner_module.pq.ParquetFile
    replaced = False

    def replacing_parquet_file(source, *args, **kwargs):
        nonlocal replaced
        parquet = original(source, *args, **kwargs)
        if not replaced and Path(getattr(source, "name", "")) == target:
            replaced = True
            shutil.copy2(replacement, tmp_path / "replacement-copy.parquet")
            os.replace(tmp_path / "replacement-copy.parquet", target)
        return parquet

    monkeypatch.setattr(scanner_module.pq, "ParquetFile", replacing_parquet_file)

    result = CatalogScanner(tmp_path).scan_dataset("stock_daily", "run-race")

    assert result.state.quality_status == "failed"
    assert result.artifacts == ()
    assert any("changed during scan" in error for error in result.state.payload["scan_errors"])


def test_trading_calendar_reference_root_scans_healthy(tmp_path: Path) -> None:
    from datetime import date

    root = _write_parquet(
        tmp_path / "reference" / "trading_calendar" / "calendar.parquet",
        [
            {
                "exchange": "SH",
                "trade_date": date(2026, 7, 1),
                "is_open": True,
                "session_type": "normal",
                "open_time": "09:30",
                "close_time": "15:00",
                "source": "szse_month_list",
                "as_of": date(2026, 7, 21),
            },
            {
                "exchange": "SZ",
                "trade_date": date(2026, 7, 1),
                "is_open": True,
                "session_type": "normal",
                "open_time": "09:30",
                "close_time": "15:00",
                "source": "szse_month_list",
                "as_of": date(2026, 7, 21),
            },
        ],
    )
    _write_lineage(
        tmp_path,
        "trading_calendar",
        root,
        unit_version="trading_calendar_v1",
        source="szse_month_list",
    )

    result = CatalogScanner(tmp_path).scan_dataset("trading_calendar", "run-calendar")

    assert result.state.quality_status == "healthy"
    assert result.state.row_count == 2
    assert result.state.unit_version == "trading_calendar_v1"
    assert result.state.earliest_time == "2026-07-01"
    assert result.state.latest_time == "2026-07-01"
    assert {item.path for item in result.artifacts} == {
        "reference/trading_calendar/calendar.parquet"
    }
    assert result.state.payload.get("scan_errors", []) == []
