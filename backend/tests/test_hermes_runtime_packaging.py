from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from app.config import Settings
from app.services.hermes_runtime import (
    HermesRuntimeConfigError,
    application_command,
    gateway_command,
    prepare_gateway_root,
)


def _mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_prepare_gateway_root_creates_a_stable_private_multiplex_root(tmp_path: Path) -> None:
    root = tmp_path / "hermes"

    first = prepare_gateway_root(root, "http://127.0.0.1:8650")
    second = prepare_gateway_root(root, "http://127.0.0.1:8650")

    assert first == second
    assert first.root == root
    assert first.host == "127.0.0.1"
    assert first.port == 8650
    assert len(first.api_key) == 64
    assert _mode(root) == 0o700
    assert _mode(root / "profiles") == 0o700
    assert _mode(root / ".env") == 0o600
    assert _mode(root / "config.yaml") == 0o600

    env_text = (root / ".env").read_text(encoding="utf-8")
    assert env_text == f"API_SERVER_KEY={first.api_key}\n"
    assert "AI_API_KEY" not in env_text
    assert "XAI_API_KEY" not in env_text

    config = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    assert config["gateway"]["multiplex_profiles"] is True
    assert config["gateway"]["api_server"] == {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 8650,
        "key": first.api_key,
    }
    assert config["gateway"]["platforms"]["api_server"]["enabled"] is True
    assert config["platform_toolsets"]["api_server"] == []
    assert config["agent"]["disabled_toolsets"] == ["bfl"]


def test_prepare_gateway_root_hardens_an_existing_managed_config(tmp_path: Path) -> None:
    root = tmp_path / "hermes"
    prepare_gateway_root(root, "http://127.0.0.1:8650")
    config_path = root / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config.pop("agent", None)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    prepare_gateway_root(root, "http://127.0.0.1:8650")

    hardened = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert hardened["agent"]["disabled_toolsets"] == ["bfl"]
    assert _mode(config_path) == 0o600


def test_prepare_gateway_root_rejects_upstream_credentials(tmp_path: Path) -> None:
    root = tmp_path / "hermes"
    root.mkdir(mode=0o700)
    (root / ".env").write_text(
        f"API_SERVER_KEY={'a' * 64}\nAI_API_KEY=must-not-live-here\n",
        encoding="utf-8",
    )

    with pytest.raises(HermesRuntimeConfigError, match="上游模型凭据"):
        prepare_gateway_root(root, "http://127.0.0.1:8650")


