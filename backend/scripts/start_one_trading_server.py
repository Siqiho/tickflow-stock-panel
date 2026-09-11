#!/usr/bin/env python3
"""Run the FastAPI application and one internal Hermes multiplex gateway."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.services.hermes_runtime import (
    HermesRuntimeConfigError,
    application_command,
    gateway_command,
    prepare_gateway_root,
    runtime_enabled,
)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _terminate(process: subprocess.Popen, timeout: float = 20.0) -> None:
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


def _wait_for_gateway(
    process: subprocess.Popen,
    base_url: str,
    stop_signal: list[int],
) -> None:
    timeout = float(os.getenv("ONE_TRADING_HERMES_STARTUP_TIMEOUT_SECONDS", "45"))
    deadline = time.monotonic() + max(5.0, timeout)
    last_error = "not ready"
    while time.monotonic() < deadline and not stop_signal[0]:
        if process.poll() is not None:
            raise HermesRuntimeConfigError(
                f"Hermes multiplex gateway exited during startup ({process.returncode})"
            )
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=1) as response:
                if response.status == 200:
                    return
                last_error = f"HTTP {response.status}"
        except (OSError, urllib.error.URLError) as exc:
            last_error = type(exc).__name__
        time.sleep(0.25)
    if stop_signal[0]:
        raise KeyboardInterrupt
    raise HermesRuntimeConfigError(f"Hermes multiplex gateway did not become ready: {last_error}")


def main() -> int:
    environment = dict(os.environ)
    environment.setdefault(
        "ONE_TRADING_HERMES_RUNTIME_ENTRYPOINT",
        "/app/scripts/hermes_one_trading_runtime.py",
    )
    app_command = application_command(environment)
    if not runtime_enabled(environment):
        if _truthy(environment.get("ONE_TRADING_HERMES_MULTIUSER_ENABLED")):
            raise HermesRuntimeConfigError("Hermes 功能不能在网关运行时关闭时启用")
        os.execvpe(app_command[0], app_command, environment)
        return 127

    runtime = prepare_gateway_root()
    command = gateway_command(environment)
    executable = Path(command[0])
    working_directory = Path(environment.get("HERMES_RUNTIME_CWD", "/opt/hermes/src"))
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise HermesRuntimeConfigError(f"Hermes runtime 不可执行: {executable}")
    if not working_directory.is_dir():
        raise HermesRuntimeConfigError(f"Hermes runtime 目录不存在: {working_directory}")

    hermes_environment = {
        **environment,
        "HERMES_HOME": str(runtime.root),
        "HERMES_ACCEPT_HOOKS": "1",
        "PYTHONUNBUFFERED": "1",
    }
    received_signal = [0]

    def receive_signal(signum: int, _frame) -> None:
        received_signal[0] = signum

    signal.signal(signal.SIGTERM, receive_signal)
    signal.signal(signal.SIGINT, receive_signal)

    print(
        f"starting Hermes multiplex gateway at {runtime.base_url} "
        f"with persistent root {runtime.root}",
        flush=True,
    )
    hermes = subprocess.Popen(
        command,
        cwd=working_directory,
        env=hermes_environment,
        start_new_session=True,
    )
    app: subprocess.Popen | None = None
    try:
        _wait_for_gateway(hermes, runtime.base_url, received_signal)
        print("Hermes multiplex gateway is ready; starting one-trading", flush=True)
        app = subprocess.Popen(
            app_command,
            cwd="/app",
            env=environment,
            start_new_session=True,
        )
        while not received_signal[0]:
            if hermes.poll() is not None:
                print(f"Hermes gateway exited unexpectedly ({hermes.returncode})", file=sys.stderr)
                return hermes.returncode or 1
            if app.poll() is not None:
                print(f"one-trading exited unexpectedly ({app.returncode})", file=sys.stderr)
                return app.returncode or 1
            time.sleep(0.25)
        return 128 + received_signal[0]
    finally:
        if app is not None:
            _terminate(app)
        _terminate(hermes)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HermesRuntimeConfigError, ValueError) as exc:
        print(f"startup refused: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
