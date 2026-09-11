from __future__ import annotations

from pathlib import Path

import pytest

from app.services.free_sources.fund_flow import (
    _parse_clist_payload,
    backfill_industry_daily_from_h5,
    fetch_board_daily_history,
    fetch_board_fund_flow_top,
    fetch_board_intraday_flow,
    fetch_stock_fund_flow,
    persist_board_daily_history,
    persist_board_intraday,
    persist_board_snapshot,
    persist_concept_snapshot,
    persist_stock_fund_flow,
    aggregate_board_window,
    refresh_top_boards_daily_history,
)
from app.services.free_sources.http_resilience import FetchResult, ResilientHttpClient


def test_fetch_stock_fund_flow_normalizes(monkeypatch):
    client = ResilientHttpClient()

    def fake_get_json(url, **kwargs):
        return FetchResult(
            ok=True,
            data={
                "data": {
                    "klines": [
                        "2026-07-01,100,10,20,30,40,1.2",
                        "2026-07-02,-50,5,6,7,8,0.5",
                    ]
                }
            },
        )

    monkeypatch.setattr(client, "get_json", fake_get_json)
    rows = fetch_stock_fund_flow("000001.SZ", client=client)
    assert len(rows) == 2
    assert rows[0]["symbol"] == "000001.SZ"
    assert rows[0]["main_net"] == 100.0
    assert rows[0]["source"] == "eastmoney_fflow"
    assert rows[0]["unit_amount"] == "yuan"


def test_fetch_stock_fund_flow_retries_alternate_host_after_disconnect(monkeypatch):
    client = ResilientHttpClient()
    calls: list[str] = []

    def fake_get_json(url, **kwargs):
        calls.append(url)
        if "push2his.eastmoney.com" in url:
            return FetchResult(ok=False, error="Server disconnected without sending a response.")
        return FetchResult(
            ok=True,
            data={
                "data": {
                    "klines": ["2026-07-31,100,10,20,30,40,1.2"],
                }
            },
        )

    monkeypatch.setattr(client, "get_json", fake_get_json)
    rows = fetch_stock_fund_flow("000636.SZ", client=client)

    assert len(rows) == 1
    assert rows[0]["symbol"] == "000636.SZ"
    assert len(calls) == 2
    assert "push2his.eastmoney.com" in calls[0]
    assert "emdatah5.eastmoney.com" in calls[1]


def test_fetch_stock_fund_flow_reports_source_after_all_hosts_fail(monkeypatch):
    client = ResilientHttpClient()
    calls: list[str] = []

    def fake_get_json(url, **kwargs):
        calls.append(url)
        return FetchResult(ok=False, error="Server disconnected without sending a response.")

    monkeypatch.setattr(client, "get_json", fake_get_json)

    with pytest.raises(RuntimeError, match="东方财富个股资金流暂时不可用"):
        fetch_stock_fund_flow("000636.SZ", client=client)

    assert len(calls) == 4


def test_parse_clist_payload_sorts_by_main_net():
    rows = _parse_clist_payload(
        {
            "data": {
                "diff": [
                    {"f12": "BK0002", "f14": "B", "f62": 10, "f3": 1.1},
                    {"f12": "BK0001", "f14": "A", "f62": 100, "f3": 2.2, "f184": 3.3},
                    {"f12": "BK0003", "f14": "C", "f62": -50, "f3": -1.0},
                ]
            }
        },
        kind="board",
    )
    assert [r["code"] for r in rows] == ["BK0001", "BK0002", "BK0003"]
    assert rows[0]["rank"] == 1
    assert rows[0]["main_net"] == 100.0
    assert rows[0]["source"] == "eastmoney_clist"


def test_fetch_board_fund_flow_top_prefers_dataapi(monkeypatch):
    client = ResilientHttpClient()
    calls = {"bkzj": 0, "clist": 0}

    def fake_get_json(url, **kwargs):
        if "dataapi/bkzj/getbkzj" in url:
            calls["bkzj"] += 1
            # first call key=f62 net ranks; subsequent key=f3 change ranks
            if "key=f3" in url or "key=f3&" in url or url.endswith("key=f3") or "key=f3" in url.replace("%3D", "="):
                return FetchResult(
                    ok=True,
                    data={
                        "data": {
                            "diff": [
                                {"f12": "BK0428", "f14": "电力", "f3": 120},  # 1.20%
                                {"f12": "BK0001", "f14": "银行", "f3": -20},
                            ]
                        }
                    },
                )
            return FetchResult(
                ok=True,
                data={
                    "data": {
                        "diff": [
                            {"f12": "BK0428", "f14": "电力", "f62": 553171712},
                            {"f12": "BK0001", "f14": "银行", "f62": -1000},
                        ]
                    }
                },
            )
        if "clist/get" in url:
            calls["clist"] += 1
            return FetchResult(ok=False, error="skip clist")
        return FetchResult(ok=False, error="unexpected url")

    monkeypatch.setattr(client, "get_json", fake_get_json)
    rows = fetch_board_fund_flow_top(client=client)
    assert rows[0]["name"] == "电力"
    assert rows[0]["source"] == "eastmoney_bkzj"
    assert rows[0]["change_pct"] == 1.2
    assert calls["bkzj"] >= 1
    assert calls["clist"] == 0


