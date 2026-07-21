from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import free_ext


class _Store:
    def __init__(self, data_dir):
        self.data_dir = data_dir


class _Repo:
    def __init__(self, data_dir):
        self.store = _Store(data_dir)


def test_chips_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.api.free_ext.chips_for_symbol",
        lambda data_dir, symbol, days=120, bins=80: {
            "symbol": symbol,
            "days": 2,
            "bins": bins,
            "items": [{"price": 10.0, "vol": 1.0, "ratio": 1.0}],
            "profit_ratio": 0.5,
            "avg_cost": 10.0,
            "method": "approx_turnover_decay_vwap_kernel",
            "disclaimer": "approx",
            "source": "local_daily_derived",
        },
    )
    app = FastAPI()
    app.include_router(free_ext.router)
    app.state.repo = _Repo(tmp_path)
    client = TestClient(app)
    r = client.get("/api/free/chips/000001.SZ")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["symbol"] == "000001.SZ"


def test_quality_run(tmp_path):
    import polars as pl

    d = tmp_path / "kline_daily" / "date=2026-07-07"
    d.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["000001.SZ"],
            "date": ["2026-07-07"],
            "open": [10.0],
            "high": [11.0],
            "low": [9.5],
            "close": [10.5],
            "volume": [1000.0],
            "amount": [10500.0],
        }
    ).write_parquet(d / "part.parquet")
    app = FastAPI()
    app.include_router(free_ext.router)
    app.state.repo = _Repo(tmp_path)
    client = TestClient(app)
    r = client.post("/api/free/quality/run")
    assert r.status_code == 200
    assert r.json()["report"]["date"] == "2026-07-07"
