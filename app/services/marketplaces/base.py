"""Base classes for Playwright-backed marketplace adapters."""

from __future__ import annotations

from abc import abstractmethod
import logging
from time import sleep
from typing import Sequence

import httpx
from playwright.sync_api import Error as PlaywrightError

from app.services.marketplaces.parsing import MarketplaceParser
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
    SnapshotPolicy,
)
from app.services.providers import BaseProvider, ProviderQuery, ProviderQueryResult, ProviderRequestPolicy, ProviderSearchError, RawSourceItem

logger = logging.getLogger(__name__)


class BasePlaywrightMarketplaceAdapter(BaseProvider):
    """Reusable scraper base with navigation, retries, throttling, and parsing separation."""

    capabilities = (
        MarketplaceCapability.SEARCH
        | MarketplaceCapability.PLAYWRIGHT
        | MarketplaceCapability.HTML_SNAPSHOTS
    )

    def __init__(
        self,
        *,
        parser: MarketplaceParser,
        launch_policy: PlaywrightLaunchPolicy | None = None,
        timeout_policy: PlaywrightTimeoutPolicy | None = None,
        retry_policy: MarketplaceRetryPolicy | None = None,
        rate_limit_policy: MarketplaceRateLimitPolicy | None = None,
        snapshot_policy: SnapshotPolicy | None = None,
    ) -> None:
        self._parser = parser
        self._launch_policy = launch_policy or PlaywrightLaunchPolicy()
        self._timeout_policy = timeout_policy or PlaywrightTimeoutPolicy()
        self._retry_policy = retry_policy or MarketplaceRetryPolicy()
        self._rate_limiter = SimpleRateLimiter(rate_limit_policy or MarketplaceRateLimitPolicy())
        self._snapshot_policy = snapshot_policy or SnapshotPolicy()

    @abstractmethod
    def build_entry_urls(self, query: ProviderQuery) -> list[str]:
        """Return the page URLs to fetch for one logical query."""

    def build_fetch_requests(self, query: ProviderQuery) -> list[PageFetchRequest]:
        """Build page fetch requests from the adapter's entry URLs."""
        return [
            PageFetchRequest(
                adapter_name=self.provider_name,
                query=query,
                url=url,
            )
            for url in self.build_entry_urls(query)
        ]

    def search(
        self,
        *,
        client: httpx.Client,
        query: ProviderQuery,
        policy: ProviderRequestPolicy,
    ) -> ProviderQueryResult:
        """Execute Playwright-driven collection and parse pages into RawSourceItem objects."""
        del client  # not used by browser-driven adapters
        result = ProviderQueryResult(provider_name=self.provider_name, query=query)
        requests = self.build_fetch_requests(query)

        try:
            with PlaywrightSessionManager(
                launch_policy=self._launch_policy_with_user_agent(policy.user_agent),
                timeout_policy=self._timeout_policy,
                snapshot_policy=self._snapshot_policy,
            ) as session:
                for request in requests:
                    artifact = self._fetch_with_retries(session=session, request=request)
                    result.items.extend(self._parse_artifact(artifact))
        except Exception as exc:
            raise ProviderSearchError(self.provider_name, query, str(exc), retryable=False) from exc

        return result

    def _fetch_with_retries(self, *, session: PlaywrightSessionManager, request: PageFetchRequest) -> PageFetchResult:
        """Fetch one page with rate limiting and bounded retry/backoff."""
        attempts = max(0, self._retry_policy.max_retries) + 1
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                self._rate_limiter.wait()
                logger.info(
                    "Marketplace page fetch started.",
                    extra={
                        "adapter_name": self.provider_name,
                        "query_text": request.query.text,
                        "request_url": request.url,
                        "attempt": attempt,
                    },
                )
                artifact = session.fetch_page(request)
                logger.info(
                    "Marketplace page fetch completed.",
                    extra={
                        "adapter_name": self.provider_name,
                        "query_text": request.query.text,
                        "request_url": request.url,
                        "final_url": artifact.final_url,
                        "status_code": artifact.status_code,
                        "html_snapshot_path": artifact.snapshot.html_path,
                    },
                )
                return artifact
            except PlaywrightError as exc:
                last_error = exc
                if attempt >= attempts:
                    break
                sleep(self._retry_policy.retry_backoff_seconds * attempt)

        if last_error is None:  # pragma: no cover - defensive branch
            raise RuntimeError("Marketplace fetch failed without a captured exception.")
        raise last_error

    def _parse_artifact(self, artifact: PageFetchResult) -> list[RawSourceItem]:
        """Delegate page parsing to the configured parser."""
        items = self._parser.parse(artifact)
        logger.info(
            "Marketplace parser completed.",
            extra={
                "adapter_name": self.provider_name,
                "query_text": artifact.query.text,
                "final_url": artifact.final_url,
                "parsed_item_count": len(items),
            },
        )
        return items

    def _launch_policy_with_user_agent(self, user_agent: str | None) -> PlaywrightLaunchPolicy:
        """Merge provider-level user agent into launch policy."""
        if user_agent is None:
            return self._launch_policy
        return PlaywrightLaunchPolicy(
            headless=self._launch_policy.headless,
            slow_mo_ms=self._launch_policy.slow_mo_ms,
            locale=self._launch_policy.locale,
            timezone_id=self._launch_policy.timezone_id,
            viewport_width=self._launch_policy.viewport_width,
            viewport_height=self._launch_policy.viewport_height,
            user_agent=user_agent,
        )
