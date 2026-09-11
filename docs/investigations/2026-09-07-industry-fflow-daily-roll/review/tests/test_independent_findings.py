from __future__ import annotations

import inspect
import threading
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl

from app.jobs import daily_pipeline
from app.services.ext_data import write_ext_parquet
from app.services.free_sources import fund_flow as ff
from app.services.free_sources.fund_flow import (
    aggregate_board_window,
    persist_board_daily_history,
    persist_board_snapshot,
    roll_industry_daily_from_h5,
)
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet


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
    repo = SimpleNamespace(
        store=SimpleNamespace(data_dir=tmp_path),
        latest_daily_date=lambda: latest,
        get_etf_instruments=lambda: type("Empty", (), {"is_empty": lambda self: True})(),
        refresh_index_views=lambda: None,
    )
    return repo


def test_review_loads_overlay_not_main_tree():
    ff_path = Path(inspect.getfile(ff)).resolve()
    dp_path = Path(inspect.getfile(daily_pipeline)).resolve()
    assert ff_path == Path(
        "/Users/simon/Trading/one-trading/docs/investigations/2026-09-07-industry-fflow-daily-roll"
        "/overlay/backend/app/services/free_sources/fund_flow.py"
    )
    assert dp_path == Path(
        "/Users/simon/Trading/one-trading/docs/investigations/2026-09-07-industry-fflow-daily-roll"
        "/overlay/backend/app/jobs/daily_pipeline.py"
    )
    main_ff = Path("/Users/simon/Trading/one-trading/backend/app/services/free_sources/fund_flow.py")
    assert "def roll_industry_daily_from_h5" not in main_ff.read_text()


