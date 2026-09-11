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
        lambda data_dir, symbol, days=120, bins=80, as_of=None: {
            "symbol": symbol,
            "as_of": as_of.isoformat() if as_of else None,
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


def test_chips_endpoint_respects_as_of_date(tmp_path):
    import polars as pl

    d = tmp_path / "kline_daily" / "date=2026-08-05"
    d.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["301526.SZ", "301526.SZ", "301526.SZ"],
            "date": ["2026-07-17", "2026-07-20", "2026-08-05"],
            "open": [10.0, 8.5, 12.0],
            "high": [10.5, 9.0, 12.5],
            "low": [9.5, 7.5, 11.5],
            "close": [10.0, 8.0, 12.0],
            "volume": [1000.0, 1200.0, 1500.0],
            "amount": [10_000.0, 9_600.0, 18_000.0],
            "turnover_rate": [2.0, 3.0, 4.0],
        }
    ).write_parquet(d / "part.parquet")

    app = FastAPI()
    app.include_router(free_ext.router)
    app.state.repo = _Repo(tmp_path)
    client = TestClient(app)

    r = client.get("/api/free/chips/301526.SZ?as_of=2026-07-20")

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["as_of"] == "2026-07-20"
    assert data["current"] == 8.0
    assert data["days"] == 2


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


def test_board_history_refresh_returns_502_and_does_not_persist_go_stock(tmp_path, monkeypatch):
    persisted: list[list] = []

    def boom(*_a, **kwargs):
        assert kwargs.get("allow_local_fallback") is False
        raise RuntimeError("em down")

    def capture_persist(_data_dir, _code, rows, **_k):
        persisted.append(list(rows))
        return len(rows)

    monkeypatch.setattr("app.api.free_ext.fetch_board_daily_history", boom)
    monkeypatch.setattr("app.api.free_ext.persist_board_daily_history", capture_persist)

    app = FastAPI()
    app.include_router(free_ext.router)
    app.state.repo = _Repo(tmp_path)
    client = TestClient(app)
    response = client.get("/api/free/fund-flow/board/BK0428/history?refresh=1")

    assert response.status_code == 502
    assert persisted == []
    assert list(tmp_path.rglob("*.parquet")) == []


def test_board_history_refresh_keeps_cache_and_does_not_merge_go_stock(tmp_path, monkeypatch):
    from app.services.free_sources.fund_flow import persist_board_daily_history

    persist_board_daily_history(
        tmp_path,
        "BK0428",
        [{
            "code": "BK0428",
            "name": "电力",
            "date": "2026-08-21",
            "main_net": 9.0,
            "source": "eastmoney_fflow_day",
            "unit_amount": "yuan",
        }],
        kind="board",
    )

    def boom(*_a, **kwargs):
        assert kwargs.get("allow_local_fallback") is False
        raise RuntimeError("em down")

    persisted: list[list] = []

    def capture_persist(_data_dir, _code, rows, **_k):
        persisted.append(list(rows))
        return len(rows)

    monkeypatch.setattr("app.api.free_ext.fetch_board_daily_history", boom)
    monkeypatch.setattr("app.api.free_ext.persist_board_daily_history", capture_persist)

    app = FastAPI()
    app.include_router(free_ext.router)
    app.state.repo = _Repo(tmp_path)
    client = TestClient(app)
    response = client.get("/api/free/fund-flow/board/BK0428/history?refresh=1")

    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is True
    assert body["rows"][0]["source"] == "eastmoney_fflow_day"
    assert persisted == []
