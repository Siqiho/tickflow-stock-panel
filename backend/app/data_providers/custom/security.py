"""URL safety checks for custom HTTP providers (SSRF mitigation)."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeURLError(ValueError):
    """Raised when a custom source URL is blocked for safety."""


def assert_safe_url(url: str, *, allow_private: bool = False) -> None:
    """Reject obviously unsafe destinations.

    - only http/https
    - block localhost/private/link-local/metadata hosts unless allow_private
    """
    parsed = urlparse(url or "")
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURLError(f"unsupported URL scheme: {parsed.scheme!r}")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise UnsafeURLError("URL host is required")

    if host in {"localhost", "metadata.google.internal"}:
        if not allow_private:
            raise UnsafeURLError(f"blocked host: {host}")
        return

    # literal IP
    try:
        ip = ipaddress.ip_address(host)
        if not allow_private and (
            ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
        ):
            raise UnsafeURLError(f"blocked IP address: {host}")
        return
    except ValueError:
        pass

    if allow_private:
        return

    # resolve DNS and inspect all A/AAAA records
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise UnsafeURLError(f"cannot resolve host: {host}") from e
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UnsafeURLError(f"host resolves to blocked address: {host} -> {addr}")
