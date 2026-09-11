from __future__ import annotations

from app.services import preferences, universe_scope
from app.services.quote_service import QuoteService

WATCHLIST = [
    "301526.SZ",
    "300502.SZ",
    "600756.SH",
    "301171.SZ",
    "000636.SZ",
    "300408.SZ",
    "300866.SZ",
    "300204.SZ",
]


def test_public_full_market_request_forces_complete_watchlist(monkeypatch) -> None:
    requested: list[str] = []

    monkeypatch.setattr(preferences, "get_realtime_pull_stock", lambda: True)
    monkeypatch.setattr(preferences, "get_realtime_pull_index", lambda: False)
    monkeypatch.setattr(preferences, "get_realtime_pull_etf", lambda: False)

    def resolve(scope: str, *, include_watchlist: bool = False, **_kwargs) -> list[str]:
        assert scope == "ALL"
        symbols = ["600756.SH"]
        if include_watchlist:
            symbols.extend(WATCHLIST)
        return sorted(set(symbols))

    monkeypatch.setattr(universe_scope, "resolve_symbols", resolve)

    service = QuoteService()

    def fetch(symbols: list[str], *, batch_size: int, pause_s: float) -> list[dict]:
        assert batch_size == 80
        assert pause_s == 0.05
        requested.extend(symbols)
        return []

    monkeypatch.setattr(service, "_fetch_public_quote_rows", fetch)

    service._fetch_public_full_market_records(
        all_index_symbols=set(),
        core_index_symbols=set(),
        all_etf_symbols=set(),
    )

    assert set(WATCHLIST).issubset(requested)
