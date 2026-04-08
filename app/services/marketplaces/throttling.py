"""Rate limiting helpers for marketplace adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import monotonic, sleep

from app.services.marketplaces.types import MarketplaceRateLimitPolicy


@dataclass(slots=True)
class SimpleRateLimiter:
    """Conservative process-local rate limiter for scraper requests."""

    policy: MarketplaceRateLimitPolicy
    _lock: Lock = field(init=False, repr=False)
    _last_request_started_at: float = field(init=False, repr=False, default=0.0)

    def __post_init__(self) -> None:
        self._lock = Lock()

    def wait(self) -> None:
        """Sleep if needed so requests stay spaced apart."""
        if self.policy.min_delay_seconds <= 0:
            return
        with self._lock:
            now = monotonic()
            elapsed = now - self._last_request_started_at
            remaining = self.policy.min_delay_seconds - elapsed
            if remaining > 0:
                sleep(remaining)
            self._last_request_started_at = monotonic()
