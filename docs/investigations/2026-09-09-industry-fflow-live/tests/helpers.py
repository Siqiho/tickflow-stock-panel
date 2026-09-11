from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from app.jobs import daily_pipeline
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet


def weekdays_ending(end: date, n: int) -> list[str]:
    days: list[str] = []
    current = end
    while len(days) < n:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current -= timedelta(days=1)
    return list(reversed(days))


def h5(code: str, name: str, day: str, net: float) -> dict:
    return {
        "code": code,
        "name": name,
        "date": day,
        "main_net": net,
        "source": "eastmoney_fflow_day",
        "unit_amount": "yuan",
    }


def board(code: str, name: str, net: float = 1.0) -> dict:
    return {
        "code": code,
        "name": name,
        "main_net": net,
        "change_pct": 1.0,
        "as_of": "2026-08-31",
        "kind": "board",
        "source": "eastmoney_bkzj",
        "unit_amount": "yuan",
    }


def write_calendar(tmp_path: Path, start: date, end: date) -> None:
    from app.data_lab.fixtures import make_trading_calendar_frame

    dest = tmp_path / "reference" / "trading_calendar"
    dest.mkdir(parents=True, exist_ok=True)
    make_trading_calendar_frame(start=start, days=(end - start).days + 1, as_of=end).write_parquet(
        dest / "calendar.parquet"
    )


def read_daily(tmp_path: Path, day: str):
    import polars as pl

    return pl.read_parquet(
        tmp_path / "ext_data" / "ext_fund_flow_bk_daily" / "timeseries" / f"date={day}" / "part.parquet"
    )


def capset() -> CapabilitySet:
    return CapabilitySet({
        Cap.KLINE_DAILY_BATCH: CapabilityLimits(),
        Cap.QUOTE_POOL: CapabilityLimits(),
        Cap.ADJ_FACTOR: CapabilityLimits(),
    })


def ok_instruments():
    return SimpleNamespace(
        ok=True,
        rows_published=3,
        prior_rows=3,
        error_code=None,
        error_message=None,
        failed_exchanges=(),
        as_dict=lambda: {"outcome": "published", "rows_published": 3},
    )


def stub_pipeline(monkeypatch, tmp_path: Path, latest: date, quotes_box: dict | None = None):
    quotes_box = quotes_box if quotes_box is not None else {}
    monkeypatch.setattr(
        daily_pipeline.instrument_sync,
        "sync_instruments_result",
        lambda _data_dir: ok_instruments(),
    )
    monkeypatch.setattr(daily_pipeline, "resolve_universe", lambda _capset: ["000001.SZ"])
    monkeypatch.setattr(daily_pipeline, "_refresh_instruments_view", lambda _repo: None)
    monkeypatch.setattr(daily_pipeline, "_refresh_single_view", lambda *_a, **_k: None)
    monkeypatch.setattr(daily_pipeline, "_refresh_views", lambda _repo: None)
    monkeypatch.setattr(daily_pipeline, "_invalidate", lambda *_a, **_k: None)
    monkeypatch.setattr(daily_pipeline, "run_pipeline", lambda **_k: 0)
    monkeypatch.setattr(daily_pipeline, "fill_enriched_coverage_gap", lambda **_k: 0)
    monkeypatch.setattr(daily_pipeline, "run_daily_quality_check", lambda _d: {"ok": True, "issues": []})
    monkeypatch.setattr(daily_pipeline._prefs, "get_pipeline_pull_a_share", lambda: True)
    monkeypatch.setattr(daily_pipeline._prefs, "get_pipeline_pull_index", lambda: True)
    monkeypatch.setattr(daily_pipeline._prefs, "get_pipeline_pull_etf", lambda: True)
    monkeypatch.setattr(daily_pipeline._prefs, "get_pipeline_universe_scope", lambda: "ALL")
    monkeypatch.setattr(daily_pipeline._prefs, "get_minute_sync_enabled", lambda: False)
    monkeypatch.setattr(daily_pipeline._prefs, "get_minute_sync_days", lambda: 5)
    monkeypatch.setattr(daily_pipeline._prefs, "is_public_adj_factor_provider", lambda: False)
    monkeypatch.setattr(daily_pipeline._prefs, "is_public_financial_provider", lambda: False)
    monkeypatch.setattr(daily_pipeline._prefs, "get_realtime_data_provider", lambda: "public")
    monkeypatch.setattr(daily_pipeline.kline_sync, "sync_and_persist_daily_batch", lambda *a, **k: 11)

    def sync_quotes(_repo):
        quotes_box["n"] = quotes_box.get("n", 0) + 1
        return 99

    monkeypatch.setattr(daily_pipeline.kline_sync, "sync_daily_by_quotes", sync_quotes)
    monkeypatch.setattr(daily_pipeline.kline_sync, "sync_adj_factor", lambda *a, **k: (0, []))
    monkeypatch.setattr(daily_pipeline.index_sync, "sync_index_instruments", lambda *a, **k: 1)
    monkeypatch.setattr(daily_pipeline.index_sync, "sync_and_persist_index_daily", lambda *a, **k: 4)
    monkeypatch.setattr(daily_pipeline.index_sync, "sync_etf_instruments", lambda *a, **k: 0)
    monkeypatch.setattr(daily_pipeline.index_sync, "sync_and_persist_etf_daily", lambda *a, **k: 0)
    return SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        latest_daily_date=lambda: latest,
        get_etf_instruments=lambda: type("Empty", (), {"is_empty": lambda self: True})(),
        refresh_index_views=lambda: None,
    ), quotes_box