def test_fetch_board_fund_flow_top_falls_back_to_clist(monkeypatch):
    client = ResilientHttpClient()

    def fake_get_json(url, **kwargs):
        if "dataapi/bkzj/getbkzj" in url:
            return FetchResult(ok=False, error="bkzj down")
        assert "clist/get" in url
        return FetchResult(
            ok=True,
            data={
                "data": {
                    "diff": [
                        {"f12": "BK0428", "f14": "电力", "f62": 553171712, "f3": 1.2, "f184": 0.5},
                        {"f12": "BK0001", "f14": "银行", "f62": -1000, "f3": -0.2},
                    ]
                }
            },
        )

    monkeypatch.setattr(client, "get_json", fake_get_json)
    rows = fetch_board_fund_flow_top(client=client)
    assert rows[0]["name"] == "电力"
    assert rows[0]["source"] == "eastmoney_clist"


def test_fetch_board_daily_history_normalizes(monkeypatch):
    client = ResilientHttpClient()
    from app.services.free_sources import fund_flow as ff
    monkeypatch.setattr(ff, "_fetch_board_daily_history_from_go_stock", lambda *a, **k: [])
    monkeypatch.setenv("FUND_FLOW_HISTORY_PREFER_LOCAL", "0")

    def fake_get_json(url, **kwargs):
        assert "daykline" in url
        assert "90.BK0428" in url
        return FetchResult(
            ok=True,
            data={
                "data": {
                    "name": "电力",
                    "klines": [
                        "2026-07-01,100,1,2,3,4,0.1",
                        "2026-07-02,200,1,2,3,4,0.2",
                    ],
                }
            },
        )

    monkeypatch.setattr(client, "get_json", fake_get_json)
    rows = fetch_board_daily_history("BK0428", client=client, limit=10)
    assert len(rows) == 2
    assert rows[0]["code"] == "BK0428"
    assert rows[0]["name"] == "电力"
    assert rows[1]["main_net"] == 200.0
    assert rows[0]["source"] == "eastmoney_fflow_day"




def test_fetch_board_daily_history_trims_h5_rows_to_limit(monkeypatch):
    from app.services.free_sources import fund_flow as ff
    client = ResilientHttpClient()
    monkeypatch.setattr(ff, "_fetch_board_daily_history_from_go_stock", lambda *a, **k: [])
    monkeypatch.setenv("FUND_FLOW_HISTORY_PREFER_LOCAL", "0")

    def fake_get_json(url, **kwargs):
        if "getDBHistoryData" in url:
            klines = [f"2026-03-{i:02d},1,0,0,0,0,0" for i in range(2, 32)]
            klines += ["2026-08-21,2,0,0,0,0,0"]
            return FetchResult(ok=True, data={"data": {"name": "电力", "klines": klines}})
        return FetchResult(ok=False, error="push2his down")

    monkeypatch.setattr(client, "get_json", fake_get_json)
    rows = fetch_board_daily_history("BK0428", client=client, limit=21)
    assert len(rows) == 21
    assert rows[0]["date"] < rows[-1]["date"]
    assert rows[-1]["date"] == "2026-08-21"
    assert all(rows[i]["date"] <= rows[i + 1]["date"] for i in range(len(rows) - 1))


