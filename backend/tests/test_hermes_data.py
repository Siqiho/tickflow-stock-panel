from __future__ import annotations

import httpx
import pytest

from app.services.user_console_data import (
    USER_CONSOLE_DATA_VIEWS,
    UserConsoleDataError,
    UserConsoleDataModule,
    is_user_console_read_path,
)


def test_catalog_covers_user_data_domains_and_excludes_account_mutations():
    module = UserConsoleDataModule(api_key="test-key", profile="ot-test")
    catalog = module.catalog()
    detailed_views = [
        view for domain in catalog["domains"] for view in module.catalog(domain=domain)["views"]
    ]
    view_ids = {view["id"] for view in detailed_views}

    assert catalog["mode"] == "read-only"
    assert catalog["views"] == []
    assert catalog["result_count"] == 0
    assert catalog["view_count"] == len(USER_CONSOLE_DATA_VIEWS)
    assert sum(catalog["domain_counts"].values()) == len(USER_CONSOLE_DATA_VIEWS)
    assert len(USER_CONSOLE_DATA_VIEWS) >= 60
    assert {
        "market_overview",
        "watchlist_enriched",
        "stock_daily",
        "stock_daily_analysis",
        "financial_metrics",
        "strategy_list",
        "alerts",
        "data_catalog",
        "ext_data_rows",
        "analysis_history",
        "analysis_history_report",
        "review_reports",
        "valuation_daily",
        "limit_up_events",
        "index_membership_history",
        "corporate_actions",
    }.issubset(view_ids)
    assert not {"accounts", "positions", "orders", "trading_actions"} & view_ids
    assert "stock_margin_trading" in view_ids  # 融资融券是用户台只读市场数据, 不是交易动作。


def test_internal_read_path_is_exact_and_never_authorizes_settings_or_mutations():
    assert is_user_console_read_path("/api/kline/daily") is True
    assert is_user_console_read_path("/api/overview/data-readiness") is True
    assert is_user_console_read_path("/api/data/status") is False
    assert is_user_console_read_path("/api/strategies/trend/source") is True
    assert is_user_console_read_path("/api/ai-history/reports/stock/sar_123") is True
    assert is_user_console_read_path("/api/ai-history/reports/stock") is False
    assert is_user_console_read_path("/api/ai-history/reports/stock/sar_123/extra") is False
    assert is_user_console_read_path("/api/settings") is False
    assert is_user_console_read_path("/api/backtest/run") is False
    assert is_user_console_read_path("/api/intraday/refresh") is False
    assert is_user_console_read_path("/api/trading/orders") is False


async def test_query_validates_params_redacts_secrets_and_budgets_lists():
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        captured["key"] = request.headers.get("x-one-trading-hermes-data-key")
        captured["profile"] = request.headers.get("x-one-trading-hermes-profile")
        return httpx.Response(
            200,
            json={
                "rules": [
                    {"id": "safe", "webhook_url": "https://secret.invalid/hook"},
                    {"id": "second"},
                    {"id": "third"},
                ],
                "api_key": "must-not-leak",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test")
    module = UserConsoleDataModule(api_key="local-key", profile="ot-test", client=client)

    result = await module.query("alerts", {"days": 5, "limit": 9999}, max_items=2)
    await client.aclose()

    assert captured == {
        "path": "/api/alerts",
        "query": {"days": "5", "limit": "500"},
        "key": "local-key",
        "profile": "ot-test",
    }
    assert len(result["data"]["rules"]) == 2
    assert result["data"]["rules"][0]["webhook_url"] == "<redacted>"
    assert result["data"]["api_key"] == "<redacted>"
    assert "$.rules" in result["truncated"]
    assert "$.api_key" in result["redacted"]


async def test_query_renders_path_params_and_rejects_unknown_or_missing_params():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"path": request.url.path})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test")
    module = UserConsoleDataModule(api_key="local-key", profile="ot-test", client=client)

    result = await module.query("stock_f10", {"symbol": "600519.SH"})
    assert result["data"]["path"] == "/api/free/f10/600519.SH"

    with pytest.raises(UserConsoleDataError, match="缺少参数"):
        await module.query("stock_f10", {})
    with pytest.raises(UserConsoleDataError, match="不接受参数"):
        await module.query("stock_f10", {"symbol": "600519.SH", "refresh": True})
    with pytest.raises(UserConsoleDataError, match="未知用户台数据视图"):
        await module.query("trading_orders", {})

    await client.aclose()


def test_bearer_and_internal_key_use_the_same_profile_scoped_secret():
    module = UserConsoleDataModule(api_key="local-key", profile="ot-test")

    assert module.authorization_is_valid("Bearer local-key") is True
    assert module.authorization_is_valid("Bearer wrong") is False
    assert module.internal_key_is_valid("local-key") is True
    assert module.internal_key_is_valid("wrong") is False

async def test_stock_daily_analysis_view_requires_symbol_and_rejects_wide_params():
    module = UserConsoleDataModule(api_key="local-key", profile="ot-test")

    with pytest.raises(UserConsoleDataError, match="缺少参数"):
        await module.query("stock_daily_analysis", {})
    with pytest.raises(UserConsoleDataError, match="不接受参数"):
        await module.query(
            "stock_daily_analysis",
            {"symbol": "300750.SZ", "ext_columns": "x.y", "start_date": "2026-01-01"},
        )
