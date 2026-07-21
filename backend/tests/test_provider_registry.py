from __future__ import annotations

from app.data_providers.registry import get_provider, list_provider_names


def test_public_provider_exposes_typed_operations():
    provider = get_provider("public")

    assert provider.name == "public"
    assert provider.supports("quote_snapshot") is True
    assert provider.supports("sealed_l1") is True
    assert provider.supports("adj_factor") is True
    assert provider.supports("financial") is True
    assert provider.supports("pools") is True
    assert provider.supports("depth5") is False
    assert "public" in list_provider_names()
