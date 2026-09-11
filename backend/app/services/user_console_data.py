"""Deep read-only Module exposing user-console data to the Hermes Agent.

The external Interface is intentionally small: discover views, then query one
view.  Endpoint selection, parameter validation, auth, redaction, and output
budgeting stay inside this Module so Hermes never learns filesystem layout or
browser-session credentials.
"""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import quote

import httpx

from app.services.hermes_tenant import HermesTenantError, HermesTenantRegistry


class UserConsoleDataError(RuntimeError):
    """Credential-free failure at the Hermes user-console data seam."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class UserConsoleDataView:
    id: str
    domain: str
    description: str
    path: str
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    fixed_query: Mapping[str, str] = field(default_factory=dict)

    @property
    def parameters(self) -> list[dict[str, Any]]:
        path_names = set(_path_parameter_names(self.path))
        return [
            {
                "name": name,
                "required": name in self.required,
                "location": "path" if name in path_names else "query",
            }
            for name in (*self.required, *self.optional)
        ]


def _view(
    view_id: str,
    domain: str,
    description: str,
    path: str,
    *,
    required: tuple[str, ...] = (),
    optional: tuple[str, ...] = (),
    fixed_query: Mapping[str, str] | None = None,
) -> UserConsoleDataView:
    return UserConsoleDataView(
        id=view_id,
        domain=domain,
        description=description,
        path=path,
        required=required,
        optional=optional,
        fixed_query=fixed_query or {},
    )


# This is the authority for data visible to Hermes. Only GET surfaces belong
# here. Account/auth/settings/trading, mutation, sync, refresh, delete, report
# save, and external-action surfaces are deliberately absent.
USER_CONSOLE_DATA_VIEWS: tuple[UserConsoleDataView, ...] = (
    _view("capabilities", "system", "用户台当前可用能力与档位", "/api/capabilities"),
    _view(
        "data_status",
        "data",
        "共享日线与指标数据的可用日期范围",
        "/api/overview/data-readiness",
    ),
    _view("data_catalog", "data", "数据集目录、质量和服务状态", "/api/data/catalog"),
    _view(
        "data_catalog_dataset",
        "data",
        "单个数据集的目录详情",
        "/api/data/catalog/{dataset_id}",
        required=("dataset_id",),
    ),
    _view(
        "data_catalog_schema",
        "data",
        "单个数据集的字段契约",
        "/api/data/catalog/{dataset_id}/schema",
        required=("dataset_id",),
    ),
    _view(
        "data_runs",
        "data",
        "数据集运行与同步历史",
        "/api/data/runs",
        optional=("dataset_id",),
    ),
    _view("data_control_summary", "data", "数据质量与控制面汇总", "/api/data/control-summary"),
    _view(
        "data_provenance", "data", "数据来源、lineage 与生命周期证据", "/api/data/source-provenance"
    ),
    _view(
        "enriched_schema",
        "data",
        "用户台行情/指标表字段说明",
        "/api/data/schema/{table}",
        required=("table",),
    ),
    _view(
        "pipeline_jobs",
        "data",
        "最近的数据管道任务状态",
        "/api/pipeline/jobs",
        optional=("limit",),
    ),
    _view(
        "pipeline_job",
        "data",
        "指定数据管道任务详情",
        "/api/pipeline/jobs/{job_id}",
        required=("job_id",),
    ),
    _view("ext_data_catalog", "extended_data", "扩展数据配置与可用数据集", "/api/ext-data"),
    _view(
        "ext_data_schema_all", "extended_data", "全部扩展数据字段目录", "/api/ext-data/schema-all"
    ),
    _view(
        "ext_data_schema",
        "extended_data",
        "指定扩展数据的字段目录",
        "/api/ext-data/schema/{config_id}",
        required=("config_id",),
    ),
    _view(
        "ext_data_rows",
        "extended_data",
        "指定扩展数据的可见行",
        "/api/ext-data/{config_id}/rows",
        required=("config_id",),
        optional=("date", "columns", "limit"),
    ),
    _view(
        "market_overview",
        "market",
        "看板市场总览、指数、涨跌分布与强弱数据",
        "/api/overview/market",
        optional=("as_of",),
    ),
    _view(
        "market_pulse",
        "market",
        "市场脉搏与板块异动时间轴",
        "/api/market-pulse",
        optional=("trade_date",),
    ),
    _view("quote_status", "market", "实时行情服务状态与新鲜度", "/api/intraday/status"),
    _view(
        "index_quotes",
        "market",
        "核心或指定指数的当前行情",
        "/api/intraday/indices",
        optional=("symbols",),
    ),
    _view(
        "market_snapshot", "market", "最新全市场轻量行情与指标快照", "/api/screener/market-snapshot"
    ),
    _view(
        "rps_rotation",
        "market",
        "行业/概念相对强弱轮动",
        "/api/rps/rotation",
        optional=("days",),
    ),
    _view(
        "limit_ladder",
        "market",
        "连板梯队与涨停/跌停方向数据",
        "/api/screener/limit-ladder",
        optional=("as_of", "direction", "ext_columns"),
    ),
    _view(
        "fund_flow_boards",
        "market",
        "行业板块主力资金流排名",
        "/api/free/fund-flow/boards",
        optional=("top",),
    ),
    _view(
        "fund_flow_concepts",
        "market",
        "概念板块主力资金流排名",
        "/api/free/fund-flow/concepts",
        optional=("top",),
    ),
    _view(
        "fund_flow_board_history",
        "market",
        "指定行业或概念的资金流历史",
        "/api/free/fund-flow/board/{code}/history",
        required=("code",),
        optional=("kind", "limit"),
        fixed_query={"refresh": "false"},
    ),
    _view(
        "fund_flow_board_intraday",
        "market",
        "指定行业或概念的盘中资金流",
        "/api/free/fund-flow/board/{code}/intraday",
        required=("code",),
        optional=("kind", "trade_date"),
        fixed_query={"refresh": "false"},
    ),
    _view("stock_pools", "market", "用户台可见股票池目录", "/api/free/pools"),
    _view(
        "stock_pool",
        "market",
        "指定股票池成分",
        "/api/free/pools/{pool_id}",
        required=("pool_id",),
        fixed_query={"refresh": "false"},
    ),
    _view("data_quality_latest", "market", "最近一次公开行情质量结果", "/api/free/quality/latest"),
    _view(
        "instrument_search",
        "stock",
        "按代码或名称搜索股票",
        "/api/kline/instruments/search",
        optional=("q", "limit"),
    ),
    _view("watchlist", "stock", "当前自选股、备注与顺序", "/api/watchlist"),
    _view(
        "watchlist_enriched",
        "stock",
        "自选股行情、实时覆盖、指标、财务摘要与信号",
        "/api/watchlist/enriched",
        optional=("ext_columns",),
    ),
    _view(
        "stock_daily",
        "stock",
        "单股日 K、指标、信号、证券信息与行情快照覆盖",
        "/api/kline/daily",
        required=("symbol",),
        optional=("days", "start_date", "end_date", "ext_columns"),
    ),
    _view(
        "stock_daily_analysis",
        "stock",
        "单股分析用日 K 窄表,仅本地已有数据",
        "/api/stock-analysis/daily-window",
        required=("symbol",),
        optional=("days",),
    ),
    _view(
        "stock_minute",
        "stock",
        "单股指定交易日分钟 K",
        "/api/kline/minute",
        required=("symbol",),
        optional=("date",),
    ),
    _view(
        "stock_quotes",
        "stock",
        "指定股票的当前公开行情",
        "/api/free/quotes",
        required=("symbols",),
    ),
    _view(
        "stock_levels",
        "stock",
        "单股支撑、压力和关键价位",
        "/api/stock-analysis/levels",
        required=("symbol",),
        optional=("days",),
    ),
    _view(
        "stock_chips",
        "stock",
        "单股筹码分布近似",
        "/api/free/chips/{symbol}",
        required=("symbol",),
        optional=("days", "bins", "as_of"),
    ),
    _view(
        "stock_fund_flow",
        "stock",
        "单股主力资金流历史",
        "/api/free/fund-flow/stock/{symbol}",
        required=("symbol",),
        optional=("limit",),
    ),
    _view(
        "stock_f10",
        "stock",
        "单股 F10 摘要",
        "/api/free/f10/{symbol}",
        required=("symbol",),
    ),
    _view(
        "stock_margin_trading",
        "stock",
        "融资融券余额与交易历史",
        "/api/f10/margin-trading",
        optional=("symbol", "start_date", "end_date", "limit", "source"),
    ),
    _view(
        "stock_changes",
        "stock",
        "股票变动与事件数据",
        "/api/free/changes",
        optional=("date",),
    ),
    _view(
        "stock_adjustment_factor",
        "stock",
        "单股复权因子",
        "/api/free/adj-factor/{symbol}",
        required=("symbol",),
    ),
    _view(
        "stock_financial_snapshot",
        "stock",
        "单股公开财务摘要",
        "/api/free/financials/{symbol}",
        required=("symbol",),
        optional=("max_periods",),
    ),
    _view(
        "financial_status", "financial", "财务数据覆盖、报告期与同步状态", "/api/financials/status"
    ),
    _view(
        "financial_metrics",
        "financial",
        "核心财务指标",
        "/api/financials/metrics",
        optional=("symbol",),
    ),
    _view(
        "financial_income",
        "financial",
        "利润表",
        "/api/financials/income",
        optional=("symbol",),
    ),
    _view(
        "financial_balance_sheet",
        "financial",
        "资产负债表",
        "/api/financials/balance-sheet",
        optional=("symbol",),
    ),
    _view(
        "financial_cash_flow",
        "financial",
        "现金流量表",
        "/api/financials/cash-flow",
        optional=("symbol",),
    ),
    _view(
        "financial_shares",
        "financial",
        "总股本与流通股本",
        "/api/financials/shares",
        optional=("symbol",),
    ),
    _view(
        "valuation_daily",
        "financial",
        "本地派生估值日数据, 含 PIT 股本对应市值",
        "/api/reference/valuation-daily",
        optional=("symbol", "start_date", "end_date", "limit"),
    ),
    _view(
        "limit_up_events",
        "market",
        "本地派生涨跌停事件, 按交易日或股票查询",
        "/api/reference/limit-up-events",
        optional=("symbol", "start_date", "end_date", "limit"),
    ),
    _view(
        "index_membership_history",
        "index",
        "本地指数/股票池成分观察历史",
        "/api/reference/index-membership",
        optional=("symbol", "pool_id", "index_code", "start_date", "end_date", "limit"),
    ),
    _view(
        "corporate_actions",
        "stock",
        "分红送转等公司行动正式事实与核对信号",
        "/api/reference/corporate-actions",
        optional=("symbol", "start_date", "end_date", "limit"),
    ),
    _view(
        "analysis_history",
        "reports",
        "当前账户已保存的个股 / 财务 / 大盘复盘历史目录, 不含报告正文",
        "/api/ai-history/reports",
        optional=("kind", "symbol", "limit"),
    ),
    _view(
        "analysis_history_report",
        "reports",
        "按类型和报告 ID 读取当前账户的一份历史报告正文",
        "/api/ai-history/reports/{kind}/{report_id}",
        required=("kind", "report_id"),
    ),
    _view("financial_reports", "reports", "用户已保存的财务分析报告", "/api/financials/reports"),
    _view("stock_reports", "reports", "用户已保存的个股分析报告", "/api/stock-analysis/reports"),
    _view("review_reports", "reports", "用户已保存的大盘复盘报告", "/api/market-recap/reports"),
    _view("index_list", "index", "指数目录", "/api/index/list"),
    _view(
        "index_search",
        "index",
        "按代码或名称搜索指数",
        "/api/index/search",
        optional=("q", "limit"),
    ),
    _view(
        "index_daily",
        "index",
        "指数日 K",
        "/api/index/daily",
        required=("symbol",),
        optional=("days", "start_date", "end_date"),
    ),
    _view(
        "index_minute",
        "index",
        "指数指定交易日分钟 K",
        "/api/index/minute",
        required=("symbol",),
        optional=("date",),
    ),
    _view("screener_strategies", "strategy", "选股器预设与说明", "/api/screener/strategies"),
    _view(
        "screener_cached",
        "strategy",
        "用户台当前可见选股结果缓存",
        "/api/screener/cached",
        optional=("ext_columns",),
    ),
    _view("strategy_list", "strategy", "全部策略定义与用户覆盖配置", "/api/strategies"),
    _view(
        "strategy_detail",
        "strategy",
        "指定策略详情",
        "/api/strategies/{strategy_id}",
        required=("strategy_id",),
    ),
    _view(
        "strategy_source",
        "strategy",
        "指定策略在用户台可查看的源码",
        "/api/strategies/{strategy_id}/source",
        required=("strategy_id",),
    ),
    _view("custom_signals", "strategy", "用户自定义技术信号", "/api/custom-signals"),
    _view(
        "custom_signal_options",
        "strategy",
        "自定义信号可用字段与运算符",
        "/api/custom-signals/options",
    ),
    _view("monitor_rules", "monitor", "监控规则. 外发地址会被脱敏", "/api/monitor-rules"),
    _view(
        "monitor_rule_options",
        "monitor",
        "监控规则字段、信号和条件选项",
        "/api/monitor-rules/options",
    ),
    _view(
        "alerts",
        "monitor",
        "用户台监控触发记录",
        "/api/alerts",
        optional=("days", "limit", "source", "type"),
    ),
    _view("backtest_status", "backtest", "回测能力状态", "/api/backtest/status"),
    _view("factor_columns", "backtest", "因子回测可用字段", "/api/backtest/factor/columns"),
)

_VIEWS_BY_ID = {view.id: view for view in USER_CONSOLE_DATA_VIEWS}


def visible_user_console_data_views() -> tuple[UserConsoleDataView, ...]:
    """Filter the static allowlist through the current account's role policy."""
    from fastapi import HTTPException

    from app.services import user_context
    from app.services.authorization import require_request_access

    user = user_context.current()
    visible: list[UserConsoleDataView] = []
    for view in USER_CONSOLE_DATA_VIEWS:
        if user.get("role") != "admin" and view.path.startswith("/api/data/"):
            # Browser users may inspect the shared market status/catalog, but
            # the Agent bridge keeps its original bounded surface. Tool access
            # must never expand implicitly when a browser read route opens.
            continue
        try:
            require_request_access(user, "GET", view.path)
        except HTTPException:
            continue
        visible.append(view)
    return tuple(visible)
