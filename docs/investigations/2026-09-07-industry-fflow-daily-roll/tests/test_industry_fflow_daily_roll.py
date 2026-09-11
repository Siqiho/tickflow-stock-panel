from __future__ import annotations

import threading
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl

from app.jobs import daily_pipeline
from app.services.free_sources import fund_flow as ff
from app.services.free_sources.fund_flow import (
    aggregate_board_window,
    persist_board_daily_history,
    persist_board_snapshot,
    persist_concept_snapshot,
    roll_industry_daily_from_h5,
)
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet


def _weekdays_ending(end: date, n: int) -> list[str]:
    days: list[str] = []
    current = end
    while len(days) < n:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current -= timedelta(days=1)
    return list(reversed(days))


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
    frame = make_trading_calendar_frame(
        start=start,
        days=(end - start).days + 1,
        as_of=end,
    )
    frame.write_parquet(dest / "calendar.parquet")


def _read_daily(tmp_path: Path, day: str) -> pl.DataFrame:
    return pl.read_parquet(
        tmp_path / "ext_data" / "ext_fund_flow_bk_daily" / "timeseries" / f"date={day}" / "part.parquet"
    )


def test_roll_selects_all_local_industry_codes_not_top20(monkeypatch, tmp_path: Path):
    snapshot = [_board(f"BK{i:04d}", f"行业{i}", float(i)) for i in range(128)]
    persist_board_snapshot(tmp_path, snapshot)
    calls: list[str] = []
    top_calls = {"n": 0}

    def fake_fetch(code, **kwargs):
        assert kwargs.get("allow_local_fallback") is False
        assert kwargs.get("prefer_h5") is True
        assert kwargs.get("kind") == "board"
        calls.append(code)
        return [_h5(code, code, "2026-09-01", 1.0)]

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
    history = _weekdays_ending(end, 64)
    codes = [("BK0001", "流入A"), ("BK0002", "流出B")]
    persist_board_snapshot(tmp_path, [_board(code, name) for code, name in codes])
    for code, name in codes:
        sign = 1.0 if code == "BK0001" else -1.0
        persist_board_daily_history(
            tmp_path,
            code,
            [_h5(code, name, day, sign * (i + 1)) for i, day in enumerate(history)],
            kind="board",
        )

    before_5 = aggregate_board_window(tmp_path, kind="board", days=5, top=6)
    before_63 = aggregate_board_window(tmp_path, kind="board", days=63, top=6)
    assert before_5["end"] == "2026-08-31"
    assert before_5["start"] == history[-5]
    assert before_63["end"] == "2026-08-31"
    assert before_63["start"] == history[-63]
    assert before_5["window_complete"] is True
    assert before_63["window_complete"] is True

    new_day = "2026-09-01"

    def fake_fetch(code, **kwargs):
        name = "流入A" if code == "BK0001" else "流出B"
        sign = 1.0 if code == "BK0001" else -1.0
        rows = [_h5(code, name, day, sign * (i + 1)) for i, day in enumerate(history)]
        rows.append(_h5(code, name, new_day, sign * 100.0))
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
    assert after_5["window_complete"] is True
    assert after_63["window_complete"] is True

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
    assert got_5["BK0001"] == expected_5["BK0001"]
    assert got_5["BK0002"] == expected_5["BK0002"]
    assert got_63["BK0001"] == expected_63["BK0001"]
    assert got_63["BK0002"] == expected_63["BK0002"]
    names_5 = [item["name"] for item in after_5["items"]]
    assert names_5[0] == "流入A"
    assert names_5[-1] == "流出B"


def test_roll_keeps_old_rows_when_upstream_fails(monkeypatch, tmp_path: Path):
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
        raise RuntimeError("em down")

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert result["ok"] is False
    assert result["history_codes"] == []
    assert len(result["failed"]) == 2
    old = _read_daily(tmp_path, "2026-08-31")
    bank = old.filter(pl.col("code") == "BK0001").row(0, named=True)
    power = old.filter(pl.col("code") == "BK0002").row(0, named=True)
    assert bank["main_net"] == 7.0
    assert power["main_net"] == 8.0
    assert bank["source"] == "eastmoney_fflow_day"


