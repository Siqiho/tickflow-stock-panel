"""Production wiring for the one-trading managed Hermes multiplex gateway."""

from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml

_API_SERVER_KEY = "API_SERVER_KEY"
_FORBIDDEN_MODEL_KEYS = {
    "AI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GROK_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "XAI_API_KEY",
}
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_REQUIRED_DISABLED_TOOLSETS = ("bfl",)


class HermesRuntimeConfigError(RuntimeError):
    """The managed gateway root is missing or violates the isolation contract."""


@dataclass(frozen=True)
class HermesGatewayRuntime:
    root: Path
    base_url: str
    host: str
    port: int
    api_key: str


def _write_exclusive(path: Path, content: str, *, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _parse_gateway_url(base_url: str) -> tuple[str, int]:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "http"
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise HermesRuntimeConfigError("Hermes 网关地址必须是无凭据的本机 HTTP 根地址")
    host = parsed.hostname or ""
    if host not in _LOOPBACK_HOSTS:
        raise HermesRuntimeConfigError("Hermes 多 Profile 网关只能监听本机回环地址")
    try:
        port = parsed.port
    except ValueError as exc:
        raise HermesRuntimeConfigError("Hermes 网关端口无效") from exc
    if port is None or not 1 <= port <= 65535:
        raise HermesRuntimeConfigError("Hermes 网关必须使用明确的有效端口")
    return host, port


def _validate_api_key(values: Mapping[str, str]) -> str:
    forbidden = sorted(key for key in _FORBIDDEN_MODEL_KEYS if values.get(key))
    if forbidden:
        raise HermesRuntimeConfigError("Hermes 根目录不得保存上游模型凭据: " + ", ".join(forbidden))
    api_key = values.get(_API_SERVER_KEY, "")
    if len(api_key) < 32 or any(character.isspace() for character in api_key):
        raise HermesRuntimeConfigError("Hermes 根 API_SERVER_KEY 缺失或强度不足")
    return api_key


def _expected_config(host: str, port: int, api_key: str) -> dict:
    return {
        "_config_version": 33,
        "agent": {"disabled_toolsets": list(_REQUIRED_DISABLED_TOOLSETS)},
        "gateway": {
            "multiplex_profiles": True,
            "api_server": {
                "enabled": True,
                "host": host,
                "port": port,
                "key": api_key,
            },
            "platforms": {"api_server": {"enabled": True}},
        },
        "platform_toolsets": {"api_server": []},
    }


def _validate_config(
    config: object,
    host: str,
    port: int,
    api_key: str,
    *,
    require_hardening: bool = True,
) -> None:
    if not isinstance(config, dict):
        raise HermesRuntimeConfigError("Hermes 根配置不是有效对象")
    gateway = config.get("gateway")
    if not isinstance(gateway, dict) or gateway.get("multiplex_profiles") is not True:
        raise HermesRuntimeConfigError("Hermes 根配置必须启用 multiplex_profiles")
    api_server = gateway.get("api_server")
    if not isinstance(api_server, dict) or api_server.get("enabled") is not True:
        raise HermesRuntimeConfigError("Hermes 根 API listener 未启用")
    if api_server.get("host") != host or api_server.get("port") != port:
        raise HermesRuntimeConfigError("Hermes 根 API listener 与内部地址不一致")
    if api_server.get("key") != api_key:
        raise HermesRuntimeConfigError("Hermes 根配置与 .env 的 API key 不一致")
    platforms = gateway.get("platforms")
    api_platform = platforms.get("api_server") if isinstance(platforms, dict) else None
    if not isinstance(api_platform, dict) or api_platform.get("enabled") is not True:
        raise HermesRuntimeConfigError("Hermes API platform 未启用")
    if config.get("providers"):
        raise HermesRuntimeConfigError("Hermes 根配置不得选择上游模型 Provider")
    if require_hardening:
        agent = config.get("agent")
        disabled = agent.get("disabled_toolsets") if isinstance(agent, dict) else None
        if not isinstance(disabled, list) or not set(_REQUIRED_DISABLED_TOOLSETS).issubset(
            {str(value) for value in disabled}
        ):
            raise HermesRuntimeConfigError("Hermes 根配置未禁用非授权外部工具集")


def _harden_managed_config(config: dict) -> bool:
    agent = config.get("agent")
    if agent is None:
        agent = {}
        config["agent"] = agent
    if not isinstance(agent, dict):
        raise HermesRuntimeConfigError("Hermes 根 agent 配置无效")
    disabled = agent.get("disabled_toolsets")
    if disabled is None:
        disabled = []
    if not isinstance(disabled, list) or not all(isinstance(value, str) for value in disabled):
        raise HermesRuntimeConfigError("Hermes 根 disabled_toolsets 配置无效")
    merged = list(dict.fromkeys([*disabled, *_REQUIRED_DISABLED_TOOLSETS]))
    if merged == disabled:
        return False
    agent["disabled_toolsets"] = merged
    return True


def _replace_private_yaml(path: Path, config: dict) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    content = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    try:
        _write_exclusive(temporary, content)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def prepare_gateway_root(
    root: str | Path | None = None,
    base_url: str | None = None,
) -> HermesGatewayRuntime:
    """Create or validate one deployment-owned, loopback-only multiplex root."""
    root_path = Path(
        root or os.getenv("ONE_TRADING_HERMES_ROOT") or "/app/data/hermes"
    ).expanduser()
    base = (base_url or os.getenv("ONE_TRADING_HERMES_BASE_URL") or "http://127.0.0.1:8650").rstrip(
        "/"
    )
    host, port = _parse_gateway_url(base)

    if root_path.is_symlink():
        raise HermesRuntimeConfigError("Hermes 根目录不能是符号链接")
    root_path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root_path, 0o700)
    profiles = root_path / "profiles"
    if profiles.is_symlink():
        raise HermesRuntimeConfigError("Hermes Profiles 目录不能是符号链接")
    profiles.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(profiles, 0o700)

    env_path = root_path / ".env"
    if env_path.is_symlink():
        raise HermesRuntimeConfigError("Hermes 根凭据文件不能是符号链接")
    if not env_path.exists():
        with suppress(FileExistsError):
            _write_exclusive(env_path, f"{_API_SERVER_KEY}={secrets.token_hex(32)}\n")
    values = _read_env(env_path)
    api_key = _validate_api_key(values)
    os.chmod(env_path, 0o600)

    config_path = root_path / "config.yaml"
    if config_path.is_symlink():
        raise HermesRuntimeConfigError("Hermes 根配置文件不能是符号链接")
    if not config_path.exists():
        content = yaml.safe_dump(
            _expected_config(host, port, api_key),
            allow_unicode=True,
            sort_keys=False,
        )
        with suppress(FileExistsError):
            _write_exclusive(config_path, content)
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise HermesRuntimeConfigError("无法读取 Hermes 根配置") from exc
    _validate_config(config, host, port, api_key, require_hardening=False)
    if _harden_managed_config(config):
        _replace_private_yaml(config_path, config)
    _validate_config(config, host, port, api_key)
    os.chmod(config_path, 0o600)

    return HermesGatewayRuntime(
        root=root_path,
        base_url=base,
        host=host,
        port=port,
        api_key=api_key,
    )


