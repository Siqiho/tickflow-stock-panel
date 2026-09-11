"""Multi-user authentication API.

端点:
  GET  /api/auth/status        — 是否已设密码、当前会话是否有效
  POST /api/auth/setup         — 首次设置密码(仅限本机/内网, 防公网抢占)
  POST /api/auth/login         — 登录(密码 → 会话 token, 含限流)
  POST /api/auth/logout        — 注销当前会话
  POST /api/auth/change-password — 改密码(需已登录)

安全:
  - setup 端点只接受本机/内网请求(request.client.host), 公网请求 403。
    否则黑客可比用户更早扫到域名, 抢先设密码, 反客为主。
  - login 限流: 同一来源 IP 连续失败 5 次, 锁 5 分钟(内存计数)。
  - 会话 token 通过 HttpOnly cookie 下发, 前端无需手动管理。
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from ipaddress import ip_address
from threading import Lock

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.config import settings
from app.services import auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "tf_session"

# 限流: { ip: (fail_count, lock_until_ts) }
_fail_counter: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))
_fail_lock = Lock()
_MAX_FAILS = 5
_LOCK_SECONDS = 300


def _is_local_network(host: str | None) -> bool:
    """是否本机或内网请求。

    反向代理(Nginx)场景下 request.client.host 是代理本身(127.0.0.1),
    需信任 X-Forwarded-For 的最左(原始客户端)。本项目部署若经反代,
    请在反代配置正确的 X-Forwarded-For(标准做法)。
    """
    if not host:
        return False
    if host in ("127.0.0.1", "::1", "localhost"):
        return True
    # 内网网段: 10.x / 172.16-31.x / 192.168.x
    if host.startswith("10.") or host.startswith("192.168."):
        return True
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
            if 16 <= second <= 31:
                return True
        except (IndexError, ValueError):
            pass
    return False


def _peer_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _trusted_proxy_ips() -> set[str]:
    trusted: set[str] = set()
    for item in (settings.auth_trusted_proxy_ips or "").split(","):
        candidate = item.strip()
        if not candidate:
            continue
        try:
            trusted.add(str(ip_address(candidate)))
        except ValueError:
            logger.warning("ignoring invalid trusted proxy IP: %s", candidate)
    return trusted


def _normalized_ip(value: str) -> str | None:
    try:
        return str(ip_address(value.strip()))
    except ValueError:
        return None


def _client_ip(request: Request) -> str:
    """Resolve the nearest untrusted client hop from a trusted proxy chain.

    A caller can pre-populate the left side of ``X-Forwarded-For``.  Walking
    from the direct peer towards the client prevents that caller-controlled
    prefix from becoming the rate-limit or registration identity.
    """
    raw_peer = _peer_ip(request)
    peer = _normalized_ip(raw_peer)
    trusted = _trusted_proxy_ips()
    if peer is None or peer not in trusted:
        return peer or raw_peer

    xff = request.headers.get("x-forwarded-for")
    if not xff:
        return peer

    for item in reversed(xff.split(",")):
        candidate = _normalized_ip(item)
        if candidate is not None and candidate not in trusted:
            return candidate

    # A forwarded request with no valid untrusted hop is incomplete or
    # malformed.  Fail closed instead of treating the trusted proxy itself as
    # a local client (which would weaken the first-admin setup guard).
    return "unknown"


def _check_login_rate_limit(ip: str) -> None:
    """登录失败限流检查, 触发则抛 429。"""
    with _fail_lock:
        _count, until = _fail_counter.get(ip, (0, 0.0))
        now = time.time()
        if until > now:
            wait = int(until - now)
            raise HTTPException(
                status_code=429,
                detail=f"登录失败次数过多, 请 {wait} 秒后重试",
            )


def _record_login_fail(ip: str) -> None:
    """记录一次登录失败, 达阈值则锁定。"""
    with _fail_lock:
        count, until = _fail_counter.get(ip, (0, 0.0))
        count += 1
        if count >= _MAX_FAILS:
            until = time.time() + _LOCK_SECONDS
            logger.warning("auth login locked for %s after %d fails", ip, count)
        _fail_counter[ip] = (count, until)


def _clear_login_fails(ip: str) -> None:
    """登录成功后清除该 IP 的失败计数。"""
    with _fail_lock:
        _fail_counter.pop(ip, None)


# ================================================================
# 端点
# ================================================================


class PasswordIn(BaseModel):
    password: str = Field(min_length=auth.MIN_PASSWORD_LENGTH, max_length=128)


class LoginIn(BaseModel):
    username: str | None = Field(default=None, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=auth.MIN_PASSWORD_LENGTH, max_length=128)
    invite_code: str = Field(default="", max_length=128)


class ChangePasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=auth.MIN_PASSWORD_LENGTH, max_length=128)


@router.get("/status")
def auth_status(request: Request) -> dict:
    """Return identity, registration policy, and the caller's AI quota."""
    token = request.cookies.get(COOKIE_NAME)
    user = auth.authenticate_session(token or "")
    return {
        "configured": auth.is_configured(),
        "authenticated": user is not None,
        "multi_user": True,
        "registration_enabled": settings.public_registration_enabled,
        "invite_required": bool(settings.public_registration_invite_code),
        "user": auth.public_user(user),
        "ai_quota": auth.quota_status(user) if user else None,
    }


