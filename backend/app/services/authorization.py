"""Role policy for the public multi-user server.

Shared market reads stay available to authenticated users. Global data,
provider, credential, scheduler, monitor, and runtime administration stays
owner-only. Regular-user mutations are deny-by-default and explicitly limited
to isolated personal state plus bounded analysis operations.
"""

from __future__ import annotations

from fastapi import HTTPException

_ADMIN_ONLY_PREFIXES = (
    "/api/admin",
    "/api/runtime-logs",
    "/api/data",
    "/api/pipeline",
    "/api/custom-sources",
    "/api/ext-data",
    "/api/monitor-rules",
    "/api/alerts",
    "/api/settings/endpoints",
    "/api/settings/ai",
)

_SHARED_MARKET_READ_PATHS = frozenset(
    {
        "/api/data/status",
        "/api/data/version",
        "/api/data/catalog",
    }
)

_SHARED_MARKET_READ_PREFIXES = (
    "/api/data/schema/",
    "/api/data/catalog/",
)

_PERSONAL_MUTATION_PREFIXES = (
    "/api/hermes-agent",
    "/api/portfolio",
    "/api/watchlist",
    "/api/stock-analysis/analyze",
    "/api/stock-analysis/reports",
    "/api/market-recap/analyze",
    "/api/market-recap/reports",
    "/api/financials/analyze",
    "/api/financials/reports",
    "/api/settings/onboarding/complete",
    "/api/settings/preferences/nav-order",
    "/api/settings/preferences/nav-hidden",
    "/api/settings/preferences/watchlist-columns",
    "/api/settings/preferences/screener-result-columns",
    "/api/settings/preferences/indices-nav-pinned",
    "/api/settings/preferences/realtime-monitor",
    "/api/news",
    "/api/analysis-menus",
    "/api/screener/run",
    "/api/screener/run_preset",
    "/api/backtest/run",
    "/api/backtest/factor/run",
    "/api/backtest/strategy/run",
    "/api/backtest/strategy/cancel",
    "/api/backtest/strategy/history/",
    "/api/strategies/config/",
    "/api/strategies/user/",
)

_PERSONAL_MUTATION_PATHS = frozenset(
    {
        "/api/strategies/run",
        "/api/strategies/run-all",
        "/api/strategies/config",
        "/api/strategies/build",
        "/api/strategies/ai/save",
    }
)


def require_request_access(user: dict, method: str, path: str) -> None:
    if user.get("role") == "admin":
        return
    if method.upper() in {"GET", "HEAD", "OPTIONS"} and (
        path in _SHARED_MARKET_READ_PATHS
        or any(path.startswith(prefix) for prefix in _SHARED_MARKET_READ_PREFIXES)
    ):
        # Catalog metadata and market-data readiness describe the one shared
        # server dataset. Control-plane reads and every mutation remain below
        # the administrator boundary.
        return
    if any(path.startswith(prefix) for prefix in _ADMIN_ONLY_PREFIXES):
        raise HTTPException(status_code=403, detail="此功能仅服务器管理员可用")
    if method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return
    if path in _PERSONAL_MUTATION_PATHS:
        return
    if path.startswith("/api/hermes-agent/gateway/"):
        raise HTTPException(status_code=403, detail="此功能仅服务器管理员可用")
    if any(path.startswith(prefix) for prefix in _PERSONAL_MUTATION_PREFIXES):
        return
    raise HTTPException(status_code=403, detail="普通用户无权修改服务器级配置或共享数据")
