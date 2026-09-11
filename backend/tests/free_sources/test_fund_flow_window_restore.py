"""Restore package: concept H5 roll, run_now isolation, calendar freshness.

All writes stay on tmp DATA_DIR. Fetch calls are monkeypatched. Formal
one-trading/data is only fingerprinted, never written.
"""
from __future__ import annotations

import hashlib
import inspect
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl

from app.data_lab.fixtures import make_trading_calendar_frame
from app.jobs import daily_pipeline
from app.services.free_sources import fund_flow as ff
from app.services.free_sources.fund_flow import (
    aggregate_board_window,
    persist_board_daily_history,
    persist_board_snapshot,
    persist_concept_snapshot,
    roll_concept_daily_from_h5,
    roll_industry_daily_from_h5,
)
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet

OFFICIAL_DATA = Path("/Users/simon/Trading/one-trading/data")


def _h5(code: str, name: str, day: str, net: float) -> dict:
    return {
        "code": code,
        "name": name,
        "date": day,
        "main_net": net,
        "source": "eastmoney_fflow_day",
        "unit_amount": "yuan",
    }


def _board(code: str, name: str, net: float = 1.0, kind: str = "board") -> dict:
    return {
        "code": code,
        "name": name,
        "main_net": net,
        "change_pct": 1.0,
        "as_of": "2026-08-31",
        "kind": kind,
        "source": "eastmoney_bkzj",
        "unit_amount": "yuan",
    }


def _concept(code: str, name: str, net: float = 1.0) -> dict:
    return _board(code, name, net, kind="concept")


def _weekdays_ending(end: date, n: int) -> list[str]:
    days: list[str] = []
    current = end
    while len(days) < n:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current -= timedelta(days=1)
    return list(reversed(days))


def _write_calendar(tmp_path: Path, start: date, end: date) -> None:
    dest = tmp_path / "reference" / "trading_calendar"
    dest.mkdir(parents=True, exist_ok=True)
    make_trading_calendar_frame(
        start=start,
        days=(end - start).days + 1,
        as_of=end,
    ).write_parquet(dest / "calendar.parquet")


def _read_concept_daily(tmp_path: Path, day: str):
    return pl.read_parquet(
        tmp_path / "ext_data" / "ext_fund_flow_concept_daily" / "timeseries" / f"date={day}" / "part.parquet"
    )


def _official_fingerprint() -> dict[str, str]:
    paths = [
        OFFICIAL_DATA / "ext_data" / "ext_fund_flow_bk" / "part.parquet",
        OFFICIAL_DATA / "ext_data" / "ext_fund_flow_concept" / "part.parquet",
        OFFICIAL_DATA / "reference" / "trading_calendar" / "calendar.parquet",
    ]
    out: dict[str, str] = {}
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        out[str(path)] = f"{path.stat().st_size}:{digest}"
    for rel in (
        "ext_data/ext_fund_flow_bk_daily/timeseries",
        "ext_data/ext_fund_flow_concept_daily/timeseries",
    ):
        root = OFFICIAL_DATA / rel
        names = sorted(p.name for p in root.glob("date=*") if p.is_dir()) if root.exists() else []
        out[str(root)] = ",".join(names)
    return out


def _capset() -> CapabilitySet:
    return CapabilitySet({
        Cap.KLINE_DAILY_BATCH: CapabilityLimits(),
        Cap.QUOTE_POOL: CapabilityLimits(),
        Cap.ADJ_FACTOR: CapabilityLimits(),
    })


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


def _stub_pipeline(monkeypatch, tmp_path: Path, latest: date):
    monkeypatch.setattr(
        daily_pipeline.instrument_sync,
        "sync_instruments_result",
        lambda _data_dir: _ok_instruments(),
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
    monkeypatch.setattr(daily_pipeline.kline_sync, "sync_daily_by_quotes", lambda _repo: 99)
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
    )


def test_industry_budget_stays_180s_and_concept_is_720s():
    industry_src = inspect.getsource(ff.roll_industry_daily_from_h5)
    concept_src = inspect.getsource(ff.roll_concept_daily_from_h5)
    assert "time_limit_s = 180.0" in industry_src
    assert "time_limit_s = 720.0" in concept_src
    fetch_src = inspect.getsource(ff.fetch_board_daily_history)
    assert "timeout=8.0" in fetch_src
    assert "cancel_event" not in fetch_src