def runtime_enabled(env: Mapping[str, str] | None = None) -> bool:
    values = env or os.environ
    return values.get("ONE_TRADING_HERMES_RUNTIME_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def application_command(env: Mapping[str, str] | None = None) -> list[str]:
    values = env or os.environ
    port = values.get("PORT", "3018")
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise HermesRuntimeConfigError("应用 PORT 无效")
    uvicorn = values.get("ONE_TRADING_UVICORN_BIN", "/app/.venv/bin/uvicorn")
    return [uvicorn, "app.main:app", "--host", "0.0.0.0", "--port", port]


def gateway_command(env: Mapping[str, str] | None = None) -> list[str]:
    values = env or os.environ
    entrypoint = values.get("ONE_TRADING_HERMES_RUNTIME_ENTRYPOINT", "").strip()
    if entrypoint:
        python = values.get("ONE_TRADING_HERMES_PYTHON", "").strip()
        if not python:
            raise HermesRuntimeConfigError("Hermes Runtime entrypoint 需要明确的 Python")
        return [python, entrypoint, "gateway", "run"]
    executable = values.get("HERMES_RUNTIME_BIN", "/opt/hermes/venv/bin/hermes")
    return [executable, "gateway", "run"]


_RUNTIME_ENTRYPOINT = (
    Path(__file__).resolve().parents[2] / "scripts" / "hermes_one_trading_runtime.py"
)
_GATEWAY_LOCK = "gateway.lock"


def managed_gateway_root(data_dir: Path) -> Path:
    return Path(data_dir).expanduser().resolve() / "hermes"


def probe_gateway_health(base_url: str, timeout: float = 1.0) -> bool:
    url = base_url.rstrip("/") + "/health"
    try:
        with urllib.request.urlopen(url, timeout=max(0.2, timeout)) as response:
            return int(getattr(response, "status", 0) or 0) == 200
    except (OSError, urllib.error.URLError, ValueError):
        return False


def read_gateway_lock_pid(root: Path) -> int | None:
    lock_path = Path(root) / _GATEWAY_LOCK
    try:
        payload = lock_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        pid = int((json.loads(payload) or {}).get("pid") or 0)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    return pid if pid > 0 else None


def pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def terminate_process_group(process: subprocess.Popen, timeout: float = 15.0) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        process.terminate()
    deadline = time.monotonic() + timeout
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.1)
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
        process.wait(timeout=5)


