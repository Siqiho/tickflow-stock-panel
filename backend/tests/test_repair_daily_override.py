"""日K修复入口必须把用户指定起点传进盘后管道。"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

from app.jobs import daily_pipeline
from app.services.repair_daily import run_repair_daily
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet


def _ok_instruments():
    return SimpleNamespace(
        ok=True,
        rows_published=3,
        prior_rows=3,
        error_code=None,
        error_message=None,
        failed_exchanges=(),
        as_dict=lambda: {"outcome": "published", "rows_published": 3},
    )


def _capset() -> CapabilitySet:
    return CapabilitySet({
        Cap.KLINE_DAILY_BATCH: CapabilityLimits(),
        Cap.QUOTE_POOL: CapabilityLimits(),
        Cap.ADJ_FACTOR: CapabilityLimits(),
    })


def _stub_common(monkeypatch, tmp_path, latest: date):
    captured: dict = {}
    monkeypatch.setattr(
        daily_pipeline.instrument_sync,
        "sync_instruments_result",
        lambda _data_dir: _ok_instruments(),
    )
    monkeypatch.setattr(daily_pipeline, "resolve_universe", lambda _capset: ["000001.SZ"])
    monkeypatch.setattr(daily_pipeline, "_refresh_instruments_view", lambda _repo: None)
    monkeypatch.setattr(daily_pipeline, "_refresh_single_view", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(daily_pipeline, "_refresh_views", lambda _repo: None)
    monkeypatch.setattr(daily_pipeline, "_invalidate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(daily_pipeline, "run_pipeline", lambda **_kwargs: 0)
    monkeypatch.setattr(daily_pipeline, "run_daily_quality_check", lambda _data_dir: {"ok": True, "issues": []})
    monkeypatch.setattr(daily_pipeline._prefs, "get_pipeline_pull_a_share", lambda: True)
    monkeypatch.setattr(daily_pipeline._prefs, "get_pipeline_pull_index", lambda: True)
    monkeypatch.setattr(daily_pipeline._prefs, "get_pipeline_pull_etf", lambda: True)
    monkeypatch.setattr(daily_pipeline._prefs, "get_minute_sync_enabled", lambda: False)
    monkeypatch.setattr(daily_pipeline._prefs, "is_public_adj_factor_provider", lambda: False)
    monkeypatch.setattr(daily_pipeline._prefs, "is_public_financial_provider", lambda: False)

    def sync_daily_batch(universe, repo, capset, start_date, end_date, on_chunk_done=None):
        captured["daily"] = {
            "universe": universe,
            "start_date": start_date,
            "end_date": end_date,
        }
        return 11

    def sync_quotes(repo):
        captured["quotes"] = True
        return 99

    def sync_adj(universe, repo, capset, start_time, end_time, on_chunk_done=None):
        captured["adj_start"] = start_time
        return 0, []

    def sync_index_instruments(repo, pull_index=True, pull_etf=False):
        return 1

    def sync_index_daily(repo, capset, start_date, end_date, on_chunk_done=None):
        captured["index_start"] = start_date
        return 4

    def sync_etf_instruments(repo):
        return 0

    monkeypatch.setattr(daily_pipeline.kline_sync, "sync_and_persist_daily_batch", sync_daily_batch)
    monkeypatch.setattr(daily_pipeline.kline_sync, "sync_daily_by_quotes", sync_quotes)
    monkeypatch.setattr(daily_pipeline.kline_sync, "sync_adj_factor", sync_adj)
    monkeypatch.setattr(daily_pipeline.index_sync, "sync_index_instruments", sync_index_instruments)
    monkeypatch.setattr(daily_pipeline.index_sync, "sync_and_persist_index_daily", sync_index_daily)
    monkeypatch.setattr(daily_pipeline.index_sync, "sync_etf_instruments", sync_etf_instruments)
    monkeypatch.setattr(daily_pipeline.index_sync, "sync_and_persist_etf_daily", lambda *a, **k: 0)

    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        latest_daily_date=lambda: latest,
        get_etf_instruments=lambda: type("Empty", (), {"is_empty": lambda self: True})(),
        refresh_index_views=lambda: None,
    )
    return repo, captured


def test_override_start_date_uses_batch_even_when_today_exists(monkeypatch, tmp_path):
    today = date.today()
    start = today.replace(day=max(1, today.day - 5)) if today.day > 5 else date(today.year, today.month, 1)
    repo, captured = _stub_common(monkeypatch, tmp_path, latest=today)
    result = daily_pipeline.run_now(
        repo,
        _capset(),
        override_start_date=start,
    )
    assert "quotes" not in captured
    assert captured["daily"]["start_date"] == datetime.combine(start, datetime.min.time())
    assert captured["adj_start"].date() == start
    assert captured["index_start"] == datetime.combine(start, datetime.min.time())
    assert result["override_start_date"] == start.isoformat()
    assert result["daily_source"] == "tickflow_batch"


def test_regular_run_now_still_uses_live_quotes_when_today_exists(monkeypatch, tmp_path):
    today = date.today()
    repo, captured = _stub_common(monkeypatch, tmp_path, latest=today)
    result = daily_pipeline.run_now(repo, _capset())
    assert captured.get("quotes") is True
    assert "daily" not in captured
    assert result["override_start_date"] is None
    assert result["daily_source"] == "tickflow_quotes"


def test_repair_daily_forwards_override_start_date(monkeypatch):
    seen = {}

    def fake_run_now(repo, capset, on_progress=None, override_start_date=None):
        seen["override_start_date"] = override_start_date
        return {"ok": True}

    monkeypatch.setattr("app.jobs.daily_pipeline.run_now", fake_run_now)
    result = run_repair_daily(object(), _capset(), date(2026, 7, 19))
    assert result == {"ok": True}
    assert seen["override_start_date"] == date(2026, 7, 19)
