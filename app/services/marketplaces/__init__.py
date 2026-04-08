"""Playwright-based marketplace adapter foundation."""

from app.services.marketplaces.base import BasePlaywrightMarketplaceAdapter
from app.services.marketplaces.parsing import MarketplaceParser
from app.services.marketplaces.registry import MarketplaceAdapterRegistry
from app.services.marketplaces.session import PlaywrightSessionManager
from app.services.marketplaces.throttling import SimpleRateLimiter
from app.services.marketplaces.types import (
    MarketplaceCapability,
    MarketplaceRateLimitPolicy,
    MarketplaceRetryPolicy,
    PageFetchRequest,
    PageFetchResult,
    PlaywrightLaunchPolicy,
    PlaywrightTimeoutPolicy,
    SnapshotArtifact,
    SnapshotPolicy,
)

__all__ = [
    "BasePlaywrightMarketplaceAdapter",
    "MarketplaceAdapterRegistry",
    "MarketplaceCapability",
    "MarketplaceParser",
    "MarketplaceRateLimitPolicy",
    "MarketplaceRetryPolicy",
    "PageFetchRequest",
    "PageFetchResult",
    "PlaywrightLaunchPolicy",
    "PlaywrightSessionManager",
    "PlaywrightTimeoutPolicy",
    "SimpleRateLimiter",
    "SnapshotArtifact",
    "SnapshotPolicy",
]
