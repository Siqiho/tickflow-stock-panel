from __future__ import annotations

from pathlib import Path

import polars as pl

from app.services.universe_scope import (
    SCOPE_CSI1000,
    SCOPE_CSI1800,
    SCOPE_CSI800,
    normalize_scope,
    resolve_symbols,
    scope_info,
)


def test_normalize_csi1800_aliases():
    assert normalize_scope("CSI800") == SCOPE_CSI800
    assert normalize_scope("000906") == SCOPE_CSI800
    assert normalize_scope("CSI1000") == SCOPE_CSI1000
    assert normalize_scope("000852") == SCOPE_CSI1000
    assert normalize_scope("CSI1800") == SCOPE_CSI1800
    assert normalize_scope("ZZ1800") == SCOPE_CSI1800


def test_resolve_csi1800_is_official_800_union_1000_and_watchlist(tmp_path: Path, monkeypatch):
    pools = tmp_path / "pools"
    pools.mkdir()
    pl.DataFrame({"symbol": ["600519.SH", "300750.SZ"]}).write_parquet(pools / "CSI800.parquet")
    pl.DataFrame({"symbol": ["000001.SZ", "300750.SZ"]}).write_parquet(pools / "CSI1000.parquet")

    monkeypatch.setattr(
        "app.tickflow.pools.get_pool",
        lambda pool_id, **kwargs: ["605289.SH"] if pool_id == "watchlist" else [],
    )

    resolved = resolve_symbols(
        "CSI1800",
        data_dir=tmp_path,
        default="CSI1800",
        include_watchlist=True,
        refresh_pools_if_missing=False,
    )

    assert resolved == ["000001.SZ", "300750.SZ", "600519.SH", "605289.SH"]
    assert "600000.SH" not in resolved
    info = scope_info("CSI1800")
    assert info["is_union"] is True


def test_preferences_whitelist_includes_csi1800():
    from app.services.preferences import _VALID_UNIVERSE_SCOPES
    from app.services.universe_scope import VALID_SCOPES

    assert "CSI800" in _VALID_UNIVERSE_SCOPES
    assert "CSI1000" in _VALID_UNIVERSE_SCOPES
    assert "CSI1800" in _VALID_UNIVERSE_SCOPES
    assert "CSI1800" in VALID_SCOPES
