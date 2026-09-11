"""Quote service lifecycle must preserve explicit user preferences."""

from app.services.quote_service import QuoteService


def test_runtime_shutdown_does_not_disable_user_realtime_preference(monkeypatch):
    service = QuoteService()
    persisted: list[bool] = []
    monkeypatch.setattr(service, "_save_enabled", persisted.append)

    service.stop(persist=False)

    assert service.status()["running"] is False
    assert persisted == []
