"""Market data-source writes must land in server prefs (the getters' source).

update_data_providers used preferences.save() (account file). Getters read
load_server(). That only worked when the owner legacy home coincided with
user_data/preferences.json.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from app.api import settings as settings_api
from app.services import preferences
from app.tickflow.capabilities import CapabilitySet


def _split_prefs(tmp_path, monkeypatch):
    user = tmp_path / "user_preferences.json"
    server = tmp_path / "server_preferences.json"
    user.write_text("{}", encoding="utf-8")
    server.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(preferences, "_path", lambda: user)
    monkeypatch.setattr(preferences, "_server_path", lambda: server)
    monkeypatch.setattr("app.services.user_context.is_admin", lambda: True)
    preferences._invalidate_cache()
    return user, server


def test_update_data_providers_writes_server_not_user_file(tmp_path, monkeypatch):
    user, server = _split_prefs(tmp_path, monkeypatch)
    monkeypatch.setattr(settings_api, "detect_capabilities", lambda: CapabilitySet())

    req = MagicMock()
    req.model_dump = lambda exclude_none: {
        "realtime_data_provider": "public",
        "daily_data_provider": "tickflow",
        "financial_data_provider": "eastmoney",
        "full_minute_data_provider": "tickflow",
        "depth5_data_provider": "tickflow",
    }
    settings_api.update_data_providers(req, MagicMock())

    assert json.loads(user.read_text(encoding="utf-8")) == {}
    stored = json.loads(server.read_text(encoding="utf-8"))
    assert stored["realtime_data_provider"] == "public"
    assert stored["daily_data_provider"] == "tickflow"
    assert stored["financial_provider"] == "eastmoney"
    assert stored["financial_data_provider"] == "eastmoney"
    assert stored["full_minute_data_provider"] == "tickflow"
    assert stored["depth5_data_provider"] == "tickflow"
    assert preferences.get_realtime_data_provider() == "public"
    assert preferences.get_financial_provider() == "eastmoney"
    assert preferences.get_full_minute_data_provider() == "tickflow"


def test_user_file_cannot_override_server_market_routing(tmp_path, monkeypatch):
    user, server = _split_prefs(tmp_path, monkeypatch)
    user.write_text(
        json.dumps({
            "realtime_data_provider": "tickflow",
            "full_minute_data_provider": "ghost_user",
            "daily_data_provider": "ghost_daily",
        }),
        encoding="utf-8",
    )
    server.write_text(
        json.dumps({
            "realtime_data_provider": "public",
            "full_minute_data_provider": "tickflow",
            "daily_data_provider": "tickflow",
        }),
        encoding="utf-8",
    )
    preferences._invalidate_cache()

    assert preferences.get_realtime_data_provider() == "public"
    assert preferences.get_full_minute_data_provider() == "tickflow"
    assert preferences.get_daily_data_provider() == "tickflow"


def test_full_minute_reads_server_prefs(tmp_path, monkeypatch):
    user, server = _split_prefs(tmp_path, monkeypatch)
    monkeypatch.setattr(
        preferences,
        "_allowed_data_providers",
        lambda: {"tickflow", "plugin_a", "plugin_b"},
    )
    user.write_text(json.dumps({"full_minute_data_provider": "plugin_a"}), encoding="utf-8")
    server.write_text(json.dumps({"full_minute_data_provider": "plugin_b"}), encoding="utf-8")
    preferences._invalidate_cache()
    assert preferences.get_full_minute_data_provider() == "plugin_b"


def test_unset_realtime_defaults_to_public(tmp_path, monkeypatch):
    _split_prefs(tmp_path, monkeypatch)
    assert preferences.get_realtime_data_provider() == "public"


def test_capability_matrix_injects_stored_same_as_daily(tmp_path, monkeypatch):
    from app.data_providers import custom as custom_sources
    from app.data_providers.capabilities import build_capability_matrix

    _split_prefs(tmp_path, monkeypatch)
    preferences.save_server({
        "daily_data_provider": "tickflow",
        "adj_factor_provider": "same_as_daily",
        "realtime_data_provider": "public",
    })
    monkeypatch.setattr(custom_sources, "list_plugins", lambda: [])
    monkeypatch.setattr(custom_sources, "list_sources", lambda: [])

    current = {
        "daily_data_provider": preferences.get_daily_data_provider(),
        "adj_factor_provider": preferences.get_adj_factor_provider_stored(),
        "minute_data_provider": preferences.get_minute_data_provider(),
        "realtime_data_provider": preferences.get_realtime_data_provider(),
        "depth5_data_provider": preferences.get_depth5_data_provider(),
        "full_minute_data_provider": preferences.get_full_minute_data_provider(),
        "financial_data_provider": preferences.get_financial_provider(),
    }
    caps = {c["id"]: c for c in build_capability_matrix(current, tickflow_tier="none")["capabilities"]}
    assert caps["adj_factor"]["current"] == "same_as_daily"
    assert caps["adj_factor"]["current_display"] == "跟随日K"
    assert caps["adj_factor"]["effective"] == "tickflow"
    assert caps["realtime"]["current"] == "public"
    assert caps["realtime"]["usable"] is True
