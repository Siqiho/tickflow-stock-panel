#!/usr/bin/env python3
"""Non-product verification launcher for restored official 3018.

This is NOT the daily-run command. Old one-trading has no process switch that
disables scheduler / ext_pull / depth / minute refresh / capability probe.
This wrapper monkeypatches those hooks before importing app.main, then serves
the official app from the official venv on 127.0.0.1:3018 with official DATA_DIR.

Differences vs daily run:
- start_scheduler / ext_pull / financial_scheduler / quote.boot_check /
  depth.boot_check+polling / minute_refresh.start are no-ops
- detect_capabilities is forced to cache-only (no TickFlow probe)
- ensure_builtin_presets and strategy-monitor migrate are no-ops
- AI / Hermes runtime env forced off for this process only; .env is not edited
- Authentication is unchanged
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path("/Users/simon/Trading/one-trading/backend")
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

# Process-level only. Do not set DATA_DIR (official data/). Do not clear TickFlow key.
os.environ["ONE_TRADING_HERMES_RUNTIME_ENABLED"] = "false"
os.environ["ONE_TRADING_HERMES_MULTIUSER_ENABLED"] = "false"
os.environ["AI_API_KEY"] = ""
os.environ["AI_86GAMESTORE_API_KEY"] = ""
os.environ["AI_SUBROUTER_API_KEY"] = ""


def _patch() -> None:
    import app.jobs.daily_pipeline as daily_pipeline

    daily_pipeline.start_scheduler = lambda *a, **k: None  # type: ignore[assignment]

    from app.services.quote_service import QuoteService

    QuoteService.boot_check = lambda self: None  # type: ignore[method-assign]

    from app.services.depth_service import DepthService

    DepthService.boot_check = lambda self: None  # type: ignore[method-assign]
    DepthService.start_polling = lambda self: None  # type: ignore[method-assign]

    from app.services.ext_pull import pull_scheduler

    pull_scheduler.start = lambda *a, **k: None  # type: ignore[assignment]
    pull_scheduler.refresh = lambda *a, **k: None  # type: ignore[assignment]

    from app.services.financial_sync import financial_scheduler

    financial_scheduler.start = lambda *a, **k: None  # type: ignore[assignment]

    import app.tickflow.policy as policy

    _orig = policy.detect_capabilities

    def _cache_only(force: bool = False):
        return _orig(force=False)

    policy.detect_capabilities = _cache_only  # type: ignore[assignment]

    import app.services.ext_presets as ext_presets

    async def _no_presets(_data_dir):
        return None

    ext_presets.ensure_builtin_presets = _no_presets  # type: ignore[assignment]

    import app.strategy.monitor_rules as mr_store

    mr_store.migrate_strategy_monitors = lambda *a, **k: None  # type: ignore[assignment]

    from app.services.minute_refresh import MinuteRefreshService

    MinuteRefreshService.start = lambda self: None  # type: ignore[method-assign]

    try:
        from app.services.wecom_bot_service import WecomBotService

        WecomBotService.boot_check = lambda self: None  # type: ignore[method-assign]
    except Exception:
        pass

    try:
        from app.services.mining_manager import MiningJobManager

        MiningJobManager.recover_interrupted = lambda self: 0  # type: ignore[method-assign]
    except Exception:
        pass


if __name__ == "__main__":
    _patch()
    import uvicorn
    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=3018, reload=False)