_PATH_PARAM_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_INTEGER_LIMITS: dict[str, tuple[int, int]] = {
    "limit": (1, 500),
    "days": (1, 2000),
    "top": (1, 100),
    "bins": (10, 200),
    "max_periods": (1, 40),
}
_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "cookie",
    "headers",
    "password",
    "refresh_token",
    "secret",
    "token",
    "webhook_secret",
    "webhook_url",
}


def _path_parameter_names(path: str) -> tuple[str, ...]:
    return tuple(_PATH_PARAM_RE.findall(path))


def _view_path_regex(path: str) -> re.Pattern[str]:
    pieces: list[str] = []
    cursor = 0
    for match in _PATH_PARAM_RE.finditer(path):
        pieces.append(re.escape(path[cursor : match.start()]))
        pieces.append(r"[^/]+")
        cursor = match.end()
    pieces.append(re.escape(path[cursor:]))
    return re.compile("^" + "".join(pieces) + "$")


_SAFE_PATH_PATTERNS = tuple(_view_path_regex(view.path) for view in USER_CONSOLE_DATA_VIEWS)


def is_user_console_read_path(path: str) -> bool:
    """Return whether *path* is an explicitly exposed user-console GET view."""
    return any(pattern.fullmatch(path) for pattern in _SAFE_PATH_PATTERNS)


