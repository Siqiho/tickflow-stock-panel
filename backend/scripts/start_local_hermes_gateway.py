#!/usr/bin/env python3
"""Run the project-owned local Hermes multiplex gateway.

The one-trading development server owns this child process through ``dev.sh``.
It intentionally uses a project data root and a dedicated loopback port, so it
never stops or adopts the user's existing personal Hermes profiles.
"""

from __future__ import annotations

import sys

from app.services.hermes_runtime import HermesRuntimeConfigError, run_supervised_gateway

if __name__ == "__main__":
    try:
        raise SystemExit(run_supervised_gateway())
    except (HermesRuntimeConfigError, ValueError) as exc:
        print(f"startup refused: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
