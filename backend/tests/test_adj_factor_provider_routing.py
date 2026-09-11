"""Adj-factor source routing: same_as_daily heal + public fallback when TickFlow cannot serve."""
from __future__ import annotations

import json

from app.services import preferences
from app.services import kline_sync
from app.tickflow.capabilities import CapabilitySet


def _server_prefs(tmp_path, monkeypatch, payload: dict):
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(preferences, "_server_path", lambda: path)
    return path


def test_same_as_daily_heals_to_daily_provider(tmp_path, monkeypatch):
    _server_prefs(
        tmp_path,
        monkeypatch,
        {"daily_data_provider": "tickflow", "adj_factor_provider": "same_as_daily"},
    )
    assert preferences.get_adj_factor_provider_stored() == "same_as_daily"
    assert preferences.get_adj_factor_provider() == "tickflow"
    assert preferences.is_public_adj_factor_provider() is False


def test_unset_adj_follows_daily_default(tmp_path, monkeypatch):
    _server_prefs(tmp_path, monkeypatch, {})
    assert preferences.get_adj_factor_provider() == "tickflow"


def test_explicit_public_adj_is_kept(tmp_path, monkeypatch):
    _server_prefs(tmp_path, monkeypatch, {"adj_factor_provider": "sina"})
    assert preferences.get_adj_factor_provider() == "sina"
    assert preferences.is_public_adj_factor_provider() is True


def test_pipeline_public_adj_gate_matches_sync_fallback(monkeypatch):
    from app.jobs.daily_pipeline import adj_sync_uses_public_adapter
    from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet

    monkeypatch.setattr(
        "app.jobs.daily_pipeline._prefs.is_public_adj_factor_provider",
        lambda: False,
    )
    empty = CapabilitySet()
    assert adj_sync_uses_public_adapter(empty) is True
    paid = CapabilitySet({Cap.ADJ_FACTOR: CapabilityLimits()})
    assert adj_sync_uses_public_adapter(paid) is False


def test_pipeline_public_adj_pref_uses_public_even_with_tickflow_cap(monkeypatch):
    from app.jobs.daily_pipeline import adj_sync_uses_public_adapter
    from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet

    monkeypatch.setattr(
        "app.jobs.daily_pipeline._prefs.is_public_adj_factor_provider",
        lambda: True,
    )
    paid = CapabilitySet({Cap.ADJ_FACTOR: CapabilityLimits()})
    assert adj_sync_uses_public_adapter(paid) is True


def test_sync_adj_uses_public_when_tickflow_has_no_cap(monkeypatch):
    called = {}

    class _Public:
        def sync_adj_factors(self, *args, **kwargs):
            called["public"] = True
            return {"rows_delta": 3, "symbols_affected": ["000001.SZ"]}

    monkeypatch.setattr(preferences, "is_public_adj_factor_provider", lambda: False)
    monkeypatch.setattr(
        "app.data_providers.registry.get_provider",
        lambda name: _Public() if name == "public" else (_ for _ in ()).throw(AssertionError(name)),
    )

    rows, symbols = kline_sync.sync_adj_factor(
        ["000001.SZ"],
        repo=type("R", (), {"store": type("S", (), {"data_dir": None})()})(),
        capset=CapabilitySet(),
    )
    assert called.get("public") is True
    assert rows == 3
    assert symbols == ["000001.SZ"]