def test_fetch_board_daily_history_uses_h5_when_push2his_disconnects(monkeypatch):
    from app.services.free_sources import fund_flow as ff
    client = ResilientHttpClient()
    monkeypatch.setattr(ff, "_fetch_board_daily_history_from_go_stock", lambda *a, **k: [])
    monkeypatch.setenv("FUND_FLOW_HISTORY_PREFER_LOCAL", "0")
    calls = []

    def fake_get_json(url, **kwargs):
        calls.append(url)
        if "push2his" in url:
            return FetchResult(ok=False, error="Server disconnected without sending a response.")
        if "getDBHistoryData" in url:
            return FetchResult(
                ok=True,
                data={
                    "data": {
                        "name": "电力",
                        "klines": ["2026-03-02,-1,0,0,0,0,0", "2026-08-21,2,0,0,0,0,0"],
                    }
                },
            )
        return FetchResult(ok=False, error="unused")

    monkeypatch.setattr(client, "get_json", fake_get_json)
    rows = fetch_board_daily_history("BK0428", client=client, limit=120)
    assert any("getDBHistoryData" in url for url in calls)
    assert len(rows) == 2
    assert rows[0]["source"] == "eastmoney_fflow_day"
    assert rows[0]["date"] == "2026-03-02"


def test_fetch_board_intraday_flow_normalizes(monkeypatch):
    client = ResilientHttpClient()

    def fake_get_json(url, **kwargs):
        assert "fflow/kline/get" in url
        return FetchResult(
            ok=True,
            data={
                "data": {
                    "name": "电力",
                    "klines": [
                        "2026-07-19 09:31:00,10,1,2,3,4",
                        "2026-07-19 09:32:00,20,1,2,3,4",
                    ],
                }
            },
        )

    monkeypatch.setattr(client, "get_json", fake_get_json)
    payload = fetch_board_intraday_flow("BK0428", client=client)
    assert payload["name"] == "电力"
    assert payload["count"] == 2
    assert payload["points"][0]["time"] == "09:31"
    assert payload["points"][1]["main_net"] == 20.0


def test_persist_stock_fund_flow(tmp_path: Path):
    rows = [
        {
            "symbol": "000001.SZ",
            "date": "2026-07-01",
            "main_net": 1.0,
            "small_net": 0.1,
            "med_net": 0.2,
            "large_net": 0.3,
            "super_net": 0.4,
            "main_net_pct": 1.0,
            "source": "eastmoney_fflow",
            "unit_amount": "yuan",
        }
    ]
    n = persist_stock_fund_flow(tmp_path, "000001.SZ", rows)
    assert n == 1
    assert (tmp_path / "ext_data" / "ext_fund_flow_stock" / "config.json").exists()
    assert list((tmp_path / "ext_data" / "ext_fund_flow_stock" / "timeseries").rglob("*.parquet"))


def test_persist_board_snapshot(tmp_path: Path):
    rows = [
        {
            "code": "BK0001",
            "name": "银行",
            "main_net": 123.0,
            "change_pct": 1.2,
            "rank": 1,
            "as_of": "2026-07-07",
            "kind": "board",
            "source": "eastmoney_clist",
            "unit_amount": "yuan",
        }
    ]
    n = persist_board_snapshot(tmp_path, rows)
    assert n == 1
    assert (tmp_path / "ext_data" / "ext_fund_flow_bk" / "part.parquet").exists()


def test_persist_board_daily_and_intraday(tmp_path: Path):
    hist = [
        {
            "code": "BK0428",
            "name": "电力",
            "date": "2026-07-01",
            "main_net": 100.0,
            "source": "eastmoney_fflow_day",
            "unit_amount": "yuan",
        },
        {
            "code": "BK0428",
            "name": "电力",
            "date": "2026-07-02",
            "main_net": 200.0,
            "source": "eastmoney_fflow_day",
            "unit_amount": "yuan",
        },
    ]
    n = persist_board_daily_history(tmp_path, "BK0428", hist, kind="board")
    assert n == 2
    assert list((tmp_path / "ext_data" / "ext_fund_flow_bk_daily" / "timeseries").rglob("*.parquet"))

    payload = {
        "code": "BK0428",
        "name": "电力",
        "trade_date": "2026-07-19",
        "points": [
            {
                "code": "BK0428",
                "name": "电力",
                "timestamp": "2026-07-19 09:31:00",
                "time": "09:31",
                "date": "2026-07-19",
                "main_net": 10.0,
                "source": "eastmoney_fflow_min",
                "unit_amount": "yuan",
            }
        ],
    }
    m = persist_board_intraday(tmp_path, payload, kind="board")
    assert m == 1
    assert list((tmp_path / "ext_data" / "ext_fund_flow_bk_minute" / "timeseries").rglob("*.parquet"))


