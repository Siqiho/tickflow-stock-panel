from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import polars as pl

from app.jobs import daily_pipeline
from app.services import instrument_sync


def _row(symbol: str, exchange: str) -> dict:
    code = symbol.split(".", 1)[0]
    return {
        "symbol": symbol,
        "name": symbol,
        "code": code,
        "exchange": exchange,
        "region": "CN",
        "type": "stock",
        "ext": {
            "listing_date": "2020-01-01",
            "total_shares": 1_000,
            "float_shares": 900,
            "tick_size": 0.01,
            "limit_up": 11.0,
            "limit_down": 9.0,
        },
    }


def _stored_row(symbol: str, exchange: str, *, as_of: date = date(2026, 8, 4)) -> dict:
    row = instrument_sync._flatten_instruments([_row(symbol, exchange)])[0]
    row["as_of"] = as_of
    return row


def _write_prior(path: Path, rows: list[dict]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _Exchanges:
    def __init__(self, rows: dict[str, list[dict]], *, fail: str | None = None) -> None:
        self.rows = rows
        self.fail = fail

    def get_instruments(self, exchange: str, instrument_type: str) -> list[dict]:
        assert instrument_type == "stock"
        if exchange == self.fail:
            raise TimeoutError(f"{exchange} timed out")
        return self.rows.get(exchange, [])


def _client(rows: dict[str, list[dict]], *, fail: str | None = None):
    return type("Client", (), {"exchanges": _Exchanges(rows, fail=fail)})()


def test_partial_exchange_timeout_keeps_complete_prior(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "instruments" / "instruments.parquet"
    before_sha = _write_prior(
        path,
        [
            _stored_row("600000.SH", "SH"),
            _stored_row("000001.SZ", "SZ"),
            _stored_row("920001.BJ", "BJ"),
        ],
    )
    monkeypatch.setattr(
        instrument_sync,
        "get_client",
        lambda: _client(
            {
                "SH": [_row("600000.SH", "SH")],
                "BJ": [_row("920001.BJ", "BJ")],
            },
            fail="SZ",
        ),
    )

    result = instrument_sync.sync_instruments_result(tmp_path)

    assert result.outcome == "kept_prior"
    assert result.error_code == "required_exchange_incomplete"
    assert result.failed_exchanges == ("SZ",)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before_sha
    assert set(pl.read_parquet(path).get_column("exchange")) == {"SH", "SZ", "BJ"}


def test_coverage_drop_keeps_valid_prior(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(instrument_sync, "FIRST_SNAPSHOT_MIN_ROWS", 1)
    path = tmp_path / "instruments" / "instruments.parquet"
    prior = [
        *[_stored_row(f"6{i:05d}.SH", "SH") for i in range(10)],
        *[_stored_row(f"0{i:05d}.SZ", "SZ") for i in range(10)],
        *[_stored_row(f"92{i:04d}.BJ", "BJ") for i in range(10)],
    ]
    before_sha = _write_prior(path, prior)
    rows = {
        "SH": [_row(f"6{i:05d}.SH", "SH") for i in range(10)],
        "SZ": [_row(f"0{i:05d}.SZ", "SZ") for i in range(9)],
        "BJ": [_row(f"92{i:04d}.BJ", "BJ") for i in range(8)],
    }
    monkeypatch.setattr(instrument_sync, "get_client", lambda: _client(rows))

    result = instrument_sync.sync_instruments_result(tmp_path)

    assert result.outcome == "kept_prior"
    assert result.error_code == "coverage_below_prior"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before_sha


def test_complete_candidate_recovers_invalid_prior_and_writes_lineage(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(instrument_sync, "FIRST_SNAPSHOT_MIN_ROWS", 3)
    path = tmp_path / "instruments" / "instruments.parquet"
    _write_prior(
        path,
        [
            _stored_row("600000.SH", "SH", as_of=date(2026, 8, 5)),
            _stored_row("920001.BJ", "BJ", as_of=date(2026, 8, 5)),
        ],
    )
    rows = {
        "SH": [_row("600000.SH", "SH")],
        "SZ": [_row("000001.SZ", "SZ")],
        "BJ": [_row("920001.BJ", "BJ")],
    }
    monkeypatch.setattr(instrument_sync, "get_client", lambda: _client(rows))

    result = instrument_sync.sync_instruments_result(tmp_path)

    assert result.outcome == "published"
    assert result.rows_published == 3
    assert result.market_counts == {"SH": 1, "SZ": 1, "BJ": 1}
    assert set(pl.read_parquet(path).get_column("exchange")) == {"SH", "SZ", "BJ"}
    lineage = list((tmp_path / "lineage" / "stock_instruments").rglob("*.json"))
    assert len(lineage) == 1


def test_scheduled_instruments_failure_is_degraded_and_does_not_refresh(
    tmp_path: Path, monkeypatch
) -> None:
    outcome = instrument_sync.InstrumentSyncOutcome(
        outcome="kept_prior",
        rows_fetched=2,
        rows_published=0,
        market_counts={"SH": 1, "SZ": 0, "BJ": 1},
        prior_rows=5_539,
        prior_market_counts={"SH": 2_310, "SZ": 2_896, "BJ": 333},
        failed_exchanges=("SZ",),
        error_code="required_exchange_incomplete",
        error_message="SZ: TimeoutError",
    )
    monkeypatch.setattr(instrument_sync, "sync_instruments_result", lambda _data_dir: outcome)
    refreshed: list[str] = []
    invalidated: list[str] = []
    monkeypatch.setattr(
        daily_pipeline, "_refresh_instruments_view", lambda _repo: refreshed.append("view")
    )
    monkeypatch.setattr(daily_pipeline, "_invalidate", invalidated.append)
    repo = type("Repo", (), {"store": type("Store", (), {"data_dir": tmp_path})()})()

    result = daily_pipeline.run_instruments_sync(repo)

    assert result["outcome"] == "kept_prior"
    assert result["instruments_rows"] == 5_539
    assert result["quality"]["ok"] is False
    assert refreshed == []
    assert invalidated == []
