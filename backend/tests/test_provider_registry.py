from __future__ import annotations

from app.data_providers.registry import get_provider, get_provider_manifests, list_provider_names


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


def test_manifest_registry_returns_detached_builtin_metadata():
    first = get_provider_manifests("public")
    first[0].source_units["changed"] = "yes"

    second = get_provider_manifests("public")

    assert "changed" not in second[0].source_units