def wait_for_gateway_health(
    base_url: str,
    *,
    process: subprocess.Popen | None = None,
    timeout: float = 45.0,
) -> None:
    deadline = time.monotonic() + max(5.0, timeout)
    last_error = "not ready"
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise HermesRuntimeConfigError(
                f"Hermes multiplex gateway exited during startup ({process.returncode})"
            )
        if probe_gateway_health(base_url):
            return
        last_error = "health check failed"
        time.sleep(0.25)
    raise HermesRuntimeConfigError(f"Hermes multiplex gateway did not become ready: {last_error}")


def local_gateway_capability() -> dict:
    from app.config import settings

    enabled = bool(settings.hermes_runtime_enabled and settings.hermes_multiuser_enabled)
    try:
        host, _port = _parse_gateway_url(settings.hermes_gateway_base_url)
        loopback = host in _LOOPBACK_HOSTS
    except HermesRuntimeConfigError:
        host = ""
        loopback = False
    managed_root = False
    try:
        managed_root = settings.hermes_profiles_root.resolve() == managed_gateway_root(
            settings.data_dir
        )
    except OSError:
        managed_root = False
    running = enabled and loopback and probe_gateway_health(settings.hermes_gateway_base_url)
    startable = enabled and loopback and managed_root and not running
    return {
        "gateway_kind": "managed_local"
        if (enabled and loopback and managed_root)
        else "unavailable",
        "gateway_running": running,
        "gateway_startable": startable,
        "can_start_gateway": False,
        "base_url": settings.hermes_gateway_base_url,
    }


