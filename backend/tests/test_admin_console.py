from __future__ import annotations

import pytest

from app.api.admin import router as admin_router
from app.config import settings
from app.services import auth
from app.services.admin_console import AdminConsole, AdminConsoleError
from app.services.hermes_tenant import HermesTenantRegistry
from app.services.user_strategies import UserStrategyWorkspace


class FakeHermesAdapter:
    def __init__(self, profile: str, calls: list[tuple[str, str]]) -> None:
        self.profile = profile
        self.calls = calls

    async def list_sessions(self, *, limit: int = 50):
        self.calls.append(("sessions", self.profile))
        return [
            {
                "id": f"session-{self.profile}",
                "title": "用户的历史问题",
                "preview": "如何分析这只股票？",
                "model": "grok-4.5",
                "started_at": 100.0,
                "last_active": 200.0,
                "message_count": 2,
                "estimated_cost_usd": 99,
            }
        ][:limit]

    async def get_messages(self, session_id: str):
        self.calls.append((f"messages:{session_id}", self.profile))
        return [
            {"id": "u1", "role": "user", "content": "如何分析这只股票？", "timestamp": 101},
            {"id": "t1", "role": "tool", "content": "internal tool trace", "timestamp": 102},
            {"id": "s1", "role": "system", "content": "internal prompt", "timestamp": 103},
            {"id": "a1", "role": "assistant", "content": "可以从基本面开始。", "timestamp": 104},
        ]


@pytest.fixture
def admin_runtime(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "public_registration_enabled", True)
    monkeypatch.setattr(settings, "public_registration_daily_per_ip", 10)
    monkeypatch.setattr(settings, "public_max_users", 10)
    monkeypatch.setattr(settings, "user_ai_daily_quota", 5)
    monkeypatch.setattr(settings, "hermes_multiuser_enabled", True)
    monkeypatch.setattr(settings, "hermes_profiles_root", tmp_path / "hermes")
    monkeypatch.setattr(settings, "hermes_gateway_base_url", "http://hermes.test")
    monkeypatch.setattr(settings, "hermes_internal_base_url", "http://127.0.0.1:3018")
    monkeypatch.setattr(settings, "hermes_owner_profile", "ot-owner")
    monkeypatch.setattr(settings, "ai_provider", "xai")
    monkeypatch.setattr(settings, "ai_model", "grok-4.5")
    hermes_python = tmp_path / "hermes-python"
    hermes_python.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings, "hermes_python", hermes_python)
    monkeypatch.setattr(auth, "_initialized_path", None)

    auth.set_password("owner-secret")
    owner = auth.verify_credentials("owner-secret", "admin")
    assert owner is not None
    alice, _ = auth.register_user("alice", "alice-secret", registration_source="alice")
    registry = HermesTenantRegistry()
    registry.resolve(owner)
    registry.resolve(alice)
    auth.consume_quota(alice)
    calls: list[tuple[str, str]] = []
    console = AdminConsole(
        registry=registry,
        adapter_factory=lambda tenant: FakeHermesAdapter(tenant.profile, calls),
        conversation_probe_timeout_s=1,
    )
    yield console, owner, alice, calls
    monkeypatch.setattr(auth, "_initialized_path", None)


@pytest.mark.asyncio
async def test_admin_user_overview_combines_identity_usage_profile_and_conversations(admin_runtime):
    console, _owner, alice, _calls = admin_runtime

    payload = await console.list_users(_owner)

    alice_row = next(user for user in payload["users"] if user["id"] == alice["id"])
    assert alice_row["username"] == "alice"
    assert alice_row["role"] == "user"
    assert alice_row["profile_status"] == "ready"
    assert alice_row["ai_requests_today"] == 1
    assert alice_row["ai_requests_7d"] == 1
    assert alice_row["ai_daily_limit"] == 5
    assert alice_row["conversation_count"] == 1
    assert alice_row["last_conversation_at"] == 200.0
    assert alice_row["profile_runtime_status"] == "ready"
    assert payload["summary"]["regular_users"] == 1
    assert payload["summary"]["active_users_today"] == 1


