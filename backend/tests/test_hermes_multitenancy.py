from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import yaml

from app.config import settings
from app.services import auth, stock_reports, user_context
from app.services.hermes_agent import (
    HermesAgentAdapter,
    HermesAgentError,
    HermesConnectionSettings,
)
from app.services.hermes_tenant import HermesTenantError, HermesTenantRegistry
from app.services.user_console_data import UserConsoleDataModule


@pytest.fixture
def hermes_tenants(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "public_registration_enabled", True)
    monkeypatch.setattr(settings, "public_registration_invite_code", "")
    monkeypatch.setattr(settings, "public_registration_daily_per_ip", 10)
    monkeypatch.setattr(settings, "public_max_users", 10)
    monkeypatch.setattr(settings, "hermes_multiuser_enabled", True)
    monkeypatch.setattr(settings, "hermes_profiles_root", tmp_path / "hermes")
    monkeypatch.setattr(settings, "hermes_gateway_base_url", "http://hermes.test")
    monkeypatch.setattr(settings, "hermes_internal_base_url", "http://127.0.0.1:3018")
    monkeypatch.setattr(settings, "hermes_owner_profile", "ot-owner")
    monkeypatch.setattr(settings, "ai_access_mode", "cloud_subscription")
    monkeypatch.setattr(settings, "ai_subscription_enabled", True)
    monkeypatch.setattr(settings, "ai_subscription_plan", "Grok 云订阅")
    monkeypatch.setattr(settings, "ai_provider", "xai")
    monkeypatch.setattr(settings, "ai_model", "grok-4.5")
    monkeypatch.setattr(settings, "ai_api_key", "server-grok-secret")
    hermes_python = tmp_path / "hermes-python"
    hermes_python.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings, "hermes_python", hermes_python)
    monkeypatch.setattr(auth, "_initialized_path", None)

    auth.set_password("owner-secret")
    alice, _ = auth.register_user("alice", "alice-secret", registration_source="alice")
    bob, _ = auth.register_user("bob", "bob-secret", registration_source="bob")
    yield tmp_path, alice, bob
    monkeypatch.setattr(auth, "_initialized_path", None)


def test_each_account_gets_a_stable_isolated_profile(hermes_tenants):
    _tmp_path, alice, bob = hermes_tenants
    registry = HermesTenantRegistry()

    alice_tenant = registry.resolve(alice)
    bob_tenant = registry.resolve(bob)
    alice_again = registry.resolve(alice)

    assert alice_tenant.profile != bob_tenant.profile
    assert alice_tenant.profile_home != bob_tenant.profile_home
    assert alice_tenant.api_key != bob_tenant.api_key
    assert alice_tenant.bridge_key != bob_tenant.bridge_key
    assert alice_tenant.data_key != bob_tenant.data_key
    assert alice_again.api_key == alice_tenant.api_key
    assert alice_again.profile == alice_tenant.profile
    assert alice_tenant.api_prefix == f"/p/{alice_tenant.profile}"

    marker = json.loads(
        (alice_tenant.profile_home / "one-trading-tenant.json").read_text(encoding="utf-8")
    )
    assert marker == {"schema": 1, "user_id": alice["id"], "profile": alice_tenant.profile}
    assert (alice_tenant.profile_home / "SOUL.md").is_file()
    assert not (alice_tenant.profile_home / "memory_store.db").exists()
    assert auth.user_for_hermes_profile(alice_tenant.profile)["id"] == alice["id"]
    profile_config = yaml.safe_load(
        (alice_tenant.profile_home / "config.yaml").read_text(encoding="utf-8")
    )
    assert profile_config["providers"]["custom"]["name"] == "one-trading-user-console"
    assert profile_config["providers"]["custom"]["transport"] == "codex_responses"
    assert profile_config["agent"]["disabled_toolsets"] == ["bfl"]
    mcp_server_name = next(iter(profile_config["mcp_servers"]))
    assert mcp_server_name.startswith("ot-data-")
    assert profile_config["mcp_servers"][mcp_server_name]["command"] == str(settings.hermes_python)
    assert profile_config["mcp_servers"][mcp_server_name]["tools"] == {
        "resources": False,
        "prompts": False,
    }
    assert mcp_server_name in profile_config["platform_toolsets"]["api_server"]
    assert "skills" in profile_config["platform_toolsets"]["api_server"]
    skills_dir = Path(__file__).resolve().parents[2] / "hermes-skills"
    assert profile_config["skills"]["external_dirs"] == [str(skills_dir)]
    soul = (alice_tenant.profile_home / "SOUL.md").read_text(encoding="utf-8")
    assert 'skill_view(name="stock-analysis")' in soul
    assert 'skill_view(name="financial-analysis")' in soul
    assert 'skill_view(name="market-recap")' in soul
    assert '先读当前 Profile 的用户关注面' in soul
    assert '不要把这些产品指令写入长期记忆' in soul
    assert '三个 Skill 的章节模板' in soul
    assert '禁止 skill_manage / patch / edit 三个权威 Skill' in soul
    assert 'stock-analysis' in soul and 'financial-analysis' in soul and 'market-recap' in soul
    assert alice_tenant.provider == "custom"
    profile_env = (alice_tenant.profile_home / ".env").read_text(encoding="utf-8")
    assert "AI_API_KEY" not in profile_env
    assert "XAI_API_KEY" not in profile_env
    assert HermesConnectionSettings.from_tenant(alice_tenant).enabled_mcp_servers == (
        "one-trading-data",
    )


