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
    return {
        "label": tier_label(),
        "capabilities": capset.to_dict(),
        "features": features,
        # convenience aliases for UI
        "daily": features["daily"],
        "minute": features["minute"],
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
