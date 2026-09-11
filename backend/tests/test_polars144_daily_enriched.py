"""Polars 1.44.1 daily/enriched key path: multi-date/symbol, concurrent upsert, fail-recover, lineage."""
from __future__ import annotations

import threading
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from app.data_catalog.scanner import CatalogScanner
from app.indicators.pipeline import run_pipeline
from app.services import preferences
from app.services.atomic_io import atomic_write_parquet, optimistic_upsert_parquet, write_lineage_record


def _daily_frame(ds: str, symbols: list[str], close: float) -> pl.DataFrame:
    day = date.fromisoformat(ds)
    return pl.DataFrame({
        "symbol": symbols,
        "date": [day] * len(symbols),
        "open": [close] * len(symbols),
        "high": [close + 1] * len(symbols),
        "low": [close - 1] * len(symbols),
        "close": [close] * len(symbols),
        "volume": [100.0] * len(symbols),
        "amount": [1000.0] * len(symbols),
    })


def test_enriched_multi_date_symbol_lineage_and_concurrent_upsert(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(preferences, "get_pipeline_universe_scope", lambda: "ALL")
    dates = ["2026-08-04", "2026-08-05", "2026-08-06"]
    symbols = ["600000.SH", "000001.SZ", "300750.SZ"]
    for ds in dates:
        out = tmp_path / "kline_daily" / f"date={ds}" / "part.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        _daily_frame(ds, symbols, 10.0 + int(ds[-1])).write_parquet(out)

    assert run_pipeline(data_dir=tmp_path) == 9  # 3 dates × 3 symbols; run_pipeline returns row count
    result = CatalogScanner(tmp_path).scan_dataset("stock_enriched", "run-polars144")
    assert result.state.quality_status == "healthy"
    assert result.state.row_count == 9
    lineage = list((tmp_path / "lineage" / "kline_daily_enriched").rglob("*.json"))
    assert len(lineage) == 3

    target = tmp_path / "kline_daily" / "date=2026-08-06" / "part.parquet"
    lock = threading.Lock()
    errors: list[BaseException] = []

    def _writer(offset: int) -> None:
        try:
            incoming = _daily_frame(
                "2026-08-06",
                [f"60{offset:04d}.SH"],
                20.0 + offset,
            )
            optimistic_upsert_parquet(
                incoming, target, keys=["symbol", "date"], sort_by=["symbol", "date"], lock=lock,
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_writer, args=(i,)) for i in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert errors == []
    written = pl.read_parquet(target)
    assert written.select("symbol").n_unique() >= 3
    assert written.filter(pl.col("date") == date(2026, 8, 6)).height >= 3

    original = pl.read_parquet(target)
    def fail_write(self, path, *args, **kwargs):
        raise OSError("simulated interruption")
    monkeypatch.setattr(pl.DataFrame, "write_parquet", fail_write)
    with pytest.raises(OSError, match="simulated interruption"):
        atomic_write_parquet(_daily_frame("2026-08-06", ["999999.SH"], 1.0), target)
    recovered = pl.read_parquet(target)
    assert recovered.sort(["symbol"]).to_dicts() == original.sort(["symbol"]).to_dicts()
    write_lineage_record(
        tmp_path,
        "kline_daily",
        {
            "date": "2026-08-06",
            "source": "fixture-concurrent",
            "unit_version": "canonical_daily_v1",
            "row_count": recovered.height,
            "scope": "ALL",
            "quality": "healthy",
            "target_artifact": "kline_daily/date=2026-08-06/part.parquet",
        },
        run_id="polars144-recover",
    )
    assert (tmp_path / "lineage" / "kline_daily" / "date=2026-08-06" / "polars144-recover.json").is_file()
