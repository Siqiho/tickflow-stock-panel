"""Capability 定义(§5.1)。

业务代码只依赖 CapabilitySet,不读 tiers.yaml,不感知"档位"。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Cap(StrEnum):
    """所有 capability 的命名常量。新增能力时只在这里加一行。"""

    QUOTE_BY_SYMBOL        = "quote.by_symbol"
    QUOTE_BATCH            = "quote.batch"
    QUOTE_POOL             = "quote.pool"
    KLINE_DAILY_BY_SYMBOL  = "kline.daily.by_symbol"
    KLINE_DAILY_BATCH      = "kline.daily.batch"
    KLINE_MINUTE_BY_SYMBOL = "kline.minute.by_symbol"
    KLINE_MINUTE_BATCH     = "kline.minute.batch"
    INTRADAY               = "intraday"
    INTRADAY_BATCH         = "intraday.batch"
    INTRADAY_UNIVERSE      = "intraday.universe"
    DEPTH5                 = "depth5"
    DEPTH5_BATCH           = "depth5.batch"
    WEBSOCKET              = "websocket"
    FINANCIAL              = "financial"
    ADJ_FACTOR             = "adj_factor"


@dataclass(slots=True, frozen=True)
class CapabilityLimits:
    """单个 capability 的运行时限制。"""
    rpm: int | None = None        # 次/分钟,None 表示未知或不限
    batch: int | None = None      # 标的/次
    subscribe: int | None = None  # WS 订阅上限


class CapabilitySet:
    """探测得到的"用户当前可用能力"。业务代码的唯一真理源。"""

    def __init__(self, caps: dict[Cap, CapabilityLimits] | None = None) -> None:
        self._caps: dict[Cap, CapabilityLimits] = dict(caps or {})

    def has(self, cap: Cap) -> bool:
        return cap in self._caps

    def limits(self, cap: Cap) -> CapabilityLimits | None:
        return self._caps.get(cap)

    def require(self, cap: Cap) -> CapabilityLimits:
        """断言可用,否则抛 CapabilityDenied。"""
        if cap not in self._caps:
            raise CapabilityDenied(cap)
        return self._caps[cap]

    def all(self) -> dict[Cap, CapabilityLimits]:
        return dict(self._caps)

    def grant(self, cap: Cap, limits: CapabilityLimits | None = None) -> None:
        """补授一个能力 (不覆盖已有)。自定义分钟源等场景用来补齐检查入口。"""
        if cap not in self._caps:
            self._caps[cap] = limits or CapabilityLimits()

    def to_dict(self) -> dict[str, dict]:
        return {
            str(cap): {
                "rpm": lim.rpm,
                "batch": lim.batch,
                "subscribe": lim.subscribe,
            }
            for cap, lim in self._caps.items()
        }


class CapabilityDenied(Exception):
    """请求的 capability 当前不可用。"""

    def __init__(self, cap: Cap, suggestion: str | None = None) -> None:
        self.cap = cap
        self.suggestion = suggestion or f"加购『{cap}』能力可解锁"
        super().__init__(f"capability not available: {cap}; {self.suggestion}")


# ---------------------------------------------------------------------------
# Human-readable feature availability (product honesty layer)
# ---------------------------------------------------------------------------

_MINUTE_CAPS = (Cap.KLINE_MINUTE_BATCH, Cap.KLINE_MINUTE_BY_SYMBOL)
_DAILY_CAPS = (Cap.KLINE_DAILY_BATCH, Cap.KLINE_DAILY_BY_SYMBOL)


def _has_any(capset: CapabilitySet, caps: tuple[Cap, ...]) -> bool:
    return any(capset.has(c) for c in caps)


def minute_availability(
    capset: CapabilitySet,
    *,
    user_enabled: bool | None = None,
) -> dict:
    """Structured minute capability for API / pipeline / UI.

    status:
      - available: provider has minute batch/by_symbol
      - disabled_by_user: has cap but user turned sync off
      - unavailable: no minute capability on current source/tier

    Product note:
      Even without TickFlow minute caps, single-symbol / index intraday view is
      unlocked via free public sources (does NOT enable full-market minute sync).
    """
    has_batch = capset.has(Cap.KLINE_MINUTE_BATCH)
    has_by_symbol = capset.has(Cap.KLINE_MINUTE_BY_SYMBOL)
    has_any = has_batch or has_by_symbol
    try:
        from app.services import kline_sync as _kline_sync
        from app.services import preferences as _minute_prefs
        minute_custom_name = _minute_prefs.get_minute_data_provider()
        _, minute_fallback, minute_resolve_err = _kline_sync._resolve_minute_provider(
            minute_custom_name,
        )
        minute_is_custom = (not minute_fallback) and minute_resolve_err is None
    except Exception:
        return {
            "available": False,
            "view_available": False,
            "status": "unavailable",
            "reason": "数据源偏好不可读",
            "reason_code": "resolve_failed",
            "capability": {
                "kline.minute.batch": False,
                "kline.minute.by_symbol": has_by_symbol,
            },
            "user_enabled": user_enabled,
            "full_market_sync_allowed": False,
            "single_symbol_fallback": None,
            "fallback_hint": None,
            "source": "none",
        }

    if minute_resolve_err and minute_custom_name and minute_custom_name != "tickflow":
        return {
            "available": False,
            "view_available": False,
            "status": "unavailable",
            "reason": "分钟数据源解析失败",
            "reason_code": "resolve_failed",
            "capability": {
                "kline.minute.batch": False,
                "kline.minute.by_symbol": has_by_symbol,
            },
            "user_enabled": user_enabled,
            "full_market_sync_allowed": False,
            "single_symbol_fallback": None,
            "fallback_hint": None,
            "source": minute_custom_name,
        }

    if minute_is_custom:
        if user_enabled is False:
            return {
                "available": True,
                "view_available": True,
                "status": "disabled_by_user",
                "reason": "已有分钟能力，但用户关闭了自动同步",
                "reason_code": "user_disabled",
                "capability": {
                    "kline.minute.batch": True,
                    "kline.minute.by_symbol": has_by_symbol,
                },
                "user_enabled": False,
                "full_market_sync_allowed": True,
                "single_symbol_fallback": None,
                "fallback_hint": None,
                "source": minute_custom_name,
            }
        return {
            "available": True,
            "view_available": True,
            "status": "available",
            "reason": None,
            "reason_code": "ok",
            "capability": {
                "kline.minute.batch": True,
                "kline.minute.by_symbol": has_by_symbol,
            },
            "user_enabled": user_enabled,
            "full_market_sync_allowed": True,
            "single_symbol_fallback": None,
            "fallback_hint": None,
            "source": minute_custom_name,
        }

    if not has_any:
        return {
            # view_available unlocks UI charts; available stays False so pipeline
            # does not claim full-market minute sync.
            "available": False,
            "view_available": True,
            "status": "public_fallback",
            "reason": "全市场分钟同步需 TickFlow Pro+；单票/指数分时可使用公开源",
            "reason_code": "public_fallback",
            "capability": {
                "kline.minute.batch": has_batch,
                "kline.minute.by_symbol": has_by_symbol,
            },
            "user_enabled": user_enabled,
            "full_market_sync_allowed": False,
            "single_symbol_fallback": "free_public_intraday",
            "fallback_hint": "单票/指数分时走公开源（不落全市场分钟库）",
            "source": "local_public",
        }

    if user_enabled is False:
        return {
            "available": True,
            "view_available": True,
            "status": "disabled_by_user",
            "reason": "已有分钟能力，但用户关闭了自动同步",
            "reason_code": "user_disabled",
            "capability": {
                "kline.minute.batch": has_batch,
                "kline.minute.by_symbol": has_by_symbol,
            },
            "user_enabled": False,
            "full_market_sync_allowed": has_batch,
            "single_symbol_fallback": None,
            "fallback_hint": None,
            "source": "tickflow",
        }

    return {
        "available": True,
        "view_available": True,
        "status": "available",
        "reason": None,
        "reason_code": "ok",
        "capability": {
            "kline.minute.batch": has_batch,
            "kline.minute.by_symbol": has_by_symbol,
        },
        "user_enabled": user_enabled,
        "full_market_sync_allowed": has_batch,
        "single_symbol_fallback": None,
        "fallback_hint": None,
        "source": "tickflow",
    }


def daily_availability(capset: CapabilitySet) -> dict:
    caps = {
        "kline.daily.batch": capset.has(Cap.KLINE_DAILY_BATCH),
        "kline.daily.by_symbol": capset.has(Cap.KLINE_DAILY_BY_SYMBOL),
    }
    try:
        from app.services import kline_sync as _kline_sync
        from app.services import preferences as _daily_prefs
        daily_name = _daily_prefs.get_daily_data_provider()
        _, fallback, err = _kline_sync._resolve_daily_provider(daily_name)
    except Exception:
        daily_name = "tickflow"
        fallback = True
        err = None

    if err is not None and daily_name not in {"tickflow", ""}:
        return {
            "available": False,
            "status": "unavailable",
            "reason": "日K数据源解析失败",
            "reason_code": "resolve_failed",
            "source": daily_name,
            "capability": caps,
        }
    if not fallback:
        return {
            "available": True,
            "status": "available",
            "reason": None,
            "reason_code": "ok",
            "source": daily_name,
            "capability": {**caps, "kline.daily.batch": True},
        }
    has_any = _has_any(capset, _DAILY_CAPS)
    return {
        "available": has_any,
        "status": "available" if has_any else "unavailable",
        "reason": None if has_any else "当前数据源无日K权限",
        "reason_code": "ok" if has_any else "no_capability",
        "source": "tickflow" if has_any else "none",
        "capability": caps,
    }


def feature_availability(
    capset: CapabilitySet,
    *,
    minute_user_enabled: bool | None = None,
    data_dir=None,
) -> dict:
    """Compact feature matrix for /api/capabilities and UI.

    financial / adj_factor also become available when local public data exists
    or the corresponding public provider preference is on.
    """
    from pathlib import Path as _Path

    prefs_unreadable = False
    try:
        from app.config import settings as _settings
        from app.services import preferences as _prefs
        from app.services.financial_normalize import (
            local_adj_factor_ready,
            local_financials_ready,
        )
        d = _Path(data_dir) if data_dir is not None else _Path(_settings.data_dir)
        local_fin = local_financials_ready(d)
        local_adj = local_adj_factor_ready(d)
        pub_fin = _prefs.is_public_financial_provider()
        pub_adj = _prefs.is_public_adj_factor_provider()
    except Exception:
        local_fin = local_adj = pub_fin = pub_adj = False
        prefs_unreadable = True

    try:
        fin_provider = _prefs.get_financial_provider()
        adj_provider = _prefs.get_adj_factor_provider()
        depth_provider = _prefs.get_depth5_data_provider()
        minute_provider = _prefs.get_minute_data_provider()
    except Exception:
        fin_provider = adj_provider = depth_provider = minute_provider = None
        prefs_unreadable = True

    fin_ok = bool(capset.has(Cap.FINANCIAL) or pub_fin or local_fin)
    adj_ok = bool(capset.has(Cap.ADJ_FACTOR) or pub_adj or local_adj)

    if prefs_unreadable and fin_provider is None:
        fin_ok = False
        fin_reason = "数据源偏好不可读"
        fin_code = "no_capability"
        fin_source = "none"
    elif pub_fin or (not capset.has(Cap.FINANCIAL) and local_fin and fin_provider == "tickflow"):
        fin_reason = None
        fin_code = "ok"
        fin_source = "local_public"
    elif fin_provider != "tickflow":
        fin_reason = None if fin_ok else "当前财务源无法提供数据,且本地尚未同步财务表"
        fin_code = "ok" if fin_ok else "no_capability"
        fin_source = fin_provider
    elif capset.has(Cap.FINANCIAL):
        fin_reason = None
        fin_code = "ok"
        fin_source = "tickflow"
    else:
        fin_reason = "当前档位无财务数据权限,且本地尚未同步财务表"
        fin_code = "no_capability"
        fin_source = "none"

    if prefs_unreadable and adj_provider is None:
        adj_ok = False
        adj_reason = "数据源偏好不可读"
        adj_code = "no_capability"
        adj_source = "none"
        adj_status = "unavailable"
    elif pub_adj:
        adj_reason = None
        adj_code = "ok"
        adj_source = "local_public"
        adj_status = "available"
    elif adj_provider != "tickflow":
        from app.services.kline_sync import _try_custom_adj_provider
        _, adj_fate = _try_custom_adj_provider(adj_provider)
        if adj_fate == "custom":
            adj_ok = True
            adj_reason = None
            adj_code = "ok"
            adj_source = adj_provider
            adj_status = "available"
        elif adj_fate == "skip":
            adj_ok = False
            adj_reason = "当前复权源解析失败"
            adj_code = "no_capability"
            adj_source = adj_provider
            adj_status = "unavailable"
        else:
            adj_ok = bool(capset.has(Cap.ADJ_FACTOR) or local_adj)
            adj_reason = None if adj_ok else "当前复权源无法提供因子"
            adj_code = "ok" if adj_ok else "no_capability"
            adj_source = adj_provider
            adj_status = "available" if adj_ok else "unavailable"
    elif capset.has(Cap.ADJ_FACTOR):
        adj_reason = None
        adj_code = "ok"
        adj_source = "tickflow"
        adj_status = "available"
    elif local_adj:
        adj_reason = None
        adj_code = "ok"
        adj_source = "local_public"
        adj_status = "available"
    else:
        # TickFlow none/free cannot serve factors. sync_adj_factor already
        # uses the public sina qfq adapter — labels must not say "none".
        adj_ok = True
        adj_reason = "当前档位无复权因子权限，同步时走公开源（新浪 qfq）"
        adj_code = "public_fallback"
        adj_source = "local_public"
        adj_status = "public_fallback"

    # Depth / sealed: custom source, explicit public, TickFlow Pro+ batch,
    # leftover TickFlow empty → public L1. Prefs unreadable: do not advertise
    # TickFlow / public_l1.
    has_depth_batch = capset.has(Cap.DEPTH5_BATCH)
    has_depth_single = capset.has(Cap.DEPTH5)
    if prefs_unreadable and depth_provider is None:
        depth_ok = False
        depth_reason = "数据源偏好不可读"
        depth_code = "no_capability"
        depth_source = "none"
        depth_status = "unavailable"
    elif depth_provider not in {"tickflow", "public", None}:
        depth_ok = True
        depth_reason = None
        depth_code = "ok"
        depth_source = depth_provider
        depth_status = "available"
    elif depth_provider == "public":
        depth_ok = True
        depth_reason = None
        depth_code = "ok"
        depth_source = "local_public"
        depth_status = "public_fallback"
    elif has_depth_batch or has_depth_single:
        depth_ok = True
        depth_reason = None
        depth_code = "ok"
        depth_source = "tickflow"
        depth_status = "available"
    else:
        depth_ok = True  # leftover TickFlow: public L1 unlocks sealed judgment
        depth_reason = None
        depth_code = "ok"
        depth_source = "local_public"
        depth_status = "public_fallback"

    # Quote realtime: TickFlow free+/paid, else public full-market snapshot
    has_quote = (
        capset.has(Cap.QUOTE_BY_SYMBOL)
        or capset.has(Cap.QUOTE_BATCH)
        or capset.has(Cap.QUOTE_POOL)
    )
    try:
        from app.services import preferences as _prefs_q
        realtime_provider = _prefs_q.get_realtime_data_provider()
    except Exception:
        realtime_provider = None

    if realtime_provider is None:
        quote_ok = False
        quote_reason = "数据源偏好不可读"
        quote_code = "no_capability"
        quote_source = "none"
        quote_status = "unavailable"
        quote_mode = "none"
    elif realtime_provider == "public":
        quote_ok = True
        quote_reason = None
        quote_code = "ok"
        quote_source = "local_public"
        quote_status = "public_fallback"
        quote_mode = "full_market_public"
    elif realtime_provider and realtime_provider not in {"tickflow", ""}:
        quote_ok = True
        quote_reason = None
        quote_code = "ok"
        quote_source = realtime_provider
        quote_status = "available"
        quote_mode = "full_market"
    elif has_quote:
        quote_ok = True
        quote_reason = None
        quote_code = "ok"
        quote_source = "tickflow"
        quote_status = "available"
        quote_mode = "full_or_watchlist"
    else:
        quote_ok = False
        quote_reason = "当前档位无实时行情权限，且未选择公开源"
        quote_code = "no_capability"
        quote_source = "none"
        quote_status = "unavailable"
        quote_mode = "none"

    minute_info = minute_availability(capset, user_enabled=minute_user_enabled)
    if (
        minute_provider
        and minute_provider != "tickflow"
        and minute_info.get("source") == "tickflow"
    ):
        minute_info = {**minute_info, "source": minute_provider}

    return {
        "daily": daily_availability(capset),
        "minute": minute_info,
        "adj_factor": {
            "available": adj_ok,
            "status": adj_status,
            "reason": adj_reason,
            "reason_code": adj_code,
            "source": adj_source,
        },
        "financial": {
            "available": fin_ok,
            "status": "available" if fin_ok else "unavailable",
            "reason": fin_reason,
            "reason_code": fin_code,
            "source": fin_source,
        },
        "depth": {
            "available": depth_ok,
            "status": depth_status,
            "reason": depth_reason,
            "reason_code": depth_code,
            "source": depth_source,
            "capability": {
                "depth5": has_depth_single,
                "depth5.batch": has_depth_batch,
            },
            "fallback": (
                None
                if depth_provider != "tickflow"
                or has_depth_batch
                or has_depth_single
                else "public_l1"
            ),
            "operation": "depth5" if has_depth_batch or has_depth_single else "sealed_l1",
            "depth5_available": has_depth_batch or has_depth_single,
        },
        "quote": {
            "available": quote_ok,
            "status": quote_status,
            "reason": quote_reason,
            "reason_code": quote_code,
            "source": quote_source,
            "mode": quote_mode,
            "operation": "quote" if has_quote else "quote_snapshot",
            "capability": {
                "quote.by_symbol": capset.has(Cap.QUOTE_BY_SYMBOL),
                "quote.batch": capset.has(Cap.QUOTE_BATCH),
                "quote.pool": capset.has(Cap.QUOTE_POOL),
            },
        },
        "websocket": {
            "available": capset.has(Cap.WEBSOCKET),
            "status": "available" if capset.has(Cap.WEBSOCKET) else "unavailable",
            "reason": None if capset.has(Cap.WEBSOCKET) else "WebSocket 需 TickFlow Expert，暂无公开源替代",
            "reason_code": "ok" if capset.has(Cap.WEBSOCKET) else "no_capability",
            "source": "tickflow" if capset.has(Cap.WEBSOCKET) else "none",
        },
    }