def test_old_day_h5_reply_keeps_local_latest_and_is_complete(monkeypatch, tmp_path: Path):
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
        assert kwargs.get("allow_local_fallback") is False
        name = "银行" if code == "BK0001" else "电力"
        return [_h5(code, name, "2026-08-31", 70.0 if code == "BK0001" else 80.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert result["ok"] is True
    assert result["latest_data_date"] == "2026-08-31"
    assert result["latest_day_complete"] is True
    day = _read_daily(tmp_path, "2026-08-31")
    assert day.filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 70.0
    assert (tmp_path / "ext_data/ext_fund_flow_bk_daily/timeseries/date=2026-09-01").exists() is False


def test_leftover_newer_date_on_non_snapshot_code_poisons_latest_complete(monkeypatch, tmp_path: Path):
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
    assert result["latest_data_date"] == "2026-09-02"
    assert result["latest_day_complete"] is False
    assert result["ok"] is False
    assert result["status"] == "incomplete_latest_day"


def test_weekend_uses_last_open_day_as_fresh(tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行")])
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [_h5("BK0001", "银行", "2026-08-28", 1.0)],
        kind="board",
    )
    _write_calendar(tmp_path, date(2026, 8, 3), date(2026, 8, 30))
    sat = aggregate_board_window(
        tmp_path, kind="board", days=1, top=6, as_of_today=date(2026, 8, 29)
    )
    assert sat["calendar_covers"] is True
    assert sat["expected_trading_day"] == "2026-08-28"
    assert sat["freshness_status"] == "fresh"
    assert sat["window_complete"] is True


def test_intraday_trading_day_marks_yesterday_complete_as_stale(tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行")])
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [_h5("BK0001", "银行", "2026-08-28", 1.0)],
        kind="board",
    )
    _write_calendar(tmp_path, date(2026, 8, 3), date(2026, 8, 31))
    monday = aggregate_board_window(
        tmp_path, kind="board", days=1, top=6, as_of_today=date(2026, 8, 31)
    )
    assert monday["expected_trading_day"] == "2026-08-31"
    assert monday["window_complete"] is True
    assert monday["freshness_status"] == "stale"
    assert monday["freshness_note"] == "已陈旧"


def test_holiday_weekday_uses_previous_open_day(tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行")])
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [_h5("BK0001", "银行", "2026-08-28", 1.0)],
        kind="board",
    )
    from app.data_lab.fixtures import make_trading_calendar_frame

    dest = tmp_path / "reference" / "trading_calendar"
    dest.mkdir(parents=True, exist_ok=True)
    frame = make_trading_calendar_frame(start=date(2026, 8, 24), days=8, as_of=date(2026, 8, 31))
    rows = frame.to_dicts()
    for row in rows:
        if str(row["trade_date"])[:10] == "2026-08-31":
            row["is_open"] = False
            row["session_type"] = "holiday"
    pl.DataFrame(rows).write_parquet(dest / "calendar.parquet")
    holiday = aggregate_board_window(
        tmp_path, kind="board", days=1, top=6, as_of_today=date(2026, 8, 31)
    )
    assert holiday["calendar_covers"] is True
    assert holiday["expected_trading_day"] == "2026-08-28"
    assert holiday["freshness_status"] == "fresh"


def test_write_ext_parquet_is_not_atomic():
    source = inspect.getsource(write_ext_parquet)
    assert "atomic_write_parquet" not in source
    assert "df.write_parquet(out_path)" in source


def test_emit_done_happens_before_industry_roll(monkeypatch, tmp_path: Path):
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
    assert seen["had_done"] is True
    assert events[-2][0] == "done" or any(stage == "done" for stage, _ in events)
    assert result["quality"]["ok"] is True
    assert result["industry_fund_flow_daily"]["ok"] is True


def test_second_run_now_redoes_daily_k_while_first_roll_holds_lock(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行")])
    quotes = {"n": 0}
    repo = _stub_pipeline(monkeypatch, tmp_path, latest=date.today(), quotes_box=quotes)
    hold = threading.Event()
    in_fetch = threading.Event()

    def fake_fetch(code, **kwargs):
        in_fetch.set()
        hold.wait(3)
        return [_h5(code, "银行", "2026-09-01", 1.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    results: list[dict] = []

    def run():
        results.append(daily_pipeline.run_now(repo, _capset()))

    first = threading.Thread(target=run)
    second = threading.Thread(target=run)
    first.start()
    assert in_fetch.wait(3)
    second.start()
    second.join(4)
    hold.set()
    first.join(4)
    assert len(results) == 2
    assert quotes["n"] == 2
    statuses = {item["industry_fund_flow_daily"].get("status") for item in results}
    assert "busy" in statuses
    assert any(item["quality"]["ok"] is True for item in results)


def test_go_stock_leftover_not_counted_as_latest_h5_coverage(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行"), _board("BK0002", "电力")])
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [_h5("BK0001", "银行", "2026-08-31", 1.0)],
        kind="board",
    )
    persist_board_daily_history(
        tmp_path,
        "BK0002",
        [{
            "code": "BK0002",
            "name": "电力",
            "date": "2026-09-01",
            "main_net": 9.0,
            "source": "go_stock_local_snapshot",
            "unit_amount": "yuan",
        }],
        kind="board",
    )

    def fake_fetch(code, **kwargs):
        return [_h5(code, code, "2026-08-31", 2.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert result["latest_data_date"] == "2026-08-31"
    assert result["latest_day_complete"] is True
    leftover = _read_daily(tmp_path, "2026-09-01")
    assert leftover.filter(pl.col("code") == "BK0002").height == 1


def test_pipeline_partial_roll_does_not_rewrite_daily_days(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行")])
    quotes = {}
    repo = _stub_pipeline(monkeypatch, tmp_path, latest=date.today(), quotes_box=quotes)

    def partial(_data_dir, **_kwargs):
        return {
            "ok": False,
            "status": "partial",
            "latest_day_complete": False,
            "kind": "board",
        }

    monkeypatch.setattr(ff, "roll_industry_daily_from_h5", partial)
    result = daily_pipeline.run_now(repo, _capset())
    assert result["quality"]["ok"] is True
    assert "daily_days" in result
    assert result["industry_fund_flow_daily"]["ok"] is False
    assert result["industry_fund_flow_daily"]["status"] == "partial"
