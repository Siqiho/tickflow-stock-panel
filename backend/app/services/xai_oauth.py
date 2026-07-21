"""xAI / Grok OAuth (device code) — 参考 anomalyco/opencode Grok-CLI 客户端。

使用 xAI 公开的 Grok-CLI OAuth client_id + RFC 8628 device authorization grant，
适配本机桌面后端：用户在任意浏览器完成 SuperGrok 登录，后端轮询换取 token。
"""
from __future__ import annotations

import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app import secrets_store

logger = logging.getLogger(__name__)

# Public Grok-CLI OAuth client (same as opencode / hermes-agent).
CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
AUTHORIZE_URL = "https://auth.x.ai/oauth2/authorize"
TOKEN_URL = "https://auth.x.ai/oauth2/token"
DEVICE_AUTHORIZATION_URL = "https://auth.x.ai/oauth2/device/code"
DEVICE_CODE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
SCOPE = "openid profile email offline_access grok-cli:access api:access"

XAI_API_BASE = "https://api.x.ai/v1"
DEFAULT_MODEL = "grok-4.5"

DEVICE_CODE_DEFAULT_INTERVAL_S = 5
DEVICE_CODE_MIN_INTERVAL_S = 1
DEVICE_CODE_SLOW_DOWN_INCREMENT_S = 5
DEVICE_CODE_DEFAULT_EXPIRES_S = 300
ACCESS_TOKEN_REFRESH_SKEW_S = 120

# secrets.json keys
SK_ACCESS = "ai_xai_access_token"
SK_REFRESH = "ai_xai_refresh_token"
SK_EXPIRES = "ai_xai_expires_at"
SK_AUTH_TYPE = "ai_xai_auth_type"  # oauth | api_key

USER_AGENT = "one-trading-xai-oauth/1.0"


class XaiOAuthError(RuntimeError):
    pass


def _http_form(url: str, data: dict[str, str], *, timeout: float = 30.0) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(detail) if detail else {}
        except json.JSONDecodeError:
            payload = {"error": detail or e.reason}
        err = payload.get("error") or str(e.reason)
        desc = payload.get("error_description") or ""
        raise XaiOAuthError(f"{err}{(': ' + desc) if desc else ''}") from e
    except urllib.error.URLError as e:
        raise XaiOAuthError(f"网络错误: {e.reason}") from e


def request_device_code() -> dict[str, Any]:
    """Start device authorization. Returns device_code, user_code, verification_uri, etc."""
    data = _http_form(
        DEVICE_AUTHORIZATION_URL,
        {
            "client_id": CLIENT_ID,
            "scope": SCOPE,
        },
    )
    if not data.get("device_code") or not data.get("user_code") or not data.get("verification_uri"):
        raise XaiOAuthError("xAI device code 响应缺少必要字段")
    return {
        "device_code": data["device_code"],
        "user_code": data["user_code"],
        "verification_uri": data.get("verification_uri") or "https://auth.x.ai/device",
        "verification_uri_complete": data.get("verification_uri_complete") or "",
        "expires_in": int(data.get("expires_in") or DEVICE_CODE_DEFAULT_EXPIRES_S),
        "interval": max(int(data.get("interval") or DEVICE_CODE_DEFAULT_INTERVAL_S), DEVICE_CODE_MIN_INTERVAL_S),
    }


def attempt_device_token(device_code: str) -> dict[str, Any]:
    """Single token poll attempt.

    Returns:
      {"status": "authorized", "tokens": {...}}
      {"status": "pending", "slow_down": bool}
    Raises XaiOAuthError on terminal errors.
    """
    try:
        data = _http_form(
            TOKEN_URL,
            {
                "grant_type": DEVICE_CODE_GRANT_TYPE,
                "client_id": CLIENT_ID,
                "device_code": device_code,
            },
        )
        if data.get("access_token"):
            return {"status": "authorized", "tokens": data}
        return {"status": "pending", "slow_down": False}
    except XaiOAuthError as e:
        msg = str(e)
        if "authorization_pending" in msg:
            return {"status": "pending", "slow_down": False}
        if "slow_down" in msg:
            return {"status": "pending", "slow_down": True}
        if "access_denied" in msg or "authorization_denied" in msg:
            raise XaiOAuthError("用户拒绝了 xAI 授权") from e
        if "expired_token" in msg:
            raise XaiOAuthError("设备码已过期，请重新登录") from e
        raise


