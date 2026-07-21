from __future__ import annotations

from pathlib import Path

import polars as pl

from app.services.universe_scope import (
    SCOPE_CSI300,
    normalize_scope,
    resolve_symbols,
)


def test_normalize_scope_aliases():
    assert normalize_scope("hs300") == "CSI300"
    assert normalize_scope("all") == "ALL"
    assert normalize_scope("bogus", default="CSI300") == "CSI300"


def test_resolve_csi300_from_pool_file(tmp_path: Path):
    pools = tmp_path / "pools"
    pools.mkdir()
    pl.DataFrame({"symbol": ["000001.SZ", "600519.SH"], "as_of": ["2026-07-17"] * 2}).write_parquet(
        pools / "CSI300.parquet"
    )
    syms = resolve_symbols(SCOPE_CSI300, data_dir=tmp_path, refresh_pools_if_missing=False)
    assert syms == ["000001.SZ", "600519.SH"]