def test_each_account_gets_a_unique_mcp_connection_and_tool_prefix(hermes_tenants):
    _tmp_path, alice, bob = hermes_tenants
    registry = HermesTenantRegistry()
    alice_tenant = registry.resolve(alice)
    bob_tenant = registry.resolve(bob)
    alice_config = yaml.safe_load((alice_tenant.profile_home / "config.yaml").read_text())
    bob_config = yaml.safe_load((bob_tenant.profile_home / "config.yaml").read_text())

    alice_server = next(iter(alice_config["mcp_servers"]))
    bob_server = next(iter(bob_config["mcp_servers"]))
    assert alice_server != bob_server
    assert alice_server.startswith("ot-data-")
    assert bob_server.startswith("ot-data-")
    assert alice_server in alice_config["platform_toolsets"]["api_server"]
    assert bob_server in bob_config["platform_toolsets"]["api_server"]
    assert alice_config["mcp_servers"][alice_server]["env"]["ONE_TRADING_HERMES_PROFILE"] == alice_tenant.profile
    assert bob_config["mcp_servers"][bob_server]["env"]["ONE_TRADING_HERMES_PROFILE"] == bob_tenant.profile


def test_existing_managed_profile_is_hardened_on_resolve(hermes_tenants):
    _tmp_path, alice, _bob = hermes_tenants
    registry = HermesTenantRegistry()
    tenant = registry.resolve(alice)
    config_path = tenant.profile_home / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config.pop("agent", None)
    unique_server = next(iter(config["mcp_servers"]))
    config["mcp_servers"]["one-trading-data"] = config["mcp_servers"].pop(unique_server)
    config["platform_toolsets"]["api_server"].remove(unique_server)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    registry.resolve(alice)

    hardened = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert hardened["agent"]["disabled_toolsets"] == ["bfl"]
    migrated_server = next(iter(hardened["mcp_servers"]))
    assert migrated_server.startswith("ot-data-")
    assert migrated_server in hardened["platform_toolsets"]["api_server"]
    assert "one-trading-data" not in hardened["mcp_servers"]
    assert hardened["mcp_servers"][migrated_server]["tools"] == {
        "resources": False,
        "prompts": False,
    }
    skills_dir = Path(__file__).resolve().parents[2] / "hermes-skills"
    assert hardened["skills"]["external_dirs"] == [str(skills_dir)]
    assert "skills" in hardened["platform_toolsets"]["api_server"]


