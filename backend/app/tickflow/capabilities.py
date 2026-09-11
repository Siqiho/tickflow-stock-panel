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
    has_any = _has_any(capset, _DAILY_CAPS)
    return {
        "available": has_any,
        "status": "available" if has_any else "unavailable",
        "reason": None if has_any else "当前数据源无日K权限",
        "reason_code": "ok" if has_any else "no_capability",
        "capability": {
            "kline.daily.batch": capset.has(Cap.KLINE_DAILY_BATCH),
            "kline.daily.by_symbol": capset.has(Cap.KLINE_DAILY_BY_SYMBOL),
        },
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

    fin_ok = bool(capset.has(Cap.FINANCIAL) or pub_fin or local_fin)
    adj_ok = bool(capset.has(Cap.ADJ_FACTOR) or pub_adj or local_adj)

    if capset.has(Cap.FINANCIAL):
        fin_reason = None
        fin_code = "ok"
        fin_source = "tickflow"
    elif pub_fin or local_fin:
        fin_reason = None
        fin_code = "ok"
        fin_source = "local_public"
    else:
        fin_reason = "当前档位无财务数据权限,且本地尚未同步财务表"
        fin_code = "no_capability"
        fin_source = "none"

    if capset.has(Cap.ADJ_FACTOR):
        adj_reason = None
        adj_code = "ok"
        adj_source = "tickflow"
    elif pub_adj or local_adj:
        adj_reason = None
        adj_code = "ok"
        adj_source = "local_public"
    else:
        adj_reason = "当前档位无复权因子权限,且本地尚未同步复权因子"
        adj_code = "no_capability"
        adj_source = "none"

    # Depth / sealed: TickFlow Pro+ batch depth, else public L1 (bid1/ask1 vol)
    has_depth_batch = capset.has(Cap.DEPTH5_BATCH)
    has_depth_single = capset.has(Cap.DEPTH5)
    if has_depth_batch or has_depth_single:
        depth_ok = True
        depth_reason = None
        depth_code = "ok"
        depth_source = "tickflow"
        depth_status = "available"
    else:
        depth_ok = True  # public L1 unlocks sealed judgment
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
        realtime_provider = "public"

    if has_quote:
        quote_ok = True
        quote_reason = None
        quote_code = "ok"
        quote_source = "tickflow"
        quote_status = "available"
        quote_mode = "full_or_watchlist"
    elif realtime_provider == "public":
        quote_ok = True
        quote_reason = None
        quote_code = "ok"
        quote_source = "local_public"
        quote_status = "public_fallback"
        quote_mode = "full_market_public"
    elif realtime_provider and realtime_provider != "tickflow":
        quote_ok = True
        quote_reason = None
        quote_code = "ok"
        quote_source = realtime_provider
        quote_status = "available"
        quote_mode = "full_market"
    else:
        quote_ok = False
        quote_reason = "当前档位无实时行情权限，且未选择公开源"
        quote_code = "no_capability"
        quote_source = "none"
        quote_status = "unavailable"
        quote_mode = "none"

    minute_info = minute_availability(capset, user_enabled=minute_user_enabled)

    return {
        "daily": daily_availability(capset),
        "minute": minute_info,
        "adj_factor": {
            "available": adj_ok,
            "status": "available" if adj_ok else "unavailable",
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
            "fallback": None if has_depth_batch or has_depth_single else "public_l1",
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
