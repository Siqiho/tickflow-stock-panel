from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.services.universe_scope import (
    SCOPE_CSI800,
    normalize_scope,
    resolve_symbols,
    scope_info,
)


def test_normalize_csi800_aliases():
    assert normalize_scope("CSI800") == SCOPE_CSI800
    assert normalize_scope("ZZ800") == SCOPE_CSI800
    assert normalize_scope("000906") == SCOPE_CSI800


def test_resolve_csi800_is_union_of_300_and_500():
    d = Path(settings.data_dir)
    u800 = set(resolve_symbols("CSI800", data_dir=d, default="CSI300"))
    u300 = set(resolve_symbols("CSI300", data_dir=d, default="CSI300"))
    u500 = set(resolve_symbols("CSI500", data_dir=d, default="CSI300"))
    assert len(u800) == len(u300 | u500)
    assert u300.issubset(u800)
    assert u500.issubset(u800)
    # official pools are disjoint
    assert len(u300 & u500) == 0
    info = scope_info("CSI800")
    assert info["is_union"] is True
