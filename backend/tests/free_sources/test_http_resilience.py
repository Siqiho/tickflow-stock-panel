from __future__ import annotations

import concurrent.futures
import time

from app.services.free_sources.http_resilience import (
    CooldownRegistry,
    InFlightDeduper,
    ResilientHttpClient,
)


def test_cooldown_blocks_until_elapsed():
    reg = CooldownRegistry()
    reg.trip("eastmoney", seconds=0.15)
    assert reg.is_cooling("eastmoney") is True
    time.sleep(0.2)
    assert reg.is_cooling("eastmoney") is False


def test_inflight_dedupes_same_key():
    deduper = InFlightDeduper()
    calls = {"n": 0}

    def slow():
        calls["n"] += 1
        time.sleep(0.1)
        return "v"

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(deduper.run, "same", slow) for _ in range(4)]
        vals = [f.result() for f in futs]
    assert vals == ["v", "v", "v", "v"]
    assert calls["n"] == 1


def test_client_returns_partial_on_one_failure(monkeypatch):
    client = ResilientHttpClient(default_timeout=1.0)

    def fake_get(url, **kwargs):
        if "bad" in url:
            raise TimeoutError("boom")

        class R:
            status_code = 200

            def json(self):
                return {"ok": True}

            text = "{}"

        return R()

    monkeypatch.setattr(client, "_get", fake_get)
    results = client.get_many(
        [
            ("good", "https://example.com/good"),
            ("bad", "https://example.com/bad"),
        ]
    )
    assert results["good"].ok is True
    assert results["bad"].ok is False
    assert results["bad"].error
