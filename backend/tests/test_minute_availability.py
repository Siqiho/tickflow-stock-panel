from __future__ import annotations

from app.tickflow.capabilities import (
    Cap,
    CapabilityLimits,
    CapabilitySet,
    feature_availability,
    minute_availability,
)


def _capset(*caps: Cap) -> CapabilitySet:
    return CapabilitySet({c: CapabilityLimits(rpm=60, batch=100) for c in caps})


def test_minute_unavailable_without_caps():
    info = minute_availability(_capset(Cap.KLINE_DAILY_BATCH), user_enabled=True)
    # full-market sync still locked; single-symbol view unlocked via public fallback
    assert info["available"] is False
    assert info.get("view_available") is True
    assert info["status"] == "public_fallback"
    assert info["reason_code"] == "public_fallback"
    assert info["full_market_sync_allowed"] is False
    assert "分钟" in (info["reason"] or "") or "公开" in (info["reason"] or "")
    assert info["single_symbol_fallback"] == "free_public_intraday"


def test_minute_disabled_by_user_when_cap_present():
    info = minute_availability(_capset(Cap.KLINE_MINUTE_BATCH), user_enabled=False)
    assert info["available"] is True
    assert info["status"] == "disabled_by_user"
    assert info["reason_code"] == "user_disabled"
    assert info["full_market_sync_allowed"] is True


def test_minute_available_when_cap_and_enabled():
    info = minute_availability(_capset(Cap.KLINE_MINUTE_BATCH), user_enabled=True)
    assert info["status"] == "available"
    assert info["reason_code"] == "ok"
    assert info["full_market_sync_allowed"] is True


def test_feature_availability_includes_daily_and_minute(monkeypatch):
    monkeypatch.setattr(
        "app.services.preferences.get_realtime_data_provider",
        lambda: "public",
    )
    feats = feature_availability(
        _capset(Cap.KLINE_DAILY_BATCH),
        minute_user_enabled=True,
    )
    assert feats["daily"]["available"] is True
    assert feats["minute"]["available"] is False
    assert feats["minute"].get("view_available") is True
    assert feats["depth"]["available"] is True
    assert feats["quote"]["available"] is True
    assert feats["quote"]["source"] == "local_public"
    assert feats["websocket"]["available"] is False


def test_feature_quote_tickflow_without_cap_is_unavailable(monkeypatch):
    """TickFlow leftover routing + no quote cap must not claim local_public."""
    monkeypatch.setattr(
        "app.services.preferences.get_realtime_data_provider",
        lambda: "tickflow",
    )
    monkeypatch.setattr(
        "app.services.financial_normalize.local_financials_ready",
        lambda d: False,
    )
    monkeypatch.setattr(
        "app.services.financial_normalize.local_adj_factor_ready",
        lambda d: False,
    )
    monkeypatch.setattr("app.services.preferences.is_public_financial_provider", lambda: False)
    monkeypatch.setattr("app.services.preferences.is_public_adj_factor_provider", lambda: False)
    feats = feature_availability(_capset(Cap.KLINE_DAILY_BATCH))
    assert feats["quote"]["available"] is False
    assert feats["quote"]["source"] == "none"
    assert feats["quote"]["mode"] == "none"
    assert feats["adj_factor"]["available"] is True
    assert feats["adj_factor"]["source"] == "local_public"
    assert feats["adj_factor"]["reason_code"] == "public_fallback"
