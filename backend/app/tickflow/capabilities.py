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
    """
    has_batch = capset.has(Cap.KLINE_MINUTE_BATCH)
    has_by_symbol = capset.has(Cap.KLINE_MINUTE_BY_SYMBOL)
    has_any = has_batch or has_by_symbol

    if not has_any:
        return {
            "available": False,
            "status": "unavailable",
            "reason": "当前数据源无分钟K权限（需 TickFlow Pro+ 或自定义分钟源）",
            "reason_code": "no_capability",
            "capability": {
                "kline.minute.batch": has_batch,
                "kline.minute.by_symbol": has_by_symbol,
            },
            "user_enabled": user_enabled,
            "full_market_sync_allowed": False,
            "single_symbol_fallback": "free_public_intraday",
            "fallback_hint": "可使用 /api/free/intraday/{symbol} 查看单票公开分时（不落全市场分钟库）",
        }

    if user_enabled is False:
        return {
            "available": True,
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
        }

    return {
        "available": True,
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
) -> dict:
    """Compact feature matrix for /api/capabilities and UI."""
    return {
        "daily": daily_availability(capset),
        "minute": minute_availability(capset, user_enabled=minute_user_enabled),
        "adj_factor": {
            "available": capset.has(Cap.ADJ_FACTOR),
            "status": "available" if capset.has(Cap.ADJ_FACTOR) else "unavailable",
            "reason": None if capset.has(Cap.ADJ_FACTOR) else "当前档位无复权因子权限",
            "reason_code": "ok" if capset.has(Cap.ADJ_FACTOR) else "no_capability",
        },
        "financial": {
            "available": capset.has(Cap.FINANCIAL),
            "status": "available" if capset.has(Cap.FINANCIAL) else "unavailable",
            "reason": None if capset.has(Cap.FINANCIAL) else "当前档位无财务数据权限",
            "reason_code": "ok" if capset.has(Cap.FINANCIAL) else "no_capability",
        },
    }
