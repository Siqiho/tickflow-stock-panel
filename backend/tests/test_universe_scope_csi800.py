from __future__ import annotations

from app.services.universe_scope import SCOPE_CSI800, normalize_scope, scope_info


def test_normalize_csi800_aliases():
    assert normalize_scope("CSI800") == SCOPE_CSI800
    assert normalize_scope("ZZ800") == SCOPE_CSI800
    assert normalize_scope("000906") == SCOPE_CSI800
    info = scope_info("CSI800")
    assert info["scope"] == SCOPE_CSI800
    assert info["is_csi"] is True
