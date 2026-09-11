from __future__ import annotations

import inspect
import threading
import time
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from app.api import pipeline as pipeline_api
from app.jobs import daily_pipeline
from app.services.ext_data import write_ext_parquet
from app.services.free_sources import fund_flow as ff
from app.services.free_sources.fund_flow import (
    aggregate_board_window,
    persist_board_daily_history,
    persist_board_snapshot,
    roll_industry_daily_from_h5,
)
from app.services.free_sources.http_resilience import FetchResult
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet

TASK = Path("/Users/simon/Trading/one-trading/docs/investigations/2026-09-07-industry-fflow-daily-roll")
SHANGHAI = ZoneInfo("Asia/Shanghai")
H5_URL = "https://emdatah5.eastmoney.com/dc/ZJLX/getDBHistoryData"


def _h5(code: str, name: str, day: str, net: float) -> dict:
    return {
        "code": code,
        "name": name,
        "date": day,
        "main_net": net,
        "source": "eastmoney_fflow_day",
        "unit_amount": "yuan",
    }


def _board(code: str, name: str, net: float = 1.0) -> dict:
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


def _write_calendar(tmp_path: Path, start: date, end: date) -> None:
    from app.data_lab.fixtures import make_trading_calendar_frame

    dest = tmp_path / "reference" / "trading_calendar"
    dest.mkdir(parents=True, exist_ok=True)
    frame = make_trading_calendar_frame(start=start, days=(end - start).days + 1, as_of=end)
    frame.write_parquet(dest / "calendar.parquet")


def _read_daily(tmp_path: Path, day: str) -> pl.DataFrame:
    return pl.read_parquet(
        tmp_path / "ext_data" / "ext_fund_flow_bk_daily" / "timeseries" / f"date={day}" / "part.parquet"
    )


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


def _stub_pipeline(monkeypatch, tmp_path: Path, latest: date, quotes_box: dict):
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
    monkeypatch.setattr(daily_pipeline, "run_daily_quality_check", lambda _d: {"ok": True, "issues": []})
    monkeypatch.setattr(daily_pipeline._prefs, "get_pipeline_pull_a_share", lambda: True)
    monkeypatch.setattr(daily_pipeline._prefs, "get_pipeline_pull_index", lambda: True)
    monkeypatch.setattr(daily_pipeline._prefs, "get_pipeline_pull_etf", lambda: True)
    monkeypatch.setattr(daily_pipeline._prefs, "get_minute_sync_enabled", lambda: False)
    monkeypatch.setattr(daily_pipeline._prefs, "is_public_adj_factor_provider", lambda: False)
    monkeypatch.setattr(daily_pipeline._prefs, "is_public_financial_provider", lambda: False)
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
    )


def test_fixes_load_all_related_overlays():
    assert Path(inspect.getfile(ff)).resolve() == TASK / "overlay/backend/app/services/free_sources/fund_flow.py"
    assert Path(inspect.getfile(daily_pipeline)).resolve() == TASK / "overlay/backend/app/jobs/daily_pipeline.py"
    assert Path(inspect.getfile(write_ext_parquet)).resolve() == TASK / "overlay/backend/app/services/ext_data.py"
    assert Path(inspect.getfile(pipeline_api)).resolve() == TASK / "overlay/backend/app/api/pipeline.py"
    source = inspect.getsource(write_ext_parquet)
    assert "atomic: bool = False" in source
    assert "df.write_parquet(out_path)" in source
    assert "atomic_write_parquet(df, out_path)" in source
    assert "pipeline_in_flight" in inspect.getsource(pipeline_api.run_now)
    assert "request_pipeline_cancel" in inspect.getsource(pipeline_api.cancel_job)


