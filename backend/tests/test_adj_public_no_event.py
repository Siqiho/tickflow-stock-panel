from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from app.services.free_sources.adj_factor_public import (
    cumulative_to_event_ex_factors,
    identity_adj_marker_row,
    is_sina_unit_only_cumulative,
    merge_write_adj_coverage,
    merge_write_adj_factor,
    read_adj_coverage,
    is_suspicious_adj_events,
)


def test_unit_only_cumulative_detected():
    assert is_sina_unit_only_cumulative([(date(2020, 7, 16), 1.0)])
    assert not is_sina_unit_only_cumulative([(date(2020, 1, 1), 2.0), (date(2021, 1, 1), 1.0)])


def test_unit_only_has_no_events():
    assert cumulative_to_event_ex_factors([(date(2020, 7, 16), 1.0)]) == []


def _explicit_public_adj(monkeypatch):
    from app.services import kline_sync

    monkeypatch.setattr(kline_sync.preferences, "get_adj_factor_provider", lambda: "public")
    monkeypatch.setattr(kline_sync.preferences, "is_public_adj_factor_provider", lambda name=None: True)


def test_identity_marker_and_coverage_roundtrip(tmp_path: Path, monkeypatch):
    _explicit_public_adj(monkeypatch)
    sym = "688981.SH"
    row = identity_adj_marker_row(sym, as_of=date(2020, 7, 16))
    df = pl.DataFrame([row])
    written, affected = merge_write_adj_factor(df, tmp_path)
    assert written >= 1
    assert sym in affected
    n = merge_write_adj_coverage(
        [{
            "symbol": sym,
            "status": "no_event",
            "source": "test",
            "events_n": 0,
            "checked_at": "2026-01-01T00:00:00",
            "note": "unit",
        }],
        tmp_path,
    )
    assert n == 1
    cov = read_adj_coverage(tmp_path)
    assert cov.filter(pl.col("symbol") == sym)["status"].to_list() == ["no_event"]
    got = pl.read_parquet(tmp_path / "adj_factor" / "all.parquet")
    assert got.filter(pl.col("symbol") == sym)["ex_factor"].to_list() == [1.0]


def test_sync_adj_skips_recent_coverage(tmp_path: Path, monkeypatch):
    from datetime import datetime, timezone
    from app.services.free_sources import adj_factor_public as m

    _explicit_public_adj(monkeypatch)

    # seed recent coverage for A
    merge_write_adj_coverage(
        [{
            "symbol": "000001.SZ",
            "status": "events",
            "source": "test",
            "events_n": 1,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "note": "seed",
        }],
        tmp_path,
    )
    calls=[]
    def fake_meta(symbol, client=None, start=None, end=None, allow_identity_marker=True):
        calls.append(symbol)
        return {
            "frame": pl.DataFrame({
                "symbol":[symbol],
                "trade_date":[date(2024,1,2)],
                "ex_factor":[1.1],
            }),
            "coverage": {
                "symbol": symbol,
                "status": "events",
                "source": "test",
                "events_n": 1,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "note": "fetched",
            },
        }
    monkeypatch.setattr(m, "fetch_adj_factors_symbol_meta", fake_meta)
    out = m.sync_adj_factor_public(
        ["000001.SZ", "000002.SZ"],
        tmp_path,
        workers=1,
        flush_every=1,
        skip_checked_within_hours=18.0,
    )
    assert out["symbols_skipped_n"] == 1
    assert out["symbols_todo_n"] == 1
    assert calls == ["000002.SZ"]


def test_dense_micro_events_are_quarantined():
    events = [
        (date(2024, 1, 1) + __import__("datetime").timedelta(days=i), 1.0005)
        for i in range(180)
    ]

    suspicious, reason = is_suspicious_adj_events(events)

    assert suspicious is True
    assert "dense_micro_events" in reason
