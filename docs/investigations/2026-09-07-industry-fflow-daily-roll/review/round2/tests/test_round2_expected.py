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
H5 = "https://emdatah5.eastmoney.com/dc/ZJLX/getDBHistoryData"


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
        "as_of": "2026-08-31",
        "kind": "board",
        "source": "eastmoney_bkzj",
        "unit_amount": "yuan",
    }


def _write_calendar(tmp_path: Path, start: date, end: date) -> None:
    from app.data_lab.fixtures import make_trading_calendar_frame

    dest = tmp_path / "reference" / "trading_calendar"
    dest.mkdir(parents=True, exist_ok=True)
    make_trading_calendar_frame(start=start, days=(end - start).days + 1, as_of=end).write_parquet(
        dest / "calendar.parquet"
    )


def _read(tmp_path: Path, day: str) -> pl.DataFrame:
    return pl.read_parquet(
        tmp_path / "ext_data/ext_fund_flow_bk_daily/timeseries" / f"date={day}" / "part.parquet"
    )


def _capset() -> CapabilitySet:
    return CapabilitySet({
        Cap.KLINE_DAILY_BATCH: CapabilityLimits(),
        Cap.QUOTE_POOL: CapabilityLimits(),
        Cap.ADJ_FACTOR: CapabilityLimits(),
    })


def _stub(monkeypatch, tmp_path: Path, quotes: dict):
    inst = SimpleNamespace(
        ok=True, rows_published=3, prior_rows=3, error_code=None, error_message=None,
        failed_exchanges=(), as_dict=lambda: {"outcome": "published"},
    )
    monkeypatch.setattr(daily_pipeline.instrument_sync, "sync_instruments_result", lambda _d: inst)
    monkeypatch.setattr(daily_pipeline, "resolve_universe", lambda _c: ["000001.SZ"])
    monkeypatch.setattr(daily_pipeline, "_refresh_instruments_view", lambda _r: None)
    monkeypatch.setattr(daily_pipeline, "_refresh_single_view", lambda *_a, **_k: None)
    monkeypatch.setattr(daily_pipeline, "_refresh_views", lambda _r: None)
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
    monkeypatch.setattr(daily_pipeline.kline_sync, "sync_daily_by_quotes", lambda _r: quotes.__setitem__("n", quotes.get("n", 0) + 1) or 99)
    monkeypatch.setattr(daily_pipeline.kline_sync, "sync_adj_factor", lambda *a, **k: (0, []))
    monkeypatch.setattr(daily_pipeline.index_sync, "sync_index_instruments", lambda *a, **k: 1)
    monkeypatch.setattr(daily_pipeline.index_sync, "sync_and_persist_index_daily", lambda *a, **k: 4)
    monkeypatch.setattr(daily_pipeline.index_sync, "sync_etf_instruments", lambda *a, **k: 0)
    monkeypatch.setattr(daily_pipeline.index_sync, "sync_and_persist_etf_daily", lambda *a, **k: 0)
    return SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        latest_daily_date=lambda: date.today(),
        get_etf_instruments=lambda: type("E", (), {"is_empty": lambda self: True})(),
        refresh_index_views=lambda: None,
    )


def test_round2_loads_six_overlay_modules_not_main_tree():
    assert Path(inspect.getfile(ff)).resolve() == TASK / "overlay/backend/app/services/free_sources/fund_flow.py"
    assert Path(inspect.getfile(daily_pipeline)).resolve() == TASK / "overlay/backend/app/jobs/daily_pipeline.py"
    assert Path(inspect.getfile(write_ext_parquet)).resolve() == TASK / "overlay/backend/app/services/ext_data.py"
    assert Path(inspect.getfile(pipeline_api)).resolve() == TASK / "overlay/backend/app/api/pipeline.py"
    overlay_api = (TASK / "overlay/frontend/src/lib/api.ts").read_text()
    assert "INDUSTRY_FFLOW_WINDOW_CONTRACT" not in overlay_api
    assert "freshness_status?: 'fresh' | 'stale' | 'unknown'" in overlay_api
    fetch_src = inspect.getsource(ff.fetch_board_daily_history)
    assert "timeout=8.0" in fetch_src
    assert "h5_only" in fetch_src


