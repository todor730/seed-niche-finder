"""Shared types for Playwright-based marketplace adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Flag, auto
from pathlib import Path
from typing import Literal

from app.services.providers import ProviderQuery

WaitUntil = Literal["commit", "domcontentloaded", "load", "networkidle"]


class MarketplaceCapability(Flag):
    """Capability flags for marketplace adapters."""

    SEARCH = auto()
    PRODUCT_DETAILS = auto()
    PLAYWRIGHT = auto()
    HTML_SNAPSHOTS = auto()
    SCREENSHOTS = auto()
    CREDENTIALS = auto()


@dataclass(frozen=True, slots=True)
class PlaywrightLaunchPolicy:
    """Browser launch and context configuration."""

    headless: bool = True
    slow_mo_ms: int = 0
    locale: str = "en-US"
    timezone_id: str = "UTC"
    viewport_width: int = 1440
    viewport_height: int = 1024
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class PlaywrightTimeoutPolicy:
    """Timeout policy for browser navigation and actions."""

    navigation_timeout_ms: int = 20_000
    action_timeout_ms: int = 10_000


@dataclass(frozen=True, slots=True)
class MarketplaceRetryPolicy:
    """Retry behavior for page fetch operations."""

    max_retries: int = 1
    retry_backoff_seconds: float = 0.5


@dataclass(frozen=True, slots=True)
class MarketplaceRateLimitPolicy:
    """Simple rate limiting knobs for marketplace requests."""

    min_delay_seconds: float = 0.5


@dataclass(frozen=True, slots=True)
class SnapshotPolicy:
    """Raw snapshot capture strategy for debugging parser drift."""

    snapshot_dir: str = "./artifacts/marketplace_snapshots"
    capture_html: bool = True
    capture_screenshot: bool = False


@dataclass(frozen=True, slots=True)
class PageFetchRequest:
    """Input contract for one page fetch."""

    adapter_name: str
    query: ProviderQuery
    url: str
    wait_until: WaitUntil = "domcontentloaded"


@dataclass(frozen=True, slots=True)
class SnapshotArtifact:
    """Paths to persisted debug snapshots for one fetched page."""

    html_path: str | None = None
    screenshot_path: str | None = None


@dataclass(frozen=True, slots=True)
class PageFetchResult:
    """Captured browser artifact passed to parsers."""

    adapter_name: str
    query: ProviderQuery
    requested_url: str
    final_url: str
    status_code: int | None
    title: str | None
    html: str | None
    fetched_at: datetime
    snapshot: SnapshotArtifact = field(default_factory=SnapshotArtifact)
    metadata: dict[str, object] = field(default_factory=dict)


def build_snapshot_base_dir(snapshot_policy: SnapshotPolicy, adapter_name: str) -> Path:
    """Return the snapshot directory for one adapter."""
    timestamp = datetime.now(UTC).strftime("%Y%m%d")
    return Path(snapshot_policy.snapshot_dir) / adapter_name / timestamp
