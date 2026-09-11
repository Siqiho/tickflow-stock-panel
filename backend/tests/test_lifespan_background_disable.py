"""ONE_TRADING_DISABLE_BACKGROUND 必须覆盖实际 lifespan 注册/启动的后台任务。

字段存在不够。本文件直接调用 app.main.lifespan。
行情探测 / TickFlow client 是外部边界, 必须 mock 且不得实调。
不把 QuoteService / daily_pipeline / Depth / pull / financial / minute 换成常量假模块;
只 spy 它们的 start/boot 入口, 断言真实 lifespan 有没有调用。
ensure_builtin_presets 只写本地 config、不拉网, 允许真实执行。
monitor engine 在两种模式下都会装入, 不是 watcher 线程。
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.tickflow.capabilities import CapabilitySet


def _fake_app() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace())


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setattr("app.secrets_store.get_tickflow_key", lambda: "")
    monkeypatch.setattr(
        "app.tickflow.policy.detect_capabilities",
        lambda force=False: CapabilitySet(),
    )
    monkeypatch.setattr(
        "app.tickflow.client.get_client",
        MagicMock(side_effect=AssertionError("must not call TickFlow")),
    )
    monkeypatch.setattr(
        "app.tickflow.client.get_async_client",
        MagicMock(side_effect=AssertionError("must not call TickFlow async")),
    )
    return data_dir


def _spy_background_starts(monkeypatch):
    from app.jobs import daily_pipeline
    from app.services import financial_sync, ext_pull
    from app.services.quote_service import QuoteService
    from app.services.depth_service import DepthService
    from app.services.minute_refresh import MinuteRefreshService

    spies = {
        "quote_boot": MagicMock(),
        "daily_start": MagicMock(return_value=SimpleNamespace(shutdown=MagicMock())),
        "depth_boot": MagicMock(),
        "depth_poll": MagicMock(),
        "pull_start": MagicMock(),
        "pull_refresh": MagicMock(),
        "financial_start": MagicMock(),
        "minute_start": MagicMock(),
    }
    monkeypatch.setattr(QuoteService, "boot_check", spies["quote_boot"])
    monkeypatch.setattr(daily_pipeline, "start_scheduler", spies["daily_start"])
    monkeypatch.setattr(DepthService, "boot_check", spies["depth_boot"])
    monkeypatch.setattr(DepthService, "start_polling", spies["depth_poll"])
    monkeypatch.setattr(ext_pull.pull_scheduler, "start", spies["pull_start"])
    monkeypatch.setattr(ext_pull.pull_scheduler, "refresh", spies["pull_refresh"])
    monkeypatch.setattr(financial_sync.financial_scheduler, "start", spies["financial_start"])
    monkeypatch.setattr(MinuteRefreshService, "start", spies["minute_start"])
    return spies


@pytest.mark.asyncio
async def test_lifespan_disable_flag_skips_registered_background_starts(isolated_settings, monkeypatch):
    monkeypatch.setenv("ONE_TRADING_DISABLE_BACKGROUND", "1")
    os.environ["ONE_TRADING_DISABLE_BACKGROUND"] = "1"

    from app.main import lifespan

    spies = _spy_background_starts(monkeypatch)
    app = _fake_app()
    async with lifespan(app):
        assert app.state.scheduler is None
        assert getattr(app.state, "monitor_engine", None) is not None

    spies["quote_boot"].assert_not_called()
    spies["daily_start"].assert_not_called()
    spies["depth_boot"].assert_not_called()
    spies["depth_poll"].assert_not_called()
    spies["pull_start"].assert_not_called()
    spies["pull_refresh"].assert_not_called()
    spies["financial_start"].assert_not_called()
    spies["minute_start"].assert_not_called()


@pytest.mark.asyncio
async def test_lifespan_normal_mode_registers_expected_background_tasks(isolated_settings, monkeypatch):
    monkeypatch.delenv("ONE_TRADING_DISABLE_BACKGROUND", raising=False)
    os.environ.pop("ONE_TRADING_DISABLE_BACKGROUND", None)

    from app.main import lifespan

    spies = _spy_background_starts(monkeypatch)
    app = _fake_app()
    async with lifespan(app):
        spies["quote_boot"].assert_called_once()
        spies["daily_start"].assert_called_once()
        spies["depth_boot"].assert_called_once()
        spies["depth_poll"].assert_called_once()
        spies["pull_start"].assert_called_once()
        spies["pull_refresh"].assert_called_once()
        spies["financial_start"].assert_called_once()
        spies["minute_start"].assert_called_once()
        assert app.state.scheduler is not None
        assert getattr(app.state, "monitor_engine", None) is not None