def test_leftover_outside_snapshot_and_old_day_reply(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行"), _board("BK0002", "电力")])
    persist_board_daily_history(
        tmp_path,
        "x",
        [
            _h5("BK0001", "银行", "2026-08-31", 7.0),
            _h5("BK0002", "电力", "2026-08-31", 8.0),
            _h5("BK9999", "遗留", "2026-09-02", 9.0),
        ],
    )

    def fake_fetch(code, **kwargs):
        assert kwargs.get("h5_only") is True
        assert kwargs.get("allow_local_fallback") is False
        return [_h5(code, code, "2026-08-28", 70.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert result["ok"] is True
    assert result["latest_data_date"] == "2026-08-31"
    assert result["latest_day_complete"] is True
    assert _read(tmp_path, "2026-08-31").filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 7.0
    assert _read(tmp_path, "2026-08-28").filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 70.0
    assert _read(tmp_path, "2026-09-02").filter(pl.col("code") == "BK9999").height == 1


def test_shanghai_intraday_close_rest_unknown(tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行")])
    persist_board_daily_history(tmp_path, "x", [_h5("BK0001", "银行", "2026-08-28", 1.0)])
    _write_calendar(tmp_path, date(2026, 8, 3), date(2026, 8, 31))
    open_ = aggregate_board_window(
        tmp_path, kind="board", days=1, top=6,
        as_of_now=datetime(2026, 8, 31, 10, 0, tzinfo=SHANGHAI),
    )
    assert open_["expected_trading_day"] == "2026-08-28"
    assert open_["freshness_status"] == "fresh"
    close = aggregate_board_window(
        tmp_path, kind="board", days=1, top=6,
        as_of_now=datetime(2026, 8, 31, 15, 0, tzinfo=SHANGHAI),
    )
    assert close["expected_trading_day"] == "2026-08-31"
    assert close["freshness_status"] == "stale"
    sat = aggregate_board_window(
        tmp_path, kind="board", days=1, top=6,
        as_of_now=datetime(2026, 8, 29, 10, 30, tzinfo=SHANGHAI),
    )
    assert sat["expected_trading_day"] == "2026-08-28"
    assert sat["freshness_status"] == "fresh"
    unknown = aggregate_board_window(tmp_path, kind="board", days=1, top=6, as_of_today=date(2026, 9, 7))
    assert unknown["freshness_status"] == "unknown"
    assert unknown["calendar_covers"] is False


def test_h5_only_one_url_no_fallback():
    calls: list[str] = []

    class Client:
        def get_json(self, url, **kwargs):
            calls.append(url)
            assert kwargs.get("timeout") == 8.0
            return FetchResult(ok=False, error="h5 down")

    with pytest.raises(RuntimeError, match="h5 down"):
        ff.fetch_board_daily_history(
            "BK0001", client=Client(), prefer_h5=True, h5_only=True, allow_local_fallback=False,
        )
    assert len(calls) == 1
    assert calls[0].startswith(f"{H5}?")
    assert "push2" not in calls[0]


def test_atomic_tmp_and_replace_failures_keep_history(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行"), _board("BK0002", "电力")])
    persist_board_daily_history(
        tmp_path,
        "x",
        [
            _h5("BK0001", "银行", "2026-03-02", 1.0),
            _h5("BK0001", "银行", "2026-08-31", 7.0),
            _h5("BK0002", "电力", "2026-08-31", 8.0),
            {
                "code": "BK0002", "name": "电力", "date": "2026-08-02",
                "main_net": 4.0, "source": "go_stock_local_snapshot", "unit_amount": "yuan",
            },
        ],
    )
    real = pl.DataFrame.write_parquet

    def boom(self, path, *args, **kwargs):
        target = Path(path)
        if ".tmp-" in target.name:
            target.write_bytes(b"CORRUPT-NOT-PARQUET")
            raise RuntimeError("tmp write failed")
        return real(self, path, *args, **kwargs)

    monkeypatch.setattr(pl.DataFrame, "write_parquet", boom)
    monkeypatch.setattr(ff, "fetch_board_daily_history", lambda code, **_k: [_h5(code, code, "2026-08-31", 99.0)])
    with pytest.raises(RuntimeError, match="tmp write failed"):
        roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert _read(tmp_path, "2026-08-31").filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 7.0
    assert _read(tmp_path, "2026-03-02").filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 1.0
    assert _read(tmp_path, "2026-08-02").filter(pl.col("code") == "BK0002").row(0, named=True)["source"] == "go_stock_local_snapshot"

    monkeypatch.undo()
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行"), _board("BK0002", "电力")])
    persist_board_daily_history(
        tmp_path, "x",
        [_h5("BK0001", "银行", "2026-08-31", 7.0), _h5("BK0002", "电力", "2026-08-31", 8.0)],
    )
    monkeypatch.setattr("app.services.atomic_io.os.replace", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("replace failed")))
    monkeypatch.setattr(ff, "fetch_board_daily_history", lambda code, **_k: [_h5(code, code, "2026-08-31", 99.0)])
    with pytest.raises(RuntimeError, match="replace failed"):
        roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert _read(tmp_path, "2026-08-31").filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 7.0


def test_second_run_now_and_cancel_route_do_not_redo_daily_k(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行")])
    quotes = {"n": 0}
    repo = _stub(monkeypatch, tmp_path, quotes)
    hold = threading.Event()
    in_fetch = threading.Event()

    def fake_fetch(code, **kwargs):
        in_fetch.set()
        hold.wait(3)
        return [_h5(code, "银行", "2026-08-31", 1.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    first_box: list[dict] = []
    first = threading.Thread(target=lambda: first_box.append(daily_pipeline.run_now(repo, _capset())))
    first.start()
    assert in_fetch.wait(3)
    assert daily_pipeline.pipeline_in_flight() is True
    assert daily_pipeline.should_force_fail_stale_pipeline_job(in_flight=True, elapsed_s=900) is False
    second = daily_pipeline.run_now(repo, _capset())
    assert second["status"] == "busy"
    assert quotes["n"] == 1
    daily_pipeline.request_pipeline_cancel()
    assert inspect.getsource(pipeline_api.cancel_job).count("request_pipeline_cancel") == 1
    hold.set()
    first.join(4)
    assert first_box[0]["quality"]["ok"] is True
    assert quotes["n"] == 1
    assert daily_pipeline.pipeline_in_flight() is False
    third = daily_pipeline.run_now(repo, _capset(), industry_time_limit_s=1)
    assert third.get("status") != "busy" or quotes["n"] >= 1
    assert quotes["n"] == 2


def test_done_after_roll_and_cooperative_deadline(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "A"), _board("BK0002", "B"), _board("BK0003", "C")])
    persist_board_daily_history(
        tmp_path, "x",
        [_h5("BK0001", "A", "2026-08-31", 1.0), _h5("BK0002", "B", "2026-08-31", 2.0), _h5("BK0003", "C", "2026-08-31", 3.0)],
    )
    events: list[str] = []
    calls: list[str] = []
    timeouts: list[float] = []

    def fake_fetch(code, **kwargs):
        calls.append(code)
        timeouts.append(8.0)
        time.sleep(0.12)
        return [_h5(code, code, "2026-08-31", 90.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    quotes = {}
    repo = _stub(monkeypatch, tmp_path, quotes)
    result = daily_pipeline.run_now(
        repo, _capset(),
        on_progress=lambda stage, pct, msg, **_k: events.append(stage),
        industry_time_limit_s=0.05,
    )
    assert events[-1] == "done"
    assert result["quality"]["ok"] is True
    assert result["industry_fund_flow_daily"]["status"] == "timeout"
    assert calls == ["BK0001"]
    assert timeouts == [8.0]
    assert _read(tmp_path, "2026-08-31").filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 90.0
    assert _read(tmp_path, "2026-08-31").filter(pl.col("code") == "BK0002").row(0, named=True)["main_net"] == 2.0
    roll_src = (TASK / "overlay/backend/app/services/free_sources/fund_flow.py").read_text()
    assert "time_limit_s = 180.0" in roll_src
    assert "Future.result" not in roll_src
    fetch_block = roll_src.split("def fetch_board_daily_history")[1].split("def _ensure_stock_ff_config")[0]
    assert "timeout=8.0" in fetch_block
    assert "cancel_event" not in fetch_block


def test_cancel_stops_next_code_and_exception_releases_lock(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "A"), _board("BK0002", "B")])
    persist_board_daily_history(
        tmp_path, "x",
        [_h5("BK0001", "A", "2026-08-31", 1.0), _h5("BK0002", "B", "2026-08-31", 2.0)],
    )
    cancel = threading.Event()
    calls: list[str] = []

    def fake_fetch(code, **kwargs):
        calls.append(code)
        cancel.set()
        return [_h5(code, code, "2026-08-31", 11.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0, cancel_event=cancel, time_limit_s=30)
    assert result["status"] == "cancelled"
    assert calls == ["BK0001"]
    assert _read(tmp_path, "2026-08-31").filter(pl.col("code") == "BK0002").row(0, named=True)["main_net"] == 2.0

    real_persist = ff.persist_board_daily_history

    def boom(*_a, **_k):
        raise RuntimeError("persist exploded")

    monkeypatch.setattr(ff, "persist_board_daily_history", boom)
    with pytest.raises(RuntimeError, match="persist exploded"):
        roll_industry_daily_from_h5(tmp_path, pause_s=0, time_limit_s=5)
    monkeypatch.setattr(ff, "persist_board_daily_history", real_persist)
    again = roll_industry_daily_from_h5(tmp_path, pause_s=0, time_limit_s=5)
    assert again.get("status") != "busy"