def test_owner_also_gets_a_managed_server_grok_profile(hermes_tenants):
    _tmp_path, _alice, _bob = hermes_tenants
    owner = auth.user_by_id("owner")
    assert owner is not None

    tenant = HermesTenantRegistry().resolve(owner)
    profile_config = yaml.safe_load(
        (tenant.profile_home / "config.yaml").read_text(encoding="utf-8")
    )

    assert tenant.profile == "ot-owner"
    assert (tenant.profile_home / "one-trading-tenant.json").is_file()
    assert profile_config["providers"]["custom"]["default_model"] == "grok-4.5"
    assert profile_config["providers"]["custom"]["base_url"].endswith(
        "/api/hermes-xai/v1/profiles/ot-owner"
    )


def test_unconfigured_local_owner_can_provision_without_creating_login_credentials(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "hermes_multiuser_enabled", True)
    monkeypatch.setattr(settings, "hermes_profiles_root", tmp_path / "hermes")
    monkeypatch.setattr(settings, "hermes_gateway_base_url", "http://hermes.test")
    monkeypatch.setattr(settings, "hermes_internal_base_url", "http://127.0.0.1:3018")
    monkeypatch.setattr(settings, "hermes_owner_profile", "ot-owner")
    monkeypatch.setattr(settings, "ai_access_mode", "cloud_subscription")
    monkeypatch.setattr(settings, "ai_subscription_enabled", True)
    monkeypatch.setattr(settings, "ai_provider", "xai")
    monkeypatch.setattr(settings, "ai_model", "grok-4.5")
    monkeypatch.setattr(settings, "ai_api_key", "server-grok-secret")
    hermes_python = tmp_path / "hermes-python"
    hermes_python.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings, "hermes_python", hermes_python)
    monkeypatch.setattr(auth, "_initialized_path", None)

    assert auth.is_configured() is False

    tenant = HermesTenantRegistry().resolve(user_context.current())

    assert tenant.user_id == "owner"
    assert tenant.profile == "ot-owner"
    assert auth.is_configured() is False
    assert auth.user_by_id("owner") is None
    assert auth.hermes_profile_for_user("owner")["profile_name"] == "ot-owner"
    marker = json.loads(
        (tenant.profile_home / "one-trading-tenant.json").read_text(encoding="utf-8")
    )
    assert marker == {"schema": 1, "user_id": "owner", "profile": "ot-owner"}

    monkeypatch.setattr(auth, "_initialized_path", None)


def test_profile_bridge_credentials_cannot_cross_accounts(hermes_tenants):
    _tmp_path, alice, bob = hermes_tenants
    registry = HermesTenantRegistry()
    alice_tenant = registry.resolve(alice)
    bob_tenant = registry.resolve(bob)

    resolved_user, _ = registry.authenticate(
        alice_tenant.profile,
        f"Bearer {alice_tenant.bridge_key}",
        purpose="bridge",
    )
    assert resolved_user["id"] == alice["id"]

    with pytest.raises(HermesTenantError, match="认证失败"):
        registry.authenticate(
            alice_tenant.profile,
            f"Bearer {bob_tenant.bridge_key}",
            purpose="bridge",
        )
    with pytest.raises(HermesTenantError, match="认证失败"):
        registry.authenticate(
            alice_tenant.profile,
            f"Bearer {alice_tenant.bridge_key}",
            purpose="data",
        )


def test_unmarked_nonempty_profile_directory_is_never_claimed(hermes_tenants):
    tmp_path, alice, _bob = hermes_tenants
    mapping = auth.ensure_hermes_profile(alice)
    profile_home = tmp_path / "hermes" / "profiles" / mapping["profile_name"]
    profile_home.mkdir(parents=True)
    (profile_home / "foreign.txt").write_text("not managed", encoding="utf-8")

    with pytest.raises(HermesTenantError, match="没有租户标记") as exc_info:
        HermesTenantRegistry().resolve(alice)

    assert exc_info.value.status_code == 409
    assert not (profile_home / "one-trading-tenant.json").exists()