def poll_device_token(device_code: str, *, interval: int | None = None, expires_in: int | None = None) -> dict[str, Any]:
    """Block until user authorizes or timeout. Returns token response."""
    interval_s = max(interval or DEVICE_CODE_DEFAULT_INTERVAL_S, DEVICE_CODE_MIN_INTERVAL_S)
    deadline = time.time() + max(expires_in or DEVICE_CODE_DEFAULT_EXPIRES_S, 30)

    while time.time() < deadline:
        result = attempt_device_token(device_code)
        if result.get("status") == "authorized":
            return result["tokens"]
        if result.get("slow_down"):
            interval_s += DEVICE_CODE_SLOW_DOWN_INCREMENT_S
        time.sleep(interval_s)

    raise XaiOAuthError("xAI 设备授权超时，请重试")


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    data = _http_form(
        TOKEN_URL,
        {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": refresh_token,
        },
    )
    if not data.get("access_token"):
        raise XaiOAuthError("刷新 access token 失败")
    return data


def _jwt_exp(token: str) -> int | None:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        pad = "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
        exp = payload.get("exp")
        return int(exp) if exp is not None else None
    except Exception:  # noqa: BLE001
        return None


def save_oauth_tokens(token_response: dict[str, Any]) -> dict[str, Any]:
    access = token_response.get("access_token") or ""
    refresh = token_response.get("refresh_token") or secrets_store.load().get(SK_REFRESH) or ""
    expires_in = int(token_response.get("expires_in") or 3600)
    expires_at = int(time.time()) + expires_in
    jwt_exp = _jwt_exp(access)
    if jwt_exp:
        expires_at = min(expires_at, jwt_exp)

    secrets_store.save({
        SK_AUTH_TYPE: "oauth",
        SK_ACCESS: access,
        SK_REFRESH: refresh,
        SK_EXPIRES: str(expires_at),
        # OAuth 模式下不再依赖手动 API Key；清空避免混淆
        "ai_api_key": "",
        "ai_provider": "xai",
        "ai_base_url": XAI_API_BASE,
    })
    return status()


def clear_oauth_tokens() -> None:
    secrets_store.clear(SK_ACCESS, SK_REFRESH, SK_EXPIRES, SK_AUTH_TYPE)


def has_oauth() -> bool:
    data = secrets_store.load()
    return bool(data.get(SK_ACCESS) or data.get(SK_REFRESH))


def status() -> dict[str, Any]:
    data = secrets_store.load()
    auth_type = data.get(SK_AUTH_TYPE) or ("oauth" if data.get(SK_ACCESS) else "")
    expires_raw = data.get(SK_EXPIRES) or "0"
    try:
        expires_at = int(expires_raw)
    except (TypeError, ValueError):
        expires_at = 0
    return {
        "auth_type": auth_type or None,
        "has_oauth": bool(data.get(SK_ACCESS) or data.get(SK_REFRESH)),
        "has_access_token": bool(data.get(SK_ACCESS)),
        "expires_at": expires_at or None,
        "expired": bool(expires_at and expires_at <= int(time.time())),
    }


def get_valid_access_token() -> str | None:
    """Return a usable OAuth access token, refreshing if needed."""
    data = secrets_store.load()
    access = data.get(SK_ACCESS) or ""
    refresh = data.get(SK_REFRESH) or ""
    if not access and not refresh:
        return None

    now = int(time.time())
    try:
        expires_at = int(data.get(SK_EXPIRES) or 0)
    except (TypeError, ValueError):
        expires_at = 0
    jwt_exp = _jwt_exp(access) if access else None
    expiring = (
        not access
        or not expires_at
        or expires_at - now <= ACCESS_TOKEN_REFRESH_SKEW_S
        or (jwt_exp is not None and jwt_exp - now <= ACCESS_TOKEN_REFRESH_SKEW_S)
    )
    if not expiring:
        return access

    if not refresh:
        return access or None

    try:
        tokens = refresh_access_token(refresh)
        save_oauth_tokens(tokens)
        return tokens.get("access_token") or None
    except XaiOAuthError as e:
        logger.warning("xAI token refresh failed: %s", e)
        return access or None
