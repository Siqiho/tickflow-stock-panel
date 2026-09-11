from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from app.config import settings
from app.services import auth
from app.services.backtest_history import BacktestHistoryError, BacktestHistoryStore
from app.services.portfolio import PortfolioError, PortfolioWorkspace
from app.services.user_strategies import (
    UserStrategyCatalog,
    UserStrategyError,
    UserStrategyWorkspace,
)
from app.strategy.engine import StrategyEngine


@pytest.fixture
def accounts(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "public_registration_enabled", True)
    monkeypatch.setattr(settings, "public_registration_daily_per_ip", 10)
    monkeypatch.setattr(settings, "public_max_users", 10)
    monkeypatch.setattr(auth, "_initialized_path", None)
    auth.set_password("owner-secret")
    owner = auth.verify_credentials("owner-secret", "admin")
    assert owner is not None
    alice, _ = auth.register_user("alice", "alice-secret", registration_source="alice")
    bob, _ = auth.register_user("bob", "bob-secret", registration_source="bob")
    yield tmp_path, owner, alice, bob
    monkeypatch.setattr(auth, "_initialized_path", None)


def _strategy(strategy_id: str = "ai_alpha") -> dict:
    return {
        "id": strategy_id,
        "name": "站上均线",
        "description": "收盘价高于 MA20",
        "source": "ai",
        "direction": "long",
        "rules": "收盘价高于二十日均线",
        "logic": "all",
        "conditions": [{"left": "close", "op": ">", "right": "field:ma20"}],
        "basic_filter": {"enabled": False},
        "scoring": {"change_pct": 1},
        "entry_signals": [],
        "exit_signals": ["signal_ma20_breakdown"],
        "stop_loss": -0.05,
        "max_hold_days": 20,
        "order_by": "score",
        "descending": True,
        "limit": 100,
    }


def test_user_strategies_are_isolated_safe_and_admin_can_run_target(accounts):
    data_dir, owner, alice, bob = accounts
    alice_workspace = UserStrategyWorkspace(data_dir, alice)
    bob_workspace = UserStrategyWorkspace(data_dir, bob)
    alice_workspace.save(_strategy())

    assert [item["id"] for item in alice_workspace.list()] == ["ai_alpha"]
    assert bob_workspace.list() == []
    with pytest.raises(UserStrategyError, match="不接受可执行 Python"):
        bob_workspace.save_code("import os\nos.system('id')")

    frame = pl.DataFrame(
        {
            "symbol": ["600000.SH", "000001.SZ"],
            "date": [date(2026, 8, 11), date(2026, 8, 11)],
            "close": [12.0, 8.0],
            "ma20": [10.0, 9.0],
            "change_pct": [0.02, -0.01],
        }
    )
    shared = StrategyEngine(lambda _day: frame, strategy_dirs=[])
    admin_catalog = UserStrategyCatalog(shared, alice_workspace)
    result = admin_catalog.run("ai_alpha", date(2026, 8, 11))

    assert result.total == 1
    assert result.rows[0]["symbol"] == "600000.SH"
    assert not UserStrategyCatalog(shared, bob_workspace).has("ai_alpha")
    assert owner["role"] == "admin"


def test_portfolio_and_backtest_history_are_isolated_per_account(accounts):
    data_dir, _owner, alice, bob = accounts
    alice_portfolio = PortfolioWorkspace(data_dir, alice)
    bob_portfolio = PortfolioWorkspace(data_dir, bob)
    alice_portfolio.upsert(
        {"symbol": "600519.SH", "quantity": 100, "avg_cost": 1500, "note": "长期观察"}
    )

    assert alice_portfolio.list()[0]["symbol"] == "600519.SH"
    assert bob_portfolio.list() == []
    with pytest.raises(PortfolioError, match="格式"):
        bob_portfolio.upsert({"symbol": "../../owner", "quantity": 1, "avg_cost": 1})

    alice_history = BacktestHistoryStore(data_dir, alice)
    bob_history = BacktestHistoryStore(data_dir, bob)
    alice_history.save(
        {
            "run_id": "abcdef1234",
            "config": {"strategy_id": "ai_alpha", "start": "2026-01-01", "end": "2026-06-01"},
            "stats": {"total_return": 0.12, "total_trades": 3},
            "strategy_info": {"id": "ai_alpha", "name": "站上均线", "source": "ai"},
            "trades": [],
            "error": None,
        },
        strategy_owner_user_id=alice["id"],
    )

    assert alice_history.list()[0]["run_id"] == "abcdef1234"
    assert bob_history.list() == []
    with pytest.raises(BacktestHistoryError, match="不存在"):
        bob_history.get("abcdef1234")