def test_regular_agent_catalog_hides_admin_only_server_views(hermes_tenants):
    _tmp_path, alice, _bob = hermes_tenants
    tenant = HermesTenantRegistry().resolve(alice)
    token = user_context.bind(alice)
    try:
        module = UserConsoleDataModule(api_key=tenant.data_key, profile=tenant.profile)
        visible = {
            view["id"]
            for domain in module.catalog()["domains"]
            for view in module.catalog(domain=domain)["views"]
        }
    finally:
        user_context.reset(token)

    assert "watchlist_enriched" in visible
    assert "market_overview" in visible
    assert "ext_data_rows" not in visible
    assert "data_catalog" not in visible


@pytest.mark.asyncio
async def test_analysis_history_bridge_reads_only_the_profile_account(hermes_tenants):
    _tmp_path, alice, bob = hermes_tenants
    registry = HermesTenantRegistry()
    alice_tenant = registry.resolve(alice)
    bob_tenant = registry.resolve(bob)

    token = user_context.bind(alice)
    try:
        stock_reports.save_report(
            {
                "id": "sar_alice_private",
                "symbol": "600519.SH",
                "name": "贵州茅台",
                "summary": "Alice 的个股摘要",
                "content": "ALICE_PRIVATE_REPORT_BODY",
                "created_at": "2026-08-12T02:00:00",
            }
        )
    finally:
        user_context.reset(token)

    token = user_context.bind(bob)
    try:
        stock_reports.save_report(
            {
                "id": "sar_bob_private",
                "symbol": "000001.SZ",
                "name": "平安银行",
                "summary": "Bob 的个股摘要",
                "content": "BOB_PRIVATE_REPORT_BODY",
                "created_at": "2026-08-12T03:00:00",
            }
        )
    finally:
        user_context.reset(token)

    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1",
    ) as client:
        alice_index = await client.post(
            f"/api/hermes-data/v1/profiles/{alice_tenant.profile}/query",
            headers={"Authorization": f"Bearer {alice_tenant.data_key}"},
            json={"view": "analysis_history", "params": {}, "max_items": 20},
        )
        alice_detail = await client.post(
            f"/api/hermes-data/v1/profiles/{alice_tenant.profile}/query",
            headers={"Authorization": f"Bearer {alice_tenant.data_key}"},
            json={
                "view": "analysis_history_report",
                "params": {"kind": "stock", "report_id": "sar_alice_private"},
                "max_items": 20,
            },
        )
        alice_cross_read = await client.post(
            f"/api/hermes-data/v1/profiles/{alice_tenant.profile}/query",
            headers={"Authorization": f"Bearer {alice_tenant.data_key}"},
            json={
                "view": "analysis_history_report",
                "params": {"kind": "stock", "report_id": "sar_bob_private"},
                "max_items": 20,
            },
        )
        bob_index = await client.post(
            f"/api/hermes-data/v1/profiles/{bob_tenant.profile}/query",
            headers={"Authorization": f"Bearer {bob_tenant.data_key}"},
            json={"view": "analysis_history", "params": {}, "max_items": 20},
        )

    assert alice_index.status_code == 200
    assert [item["id"] for item in alice_index.json()["data"]["reports"]] == ["sar_alice_private"]
    assert alice_detail.status_code == 200
    assert alice_detail.json()["data"]["report"]["content"] == "ALICE_PRIVATE_REPORT_BODY"
    assert alice_cross_read.status_code == 502
    assert "BOB_PRIVATE_REPORT_BODY" not in alice_cross_read.text
    assert bob_index.status_code == 200
    assert [item["id"] for item in bob_index.json()["data"]["reports"]] == ["sar_bob_private"]


