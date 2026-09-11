from __future__ import annotations

from datetime import date

from app.services.free_sources.http_resilience import FetchResult, ResilientHttpClient
from app.services.free_sources.intraday_public import (
    fetch_public_depth_l1,
    public_intraday_to_minute_rows,
)


def test_public_intraday_to_minute_rows(monkeypatch):
    client = ResilientHttpClient()
    payload = {
        "data": {
            "sz000001": {
                "data": {
                    "date": "20260720",
                    "data": [
                        "0930 10.00 1000 10000",
                        "0931 10.10 1500 16000",
                        "0932 10.05 1800 19000",
                    ],
                }
            }
        }
    }

    def fake_get_json(url, **kwargs):
        return FetchResult(ok=True, data=payload, status_code=200)

    monkeypatch.setattr(client, "get_json", fake_get_json)
    rows = public_intraday_to_minute_rows("000001.SZ", trade_date=date(2026, 7, 20), client=client)
    assert len(rows) == 3
    assert rows[0]["close"] == 10.0
    assert rows[1]["volume"] == 500.0
    assert rows[2]["amount"] == 3000.0
    assert "2026-07-20" in rows[0]["datetime"]


def test_public_intraday_to_minute_rows_rejects_another_trade_date(monkeypatch):
    client = ResilientHttpClient()
    payload = {
        "data": {
            "sz000001": {
                "data": {
                    "date": "20260805",
                    "data": ["0930 12.00 1000 12000"],
                }
            }
        }
    }

    def fake_get_json(url, **kwargs):
        return FetchResult(ok=True, data=payload, status_code=200)

    monkeypatch.setattr(client, "get_json", fake_get_json)

    rows = public_intraday_to_minute_rows(
        "000001.SZ",
        trade_date=date(2026, 7, 20),
        client=client,
    )

    assert rows == []


def test_fetch_public_depth_l1(monkeypatch):
    client = ResilientHttpClient()
    parts = [""] * 50
    parts[1] = "平安银行"
    parts[2] = "000001"
    parts[3] = "11.20"
    parts[4] = "11.00"
    parts[5] = "11.10"
    parts[6] = "100"
    parts[9] = "11.19"
    parts[10] = "8"
    parts[19] = "11.21"
    parts[20] = "3"
    sample = 'v_sz000001="' + "~".join(parts) + '";\n'

    def fake_get_text(url, **kwargs):
        return FetchResult(ok=True, text=sample, status_code=200)

    monkeypatch.setattr(client, "get_text", fake_get_text)
    out = fetch_public_depth_l1(["000001.SZ"], client=client)
    assert "000001.SZ" in out
    assert out["000001.SZ"]["bid1_vol"] == 8
    assert out["000001.SZ"]["ask1_vol"] == 3
