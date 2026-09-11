import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from app.api import auth as auth_api
from app.api import routes
from app.config import settings


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443),
            "scheme": "https",
        }
    )


def _forwarded_request(peer: str, forwarded: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/setup",
            "headers": [(b"x-forwarded-for", forwarded.encode("ascii"))],
            "client": (peer, 12345),
            "server": ("testserver", 443),
            "scheme": "https",
        }
    )


def test_health_exposes_release_identity(monkeypatch):
    monkeypatch.setattr(routes.tf_client, "current_mode", lambda: "none")
    monkeypatch.setattr(settings, "release_channel", "private")
    monkeypatch.setattr(settings, "build_sha", "abc123")

    payload = routes.health()

    assert payload["release_channel"] == "private"
    assert payload["build_sha"] == "abc123"


def test_login_cookie_can_be_forced_secure(monkeypatch):
    monkeypatch.setattr(auth_api.auth, "is_configured", lambda: True)
    monkeypatch.setattr(auth_api.auth, "verify_and_create_session", lambda _password: "token")
    monkeypatch.setattr(settings, "cookie_secure", True)
    response = Response()

    result = auth_api.login(
        auth_api.LoginIn(password="secret"),
        _request(),
        response,
    )

    assert result == {"ok": True, "authenticated": True, "user": None}
    assert "Secure" in response.headers["set-cookie"]


def test_untrusted_peer_cannot_spoof_forwarded_client_ip(monkeypatch):
    monkeypatch.setattr(settings, "auth_trusted_proxy_ips", "")
    request = _forwarded_request("203.0.113.10", "127.0.0.1")

    assert auth_api._client_ip(request) == "203.0.113.10"
    with pytest.raises(HTTPException) as exc_info:
        auth_api.setup_password(auth_api.PasswordIn(password="secret1"), request)

    assert exc_info.value.status_code == 403


def test_configured_proxy_may_forward_the_original_client_ip(monkeypatch):
    monkeypatch.setattr(settings, "auth_trusted_proxy_ips", "10.0.0.5")
    request = _forwarded_request("10.0.0.5", "192.168.1.20")

    assert auth_api._client_ip(request) == "192.168.1.20"


def test_trusted_proxy_ignores_spoofed_leftmost_forwarded_hop(monkeypatch):
    monkeypatch.setattr(settings, "auth_trusted_proxy_ips", "10.42.0.1")
    request = _forwarded_request(
        "10.42.0.1",
        "127.0.0.1, 198.51.100.24",
    )

    assert auth_api._client_ip(request) == "198.51.100.24"


def test_trusted_proxy_chain_skips_other_trusted_proxy_hops(monkeypatch):
    monkeypatch.setattr(
        settings,
        "auth_trusted_proxy_ips",
        "10.42.0.1,10.7.10.139",
    )
    request = _forwarded_request(
        "10.42.0.1",
        "198.51.100.24, 10.7.10.139",
    )

    assert auth_api._client_ip(request) == "198.51.100.24"