def test_old_day_h5_reply_keeps_local_latest_complete(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行"), _board("BK0002", "电力")])
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [
            _h5("BK0001", "银行", "2026-08-31", 7.0),
            _h5("BK0002", "电力", "2026-08-31", 8.0),
        ],
        kind="board",
    )

    def fake_fetch(code, **kwargs):
        assert kwargs.get("prefer_h5") is True
        assert kwargs.get("h5_only") is True
        assert kwargs.get("allow_local_fallback") is False
        name = "银行" if code == "BK0001" else "电力"
        return [_h5(code, name, "2026-08-28", 70.0 if code == "BK0001" else 80.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert result["ok"] is True
    assert result["latest_data_date"] == "2026-08-31"
    assert result["latest_day_complete"] is True
    day = _read_daily(tmp_path, "2026-08-31")
    assert day.filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 7.0
    old_reply = _read_daily(tmp_path, "2026-08-28")
    assert old_reply.filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 70.0
    assert (tmp_path / "ext_data/ext_fund_flow_bk_daily/timeseries/date=2026-09-01").exists() is False


def test_leftover_newer_date_outside_snapshot_does_not_poison_latest(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行"), _board("BK0002", "电力")])
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [
            _h5("BK0001", "银行", "2026-08-31", 1.0),
            _h5("BK0002", "电力", "2026-08-31", 2.0),
            _h5("BK9999", "遗留", "2026-09-02", 9.0),
        ],
        kind="board",
    )

    def fake_fetch(code, **kwargs):
        return [_h5(code, code, "2026-08-31", 3.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert result["failed"] == []
    assert result["history_codes"] == ["BK0001", "BK0002"]
    assert result["latest_data_date"] == "2026-08-31"
    assert result["latest_day_complete"] is True
    assert result["ok"] is True
    leftover = _read_daily(tmp_path, "2026-09-02")
    assert leftover.filter(pl.col("code") == "BK9999").height == 1


def test_intraday_before_close_uses_previous_open_day(tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行")])
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [_h5("BK0001", "银行", "2026-08-28", 1.0)],
        kind="board",
    )
    _write_calendar(tmp_path, date(2026, 8, 3), date(2026, 8, 31))
    monday_open = aggregate_board_window(
        tmp_path,
        kind="board",
        days=1,
        top=6,
        as_of_today=date(2026, 8, 31),
        as_of_now=datetime(2026, 8, 31, 10, 0, tzinfo=SHANGHAI),
    )
    assert monday_open["expected_trading_day"] == "2026-08-28"
    assert monday_open["window_complete"] is True
    assert monday_open["freshness_status"] == "fresh"
    after_close = aggregate_board_window(
        tmp_path,
        kind="board",
        days=1,
        top=6,
        as_of_today=date(2026, 8, 31),
        as_of_now=datetime(2026, 8, 31, 15, 0, tzinfo=SHANGHAI),
    )
    assert after_close["expected_trading_day"] == "2026-08-31"
    assert after_close["freshness_status"] == "stale"
    date_only = aggregate_board_window(
        tmp_path, kind="board", days=1, top=6, as_of_today=date(2026, 8, 31)
    )
    assert date_only["expected_trading_day"] == "2026-08-31"
    assert date_only["freshness_status"] == "stale"


def test_weekend_and_holiday_and_unknown_calendar(tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行")])
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [_h5("BK0001", "银行", "2026-08-28", 1.0)],
        kind="board",
    )
    _write_calendar(tmp_path, date(2026, 8, 3), date(2026, 8, 30))
    sat = aggregate_board_window(
        tmp_path,
        kind="board",
        days=1,
        top=6,
        as_of_today=date(2026, 8, 29),
        as_of_now=datetime(2026, 8, 29, 10, 30, tzinfo=SHANGHAI),
    )
    assert sat["calendar_covers"] is True
    assert sat["expected_trading_day"] == "2026-08-28"
    assert sat["freshness_status"] == "fresh"

    from app.data_lab.fixtures import make_trading_calendar_frame

    dest = tmp_path / "reference" / "trading_calendar"
    dest.mkdir(parents=True, exist_ok=True)
    frame = make_trading_calendar_frame(start=date(2026, 8, 24), days=8, as_of=date(2026, 8, 31))
    rows = frame.to_dicts()
    for row in rows:
        if str(row["trade_date"])[:10] == "2026-08-31":
            row["is_open"] = False
            row["session_type"] = "holiday"
            row["close_time"] = None
    pl.DataFrame(rows).write_parquet(dest / "calendar.parquet")
    holiday = aggregate_board_window(
        tmp_path,
        kind="board",
        days=1,
        top=6,
        as_of_today=date(2026, 8, 31),
        as_of_now=datetime(2026, 8, 31, 10, 0, tzinfo=SHANGHAI),
    )
    assert holiday["expected_trading_day"] == "2026-08-28"
    assert holiday["freshness_status"] == "fresh"

    unknown = aggregate_board_window(
        tmp_path, kind="board", days=1, top=6, as_of_today=date(2026, 9, 7)
    )
    assert unknown["freshness_status"] == "unknown"
    assert unknown["calendar_covers"] is False
    assert unknown["expected_trading_day"] is None


def test_h5_only_uses_exact_url_and_does_not_probe_fallbacks():
    calls: list[str] = []

    class FakeClient:
        def get_json(self, url, **_kwargs):
            calls.append(url)
            return FetchResult(ok=False, error="h5 down")

    with pytest.raises(RuntimeError, match="h5 down"):
        ff.fetch_board_daily_history(
            "BK0001",
            client=FakeClient(),
            prefer_h5=True,
            h5_only=True,
            allow_local_fallback=False,
        )
    assert len(calls) == 1
    assert calls[0].startswith(f"{H5_URL}?")
    assert all("push2" not in url for url in calls)

    fallback_calls: list[str] = []

    class FallbackClient:
        def get_json(self, url, **_kwargs):
            fallback_calls.append(url)
            return FetchResult(ok=False, error="down")

    with pytest.raises(RuntimeError):
        ff.fetch_board_daily_history(
            "BK0001",
            client=FallbackClient(),
            prefer_h5=True,
            h5_only=False,
            allow_local_fallback=False,
        )
    assert len(fallback_calls) == 4
    assert fallback_calls[0].startswith(f"{H5_URL}?")
    assert any("push2his.eastmoney.com" in url for url in fallback_calls)


def test_atomic_write_keeps_old_partition_when_tmp_write_raises(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行"), _board("BK0002", "电力")])
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [
            _h5("BK0001", "银行", "2026-03-02", 1.0),
            _h5("BK0001", "银行", "2026-08-31", 7.0),
            _h5("BK0002", "电力", "2026-08-31", 8.0),
            {
                "code": "BK0002",
                "name": "电力",
                "date": "2026-08-02",
                "main_net": 4.0,
                "source": "go_stock_local_snapshot",
                "unit_amount": "yuan",
            },
        ],
        kind="board",
    )
    real_write = pl.DataFrame.write_parquet

    def boom(self, path, *args, **kwargs):
        target = Path(path)
        if ".tmp-" in target.name:
            target.write_bytes(b"CORRUPT-NOT-PARQUET")
            raise RuntimeError("write exploded mid-tmp")
        return real_write(self, path, *args, **kwargs)

    monkeypatch.setattr(pl.DataFrame, "write_parquet", boom)
    monkeypatch.setattr(
        ff,
        "fetch_board_daily_history",
        lambda code, **_k: [_h5(code, code, "2026-08-31", 99.0)],
    )
    with pytest.raises(RuntimeError, match="write exploded mid-tmp"):
        roll_industry_daily_from_h5(tmp_path, pause_s=0)
    latest = _read_daily(tmp_path, "2026-08-31")
    assert latest.filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 7.0
    assert latest.filter(pl.col("code") == "BK0002").row(0, named=True)["main_net"] == 8.0
    older = _read_daily(tmp_path, "2026-03-02")
    assert older.filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 1.0
    leftover = _read_daily(tmp_path, "2026-08-02")
    assert leftover.filter(pl.col("code") == "BK0002").row(0, named=True)["source"] == "go_stock_local_snapshot"


def test_atomic_replace_failure_keeps_old_partition(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行"), _board("BK0002", "电力")])
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [
            _h5("BK0001", "银行", "2026-03-02", 1.0),
            _h5("BK0001", "银行", "2026-08-31", 7.0),
            _h5("BK0002", "电力", "2026-08-31", 8.0),
        ],
        kind="board",
    )

    def boom_replace(_src, _dst):
        raise RuntimeError("replace exploded")

    monkeypatch.setattr("app.services.atomic_io.os.replace", boom_replace)
    monkeypatch.setattr(
        ff,
        "fetch_board_daily_history",
        lambda code, **_k: [_h5(code, code, "2026-08-31", 99.0)],
    )
    with pytest.raises(RuntimeError, match="replace exploded"):
        roll_industry_daily_from_h5(tmp_path, pause_s=0)
    latest = _read_daily(tmp_path, "2026-08-31")
    assert latest.filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 7.0
    assert latest.filter(pl.col("code") == "BK0002").row(0, named=True)["main_net"] == 8.0
    older = _read_daily(tmp_path, "2026-03-02")
    assert older.filter(pl.col("code") == "BK0001").height == 1


def test_second_run_now_does_not_redo_daily_k_while_first_is_in_flight(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行")])
    quotes = {"n": 0}
    repo = _stub_pipeline(monkeypatch, tmp_path, latest=date.today(), quotes_box=quotes)
    hold = threading.Event()
    in_fetch = threading.Event()

    def fake_fetch(code, **kwargs):
        in_fetch.set()
        hold.wait(3)
        return [_h5(code, "银行", "2026-08-31", 1.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    first_result: list[dict] = []

    def run():
        first_result.append(daily_pipeline.run_now(repo, _capset()))

    first = threading.Thread(target=run)
    first.start()
    assert in_fetch.wait(3)
    assert daily_pipeline.pipeline_in_flight() is True
    second = daily_pipeline.run_now(repo, _capset())
    assert second["status"] == "busy"
    assert second["industry_fund_flow_daily"]["status"] == "busy"
    assert quotes["n"] == 1
    hold.set()
    first.join(4)
    assert first_result[0]["quality"]["ok"] is True
    assert quotes["n"] == 1
    assert daily_pipeline.pipeline_in_flight() is False


def test_emit_done_happens_after_industry_roll(monkeypatch, tmp_path: Path):
    events: list[tuple[str, int]] = []
    seen = {}

    def roll(_data_dir, **_kwargs):
        seen["had_done"] = any(stage == "done" for stage, _pct in events)
        return {"ok": True, "status": "ok", "kind": "board"}

    quotes = {}
    repo = _stub_pipeline(monkeypatch, tmp_path, latest=date.today(), quotes_box=quotes)
    monkeypatch.setattr(ff, "roll_industry_daily_from_h5", roll)
    result = daily_pipeline.run_now(
        repo,
        _capset(),
        on_progress=lambda stage, pct, msg, **_k: events.append((stage, pct)),
    )
    assert seen["had_done"] is False
    assert events[-1][0] == "done"
    assert result["quality"]["ok"] is True
    assert result["industry_fund_flow_daily"]["ok"] is True


def test_pipeline_time_limit_stops_further_writes_and_keeps_quality(monkeypatch, tmp_path: Path):
    persist_board_snapshot(
        tmp_path,
        [_board("BK0001", "银行"), _board("BK0002", "电力"), _board("BK0003", "煤炭")],
    )
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [
            _h5("BK0001", "银行", "2026-08-31", 1.0),
            _h5("BK0002", "电力", "2026-08-31", 2.0),
            _h5("BK0003", "煤炭", "2026-08-31", 3.0),
        ],
        kind="board",
    )
    writes: list[float] = []
    real_persist = ff.persist_board_daily_history

    def wrapped_persist(*args, **kwargs):
        writes.append(time.monotonic())
        return real_persist(*args, **kwargs)

    calls: list[str] = []

    def fake_fetch(code, **kwargs):
        calls.append(code)
        time.sleep(0.12)
        return [_h5(code, code, "2026-08-31", 90.0)]

    monkeypatch.setattr(ff, "persist_board_daily_history", wrapped_persist)
    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    quotes = {}
    repo = _stub_pipeline(monkeypatch, tmp_path, latest=date.today(), quotes_box=quotes)
    events: list[str] = []
    result = daily_pipeline.run_now(
        repo,
        _capset(),
        on_progress=lambda stage, pct, msg, **_k: events.append(stage),
        industry_time_limit_s=0.05,
    )
    after = time.monotonic()
    time.sleep(0.2)
    assert result["industry_fund_flow_daily"]["status"] == "timeout"
    assert result["industry_fund_flow_daily"]["ok"] is False
    assert result["quality"]["ok"] is True
    assert events[-1] == "done"
    assert calls == ["BK0001"]
    assert writes
    assert max(writes) <= after + 0.02
    latest = _read_daily(tmp_path, "2026-08-31")
    assert latest.filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 90.0
    assert latest.filter(pl.col("code") == "BK0002").row(0, named=True)["main_net"] == 2.0
    assert latest.filter(pl.col("code") == "BK0003").row(0, named=True)["main_net"] == 3.0


def test_cancel_event_stops_before_second_code(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行"), _board("BK0002", "电力")])
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [_h5("BK0001", "银行", "2026-08-31", 1.0), _h5("BK0002", "电力", "2026-08-31", 2.0)],
        kind="board",
    )
    cancel = threading.Event()
    calls: list[str] = []

    def fake_fetch(code, **kwargs):
        calls.append(code)
        cancel.set()
        return [_h5(code, code, "2026-08-31", 11.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    result = roll_industry_daily_from_h5(
        tmp_path, pause_s=0, cancel_event=cancel, time_limit_s=30
    )
    assert result["status"] == "cancelled"
    assert calls == ["BK0001"]
    latest = _read_daily(tmp_path, "2026-08-31")
    assert latest.filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 11.0
    assert latest.filter(pl.col("code") == "BK0002").row(0, named=True)["main_net"] == 2.0


def test_stale_job_helper_does_not_fail_in_flight_worker():
    assert daily_pipeline.should_force_fail_stale_pipeline_job(
        in_flight=True, elapsed_s=900, stale_after_s=600
    ) is False
    assert daily_pipeline.should_force_fail_stale_pipeline_job(
        in_flight=False, elapsed_s=900, stale_after_s=600
    ) is True
    assert daily_pipeline.should_force_fail_stale_pipeline_job(
        in_flight=False, elapsed_s=10, stale_after_s=600
    ) is False
    assert "pipeline_in_flight()" in inspect.getsource(pipeline_api.run_now)
    assert "should_force_fail_stale_pipeline_job" in inspect.getsource(pipeline_api.run_now)
