from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
import yaml

from app.config import settings
from app.services import auth
from app.services.hermes_agent import HermesAgentAdapter, HermesAgentError, HermesConnectionSettings
from app.services.hermes_tenant import HermesTenantRegistry

HERMES_RUNTIME_BIN = os.getenv("HERMES_RUNTIME_BIN", "")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.skipif(not HERMES_RUNTIME_BIN, reason="set HERMES_RUNTIME_BIN for real multiplex check")
@pytest.mark.asyncio
async def test_real_gateway_keeps_two_accounts_in_different_profiles(tmp_path, monkeypatch):
    port = _free_port()
    runtime_bin = Path(HERMES_RUNTIME_BIN).expanduser().absolute()
    runtime_python = runtime_bin.with_name("python")
    bridge_requests: list[dict[str, object]] = []

    class BridgeHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            length = int(self.headers.get("content-length") or 0)
            raw_body = self.rfile.read(length)
            if not self.path.endswith("/responses"):
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            profile = self.path.split("/profiles/", 1)[1].split("/", 1)[0]
            payload = json.loads(raw_body or b"{}")
            tool_descriptions: dict[str, str] = {}
            for tool in payload.get("tools", []):
                if not isinstance(tool, dict):
                    continue
                function = tool.get("function") if isinstance(tool.get("function"), dict) else {}
                name = str(tool.get("name") or function.get("name") or "")
                if name:
                    tool_descriptions[name] = str(
                        tool.get("description") or function.get("description") or ""
                    )
            bridge_requests.append(
                {
                    "profile": profile,
                    "authorization": self.headers.get("authorization", ""),
                    "model": str(payload.get("model") or ""),
                    "tools": sorted(
                        tool_descriptions
                    ),
                    "tool_descriptions": tool_descriptions,
                }
            )
            answer = f"runtime-profile:{profile}"
            item = {
                "id": f"msg_{profile}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": answer,
                        "annotations": [],
                        "logprobs": [],
                    }
                ],
            }
            completed = {
                "id": f"resp_{profile}",
                "object": "response",
                "created_at": int(time.time()),
                "status": "completed",
                "error": None,
                "incomplete_details": None,
                "instructions": None,
                "max_output_tokens": None,
                "model": "grok-4.5",
                "output": [item],
                "parallel_tool_calls": True,
                "previous_response_id": None,
                "reasoning": {"effort": None, "summary": None},
                "store": False,
                "temperature": 1.0,
                "text": {"format": {"type": "text"}},
                "tool_choice": "auto",
                "tools": [],
                "top_p": 1.0,
                "truncation": "disabled",
                "usage": {
                    "input_tokens": 1,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 1,
                    "output_tokens_details": {"reasoning_tokens": 0},
                    "total_tokens": 2,
                },
                "metadata": {},
            }
            events = [
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {**item, "status": "in_progress", "content": []},
                },
                {
                    "type": "response.output_text.delta",
                    "item_id": item["id"],
                    "output_index": 0,
                    "content_index": 0,
                    "delta": answer,
                    "logprobs": [],
                },
                {"type": "response.output_item.done", "output_index": 0, "item": item},
                {"type": "response.completed", "response": completed},
            ]
            wire = "".join(
                f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
            ) + "data: [DONE]\n\n"
            encoded = wire.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, _format, *_args):
            return

    bridge = ThreadingHTTPServer(("127.0.0.1", 0), BridgeHandler)
    bridge_port = int(bridge.server_address[1])
    bridge_thread = threading.Thread(target=bridge.serve_forever, daemon=True)
    bridge_thread.start()
    root = tmp_path / "hermes"
    root.mkdir(parents=True)
    (root / ".env").write_text(f"API_SERVER_KEY={'a' * 64}\n", encoding="utf-8")
    (root / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "gateway": {
                    "multiplex_profiles": True,
                    "api_server": {
                        "enabled": True,
                        "host": "127.0.0.1",
                        "port": port,
                        "key": "a" * 64,
                    },
                    "platforms": {"api_server": {"enabled": True}},
                },
                "platform_toolsets": {"api_server": []},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "public_registration_enabled", True)
    monkeypatch.setattr(settings, "public_registration_daily_per_ip", 10)
    monkeypatch.setattr(settings, "public_max_users", 10)
    monkeypatch.setattr(settings, "hermes_multiuser_enabled", True)
    monkeypatch.setattr(settings, "hermes_profiles_root", root)
    monkeypatch.setattr(settings, "hermes_gateway_base_url", f"http://127.0.0.1:{port}")
    monkeypatch.setattr(settings, "ai_access_mode", "cloud_subscription")
    monkeypatch.setattr(settings, "ai_subscription_enabled", True)
    monkeypatch.setattr(settings, "ai_subscription_plan", "Grok 云订阅")
    monkeypatch.setattr(settings, "ai_provider", "xai")
    monkeypatch.setattr(settings, "ai_model", "grok-4.5")
    monkeypatch.setattr(settings, "ai_api_key", "server-grok-secret")
    monkeypatch.setattr(
        settings,
        "hermes_python",
        runtime_python,
    )
    monkeypatch.setattr(
        settings,
        "hermes_internal_base_url",
        f"http://127.0.0.1:{bridge_port}",
    )
    monkeypatch.setattr(auth, "_initialized_path", None)
    auth.set_password("owner-secret")
    alice, _ = auth.register_user("alice", "alice-secret", registration_source="alice")
    bob, _ = auth.register_user("bob", "bob-secret", registration_source="bob")
    registry = HermesTenantRegistry()
    alice_tenant = registry.resolve(alice)
    bob_tenant = registry.resolve(bob)

    environment = {
        **os.environ,
        "HERMES_HOME": str(root),
        "HERMES_ACCEPT_HOOKS": "1",
        "PYTHONUNBUFFERED": "1",
    }
    alice_profile_config = yaml.safe_load(
        (alice_tenant.profile_home / "config.yaml").read_text(encoding="utf-8")
    )
    runtime_entrypoint = Path(__file__).resolve().parents[1] / "scripts" / "hermes_one_trading_runtime.py"
    process = subprocess.Popen(
        [str(runtime_python), str(runtime_entrypoint), "gateway", "run"],
        cwd=str(runtime_bin.parents[2].resolve()),
        env={
            **environment,
            "HERMES_RUNTIME_CWD": str(runtime_bin.parents[2].resolve()),
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 25
        last_error = ""
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                pytest.fail(f"Hermes gateway exited early: {output[-4000:]}")
            try:
                response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)
                if response.status_code == 200:
                    break
                last_error = f"HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                last_error = type(exc).__name__
            await asyncio.sleep(0.2)
        else:
            pytest.fail(f"Hermes gateway did not become ready: {last_error}")

        alice_adapter = HermesAgentAdapter(HermesConnectionSettings.from_tenant(alice_tenant))
        bob_adapter = HermesAgentAdapter(HermesConnectionSettings.from_tenant(bob_tenant))
        alice_status = await alice_adapter.status()
        bob_status = await bob_adapter.status()
        assert alice_status["connected"] is True
        assert bob_status["connected"] is True
        assert alice_status["model_source"] == "server_grok_subscription"
        assert bob_status["model_source"] == "server_grok_subscription"
        assert alice_status["model"] == bob_status["model"] == "grok-4.5"

        alice_session = await alice_adapter.create_session("Alice only")
        bob_session = await bob_adapter.create_session("Bob only")
        assert alice_session["id"] != bob_session["id"]
        with pytest.raises(HermesAgentError):
            await bob_adapter.get_messages(alice_session["id"])

        alice_events = [
            event async for event in alice_adapter.stream_chat(alice_session["id"], "Alice")
        ]
        bob_events = [event async for event in bob_adapter.stream_chat(bob_session["id"], "Bob")]
        assert "".join(
            str(event.get("content") or "")
            for event in alice_events
            if event.get("type") == "delta"
        ) == f"runtime-profile:{alice_tenant.profile}", alice_events
        assert "".join(
            str(event.get("content") or "")
            for event in bob_events
            if event.get("type") == "delta"
        ) == f"runtime-profile:{bob_tenant.profile}", bob_events
        assert any(event.get("type") == "done" for event in alice_events), alice_events
        assert any(event.get("type") == "done" for event in bob_events), bob_events

        by_profile = {str(item["profile"]): item for item in bridge_requests}
        alice_request = by_profile[alice_tenant.profile]
        bob_request = by_profile[bob_tenant.profile]
        assert alice_request["authorization"] == f"Bearer {alice_tenant.bridge_key}"
        assert bob_request["authorization"] == f"Bearer {bob_tenant.bridge_key}"
        assert alice_request["model"] == bob_request["model"] == "grok-4.5"

        alice_server = next(iter(alice_profile_config["mcp_servers"]))
        bob_profile_config = yaml.safe_load(
            (bob_tenant.profile_home / "config.yaml").read_text(encoding="utf-8")
        )
        bob_server = next(iter(bob_profile_config["mcp_servers"]))
        alice_prefix = f"mcp__{alice_server.replace('-', '_')}__"
        bob_prefix = f"mcp__{bob_server.replace('-', '_')}__"
        alice_tools = {str(name) for name in alice_request["tools"]}
        bob_tools = {str(name) for name in bob_request["tools"]}
        assert "tool_search" in alice_tools
        assert "tool_search" in bob_tools
        alice_search = str(alice_request["tool_descriptions"]["tool_search"])
        bob_search = str(bob_request["tool_descriptions"]["tool_search"])
        assert alice_prefix in alice_search
        assert bob_prefix not in alice_search
        assert bob_prefix in bob_search
        assert alice_prefix not in bob_search
        assert "one_trading_data_catalog" in alice_search
        assert "one_trading_data_query" in alice_search
        assert "list_resources" not in alice_search
        assert "list_prompts" not in alice_search
        assert "one_trading_data_catalog" in bob_search
        assert "one_trading_data_query" in bob_search
        assert "list_resources" not in bob_search
        assert "list_prompts" not in bob_search
        assert (root / "logs" / "mcp-stderr.log").is_file()
        assert not (alice_tenant.profile_home / "logs" / "mcp-stderr.log").exists()
        assert not (bob_tenant.profile_home / "logs" / "mcp-stderr.log").exists()

        assert (alice_tenant.profile_home / "state.db").is_file()
        assert (bob_tenant.profile_home / "state.db").is_file()
        assert (alice_tenant.profile_home / "memory_store.db").is_file()
        assert (bob_tenant.profile_home / "memory_store.db").is_file()
        assert (alice_tenant.profile_home / "memory_store.db").resolve() != (
            bob_tenant.profile_home / "memory_store.db"
        ).resolve()
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        bridge.shutdown()
        bridge.server_close()
        bridge_thread.join(timeout=5)
        monkeypatch.setattr(auth, "_initialized_path", None)
