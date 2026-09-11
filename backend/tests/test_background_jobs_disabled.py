"""Fixture seam: ONE_TRADING_DISABLE_BACKGROUND must opt in; default stays on."""
from __future__ import annotations

import pytest

import app.config as config


def test_background_jobs_default_enabled(monkeypatch):
    monkeypatch.delenv("ONE_TRADING_DISABLE_BACKGROUND", raising=False)
    assert config.background_jobs_disabled() is False


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_background_jobs_opt_in(monkeypatch, value):
    monkeypatch.setenv("ONE_TRADING_DISABLE_BACKGROUND", value)
    assert config.background_jobs_disabled() is True


def test_background_jobs_rejects_random_values(monkeypatch):
    monkeypatch.setenv("ONE_TRADING_DISABLE_BACKGROUND", "maybe")
    assert config.background_jobs_disabled() is False
