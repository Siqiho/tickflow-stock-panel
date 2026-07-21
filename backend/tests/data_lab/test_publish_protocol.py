"""M5.1 publish protocol tests — isolated temp DATA_DIR only."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from app.data_lab.fixtures import (
    make_listing_events_frame,
    make_status_history_frame,
    make_trading_calendar_frame,
)
from app.data_lab.publish_protocol import PublishRequest, formal_path, publish_dataset
from app.data_lab.schemas_reference import get_reference_schema


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    root = tmp_path / "lab_data"
    root.mkdir()
    return root


def test_empty_frame_refuses_and_keeps_prior(data_dir: Path) -> None:
    schema = get_reference_schema("trading_calendar")
    target = formal_path(data_dir, schema)
    good = make_trading_calendar_frame()
    first = publish_dataset(
        PublishRequest(
            dataset_id="trading_calendar",
            data_dir=data_dir,
            frame=good,
            source="lab_fixture",
            run_id="run-good",
            cleanup_staging_on_success=False,
        )
    )
    assert first.ok is True
    assert target.exists()
    prior_bytes = target.read_bytes()

    empty = good.head(0)
    second = publish_dataset(
        PublishRequest(
            dataset_id="trading_calendar",
            data_dir=data_dir,
            frame=empty,
            source="lab_fixture",
            run_id="run-empty",
        )
    )
    assert second.ok is False
    assert second.kept_prior is True
    assert second.error == "quality_gates_failed"
    assert target.read_bytes() == prior_bytes
    assert any(c["code"] == "not_empty" and c["passed"] is False for c in second.checks)


def test_calendar_publish_writes_lineage_unit_version(data_dir: Path) -> None:
    frame = make_trading_calendar_frame()
    result = publish_dataset(
        PublishRequest(
            dataset_id="trading_calendar",
            data_dir=data_dir,
            frame=frame,
            source="lab_fixture",
            run_id="run-cal-1",
            as_of=date(2026, 7, 21),
        )
    )
    assert result.ok is True
    assert result.row_count == frame.height
    assert result.lineage_path is not None
    lineage = Path(result.lineage_path)
    assert lineage.exists()
    text = lineage.read_text(encoding="utf-8")
    assert "trading_calendar_v1" in text
    assert "lab_fixture" in text
    published = pl.read_parquet(result.published_path)
    assert published.height == frame.height
    assert set(published.columns) >= {
        "exchange",
        "trade_date",
        "is_open",
        "session_type",
        "source",
        "as_of",
    }


def test_duplicate_pk_after_conflicting_payload_fails_overlap(data_dir: Path) -> None:
    base = make_trading_calendar_frame(days=3)
    first = publish_dataset(
        PublishRequest(
            dataset_id="trading_calendar",
            data_dir=data_dir,
            frame=base,
            source="lab_fixture",
            run_id="run-base",
        )
    )
    assert first.ok is True
    prior = Path(first.published_path).read_bytes()

    # Flip a known open day to closed → overlap conflict
    flipped = base.with_columns(
        pl.when((pl.col("exchange") == "SH") & (pl.col("trade_date") == date(2026, 7, 13)))
        .then(False)
        .otherwise(pl.col("is_open"))
        .alias("is_open"),
        pl.when((pl.col("exchange") == "SH") & (pl.col("trade_date") == date(2026, 7, 13)))
        .then(pl.lit("holiday"))
        .otherwise(pl.col("session_type"))
        .alias("session_type"),
        pl.when((pl.col("exchange") == "SH") & (pl.col("trade_date") == date(2026, 7, 13)))
        .then(None)
        .otherwise(pl.col("open_time"))
        .alias("open_time"),
        pl.when((pl.col("exchange") == "SH") & (pl.col("trade_date") == date(2026, 7, 13)))
        .then(None)
        .otherwise(pl.col("close_time"))
        .alias("close_time"),
    )
    second = publish_dataset(
        PublishRequest(
            dataset_id="trading_calendar",
            data_dir=data_dir,
            frame=flipped,
            source="lab_fixture",
            run_id="run-flip",
            allow_status_flip=False,
        )
    )
    assert second.ok is False
    assert second.kept_prior is True
    assert Path(first.published_path).read_bytes() == prior
    assert any(c["code"] == "overlap_conflicts" and c["passed"] is False for c in second.checks)


def test_idempotent_second_publish(data_dir: Path) -> None:
    frame = make_trading_calendar_frame()
    a = publish_dataset(
        PublishRequest(
            dataset_id="trading_calendar",
            data_dir=data_dir,
            frame=frame,
            source="lab_fixture",
            run_id="run-a",
        )
    )
    b = publish_dataset(
        PublishRequest(
            dataset_id="trading_calendar",
            data_dir=data_dir,
            frame=frame,
            source="lab_fixture",
            run_id="run-b",
        )
    )
    assert a.ok and b.ok
    assert a.row_count == b.row_count
    df_a = pl.read_parquet(a.published_path).sort(["exchange", "trade_date"])
    df_b = pl.read_parquet(b.published_path).sort(["exchange", "trade_date"])
    assert df_a.equals(df_b)


def test_status_and_listing_sample_publish(data_dir: Path) -> None:
    status = publish_dataset(
        PublishRequest(
            dataset_id="instrument_status_history",
            data_dir=data_dir,
            frame=make_status_history_frame(),
            source="lab_fixture",
            run_id="run-status",
        )
    )
    listing = publish_dataset(
        PublishRequest(
            dataset_id="listing_delisting_events",
            data_dir=data_dir,
            frame=make_listing_events_frame(),
            source="lab_fixture",
            run_id="run-list",
        )
    )
    assert status.ok is True
    assert listing.ok is True
    assert Path(status.published_path).exists()
    assert Path(listing.published_path).exists()


def test_invalid_symbol_rejected(data_dir: Path) -> None:
    frame = make_status_history_frame().with_columns(pl.lit("600000").alias("symbol"))
    result = publish_dataset(
        PublishRequest(
            dataset_id="instrument_status_history",
            data_dir=data_dir,
            frame=frame,
            source="lab_fixture",
            run_id="run-bad-symbol",
        )
    )
    assert result.ok is False
    assert any(c["code"] == "symbol_pattern" and c["passed"] is False for c in result.checks)


def test_duplicate_pk_deduped_when_identical(data_dir: Path) -> None:
    base = make_listing_events_frame()
    duped = pl.concat([base, base], how="vertical")
    result = publish_dataset(
        PublishRequest(
            dataset_id="listing_delisting_events",
            data_dir=data_dir,
            frame=duped,
            source="lab_fixture",
            run_id="run-dedupe",
        )
    )
    assert result.ok is True
    assert result.row_count == base.height


def test_protocol_exception_keeps_prior(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frame = make_trading_calendar_frame()
    first = publish_dataset(
        PublishRequest(
            dataset_id="trading_calendar",
            data_dir=data_dir,
            frame=frame,
            source="lab_fixture",
            run_id="run-prior",
        )
    )
    assert first.ok
    prior_bytes = Path(first.published_path).read_bytes()

    from app.data_lab import publish_protocol as pp

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated_crash_before_replace")

    monkeypatch.setattr(pp, "atomic_write_parquet", boom)
    # first call writes normalized via atomic_write_parquet — boom will fail early;
    # prior formal must remain.
    second = publish_dataset(
        PublishRequest(
            dataset_id="trading_calendar",
            data_dir=data_dir,
            frame=frame,
            source="lab_fixture",
            run_id="run-crash",
        )
    )
    assert second.ok is False
    assert second.kept_prior is True
    assert Path(first.published_path).read_bytes() == prior_bytes
    assert second.staging_dir is not None
    assert Path(second.staging_dir).exists()