@router.post("/setup")
def setup_password(req: PasswordIn, request: Request) -> dict:
    """首次设置访问密码。仅限本机/内网请求(防公网抢占)。

    若已设置过密码, 返回 409(改密码走 /change-password)。
    """
    # 关键: 限制只有服务器主人(本机/内网)能设密码
    peer_ip = _peer_ip(request)
    if request.headers.get("x-forwarded-for") and peer_ip not in _trusted_proxy_ips():
        logger.warning("setup rejected from untrusted forwarded peer: %s", peer_ip)
        raise HTTPException(
            status_code=403,
            detail="首次设置密码不接受未受信任代理转发的来源地址",
        )
    client_ip = _client_ip(request)
    if not _is_local_network(client_ip):
        logger.warning("setup rejected from non-local ip: %s", client_ip)
        raise HTTPException(
            status_code=403,
            detail="首次设置密码仅允许本机或内网访问,请通过 SSH/本地浏览器操作",
        )

    if auth.is_configured():
        raise HTTPException(status_code=409, detail="密码已设置,如需修改请登录后使用改密码功能")

    auth.set_password(req.password)
    logger.info("access password set up from %s", client_ip)
    return {"ok": True, "configured": True}


@router.post("/login")
def login(req: LoginIn, request: Request, response: Response) -> dict:
    """Authenticate one account and issue an HttpOnly session cookie."""
    ip = _client_ip(request)
    _check_login_rate_limit(ip)

    if not auth.is_configured():
        raise HTTPException(status_code=409, detail="尚未设置访问密码")

    token = (
        auth.verify_and_create_session(req.password, req.username)
        if req.username
        else auth.verify_and_create_session(req.password)
    )
    if not token:
        _record_login_fail(ip)
        raise HTTPException(status_code=401, detail="密码错误")

    _clear_login_fails(ip)
    # HttpOnly: 防 XSS 窃取; SameSite=Lax: 防 CSRF; Path=/: 全站生效
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=max(1, settings.user_session_ttl_days) * 24 * 3600,
        httponly=True,
        samesite="lax",
        path="/",
        secure=settings.cookie_secure,
    )
    user = auth.authenticate_session(token)
    return {
        "ok": True,
        "authenticated": True,
        "user": auth.public_user(user),
    }


@router.post("/register")
def register(req: RegisterIn, request: Request, response: Response) -> dict:
    """Create a public user when the deployment registration gate is enabled."""
    ip = _client_ip(request)
    _check_login_rate_limit(ip)
    try:
        user, token = auth.register_user(req.username, req.password, req.invite_code, ip)
    except PermissionError as exc:
        status_code = 429 if "上限" in str(exc) else 403
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except ValueError as exc:
        _record_login_fail(ip)
        raise HTTPException(
            status_code=409 if "已存在" in str(exc) else 400, detail=str(exc)
        ) from exc
    _clear_login_fails(ip)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=max(1, settings.user_session_ttl_days) * 24 * 3600,
        httponly=True,
        samesite="lax",
        path="/",
        secure=settings.cookie_secure,
    )
    return {"ok": True, "authenticated": True, "user": auth.public_user(user)}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    """注销当前会话。"""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        auth.revoke_session(token)
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/change-password")
def change_password(req: ChangePasswordIn, request: Request) -> dict:
    """修改密码: 需验证旧密码, 成功后所有会话失效(含当前, 需重新登录)。"""
    token = request.cookies.get(COOKIE_NAME) or ""
    user = auth.authenticate_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")

    if not auth.is_configured():
        raise HTTPException(status_code=409, detail="尚未设置访问密码")

    try:
        auth.change_password(user["id"], req.old_password, req.new_password)
    except PermissionError as exc:
        ip = _client_ip(request)
        _record_login_fail(ip)
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "message": "密码已修改, 请重新登录"}