def test_roll_incomplete_batch_persists_successes_only(monkeypatch, tmp_path: Path):
    persist_board_snapshot(
        tmp_path,
        [_board("BK0001", "银行"), _board("BK0002", "电力"), _board("BK0003", "煤炭")],
    )
    persist_board_daily_history(
        tmp_path,
        "BK0003",
        [_h5("BK0003", "煤炭", "2026-08-31", 3.0)],
        kind="board",
    )

    def fake_fetch(code, **kwargs):
        if code == "BK0003":
            raise RuntimeError("timeout")
        return [_h5(code, code, "2026-09-01", 11.0)]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0, batch_size=2)
    assert result["ok"] is False
    assert result["status"] == "partial"
    assert set(result["history_codes"]) == {"BK0001", "BK0002"}
    assert result["failed"][0]["code"] == "BK0003"
    assert result["latest_data_date"] == "2026-09-01"
    assert result["latest_day_complete"] is False
    new = _read_daily(tmp_path, "2026-09-01")
    assert set(new["code"].to_list()) == {"BK0001", "BK0002"}
    old = _read_daily(tmp_path, "2026-08-31")
    coal = old.filter(pl.col("code") == "BK0003").row(0, named=True)
    assert coal["main_net"] == 3.0


def test_roll_does_not_treat_nonempty_as_latest_day_complete(monkeypatch, tmp_path: Path):
    persist_board_snapshot(
        tmp_path,
        [_board("BK0001", "银行"), _board("BK0002", "电力"), _board("BK0003", "煤炭")],
    )

    def fake_fetch(code, **kwargs):
        if code == "BK0003":
            return [_h5(code, "煤炭", "2026-08-31", 1.0)]
        return [
            _h5(code, code, "2026-08-31", 1.0),
            _h5(code, code, "2026-09-01", 2.0),
        ]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert result["history_codes"] == ["BK0001", "BK0002", "BK0003"]
    assert result["failed"] == []
    assert result["latest_data_date"] == "2026-09-01"
    assert result["latest_day_complete"] is False
    assert result["ok"] is False
    assert result["status"] == "incomplete_latest_day"


def test_roll_is_idempotent_and_blocks_concurrent_rerun(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行"), _board("BK0002", "电力")])
    calls = {"n": 0}
    hold = threading.Event()
    in_fetch = threading.Event()

    def fake_fetch(code, **kwargs):
        calls["n"] += 1
        in_fetch.set()
        hold.wait(2)
        return [_h5(code, code, "2026-09-01", 4.0)]

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
    assert len(results) == 2
    statuses = {item.get("status") for item in results}
    assert "busy" in statuses
    assert any(item.get("skipped_lock") for item in results)
    assert any(item.get("latest_day_complete") for item in results)

    calls["n"] = 0
    hold.set()
    first_pass = [item for item in results if item.get("status") != "busy"][0]
    second_pass = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert second_pass["latest_data_date"] == first_pass["latest_data_date"]
    assert second_pass["latest_day_complete"] is True
    day = _read_daily(tmp_path, "2026-09-01")
    assert day.height == 2
    assert set(day["code"].to_list()) == {"BK0001", "BK0002"}
    assert day["main_net"].to_list() == [4.0, 4.0]


def test_roll_keeps_history_beyond_h5_120_window(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行")])
    old_days = _weekdays_ending(date(2026, 8, 31), 150)
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [_h5("BK0001", "银行", day, float(i)) for i, day in enumerate(old_days)],
        kind="board",
    )
    oldest = old_days[0]
    newest_local = old_days[-1]

    def fake_fetch(code, **kwargs):
        return [_h5(code, "银行", day, 100.0 + i) for i, day in enumerate(old_days[-120:])]

    monkeypatch.setattr(ff, "fetch_board_daily_history", fake_fetch)
    result = roll_industry_daily_from_h5(tmp_path, pause_s=0)
    assert result["ok"] is True
    kept = _read_daily(tmp_path, oldest)
    assert kept.filter(pl.col("code") == "BK0001").height == 1
    assert kept.row(0, named=True)["main_net"] == 0.0
    latest = _read_daily(tmp_path, newest_local)
    assert latest.row(0, named=True)["main_net"] == 100.0 + 119


def test_industry_freshness_stale_unknown_and_not_kline(tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "银行")])
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [_h5("BK0001", "银行", "2026-08-31", 1.0)],
        kind="board",
    )
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
    assert stale["window_complete"] is True
    assert stale["freshness_status"] == "stale"
    assert stale["calendar_covers"] is True
    assert stale["expected_trading_day"] == "2026-09-07"
    assert stale["freshness_note"] == "已陈旧"

    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [_h5("BK0001", "银行", "2026-09-07", 2.0)],
        kind="board",
    )
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


