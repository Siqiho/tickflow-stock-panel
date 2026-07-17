from __future__ import annotations

from pathlib import Path

from app.services.free_sources.fund_flow import (
    fetch_stock_fund_flow,
    persist_board_snapshot,
    persist_stock_fund_flow,
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
            "source": "eastmoney_bkzj",
            "unit_amount": "yuan",
        }
    ]
    n = persist_board_snapshot(tmp_path, rows)
    assert n == 1
    assert (tmp_path / "ext_data" / "ext_fund_flow_bk" / "part.parquet").exists()