def _normalize_param(name: str, value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(item).strip() for item in value if str(item).strip())
    text = str(value).strip()
    if name in _INTEGER_LIMITS and text:
        try:
            number = int(text)
        except ValueError as exc:
            raise UserConsoleDataError(f"参数 {name} 必须是整数") from exc
        minimum, maximum = _INTEGER_LIMITS[name]
        number = max(minimum, min(maximum, number))
        return str(number)
    return text


def _redact_and_budget(
    value: Any,
    *,
    max_items: int,
    max_string_chars: int,
    path: str = "$",
) -> tuple[Any, list[str], list[str]]:
    truncated: list[str] = []
    redacted: list[str] = []
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, child) in enumerate(value.items()):
            child_path = f"{path}.{key}"
            if index >= 250:
                truncated.append(path)
                break
            lowered = str(key).lower()
            if lowered in _SENSITIVE_KEYS or lowered.endswith(
                ("_password", "_secret", "_token", "_api_key")
            ):
                result[str(key)] = "<redacted>" if child else child
                if child:
                    redacted.append(child_path)
                continue
            result[str(key)], child_truncated, child_redacted = _redact_and_budget(
                child,
                max_items=max_items,
                max_string_chars=max_string_chars,
                path=child_path,
            )
            truncated.extend(child_truncated)
            redacted.extend(child_redacted)
        return result, truncated, redacted
    if isinstance(value, list):
        result = []
        for index, child in enumerate(value[:max_items]):
            cleaned, child_truncated, child_redacted = _redact_and_budget(
                child,
                max_items=max_items,
                max_string_chars=max_string_chars,
                path=f"{path}[{index}]",
            )
            result.append(cleaned)
            truncated.extend(child_truncated)
            redacted.extend(child_redacted)
        if len(value) > max_items:
            truncated.append(path)
        return result, truncated, redacted
    if isinstance(value, str) and len(value) > max_string_chars:
        truncated.append(path)
        return value[:max_string_chars] + "…", truncated, redacted
    return value, truncated, redacted


