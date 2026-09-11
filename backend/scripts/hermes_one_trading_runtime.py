#!/usr/bin/env python3
"""Hermes gateway entrypoint with Profile-scoped MCP discovery.

Hermes 0.20 performs its normal MCP discovery before a multiplexed Profile is
provisioned or selected.  one-trading creates Profiles lazily, so the API
Server must discover that Profile's uniquely named read-only MCP server before
it snapshots tools for the first Agent turn.
"""

from __future__ import annotations

import os
import sys
import threading
from importlib import import_module
from pathlib import Path

_runtime_cwd = os.getenv("HERMES_RUNTIME_CWD", "").strip()
if _runtime_cwd and _runtime_cwd not in sys.path:
    sys.path.insert(0, _runtime_cwd)

APIServerAdapter = import_module("gateway.platforms.api_server").APIServerAdapter
hermes_main = import_module("hermes_cli.main").main


def _route_process_mcp_metadata_to_runtime_root() -> None:
    """Keep process-global MCP metadata out of any tenant Profile."""
    root = Path(os.environ.get("HERMES_HOME") or "").expanduser()
    if not root.is_dir():
        return
    mcp_tool = import_module("tools.mcp_tool")
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_path = log_dir / "mcp-stderr.log"
    # Hermes intentionally holds this process-wide stderr fd for the gateway
    # lifetime; closing it here would break later MCP child redirection.
    handle = open(  # noqa: SIM115
        log_path,
        "a",
        encoding="utf-8",
        errors="replace",
        buffering=1,
    )
    os.chmod(log_path, 0o600)
    mcp_tool._mcp_stderr_log_fh = handle
    mcp_tool._MCP_DISCOVERY_LOCK_PATH = str(root / ".mcp-discovery.lock")


_route_process_mcp_metadata_to_runtime_root()

_discovery_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _discover_profile_mcp_tools() -> None:
    from hermes_constants import get_hermes_home
    from tools.mcp_tool import discover_mcp_tools

    profile_home = str(get_hermes_home())
    with _locks_guard:
        lock = _discovery_locks.setdefault(profile_home, threading.Lock())
    with lock:
        discover_mcp_tools()


_original_create_agent = APIServerAdapter._create_agent


def _create_agent_with_profile_mcp(self, *args, **kwargs):
    _discover_profile_mcp_tools()
    return _original_create_agent(self, *args, **kwargs)


APIServerAdapter._create_agent = _create_agent_with_profile_mcp


if __name__ == "__main__":
    sys.exit(hermes_main())