def _spawn_managed_gateway() -> tuple[subprocess.Popen, HermesGatewayRuntime]:
    from app.config import settings

    if not settings.hermes_runtime_enabled:
        raise HermesRuntimeConfigError("本地 Hermes Runtime 尚未启用")
    if not settings.hermes_multiuser_enabled:
        raise HermesRuntimeConfigError("多用户 Hermes 功能开关尚未启用")
    expected_root = managed_gateway_root(settings.data_dir)
    if settings.hermes_profiles_root.resolve() != expected_root:
        raise HermesRuntimeConfigError("只能启动项目受管 data/hermes 内部网关")
    runtime = prepare_gateway_root(
        settings.hermes_profiles_root,
        settings.hermes_gateway_base_url,
    )
    environment = {
        **os.environ,
        "HERMES_HOME": str(runtime.root),
        "HERMES_ACCEPT_HOOKS": "1",
        "PYTHONUNBUFFERED": "1",
    }
    runtime_bin = settings.hermes_runtime_bin.strip() or str(
        settings.hermes_python.with_name("hermes")
    )
    command = gateway_command(
        {
            **environment,
            "HERMES_RUNTIME_BIN": runtime_bin,
            "ONE_TRADING_HERMES_PYTHON": str(settings.hermes_python),
            "ONE_TRADING_HERMES_RUNTIME_ENTRYPOINT": str(_RUNTIME_ENTRYPOINT),
        }
    )
    executable = Path(command[0]).expanduser().absolute()
    working_directory = (
        Path(
            settings.hermes_runtime_cwd.strip()
            or environment.get("HERMES_RUNTIME_CWD")
            or executable.parents[2]
        )
        .expanduser()
        .resolve()
    )
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise HermesRuntimeConfigError(f"Hermes runtime 不可执行: {executable}")
    if not working_directory.is_dir():
        raise HermesRuntimeConfigError(f"Hermes runtime 目录不存在: {working_directory}")
    process = subprocess.Popen(
        [str(executable), *command[1:]],
        cwd=working_directory,
        env={
            **environment,
            "HERMES_RUNTIME_BIN": str(executable),
            "HERMES_RUNTIME_CWD": str(working_directory),
            "ONE_TRADING_HERMES_PYTHON": str(settings.hermes_python),
            "ONE_TRADING_HERMES_RUNTIME_ENTRYPOINT": str(_RUNTIME_ENTRYPOINT),
        },
        start_new_session=True,
    )
    return process, runtime


def start_managed_gateway(*, timeout: float | None = None) -> dict:
    """Start the project-owned loopback multiplex gateway if it is down."""
    from app.config import settings

    capability = local_gateway_capability()
    if capability["gateway_kind"] != "managed_local":
        raise HermesRuntimeConfigError("当前运行面不能从控制台启动内部网关")
    if probe_gateway_health(settings.hermes_gateway_base_url):
        return {
            "ok": True,
            "started": False,
            "already_running": True,
            "pid": read_gateway_lock_pid(settings.hermes_profiles_root),
            "base_url": settings.hermes_gateway_base_url,
            "message": "内部网关已在运行",
        }
    existing_pid = read_gateway_lock_pid(settings.hermes_profiles_root)
    wait_timeout = float(
        timeout
        if timeout is not None
        else os.getenv("ONE_TRADING_HERMES_STARTUP_TIMEOUT_SECONDS", "45")
    )
    if existing_pid and pid_is_alive(existing_pid):
        wait_for_gateway_health(settings.hermes_gateway_base_url, timeout=wait_timeout)
        return {
            "ok": True,
            "started": False,
            "already_running": True,
            "pid": existing_pid,
            "base_url": settings.hermes_gateway_base_url,
            "message": "内部网关已在运行",
        }
    process, runtime = _spawn_managed_gateway()
    try:
        wait_for_gateway_health(runtime.base_url, process=process, timeout=wait_timeout)
    except Exception:
        terminate_process_group(process)
        raise
    return {
        "ok": True,
        "started": True,
        "already_running": False,
        "pid": process.pid,
        "base_url": runtime.base_url,
        "message": "内部网关已启动",
    }


def run_supervised_gateway() -> int:
    """Foreground supervisor used by local `dev.sh`."""
    process, runtime = _spawn_managed_gateway()
    received_signal = [0]

    def receive_signal(signum: int, _frame) -> None:
        received_signal[0] = signum

    signal.signal(signal.SIGTERM, receive_signal)
    signal.signal(signal.SIGINT, receive_signal)
    print(
        f"starting one-trading Hermes multiplex gateway at {runtime.base_url} "
        f"with root {runtime.root}",
        flush=True,
    )
    try:
        wait_for_gateway_health(
            runtime.base_url,
            process=process,
            timeout=float(os.getenv("ONE_TRADING_HERMES_STARTUP_TIMEOUT_SECONDS", "45")),
        )
        print("one-trading Hermes multiplex gateway is ready", flush=True)
        while not received_signal[0]:
            return_code = process.poll()
            if return_code is not None:
                return return_code or 1
            time.sleep(0.25)
        return 128 + received_signal[0]
    finally:
        terminate_process_group(process)