class UserConsoleDataModule:
    """Expose all approved user-console data behind discover/query Interface."""

    INTERNAL_KEY_HEADER: ClassVar[str] = "X-One-Trading-Hermes-Data-Key"
    INTERNAL_PROFILE_HEADER: ClassVar[str] = "X-One-Trading-Hermes-Profile"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        profile: str | None = None,
        client: httpx.AsyncClient | None = None,
        app: Any | None = None,
        base_url: str = "http://127.0.0.1:3018",
    ) -> None:
        self._api_key = api_key
        self._profile = profile
        self._client_override = client
        self._app = app
        self._base_url = base_url.rstrip("/")

    def _resolved_api_key(self) -> str:
        if self._api_key is not None:
            return self._api_key
        try:
            tenant = HermesTenantRegistry().current()
            self._profile = tenant.profile
            return tenant.data_key
        except HermesTenantError as exc:
            raise UserConsoleDataError("Hermes 用户台数据桥接尚未配置", status_code=503) from exc

    def _resolved_profile(self) -> str:
        if self._profile:
            return self._profile
        try:
            tenant = HermesTenantRegistry().current()
            self._profile = tenant.profile
            return tenant.profile
        except HermesTenantError as exc:
            raise UserConsoleDataError("Hermes 用户台数据桥接缺少 Profile", status_code=503) from exc

    def authorization_is_valid(self, authorization: str | None) -> bool:
        expected = self._resolved_api_key()
        scheme, _, supplied = (authorization or "").partition(" ")
        return bool(
            expected
            and scheme.lower() == "bearer"
            and supplied
            and secrets.compare_digest(supplied.strip(), expected)
        )

    def internal_key_is_valid(self, supplied: str | None) -> bool:
        expected = self._resolved_api_key()
        return bool(expected and supplied and secrets.compare_digest(supplied.strip(), expected))

    def catalog(self, *, domain: str = "", search: str = "") -> dict[str, Any]:
        domain_key = domain.strip().lower()
        search_key = search.strip().lower()
        detailed = bool(domain_key or search_key)
        allowed_views = visible_user_console_data_views()
        views = []
        for view in allowed_views:
            if domain_key and view.domain != domain_key:
                continue
            if (
                search_key
                and search_key not in f"{view.id} {view.domain} {view.description}".lower()
            ):
                continue
            if detailed:
                views.append(
                    {
                        "id": view.id,
                        "domain": view.domain,
                        "description": view.description,
                        "parameters": view.parameters,
                    }
                )
        domains = sorted({view.domain for view in allowed_views})
        domain_counts = {
            item: sum(view.domain == item for view in allowed_views) for item in domains
        }
        return {
            "interface": "one-trading-user-console-data/v1",
            "mode": "read-only",
            "domains": domains,
            "domain_counts": domain_counts,
            "view_count": len(allowed_views),
            "result_count": len(views),
            "views": views,
            "hint": (
                "请传入 domain 或 search 以按需获取该领域的视图 ID 与参数。"
                "默认只返回轻量摘要以避免把整份目录塞入模型上下文。"
                if not detailed
                else "使用返回的 view ID 调用 one_trading_data_query。"
            ),
            "excluded": [
                "账户、持仓、订单与交易",
                "认证凭据与账户设置",
                "同步、刷新、保存、删除、清理和外发操作",
                "未进入当前用户运行面的 announcement_events",
            ],
        }

    async def query(
        self,
        view_id: str,
        params: Mapping[str, Any] | None = None,
        *,
        max_items: int = 100,
    ) -> dict[str, Any]:
        view = _VIEWS_BY_ID.get(view_id.strip())
        if view is None:
            raise UserConsoleDataError(f"未知用户台数据视图: {view_id}")
        if view not in visible_user_console_data_views():
            raise UserConsoleDataError("当前用户无权访问该用户台数据视图", status_code=403)

        supplied = dict(params or {})
        allowed = set(view.required) | set(view.optional)
        unknown = sorted(set(supplied) - allowed)
        if unknown:
            raise UserConsoleDataError(f"视图 {view.id} 不接受参数: {', '.join(unknown)}")
        missing = [name for name in view.required if not _normalize_param(name, supplied.get(name))]
        if missing:
            raise UserConsoleDataError(f"视图 {view.id} 缺少参数: {', '.join(missing)}")

        path = view.path
        path_names = set(_path_parameter_names(path))
        for name in path_names:
            value = _normalize_param(name, supplied.get(name))
            path = path.replace("{" + name + "}", quote(value, safe=""))
        query_params = dict(view.fixed_query)
        for name in allowed - path_names:
            if name not in supplied:
                continue
            value = _normalize_param(name, supplied[name])
            if value:
                query_params[name] = value

        max_items = max(1, min(500, int(max_items)))
        api_key = self._resolved_api_key()
        headers = {
            self.INTERNAL_KEY_HEADER: api_key,
            self.INTERNAL_PROFILE_HEADER: self._resolved_profile(),
            "Accept": "application/json",
        }
        owns_client = self._client_override is None
        if self._client_override is not None:
            client = self._client_override
        elif self._app is not None:
            client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self._app),
                base_url="http://127.0.0.1",
                timeout=httpx.Timeout(60.0, connect=5.0),
            )
        else:
            client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(60.0, connect=5.0),
                trust_env=False,
            )
        try:
            response = await client.get(path, params=query_params, headers=headers)
        except httpx.HTTPError as exc:
            raise UserConsoleDataError(
                f"用户台数据视图 {view.id} 当前不可用", status_code=502
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

        if response.is_error:
            detail = ""
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    detail = str(payload.get("detail") or payload.get("message") or "")[:300]
            except (ValueError, TypeError):
                pass
            suffix = f": {detail}" if detail else ""
            raise UserConsoleDataError(
                f"用户台数据视图 {view.id} 返回 HTTP {response.status_code}{suffix}",
                status_code=502,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise UserConsoleDataError(
                f"用户台数据视图 {view.id} 没有返回 JSON", status_code=502
            ) from exc

        cleaned, truncated, redacted = _redact_and_budget(
            payload,
            max_items=max_items,
            max_string_chars=8_000,
        )
        # Guard against a pathological mapping made only of scalar fields.
        serialized = json.dumps(cleaned, ensure_ascii=False, default=str)
        if len(serialized) > 120_000:
            cleaned, more_truncated, more_redacted = _redact_and_budget(
                payload,
                max_items=min(max_items, 30),
                max_string_chars=2_000,
            )
            truncated.extend(more_truncated or ["$"])
            redacted.extend(more_redacted)

        return {
            "interface": "one-trading-user-console-data/v1",
            "mode": "read-only",
            "view": view.id,
            "domain": view.domain,
            "description": view.description,
            "queried_at": datetime.now(UTC).isoformat(),
            "parameters": {key: value for key, value in supplied.items() if key in allowed},
            "truncated": sorted(set(truncated)),
            "redacted": sorted(set(redacted)),
            "data": cleaned,
        }
