from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet


def test_capabilities_includes_features(monkeypatch):
    capset = CapabilitySet(
        {
            Cap.KLINE_DAILY_BATCH: CapabilityLimits(rpm=60, batch=100),
            Cap.KLINE_DAILY_BY_SYMBOL: CapabilityLimits(rpm=60, batch=1),
        }
    )
    monkeypatch.setattr("app.api.routes.detect_capabilities", lambda force=False: capset)
    monkeypatch.setattr("app.api.routes.tier_label", lambda: "None")
    monkeypatch.setattr("app.api.routes.preferences.get_minute_sync_enabled", lambda: True)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.get("/api/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert "features" in body
    assert body["minute"]["available"] is False
    assert body["minute"]["reason_code"] == "no_capability"
    assert body["daily"]["available"] is True
