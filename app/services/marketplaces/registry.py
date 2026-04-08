"""Registry for marketplace adapters."""

from __future__ import annotations

from typing import Sequence

from app.services.marketplaces.base import BasePlaywrightMarketplaceAdapter


class MarketplaceAdapterRegistry:
    """Lightweight registry for Playwright marketplace adapters."""

    def __init__(self, adapters: Sequence[BasePlaywrightMarketplaceAdapter] | None = None) -> None:
        self._adapters = {adapter.provider_name: adapter for adapter in adapters or ()}

    def register(self, adapter: BasePlaywrightMarketplaceAdapter) -> None:
        """Register or replace an adapter by name."""
        self._adapters[adapter.provider_name] = adapter

    def get(self, provider_name: str) -> BasePlaywrightMarketplaceAdapter | None:
        """Return an adapter by name when present."""
        return self._adapters.get(provider_name)

    def list_enabled(self) -> list[BasePlaywrightMarketplaceAdapter]:
        """Return adapters in stable name order."""
        return [self._adapters[name] for name in sorted(self._adapters)]
