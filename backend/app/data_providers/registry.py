"""Provider registry.

Production default remains TickFlow. Custom HTTP sources are loaded from
`data/data_sources/*.yaml` via `app.data_providers.custom` and are NEVER the
implicit default. Callers must pass an explicit custom source name.
"""
from __future__ import annotations

from app.data_providers.tickflow_provider import TickFlowProvider

_PROVIDERS = {
    "tickflow": TickFlowProvider,
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
    return ["tickflow", *sorted(custom_names())]
