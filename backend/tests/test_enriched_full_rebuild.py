from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from app.data_catalog.scanner import CatalogScanner
from app.indicators import pipeline
from app.services.atomic_io import write_lineage_record


def _write_daily(data_dir: Path, ds: str, close: float) -> None:
    out = data_dir / "kline_daily" / f"date={ds}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "symbol": ["600000.SH"],
            "date": [date.fromisoformat(ds)],
            "open": [close],
            "high": [close],
            "low": [close],
            "close": [close],
            "volume": [100.0],
            "amount": [1_000.0],
        }
    ).write_parquet(out)


def _write_existing(
    data_dir: Path,
    ds: str,
    close: float,
    *,
    with_lineage: bool = True,
) -> None:
    out = data_dir / "kline_daily_enriched" / f"date={ds}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "symbol": ["600000.SH"],
            "date": [date.fromisoformat(ds)],
            "open": [close],
            "high": [close],
            "low": [close],
            "close": [close],
            "volume": [100.0],
            "amount": [1_000.0],
            "raw_close": [close],
            "raw_high": [close],
            "raw_low": [close],
        }
    ).write_parquet(out)
    if with_lineage:
        write_lineage_record(
            data_dir,
            "kline_daily_enriched",
            {
                "date": ds,
                "source": "test-existing",
                "unit_version": "canonical_daily_v1",
                "quality": "healthy",
                "target_artifact": str(out.relative_to(data_dir)),
            },
        )


def _fake_compute_enriched(raw: pl.DataFrame, **_kwargs) -> pl.DataFrame:
    return raw.with_columns(
        pl.col("close").alias("raw_close"),
        pl.col("high").alias("raw_high"),
        pl.col("low").alias("raw_low"),
        pl.lit(None, dtype=pl.Float64).alias("turnover_rate"),
        pl.lit(0, dtype=pl.UInt32).alias("consecutive_limit_ups"),
        pl.lit(0, dtype=pl.UInt32).alias("consecutive_limit_downs"),
    )


def _calculation_modes(data_dir: Path) -> set[str]:
    modes: set[str] = set()
    for path in (data_dir / "lineage" / "kline_daily_enriched").rglob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("calculation_mode"):
            modes.add(payload["calculation_mode"])
    return modes


def test_full_rebuild_overwrites_without_deleting_the_existing_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_daily(tmp_path, "2026-07-14", 14.0)
    _write_daily(tmp_path, "2026-07-15", 15.0)
    _write_existing(tmp_path, "2026-07-15", 1.0)
    marker = tmp_path / "kline_daily_enriched" / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(pipeline, "compute_enriched", _fake_compute_enriched)

    assert pipeline.run_pipeline(data_dir=tmp_path) == 2

    assert marker.read_text(encoding="utf-8") == "keep"
    assert pl.read_parquet(tmp_path / "kline_daily_enriched" / "date=2026-07-14" / "part.parquet")[
        "close"
    ].to_list() == [14.0]
    assert pl.read_parquet(tmp_path / "kline_daily_enriched" / "date=2026-07-15" / "part.parquet")[
        "close"
    ].to_list() == [15.0]


def test_full_rebuild_rejects_missing_existing_dates_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_daily(tmp_path, "2026-07-15", 15.0)
    _write_existing(tmp_path, "2026-07-14", 14.0)
    _write_existing(tmp_path, "2026-07-15", 1.0)
    monkeypatch.setattr(pipeline, "compute_enriched", _fake_compute_enriched)

    with pytest.raises(RuntimeError, match="缺少已有日期分区"):
        pipeline.run_pipeline(data_dir=tmp_path)

    assert pl.read_parquet(tmp_path / "kline_daily_enriched" / "date=2026-07-15" / "part.parquet")[
        "close"
    ].to_list() == [1.0]


def test_lineage_failure_never_deletes_unwritten_existing_partitions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_daily(tmp_path, "2026-07-14", 14.0)
    _write_daily(tmp_path, "2026-07-15", 15.0)
    _write_existing(tmp_path, "2026-07-14", 1.0)
    _write_existing(tmp_path, "2026-07-15", 2.0)
    monkeypatch.setattr(pipeline, "compute_enriched", _fake_compute_enriched)

    def fail_lineage(*_args, **_kwargs) -> None:
        raise OSError("forced lineage failure")

    monkeypatch.setattr(pipeline, "write_lineage_record", fail_lineage)

    with pytest.raises(OSError, match="forced lineage failure"):
        pipeline.run_pipeline(data_dir=tmp_path)

    remaining = sorted(
        path.name for path in (tmp_path / "kline_daily_enriched").glob("date=*") if path.is_dir()
    )
    assert remaining == ["date=2026-07-14", "date=2026-07-15"]


