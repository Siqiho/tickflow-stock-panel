"""API 路由 — /health 与 /api/capabilities。"""
from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.services import preferences
from app.tickflow import client as tf_client
from app.tickflow.capabilities import feature_availability
from app.tickflow.policy import detect_capabilities, tier_label

router = APIRouter()


def _capabilities_payload(force: bool = False) -> dict:
    capset = detect_capabilities(force=force)
    minute_user_enabled = preferences.get_minute_sync_enabled()
    features = feature_availability(capset, minute_user_enabled=minute_user_enabled)
    caps = capset.to_dict()
    # Backward-compat: some UI still checks capabilities["financial"] key presence.
    # When local/public financials are ready, expose a lightweight marker without
    # claiming full TickFlow Expert limits.
    if features.get("financial", {}).get("available") and "financial" not in caps:
        caps["financial"] = {
            "rpm": None,
            "batch": None,
            "subscribe": None,
            "source": features["financial"].get("source", "local_public"),
            "local": True,
        }
    if features.get("adj_factor", {}).get("available") and "adj_factor" not in caps:
        caps["adj_factor"] = {
            "rpm": None,
            "batch": None,
            "subscribe": None,
            "source": features["adj_factor"].get("source", "local_public"),
            "local": True,
        }
    # Single-symbol minute view via public source — marker for legacy UI checks.
    minute_feat = features.get("minute") or {}
    if minute_feat.get("view_available") and "kline.minute.batch" not in caps and "kline.minute.by_symbol" not in caps:
        caps["kline.minute.by_symbol"] = {
            "rpm": None,
            "batch": 1,
            "subscribe": None,
            "source": minute_feat.get("source", "local_public"),
            "local": True,
            "view_only": True,
            "full_market_sync": False,
        }
    quote_feat = features.get("quote") or {}
    if quote_feat.get("available") and "quote.by_symbol" not in caps:
        caps["quote.by_symbol"] = {
            "rpm": None,
            "batch": None,
            "subscribe": None,
            "source": quote_feat.get("source", "local_public"),
            "local": True,
            "mode": quote_feat.get("mode", "watchlist_public"),
        }
    return {
        "label": tier_label(),
        "capabilities": caps,
        "features": features,
        # convenience aliases for UI
        "daily": features["daily"],
        "minute": features["minute"],
        "financial": features.get("financial"),
        "adj_factor": features.get("adj_factor"),
        "depth": features.get("depth"),
        "quote": features.get("quote"),
        "websocket": features.get("websocket"),
    }


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        # 三态: none(无key/无效) / free(免费key) / api_key(付费档)
        "mode": tf_client.current_mode(),
    }


@router.get("/api/capabilities")
def capabilities() -> dict:
    """前端用来决定哪些功能可用、哪些灰显。

    额外返回 features.daily / features.minute 等结构化可用性与 reason，
    避免 UI 只根据 capabilities 字典 key 猜测。
    """
    return _capabilities_payload(force=False)


@router.post("/api/capabilities/redetect")
def redetect() -> dict:
    """用户在设置页"重新检测"按钮。"""
    return _capabilities_payload(force=True)
