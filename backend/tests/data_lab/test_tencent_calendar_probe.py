"""Tencent open-day probe unit tests (mocked transport)."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.data_lab.sources.tencent_calendar_probe import (
    TencentCalendarProbeError,
    fetch_tencent_open_days,
)


def test_fetch_tencent_open_days_parses_mock() -> None:
    payload = {
        "code": 0,
        "msg": "",
        "data": {
            "sh000001": {
                "day": [
                    ["2026-07-01", "1", "1", "1", "1", "1"],
                    ["2026-07-02", "1", "1", "1", "1", "1"],
                    ["2026-07-04", "1", "1", "1", "1", "1"],
                ]
            }
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "sh000001" in str(request.url)
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        days = fetch_tencent_open_days(
            code="sh000001",
            start=date(2026, 7, 1),
            end=date(2026, 7, 21),
            client=client,
        )
    assert days == [date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 4)]


def test_fetch_tencent_open_days_empty_fails() -> None:
    payload = {"code": 0, "msg": "param error", "data": []}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(TencentCalendarProbeError),
    ):
        fetch_tencent_open_days(
            start=date(2026, 1, 1),
            end=date(2026, 1, 31),
            client=client,
            retries=0,
        )
