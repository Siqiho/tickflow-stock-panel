"""Provider registry.

Production default remains TickFlow. Custom HTTP sources are loaded from
`data/data_sources/*.yaml` via `app.data_providers.custom` and are NEVER the
implicit default. Callers must pass an explicit custom source name.
"""

from __future__ import annotations

from app.data_providers.base import ProviderDatasetManifest
from app.data_providers.public_provider import PublicProvider
from app.data_providers.tickflow_provider import TickFlowProvider

_PROVIDERS = {
    "tickflow": TickFlowProvider,
    "public": PublicProvider,
}


def get_provider(name: str = "tickflow"):
    """Resolve a provider by name.

    - tickflow: built-in production provider
    - other names: optional custom HTTP source registered by custom.loader
    """
    key = (name or "tickflow").strip().lower()
    if key in _PROVIDERS:
        return _PROVIDERS[key]()

    # Lazy import to avoid circular imports and avoid auto-loading YAML at import time
    from app.data_providers.custom import get_provider as get_custom_provider
    from app.data_providers.custom import load_all as load_custom_all
    from app.data_providers.custom import names as custom_names

    if not custom_names():
        load_custom_all()
    provider = get_custom_provider(key)
    if provider is None:
        raise ValueError(f"Unsupported data provider: {name}")
    return provider


def list_provider_names() -> list[str]:
    from app.data_providers.custom import load_all as load_custom_all
    from app.data_providers.custom import names as custom_names

    load_custom_all()
    return ["tickflow", "public", *sorted(custom_names())]


def get_provider_manifests(name: str) -> list[ProviderDatasetManifest]:
    """Return detached built-in manifests without loading custom-provider configuration."""
    key = (name or "").strip().lower()
    provider_type = _PROVIDERS.get(key)
    if provider_type is None:
        return []
    manifests = sorted(
        provider_type.dataset_manifests,
        key=lambda manifest: (manifest.provider, manifest.dataset_id, manifest.operations),
    )
    return [manifest.model_copy(deep=True) for manifest in manifests]


def list_provider_manifests() -> list[ProviderDatasetManifest]:
    """List detached built-in metadata in deterministic order, with no provider calls."""
    manifests = [
        manifest.model_copy(deep=True)
        for provider_type in _PROVIDERS.values()
        for manifest in provider_type.dataset_manifests
    ]
    return sorted(
        manifests,
        key=lambda manifest: (manifest.provider, manifest.dataset_id, manifest.operations),
    )
