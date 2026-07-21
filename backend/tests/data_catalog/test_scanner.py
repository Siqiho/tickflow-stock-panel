from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl

from app.data_catalog.definitions import DATASET_DEFINITIONS
from app.data_catalog.scanner import CatalogScanner


def _write_parquet(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path)
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
        "exchange": symbol.rsplit(".", 1)[-1],
        "asset_type": asset_type,
        "list_date": date(2020, 1, 1),
        "status": "listed",
    }


def test_full_scan_is_one_walk_exact_bytes_and_assigns_every_file_once(
    tmp_path: Path, monkeypatch
) -> None:
    _write_parquet(tmp_path / "instruments" / "part.parquet", [_instrument("600000.SH", "浦发", "stock")])
    _write_parquet(tmp_path / "kline_daily" / "date=2026-07-21" / "part.parquet", [_bar("600000.SH")])
    (tmp_path / "kline_daily" / "notes.txt").write_text("owned non-parquet", encoding="utf-8")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "runtime.log").write_bytes(b"log-bytes")
    (tmp_path / "misc").mkdir()
    (tmp_path / "misc" / "unknown.bin").write_bytes(b"other")
    symlink = tmp_path / "misc" / "link.bin"
    symlink.symlink_to(tmp_path / "misc" / "unknown.bin")

    import app.data_catalog.scanner as scanner_module

    original_walk = os.walk
    walked: list[Path] = []

    def counting_walk(path, *args, **kwargs):
        walked.append(Path(path))
        return original_walk(path, *args, **kwargs)

    monkeypatch.setattr(scanner_module.os, "walk", counting_walk)
    run_ids = {definition.descriptor.dataset_id: f"run-{definition.descriptor.dataset_id}" for definition in DATASET_DEFINITIONS}

    snapshot = CatalogScanner(tmp_path).scan_all(run_ids)

    regular_files = [
        path
        for path in tmp_path.rglob("*")
        if path.is_file() and not path.is_symlink()
    ]
    assert walked == [tmp_path]
    assert snapshot.storage.total_bytes == sum(path.stat().st_size for path in regular_files)
    assert snapshot.storage.total_bytes == (
        snapshot.storage.managed_data_bytes + snapshot.storage.operational_bytes
    )
    assert sum(category.bytes for category in snapshot.storage.categories) == snapshot.storage.total_bytes
    assert sum(category.files for category in snapshot.storage.categories) == len(regular_files)
    artifact_paths = [
        artifact.path
        for result in snapshot.datasets.values()
        for artifact in result.artifacts
    ]
    assert len(artifact_paths) == len(set(artifact_paths))
    assert snapshot.datasets["stock_daily"].state.managed_bytes == sum(
        path.stat().st_size
        for path in (tmp_path / "kline_daily").rglob("*")
        if path.is_file()
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

    run_ids = {definition.descriptor.dataset_id: f"run-{definition.descriptor.dataset_id}" for definition in DATASET_DEFINITIONS}
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
    _write_parquet(
        tmp_path / "depth5" / "date=2026-07-21" / "l1.parquet",
        [{"symbol": "600000.SH", "timestamp": timestamp, "bid_price_1": 10.0, "ask_price_1": 10.1}],
    )
    _write_parquet(
        tmp_path / "depth5" / "date=2026-07-21" / "level5.parquet",
        [{"symbol": "000001.SZ", "timestamp": timestamp, "bid_price_5": 9.5, "ask_price_5": 10.5}],
    )
    _write_parquet(
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

    run_ids = {definition.descriptor.dataset_id: f"run-{definition.descriptor.dataset_id}" for definition in DATASET_DEFINITIONS}
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
    _write_parquet(
        tmp_path / "kline_daily" / "date=2026-07-21" / "part.parquet",
        [_bar("600000.SH"), _bar("000001.SZ"), _bar("430001.BJ")],
    )

    run_ids = {definition.descriptor.dataset_id: f"run-{definition.descriptor.dataset_id}" for definition in DATASET_DEFINITIONS}
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
    _write_parquet(tmp_path / "kline_index_daily" / "part.parquet", [_bar("000001.SH")])

    run_ids = {definition.descriptor.dataset_id: f"run-{definition.descriptor.dataset_id}" for definition in DATASET_DEFINITIONS}
    snapshot = CatalogScanner(tmp_path).scan_all(run_ids)

    stock = snapshot.datasets["stock_daily"]
    assert stock.state.quality_status == "failed"
    assert 1 <= len(stock.state.payload["scan_errors"]) <= 20
    assert stock.state.payload["scan_errors"] == sorted(stock.state.payload["scan_errors"])
    assert all(str(tmp_path) not in error for error in stock.state.payload["scan_errors"])
    assert snapshot.datasets["index_daily"].state.quality_status == "healthy"


def test_scan_dataset_only_walks_owned_root_and_accepts_cached_expected_counts(
    tmp_path: Path, monkeypatch
) -> None:
    _write_parquet(tmp_path / "kline_daily" / "part.parquet", [_bar("600000.SH")])
    _write_parquet(tmp_path / "kline_index_daily" / "part.parquet", [_bar("000001.SH")])

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
