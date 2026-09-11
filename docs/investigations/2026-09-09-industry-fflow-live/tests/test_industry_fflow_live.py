from __future__ import annotations

import inspect
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path
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
    persist_concept_snapshot,
    roll_industry_daily_from_h5,
)
from app.services.free_sources.http_resilience import FetchResult

HELPERS = Path(__file__).resolve().parent
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))
from helpers import board, capset, h5, read_daily, stub_pipeline, weekdays_ending, write_calendar

ROOT = Path("/Users/simon/Trading/one-trading")
SHANGHAI = ZoneInfo("Asia/Shanghai")
H5_URL = "https://emdatah5.eastmoney.com/dc/ZJLX/getDBHistoryData"


def test_main_tree_keeps_job_slot_and_optional_atomic():
    src = inspect.getsource(pipeline_api.run_now)
    cancel_src = inspect.getsource(pipeline_api.cancel_job)
    write_src = inspect.getsource(write_ext_parquet)
    assert "reap_stale" in src
    assert "try_acquire_run_slot" in src
    assert "pipeline_in_flight" not in src
    assert "600" not in src
    assert "request_industry_roll_cancel" in cancel_src
    assert "request_cancel(job_id)" in cancel_src
    assert "atomic: bool = False" in write_src
    assert "df.write_parquet(out_path)" in write_src
    assert "atomic_write_parquet(df, out_path)" in write_src
    roll_src = inspect.getsource(ff.roll_industry_daily_from_h5)
    assert "time_limit_s = 180.0" in roll_src
    fetch_src = inspect.getsource(ff.fetch_board_daily_history)
    assert "timeout=8.0" in fetch_src
    assert "cancel_event" not in fetch_src
    assert "Future.result" not in Path(inspect.getfile(ff)).read_text()
    assert not hasattr(daily_pipeline, "pipeline_in_flight")
    assert hasattr(daily_pipeline, "request_industry_roll_cancel")


def test_frontend_main_sources_have_industry_freshness_fields():
    api = (ROOT / "frontend/src/lib/api.ts").read_text()
    panel = (ROOT / "frontend/src/components/SectorFundFlowPanel.tsx").read_text()
    assert "freshness_status?: 'fresh' | 'stale' | 'unknown'" in api
    assert "data_as_of?: string | null" in api
    assert "industryWindowFreshnessLine" in panel
    assert "kind === 'board' && windowData" in panel
    assert "概念" in panel


