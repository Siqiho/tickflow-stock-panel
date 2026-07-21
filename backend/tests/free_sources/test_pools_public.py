from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from app.services.free_sources.pools_public import (
    _to_symbol,
    load_pool_symbols,
    write_pool_parquet,
)


def test_to_symbol():
    assert _to_symbol("000001", "深圳证券交易所") == "000001.SZ"
    assert _to_symbol("600000", "上海证券交易所") == "600000.SH"
    assert _to_symbol("sh600519") == "600519.SH"
    assert _to_symbol("sz000001") == "000001.SZ"


def test_write_and_load_pool(tmp_path: Path):
    df = pl.DataFrame(
        {
            "symbol": ["000001.SZ", "600519.SH"],
            "as_of": [date(2026, 7, 17), date(2026, 7, 17)],
            "name": ["平安银行", "贵州茅台"],
            "source": ["csindex", "csindex"],
        }
    )
    path = write_pool_parquet(df, tmp_path, "CSI300")
    assert path.exists()
    syms = load_pool_symbols(tmp_path, "CSI300")
    assert syms == ["000001.SZ", "600519.SH"]
    cached = pl.read_parquet(path)
    assert set(["symbol", "as_of"]).issubset(set(cached.columns))
