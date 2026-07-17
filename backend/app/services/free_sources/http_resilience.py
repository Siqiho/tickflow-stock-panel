"""Timeout / cooldown / in-flight dedupe helpers for free public HTTP sources."""
from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

import httpx


@dataclass
class FetchResult:
    ok: bool
    data: Any = None
    error: str | None = None
    status_code: int | None = None
    text: str | None = None


class CooldownRegistry:
    def __init__(self) -> None:
        self._until: dict[str, float] = {}
        self._lock = threading.Lock()

    def trip(self, key: str, seconds: float) -> None:
        with self._lock:
            self._until[key] = max(self._until.get(key, 0.0), time.monotonic() + max(0.0, float(seconds)))

    def is_cooling(self, key: str) -> bool:
        with self._lock:
            return time.monotonic() < self._until.get(key, 0.0)

    def remaining(self, key: str) -> float:
        with self._lock:
            return max(0.0, self._until.get(key, 0.0) - time.monotonic())

    def clear(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._until.clear()
            else:
                self._until.pop(key, None)


class InFlightDeduper:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inflight: dict[str, Future] = {}

    def run(self, key: str, fn: Callable[[], Any]) -> Any:
        with self._lock:
            existing = self._inflight.get(key)
            if existing is not None:
                fut = existing
                owner = False
            else:
                fut = Future()
                self._inflight[key] = fut
                owner = True
        if not owner:
            return fut.result()
        try:
            val = fn()
        except Exception as exc:  # noqa: BLE001
            fut.set_exception(exc)
            with self._lock:
                self._inflight.pop(key, None)
            raise
        else:
            fut.set_result(val)
            with self._lock:
                self._inflight.pop(key, None)
            return val


class ResilientHttpClient:
    """Small shared client for free public endpoints.

    Partial failure is expressed per URL via FetchResult; callers decide degrade policy.
    """

    def __init__(self, default_timeout: float = 8.0, max_workers: int = 4) -> None:
        self.default_timeout = default_timeout
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="free-http")
        self.cooldown = CooldownRegistry()
        self.deduper = InFlightDeduper()

    def _get(
        self,
        url: str,
        *,
        headers: dict | None = None,
        timeout: float | None = None,
        params: dict | None = None,
    ) -> httpx.Response:
        return httpx.get(
            url,
            headers=headers or {},
            params=params,
            timeout=timeout or self.default_timeout,
            follow_redirects=True,
        )

    def get_json(
        self,
        url: str,
        *,
        source_key: str | None = None,
        headers: dict | None = None,
        timeout: float | None = None,
        params: dict | None = None,
        cooldown_on_error: float = 30.0,
        parse_json: bool = True,
    ) -> FetchResult:
        key = source_key or url
        if self.cooldown.is_cooling(key):
            return FetchResult(ok=False, error=f"cooldown {self.cooldown.remaining(key):.1f}s")

        def work() -> FetchResult:
            try:
                resp = self._get(url, headers=headers, timeout=timeout, params=params)
                if resp.status_code >= 400:
                    self.cooldown.trip(key, cooldown_on_error)
                    return FetchResult(
                        ok=False,
                        error=f"HTTP {resp.status_code}",
                        status_code=resp.status_code,
                        text=resp.text[:500],
                    )
                data = None
                if parse_json:
                    data = resp.json()
                return FetchResult(
                    ok=True,
                    data=data,
                    status_code=resp.status_code,
                    text=None if parse_json else resp.text,
                )
            except Exception as exc:  # noqa: BLE001
                self.cooldown.trip(key, cooldown_on_error)
                return FetchResult(ok=False, error=str(exc))

        return self.deduper.run(f"GET:{key}:{url}:{params}", work)

    def get_text(
        self,
        url: str,
        *,
        source_key: str | None = None,
        headers: dict | None = None,
        timeout: float | None = None,
        cooldown_on_error: float = 30.0,
    ) -> FetchResult:
        key = source_key or url
        if self.cooldown.is_cooling(key):
            return FetchResult(ok=False, error=f"cooldown {self.cooldown.remaining(key):.1f}s")

        def work() -> FetchResult:
            try:
                resp = self._get(url, headers=headers, timeout=timeout)
                if resp.status_code >= 400:
                    self.cooldown.trip(key, cooldown_on_error)
                    return FetchResult(ok=False, error=f"HTTP {resp.status_code}", status_code=resp.status_code)
                return FetchResult(ok=True, text=resp.text, status_code=resp.status_code)
            except Exception as exc:  # noqa: BLE001
                self.cooldown.trip(key, cooldown_on_error)
                return FetchResult(ok=False, error=str(exc))

        return self.deduper.run(f"GETTEXT:{key}:{url}", work)

    def get_many(
        self,
        items: list[tuple[str, str]],
        *,
        headers: dict | None = None,
    ) -> dict[str, FetchResult]:
        futs = {
            name: self._executor.submit(self.get_json, url, source_key=name, headers=headers)
            for name, url in items
        }
        return {name: fut.result() for name, fut in futs.items()}


_DEFAULT_CLIENT: ResilientHttpClient | None = None


def get_shared_client() -> ResilientHttpClient:
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = ResilientHttpClient()
    return _DEFAULT_CLIENT