def test_concept_roll_uses_snapshot_universe_and_concept_target(monkeypatch, tmp_path: Path):
    persist_concept_snapshot(tmp_path, [_concept(f"BK{i:04d}", f"概念{i}") for i in range(12)])
    calls: list[str] = []
    top_calls = {"n": 0}

    def fake_fetch(code, **kwargs):
        assert kwargs.get("allow_local_fallback") is False
        assert kwargs.get("prefer_h5") is True
        assert kwargs.get("h5_only") is True
        assert kwargs.get("kind") == "concept"
        calls.append(code)
        return [_h5(code, code, "2026-09-01", 1.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    monkeypatch.setattr(
        ff,
        "refresh_top_boards_daily_history",
        lambda *_a, **_k: top_calls.__setitem__("n", top_calls["n"] + 1),
    )
    result = roll_concept_daily_from_h5(tmp_path, pause_s=0)
    assert result["kind"] == "concept"
    assert result["selected"] == 12
    assert len(calls) == 12
    assert result["ok"] is True
    assert top_calls["n"] == 0
    assert "freshness_status" not in result
    written = tmp_path / "ext_data" / "ext_fund_flow_concept_daily" / "timeseries" / "date=2026-09-01" / "part.parquet"
    assert written.exists()
    assert not (tmp_path / "ext_data" / "ext_fund_flow_bk_daily" / "timeseries").exists()
    lock = tmp_path / "ext_data" / "ext_fund_flow_concept_daily" / ".concept_daily_roll.lock"
    assert lock.exists()


def test_concept_stable_universe_ok_ignores_new_theme_failure(monkeypatch, tmp_path: Path):
    persist_concept_snapshot(
        tmp_path,
        [
            _concept("BK0001", "稳定A"),
            _concept("BK0002", "稳定B"),
            _concept("BK0099", "新主题"),
        ],
    )
    persist_board_daily_history(
        tmp_path,
        "x",
        [_h5("BK0001", "稳定A", "2026-08-31", 1.0), _h5("BK0002", "稳定B", "2026-08-31", 2.0)],
        kind="concept",
    )

    def fake_fetch(code, **kwargs):
        assert kwargs.get("kind") == "concept"
        if code == "BK0099":
            raise RuntimeError("new theme empty")
        return [_h5(code, code, "2026-08-31", 1.0), _h5(code, code, "2026-09-01", 10.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    result = roll_concept_daily_from_h5(tmp_path, pause_s=0)
    assert result["latest_data_date"] == "2026-09-01"
    assert result["latest_day_complete"] is True
    assert result["ok"] is True
    assert result["stable_selected"] == 2
    assert any(item["code"] == "BK0099" for item in result["failed"])
    after = aggregate_board_window(tmp_path, kind="concept", days=1, top=8)
    assert after["end"] == "2026-09-01"
    assert "freshness_status" not in after


def test_concept_independent_lock_budget_cancel_and_failure(monkeypatch, tmp_path: Path):
    persist_concept_snapshot(
        tmp_path,
        [_concept("BK0001", "头"), _concept("BK0002", "中"), _concept("BK0003", "尾")],
    )
    persist_board_snapshot(tmp_path, [_board("BK1001", "行业")])
    persist_board_daily_history(
        tmp_path,
        "x",
        [
            _h5("BK0001", "头", "2026-08-31", 1.0),
            _h5("BK0002", "中", "2026-08-31", 2.0),
            _h5("BK0003", "尾", "2026-08-31", 3.0),
        ],
        kind="concept",
    )
    persist_board_daily_history(tmp_path, "BK1001", [_h5("BK1001", "行业", "2026-08-31", 9.0)], kind="board")

    calls: list[str] = []

    def slow_fetch(code, **kwargs):
        calls.append(code)
        time.sleep(0.12)
        return [_h5(code, code, "2026-09-01", 90.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", slow_fetch)
    first = roll_concept_daily_from_h5(tmp_path, pause_s=0, batch_size=1, time_limit_s=0.05)
    assert first["status"] == "timeout"
    assert first["ok"] is False
    assert calls == ["BK0001"]

    calls.clear()
    second = roll_concept_daily_from_h5(tmp_path, pause_s=0, batch_size=1, time_limit_s=30)
    assert "BK0001" not in calls
    assert calls == ["BK0002", "BK0003"]
    assert second["ok"] is True
    assert set(second["skipped_already_current"]) == {"BK0001"}

    monkeypatch.setattr(ff, "fetch_board_daily_history", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("em down")))
    failed = roll_concept_daily_from_h5(tmp_path, pause_s=0)
    assert failed["ok"] is False
    assert _read_concept_daily(tmp_path, "2026-08-31").filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 1.0

    hold = threading.Event()
    in_fetch = threading.Event()

    def blocking_concept(code, **kwargs):
        if kwargs.get("kind") == "concept":
            in_fetch.set()
            hold.wait(2)
            return [_h5(code, code, "2026-09-02", 1.0)]
        return [_h5(code, code, "2026-09-02", 2.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", blocking_concept)
    concept_results: list[dict] = []

    def run_concept():
        concept_results.append(roll_concept_daily_from_h5(tmp_path, pause_s=0))

    first_thread = threading.Thread(target=run_concept)
    first_thread.start()
    assert in_fetch.wait(2)
    industry = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert industry["kind"] == "board"
    assert industry.get("skipped_lock") is not True
    busy = roll_concept_daily_from_h5(tmp_path, pause_s=0)
    assert busy.get("skipped_lock") is True
    hold.set()
    first_thread.join(2)

    cancel = threading.Event()
    cancel_calls: list[str] = []

    def cancel_fetch(code, **kwargs):
        cancel_calls.append(code)
        cancel.set()
        return [_h5(code, code, "2026-09-03", 11.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", cancel_fetch)
    cancelled = roll_concept_daily_from_h5(tmp_path, pause_s=0, cancel_event=cancel, time_limit_s=30)
    assert cancelled["status"] == "cancelled"
    assert cancel_calls == ["BK0001"]


def test_run_now_industry_then_concept_and_failure_isolation(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK1001", "行业")])
    persist_concept_snapshot(tmp_path, [_concept("BK0001", "主题")])
    persist_board_daily_history(tmp_path, "BK1001", [_h5("BK1001", "行业", "2026-08-31", 1.0)], kind="board")
    persist_board_daily_history(tmp_path, "BK0001", [_h5("BK0001", "主题", "2026-08-31", 2.0)], kind="concept")
    events: list[str] = []
    kinds: list[str] = []

    def fake_fetch(code, **kwargs):
        kinds.append(str(kwargs.get("kind")))
        return [_h5(code, code, "2026-09-01", 3.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    repo = _stub_pipeline(monkeypatch, tmp_path, latest=date.today())
    result = daily_pipeline.run_now(
        repo,
        _capset(),
        on_progress=lambda stage, pct, msg, **_k: events.append(stage),
    )
    assert events[-1] == "done"
    assert events.index("industry_fund_flow") < events.index("concept_fund_flow") < events.index("done")
    assert kinds == ["board", "concept"]
    assert result["quality"]["ok"] is True
    assert result["industry_fund_flow_daily"]["ok"] is True
    assert result["concept_fund_flow_daily"]["ok"] is True
    assert "freshness_status" not in result["concept_fund_flow_daily"]

    persist_board_snapshot(tmp_path, [_board("BK1001", "行业"), _board("BK1002", "行业2")])
    persist_board_daily_history(
        tmp_path,
        "x",
        [_h5("BK1001", "行业", "2026-08-31", 1.0), _h5("BK1002", "行业2", "2026-08-31", 2.0)],
        kind="board",
    )

    def slow_industry(code, **kwargs):
        if kwargs.get("kind") == "board":
            time.sleep(0.12)
        return [_h5(code, code, "2026-09-01", 9.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", slow_industry)
    timed = daily_pipeline.run_now(repo, _capset(), industry_time_limit_s=0.05)
    assert timed["quality"]["ok"] is True
    assert timed["industry_fund_flow_daily"]["status"] == "timeout"
    assert timed["concept_fund_flow_daily"]["ok"] is True

    def boom(*_a, **_k):
        raise RuntimeError("concept exploded")

    monkeypatch.setattr(ff, "roll_concept_daily_from_h5", boom)
    monkeypatch.setattr(ff, "fetch_board_daily_history", lambda code, **_k: [_h5(code, code, "2026-09-01", 1.0)])
    failed = daily_pipeline.run_now(repo, _capset())
    assert failed["quality"]["ok"] is True
    assert failed["concept_fund_flow_daily"]["status"] == "error"
    assert "不影响已成功日K" in failed["concept_fund_flow_daily"]["note"]


def test_calendar_stale_unknown_and_coverage(tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行")])
    persist_board_daily_history(tmp_path, "BK0001", [_h5("BK0001", "银行", "2026-08-31", 1.0)], kind="board")
    (tmp_path / "kline_daily" / "date=2026-09-07").mkdir(parents=True)
    unknown = aggregate_board_window(
        tmp_path,
        kind="board",
        days=1,
        top=6,
        as_of_today=date(2026, 9, 7),
    )
    assert unknown["window_complete"] is True
    assert unknown["end"] == "2026-08-31"
    assert unknown["data_as_of"] == "2026-08-31"
    assert unknown["freshness_status"] == "unknown"
    assert unknown["calendar_covers"] is False
    assert "无法确定" in unknown["freshness_note"]

    _write_calendar(tmp_path, date(2026, 8, 3), date(2026, 8, 31))
    still_unknown = aggregate_board_window(
        tmp_path,
        kind="board",
        days=1,
        top=6,
        as_of_today=date(2026, 9, 7),
    )
    assert still_unknown["freshness_status"] == "unknown"
    assert still_unknown["calendar_covers"] is False
    assert still_unknown["expected_trading_day"] is None

    _write_calendar(tmp_path, date(2026, 8, 3), date(2026, 9, 7))
    stale = aggregate_board_window(
        tmp_path,
        kind="board",
        days=1,
        top=6,
        as_of_today=date(2026, 9, 7),
    )
    assert stale["freshness_status"] == "stale"
    assert stale["calendar_covers"] is True
    assert stale["expected_trading_day"] == "2026-09-07"
    assert stale["freshness_note"] == "已陈旧"

    persist_board_daily_history(tmp_path, "BK0001", [_h5("BK0001", "银行", "2026-09-07", 2.0)], kind="board")
    fresh = aggregate_board_window(
        tmp_path,
        kind="board",
        days=1,
        top=6,
        as_of_today=date(2026, 9, 7),
    )
    assert fresh["end"] == "2026-09-07"
    assert fresh["freshness_status"] == "fresh"
    assert fresh["freshness_note"] == "足够新"

    concept = aggregate_board_window(tmp_path, kind="concept", days=1, top=6, as_of_today=date(2026, 9, 7))
    assert "freshness_status" not in concept


def test_rolls_and_run_now_do_not_write_formal_data(monkeypatch, tmp_path: Path):
    before = _official_fingerprint()
    persist_concept_snapshot(tmp_path, [_concept("BK0001", "主题")])
    persist_board_snapshot(tmp_path, [_board("BK1001", "行业")])
    monkeypatch.setattr(
        ff,
        "fetch_board_daily_history",
        lambda code, **kwargs: [_h5(code, code, "2026-09-01", 1.0)],
    )
    roll_concept_daily_from_h5(tmp_path, pause_s=0)
    roll_industry_daily_from_h5(tmp_path, pause_s=0)
    repo = _stub_pipeline(monkeypatch, tmp_path, latest=date.today())
    daily_pipeline.run_now(repo, _capset(), industry_time_limit_s=1, concept_time_limit_s=1)
    after = _official_fingerprint()
    assert before == after
    assert not str(OFFICIAL_DATA) in str(tmp_path)
    assert (tmp_path / "ext_data" / "ext_fund_flow_concept_daily").exists()
    assert not any(
        OFFICIAL_DATA in path.parents or path == OFFICIAL_DATA
        for path in tmp_path.rglob("*")
    )