def test_refresh_top_boards_daily_history(monkeypatch, tmp_path: Path):
    client = ResilientHttpClient()
    calls = {"clist": 0, "day": 0}

    def fake_get_json(url, **kwargs):
        if "dataapi/bkzj/getbkzj" in url:
            calls["clist"] += 1  # reuse counter as ranking calls
            if "key=f3" in url:
                return FetchResult(
                    ok=True,
                    data={
                        "data": {
                            "diff": [
                                {"f12": "BK0001", "f14": "流入A", "f3": 10},
                                {"f12": "BK0002", "f14": "流出B", "f3": -8},
                            ]
                        }
                    },
                )
            return FetchResult(
                ok=True,
                data={
                    "data": {
                        "diff": [
                            {"f12": "BK0001", "f14": "流入A", "f62": 100},
                            {"f12": "BK0002", "f14": "流出B", "f62": -80},
                        ]
                    }
                },
            )
        if "clist/get" in url:
            calls["clist"] += 1
            return FetchResult(ok=False, error="unused")
        if "daykline" in url:
            calls["day"] += 1
            code = "BK0001" if "BK0001" in url else "BK0002"
            return FetchResult(
                ok=True,
                data={
                    "data": {
                        "name": code,
                        "klines": [f"2026-07-0{i},10,1,1,1,1,0.1" for i in range(1, 4)],
                    }
                },
            )
        return FetchResult(ok=False, error="unexpected url")

    monkeypatch.setattr(client, "get_json", fake_get_json)
    result = refresh_top_boards_daily_history(
        tmp_path, kind="board", top_n=1, limit=10, client=client
    )
    assert result["ok"] is True
    assert result["ranking_count"] == 2
    assert result["selected"] == 2
    assert result["history_points"] == 6
    assert calls["clist"] >= 1  # dataapi may call f62 + f3
    assert calls["day"] == 2
    assert (tmp_path / "ext_data" / "ext_fund_flow_bk" / "part.parquet").exists()


def test_fetch_board_daily_history_default_does_not_use_go_stock(monkeypatch):
    from inspect import signature

    from app.services.free_sources import fund_flow as ff

    assert signature(ff.fetch_board_daily_history).parameters["allow_local_fallback"].default is False

    client = ResilientHttpClient()
    called = {"local": 0}

    def fake_local(*_a, **_k):
        called["local"] += 1
        return [{
            "code": "BK0428",
            "name": "电力",
            "date": "2026-08-21",
            "main_net": 1.0,
            "source": "go_stock_local_snapshot",
            "unit_amount": "yuan",
        }]

    monkeypatch.setattr(ff, "_fetch_board_daily_history_from_go_stock", fake_local)
    monkeypatch.setenv("FUND_FLOW_HISTORY_PREFER_LOCAL", "1")
    monkeypatch.setattr(client, "get_json", lambda *_a, **_k: FetchResult(ok=False, error="em down"))

    with pytest.raises(RuntimeError, match="em down"):
        fetch_board_daily_history("BK0428", client=client, limit=10, kind="board")
    assert called["local"] == 0


def test_fetch_board_daily_history_opt_in_local_fallback(monkeypatch):
    from app.services.free_sources import fund_flow as ff

    client = ResilientHttpClient()
    monkeypatch.setattr(
        ff,
        "_fetch_board_daily_history_from_go_stock",
        lambda *_a, **_k: [{
            "code": "BK0428",
            "name": "电力",
            "date": "2026-08-21",
            "main_net": 1.0,
            "source": "go_stock_local_snapshot",
            "unit_amount": "yuan",
        }],
    )
    monkeypatch.setattr(client, "get_json", lambda *_a, **_k: FetchResult(ok=False, error="em down"))

    rows = fetch_board_daily_history(
        "BK0428", client=client, limit=10, kind="board", allow_local_fallback=True
    )
    assert rows[0]["source"] == "go_stock_local_snapshot"
    assert rows[0]["main_net"] == 1.0


def test_aggregate_board_window_does_not_treat_missing_days_as_zero(tmp_path: Path):
    import polars as pl
    from datetime import date
    from app.services.free_sources.fund_flow import persist_board_daily_history, persist_board_snapshot

    persist_board_snapshot(tmp_path, [
        {"code": "BK0001", "name": "完整板", "main_net": 1.0, "change_pct": 1.0, "as_of": "2026-08-21", "kind": "board", "source": "test", "unit_amount": "yuan"},
        {"code": "BK0002", "name": "缺口板", "main_net": 99.0, "change_pct": 1.0, "as_of": "2026-08-21", "kind": "board", "source": "test", "unit_amount": "yuan"},
    ])
    persist_board_daily_history(tmp_path, "BK0001", [
        {"code": "BK0001", "name": "完整板", "date": "2026-08-20", "main_net": 10.0, "source": "test", "unit_amount": "yuan"},
        {"code": "BK0001", "name": "完整板", "date": "2026-08-21", "main_net": 5.0, "source": "test", "unit_amount": "yuan"},
    ], kind="board")
    result = aggregate_board_window(tmp_path, kind="board", days=2, top=8)
    assert result["covered_count"] == 1
    assert result["missing_count"] == 1
    assert result["items"][0]["name"] == "完整板"
    assert result["items"][0]["main_net"] == 15.0
    assert result["missing"][0]["name"] == "缺口板"
    assert result["window_complete"] is False
    assert result["full_count"] == 1
    assert result["short"][0]["name"] == "缺口板"
    assert result["prior_available"] is False
    assert result["prior_note"] == "窗口外数据不足"

