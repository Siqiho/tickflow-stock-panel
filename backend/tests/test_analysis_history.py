from __future__ import annotations

import pytest

from app.config import settings
from app.services import ai_reports, market_recap_reports, stock_reports, user_context
from app.services.analysis_history import (
    get_analysis_history_report,
    list_analysis_history,
)


@pytest.fixture
def isolated_history(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    return tmp_path / "data"


def _principal(user_id: str) -> dict[str, str]:
    return {"id": user_id, "username": user_id, "role": "user"}


def test_analysis_history_is_compact_and_current_account_scoped(isolated_history):
    alice = _principal("usr_alice")
    bob = _principal("usr_bob")

    token = user_context.bind(alice)
    try:
        stock_reports.save_report(
            {
                "id": "sar_alice",
                "symbol": "600519.sh",
                "name": "贵州茅台",
                "focus": "估值",
                "content": "ALICE_STOCK_BODY",
                "summary": "个股摘要",
                "created_at": "2026-08-12T02:00:00",
            }
        )
        ai_reports.save_report(
            {
                "id": "rpt_alice",
                "symbol": "600519.SH",
                "name": "贵州茅台",
                "content": "ALICE_FINANCIAL_BODY",
                "summary": "财务摘要",
                "periods": 4,
                "created_at": "2026-08-12T01:00:00",
            }
        )
        market_recap_reports.save_report(
            {
                "id": "mkr_alice",
                "as_of": "2026-08-11",
                "content": "ALICE_RECAP_BODY",
                "summary": "复盘摘要",
                "emotion_label": "偏暖",
                "created_at": "2026-08-12T00:00:00",
            }
        )

        index = list_analysis_history()
        filtered = list_analysis_history(symbol="600519.sh")
        detail = get_analysis_history_report("stock", "sar_alice")
    finally:
        user_context.reset(token)

    assert index["scope"] == "current_account"
    assert index["mode"] == "read-only"
    assert index["total"] == 3
    assert [item["id"] for item in index["reports"]] == [
        "sar_alice",
        "rpt_alice",
        "mkr_alice",
    ]
    assert all("content" not in item for item in index["reports"])
    assert {item["kind"] for item in filtered["reports"]} == {"stock", "financial"}
    assert detail is not None
    assert detail["report"]["symbol"] == "600519.SH"
    assert detail["report"]["content"] == "ALICE_STOCK_BODY"

    token = user_context.bind(bob)
    try:
        stock_reports.save_report(
            {
                "id": "sar_bob",
                "symbol": "000001.SZ",
                "content": "BOB_PRIVATE_BODY",
                "created_at": "2026-08-12T03:00:00",
            }
        )
        bob_index = list_analysis_history()
    finally:
        user_context.reset(token)

    assert [item["id"] for item in bob_index["reports"]] == ["sar_bob"]
    assert (
        isolated_history / "tenants" / "usr_alice" / "user_data" / "ai_stock_reports.json"
    ).is_file()
    assert (
        isolated_history / "tenants" / "usr_bob" / "user_data" / "ai_stock_reports.json"
    ).is_file()

    token = user_context.bind(alice)
    try:
        assert get_analysis_history_report("stock", "sar_bob") is None
        assert "sar_bob" not in {item["id"] for item in list_analysis_history()["reports"]}
    finally:
        user_context.reset(token)


def test_analysis_history_rejects_unknown_kind(isolated_history):
    token = user_context.bind(_principal("usr_alice"))
    try:
        with pytest.raises(ValueError, match="不支持"):
            list_analysis_history(kind="orders")
        with pytest.raises(ValueError, match="不支持"):
            get_analysis_history_report("orders", "anything")
    finally:
        user_context.reset(token)