@pytest.mark.asyncio
async def test_agent_adapter_routes_every_operation_through_its_profile(hermes_tenants):
    _tmp_path, alice, _bob = hermes_tenants
    tenant = HermesTenantRegistry().resolve(alice)
    seen: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.method,
                request.url.path,
                request.headers.get("authorization", ""),
            )
        )
        if request.url.path.endswith("/v1/models"):
            return httpx.Response(
                200,
                json={"data": [{"id": tenant.profile}]},
                request=request,
            )
        if request.url.path.endswith("/api/sessions") and request.method == "POST":
            return httpx.Response(
                200,
                json={"session": {"id": "alice-session"}},
                request=request,
            )
        raise AssertionError(f"unexpected request {request.method} {request.url.path}")

    settings_for_user = HermesConnectionSettings.from_tenant(tenant)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://hermes.test",
    ) as client:
        session = await HermesAgentAdapter(settings_for_user, client=client).create_session("你好")

    assert session["id"] == "alice-session"
    assert [path for _method, path, _auth in seen] == [
        f"/p/{tenant.profile}/v1/models",
        f"/p/{tenant.profile}/api/sessions",
    ]
    assert {authorization for _method, _path, authorization in seen} == {
        f"Bearer {tenant.api_key}"
    }


@pytest.mark.asyncio
async def test_agent_adapter_fails_closed_when_gateway_ignores_profile_prefix(hermes_tenants):
    _tmp_path, alice, _bob = hermes_tenants
    tenant = HermesTenantRegistry().resolve(alice)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "one-trading"}]},
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://hermes.test",
    ) as client:
        adapter = HermesAgentAdapter(HermesConnectionSettings.from_tenant(tenant), client=client)
        with pytest.raises(HermesAgentError, match="拒绝回退"):
            await adapter.create_session()


@pytest.mark.asyncio
async def test_agent_status_fails_closed_without_server_grok_subscription(
    hermes_tenants,
    monkeypatch,
):
    _tmp_path, alice, _bob = hermes_tenants
    tenant = HermesTenantRegistry().resolve(alice)
    monkeypatch.setattr(settings, "ai_access_mode", "self_hosted")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"gateway must not be contacted: {request.url}")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://hermes.test",
    ) as client:
        status = await HermesAgentAdapter(
            HermesConnectionSettings.from_tenant(tenant),
            client=client,
        ).status()

    assert status["connected"] is False
    assert status["model_source"] == "server_grok_subscription"
    assert status["model_subscription_active"] is False
    assert status["message"] == "服务器统一 Grok 订阅当前不可用"


@pytest.mark.asyncio
async def test_data_module_forwards_profile_and_profile_specific_key(hermes_tenants):
    _tmp_path, alice, _bob = hermes_tenants
    tenant = HermesTenantRegistry().resolve(alice)
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["profile"] = request.headers.get("x-one-trading-hermes-profile", "")
        captured["key"] = request.headers.get("x-one-trading-hermes-data-key", "")
        return httpx.Response(200, json={"ok": True}, request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://one-trading.test",
    ) as client:
        result = await UserConsoleDataModule(
            api_key=tenant.data_key,
            profile=tenant.profile,
            client=client,
        ).query("capabilities")

    assert result["data"] == {"ok": True}
    assert captured == {"profile": tenant.profile, "key": tenant.data_key}


def test_backtest_job_identity_includes_user_id():
    from app.api.backtest import _make_job_key

    params = dict(
        strategy_id="demo",
        symbols="600519.SH",
        start="2026-01-01",
        end="2026-02-01",
        matching="open_t+1",
        entry_fill=None,
        exit_fill=None,
        fees_pct=0.0002,
        slippage_bps=5.0,
        max_positions=10,
        max_exposure_pct=1.0,
        initial_capital=1_000_000.0,
        position_sizing="equal",
        params=None,
        overrides=None,
    )
    assert _make_job_key("usr_alice", **params) != _make_job_key("usr_bob", **params)