@pytest.mark.asyncio
async def test_admin_conversation_view_is_read_only_and_filtered(admin_runtime):
    console, owner, alice, _calls = admin_runtime
    profile_before = auth.hermes_profile_for_user(alice["id"])

    sessions = await console.list_user_sessions(owner, alice["id"])
    messages = await console.get_user_messages(
        owner,
        alice["id"],
        sessions["sessions"][0]["id"],
    )

    assert len(sessions["sessions"]) == 1
    assert sessions["sessions"][0]["id"].startswith("session-ot-")
    assert sessions["sessions"][0]["title"] == "用户的历史问题"
    assert "estimated_cost_usd" not in sessions["sessions"][0]
    assert [message["role"] for message in messages["messages"]] == ["user", "assistant"]
    assert "internal tool trace" not in str(messages)
    assert "internal prompt" not in str(messages)
    assert auth.hermes_profile_for_user(alice["id"]) == profile_before
    with auth._db() as conn:
        retired_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='admin_audit_events'"
        ).fetchone()
    assert retired_table is None


@pytest.mark.asyncio
async def test_user_insight_rejects_non_admin_before_reading(admin_runtime):
    console, _owner, alice, calls = admin_runtime

    with pytest.raises(AdminConsoleError, match="仅服务器管理员") as role_error:
        await console.list_user_sessions(alice, alice["id"])
    with pytest.raises(AdminConsoleError, match="仅服务器管理员"):
        await console.list_users(alice)

    assert role_error.value.status_code == 403
    assert calls == []


def test_admin_can_list_but_not_mutate_a_users_saved_strategies(admin_runtime):
    console, owner, alice, _calls = admin_runtime
    workspace = UserStrategyWorkspace(settings.data_dir, alice)
    workspace.save({
        "id": "ai_alpha",
        "name": "站上均线",
        "description": "收盘价高于 MA20",
        "source": "ai",
        "direction": "long",
        "rules": "收盘价高于二十日均线",
        "logic": "all",
        "conditions": [{"left": "close", "op": ">", "right": "field:ma20"}],
        "basic_filter": {"enabled": False},
        "scoring": {"change_pct": 1},
        "entry_signals": [],
        "exit_signals": ["signal_ma20_breakdown"],
        "stop_loss": -0.05,
        "max_hold_days": 20,
        "order_by": "score",
        "descending": True,
        "limit": 100,
    })

    result = console.list_user_strategies(owner, alice["id"])

    assert result["user"] == {"id": alice["id"], "username": "alice", "role": "user"}
    assert result["strategies"][0]["id"] == "ai_alpha"
    assert "conditions" not in result["strategies"][0]
    assert workspace.has("ai_alpha")


def test_retired_admin_read_metadata_is_removed_from_existing_identity_db(admin_runtime):
    _console, _owner, _alice, _calls = admin_runtime
    with auth._db() as conn:
        conn.execute(
            """CREATE TABLE admin_audit_events (
                id INTEGER PRIMARY KEY,
                reason TEXT NOT NULL
            )"""
        )
    auth._initialized_path = None

    auth._ensure_schema()

    with auth._db() as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='admin_audit_events'"
        ).fetchone()
    assert table is None


def test_admin_conversation_routes_are_get_only_and_have_no_audit_endpoint():
    methods_by_path = {
        route.path: route.methods
        for route in admin_router.routes
        if hasattr(route, "methods")
    }

    assert methods_by_path["/api/admin/users/{user_id}/conversations"] == {"GET"}
    assert methods_by_path[
        "/api/admin/users/{user_id}/conversations/{session_id}/messages"
    ] == {"GET"}
    assert "/api/admin/audit" not in methods_by_path
