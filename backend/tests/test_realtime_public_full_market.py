from __future__ import annotations

from app.services.quote_service import QuoteService
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet, feature_availability


def test_realtime_mode_public_is_full_market(monkeypatch):
    monkeypatch.setattr(
        "app.services.preferences.get_realtime_data_provider",
        lambda: "public",
    )
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "none"))
    assert QuoteService.realtime_mode() == "full_market"
    assert QuoteService.is_realtime_allowed() is True


def test_feature_quote_mode_full_market_public(monkeypatch):
    monkeypatch.setattr(
        "app.services.preferences.get_realtime_data_provider",
        lambda: "public",
    )
    # prevent local fin/adj probes failing the test environment
    monkeypatch.setattr(
        "app.services.financial_normalize.local_financials_ready",
        lambda d: False,
    )
    monkeypatch.setattr(
        "app.services.financial_normalize.local_adj_factor_ready",
        lambda d: False,
    )
    monkeypatch.setattr(
        "app.services.preferences.is_public_financial_provider",
        lambda: False,
    )
    monkeypatch.setattr(
        "app.services.preferences.is_public_adj_factor_provider",
        lambda: False,
    )
    feats = feature_availability(CapabilitySet({Cap.KLINE_DAILY_BATCH: CapabilityLimits(rpm=60, batch=100)}))
    assert feats["quote"]["available"] is True
    assert feats["quote"]["mode"] == "full_market_public"
