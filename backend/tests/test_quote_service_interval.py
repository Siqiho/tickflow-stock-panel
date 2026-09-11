"""Board quote clock must follow preferences, not leftover in-memory seconds."""

from app.services.quote_service import QuoteService


def test_status_syncs_leftover_interval_from_preferences(monkeypatch):
    service = QuoteService()
    service._interval = 8.0
    monkeypatch.setattr("app.services.preferences.get_realtime_quote_interval", lambda: 15.0)
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "none"))

    status = service.status()

    assert status["interval_s"] == 15.0
    assert service._interval == 15.0


def test_enable_while_running_picks_up_preference_interval(monkeypatch):
    service = QuoteService()
    service._running = True
    service._enabled = True
    service._interval = 8.0
    monkeypatch.setattr("app.services.preferences.get_realtime_quote_interval", lambda: 15.0)
    monkeypatch.setattr(QuoteService, "_current_tier", staticmethod(lambda: "none"))
    monkeypatch.setattr(service, "_save_enabled", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(QuoteService, "is_realtime_allowed", staticmethod(lambda: True))

    assert service.enable() is True
    assert service._interval == 15.0
    assert service._running is True