def test_coverage_gap_fill_merges_missing_symbols_without_dropping_priors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_daily(tmp_path, "2026-07-15", 15.0)
    extra = tmp_path / "kline_daily" / "date=2026-07-15" / "part.parquet"
    pl.concat(
        [
            pl.read_parquet(extra),
            pl.DataFrame(
                {
                    "symbol": ["000636.SZ"],
                    "date": [date(2026, 7, 15)],
                    "open": [20.0],
                    "high": [21.0],
                    "low": [19.5],
                    "close": [20.5],
                    "volume": [200.0],
                    "amount": [4_000.0],
                }
            ),
        ]
    ).write_parquet(extra)
    _write_existing(tmp_path, "2026-07-15", 15.0)
    monkeypatch.setattr(pipeline, "compute_enriched", _fake_compute_enriched)

    assert pipeline.fill_enriched_coverage_gap(tmp_path, target_date="2026-07-15") == 1
    merged = pl.read_parquet(tmp_path / "kline_daily_enriched" / "date=2026-07-15" / "part.parquet")
    assert sorted(merged["symbol"].to_list()) == ["000636.SZ", "600000.SH"]
    assert merged.filter(pl.col("symbol") == "600000.SH")["close"].to_list() == [15.0]
    assert "coverage_gap_fill" in _calculation_modes(tmp_path)

    assert pipeline.run_pipeline(data_dir=tmp_path, new_dates_only=True) == 0


def test_incremental_retry_reconciles_a_partition_missing_its_lineage(
    tmp_path: Path,
) -> None:
    _write_daily(tmp_path, "2026-07-15", 15.0)
    _write_existing(tmp_path, "2026-07-15", 15.0, with_lineage=False)

    before = CatalogScanner(tmp_path).scan_dataset(
        "stock_enriched",
        "before-reconcile",
    )
    assert before.state.quality_status == "unknown"

    assert pipeline.run_pipeline(data_dir=tmp_path, new_dates_only=True) == 0

    after = CatalogScanner(tmp_path).scan_dataset(
        "stock_enriched",
        "after-reconcile",
    )
    assert after.state.quality_status == "healthy"
    assert after.state.row_count == 1
    assert after.lineage[0].artifact_path == ("kline_daily_enriched/date=2026-07-15/part.parquet")
    assert "lineage_reconcile" in _calculation_modes(tmp_path)


def test_new_date_incremental_publish_writes_matching_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_daily(tmp_path, "2026-07-14", 14.0)
    _write_daily(tmp_path, "2026-07-15", 15.0)
    _write_existing(tmp_path, "2026-07-14", 14.0)
    monkeypatch.setattr(pipeline, "compute_enriched", _fake_compute_enriched)

    assert pipeline.run_pipeline(data_dir=tmp_path, new_dates_only=True) == 1
    assert "new_dates_only" in _calculation_modes(tmp_path)


def test_affected_symbol_incremental_publish_writes_matching_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_daily(tmp_path, "2026-07-15", 15.0)
    _write_existing(tmp_path, "2026-07-15", 1.0)
    monkeypatch.setattr(pipeline, "compute_enriched", _fake_compute_enriched)

    assert (
        pipeline.run_pipeline(
            data_dir=tmp_path,
            symbols=["600000.SH"],
            new_dates_only=True,
        )
        == 1
    )
    assert "affected_symbols" in _calculation_modes(tmp_path)


def test_selected_symbol_publish_writes_matching_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_daily(tmp_path, "2026-07-15", 15.0)
    monkeypatch.setattr(pipeline, "compute_enriched", _fake_compute_enriched)

    assert (
        pipeline.run_pipeline(
            data_dir=tmp_path,
            symbols=["600000.SH"],
        )
        == 1
    )
    assert "selected_symbols" in _calculation_modes(tmp_path)