def test_aggregate_board_window_marks_incomplete_when_history_is_shorter_than_requested(tmp_path: Path):
    from app.services.free_sources.fund_flow import persist_board_daily_history, persist_board_snapshot, aggregate_board_window
    persist_board_snapshot(tmp_path, [
        {"code": "BK0001", "name": "完整板", "main_net": 1.0, "change_pct": 1.0, "as_of": "2026-08-21", "kind": "board", "source": "test", "unit_amount": "yuan"},
    ])
    persist_board_daily_history(tmp_path, "BK0001", [
        {"code": "BK0001", "name": "完整板", "date": "2026-08-20", "main_net": 10.0, "source": "test", "unit_amount": "yuan"},
        {"code": "BK0001", "name": "完整板", "date": "2026-08-21", "main_net": 5.0, "source": "test", "unit_amount": "yuan"},
    ], kind="board")
    result = aggregate_board_window(tmp_path, kind="board", days=21, top=8)
    assert result["requested_days"] == 21
    assert result["trading_days"] == 2
    assert result["window_complete"] is False
    assert result["window_note"] == "窗口数据不足"


def test_aggregate_board_window_incomplete_when_some_codes_are_short(tmp_path: Path):
    persist_board_snapshot(tmp_path, [
        {"code": "BK0001", "name": "满窗", "main_net": 1.0, "change_pct": 1.0, "as_of": "2026-08-21", "kind": "board", "source": "test", "unit_amount": "yuan"},
        {"code": "BK0002", "name": "短窗", "main_net": 2.0, "change_pct": 1.0, "as_of": "2026-08-21", "kind": "board", "source": "test", "unit_amount": "yuan"},
    ])
    persist_board_daily_history(tmp_path, "BK0001", [
        {"code": "BK0001", "name": "满窗", "date": "2026-08-19", "main_net": 3.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
        {"code": "BK0001", "name": "满窗", "date": "2026-08-20", "main_net": 4.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
        {"code": "BK0001", "name": "满窗", "date": "2026-08-21", "main_net": 5.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
    ], kind="board")
    persist_board_daily_history(tmp_path, "BK0002", [
        {"code": "BK0002", "name": "短窗", "date": "2026-08-20", "main_net": 1.0, "source": "go_stock_local_snapshot", "unit_amount": "yuan"},
        {"code": "BK0002", "name": "短窗", "date": "2026-08-21", "main_net": 2.0, "source": "go_stock_local_snapshot", "unit_amount": "yuan"},
    ], kind="board")
    result = aggregate_board_window(tmp_path, kind="board", days=3, top=8)
    assert result["trading_days"] == 3
    assert result["covered_count"] == 1
    assert result["full_count"] == 1
    assert result["window_complete"] is False
    assert result["window_note"] == "窗口数据不足"
    assert result["short"][0]["code"] == "BK0002"
    assert result["missing"][0]["code"] == "BK0002"


def test_aggregate_board_window_counts_only_h5_trading_days_from_latest(tmp_path: Path):
    persist_board_snapshot(tmp_path, [
        {"code": "BK0001", "name": "满窗", "main_net": 1.0, "kind": "board", "source": "test", "unit_amount": "yuan"},
    ])
    persist_board_daily_history(tmp_path, "BK0001", [
        {"code": "BK0001", "name": "满窗", "date": "2026-08-24", "main_net": 1.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
        {"code": "BK0001", "name": "满窗", "date": "2026-08-25", "main_net": 2.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
        {"code": "BK0001", "name": "满窗", "date": "2026-08-02", "main_net": 80.0, "source": "go_stock_local_snapshot", "unit_amount": "yuan"},
        {"code": "BK0001", "name": "满窗", "date": "2026-08-26", "main_net": 3.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
        {"code": "BK0001", "name": "满窗", "date": "2026-08-27", "main_net": 4.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
        {"code": "BK0001", "name": "满窗", "date": "2026-08-28", "main_net": 5.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
        {"code": "BK0001", "name": "满窗", "date": "2026-08-31", "main_net": 6.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
    ], kind="board")
    week = aggregate_board_window(tmp_path, kind="board", days=5, top=8)
    assert week["start"] == "2026-08-25"
    assert week["end"] == "2026-08-31"
    assert week["trading_days"] == 5
    assert week["items"][0]["main_net"] == 20.0
    assert week["window_complete"] is True


def test_aggregate_board_window_ignores_go_stock_only_tail_dates(tmp_path: Path):
    persist_board_snapshot(tmp_path, [
        {"code": "BK0001", "name": "满窗", "main_net": 1.0, "kind": "board", "source": "test", "unit_amount": "yuan"},
    ])
    persist_board_daily_history(tmp_path, "BK0001", [
        {"code": "BK0001", "name": "满窗", "date": "2026-08-26", "main_net": 3.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
        {"code": "BK0001", "name": "满窗", "date": "2026-08-27", "main_net": 4.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
        {"code": "BK0002", "name": "残片", "date": "2026-08-27", "main_net": 1.0, "source": "go_stock_local_snapshot", "unit_amount": "yuan"},
        {"code": "BK0001", "name": "满窗", "date": "2026-08-28", "main_net": 5.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
        {"code": "BK0002", "name": "残片", "date": "2026-08-29", "main_net": 8.0, "source": "go_stock_local_snapshot", "unit_amount": "yuan"},
        {"code": "BK0001", "name": "满窗", "date": "2026-08-31", "main_net": 9.0, "source": "go_stock_local_snapshot", "unit_amount": "yuan"},
    ], kind="board")
    result = aggregate_board_window(tmp_path, kind="board", days=3, top=8)
    assert result["end"] == "2026-08-28"
    assert result["start"] == "2026-08-26"
    assert result["trading_days"] == 3
    assert result["full_count"] == 1
    assert result["window_complete"] is True
    assert result["items"][0]["main_net"] == 12.0


def test_aggregate_concept_window_opens_when_young_themes_cannot_fill(tmp_path: Path):
    snapshot = []
    rows = []
    for i in range(20):
        code = f"BK{i:04d}"
        snapshot.append({"code": code, "name": f"概念{i}", "main_net": float(i), "kind": "concept", "source": "test", "unit_amount": "yuan"})
        for d, net in (("2026-08-26", 1.0 + i), ("2026-08-27", 2.0 + i), ("2026-08-28", 3.0 + i)):
            rows.append({"code": code, "name": f"概念{i}", "date": d, "main_net": net, "source": "eastmoney_fflow_day", "unit_amount": "yuan"})
    snapshot.append({"code": "BK9999", "name": "新主题", "main_net": 99.0, "kind": "concept", "source": "test", "unit_amount": "yuan"})
    rows.append({"code": "BK9999", "name": "新主题", "date": "2026-08-28", "main_net": 99.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"})
    persist_concept_snapshot(tmp_path, snapshot)
    persist_board_daily_history(tmp_path, "BK0000", rows, kind="concept")
    result = aggregate_board_window(tmp_path, kind="concept", days=3, top=8)
    assert result["window_complete"] is True
    assert result["full_count"] == 20
    assert result["snapshot_count"] == 21
    names = {item["name"] for item in result["items"]}
    assert "新主题" not in names
    assert "概念19" in names


def test_aggregate_board_window_keeps_both_inflow_and_outflow_heads(tmp_path: Path):
    snapshot = []
    rows = []
    for i in range(20):
        code = f"BK{i:04d}"
        name = f"板{i}"
        snapshot.append(
            {"code": code, "name": name, "main_net": float(i), "kind": "board", "source": "test", "unit_amount": "yuan"}
        )
        rows.append(
            {
                "code": code,
                "name": name,
                "date": "2026-08-21",
                "main_net": 100.0 - i * 10.0,
                "source": "eastmoney_fflow_day",
                "unit_amount": "yuan",
            }
        )
    persist_board_snapshot(tmp_path, snapshot)
    persist_board_daily_history(tmp_path, "BK0000", rows, kind="board")
    result = aggregate_board_window(tmp_path, kind="board", days=1, top=2)
    names = [item["name"] for item in result["items"]]
    assert names[:2] == ["板0", "板1"]
    assert "板19" in names
    assert "板18" in names
    assert result["items"][-1]["name"] == "板18" or result["items"][-2]["name"] == "板18"
    assert min(item["main_net"] for item in result["items"]) == 100.0 - 19 * 10.0


def test_aggregate_board_window_fills_inflow_column_beyond_positive_sums(tmp_path: Path):
    snapshot = []
    rows = []
    nets = [80.0, 10.0, -1.0, -2.0, -3.0, -4.0, -50.0, -60.0, -70.0]
    for i, net in enumerate(nets):
        code = f"BK{i:04d}"
        name = f"板{i}"
        snapshot.append(
            {"code": code, "name": name, "main_net": net, "kind": "board", "source": "test", "unit_amount": "yuan"}
        )
        rows.append(
            {
                "code": code,
                "name": name,
                "date": "2026-08-21",
                "main_net": net,
                "source": "eastmoney_fflow_day",
                "unit_amount": "yuan",
            }
        )
    persist_board_snapshot(tmp_path, snapshot)
    persist_board_daily_history(tmp_path, "BK0000", rows, kind="board")
    result = aggregate_board_window(tmp_path, kind="board", days=1, top=4)
    names = [item["name"] for item in result["items"]]
    assert names[:4] == ["板0", "板1", "板2", "板3"]
    assert names[4:] == ["板8", "板7", "板6", "板5"]


def test_persist_board_daily_merges_by_code_without_dropping_peers(tmp_path: Path):
    persist_board_daily_history(tmp_path, "BK0001", [
        {"code": "BK0001", "name": "银行", "date": "2026-08-21", "main_net": 1.0, "source": "go_stock_local_snapshot", "unit_amount": "yuan", "snap_time": "15:00"},
        {"code": "BK0002", "name": "电力", "date": "2026-08-21", "main_net": 2.0, "source": "go_stock_local_snapshot", "unit_amount": "yuan", "snap_time": "15:00"},
    ], kind="board")
    persist_board_daily_history(tmp_path, "BK0002", [
        {"code": "BK0002", "name": "电力", "date": "2026-08-21", "main_net": 9.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
    ], kind="board")
    import polars as pl
    out = pl.read_parquet(tmp_path / "ext_data" / "ext_fund_flow_bk_daily" / "timeseries" / "date=2026-08-21" / "part.parquet")
    assert out["code"].n_unique() == 2
    power = out.filter(pl.col("code") == "BK0002").row(0, named=True)
    assert power["main_net"] == 9.0
    assert power["source"] == "eastmoney_fflow_day"
    bank = out.filter(pl.col("code") == "BK0001").row(0, named=True)
    assert bank["main_net"] == 1.0


def test_fetch_board_daily_history_prefer_h5_hits_h5_first(monkeypatch):
    from app.services.free_sources import fund_flow as ff
    client = ResilientHttpClient()
    monkeypatch.setattr(ff, "_fetch_board_daily_history_from_go_stock", lambda *a, **k: [{"code": "BK0428", "source": "go_stock_local_snapshot"}])
    monkeypatch.setenv("FUND_FLOW_HISTORY_PREFER_LOCAL", "0")
    calls = []

    def fake_get_json(url, **kwargs):
        calls.append(url)
        if "getDBHistoryData" in url:
            return FetchResult(
                ok=True,
                data={"data": {"name": "电力", "klines": ["2026-08-21,2,0,0,0,0,0"]}},
            )
        return FetchResult(ok=False, error="should not be needed")

    monkeypatch.setattr(client, "get_json", fake_get_json)
    rows = fetch_board_daily_history(
        "BK0428",
        client=client,
        limit=21,
        allow_local_fallback=False,
        prefer_h5=True,
    )
    assert calls and "getDBHistoryData" in calls[0]
    assert not any("push2his" in url for url in calls)
    assert rows[0]["source"] == "eastmoney_fflow_day"


def test_fetch_board_daily_history_rejects_local_when_fallback_disabled(monkeypatch):
    from app.services.free_sources import fund_flow as ff
    client = ResilientHttpClient()
    monkeypatch.setattr(ff, "_fetch_board_daily_history_from_go_stock", lambda *a, **k: [{"code": "BK0428", "source": "go_stock_local_snapshot"}])
    monkeypatch.setenv("FUND_FLOW_HISTORY_PREFER_LOCAL", "0")

    def fake_get_json(url, **kwargs):
        return FetchResult(ok=False, error="em down")

    monkeypatch.setattr(client, "get_json", fake_get_json)
    with pytest.raises(RuntimeError, match="em down"):
        fetch_board_daily_history("BK0428", client=client, limit=21, allow_local_fallback=False)


def test_backfill_industry_daily_from_h5_writes_only_eastmoney_and_merges(monkeypatch, tmp_path: Path):
    persist_board_snapshot(tmp_path, [
        {"code": "BK0001", "name": "银行", "main_net": 1.0, "kind": "board", "source": "eastmoney_bkzj", "unit_amount": "yuan"},
        {"code": "BK0002", "name": "电力", "main_net": 2.0, "kind": "board", "source": "eastmoney_bkzj", "unit_amount": "yuan"},
    ])
    persist_board_daily_history(tmp_path, "BK0001", [
        {"code": "BK0001", "name": "银行", "date": "2026-08-20", "main_net": 1.0, "source": "go_stock_local_snapshot", "unit_amount": "yuan"},
        {"code": "BK0002", "name": "电力", "date": "2026-08-20", "main_net": 2.0, "source": "go_stock_local_snapshot", "unit_amount": "yuan"},
    ], kind="board")

    def fake_fetch(code, **kwargs):
        assert kwargs.get("allow_local_fallback") is False
        assert kwargs.get("prefer_h5") is True
        return [
            {"code": code, "name": code, "date": "2026-08-20", "main_net": 9.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
            {"code": code, "name": code, "date": "2026-08-21", "main_net": 8.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
        ]

    monkeypatch.setattr(
        "app.services.free_sources.fund_flow.fetch_board_daily_history",
        fake_fetch,
    )
    result = backfill_industry_daily_from_h5(
        tmp_path,
        codes=["BK0002"],
        limit=2,
        min_days=2,
        pause_s=0,
    )
    assert result["history_codes"] == ["BK0002"]
    assert result["failed"] == []
    import polars as pl
    day20 = pl.read_parquet(tmp_path / "ext_data" / "ext_fund_flow_bk_daily" / "timeseries" / "date=2026-08-20" / "part.parquet")
    assert set(day20["code"].to_list()) == {"BK0001", "BK0002"}
    power = day20.filter(pl.col("code") == "BK0002").row(0, named=True)
    assert power["source"] == "eastmoney_fflow_day"
    assert power["main_net"] == 9.0
    bank = day20.filter(pl.col("code") == "BK0001").row(0, named=True)
    assert bank["source"] == "go_stock_local_snapshot"


def test_backfill_concept_daily_from_h5_writes_only_eastmoney_and_merges(monkeypatch, tmp_path: Path):
    persist_concept_snapshot(tmp_path, [
        {"code": "BK1009", "name": "元宇宙概念", "main_net": 1.0, "kind": "concept", "source": "eastmoney_bkzj", "unit_amount": "yuan"},
        {"code": "BK0596", "name": "融资融券", "main_net": -2.0, "kind": "concept", "source": "eastmoney_bkzj", "unit_amount": "yuan"},
    ])
    persist_board_daily_history(tmp_path, "BK1009", [
        {"code": "BK1009", "name": "元宇宙概念", "date": "2026-08-20", "main_net": 1.0, "source": "go_stock_local_snapshot", "unit_amount": "yuan"},
        {"code": "BK0596", "name": "融资融券", "date": "2026-08-20", "main_net": 2.0, "source": "go_stock_local_snapshot", "unit_amount": "yuan"},
    ], kind="concept")

    def fake_fetch(code, **kwargs):
        assert kwargs.get("kind") == "concept"
        assert kwargs.get("allow_local_fallback") is False
        assert kwargs.get("prefer_h5") is True
        return [
            {"code": code, "name": code, "date": "2026-08-20", "main_net": 9.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
            {"code": code, "name": code, "date": "2026-08-21", "main_net": 8.0, "source": "eastmoney_fflow_day", "unit_amount": "yuan"},
        ]

    monkeypatch.setattr(
        "app.services.free_sources.fund_flow.fetch_board_daily_history",
        fake_fetch,
    )
    result = backfill_industry_daily_from_h5(
        tmp_path,
        codes=["BK1009"],
        limit=2,
        min_days=2,
        pause_s=0,
        kind="concept",
    )
    assert result["kind"] == "concept"
    assert result["history_codes"] == ["BK1009"]
    assert result["failed"] == []
    import polars as pl
    day20 = pl.read_parquet(tmp_path / "ext_data" / "ext_fund_flow_concept_daily" / "timeseries" / "date=2026-08-20" / "part.parquet")
    assert set(day20["code"].to_list()) == {"BK1009", "BK0596"}
    meta = day20.filter(pl.col("code") == "BK1009").row(0, named=True)
    assert meta["source"] == "eastmoney_fflow_day"
    assert meta["main_net"] == 9.0
    margin = day20.filter(pl.col("code") == "BK0596").row(0, named=True)
    assert margin["source"] == "go_stock_local_snapshot"

