"""设置 API — Key 配置 / 模式切换。

提供面向非开发者的 UI 配置入口,避免逼用户改 .env。
"""
from __future__ import annotations

import logging
import time

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import secrets_store
from app.tickflow import client as tf_client
from app.tickflow.policy import (
    detect_capabilities,
    extras_caps,
    missing_caps,
    probe_log,
    tier_label,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _require_self_hosted_ai_settings() -> None:
    """Cloud subscription credentials are deployment-owned, never WebView-owned."""
    from app.services.ai_provider import is_cloud_subscription_mode

    if is_cloud_subscription_mode():
        raise HTTPException(status_code=403, detail="云端 AI 订阅由服务器统一管理，APK 不能修改 AI 凭据")


def _require_server_ai_login_request(request: Request) -> None:
    """Cloud OAuth is manageable from the server web UI, never from the APK."""
    from app.services.ai_provider import is_cloud_subscription_mode

    if not is_cloud_subscription_mode():
        return
    user_agent = request.headers.get("user-agent", "").lower()
    if "one-trading-android/" in user_agent:
        raise HTTPException(status_code=403, detail="APK 只能使用云端 AI，不能管理服务器 OAuth 会话")


def _server_xai_status() -> dict:
    status = _ai_xai_status()
    return {
        **status,
        "auth_type": "server_oauth" if status.get("has_oauth") else "server_managed",
    }


def _ai_xai_status() -> dict:
    try:
        from app.services import xai_oauth
        return xai_oauth.status()
    except Exception as e:
        logger.warning("xai status failed: %s", e)
        return {"auth_type": None, "has_oauth": False, "has_access_token": False, "expires_at": None, "expired": False}

# 默认端点 —— endpoints.json 列表第一项,UI"当前使用"始终对齐此项。
# 注意:Free 模式 SDK 实际走 free-api(免费数据通道),但 UI 显示统一用默认节点。
DEFAULT_PAID_ENDPOINT = "https://api.tickflow.org"


def _sync_financial_scheduler_caps(app_state, capset) -> None:
    """把重新探测出的能力同步给财务调度器。

    app.state.capabilities 在此已更新, 但 FinancialScheduler 在启动时捕获的是旧引用,
    需显式刷新, 否则用户升级到 Expert 后点「全部同步」仍会因调度器读旧 capset 而被拒。
    """
    fs = getattr(app_state, "financial_scheduler", None)
    if fs is None:
        return
    try:
        fs.update_capabilities(capset)
    except Exception as e:
        logging.getLogger(__name__).warning("update financial_scheduler capabilities failed: %s", e)


class TickflowKeyIn(BaseModel):
    api_key: str


@router.get("")
def get_settings() -> dict:
    """返回当前配置概况(Key 脱敏)。"""
    from app.config import settings
    from app.services import preferences, user_context
    from app.services.ai_provider import (
        ai_access_status,
        ai_configured,
        current_ai_model,
        current_ai_provider,
        current_codex_command,
        is_cloud_subscription_mode,
        list_server_subscriptions,
    )

    key = secrets_store.get_tickflow_key()
    ai_provider = current_ai_provider()
    cloud_managed = is_cloud_subscription_mode()
    admin = user_context.is_admin()
    return {
        "mode": tf_client.current_mode(),
        "tickflow_api_key_masked": secrets_store.mask(key) if admin else "",
        "has_tickflow_key": bool(key) if admin else False,
        "tier_label": tier_label(),
        "current_endpoint": tf_client.current_endpoint(),
        "probe_log": probe_log() if admin else [],
        "missing_caps": missing_caps() if admin else [],
        "extras_caps": extras_caps() if admin else [],
        # 首次使用引导
        "onboarding_completed": preferences.get_onboarding_completed() if admin else True,
        # AI 配置
        "ai_provider": ai_provider,
        "ai_base_url": "" if cloud_managed else secrets_store.get_ai_config("ai_base_url", settings.ai_base_url),
        "ai_api_key_masked": "" if cloud_managed else secrets_store.mask(secrets_store.get_ai_key()),
        "has_ai_key": bool(settings.ai_api_key) if cloud_managed else bool(secrets_store.get_ai_key()),
        "ai_configured": ai_configured(ai_provider),
        "ai_model": current_ai_model(),
        "ai_codex_command": current_codex_command(),
        "ai_user_agent": "" if cloud_managed else secrets_store.get_ai_config("ai_user_agent", settings.ai_user_agent),
        "ai_xai": (
            (_server_xai_status() if cloud_managed else _ai_xai_status())
            if admin else {"auth_type": "server_managed", "has_oauth": False,
                           "has_access_token": False, "expires_at": None, "expired": False}
        ),
        "ai_access": ai_access_status(),
        "ai_subscriptions": (
            list_server_subscriptions(include_secrets=admin) if cloud_managed else []
        ),
        "is_admin": admin,
        "credential_management": "owner" if admin else "admin_only",
    }


class SwitchEndpointIn(BaseModel):
    url: str


@router.post("/switch_endpoint")
def switch_endpoint(req: SwitchEndpointIn, request: Request) -> dict:
    """切换 TickFlow 端点并立即生效。

    端点切换仅对付费档(starter+,走 api.tickflow.org)有意义;
    none/free 档运行在 free-api 服务器,无付费端点权限,禁止切换。
    """
    # none/free 档没有付费端点权限,禁止切换
    if tf_client.current_mode() != "api_key":
        return {"ok": False, "error": "当前档位无法切换端点,仅付费套餐(Starter+)支持"}

    url = req.url.strip().rstrip("/")
    if not url.startswith("https://"):
        return {"ok": False, "error": "仅支持 HTTPS 端点"}

    # 持久化到 secrets.json
    secrets_store.save({"tickflow_base_url": url})
    # 重置客户端，下次调用自动用新端点
    tf_client.reset_clients()

    return {
        "ok": True,
        "current_endpoint": tf_client.current_endpoint(),
    }


@router.post("/tickflow-key")
def save_tickflow_key(req: TickflowKeyIn, request: Request) -> dict:
    """保存 TickFlow API Key 并立即重新探测能力。

    先探后存(关键改动,修复乱填 key 也会被持久化的问题):
      1. 临时用新 key 探测(付费端点),判定档位
      2. 判定为 none(连单只日K都拿不到)→ key 无效:不存,清除已存的,
         返回 {ok: false, reason: "invalid"},前端提示「Key 无效」
      3. 判定为 free(免费有效 key)→ 存 key,客户端切到 free-api 服务器
      4. 判定为 starter+ → 存 key,切到付费端点(现有逻辑)

    端点联动:从无 key 升级到付费 key 时,残留的 free-api 端点不可用,
    故自动切到默认付费端点(api.tickflow.org);free 档则清除自定义端点。
    """
    from app.tickflow.policy import (
        base_tier_name,
        is_invalid_key,
    )

    key = req.api_key.strip()
    if not key:
        return {"ok": False, "error": "key empty"}

    # ===== 1) 临时存 key + 重置客户端,让探测走付费端点 =====
    secrets_store.save({"tickflow_api_key": key})
    tf_client.reset_clients()

    # 立即重新探测(此时 client 已按档位判定,但首次探测必然走付费端点验证)
    capset = detect_capabilities(force=True)
    request.app.state.capabilities = capset
    _sync_financial_scheduler_caps(request.app.state, capset)

    # ===== 2) 判定为无效 key(连单只日K都拿不到)→ 不存,清除 =====
    if is_invalid_key() or base_tier_name() == "none":
        # 无效 key:清除刚存的,避免乱填被持久化;退回 none 档
        secrets_store.clear("tickflow_api_key", "tickflow_base_url")
        tf_client.reset_clients()
        capset = detect_capabilities(force=True)
        request.app.state.capabilities = capset
        _sync_financial_scheduler_caps(request.app.state, capset)
        return {
            "ok": False,
            "reason": "invalid",
            "error": "Key 无效或已过期,请检查后重试",
            "mode": "none",
            "tier_label": tier_label(),
            "current_endpoint": tf_client.current_endpoint(),
            "probe_log": [],
            "capabilities_count": len(capset.all()),
        }

    # ===== 3) free 档(免费有效 key)→ 存 key,切到 free-api 服务器 =====
    if base_tier_name() == "free":
        # 免费档运行时走 free-api 服务器,清除付费端点的自定义配置
        secrets_store.clear("tickflow_base_url")
        tf_client.reset_clients()
        return {
            "ok": True,
            "tickflow_api_key_masked": secrets_store.mask(key),
            "mode": "free",
            "tier_label": tier_label(),
            "current_endpoint": tf_client.current_endpoint(),
            "probe_log": [],
            "capabilities_count": len(capset.all()),
        }

    # ===== 4) starter+ 付费档 → 确保走付费端点(现有逻辑) =====
    # 若之前是 none/free(无自定义付费端点),切到默认付费端点
    base = secrets_store.load().get("tickflow_base_url")
    if not base:
        secrets_store.save({"tickflow_base_url": DEFAULT_PAID_ENDPOINT})
    tf_client.reset_clients()

    return {
        "ok": True,
        "tickflow_api_key_masked": secrets_store.mask(key),
        "mode": "api_key",
        "tier_label": tier_label(),
        "current_endpoint": tf_client.current_endpoint(),
        "probe_log": [],
        "capabilities_count": len(capset.all()),
    }


@router.delete("/tickflow-key")
def clear_tickflow_key(request: Request) -> dict:
    """清除 Key,退回无档(none)。

    同时清除 tickflow_base_url(测速切换的自定义端点),使客户端走 free-api
    服务器取历史日K;档位标签为 None(无档)。
    """
    secrets_store.clear("tickflow_api_key", "tickflow_base_url")
    tf_client.reset_clients()

    capset = detect_capabilities(force=True)
    request.app.state.capabilities = capset
    _sync_financial_scheduler_caps(request.app.state, capset)

    return {
        "ok": True,
        "mode": "none",
        "tier_label": tier_label(),
        "current_endpoint": tf_client.current_endpoint(),
        "capabilities_count": len(capset.all()),
    }


@router.post("/onboarding/complete")
def complete_onboarding() -> dict:
    """标记首次使用向导完成。

    写入 preferences.json,前端守卫据此判断是否需要再次展示向导。
    跨设备/清缓存安全 —— 状态落在后端文件,不依赖浏览器本地存储。
    """
    from app.services import preferences
    done = preferences.set_onboarding_completed(True)
    return {"ok": True, "onboarding_completed": done}


class AiSettingsIn(BaseModel):
    provider: str = "openai_compat"
    base_url: str = ""
    api_key: str | None = None
    model: str = ""
    codex_command: str = ""
    user_agent: str = ""


@router.post("/ai")
def save_ai_settings(req: AiSettingsIn) -> dict:
    """保存 AI 配置（全部持久化到 secrets.json）"""
    _require_self_hosted_ai_settings()
    from app.config import settings
    from app.services.ai_provider import (
        XAI_API_BASE,
        XAI_PROVIDER,
        ai_configured,
        current_ai_model,
        current_ai_provider,
        current_codex_command,
        normalize_codex_command,
    )

    updates: dict = {}
    if req.provider:
        updates["ai_provider"] = req.provider
        settings.ai_provider = req.provider
    # xAI 官方端点固定；其他 provider 按用户填写
    if req.provider == XAI_PROVIDER:
        updates["ai_base_url"] = XAI_API_BASE
        settings.ai_base_url = XAI_API_BASE
    elif req.base_url:
        updates["ai_base_url"] = req.base_url
        settings.ai_base_url = req.base_url
    if req.api_key is not None:
        if req.api_key:
            updates["ai_api_key"] = req.api_key
            settings.ai_api_key = req.api_key
            if req.provider == XAI_PROVIDER:
                # 粘贴 Key 时切换为 api_key 模式（不立刻清 OAuth，避免误操作；调用优先 OAuth）
                updates["ai_xai_auth_type"] = "api_key"
        else:
            secrets_store.clear("ai_api_key")
            settings.ai_api_key = ""
    if req.provider == "codex_cli" and not req.model:
        secrets_store.clear("ai_model")
        settings.ai_model = ""
    elif req.model:
        updates["ai_model"] = req.model
        settings.ai_model = req.model
    if req.provider == "codex_cli":
        try:
            codex_command = normalize_codex_command(req.codex_command)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        updates["ai_codex_command"] = codex_command
        settings.ai_codex_command = codex_command
    # user_agent 允许清空(回到默认浏览器 UA),故无条件持久化
    updates["ai_user_agent"] = req.user_agent
    settings.ai_user_agent = req.user_agent

    if updates:
        secrets_store.save(updates)

    provider = current_ai_provider()
    return {
        "ok": True,
        "ai_provider": provider,
        "ai_model": current_ai_model(),
        "ai_codex_command": current_codex_command(),
        "ai_configured": ai_configured(provider),
        "ai_xai": _ai_xai_status(),
    }


class AiSubscriptionIn(BaseModel):
    provider: str
    model: str = ""
    base_url: str = ""
    api_key: str = ""


class AiSubscriptionSourceIn(BaseModel):
    provider: str
    base_url: str = ""
    api_key: str | None = None
    clear_api_key: bool = False


@router.post("/ai/subscription")
def save_ai_subscription(req: AiSubscriptionIn, request: Request) -> dict:
    """Switch the hosted subscription source. Keys stay server-owned."""
    _require_server_ai_login_request(request)
    from app.services import user_context
    if not user_context.is_admin():
        raise HTTPException(status_code=403, detail="仅服务器管理员可以切换模型提供商")
    from app.services.ai_provider import (
        ai_configured,
        current_ai_model,
        current_ai_provider,
        list_server_subscriptions,
        select_server_subscription,
    )

    try:
        access = select_server_subscription(req.provider, req.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    provider = current_ai_provider()
    return {
        "ok": True,
        "ai_provider": provider,
        "ai_model": current_ai_model(),
        "ai_configured": ai_configured(provider),
        "ai_access": access,
        "ai_subscriptions": list_server_subscriptions(include_secrets=True),
        "ai_xai": _server_xai_status(),
    }


@router.post("/ai/subscription/source")
def save_ai_subscription_source(req: AiSubscriptionSourceIn, request: Request) -> dict:
    """Save admin-managed provider URL/key without exposing raw credentials."""
    _require_server_ai_login_request(request)
    from app.services import user_context
    if not user_context.is_admin():
        raise HTTPException(status_code=403, detail="仅服务器管理员可以配置模型提供商")
    from app.services.ai_provider import save_server_subscription_source

    try:
        return save_server_subscription_source(
            req.provider,
            base_url=req.base_url,
            api_key=req.api_key,
            clear_api_key=req.clear_api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/ai/subscription/test")
async def test_ai_subscription(req: AiSubscriptionIn, request: Request) -> dict:
    """Probe the selected hosted source without applying it."""
    _require_server_ai_login_request(request)
    from app.services import user_context
    if not user_context.is_admin():
        raise HTTPException(status_code=403, detail="仅服务器管理员可以测试模型提供商")
    from app.services.ai_provider import probe_server_subscription

    try:
        return await probe_server_subscription(
            req.provider,
            req.model,
            api_key=req.api_key,
            base_url=req.base_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/ai")
def clear_ai_settings() -> dict:
    """一键清空 AI 配置(provider / base_url / api_key / model)。

    保留 ai_user_agent —— 自定义请求头与凭证解耦,清空凭证不影响绕过 CDN 拦截的设置。
    """
    _require_self_hosted_ai_settings()
    from app.config import settings

    secrets_store.clear(
        "ai_provider",
        "ai_base_url",
        "ai_api_key",
        "ai_model",
        "ai_codex_command",
        "ai_xai_access_token",
        "ai_xai_refresh_token",
        "ai_xai_expires_at",
        "ai_xai_auth_type",
    )
    # 同步重置运行时内存(provider 回默认值,其余置空)
    settings.ai_provider = "openai_compat"
    settings.ai_base_url = ""
    settings.ai_api_key = ""
    settings.ai_model = ""
    settings.ai_codex_command = "codex"

    return {"ok": True}


# ===== xAI / Grok SuperGrok 登录 =====

class XaiDeviceStartOut(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str = ""
    expires_in: int
    interval: int


@router.post("/ai/xai/device/start")
def xai_device_start(request: Request) -> dict:
    """发起 xAI 设备码登录（SuperGrok 订阅 OAuth）。"""
    _require_server_ai_login_request(request)
    from app.services import xai_oauth
    try:
        return xai_oauth.request_device_code()
    except xai_oauth.XaiOAuthError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("xai device start failed")
        raise HTTPException(status_code=502, detail=f"无法连接 xAI 认证服务: {e}") from e


class XaiDevicePollIn(BaseModel):
    device_code: str
    interval: int | None = None
    expires_in: int | None = None
    model: str = "grok-4.5"


@router.post("/ai/xai/device/poll")
def xai_device_poll(req: XaiDevicePollIn, request: Request) -> dict:
    """单次探测设备码状态；前端按 interval 轮询本接口。"""
    _require_server_ai_login_request(request)
    from app.config import settings
    from app.services import xai_oauth
    from app.services.ai_provider import (
        XAI_API_BASE,
        XAI_DEFAULT_MODEL,
        XAI_PROVIDER,
        ai_configured,
        current_ai_model,
        is_cloud_subscription_mode,
        select_server_subscription,
    )

    try:
        result = xai_oauth.attempt_device_token(req.device_code)
    except xai_oauth.XaiOAuthError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if result.get("status") != "authorized":
        return {
            "ok": False,
            "status": "pending",
            "slow_down": bool(result.get("slow_down")),
        }

    tokens = result["tokens"]
    xai_oauth.save_oauth_tokens(tokens)
    model = (req.model or "").strip() or XAI_DEFAULT_MODEL
    secrets_store.save({
        "ai_provider": XAI_PROVIDER,
        "ai_base_url": XAI_API_BASE,
        "ai_model": model,
    })
    settings.ai_provider = XAI_PROVIDER
    settings.ai_base_url = XAI_API_BASE
    settings.ai_model = model
    if is_cloud_subscription_mode():
        select_server_subscription(XAI_PROVIDER, model)
    else:
        settings.ai_api_key = ""

    return {
        "ok": True,
        "status": "authorized",
        "ai_provider": XAI_PROVIDER,
        "ai_model": current_ai_model(),
        "ai_configured": ai_configured(XAI_PROVIDER),
        "ai_xai": xai_oauth.status(),
    }


@router.get("/ai/xai/status")
def xai_status() -> dict:
    from app.services.ai_provider import is_cloud_subscription_mode
    if is_cloud_subscription_mode():
        return _server_xai_status()
    return _ai_xai_status()


@router.delete("/ai/xai/session")
def xai_logout(request: Request) -> dict:
    """仅清除 xAI OAuth 会话，保留其它 AI 配置。"""
    _require_server_ai_login_request(request)
    from app.services import xai_oauth
    xai_oauth.clear_oauth_tokens()
    return {"ok": True, "ai_xai": _ai_xai_status()}


# ===== 偏好设置 =====

def _realtime_allowed() -> bool:
    """当前档位是否允许实时行情(none/free 不允许)。"""
    from app.services.quote_service import QuoteService
    return QuoteService.is_realtime_allowed()


class MinuteSyncPrefs(BaseModel):
    minute_sync_enabled: bool
    minute_sync_days: int = 5


@router.get("/preferences")
def get_preferences() -> dict:
    """返回用户偏好设置。"""
    from app.services import preferences
    return {
        "realtime_quotes_enabled": preferences.get_realtime_quotes_enabled(),
        "realtime_allowed": _realtime_allowed(),
        "indices_nav_pinned": preferences.get_indices_nav_pinned(),
        "minute_sync_enabled": preferences.get_minute_sync_enabled(),
        "minute_sync_days": preferences.get_minute_sync_days(),
        "daily_data_provider": preferences.get_daily_data_provider(),
        "adj_factor_provider": preferences.get_adj_factor_provider(),
        "financial_provider": preferences.get_financial_provider(),
        "pool_provider": preferences.get_pool_provider(),
        "minute_data_provider": preferences.get_minute_data_provider(),
        "realtime_data_provider": preferences.get_realtime_data_provider(),
        "realtime_watchlist_symbols": preferences.get_realtime_watchlist_symbols(),
        **preferences.get_realtime_quote_scope(),
        "pipeline_pull_a_share": preferences.get_pipeline_pull_a_share(),
        "pipeline_pull_etf": preferences.get_pipeline_pull_etf(),
        "pipeline_pull_index": preferences.get_pipeline_pull_index(),
        "pipeline_universe_scope": preferences.get_pipeline_universe_scope(),
        "public_data_scope": preferences.get_public_data_scope(),
        "financial_max_periods": preferences.get_financial_max_periods(),
        "pipeline_index_symbols": preferences.get_pipeline_index_symbols(),
        "pipeline_schedule": preferences.get_pipeline_schedule(),
        "instruments_schedule": preferences.get_instruments_schedule(),
        "enriched_batch_size": preferences.get_enriched_batch_size(),
        "index_daily_batch_size": preferences.get_index_daily_batch_size(),
        "watchlist_columns": preferences.get_watchlist_columns(),
        "screener_result_columns": preferences.get_screener_result_columns(),
        "sse_refresh_pages": preferences.get_sse_refresh_pages(),
        "strategy_monitor_enabled": preferences.get_strategy_monitor_enabled(),
        "strategy_monitor_ids": preferences.get_strategy_monitor_ids(),
        "system_notify_enabled": preferences.get_system_notify_enabled(),
        "feishu_webhook_url": preferences.get_feishu_webhook_url(),
        "feishu_webhook_secret": preferences.get_feishu_webhook_secret(),
        "wecom_webhook_url": preferences.get_wecom_webhook_url(),
        "custom_webhook_url": preferences.get_custom_webhook_url(),
        "custom_webhook_secret_set": bool(secrets_store.get_custom_webhook_secret()),
        "email_smtp_config": preferences.get_email_smtp_config(),
        "email_smtp_password_set": bool(secrets_store.get_email_smtp_password()),
        "webhook_enabled_default": preferences.get_webhook_enabled_default(),
        "webhook_default_channels": preferences.get_webhook_default_channels(),
        "minute_batch_compress": preferences.get_minute_batch_compress(),
        "daily_batch_compress": preferences.get_daily_batch_compress(),
        "sidebar_index_symbols": preferences.get_sidebar_index_symbols(),
        "nav_order": preferences.get_nav_order(),
        "nav_hidden": preferences.get_nav_hidden(),
        "screener_auto_run": preferences.get_screener_auto_run(),
        "limit_ladder_monitor_enabled": preferences.get_limit_ladder_monitor_enabled(),
        "depth_polling_interval": preferences.get_depth_polling_interval(),
        "depth_finalize_time": preferences.get_depth_finalize_time(),
        "review_schedule": preferences.get_review_schedule(),
        "review_push_channels": preferences.get_review_push_channels(),
        "review_push_mode": preferences.get_review_push_mode(),
        "pipeline_regime_enabled": preferences.get_pipeline_regime_enabled(),
        "regime_batch_days": preferences.get_regime_batch_days(),
        "regime_warmup_days": preferences.get_regime_warmup_days(),
        "wecom_bot_id": preferences.get_wecom_bot_id(),
        "wecom_bot_secret": preferences.get_wecom_bot_secret(),
        "wecom_bot_enabled": preferences.get_wecom_bot_enabled(),
        "watchlist_groups_in_nav": preferences.get_watchlist_groups_in_nav(),
        "minute_refresh_enabled": preferences.get_minute_refresh_enabled(),
        "minute_refresh_interval": preferences.get_minute_refresh_interval(),
        "depth5_data_provider": preferences.get_depth5_data_provider(),
        "financial_data_provider": preferences.get_financial_provider(),
        "data_source_job_timeout_s": preferences.get_data_source_job_timeout_s(),
        "data_source_long_job_timeout_s": preferences.get_data_source_long_job_timeout_s(),
        **preferences.get_mining_schedule(),
    }


@router.get("/preferences/watchlist-columns")
def get_watchlist_columns() -> dict:
    """返回自选列表列配置。"""
    from app.services import preferences
    cols = preferences.get_watchlist_columns()
    return {"columns": cols}


class NavOrderIn(BaseModel):
    nav_order: list[str]


class NavHiddenIn(BaseModel):
    nav_hidden: list[str]


@router.put("/preferences/nav-order")
def update_nav_order(req: NavOrderIn) -> dict:
    """保存左侧菜单排序（内置页面 path + 扩展分析菜单 id 的有序列表）。"""
    from app.services import preferences
    saved = preferences.set_nav_order(req.nav_order)
    return {"nav_order": saved}


@router.put("/preferences/nav-hidden")
def update_nav_hidden(req: NavHiddenIn) -> dict:
    """保存左侧菜单隐藏项。"""
    from app.services import preferences
    saved = preferences.set_nav_hidden(req.nav_hidden)
    return {"nav_hidden": saved}


@router.put("/preferences/watchlist-columns")
def update_watchlist_columns(req: dict) -> dict:
    """保存自选列表列配置。"""
    from app.services import preferences
    columns = req.get("columns", [])
    saved = preferences.set_watchlist_columns(columns)
    return {"columns": saved}


@router.get("/preferences/screener-result-columns")
def get_screener_result_columns() -> dict:
    """返回策略结果列表列配置。"""
    from app.services import preferences
    cols = preferences.get_screener_result_columns()
    return {"columns": cols}


@router.put("/preferences/screener-result-columns")
def update_screener_result_columns(req: dict) -> dict:
    """保存策略结果列表列配置。"""
    from app.services import preferences
    columns = req.get("columns", [])
    saved = preferences.set_screener_result_columns(columns)
    return {"columns": saved}


@router.put("/preferences/minute-sync")
def update_minute_sync(req: MinuteSyncPrefs) -> dict:
    """保存分钟 K 同步偏好。"""
    from app.services import preferences
    days = max(1, min(30, req.minute_sync_days))
    preferences.save_server({
        "minute_sync_enabled": req.minute_sync_enabled,
        "minute_sync_days": days,
    })
    return {
        "minute_sync_enabled": req.minute_sync_enabled,
        "minute_sync_days": days,
    }


class RealtimeQuotesPrefs(BaseModel):
    realtime_quotes_enabled: bool


class RealtimeQuoteScopePrefs(BaseModel):
    realtime_pull_stock: bool | None = None
    realtime_pull_etf: bool | None = None




class AdjFactorProviderPrefs(BaseModel):
    adj_factor_provider: str  # tickflow | public | sina | sina_qfq | free | same_as_daily


@router.put("/preferences/adj-factor-provider")
def update_adj_factor_provider(req: AdjFactorProviderPrefs) -> dict:
    """设置除权因子数据源。public/sina* 使用免费新浪 qfq，不依赖 TickFlow ADJ_FACTOR。"""
    from app.services import preferences
    allowed = {"tickflow", "public", "sina", "sina_qfq", "free", "same_as_daily"}
    val = (req.adj_factor_provider or "same_as_daily").strip().lower()
    if val not in allowed:
        raise HTTPException(status_code=400, detail=f"unsupported adj_factor_provider: {val}")
    preferences.save_server({"adj_factor_provider": val})
    return {"adj_factor_provider": preferences.get_adj_factor_provider()}




class FinancialProviderPrefs(BaseModel):
    financial_provider: str  # tickflow | public | eastmoney | em | free


@router.put("/preferences/financial-provider")
def update_financial_provider(req: FinancialProviderPrefs) -> dict:
    """设置财务四表数据源。public/eastmoney 使用东财 HSF10，不依赖 TickFlow FINANCIAL。"""
    from app.services import preferences
    allowed = {"tickflow", "public", "eastmoney", "em", "free"}
    val = (req.financial_provider or "tickflow").strip().lower()
    if val not in allowed:
        raise HTTPException(status_code=400, detail=f"unsupported financial_provider: {val}")
    preferences.save_server({"financial_provider": val, "financial_data_provider": val})
    return {"financial_provider": preferences.get_financial_provider()}




class PoolProviderPrefs(BaseModel):
    pool_provider: str  # tickflow | public | csindex | sina | free


@router.put("/preferences/pool-provider")
def update_pool_provider(req: PoolProviderPrefs) -> dict:
    """设置指数成分池数据源。public/csindex 使用中证官方 XLS(+新浪 fallback)。"""
    from app.services import preferences
    allowed = {"tickflow", "public", "csindex", "sina", "free"}
    val = (req.pool_provider or "public").strip().lower()
    if val not in allowed:
        raise HTTPException(status_code=400, detail=f"unsupported pool_provider: {val}")
    preferences.save_server({"pool_provider": val})
    return {"pool_provider": preferences.get_pool_provider()}


@router.put("/preferences/realtime-quotes")
def update_realtime_quotes(req: RealtimeQuotesPrefs, request: Request) -> dict:
    """保存全局实时行情开关。

    none/free 档开启自选股实时（公开源可兜底）；starter+ 开启全市场实时。
    前端据此展示模式与限制。
    """
    from app.services import preferences
    qs = getattr(request.app.state, "quote_service", None)

    allowed = qs.is_realtime_allowed() if qs else True
    if req.realtime_quotes_enabled and not allowed:
        # 当前档位不允许开启实时行情 — 强制关闭
        preferences.save_server({"realtime_quotes_enabled": False})
        if qs:
            qs.disable()
        return {"realtime_quotes_enabled": False, "realtime_allowed": False}
    if req.realtime_quotes_enabled and qs and qs.realtime_mode() == "watchlist" and not preferences.get_realtime_watchlist_symbols():
        preferences.save_server({"realtime_quotes_enabled": False})
        return {"realtime_quotes_enabled": False, "realtime_allowed": True, "mode": "watchlist", "error": "watchlist_empty"}

    preferences.save_server({"realtime_quotes_enabled": req.realtime_quotes_enabled})
    if qs:
        if req.realtime_quotes_enabled:
            qs.enable()
        else:
            qs.disable()

    return {"realtime_quotes_enabled": req.realtime_quotes_enabled, "realtime_allowed": allowed}


@router.put("/preferences/realtime-quote-scope")
def update_realtime_quote_scope(req: RealtimeQuoteScopePrefs) -> dict:
    """保存盘中实时行情范围；独立于盘后管道范围。"""
    from app.services import preferences
    cfg = req.model_dump(exclude_none=True)
    return preferences.set_realtime_quote_scope(cfg)


class RealtimeWatchlistPrefs(BaseModel):
    symbols: list[str] = []


@router.put("/preferences/realtime-watchlist")
def update_realtime_watchlist(req: RealtimeWatchlistPrefs) -> dict:
    """兼容旧入口；Free 实时标的由自选页前 5 个决定。"""
    from app.services import preferences
    symbols = preferences.set_realtime_watchlist_symbols(req.symbols)
    return {"realtime_watchlist_symbols": symbols}


class IndicesNavPinnedPrefs(BaseModel):
    indices_nav_pinned: bool


@router.put("/preferences/indices-nav-pinned")
def update_indices_nav_pinned(req: IndicesNavPinnedPrefs) -> dict:
    """保存侧栏指数报价卡片固定显示开关。
    ON=常驻显示；OFF=跟随实时行情开关（仅实时开时显示）。"""
    from app.services import preferences
    preferences.save({"indices_nav_pinned": req.indices_nav_pinned})
    return {"indices_nav_pinned": req.indices_nav_pinned}


class RealtimeMonitorConfigIn(BaseModel):
    sse_refresh_pages: dict[str, bool] | None = None
    strategy_monitor_enabled: bool | None = None
    strategy_monitor_ids: list[str] | None = None
    sidebar_index_symbols: list[str] | None = None
    screener_auto_run: bool | None = None


@router.put("/preferences/realtime-monitor")
def update_realtime_monitor_config(req: RealtimeMonitorConfigIn, request: Request) -> dict:
    """更新实时监控配置。策略监控统一迁移为 MonitorRule,由监控引擎评估。"""
    from app.services import preferences

    cfg = req.model_dump(exclude_none=True)
    result = preferences.set_realtime_monitor_config(cfg)

    # 策略监控开关/池变化 → 同步迁移为 type=strategy 规则 + reload 引擎
    if req.strategy_monitor_ids is not None or req.strategy_monitor_enabled is not None:
        monitor_engine = getattr(request.app.state, "monitor_engine", None)
        strategy_engine = getattr(request.app.state, "strategy_engine", None)
        data_dir = request.app.state.repo.store.data_dir
        if monitor_engine is not None and strategy_engine is not None:
            from app.strategy import monitor_rules as mr_store
            try:
                if preferences.get_strategy_monitor_enabled():
                    ids = preferences.get_strategy_monitor_ids()
                    names = {s.id: s.name for s in strategy_engine.list_strategies()}
                    mr_store.migrate_strategy_monitors(data_dir, ids, names)
                else:
                    # 关闭策略监控: 停用所有策略规则
                    mr_store.migrate_strategy_monitors(data_dir, [], {})
                # reload 规则到引擎
                monitor_engine.set_rules(mr_store.load_all(data_dir))
            except Exception:
                pass

    return result


class PipelinePullTypesIn(BaseModel):
    """盘后管道拉取内容开关(A股 / ETF / 指数 独立控制)。"""
    pipeline_pull_a_share: bool | None = None
    pipeline_pull_etf: bool | None = None
    pipeline_pull_index: bool | None = None


@router.put("/preferences/pipeline-pull-types")
def update_pipeline_pull_types(req: PipelinePullTypesIn) -> dict:
    """更新盘后管道拉取内容开关。"""
    from app.services import preferences
    cfg = req.model_dump(exclude_none=True)
    return preferences.set_pipeline_pull_types(cfg)


class PipelineIndexSymbolsIn(BaseModel):
    """指数自定义拉取代码(逗号/换行/空格分隔,空串表示全量)。"""
    symbols: str = ""




class UniverseScopeIn(BaseModel):
    """标的范围: ALL | CSI300 | CSI500 | CSI800 | CSI1000 | CSI1800 | SSE50 | WATCHLIST"""
    scope: str


@router.put("/preferences/pipeline-universe-scope")
def update_pipeline_universe_scope(req: UniverseScopeIn) -> dict:
    """盘后管道主标的范围（影响日K/管道 universe）。"""
    from app.services import preferences
    from app.services.universe_scope import SCOPE_LABELS
    val = preferences.set_pipeline_universe_scope(req.scope)
    return {
        "pipeline_universe_scope": val,
        "label": SCOPE_LABELS.get(val, val),
    }


@router.put("/preferences/public-data-scope")
def update_public_data_scope(req: UniverseScopeIn) -> dict:
    """public 复权/财务同步默认范围（默认 CSI300；可设 CSI800=300∪500）。"""
    from app.services import preferences
    from app.services.universe_scope import SCOPE_LABELS
    val = preferences.set_public_data_scope(req.scope)
    return {
        "public_data_scope": val,
        "label": SCOPE_LABELS.get(val, val),
    }




class FinancialMaxPeriodsIn(BaseModel):
    financial_max_periods: int


@router.put("/preferences/financial-max-periods")
def update_financial_max_periods(req: FinancialMaxPeriodsIn) -> dict:
    """public 财务拉取报告期数量 (4-40, 默认 12)。"""
    from app.services import preferences
    val = preferences.set_financial_max_periods(req.financial_max_periods)
    return {"financial_max_periods": val}


@router.get("/preferences/universe-scope-options")
def universe_scope_options() -> dict:
    """前端下拉选项。"""
    from app.services.universe_scope import SCOPE_LABELS, VALID_SCOPES
    return {
        "items": [{"value": s, "label": SCOPE_LABELS.get(s, s)} for s in VALID_SCOPES],
        "defaults": {
            "pipeline_universe_scope": "ALL",
            "public_data_scope": "CSI300",
        },
    }


@router.put("/preferences/pipeline-index-symbols")
def update_pipeline_index_symbols(req: PipelineIndexSymbolsIn) -> dict:
    """保存指数自定义拉取代码。"""
    from app.services import preferences
    symbols = preferences.set_pipeline_index_symbols(req.symbols)
    return {"pipeline_index_symbols": symbols}


class QuoteIntervalIn(BaseModel):
    interval: float


class SystemNotifyPrefsIn(BaseModel):
    enabled: bool


@router.put("/preferences/system-notify")
def update_system_notify(req: SystemNotifyPrefsIn) -> dict:
    """系统通知开关 — 开启后监控告警同时推送到操作系统通知中心。

    纯偏好, 无副作用 (不像策略监控要迁移规则), 直接落盘即可。
    quote_service 在每轮告警评估时读此开关决定是否发系统通知。
    """
    from app.services import preferences
    saved = preferences.set_system_notify_enabled(req.enabled)
    return {"system_notify_enabled": saved}


class FeishuWebhookPrefsIn(BaseModel):
    url: str
    secret: str = ""


@router.put("/preferences/feishu-webhook")
def update_feishu_webhook(req: FeishuWebhookPrefsIn) -> dict:
    """飞书 Webhook 地址 + 签名密钥 — 全局一处配置, 所有启用推送的监控规则共用。

    - url: 传入空串表示清空配置; 非空则需为合法的飞书自定义机器人地址。
    - secret: 机器人启用了「签名校验」时填密钥, 留空表示不验签。
    """
    from app.services import preferences, webhook_adapter

    url = (req.url or "").strip()
    if url and not webhook_adapter.is_valid_feishu_url(url):
        raise HTTPException(
            status_code=400,
            detail="Webhook 地址非法, 需为飞书自定义机器人地址 "
                   "(https://open.feishu.cn/open-apis/bot/v2/hook/...)",
        )
    saved_url = preferences.set_feishu_webhook_url(url)
    saved_secret = preferences.set_feishu_webhook_secret((req.secret or "").strip())
    return {"feishu_webhook_url": saved_url, "feishu_webhook_secret": saved_secret}


class WecomWebhookPrefsIn(BaseModel):
    url: str


@router.put("/preferences/wecom-webhook")
def update_wecom_webhook(req: WecomWebhookPrefsIn) -> dict:
    """企业微信群推送 Webhook — 已实现, 默认空/不推送。"""
    from app.services import preferences, webhook_adapter

    url = (req.url or "").strip()
    if url and not webhook_adapter.is_valid_wecom_url(url):
        raise HTTPException(
            status_code=400,
            detail="Webhook 地址非法, 需为企业微信群推送地址或纯 key",
        )
    return {"wecom_webhook_url": preferences.set_wecom_webhook_url(url)}


class CustomWebhookPrefsIn(BaseModel):
    url: str
    secret: str | None = None


@router.put("/preferences/custom-webhook")
def update_custom_webhook(req: CustomWebhookPrefsIn) -> dict:
    """Configure the generic third-party JSON webhook and optional HMAC secret."""
    from app.services import preferences, webhook_adapter

    url = (req.url or "").strip()
    if url and not webhook_adapter.is_valid_custom_url(url):
        raise HTTPException(status_code=400, detail="Webhook 地址必须是完整的 HTTP(S) URL")
    saved_url = preferences.set_custom_webhook_url(url)
    if not saved_url:
        secrets_store.set_custom_webhook_secret("")
    elif req.secret is not None:
        secrets_store.set_custom_webhook_secret(req.secret)
    return {
        "custom_webhook_url": saved_url,
        "custom_webhook_secret_set": bool(secrets_store.get_custom_webhook_secret()),
    }


class EmailSmtpPrefsIn(BaseModel):
    host: str
    port: int = Field(default=465, ge=1, le=65535)
    security: Literal["ssl", "starttls", "none"] = "ssl"
    username: str = ""
    password: str | None = None
    from_address: str = ""
    to_addresses: list[str] = Field(default_factory=list)


@router.put("/preferences/email-smtp")
def update_email_smtp(req: EmailSmtpPrefsIn) -> dict:
    """Configure the SMTP transport shared by monitor alerts and review reports."""
    from app.services import email_adapter, preferences

    host = (req.host or "").strip()
    username = (req.username or "").strip()
    from_address = (req.from_address or username).strip()
    recipients = list(dict.fromkeys(item.strip() for item in req.to_addresses if item.strip()))
    if host:
        if not from_address or not email_adapter.is_valid_email(from_address):
            raise HTTPException(status_code=400, detail="请填写有效的发件人邮箱")
        if not recipients or any(not email_adapter.is_valid_email(item) for item in recipients):
            raise HTTPException(status_code=400, detail="请至少填写一个有效的收件人邮箱")
        effective_password = (
            secrets_store.get_email_smtp_password()
            if req.password is None
            else req.password
        )
        if username and not effective_password:
            raise HTTPException(status_code=400, detail="已填写 SMTP 登录用户名, 请同时填写密码或授权码")
    else:
        username = ""
        from_address = ""
        recipients = []

    config = preferences.set_email_smtp_config({
        "host": host,
        "port": req.port,
        "security": req.security,
        "username": username,
        "from_address": from_address,
        "to_addresses": recipients,
    })
    if not host or not username:
        secrets_store.set_email_smtp_password("")
    elif req.password is not None:
        secrets_store.set_email_smtp_password(req.password)
    return {
        "email_smtp_config": config,
        "email_smtp_password_set": bool(secrets_store.get_email_smtp_password()),
    }


class MinuteBatchCompressPrefs(BaseModel):
    minute_batch_compress: bool


class DailyBatchCompressPrefs(BaseModel):
    daily_batch_compress: bool


@router.put("/preferences/minute-batch-compress")
def update_minute_batch_compress(req: MinuteBatchCompressPrefs) -> dict:
    """保存分时详情与批量响应的 gzip 传输压缩开关。逐请求即时读取, 保存后立即生效。"""
    from app.services import preferences
    preferences.save({"minute_batch_compress": req.minute_batch_compress})
    return {"minute_batch_compress": preferences.get_minute_batch_compress()}


@router.put("/preferences/daily-batch-compress")
def update_daily_batch_compress(req: DailyBatchCompressPrefs) -> dict:
    """保存日K详情与批量响应的 gzip 传输压缩开关 (与分时独立)。逐请求即时读取。"""
    from app.services import preferences
    preferences.save({"daily_batch_compress": req.daily_batch_compress})
    return {"daily_batch_compress": preferences.get_daily_batch_compress()}


class WecomBotPrefsIn(BaseModel):
    bot_id: str
    secret: str
    enabled: bool = False


@router.put("/preferences/wecom-bot")
def update_wecom_bot(req: WecomBotPrefsIn) -> dict:
    """保存企业微信智能机器人凭证。默认关闭, 本阶段不建立外发长连接。"""
    from app.services import preferences

    bot_id = (req.bot_id or "").strip()
    secret = (req.secret or "").strip()
    preferences.set_wecom_bot_id(bot_id)
    preferences.set_wecom_bot_secret(secret)
    enabled = bool(req.enabled and bot_id and secret)
    preferences.set_wecom_bot_enabled(enabled)
    return {
        "wecom_bot_id": preferences.get_wecom_bot_id(),
        "wecom_bot_secret": preferences.get_wecom_bot_secret(),
        "wecom_bot_enabled": enabled,
        "wecom_bot_status": {
            "running": False,
            "connected": False,
            "reason": "default_off" if not enabled else "outbound_disabled",
        },
    }


class WecomBotToggleIn(BaseModel):
    enabled: bool


@router.put("/preferences/wecom-bot-toggle")
def toggle_wecom_bot(req: WecomBotToggleIn) -> dict:
    from app.services import preferences

    bot_id = preferences.get_wecom_bot_id()
    secret = preferences.get_wecom_bot_secret()
    enabled = bool(req.enabled and bot_id and secret)
    preferences.set_wecom_bot_enabled(enabled)
    return {
        "wecom_bot_enabled": enabled,
        "wecom_bot_status": {
            "running": False,
            "connected": False,
            "reason": "default_off" if not enabled else "outbound_disabled",
        },
    }


class WebhookTestIn(BaseModel):
    channel: Literal["feishu", "wecom", "custom", "email"]


@router.post("/preferences/webhook-test")
def test_webhook(req: WebhookTestIn) -> dict:
    """只打已保存配置。未配置返回 ok=False, 不发起外发。测试通道需自行 mock。"""
    from app.services import preferences, webhook_adapter

    title = "one-trading 推送测试"
    body = "配置探测 (默认关闭, 仅在已保存地址时才会请求)"
    if req.channel == "feishu":
        url = preferences.get_feishu_webhook_url()
        if not url:
            return {"ok": False, "detail": "尚未配置飞书 Webhook，请先保存"}
        if not webhook_adapter.is_valid_feishu_url(url):
            return {"ok": False, "detail": "地址非法"}
        ok = webhook_adapter.send_feishu(
            url, title, body, preferences.get_feishu_webhook_secret(), max_attempts=1,
        )
    elif req.channel == "wecom":
        url = preferences.get_wecom_webhook_url()
        if not url:
            return {"ok": False, "detail": "尚未配置企业微信 Webhook，请先保存"}
        if not webhook_adapter.is_valid_wecom_url(url):
            return {"ok": False, "detail": "地址非法"}
        ok = webhook_adapter.send_wecom(url, title, body)
    elif req.channel == "custom":
        url = preferences.get_custom_webhook_url()
        if not url:
            return {"ok": False, "detail": "尚未配置第三方 Webhook, 请先保存"}
        if not webhook_adapter.is_valid_custom_url(url):
            return {"ok": False, "detail": "地址非法"}
        ok = webhook_adapter.send_custom(
            url,
            title,
            body,
            event_type="test",
            secret=secrets_store.get_custom_webhook_secret(),
            max_attempts=1,
        )
    else:
        from app.services import email_adapter

        config = preferences.get_email_smtp_config()
        if not email_adapter.is_configured(config):
            return {"ok": False, "detail": "尚未完整配置邮件 SMTP, 请先保存"}
        ok = email_adapter.send_email(
            config,
            secrets_store.get_email_smtp_password(),
            title,
            body,
            max_attempts=1,
        )
    if ok:
        return {"ok": True, "detail": "测试消息已发送"}
    return {"ok": False, "detail": "推送失败或被默认关闭拦截"}


class WebhookEnabledDefaultIn(BaseModel):
    enabled: bool


@router.put("/preferences/webhook-enabled-default")
def update_webhook_enabled_default(req: WebhookEnabledDefaultIn) -> dict:
    """新建监控规则时是否默认勾选「飞书推送」。

    数据模型当前只有飞书一个可用渠道 (QMT/ptrade 待定),故此处仅一个布尔。
    单条规则仍可在规则编辑页独立修改此项。
    """
    from app.services import preferences

    saved = preferences.set_webhook_enabled_default(req.enabled)
    return {"webhook_enabled_default": saved}


@router.put("/preferences/quote-interval")
def update_quote_interval(req: QuoteIntervalIn, request: Request) -> dict:
    """更新行情轮询间隔。按档位自动 clamp。"""
    qs = getattr(request.app.state, "quote_service", None)
    if not qs:
        return {"interval": req.interval, "min_interval": 6.0, "max_interval": 60.0}
    clamped = qs.set_interval(req.interval)
    return {
        "interval": clamped,
        "min_interval": qs.get_min_interval(),
        "max_interval": qs.MAX_INTERVAL,
    }


@router.get("/preferences/quote-interval")
def get_quote_interval(request: Request) -> dict:
    """获取当前行情轮询间隔和档位限制。"""
    qs = getattr(request.app.state, "quote_service", None)
    if not qs:
        return {"interval": 15.0, "min_interval": 5.0, "max_interval": 60.0}
    return {
        "interval": qs._interval,
        "min_interval": qs.get_min_interval(),
        "max_interval": qs.MAX_INTERVAL,
    }


class TestEndpointIn(BaseModel):
    url: str
    # 测试轮数;不传时取 endpoints.json 的 testRounds(默认 5)
    rounds: int | None = None


# 官方端点发现清单 —— 前端浏览器无法直接跨域拉取 tickflow.org/endpoints.json
# (无 CORS 头),因此由后端代理。缓存 5 分钟,失败时回退到内置列表。
ENDPOINTS_URL = "https://tickflow.org/endpoints.json"
ENDPOINTS_TTL = 300.0  # 秒

# 回退列表 —— 与官方 endpoints.json 的 endpoints[] 字段对齐。
# 当远程拉取失败时使用,保证 UI 永远有内容可显示。
_FALLBACK_ENDPOINTS: list[dict] = [
    {
        "id": "default",
        "url": "https://api.tickflow.org",
        "label": "默认端点",
        "region": "auto",
        "description": "默认端点",
        "premium": False,
    },
    {
        "id": "hk",
        "url": "https://hk-api.tickflow.org",
        "label": "香港端点",
        "region": "ap-east-1",
        "description": "备用端点，部分地区访问更稳定",
        "premium": False,
    },
    {
        "id": "sg",
        "url": "https://sg-api.tickflow.org",
        "label": "新加坡端点",
        "region": "ap-southeast-1",
        "description": "备用端点，亚太地区访问更稳定",
        "premium": False,
    },
    {
        "id": "us",
        "url": "https://us-api.tickflow.org",
        "label": "美国端点",
        "region": "us-east-1",
        "description": "备用端点，欧美地区访问更稳定",
        "premium": False,
    },
    {
        "id": "cn",
        "url": "https://139.196.55.234:50443",
        "label": "中国大陆端点（Beta）",
        "region": "cn-east-1",
        "description": "备用端点，中国大陆地区访问更稳定，目前处于测试阶段，谨慎使用",
        "premium": False,
    },
    {
        "id": "cn-premium",
        "url": "https://106.15.238.72:50443",
        "label": "中国大陆专线端点",
        "region": "cn-east-1",
        "description": "专线加速端点，需要专线加速权限（该权限包含在 Expert 及以上套餐中，也可通过自定义组合单独开通）",
        "premium": True,
    },
]

# 进程内缓存:{ "ts": float, "data": dict }
_endpoints_cache: dict = {"ts": 0.0, "data": None}


@router.get("/endpoints")
def list_endpoints() -> dict:
    """代理拉取 tickflow.org/endpoints.json 并返回规范化端点列表。

    前端无法跨域直连该 URL(无 CORS 头),故由本接口代理。带 8s 超时、
    5 分钟内存缓存,远程失败时回退到内置列表,保证 UI 始终有内容。
    返回结构与原始 endpoints.json 一致(透传 schema/version 等元信息)。
    """
    import httpx

    now = time.monotonic()
    cached = _endpoints_cache.get("data")
    if cached is not None and (now - _endpoints_cache["ts"]) < ENDPOINTS_TTL:
        return cached

    source = "remote"
    data: dict | None = None
    try:
        resp = httpx.get(ENDPOINTS_URL, timeout=8.0, follow_redirects=True)
        if resp.status_code == 200:
            parsed = resp.json()
            eps = parsed.get("endpoints")
            # 校验:必须是列表且每项含必要字段,否则视为无效
            if isinstance(eps, list) and all(
                isinstance(e, dict) and "url" in e for e in eps
            ):
                data = {
                    "version": parsed.get("version", 1),
                    "description": parsed.get(
                        "description", "TickFlow API 端点配置"
                    ),
                    "healthPath": parsed.get("healthPath", "/health"),
                    "testRounds": parsed.get("testRounds", 5),
                    "endpoints": eps,
                }
    except (httpx.HTTPError, ValueError):
        logger.warning("拉取 endpoints.json 失败，使用内置回退列表", exc_info=True)

    if data is None:
        source = "fallback"
        data = {
            "version": 1,
            "description": "TickFlow API 端点配置",
            "healthPath": "/health",
            "testRounds": 5,
            "endpoints": _FALLBACK_ENDPOINTS,
        }

    # 标记数据来源,便于前端提示(回退时显示"内置列表")。
    data["source"] = source
    _endpoints_cache["ts"] = now
    _endpoints_cache["data"] = data
    return data


async def _http_ping(url: str, timeout: float = 10.0) -> float | None:
    """单次异步 GET 请求并返回延迟(ms),失败返回 None。

    对齐官方 latency_test.py:用 /health 轻量端点测真实网络延迟,
    不携带 API Key(/health 公开)。异步实现,保证多端点并行测速不阻塞。
    """
    import httpx

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            dt = (time.perf_counter() - t0) * 1000
            # 只把 <400 视为成功;4xx/5xx 也算"不可达"
            if resp.status_code < 400:
                return round(dt, 2)
            return None
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError, OSError):
        return None


@router.post("/test_endpoint")
async def test_endpoint(req: TestEndpointIn) -> dict:
    """测试端点网络延迟:对 /health 多轮探测取中位数。

    参考 TickFlow 官方 latency_test.py:
    - 路径用 /health(公开、轻量),反映真实网络延迟而非业务接口耗时
    - 多轮探测(默认 5 轮,取自 endpoints.json 的 testRounds),间隔 0.3s
    - 返回 median/min/max/success,前端显示中位数
    - 异步实现,保证"全部测速"时多端点真正并行
    """
    import asyncio
    import statistics

    base = req.url.rstrip("/")
    rounds = max(1, min(10, req.rounds or _endpoints_cache.get("data", {}).get("testRounds", 5)))
    health_url = base + "/health"

    latencies: list[float] = []
    for _ in range(rounds):
        ms = await _http_ping(health_url)
        if ms is not None:
            latencies.append(ms)
        # 官方脚本间隔 0.3s;末轮无需等待
        await asyncio.sleep(0.3)

    success = len(latencies)
    if success == 0:
        return {
            "ok": False,
            "error": "不可达",
            "url": req.url,
            "rounds": rounds,
            "success": 0,
            "median_ms": None,
            "min_ms": None,
            "max_ms": None,
        }

    median = round(statistics.median(latencies), 2)
    return {
        "ok": True,
        "url": req.url,
        "rounds": rounds,
        "success": success,
        "median_ms": median,
        "min_ms": round(min(latencies), 2),
        "max_ms": round(max(latencies), 2),
        # 兼容旧字段:取中位数作为代表延迟
        "latency_ms": median,
    }


class PipelineScheduleIn(BaseModel):
    hour: int
    minute: int


@router.put("/preferences/pipeline-schedule")
def update_pipeline_schedule(req: PipelineScheduleIn, request: Request) -> dict:
    """保存盘后管道调度时间并立即 reschedule。"""
    from app.services import preferences
    sched = preferences.set_pipeline_schedule(req.hour, req.minute)

    # 动态 reschedule
    from apscheduler.triggers.cron import CronTrigger
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        scheduler.reschedule_job(
            "daily_pipeline",
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=sched["hour"],
                minute=sched["minute"],
                timezone="Asia/Shanghai",
            ),
        )
        logger.info("pipeline rescheduled to %02d:%02d mon-fri", sched["hour"], sched["minute"])

    return sched


@router.put("/preferences/instruments-schedule")
def update_instruments_schedule(req: PipelineScheduleIn, request: Request) -> dict:
    """保存盘前标的维表调度时间并立即 reschedule。"""
    from app.services import preferences
    sched = preferences.set_instruments_schedule(req.hour, req.minute)

    from apscheduler.triggers.cron import CronTrigger
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        scheduler.reschedule_job(
            "pre_market_instruments",
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=sched["hour"],
                minute=sched["minute"],
                timezone="Asia/Shanghai",
            ),
        )
        return sched


class EnrichedBatchSizeIn(BaseModel):
    size: int


@router.put("/preferences/enriched-batch-size")
def update_enriched_batch_size(req: EnrichedBatchSizeIn) -> dict:
    """保存 enriched 全量计算批次大小。"""
    from app.services import preferences
    size = preferences.set_enriched_batch_size(req.size)
    return {"enriched_batch_size": size}


class IndexDailyBatchSizeIn(BaseModel):
    size: int


@router.put("/preferences/index-daily-batch-size")
def update_index_daily_batch_size(req: IndexDailyBatchSizeIn) -> dict:
    """保存指数日 K 同步批次大小。"""
    from app.services import preferences
    size = preferences.set_index_daily_batch_size(req.size)
    return {"index_daily_batch_size": size}


# ── 五档盘口 sealed 配置 ──────────────────────────────

class LimitLadderMonitorIn(BaseModel):
    enabled: bool


@router.put("/preferences/limit-ladder-monitor")
def update_limit_ladder_monitor(req: LimitLadderMonitorIn, request: Request) -> dict:
    """连板梯队 5 档监控开关。开启→启动 depth 轮询, 关闭→停止。"""
    from app.services import preferences
    preferences.save_server({"limit_ladder_monitor_enabled": req.enabled})

    # 立即应用: 启停 depth 轮询线程
    depth_svc = getattr(request.app.state, "depth_service", None)
    if depth_svc:
        depth_svc.apply_monitor_toggle(req.enabled)

    return {"limit_ladder_monitor_enabled": req.enabled}


@router.post("/preferences/limit-ladder-monitor/run")
def run_limit_ladder_fix(request: Request) -> dict:
    """立即手动修正一次真假板(TickFlow 五档或公开 L1 盘口 + 更新缓存)。"""
    depth_svc = getattr(request.app.state, "depth_service", None)
    if not depth_svc:
        raise HTTPException(status_code=503, detail="depth 服务未初始化")
    return depth_svc.run_once()


class DepthPollingIntervalIn(BaseModel):
    interval: float


@router.put("/preferences/depth-polling-interval")
def update_depth_polling_interval(req: DepthPollingIntervalIn, request: Request) -> dict:
    """保存五档盘口盘中轮询间隔(秒)。公开 L1 / TickFlow 均可用。"""
    from app.services import preferences
    interval = preferences.set_depth_polling_interval(req.interval)
    return {"depth_polling_interval": interval}


class DepthFinalizeTimeIn(BaseModel):
    hour: int
    minute: int


@router.put("/preferences/depth-finalize-time")
def update_depth_finalize_time(req: DepthFinalizeTimeIn, request: Request) -> dict:
    """保存盘后 sealed 定版时间(范围15:01~18:00)并立即 reschedule。"""
    from app.services import preferences
    sched = preferences.set_depth_finalize_time(req.hour, req.minute)

    from apscheduler.triggers.cron import CronTrigger
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        scheduler.reschedule_job(
            "depth_finalize",
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=sched["hour"],
                minute=sched["minute"],
                timezone="Asia/Shanghai",
            ),
        )
        logger.info("depth_finalize rescheduled to %02d:%02d mon-fri", sched["hour"], sched["minute"])

    return sched


class ReviewScheduleIn(BaseModel):
    enabled: bool
    hour: int
    minute: int


@router.put("/preferences/review-schedule")
def update_review_schedule(req: ReviewScheduleIn, request: Request) -> dict:
    """保存定时复盘调度并立即更新 APScheduler job。

    - enabled=True: 注册/更新 job(工作日定时生成复盘报告)
    - enabled=False: 移除 job(停止定时复盘)
    - 校验: 开启时若 AI Key 未配置则拒绝(复盘依赖 AI), 提示用户先配置。
    - 时间下限 15:00(A股收盘), 由 preferences 层强制。
    """
    from app.services import preferences

    if req.enabled:
        # 复盘必须有 AI Key, 否则每日报错刷日志
        from app import secrets_store
        if not secrets_store.get_ai_key():
            raise HTTPException(
                status_code=400,
                detail="复盘依赖 AI,请先在「设置 → AI」配置 API Key 后再开启定时复盘",
            )

    sched = preferences.set_review_schedule(req.enabled, req.hour, req.minute)

    # 动态操作 APScheduler job
    from app.jobs.daily_pipeline import REVIEW_JOB_ID, _register_review_job
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        if sched["enabled"]:
            _register_review_job(scheduler, request.app.state.repo, sched["hour"], sched["minute"])
            logger.info("scheduled_review enabled @%02d:%02d mon-fri", sched["hour"], sched["minute"])
        else:
            try:
                scheduler.remove_job(REVIEW_JOB_ID)
                logger.info("scheduled_review disabled (job removed)")
            except Exception:
                pass  # job 本就不存在(从未开过), 无需处理

    return sched


class ReviewPushIn(BaseModel):
    channels: list[str]  # 多选: feishu / wecom / custom / email; 空数组=不推送
    mode: str | None = None  # 可选: auto=归档即推 / manual=仅显式 push; 不传则不变


@router.put("/preferences/review-push")
def update_review_push(req: ReviewPushIn) -> dict:
    """复盘推送设置(渠道多选 + 触发方式)。

    纯偏好, 与定时复盘 / 实时行情完全独立, 常驻可单独设置。空数组=不推送。
    实际推送由归档端点(POST /api/market-recap/reports)与定时任务(_run_scheduled_review)
    在归档后读取渠道列表, 并按 review_push_mode 决定是否外发:
      - manual: 定时复盘只归档不推送, 手动保存需显式 push=true
      - auto: 归档即推(行为与旧逻辑一致)
    白名单外的渠道会被过滤掉, 白名单外的 mode 值回退 manual。
    """
    from app.services import preferences
    saved = preferences.set_review_push_channels(req.channels)
    mode = preferences.get_review_push_mode()
    if req.mode is not None:
        mode = preferences.set_review_push_mode(req.mode)
    return {"review_push_channels": saved, "review_push_mode": mode}


class PipelineRegimeEnabledIn(BaseModel):
    pipeline_regime_enabled: bool


class RegimeBatchParamsIn(BaseModel):
    batch_days: int | None = None
    warmup_days: int | None = None


@router.post("/preferences/pipeline-regime-enabled")
def update_pipeline_regime_enabled(req: PipelineRegimeEnabledIn) -> dict:
    from app.services import preferences
    enabled = preferences.set_pipeline_regime_enabled(req.pipeline_regime_enabled)
    return {"pipeline_regime_enabled": enabled}


@router.post("/preferences/regime-batch-params")
def update_regime_batch_params(req: RegimeBatchParamsIn) -> dict:
    from app.services import preferences
    return preferences.set_regime_batch_params(req.batch_days, req.warmup_days)


class PluginKeyIn(BaseModel):
    plugin: str
    api_key: str


class DataSourceTimeoutsIn(BaseModel):
    data_source_job_timeout_s: int | None = None
    data_source_long_job_timeout_s: int | None = None


class WatchlistGroupsInNavIn(BaseModel):
    watchlist_groups_in_nav: bool


@router.get("/data-sources")
def list_data_sources() -> dict:
    from app.data_providers import custom as custom_sources

    return {
        "builtin": [{
            "name": "tickflow",
            "display_name": "TickFlow",
            "datasets": ["daily", "adj_factor", "realtime", "minute"],
        }],
        "plugins": custom_sources.list_plugins(),
        "custom": custom_sources.list_sources(),
        "errors": custom_sources.errors(),
        "config_dir": str(custom_sources.data_sources_dir()),
    }


@router.get("/capability-matrix")
def get_capability_matrix() -> dict:
    from app.data_providers.capabilities import build_capability_matrix
    from app.services import preferences
    from app.tickflow.policy import detect_capabilities, tier_label

    capset = detect_capabilities()
    current = {
        "daily_data_provider": preferences.get_daily_data_provider(),
        "adj_factor_provider": preferences.get_adj_factor_provider(),
        "minute_data_provider": preferences.get_minute_data_provider(),
        "realtime_data_provider": preferences.get_realtime_data_provider(),
        "depth5_data_provider": preferences.get_depth5_data_provider(),
        "financial_data_provider": preferences.get_financial_provider(),
        "depth5_data_provider": preferences.get_depth5_data_provider(),
    }
    return build_capability_matrix(current, tickflow_tier=tier_label())


@router.post("/plugin-key")
def save_plugin_key(req: PluginKeyIn) -> dict:
    from app.data_providers import custom as custom_sources
    from app import secrets_store

    name = req.plugin.strip().lower()
    key = req.api_key.strip()
    ok, message = custom_sources.probe_plugin_key(name, key)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    secrets_store.save({f"{name}_api_key": key})
    custom_sources.load_all()
    status = next((p for p in custom_sources.list_plugins() if p["name"] == name), None)
    return {
        "ok": True,
        "message": message,
        "plugin_available": bool(status and status.get("available")),
        "plugin": status,
    }


@router.delete("/plugin-key/{name}")
def clear_plugin_key(name: str) -> dict:
    from app.data_providers import custom as custom_sources
    from app import secrets_store

    secrets_store.clear(f"{name.strip().lower()}_api_key")
    custom_sources.load_all()
    status = next((p for p in custom_sources.list_plugins() if p["name"] == name), None)
    return {
        "ok": True,
        "plugin_available": bool(status and status.get("available")),
        "plugin": status,
    }


@router.post("/data-sources/reload")
def reload_data_sources() -> dict:
    from app.data_providers import custom as custom_sources
    custom_sources.load_all()
    return list_data_sources()


@router.post("/plugins/{name}/install")
def install_plugin(name: str) -> dict:
    from app.data_providers import custom as custom_sources
    ok, message = custom_sources.install_plugin(name)
    custom_sources.load_all()
    result = list_data_sources()
    result["ok"] = ok
    result["message"] = message
    return result


@router.delete("/plugins/{name}/install")
def uninstall_plugin(name: str) -> dict:
    from app.data_providers import custom as custom_sources
    ok, message = custom_sources.uninstall_plugin(name)
    custom_sources.load_all()
    result = list_data_sources()
    result["ok"] = ok
    result["message"] = message
    return result


@router.put("/preferences/watchlist-groups-in-nav")
def update_watchlist_groups_in_nav(req: WatchlistGroupsInNavIn) -> dict:
    from app.services import preferences
    return {"watchlist_groups_in_nav": preferences.set_watchlist_groups_in_nav(req.watchlist_groups_in_nav)}


@router.put("/preferences/data-source-job-timeouts")
def update_data_source_job_timeouts(req: DataSourceTimeoutsIn) -> dict:
    from app.services import preferences
    return preferences.set_data_source_job_timeouts(
        req.data_source_job_timeout_s,
        req.data_source_long_job_timeout_s,
    )


class DataProvidersIn(BaseModel):
    daily_data_provider: str | None = None
    adj_factor_provider: str | None = None
    minute_data_provider: str | None = None
    depth5_data_provider: str | None = None
    realtime_data_provider: str | None = None
    financial_data_provider: str | None = None


class MiningSchedulePrefs(BaseModel):
    mining_schedule_enabled: bool
    mining_schedule_weekday: int = Field(ge=0, le=4)
    mining_budget_profile: str = "balanced"


class CustomSourceIn(BaseModel):
    name: str
    display_name: str = ""
    auth: dict = {}
    datasets: dict = {}


class CustomSourceTestIn(BaseModel):
    provider: str
    dataset: str
    symbols: list[str] | None = None
    config: CustomSourceIn | None = None


@router.put("/preferences/data-providers")
def update_data_providers(req: DataProvidersIn, request: Request) -> dict:
    from app.services import preferences
    updates = req.model_dump(exclude_none=True)
    if "financial_data_provider" in updates:
        updates["financial_provider"] = updates["financial_data_provider"]
    if updates:
        preferences.save(updates)
    try:
        request.app.state.capabilities = detect_capabilities()
    except Exception as exc:  # noqa: BLE001
        logger.warning("capability refresh after data-provider change failed: %s", exc)
    return {
        "daily_data_provider": preferences.get_daily_data_provider(),
        "adj_factor_provider": preferences.get_adj_factor_provider(),
        "minute_data_provider": preferences.get_minute_data_provider(),
        "depth5_data_provider": preferences.get_depth5_data_provider(),
        "realtime_data_provider": preferences.get_realtime_data_provider(),
        "financial_data_provider": preferences.get_financial_provider(),
    }


@router.put("/preferences/mining-schedule")
def update_mining_schedule(req: MiningSchedulePrefs) -> dict:
    from app.services import preferences
    return preferences.set_mining_schedule(
        req.mining_schedule_enabled,
        req.mining_schedule_weekday,
        req.mining_budget_profile,
    )


@router.get("/data-sources/{name}")
def get_data_source(name: str) -> dict:
    from app.data_providers import custom as custom_sources
    cfg = custom_sources.get_config_dict(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"数据源 '{name}' 不存在")
    return cfg


@router.post("/data-sources")
def save_data_source(req: CustomSourceIn) -> dict:
    from app.data_providers import custom as custom_sources
    config = req.model_dump()
    config["name"] = (config.get("name") or "").lower()
    try:
        custom_sources.save_config(config["name"], config)
        custom_sources.load_all()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return list_data_sources()


@router.delete("/data-sources/{name}")
def delete_data_source(name: str, request: Request) -> dict:
    from app.data_providers import custom as custom_sources
    from app.services import preferences
    try:
        custom_sources.delete_config(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    custom_sources.load_all()
    updates: dict = {}
    if preferences.get_daily_data_provider() == name:
        updates["daily_data_provider"] = "tickflow"
    if preferences.get_realtime_data_provider() == name:
        updates["realtime_data_provider"] = "tickflow"
    if preferences.get_financial_provider() == name:
        updates["financial_provider"] = "tickflow"
        updates["financial_data_provider"] = "tickflow"
    if preferences.get_adj_factor_provider() == name:
        updates["adj_factor_provider"] = "tickflow"
    if updates:
        preferences.save(updates)
    try:
        request.app.state.capabilities = detect_capabilities()
    except Exception as exc:  # noqa: BLE001
        logger.warning("capability refresh after data-source delete failed: %s", exc)
    return list_data_sources()


@router.post("/data-sources/test")
def test_data_source(req: CustomSourceTestIn) -> dict:
    from app.data_providers import custom as custom_sources
    temporary = req.config is not None
    provider = None
    try:
        if req.config:
            config = req.config.model_dump()
            dataset_config = (config.get("datasets") or {}).get(req.dataset)
            if dataset_config is None:
                raise ValueError(f"dataset '{req.dataset}' is not configured")
            config["datasets"] = {req.dataset: dataset_config}
            provider = custom_sources.create_provider(config)
        else:
            provider = custom_sources.get_provider(req.provider)
        return provider.test_dataset(req.dataset, req.symbols)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"自定义数据源测试失败: {e}") from e
    finally:
        if temporary and provider is not None:
            provider.close()


@router.get("/minute-refresh/status")
def minute_refresh_status(request: Request) -> dict:
    svc = getattr(request.app.state, "minute_refresh", None)
    if svc is None:
        return {"available": False, "enabled": False, "running": False}
    payload = dict(svc.status())
    payload["available"] = True
    return payload

