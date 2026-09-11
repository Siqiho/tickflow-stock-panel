"""V6: two synthetic users through real routes, threads, and spawn workers.

Does not replace factor/monitor/backtest/kline modules with constant mocks.
External quote / model / notify boundaries are stubbed so they are not called.
"""
from __future__ import annotations

import multiprocessing as mp
from contextvars import copy_context
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import auth as auth_api
from app.api import backtest as backtest_api
from app.api import factors as factors_api
from app.api import kline as kline_api
from app.api import monitor_rules as monitor_api
from app.api import pipeline as pipeline_api
from app.api import strategy as strategy_api
from app.api.auth import COOKIE_NAME
from app.backtest.worker import make_worker_task, worker_principal_from_task
from app.config import settings
from app.factors.registry import FactorSpec, get_factor, register_factor, unregister_factor
from app.services import auth, strategy_cache, user_context
from app.services.authorization import require_request_access
from app.services.backtest_history import BacktestHistoryStore
from app.strategy.monitor import MonitorRuleEngine
from app.tickflow.capabilities import CapabilitySet


def _principal(user_id: str, *, role: str = "user") -> dict:
    return {"id": user_id, "username": user_id, "role": role}


def _custom_spec(fid: str, label: str) -> FactorSpec:
    return FactorSpec(
        id=fid, label=label, group="自定义", formula_text="close + 1",
        kind="custom", version=1,
    )


def _spawn_probe(task: dict, data_dir: str) -> dict:
    """Real child process: bind task principal and read registry + user_data_dir."""
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from app.backtest.worker import worker_principal_from_task
    from app.factors.registry import get_factor
    from app.services import user_context
    from app.strategy import config as strategy_config

    principal = worker_principal_from_task(task)
    token = user_context.bind(principal) if principal else None
    try:
        return {
            "user_id": user_context.current().get("id"),
            "has_alice_factor": get_factor("uf_alice_v6") is not None,
            "data_dir": str(user_context.user_data_dir(Path(data_dir))),
            "override": strategy_config.load_override(Path(data_dir), "demo"),
        }
    finally:
        if token is not None:
            user_context.reset(token)