def test_roll_selects_all_local_industry_codes_not_top20(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [board(f"BK{i:04d}", f"行业{i}", float(i)) for i in range(128)])
    calls: list[str] = []
    top_calls = {"n": 0}

    def fake_fetch(code, **kwargs):
        assert kwargs.get("allow_local_fallback") is False
        assert kwargs.get("prefer_h5") is True
        assert kwargs.get("h5_only") is True
        assert kwargs.get("kind") == "board"
        calls.append(code)
        return [h5(code, code, "2026-09-01", 1.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    monkeypatch.setattr(
        ff,
        "refresh_top_boards_daily_history",
        lambda *_a, **_k: top_calls.__setitem__("n", top_calls["n"] + 1),
    )
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert result["selected"] == 128
    assert len(calls) == 128
    assert set(calls) == {f"BK{i:04d}" for i in range(128)}
    assert result["latest_data_date"] == "2026-09-01"
    assert result["latest_day_complete"] is True
    assert result["ok"] is True
    assert top_calls["n"] == 0


def test_roll_new_day_moves_5_and_63_windows_and_independent_sums(monkeypatch, tmp_path: Path):
    end = date(2026, 8, 31)
    history = weekdays_ending(end, 64)
    codes = [("BK0001", "流入A"), ("BK0002", "流出B")]
    persist_board_snapshot(tmp_path, [board(code, name) for code, name in codes])
    for code, name in codes:
        sign = 1.0 if code == "BK0001" else -1.0
        persist_board_daily_history(
            tmp_path,
            code,
            [h5(code, name, day, sign * (i + 1)) for i, day in enumerate(history)],
            kind="board",
        )

    before_5 = aggregate_board_window(tmp_path, kind="board", days=5, top=6)
    before_63 = aggregate_board_window(tmp_path, kind="board", days=63, top=6)
    assert before_5["end"] == "2026-08-31"
    assert before_5["start"] == history[-5]
    assert before_63["end"] == "2026-08-31"
    assert before_63["start"] == history[-63]

    new_day = "2026-09-01"

    def fake_fetch(code, **kwargs):
        name = "流入A" if code == "BK0001" else "流出B"
        sign = 1.0 if code == "BK0001" else -1.0
        rows = [h5(code, name, day, sign * (i + 1)) for i, day in enumerate(history)]
        rows.append(h5(code, name, new_day, sign * 100.0))
        return rows[-120:]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert result["latest_data_date"] == new_day
    assert result["latest_day_complete"] is True

    after_5 = aggregate_board_window(tmp_path, kind="board", days=5, top=6)
    after_63 = aggregate_board_window(tmp_path, kind="board", days=63, top=6)
    assert after_5["end"] == new_day
    assert after_5["start"] == history[-4]
    assert after_63["end"] == new_day
    assert after_63["start"] == history[-62]
    expected_5 = {
        "BK0001": sum(1.0 * (i + 1) for i, day in enumerate(history) if day >= after_5["start"]) + 100.0,
        "BK0002": sum(-1.0 * (i + 1) for i, day in enumerate(history) if day >= after_5["start"]) - 100.0,
    }
    expected_63 = {
        "BK0001": sum(1.0 * (i + 1) for i, day in enumerate(history) if day >= after_63["start"]) + 100.0,
        "BK0002": sum(-1.0 * (i + 1) for i, day in enumerate(history) if day >= after_63["start"]) - 100.0,
    }
    got_5 = {item["code"]: item["main_net"] for item in after_5["items"]}
    got_63 = {item["code"]: item["main_net"] for item in after_63["items"]}
    assert got_5 == expected_5
    assert got_63 == expected_63
    assert [item["name"] for item in after_5["items"]][0] == "流入A"
    assert [item["name"] for item in after_5["items"]][-1] == "流出B"


def test_timeout_resume_fetches_tail_not_head(monkeypatch, tmp_path: Path):
    persist_board_snapshot(
        tmp_path,
        [board("BK0001", "头"), board("BK0002", "中"), board("BK0003", "尾")],
    )
    persist_board_daily_history(
        tmp_path,
        "x",
        [
            h5("BK0001", "头", "2026-08-31", 1.0),
            h5("BK0002", "中", "2026-08-31", 2.0),
            h5("BK0003", "尾", "2026-08-31", 3.0),
        ],
    )
    calls: list[str] = []

    def fake_fetch(code, **kwargs):
        calls.append(code)
        time.sleep(0.12)
        return [h5(code, code, "2026-09-01", 90.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    first = roll_industry_daily_from_h5(tmp_path, pause_s=0, batch_size=1, time_limit_s=0.05)
    assert first["status"] == "timeout"
    assert calls == ["BK0001"]
    assert first["ok"] is False
    assert first["latest_day_complete"] is False
    assert read_daily(tmp_path, "2026-09-01").filter(pl.col("code") == "BK0001").height == 1
    assert (tmp_path / "ext_data/ext_fund_flow_bk_daily/timeseries/date=2026-09-01").exists()

    calls.clear()
    second = roll_industry_daily_from_h5(tmp_path, pause_s=0, batch_size=1, time_limit_s=30)
    assert "BK0001" not in calls
    assert calls == ["BK0002", "BK0003"]
    assert second["latest_day_complete"] is True
    assert second["ok"] is True
    assert set(second["skipped_already_current"]) == {"BK0001"}
    day = read_daily(tmp_path, "2026-09-01")
    assert set(day["code"].to_list()) == {"BK0001", "BK0002", "BK0003"}


def test_roll_keeps_old_rows_when_upstream_fails(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [board("BK0001", "银行"), board("BK0002", "电力")])
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [h5("BK0001", "银行", "2026-08-31", 7.0), h5("BK0002", "电力", "2026-08-31", 8.0)],
    )

    def fake_fetch(code, **kwargs):
        raise RuntimeError("em down")

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert result["ok"] is False
    assert result["history_codes"] == []
    assert len(result["failed"]) == 2
    old = read_daily(tmp_path, "2026-08-31")
    assert old.filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 7.0
    assert old.filter(pl.col("code") == "BK0002").row(0, named=True)["main_net"] == 8.0


def test_roll_incomplete_batch_and_nonempty_not_complete(monkeypatch, tmp_path: Path):
    persist_board_snapshot(
        tmp_path,
        [board("BK0001", "银行"), board("BK0002", "电力"), board("BK0003", "煤炭")],
    )
    persist_board_daily_history(tmp_path, "BK0003", [h5("BK0003", "煤炭", "2026-08-31", 3.0)])

    def fake_fetch(code, **kwargs):
        if code == "BK0003":
            raise RuntimeError("timeout")
        return [h5(code, code, "2026-09-01", 11.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0, batch_size=2)
    assert result["status"] == "partial"
    assert set(result["history_codes"]) == {"BK0001", "BK0002"}
    assert result["latest_day_complete"] is False
    assert read_daily(tmp_path, "2026-08-31").filter(pl.col("code") == "BK0003").row(0, named=True)["main_net"] == 3.0

    def fake_fetch2(code, **kwargs):
        if code == "BK0103":
            return [h5(code, "C", "2026-08-31", 1.0)]
        return [h5(code, code, "2026-08-31", 1.0), h5(code, code, "2026-09-02", 2.0)]

    persist_board_snapshot(
        tmp_path,
        [board("BK0101", "A"), board("BK0102", "B"), board("BK0103", "C")],
    )
    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch2)
    second = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert second["latest_data_date"] == "2026-09-02"
    assert second["latest_day_complete"] is False
    assert second["ok"] is False
    assert second["status"] == "incomplete_latest_day"


def test_concurrent_lock_and_history_beyond_120(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [board("BK0001", "银行"), board("BK0002", "电力")])
    hold = threading.Event()
    in_fetch = threading.Event()

    def fake_fetch(code, **kwargs):
        in_fetch.set()
        hold.wait(2)
        return [h5(code, code, "2026-09-01", 4.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    results: list[dict] = []

    def run():
        results.append(roll_industry_daily_from_h5(tmp_path, pause_s=0))

    first = threading.Thread(target=run)
    second = threading.Thread(target=run)
    first.start()
    assert in_fetch.wait(2)
    second.start()
    second.join(2)
    hold.set()
    first.join(2)
    assert {item.get("status") for item in results} >= {"busy"}
    assert any(item.get("skipped_lock") for item in results)

    persist_board_snapshot(tmp_path, [board("BK0001", "银行")])
    old_days = weekdays_ending(date(2026, 8, 31), 150)
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [h5("BK0001", "银行", day, float(i)) for i, day in enumerate(old_days)],
    )
    monkeypatch.setattr(
        ff,
        "fetch_board_daily_history",
        lambda code, **_k: [h5(code, "银行", day, 100.0 + i) for i, day in enumerate(old_days[-120:])],
    )
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert result["ok"] is True
    kept = read_daily(tmp_path, old_days[0])
    assert kept.filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 0.0


def test_old_day_reply_and_leftover_outside_snapshot(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [board("BK0001", "银行"), board("BK0002", "电力")])
    persist_board_daily_history(
        tmp_path,
        "x",
        [
            h5("BK0001", "银行", "2026-08-31", 7.0),
            h5("BK0002", "电力", "2026-08-31", 8.0),
            h5("BK9999", "遗留", "2026-09-02", 9.0),
        ],
    )

    def old_reply(code, **kwargs):
        assert kwargs.get("h5_only") is True
        name = "银行" if code == "BK0001" else "电力"
        return [h5(code, name, "2026-08-28", 70.0 if code == "BK0001" else 80.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", old_reply)
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert result["latest_data_date"] == "2026-08-31"
    assert result["latest_day_complete"] is True
    assert result["ok"] is True
    assert read_daily(tmp_path, "2026-08-31").filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 7.0
    assert read_daily(tmp_path, "2026-08-28").filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 70.0
    leftover = read_daily(tmp_path, "2026-09-02")
    assert leftover.filter(pl.col("code") == "BK9999").height == 1


def test_freshness_calendar_and_concept_rules(tmp_path: Path):
    persist_board_snapshot(tmp_path, [board("BK0001", "银行")])
    persist_board_daily_history(tmp_path, "BK0001", [h5("BK0001", "银行", "2026-08-28", 1.0)])
    (tmp_path / "kline_daily" / "date=2026-09-07").mkdir(parents=True)
    unknown = aggregate_board_window(tmp_path, kind="board", days=1, top=6, as_of_today=date(2026, 9, 7))
    assert unknown["freshness_status"] == "unknown"
    assert unknown["calendar_covers"] is False
    write_calendar(tmp_path, date(2026, 8, 3), date(2026, 8, 31))
    still_unknown = aggregate_board_window(tmp_path, kind="board", days=1, top=6, as_of_today=date(2026, 9, 7))
    assert still_unknown["freshness_status"] == "unknown"

    monday_open = aggregate_board_window(
        tmp_path,
        kind="board",
        days=1,
        top=6,
        as_of_today=date(2026, 8, 31),
        as_of_now=datetime(2026, 8, 31, 10, 0, tzinfo=SHANGHAI),
    )
    assert monday_open["expected_trading_day"] == "2026-08-28"
    assert monday_open["freshness_status"] == "fresh"
    after_close = aggregate_board_window(
        tmp_path,
        kind="board",
        days=1,
        top=6,
        as_of_now=datetime(2026, 8, 31, 15, 0, tzinfo=SHANGHAI),
    )
    assert after_close["expected_trading_day"] == "2026-08-31"
    assert after_close["freshness_status"] == "stale"

    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [
            h5("BK0001", "满窗", "2026-08-24", 1.0),
            h5("BK0001", "满窗", "2026-08-25", 2.0),
            h5("BK0001", "满窗", "2026-08-26", 3.0),
            h5("BK0001", "满窗", "2026-08-27", 4.0),
            h5("BK0001", "满窗", "2026-08-28", 5.0),
            h5("BK0001", "满窗", "2026-08-31", 6.0),
        ],
    )
    week = aggregate_board_window(tmp_path, kind="board", days=5, top=6)
    assert week["start"] == "2026-08-25"
    assert week["end"] == "2026-08-31"
    assert week["items"][0]["main_net"] == 20.0

    snapshot = []
    rows = []
    for i in range(20):
        snapshot.append({"code": f"BK{i:04d}", "name": f"概念{i}", "main_net": float(i), "kind": "concept", "source": "test", "unit_amount": "yuan"})
        for day, net in (("2026-08-26", 1.0 + i), ("2026-08-27", 2.0 + i), ("2026-08-28", 3.0 + i)):
            rows.append({"code": f"BK{i:04d}", "name": f"概念{i}", "date": day, "main_net": net, "source": "eastmoney_fflow_day", "unit_amount": "yuan"})
    snapshot.append({"code": "BK9999", "name": "新主题", "main_net": 99.0, "kind": "concept", "source": "test", "unit_amount": "yuan"})
    rows.append({"code": "BK9999", "name": "新主题", "date": "2026-08-28", "main_net": 99.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"})
    persist_concept_snapshot(tmp_path, snapshot)
    persist_board_daily_history(tmp_path, "BK0000", rows, kind="concept")
    concept = aggregate_board_window(tmp_path, kind="concept", days=3, top=8)
    assert concept["window_complete"] is True
    assert concept["full_count"] == 20
    assert "新主题" not in {item["name"] for item in concept["items"]}
    assert "freshness_status" not in concept


def test_top6_heads_unchanged(tmp_path: Path):
    snapshot = []
    rows = []
    nets = [80.0, 10.0, -1.0, -2.0, -3.0, -4.0, -50.0, -60.0, -70.0]
    for i, net in enumerate(nets):
        snapshot.append(board(f"BK{i:04d}", f"板{i}", net))
        rows.append(h5(f"BK{i:04d}", f"板{i}", "2026-08-21", net))
    persist_board_snapshot(tmp_path, snapshot)
    persist_board_daily_history(tmp_path, "BK0000", rows, kind="board")
    result = aggregate_board_window(tmp_path, kind="board", days=1, top=4)
    names = [item["name"] for item in result["items"]]
    assert names[:4] == ["板0", "板1", "板2", "板3"]
    assert names[4:] == ["板8", "板7", "板6", "板5"]


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

    fallback: list[str] = []

    class FallbackClient:
        def get_json(self, url, **_kwargs):
            fallback.append(url)
            return FetchResult(ok=False, error="down")

    with pytest.raises(RuntimeError):
        ff.fetch_board_daily_history(
            "BK0001",
            client=FallbackClient(),
            prefer_h5=True,
            h5_only=False,
            allow_local_fallback=False,
        )
    assert len(fallback) == 4
    assert any("push2his.eastmoney.com" in url for url in fallback)


def test_atomic_tmp_and_replace_failures_keep_history(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [board("BK0001", "银行"), board("BK0002", "电力")])
    persist_board_daily_history(
        tmp_path,
        "x",
        [
            h5("BK0001", "银行", "2026-03-02", 1.0),
            h5("BK0001", "银行", "2026-08-31", 7.0),
            h5("BK0002", "电力", "2026-08-31", 8.0),
            {
                "code": "BK0002",
                "name": "电力",
                "date": "2026-08-02",
                "main_net": 4.0,
                "source": "go_stock_local_snapshot",
                "unit_amount": "yuan",
            },
        ],
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
        lambda code, **_k: [h5(code, code, "2026-08-31", 99.0)],
    )
    with pytest.raises(RuntimeError, match="write exploded mid-tmp"):
        roll_industry_daily_from_h5(tmp_path, pause_s=0)
    latest = read_daily(tmp_path, "2026-08-31")
    assert latest.filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 7.0
    assert read_daily(tmp_path, "2026-03-02").filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 1.0
    assert read_daily(tmp_path, "2026-08-02").filter(pl.col("code") == "BK0002").row(0, named=True)["source"] == "go_stock_local_snapshot"

    monkeypatch.setattr(pl.DataFrame, "write_parquet", real_write)
    persist_board_daily_history(
        tmp_path,
        "x",
        [h5("BK0001", "银行", "2026-08-31", 7.0), h5("BK0002", "电力", "2026-08-31", 8.0)],
    )
    monkeypatch.setattr("app.services.atomic_io.os.replace", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("replace exploded")))
    monkeypatch.setattr(ff, "fetch_board_daily_history", lambda code, **_k: [h5(code, code, "2026-08-31", 99.0)])
    with pytest.raises(RuntimeError, match="replace exploded"):
        roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert read_daily(tmp_path, "2026-08-31").filter(pl.col("code") == "BK0001").row(0, named=True)["main_net"] == 7.0


def test_done_after_roll_timeout_cancel_and_quality_isolation(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [board("BK0001", "银行"), board("BK0002", "电力"), board("BK0003", "煤炭")])
    persist_board_daily_history(
        tmp_path,
        "x",
        [
            h5("BK0001", "银行", "2026-08-31", 1.0),
            h5("BK0002", "电力", "2026-08-31", 2.0),
            h5("BK0003", "煤炭", "2026-08-31", 3.0),
        ],
    )
    events: list[str] = []
    calls: list[str] = []

    def fake_fetch(code, **kwargs):
        calls.append(code)
        time.sleep(0.12)
        return [h5(code, code, "2026-08-31", 90.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    repo, quotes = stub_pipeline(monkeypatch, tmp_path, latest=date.today(), quotes_box={})
    result = daily_pipeline.run_now(
        repo,
        capset(),
        on_progress=lambda stage, pct, msg, **_k: events.append(stage),
        industry_time_limit_s=0.05,
    )
    assert events[-1] == "done"
    assert result["quality"]["ok"] is True
    assert result["industry_fund_flow_daily"]["status"] == "timeout"
    assert result["industry_fund_flow_daily"]["ok"] is False
    assert calls == ["BK0001"]
    assert read_daily(tmp_path, "2026-08-31").filter(pl.col("code") == "BK0002").row(0, named=True)["main_net"] == 2.0
    assert quotes["n"] == 1

    cancel = threading.Event()
    calls.clear()

    def cancel_fetch(code, **kwargs):
        calls.append(code)
        cancel.set()
        return [h5(code, code, "2026-08-31", 11.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", cancel_fetch)
    cancelled = roll_industry_daily_from_h5(tmp_path, pause_s=0, cancel_event=cancel, time_limit_s=30)
    assert cancelled["status"] == "cancelled"
    assert calls == ["BK0001"]

    def boom(_data_dir, **_kwargs):
        raise RuntimeError("industry roll exploded")

    monkeypatch.setattr(ff, "roll_industry_daily_from_h5", boom)
    failed = daily_pipeline.run_now(repo, capset())
    assert failed["quality"]["ok"] is True
    assert failed["industry_fund_flow_daily"]["status"] == "error"
    assert "不影响已成功日K" in failed["industry_fund_flow_daily"]["note"]