@pytest.mark.parametrize(
    ("multiplex", "host"),
    [(False, "127.0.0.1"), (True, "0.0.0.0")],
)
def test_prepare_gateway_root_rejects_an_unsafe_existing_listener(
    tmp_path: Path,
    multiplex: bool,
    host: str,
) -> None:
    root = tmp_path / "hermes"
    root.mkdir(mode=0o700)
    api_key = "b" * 64
    (root / ".env").write_text(f"API_SERVER_KEY={api_key}\n", encoding="utf-8")
    (root / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "gateway": {
                    "multiplex_profiles": multiplex,
                    "api_server": {
                        "enabled": True,
                        "host": host,
                        "port": 8650,
                        "key": api_key,
                    },
                    "platforms": {"api_server": {"enabled": True}},
                },
                "platform_toolsets": {"api_server": []},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(HermesRuntimeConfigError):
        prepare_gateway_root(root, "http://127.0.0.1:8650")


def test_runtime_commands_keep_hermes_internal_and_follow_zeabur_port() -> None:
    env = {
        "PORT": "8080",
        "HERMES_RUNTIME_BIN": "/opt/hermes/venv/bin/hermes",
    }

    assert application_command(env) == [
        "/app/.venv/bin/uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8080",
    ]
    assert gateway_command(env) == ["/opt/hermes/venv/bin/hermes", "gateway", "run"]
    assert gateway_command(
        {
            "ONE_TRADING_HERMES_PYTHON": "/opt/hermes/venv/bin/python",
            "ONE_TRADING_HERMES_RUNTIME_ENTRYPOINT": "/app/scripts/hermes_one_trading_runtime.py",
        }
    ) == [
        "/opt/hermes/venv/bin/python",
        "/app/scripts/hermes_one_trading_runtime.py",
        "gateway",
        "run",
    ]


def test_runtime_enabled_is_available_to_the_local_supervisor(monkeypatch) -> None:
    monkeypatch.setenv("ONE_TRADING_HERMES_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("HERMES_RUNTIME_BIN", "/tmp/hermes/bin/hermes")
    monkeypatch.setenv("HERMES_RUNTIME_CWD", "/tmp/hermes/src")
    local_settings = Settings(_env_file=None)
    assert local_settings.hermes_runtime_enabled is True
    assert local_settings.hermes_runtime_bin == "/tmp/hermes/bin/hermes"
    assert local_settings.hermes_runtime_cwd == "/tmp/hermes/src"


def test_release_dockerfile_pins_the_tested_runtime_and_persistent_root() -> None:
    project_root = Path(__file__).resolve().parents[2]
    dockerfile = (project_root / "Dockerfile.one-trading").read_text(encoding="utf-8")

    assert "91937a6dc3ffbbe2f3be91a500f0ecf962c4cf53" in dockerfile
    assert "/opt/hermes/src[mcp]" in dockerfile
    assert "aiohttp==3.14.1" in dockerfile
    assert "import aiohttp, mcp" in dockerfile
    assert "ONE_TRADING_HERMES_ROOT=/app/data/hermes" in dockerfile
    assert "ONE_TRADING_HERMES_PYTHON=/opt/hermes/venv/bin/python" in dockerfile
    assert "ONE_TRADING_HERMES_MULTIUSER_ENABLED=true" not in dockerfile
    assert "start_one_trading_server.py" in dockerfile
    assert "hermes_one_trading_runtime.py" in dockerfile
    assert os.fspath(project_root / "backend" / "scripts" / "hermes_user_console_mcp.py")


def test_local_dev_supervises_a_project_owned_multiplex_gateway() -> None:
    project_root = Path(__file__).resolve().parents[2]
    dev_script = (project_root / "dev.sh").read_text(encoding="utf-8")
    local_launcher = project_root / "backend" / "scripts" / "start_local_hermes_gateway.py"

    assert local_launcher.is_file()
    assert "start_local_hermes_gateway.py" in dev_script
    assert "ONE_TRADING_HERMES_RUNTIME_ENABLED" in dev_script
    assert "Hermes multiplex gateway 已就绪" in dev_script


def test_local_gateway_capability_only_allows_managed_loopback_root(tmp_path, monkeypatch) -> None:
    from app.config import settings
    from app.services.hermes_runtime import local_gateway_capability, start_managed_gateway

    monkeypatch.setattr(settings, "hermes_runtime_enabled", True)
    monkeypatch.setattr(settings, "hermes_multiuser_enabled", True)
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "hermes_profiles_root", tmp_path / "elsewhere")
    monkeypatch.setattr(settings, "hermes_gateway_base_url", "http://127.0.0.1:8651")
    monkeypatch.setattr(
        "app.services.hermes_runtime.probe_gateway_health", lambda *_args, **_kwargs: False
    )

    capability = local_gateway_capability()
    assert capability["gateway_kind"] == "unavailable"
    assert capability["gateway_startable"] is False

    monkeypatch.setattr(settings, "hermes_profiles_root", tmp_path / "data" / "hermes")
    capability = local_gateway_capability()
    assert capability["gateway_kind"] == "managed_local"
    assert capability["gateway_startable"] is True
    assert capability["can_start_gateway"] is False

    monkeypatch.setattr(
        "app.services.hermes_runtime.probe_gateway_health", lambda *_args, **_kwargs: True
    )
    result = start_managed_gateway()
    assert result["ok"] is True
    assert result["already_running"] is True
    assert result["started"] is False


def test_start_managed_gateway_spawns_once_when_health_is_down(tmp_path, monkeypatch) -> None:
    from app.config import settings
    from app.services.hermes_runtime import start_managed_gateway

    spawned: list[object] = []

    class FakeProcess:
        pid = 4242

        def poll(self):
            return None

    def fake_spawn():
        process = FakeProcess()
        spawned.append(process)
        runtime = type(
            "Runtime",
            (),
            {"base_url": "http://127.0.0.1:8651", "root": tmp_path / "data" / "hermes"},
        )()
        return process, runtime

    monkeypatch.setattr(settings, "hermes_runtime_enabled", True)
    monkeypatch.setattr(settings, "hermes_multiuser_enabled", True)
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "hermes_profiles_root", tmp_path / "data" / "hermes")
    monkeypatch.setattr(settings, "hermes_gateway_base_url", "http://127.0.0.1:8651")
    monkeypatch.setattr(
        "app.services.hermes_runtime.probe_gateway_health", lambda *_args, **_kwargs: False
    )
    monkeypatch.setattr(
        "app.services.hermes_runtime.read_gateway_lock_pid", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr("app.services.hermes_runtime._spawn_managed_gateway", fake_spawn)
    monkeypatch.setattr(
        "app.services.hermes_runtime.wait_for_gateway_health", lambda *_args, **_kwargs: None
    )

    result = start_managed_gateway()
    assert result["ok"] is True
    assert result["started"] is True
    assert result["pid"] == 4242
    assert len(spawned) == 1