@pytest.fixture
def two_users(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "auth_owner_username", "admin")
    monkeypatch.setattr(settings, "public_registration_enabled", True)
    monkeypatch.setattr(settings, "public_registration_invite_code", "")
    monkeypatch.setattr(settings, "public_registration_daily_per_ip", 10)
    monkeypatch.setattr(settings, "public_max_users", 10)
    monkeypatch.setattr(auth, "_initialized_path", None)
    auth.set_password("owner-secret")
    alice, alice_token = auth.register_user("alice", "alice-secret", registration_source="alice")
    bob, bob_token = auth.register_user("bob", "bob-secret", registration_source="bob")
    owner_token = auth.verify_and_create_session("owner-secret", "admin")
    assert owner_token

    rows = []
    end = date.today()
    for index in range(40):
        day = end - timedelta(days=39 - index)
        for symbol_id, daily_return in (("A", 0.01), ("B", 0.02)):
            rows.append({
                "symbol": symbol_id,
                "date": day,
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.0 + index,
                "volume": 1000.0,
                "amount": 10000.0,
                "turnover_rate": 0.02,
            })
    panel = pl.DataFrame(rows).sort(["symbol", "date"])

    class _Engine:
        def load_panel(self, symbols, start, end, *, columns=None, asset_type="stock", **_kwargs):
            frame = panel
            if columns is not None:
                for column in columns:
                    if column not in frame.columns:
                        frame = frame.with_columns(pl.lit(None).cast(pl.Float64).alias(column))
                frame = frame.select(columns)
            return frame.filter((pl.col("date") >= start) & (pl.col("date") <= end))

    app = FastAPI()
    app.include_router(auth_api.router)
    app.include_router(factors_api.router)
    app.include_router(monitor_api.router)
    app.include_router(strategy_api.router)
    app.include_router(backtest_api.router)
    app.include_router(kline_api.router)
    app.include_router(pipeline_api.router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    app.state.backtest_engine = _Engine()
    app.state.monitor_engine = MonitorRuleEngine()
    app.state.capabilities = None
    app.state.strategy_engine = SimpleNamespace(
        get=lambda sid: (_ for _ in ()).throw(ValueError(sid)),
        reload=lambda: None,
        list_strategies=lambda: [],
    )

    @app.middleware("http")
    async def _product_acl(request, call_next):
        path = request.url.path
        if path.startswith("/api/auth/"):
            return await call_next(request)
        token = request.cookies.get(COOKIE_NAME)
        user = auth.authenticate_session(token or "")
        if not user:
            return JSONResponse(status_code=401, content={"detail": "未登录或会话已过期"})
        try:
            require_request_access(user, request.method, path)
        except Exception as exc:
            from fastapi import HTTPException
            if isinstance(exc, HTTPException):
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            raise
        request.state.user = user
        ctx = user_context.bind(user)
        try:
            return await call_next(request)
        finally:
            user_context.reset(ctx)

    client = TestClient(app)
    yield {
        "client": client,
        "tmp_path": tmp_path,
        "alice": alice,
        "bob": bob,
        "alice_token": alice_token,
        "bob_token": bob_token,
        "owner_token": owner_token,
        "engine": app.state.monitor_engine,
        "app": app,
    }
    for fid in ("uf_alice_v6", "uf_owner_v6"):
        token = user_context.bind({
            "id": "owner", "username": "admin", "role": "admin", "legacy_home": True,
        })
        try:
            try:
                unregister_factor(fid)
            except Exception:
                pass
        finally:
            user_context.reset(token)
    monkeypatch.setattr(auth, "_initialized_path", None)


def _as(client: TestClient, token: str) -> None:
    client.cookies.set(COOKIE_NAME, token)


def test_factor_registry_and_cache_isolated_via_route_and_thread(two_users):
    client = two_users["client"]
    tmp_path = two_users["tmp_path"]
    alice = two_users["alice"]
    bob = two_users["bob"]

    _as(client, two_users["owner_token"])
    created = client.post("/api/factors/custom", json={
        "id": "uf_owner_v6",
        "label": "owner v6",
        "formula": "close + 1",
    })
    assert created.status_code == 200, created.text
    owner_ids = {item["id"] for item in client.get("/api/factors").json()["factors"]}
    assert "uf_owner_v6" in owner_ids

    _as(client, two_users["alice_token"])
    assert client.get("/api/factors/uf_owner_v6").status_code == 404
    assert client.post("/api/factors/custom", json={
        "label": "alice", "formula": "close + 1",
    }).status_code == 403

    alice_seen: dict = {}
    bob_seen: dict = {}

    def _alice_thread():
        register_factor(_custom_spec("uf_alice_v6", "alice v6"))
        strategy_cache.write_cache(tmp_path, "2026-09-08", {
            "demo": {"rows": [{"symbol": "600519.SH"}], "total": 1},
        })
        alice_seen["factor"] = get_factor("uf_alice_v6") is not None
        alice_seen["owner_factor"] = get_factor("uf_owner_v6") is not None
        cached = strategy_cache.read_cache(tmp_path)
        alice_seen["cache"] = (cached or {}).get("results", {}).get("demo", {}).get("total")
        alice_seen["dir"] = str(user_context.user_data_dir(tmp_path))

    token = user_context.bind(alice)
    try:
        ctx = copy_context()
        import threading
        thread = threading.Thread(target=ctx.run, args=(_alice_thread,))
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert alice_seen["factor"] is True
        assert alice_seen["owner_factor"] is False
        assert alice_seen["cache"] == 1
        assert f"tenants/{alice['id']}" in alice_seen["dir"]
    finally:
        try:
            unregister_factor("uf_alice_v6")
        except Exception:
            pass
        user_context.reset(token)

    def _bob_thread():
        bob_seen["factor"] = get_factor("uf_alice_v6") is not None
        bob_seen["cache"] = strategy_cache.read_cache(tmp_path)
        bob_seen["dir"] = str(user_context.user_data_dir(tmp_path))

    token = user_context.bind(bob)
    try:
        ctx = copy_context()
        import threading
        thread = threading.Thread(target=ctx.run, args=(_bob_thread,))
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert bob_seen["factor"] is False
        assert bob_seen["cache"] is None
        assert f"tenants/{bob['id']}" in bob_seen["dir"]
    finally:
        user_context.reset(token)


def test_backtest_history_and_worker_principal_stay_isolated(two_users, tmp_path):
    alice = two_users["alice"]
    bob = two_users["bob"]
    data_dir = two_users["tmp_path"]

    token = user_context.bind(alice)
    try:
        from app.strategy import config as strategy_config
        strategy_config.save_override(data_dir, "demo", {"basic_filter": {"price_min": 10}})
        task = make_worker_task("mining", data_dir, {"run_id": "aaaaaaaaaa", "request": {}, "data_fingerprint": {}, "source": "manual"})
        assert worker_principal_from_task(task)["id"] == alice["id"]
        store = BacktestHistoryStore(data_dir, alice)
        store.save(
            {
                "run_id": "aaaaaaaaaa",
                "strategy_info": {"id": "demo", "name": "demo", "source": "custom"},
                "config": {"strategy_id": "demo"},
                "stats": {},
            },
            strategy_owner_user_id=alice["id"],
        )
        ctx = copy_context()
        seen: dict = {}

        def _in_thread():
            seen["task_id"] = worker_principal_from_task(make_worker_task(
                "mining", data_dir, {"run_id": "bbbbbbbbbb", "request": {}, "data_fingerprint": {}, "source": "manual"},
            ))["id"]
            seen["history"] = [row["run_id"] for row in BacktestHistoryStore(data_dir).list()]
            seen["dir"] = str(user_context.user_data_dir(data_dir))

        import threading
        thread = threading.Thread(target=ctx.run, args=(_in_thread,))
        thread.start()
        thread.join(timeout=5)
        assert seen["task_id"] == alice["id"]
        assert seen["history"] == ["aaaaaaaaaa"]
        assert f"tenants/{alice['id']}" in seen["dir"]
    finally:
        user_context.reset(token)

    token = user_context.bind(bob)
    try:
        assert BacktestHistoryStore(data_dir).list() == []
        bob_task = make_worker_task(
            "mining", data_dir, {"run_id": "cccccccccc", "request": {}, "data_fingerprint": {}, "source": "manual"},
        )
        assert worker_principal_from_task(bob_task)["id"] == bob["id"]
        ctx = mp.get_context("spawn")
        with ctx.Pool(1) as pool:
            child = pool.apply(_spawn_probe, (bob_task, str(data_dir)))
        assert child["user_id"] == bob["id"]
        assert child["has_alice_factor"] is False
        assert f"tenants/{bob['id']}" in child["data_dir"]
        assert child["override"] == {}
    finally:
        user_context.reset(token)


def test_monitor_evaluate_keeps_runtime_owner_slices(two_users):
    engine = two_users["engine"]
    alice = two_users["alice"]
    bob = two_users["bob"]
    panel = pl.DataFrame({
        "symbol": ["600519.SH", "000001.SZ"],
        "name": ["茅台", "平安"],
        "close": [1800.0, 12.0],
        "change_pct": [0.02, -0.01],
    })
    engine.set_rules_for_user(alice["id"], [{
        "id": "alice_price",
        "name": "alice",
        "type": "price",
        "enabled": True,
        "scope": "symbols",
        "symbols": ["600519.SH"],
        "conditions": [{"field": "close", "op": ">", "value": 1}],
        "cooldown_seconds": 0,
    }])
    engine.set_rules_for_user(bob["id"], [{
        "id": "bob_price",
        "name": "bob",
        "type": "price",
        "enabled": True,
        "scope": "symbols",
        "symbols": ["000001.SZ"],
        "conditions": [{"field": "close", "op": ">", "value": 1}],
        "cooldown_seconds": 0,
    }])

    events = engine.evaluate(panel)
    owners = {(event["owner_user_id"], event["rule_id"], event["symbol"]) for event in events}
    assert (alice["id"], "alice_price", "600519.SH") in owners
    assert (bob["id"], "bob_price", "000001.SZ") in owners
    assert (alice["id"], "alice_price", "000001.SZ") not in owners
    assert (bob["id"], "bob_price", "600519.SH") not in owners

    engine.set_rules_for_user(alice["id"], [])
    assert engine.get_rule("alice_price", alice["id"]) is None
    assert engine.get_rule("bob_price", bob["id"]) is not None
    leftover = engine.evaluate(panel)
    assert all(event["owner_user_id"] == bob["id"] for event in leftover)


def test_http_missing_capset_is_empty_set_not_none_passthrough(two_users, monkeypatch):
    from app.tickflow.capabilities import Cap

    client = two_users["client"]
    _as(client, two_users["owner_token"])

    pull_spy = MagicMock(side_effect=AssertionError("must not pull without capset"))
    monkeypatch.setattr(kline_api.kline_sync, "sync_daily_batch", pull_spy)
    monkeypatch.setattr(kline_api.kline_sync, "sync_and_persist_minute", pull_spy)
    get_client = MagicMock(side_effect=AssertionError("must not call TickFlow"))
    monkeypatch.setattr("app.services.kline_sync.get_client", get_client)

    daily = client.post("/api/kline/sync?symbol=600519.SH&days=20")
    assert daily.status_code == 200
    assert daily.json()["rows_written"] == 0
    pull_spy.assert_not_called()
    get_client.assert_not_called()

    minute = client.post("/api/kline/sync_minute")
    assert minute.status_code == 403
    pull_spy.assert_not_called()

    captured: dict = {}
    started = __import__("threading").Event()

    def fake_run(repo, capset, on_progress=None):
        captured["capset"] = capset
        started.set()
        return {"quality": {"ok": True}}

    monkeypatch.setattr(pipeline_api.daily_pipeline, "run_now", fake_run)
    pipeline = client.post("/api/pipeline/run")
    assert pipeline.status_code == 200
    http_capset = pipeline_api._http_capset(SimpleNamespace(app=two_users["app"]))
    assert isinstance(http_capset, CapabilitySet)
    assert http_capset.all() == {}
    assert started.wait(timeout=3)
    assert captured["capset"] is not None
    assert not captured["capset"].has(Cap.KLINE_DAILY_BATCH)


def test_ai_save_and_publish_keep_owner_admin_acl(two_users):
    import json

    client = two_users["client"]

    def _definition(sid: str) -> str:
        return json.dumps({
            "id": sid,
            "name": sid,
            "rules": "close > 0",
            "source": "ai",
            "research_only": True,
            "conditions": [{"left": "close", "op": ">", "right": 0}],
        }, ensure_ascii=False)

    _as(client, two_users["alice_token"])
    alice_save = client.post("/api/strategies/ai/save", json={"strategy_id": "ai_v6", "code": _definition("ai_v6")})
    assert alice_save.status_code == 200, alice_save.text
    alice_publish = client.post("/api/strategies/ai_v6/publish")
    assert alice_publish.status_code == 403

    _as(client, two_users["bob_token"])
    bob_publish = client.post("/api/strategies/ai_v6/publish")
    assert bob_publish.status_code == 403

    _as(client, two_users["owner_token"])
    owner_save = client.post(
        "/api/strategies/ai/save",
        json={"strategy_id": "ai_owner_v6", "code": _definition("ai_owner_v6")},
    )
    assert owner_save.status_code == 200, owner_save.text
    owner_publish = client.post("/api/strategies/ai_owner_v6/publish")
    assert owner_publish.status_code in {200, 400}
    if owner_publish.status_code == 200:
        assert owner_publish.json()["ok"] is True
