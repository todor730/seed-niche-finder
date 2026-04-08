"""Playwright browser/session lifecycle management."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from playwright.sync_api import Browser, BrowserContext, Error as PlaywrightError, Page, Playwright, sync_playwright

from app.services.marketplaces.types import (
    PageFetchRequest,
    PageFetchResult,
    PlaywrightLaunchPolicy,
    PlaywrightTimeoutPolicy,
    SnapshotArtifact,
    SnapshotPolicy,
    build_snapshot_base_dir,
)

logger = logging.getLogger(__name__)


class PlaywrightSessionManager(AbstractContextManager["PlaywrightSessionManager"]):
    """Owns Playwright browser lifecycle and produces parser-ready page artifacts."""

    def __init__(
        self,
        *,
        launch_policy: PlaywrightLaunchPolicy,
        timeout_policy: PlaywrightTimeoutPolicy,
        snapshot_policy: SnapshotPolicy,
    ) -> None:
        self._launch_policy = launch_policy
        self._timeout_policy = timeout_policy
        self._snapshot_policy = snapshot_policy
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    def __enter__(self) -> "PlaywrightSessionManager":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self._launch_policy.headless,
            slow_mo=self._launch_policy.slow_mo_ms,
        )
        context_kwargs: dict[str, Any] = {
            "locale": self._launch_policy.locale,
            "timezone_id": self._launch_policy.timezone_id,
            "viewport": {
                "width": self._launch_policy.viewport_width,
                "height": self._launch_policy.viewport_height,
            },
        }
        if self._launch_policy.user_agent:
            context_kwargs["user_agent"] = self._launch_policy.user_agent
        self._context = self._browser.new_context(**context_kwargs)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
        return None

    def close(self) -> None:
        """Close page context, browser, and Playwright runtime gracefully."""
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def fetch_page(self, request: PageFetchRequest) -> PageFetchResult:
        """Fetch one page and return a parser-ready artifact."""
        if self._context is None:
            raise RuntimeError("PlaywrightSessionManager must be entered before fetching pages.")

        page = self._context.new_page()
        page.set_default_navigation_timeout(self._timeout_policy.navigation_timeout_ms)
        page.set_default_timeout(self._timeout_policy.action_timeout_ms)
        response = None
        html: str | None = None
        page_title: str | None = None
        snapshot = SnapshotArtifact()
        fetched_at = datetime.now(UTC)

        try:
            response = page.goto(request.url, wait_until=request.wait_until, timeout=self._timeout_policy.navigation_timeout_ms)
            html = page.content()
            page_title = page.title()
            snapshot = self._capture_snapshot(request=request, page=page, html=html)
            return PageFetchResult(
                adapter_name=request.adapter_name,
                query=request.query,
                requested_url=request.url,
                final_url=page.url,
                status_code=response.status if response is not None else None,
                title=page_title or None,
                html=html,
                fetched_at=fetched_at,
                snapshot=snapshot,
                metadata={},
            )
        except PlaywrightError as exc:
            logger.warning(
                "Playwright page fetch failed.",
                extra={
                    "adapter_name": request.adapter_name,
                    "query_text": request.query.text,
                    "requested_url": request.url,
                    "error_type": exc.__class__.__name__,
                },
            )
            raise
        finally:
            page.close()

    def _capture_snapshot(self, *, request: PageFetchRequest, page: Page, html: str | None) -> SnapshotArtifact:
        """Persist raw HTML and optional screenshots for parser debugging."""
        html_path: str | None = None
        screenshot_path: str | None = None
        base_dir = build_snapshot_base_dir(self._snapshot_policy, request.adapter_name)
        base_dir.mkdir(parents=True, exist_ok=True)
        snapshot_id = f"{datetime.now(UTC).strftime('%H%M%S')}_{uuid4().hex}"

        if self._snapshot_policy.capture_html and html is not None:
            target = base_dir / f"{snapshot_id}.html"
            target.write_text(html, encoding="utf-8")
            html_path = str(target)
        if self._snapshot_policy.capture_screenshot:
            target = base_dir / f"{snapshot_id}.png"
            page.screenshot(path=str(target), full_page=True)
            screenshot_path = str(target)

        return SnapshotArtifact(html_path=html_path, screenshot_path=screenshot_path)
