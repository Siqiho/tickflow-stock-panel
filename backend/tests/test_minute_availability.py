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
    assert feats["depth"]["available"] is False
    assert feats["depth"]["source"] == "none"
    assert feats["quote"]["available"] is True
    assert feats["quote"]["source"] == "local_public"
    assert feats["websocket"]["available"] is False


def test_feature_availability_custom_depth_without_tickflow_cap(monkeypatch):
    """Custom depth5 must not look unavailable just because TickFlow lacks DEPTH5."""
    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "public")
    monkeypatch.setattr("app.services.preferences.get_depth5_data_provider", lambda: "depth_src")
    monkeypatch.setattr("app.services.preferences.get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_adj_factor_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.is_public_financial_provider", lambda: False)
    monkeypatch.setattr("app.services.preferences.is_public_adj_factor_provider", lambda: False)
    monkeypatch.setattr("app.services.financial_normalize.local_financials_ready", lambda d: False)
    monkeypatch.setattr("app.services.financial_normalize.local_adj_factor_ready", lambda d: False)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: name == "depth_src" and dataset == "depth5",
    )
    feats = feature_availability(_capset(Cap.KLINE_DAILY_BATCH))
    assert feats["depth"]["available"] is True
    assert feats["depth"]["source"] == "depth_src"
    assert feats["depth"]["status"] == "available"
    assert feats["depth"]["fallback"] is None


def test_feature_availability_custom_adj_without_tickflow_cap(monkeypatch):
    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "public")
    monkeypatch.setattr("app.services.preferences.get_adj_factor_provider", lambda: "fuyao")
    monkeypatch.setattr("app.services.preferences.get_financial_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_depth5_data_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.get_minute_data_provider", lambda: "tickflow")
    monkeypatch.setattr("app.services.preferences.is_public_financial_provider", lambda: False)
    monkeypatch.setattr("app.services.preferences.is_public_adj_factor_provider", lambda: False)
    monkeypatch.setattr("app.services.financial_normalize.local_financials_ready", lambda d: False)
    monkeypatch.setattr("app.services.financial_normalize.local_adj_factor_ready", lambda d: False)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: name == "fuyao" and dataset == "adj_factor",
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda name: object())
    feats = feature_availability(_capset(Cap.KLINE_DAILY_BATCH))
    assert feats["adj_factor"]["available"] is True
    assert feats["adj_factor"]["source"] == "fuyao"
    assert feats["adj_factor"]["status"] == "available"
    assert feats["adj_factor"]["reason_code"] == "ok"


def test_feature_availability_reports_custom_sources(monkeypatch):
    monkeypatch.setattr("app.services.preferences.get_realtime_data_provider", lambda: "fuyao")
    monkeypatch.setattr("app.services.preferences.get_financial_provider", lambda: "fuyao")
    monkeypatch.setattr("app.services.preferences.get_adj_factor_provider", lambda: "sdk")
    monkeypatch.setattr("app.services.preferences.get_depth5_data_provider", lambda: "depth_src")
    monkeypatch.setattr("app.services.preferences.get_minute_data_provider", lambda: "sdk")
    monkeypatch.setattr("app.services.preferences.is_public_financial_provider", lambda: False)
    monkeypatch.setattr("app.services.preferences.is_public_adj_factor_provider", lambda: False)
    monkeypatch.setattr("app.services.financial_normalize.local_financials_ready", lambda d: False)
    monkeypatch.setattr("app.services.financial_normalize.local_adj_factor_ready", lambda d: False)
    monkeypatch.setattr(
        "app.data_providers.custom.provider_has_dataset",
        lambda name, dataset: (
            (name == "sdk" and dataset in {"minute", "adj_factor"})
            or (name == "fuyao" and dataset == "realtime")
            or (name == "depth_src" and dataset == "depth5")
        ),
    )
    monkeypatch.setattr("app.data_providers.custom.get_provider", lambda name: object())

    feats = feature_availability(
        _capset(Cap.FINANCIAL, Cap.ADJ_FACTOR, Cap.DEPTH5_BATCH, Cap.KLINE_MINUTE_BATCH, Cap.QUOTE_BATCH),
        minute_user_enabled=True,
    )
    assert feats["financial"]["source"] == "fuyao"
    assert feats["adj_factor"]["source"] == "sdk"
    assert feats["depth"]["source"] == "depth_src"
    assert feats["minute"]["source"] == "sdk"
    assert feats["quote"]["source"] == "fuyao"


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
    assert feats["adj_factor"]["available"] is False
    assert feats["adj_factor"]["source"] == "none"
    assert feats["adj_factor"]["reason_code"] == "no_capability"