@pytest.mark.parametrize("new_dates_only", [False, True])
def test_rebuild_replaces_an_unreadable_existing_partition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    new_dates_only: bool,
) -> None:
    _write_daily(tmp_path, "2026-07-15", 15.0)
    corrupt = tmp_path / "kline_daily_enriched" / "date=2026-07-15" / "part.parquet"
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_bytes(b"not-a-parquet-file")
    monkeypatch.setattr(pipeline, "compute_enriched", _fake_compute_enriched)

    assert (
        pipeline.run_pipeline(
            data_dir=tmp_path,
            new_dates_only=new_dates_only,
        )
        == 1
    )
    assert pl.read_parquet(corrupt)["close"].to_list() == [15.0]


def test_full_rebuild_multi_asset_multi_date_and_keeps_old_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for ds, close in (("2026-07-14", 14.0), ("2026-07-15", 15.0)):
        out = tmp_path / "kline_daily" / f"date={ds}" / "part.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(
            {
                "symbol": ["600000.SH", "000001.SZ"],
                "date": [date.fromisoformat(ds), date.fromisoformat(ds)],
                "open": [close, close + 1],
                "high": [close, close + 1],
                "low": [close, close + 1],
                "close": [close, close + 1],
                "volume": [100.0, 200.0],
                "amount": [1_000.0, 2_000.0],
            }
        ).write_parquet(out)
    _write_existing(tmp_path, "2026-07-14", 1.0)
    monkeypatch.setattr(pipeline, "compute_enriched", _fake_compute_enriched)
    written = pipeline.run_pipeline(data_dir=tmp_path)
    # Local pipeline reports processed rows, not partition count.
    assert written == 4
    for ds in ("2026-07-14", "2026-07-15"):
        frame = pl.read_parquet(tmp_path / "kline_daily_enriched" / f"date={ds}" / "part.parquet")
        assert sorted(frame["symbol"].to_list()) == ["000001.SZ", "600000.SH"]
        assert frame.height == 2
        assert frame["symbol"].n_unique() == 2

    old = pl.read_parquet(tmp_path / "kline_daily_enriched" / "date=2026-07-15" / "part.parquet")
    old_lineage = sorted(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "lineage" / "kline_daily_enriched" / "date=2026-07-15").glob("*.json")
    )

    def boom(raw: pl.DataFrame, **_kwargs) -> pl.DataFrame:
        raise RuntimeError("forced compute failure")

    monkeypatch.setattr(pipeline, "compute_enriched", boom)
    with pytest.raises(RuntimeError, match="forced compute failure"):
        pipeline.run_pipeline(data_dir=tmp_path)
    kept = pl.read_parquet(tmp_path / "kline_daily_enriched" / "date=2026-07-15" / "part.parquet")
    assert kept["close"].to_list() == old["close"].to_list()
    assert kept["symbol"].to_list() == old["symbol"].to_list()
    kept_lineage = sorted(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "lineage" / "kline_daily_enriched" / "date=2026-07-15").glob("*.json")
    )
    assert kept_lineage == old_lineage


def test_full_rebuild_dedups_duplicate_symbols_in_one_date(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "kline_daily" / "date=2026-07-15" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "symbol": ["600000.SH", "600000.SH"],
            "date": [date(2026, 7, 15), date(2026, 7, 15)],
            "open": [10.0, 11.0],
            "high": [10.0, 11.0],
            "low": [10.0, 11.0],
            "close": [10.0, 11.0],
            "volume": [100.0, 200.0],
            "amount": [1_000.0, 2_000.0],
        }
    ).write_parquet(out)
    monkeypatch.setattr(pipeline, "compute_enriched", _fake_compute_enriched)
    written = pipeline.run_pipeline(data_dir=tmp_path)
    # Staging counts raw rows; publish must still collapse the primary key.
    assert written >= 1
    frame = pl.read_parquet(tmp_path / "kline_daily_enriched" / "date=2026-07-15" / "part.parquet")
    assert frame.height == 1
    assert frame["symbol"].n_unique() == 1
    assert frame["symbol"].to_list() == ["600000.SH"]


def test_reconcile_ignores_a_non_object_lineage_sidecar(
    tmp_path: Path,
) -> None:
    _write_daily(tmp_path, "2026-07-15", 15.0)
    _write_existing(tmp_path, "2026-07-15", 15.0, with_lineage=False)
    invalid = tmp_path / "lineage" / "kline_daily_enriched" / "date=2026-07-15" / "invalid.json"
    invalid.parent.mkdir(parents=True, exist_ok=True)
    invalid.write_text("[]", encoding="utf-8")

    assert pipeline.run_pipeline(data_dir=tmp_path, new_dates_only=True) == 0
    assert len(list(invalid.parent.glob("*.json"))) == 2
