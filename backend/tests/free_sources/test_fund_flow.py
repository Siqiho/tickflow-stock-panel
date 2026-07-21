from __future__ import annotations

from pathlib import Path

from app.services.free_sources.fund_flow import (
    fetch_board_daily_history,
    fetch_board_fund_flow_top,
    fetch_board_intraday_flow,
    fetch_stock_fund_flow,
    persist_board_daily_history,
    persist_board_intraday,
    persist_board_snapshot,
    persist_stock_fund_flow,
    refresh_top_boards_daily_history,
    _parse_clist_payload,
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


def test_fetch_board_daily_history_falls_back_to_go_stock_local(monkeypatch, tmp_path: Path):
    """When EM daykline hosts fail, aggregate go-stock local snapshots."""
    from app.services.free_sources import fund_flow as ff

    client = ResilientHttpClient()

    def fake_get_json(url, **kwargs):
        return FetchResult(ok=False, error="em down")

    monkeypatch.setattr(client, "get_json", fake_get_json)

    # point candidates to real workspace db if present, else skip
    db = Path("/Users/simon/Trading/go-stock/data/stock.db")
    if not db.exists():
        return
    monkeypatch.setattr(ff, "_go_stock_db_candidates", lambda: [db])
    rows = ff.fetch_board_daily_history("BK1238", client=client, limit=10, kind="board")
    assert rows
    assert rows[0]["source"] == "go_stock_local_snapshot"
    assert "date" in rows[0] and rows[0].get("main_net") is not None
