"""financial_provider 优先于遗留 financial_data_provider。"""
from __future__ import annotations

import json

from app.services import preferences


def _server_prefs(tmp_path, monkeypatch, payload: dict):
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(preferences, "_server_path", lambda: path)
    return path


def test_local_financial_provider_wins_over_stale_v02_key(tmp_path, monkeypatch):
    _server_prefs(
        tmp_path,
        monkeypatch,
        {"financial_provider": "public", "financial_data_provider": "tickflow"},
    )

    assert preferences.get_financial_provider() == "public"
    assert preferences.is_public_financial_provider() is True


def test_v02_key_is_used_only_when_local_key_is_absent(tmp_path, monkeypatch):
    _server_prefs(tmp_path, monkeypatch, {"financial_data_provider": "public"})

    assert preferences.get_financial_provider() == "public"
    assert preferences.is_public_financial_provider() is True


def test_tickflow_v02_key_alone_stays_tickflow(tmp_path, monkeypatch):
    _server_prefs(tmp_path, monkeypatch, {"financial_data_provider": "tickflow"})

    assert preferences.get_financial_provider() == "tickflow"
    assert preferences.is_public_financial_provider() is False


def test_missing_financial_keys_default_to_tickflow(tmp_path, monkeypatch):
    _server_prefs(tmp_path, monkeypatch, {})

    assert preferences.get_financial_provider() == "tickflow"
    assert preferences.is_public_financial_provider() is False
