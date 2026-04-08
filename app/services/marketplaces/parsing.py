"""Parser contract for marketplace page artifacts."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.services.marketplaces.types import PageFetchResult
from app.services.providers import RawSourceItem


class MarketplaceParser(ABC):
    """Pure parser contract separate from navigation/browser lifecycle."""

    @abstractmethod
    def parse(self, artifact: PageFetchResult) -> list[RawSourceItem]:
        """Parse one fetched page artifact into normalized raw evidence items."""
