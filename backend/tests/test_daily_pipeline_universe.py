"""Pipeline universe behavior at the configured-scope boundary."""

from __future__ import annotations

from app.jobs import daily_pipeline
from app.services import universe_scope
from app.tickflow import pools
from app.tickflow.capabilities import CapabilitySet


def test_pipeline_universe_unions_csi500_with_watchlist(monkeypatch):
    """Saved stocks remain in the daily pipeline even outside CSI500."""
    monkeypatch.setattr(
        daily_pipeline._prefs,
        "get_pipeline_universe_scope",
        lambda: "CSI500",
    )
    monkeypatch.setattr(
        universe_scope,
        "_ensure_csi_pool",
        lambda *args, **kwargs: ["301526.SZ", "600000.SH"],
    )
    monkeypatch.setattr(
        pools,
        "get_pool",
        lambda pool_id, **kwargs: (
            ["301526.SZ", "300502.SZ"] if pool_id == "watchlist" else []
        ),
    )

    symbols = daily_pipeline.resolve_universe(CapabilitySet())

    assert symbols == ["300502.SZ", "301526.SZ", "600000.SH"]