def test_concept_window_rules_unchanged(tmp_path: Path):
    snapshot = []
    rows = []
    for i in range(20):
        code = f"BK{i:04d}"
        snapshot.append(
            {
                "code": code,
                "name": f"概念{i}",
                "main_net": float(i),
                "kind": "concept",
                "source": "test",
                "unit_amount": "yuan",
            }
        )
        for day, net in (("2026-08-26", 1.0 + i), ("2026-08-27", 2.0 + i), ("2026-08-28", 3.0 + i)):
            rows.append(
                {
                    "code": code,
                    "name": f"概念{i}",
                    "date": day,
                    "main_net": net,
                    "source": "eastmoney_fflow_day",
                    "unit_amount": "yuan",
                }
            )
    snapshot.append(
        {
            "code": "BK9999",
            "name": "新主题",
            "main_net": 99.0,
            "kind": "concept",
            "source": "test",
            "unit_amount": "yuan",
        }
    )
    rows.append(
        {
            "code": "BK9999",
            "name": "新主题",
            "date": "2026-08-28",
            "main_net": 99.0,
            "source": "eastmoney_fflow_day",
            "unit_amount": "yuan",
        }
    )
    persist_concept_snapshot(tmp_path, snapshot)
    persist_board_daily_history(tmp_path, "BK0000", rows, kind="concept")
    result = aggregate_board_window(tmp_path, kind="concept", days=3, top=8)
    assert result["window_complete"] is True
    assert result["full_count"] == 20
    assert result["snapshot_count"] == 21
    names = {item["name"] for item in result["items"]}
    assert "新主题" not in names
    assert "概念19" in names
    assert "freshness_status" not in result
    assert "data_as_of" not in result


def test_industry_five_day_week_unchanged(tmp_path: Path):
    persist_board_snapshot(tmp_path, [_board("BK0001", "满窗")])
    persist_board_daily_history(
        tmp_path,
        "BK0001",
        [
            _h5("BK0001", "满窗", "2026-08-24", 1.0),
            _h5("BK0001", "满窗", "2026-08-25", 2.0),
            _h5("BK0001", "满窗", "2026-08-26", 3.0),
            _h5("BK0001", "满窗", "2026-08-27", 4.0),
            _h5("BK0001", "满窗", "2026-08-28", 5.0),
            _h5("BK0001", "满窗", "2026-08-31", 6.0),
        ],
        kind="board",
    )
    week = aggregate_board_window(tmp_path, kind="board", days=5, top=6)
    assert week["start"] == "2026-08-25"
    assert week["end"] == "2026-08-31"
    assert week["trading_days"] == 5
    assert week["items"][0]["main_net"] == 20.0


def test_industry_top6_heads_unchanged(tmp_path: Path):
    snapshot = []
    rows = []
    nets = [80.0, 10.0, -1.0, -2.0, -3.0, -4.0, -50.0, -60.0, -70.0]
    for i, net in enumerate(nets):
        code = f"BK{i:04d}"
        snapshot.append(_board(code, f"板{i}", net))
        rows.append(_h5(code, f"板{i}", "2026-08-21", net))
    persist_board_snapshot(tmp_path, snapshot)
    persist_board_daily_history(tmp_path, "BK0000", rows, kind="board")
    result = aggregate_board_window(tmp_path, kind="board", days=1, top=4)
    names = [item["name"] for item in result["items"]]
    assert names[:4] == ["板0", "板1", "板2", "板3"]
    assert names[4:] == ["板8", "板7", "板6", "板5"]


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


def _stub_pipeline(monkeypatch, tmp_path: Path, latest: date):
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
    monkeypatch.setattr(daily_pipeline.kline_sync, "sync_and_persist_daily_batch", lambda *a, **k: 11)

    def sync_quotes(_repo):
        captured["quotes"] = True
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
    return repo, captured


def test_pipeline_industry_failure_does_not_fail_daily_k(monkeypatch, tmp_path: Path):
    today = date.today()
    repo, captured = _stub_pipeline(monkeypatch, tmp_path, latest=today)

    def boom(_data_dir, **_kwargs):
        raise RuntimeError("industry roll exploded")

    monkeypatch.setattr(ff, "roll_industry_daily_from_h5", boom)
    result = daily_pipeline.run_now(repo, _capset())
    assert captured.get("quotes") is True
    assert result["quality"]["ok"] is True
    assert result["daily_source"] == "tickflow_quotes"
    assert result["industry_fund_flow_daily"]["ok"] is False
    assert result["industry_fund_flow_daily"]["status"] == "error"
    assert "不影响已成功日K" in result["industry_fund_flow_daily"]["note"]
