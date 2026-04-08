"""Unified provider abstraction for raw external evidence collection."""

from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Flag, auto
import logging
from time import sleep
from typing import Iterable, Protocol, Sequence

import httpx

logger = logging.getLogger(__name__)


class ProviderCapability(Flag):
    """Capability flags exposed by a provider implementation."""

    SEARCH = auto()
    QUERY_EXPANSION = auto()
    AUTHORS = auto()
    CATEGORIES = auto()
    RATINGS = auto()
    PUBLISHED_DATE = auto()
    DESCRIPTIONS = auto()


@dataclass(frozen=True, slots=True)
class ProviderQuery:
    """A canonical provider query unit."""

    text: str
    kind: str = "seed"
    priority: int = 100
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderRequestPolicy:
    """Runtime policy for provider transport behavior."""

    timeout_seconds: float = 2.0
    max_retries: int = 1
    retry_backoff_seconds: float = 0.25
    max_concurrency: int = 4
    user_agent: str = "ebook-niche-research-engine/0.1 (+local-dev)"
    follow_redirects: bool = True


@dataclass(slots=True)
class RawSourceItem:
    """Standardized raw evidence item returned by provider search."""

    provider_name: str
    query_text: str
    query_kind: str | None
    dedupe_key: str
    title: str
    provider_item_id: str | None = None
    source_url: str | None = None
    subtitle: str | None = None
    authors: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    description_text: str | None = None
    content_text: str = ""
    published_date_raw: str | None = None
    average_rating: float | None = None
    rating_count: int | None = None
    review_count: int | None = None
    raw_payload: dict[str, object] = field(default_factory=dict)

    @property
    def query_used(self) -> str:
        """Backward-compatible alias for the canonical query field."""
        return self.query_text

    @property
    def source_identifier(self) -> str | None:
        """Backward-compatible alias for the provider item identifier."""
        return self.provider_item_id

    @property
    def url(self) -> str | None:
        """Convenience alias for the canonical source URL."""
        return self.source_url


@dataclass(slots=True)
class ProviderQueryResult:
    """Result of one provider query execution."""

    provider_name: str
    query: ProviderQuery
    items: list[RawSourceItem] = field(default_factory=list)
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


@dataclass(slots=True)
class ProviderFailure:
    """Captured provider failure without aborting the full batch."""

    provider_name: str
    query: ProviderQuery
    error_type: str
    message: str
    retryable: bool
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class ProviderSearchBatchResult:
    """Aggregated multi-provider search result for one seed niche."""

    seed_niche: str
    queries: list[ProviderQuery]
    results: list[ProviderQueryResult] = field(default_factory=list)
    failures: list[ProviderFailure] = field(default_factory=list)

    @property
    def all_items(self) -> list[RawSourceItem]:
        """Return all raw source items deduplicated per provider/dedupe key."""
        deduped: dict[tuple[str, str], RawSourceItem] = {}
        for result in self.results:
            for item in result.items:
                deduped.setdefault((item.provider_name, item.dedupe_key), item)
        return list(deduped.values())

    @property
    def total_item_count(self) -> int:
        """Return the count of deduplicated items."""
        return len(self.all_items)

    @property
    def provider_names(self) -> list[str]:
        """Return provider names that participated in the batch."""
        return sorted({result.provider_name for result in self.results} | {failure.provider_name for failure in self.failures})


@dataclass(frozen=True, slots=True)
class _ProviderTaskExecution:
    """Internal execution result for one provider/query task."""

    task_index: int
    result: ProviderQueryResult | None = None
    failure: ProviderFailure | None = None


@dataclass(frozen=True, slots=True)
class BookSignal:
    """Compatibility bridge shape used by the current ranking layer."""

    title: str
    authors: list[str]
    categories: list[str]
    review_count: int | None
    average_rating: float | None
    published_year: int | None
    source: str
    source_url: str | None


class ProviderSearchError(RuntimeError):
    """Expected provider-level transport or response error."""

    def __init__(self, provider_name: str, query: ProviderQuery, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.provider_name = provider_name
        self.query = query
        self.retryable = retryable


class QueryExpansionHook(Protocol):
    """Hook that expands canonical provider queries from a seed niche."""

    def expand(self, seed_niche: str, queries: Sequence[ProviderQuery]) -> list[ProviderQuery]:
        """Return the next query set for a seed niche."""


class DefaultBookQueryExpansionHook:
    """Base query expansion for book-market discovery."""

    def expand(self, seed_niche: str, queries: Sequence[ProviderQuery]) -> list[ProviderQuery]:
        normalized = seed_niche.strip().lower()
        if not normalized:
            return list(queries)
        expanded = list(queries)
        expanded.extend(
            [
                ProviderQuery(text=normalized, kind="seed", priority=100, tags=("seed",)),
                ProviderQuery(text=f"{normalized} books", kind="books", priority=95, tags=("books",)),
                ProviderQuery(text=f"{normalized} fiction", kind="fiction", priority=85, tags=("fiction",)),
            ]
        )
        return expanded


class MarketplaceIntentQueryExpansionHook:
    """Adds generic commercial-intent book queries."""

    def expand(self, seed_niche: str, queries: Sequence[ProviderQuery]) -> list[ProviderQuery]:
        normalized = seed_niche.strip().lower()
        if not normalized:
            return list(queries)
        expanded = list(queries)
        expanded.extend(
            [
                ProviderQuery(text=f"best {normalized} books", kind="best_of", priority=90, tags=("best_of",)),
                ProviderQuery(text=f"{normalized} best sellers", kind="best_sellers", priority=88, tags=("best_sellers",)),
                ProviderQuery(text=f"{normalized} kindle books", kind="kindle", priority=86, tags=("kindle",)),
            ]
        )
        return expanded


def _dedupe_queries(queries: Sequence[ProviderQuery]) -> list[ProviderQuery]:
    deduped: dict[tuple[str, str], ProviderQuery] = {}
    for query in queries:
        normalized_text = query.text.strip().lower()
        if not normalized_text:
            continue
        key = (normalized_text, query.kind.strip().lower())
        existing = deduped.get(key)
        normalized_query = ProviderQuery(
            text=normalized_text,
            kind=query.kind.strip().lower(),
            priority=query.priority,
            tags=tuple(sorted({tag.strip().lower() for tag in query.tags if tag.strip()})),
        )
        if existing is None or normalized_query.priority > existing.priority:
            deduped[key] = normalized_query
    return sorted(deduped.values(), key=lambda item: (-item.priority, item.text, item.kind))


def _coerce_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_string(value: object, *, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if max_length is not None:
        return normalized[:max_length]
    return normalized


def _normalize_url(value: object) -> str | None:
    normalized = _normalize_string(value, max_length=1024)
    if normalized is None:
        return None
    lowered = normalized.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return normalized
    return None


def _normalize_string_list(
    values: object,
    *,
    limit: int | None = None,
    max_item_length: int | None = None,
) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        item = _normalize_string(raw_value, max_length=max_item_length)
        if item is None:
            continue
        dedupe_key = item.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(item)
        if limit is not None and len(normalized) >= limit:
            break
    return normalized


def _normalize_google_books_categories(volume_info: dict[str, object]) -> list[str]:
    return _normalize_string_list(volume_info.get("categories", []), limit=12, max_item_length=120)


def _normalize_open_library_subjects(doc: dict[str, object]) -> list[str]:
    return _normalize_string_list(doc.get("subject", []), limit=12, max_item_length=120)


def _build_content_text(
    *,
    title: str,
    subtitle: str | None,
    authors: Iterable[str],
    categories: Iterable[str],
    description_text: str | None,
) -> str:
    parts = [
        title.strip(),
        (subtitle or "").strip(),
        " ".join(author.strip() for author in authors if author.strip()),
        " ".join(category.strip() for category in categories if category.strip()),
        (description_text or "").strip(),
    ]
    return "\n".join(part for part in parts if part)


def _parse_published_year(published_date_raw: str | None) -> int | None:
    if not published_date_raw:
        return None
    year_candidate = published_date_raw[:4]
    return int(year_candidate) if year_candidate.isdigit() else None


def raw_source_items_to_book_signals(items: Sequence[RawSourceItem]) -> list[BookSignal]:
    """Bridge raw provider output into the current ranking-compatible shape."""
    return [
        BookSignal(
            title=item.title,
            authors=list(item.authors),
            categories=list(item.categories),
            review_count=item.review_count,
            average_rating=item.average_rating,
            published_year=_parse_published_year(item.published_date_raw),
            source=item.provider_name,
            source_url=item.source_url,
        )
        for item in items
    ]


def _is_retryable_http_error(exception: httpx.HTTPError) -> bool:
    if isinstance(exception, httpx.TimeoutException):
        return True
    response = getattr(exception, "response", None)
    if response is None:
        return True
    return response.status_code >= 500


def _request_json(
    *,
    client: httpx.Client,
    provider_name: str,
    query: ProviderQuery,
    url: str,
    params: dict[str, object],
    policy: ProviderRequestPolicy,
) -> dict[str, object]:
    headers = {"User-Agent": policy.user_agent}
    attempts = max(0, policy.max_retries) + 1
    last_error: ProviderSearchError | None = None

    for attempt in range(1, attempts + 1):
        try:
            response = client.get(
                url,
                params=params,
                headers=headers,
                timeout=policy.timeout_seconds,
                follow_redirects=policy.follow_redirects,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ProviderSearchError(provider_name, query, "Provider returned a non-object JSON payload.", retryable=False)
            return payload
        except httpx.HTTPError as exc:
            retryable = _is_retryable_http_error(exc)
            last_error = ProviderSearchError(provider_name, query, str(exc), retryable=retryable)
            if not retryable or attempt >= attempts:
                break
            sleep(policy.retry_backoff_seconds * attempt)

    if last_error is not None:
        raise last_error
    raise ProviderSearchError(provider_name, query, "Unknown provider transport failure.", retryable=False)


class BaseProvider(ABC):
    """Abstract provider contract for raw source evidence search."""

    provider_name: str
    capabilities: ProviderCapability = ProviderCapability.SEARCH

    def expand_queries(self, seed_niche: str, base_queries: Sequence[ProviderQuery]) -> list[ProviderQuery]:
        """Allow provider-specific query adjustments while preserving the canonical shape."""
        return list(base_queries)

    def _make_raw_source_item(
        self,
        *,
        query: ProviderQuery,
        title: str,
        dedupe_key: str,
        provider_item_id: str | None = None,
        source_url: str | None = None,
        subtitle: str | None = None,
        authors: Sequence[str] | None = None,
        categories: Sequence[str] | None = None,
        description_text: str | None = None,
        published_date_raw: str | None = None,
        average_rating: float | None = None,
        rating_count: int | None = None,
        review_count: int | None = None,
        raw_payload: dict[str, object] | None = None,
    ) -> RawSourceItem:
        """Create a standardized raw source item with shared normalization."""
        normalized_title = _normalize_string(title, max_length=512)
        if normalized_title is None:
            raise ValueError("Raw source items require a non-empty title.")
        normalized_subtitle = _normalize_string(subtitle, max_length=512)
        normalized_authors = _normalize_string_list(list(authors or []), limit=8, max_item_length=120)
        normalized_categories = _normalize_string_list(list(categories or []), limit=12, max_item_length=120)
        normalized_description = _normalize_string(description_text)
        normalized_published_date_raw = _normalize_string(published_date_raw, max_length=50)
        normalized_source_url = _normalize_url(source_url)
        normalized_provider_item_id = _normalize_string(provider_item_id, max_length=255)
        normalized_dedupe_key = _normalize_string(dedupe_key, max_length=255)
        if normalized_dedupe_key is None:
            raise ValueError("Raw source items require a non-empty dedupe key.")

        return RawSourceItem(
            provider_name=self.provider_name,
            query_text=query.text,
            query_kind=query.kind,
            provider_item_id=normalized_provider_item_id,
            dedupe_key=normalized_dedupe_key,
            source_url=normalized_source_url,
            title=normalized_title,
            subtitle=normalized_subtitle,
            authors=normalized_authors,
            categories=normalized_categories,
            description_text=normalized_description,
            content_text=_build_content_text(
                title=normalized_title,
                subtitle=normalized_subtitle,
                authors=normalized_authors,
                categories=normalized_categories,
                description_text=normalized_description,
            ),
            published_date_raw=normalized_published_date_raw,
            average_rating=average_rating,
            rating_count=rating_count,
            review_count=review_count,
            raw_payload=raw_payload or {},
        )

    @abstractmethod
    def search(
        self,
        *,
        client: httpx.Client,
        query: ProviderQuery,
        policy: ProviderRequestPolicy,
    ) -> ProviderQueryResult:
        """Execute a single provider query and return standardized raw evidence items."""


class GoogleBooksProvider(BaseProvider):
    """Google Books adapter that returns standardized raw evidence items."""

    provider_name = "google_books"
    capabilities = (
        ProviderCapability.SEARCH
        | ProviderCapability.AUTHORS
        | ProviderCapability.CATEGORIES
        | ProviderCapability.RATINGS
        | ProviderCapability.PUBLISHED_DATE
        | ProviderCapability.DESCRIPTIONS
    )

    def _normalize_item(self, *, query: ProviderQuery, item: dict[str, object]) -> RawSourceItem | None:
        volume_info = item.get("volumeInfo", {})
        if not isinstance(volume_info, dict):
            return None

        title = _normalize_string(volume_info.get("title"), max_length=512)
        if title is None:
            return None

        provider_item_id = _normalize_string(item.get("id"), max_length=255)
        source_url = _normalize_url(volume_info.get("infoLink"))
        subtitle = _normalize_string(volume_info.get("subtitle"), max_length=512)
        authors = _normalize_string_list(volume_info.get("authors", []), limit=8, max_item_length=120)
        categories = _normalize_google_books_categories(volume_info)
        description_text = _normalize_string(volume_info.get("description"))
        published_date_raw = _normalize_string(volume_info.get("publishedDate"), max_length=50)
        average_rating = _coerce_float(volume_info.get("averageRating"))
        rating_count = _coerce_int(volume_info.get("ratingsCount"))

        dedupe_key = provider_item_id or f"{title.casefold()}::{(source_url or '').casefold()}"
        return self._make_raw_source_item(
            query=query,
            title=title,
            dedupe_key=dedupe_key,
            provider_item_id=provider_item_id,
            source_url=source_url,
            subtitle=subtitle,
            authors=authors,
            categories=categories,
            description_text=description_text,
            published_date_raw=published_date_raw,
            average_rating=average_rating,
            rating_count=rating_count,
            review_count=None,
            raw_payload=item,
        )

    def search(
        self,
        *,
        client: httpx.Client,
        query: ProviderQuery,
        policy: ProviderRequestPolicy,
    ) -> ProviderQueryResult:
        result = ProviderQueryResult(provider_name=self.provider_name, query=query)
        payload = _request_json(
            client=client,
            provider_name=self.provider_name,
            query=query,
            url="https://www.googleapis.com/books/v1/volumes",
            params={"q": query.text, "maxResults": 20, "projection": "lite"},
            policy=policy,
        )

        items: list[RawSourceItem] = []
        for item in payload.get("items", []):
            if not isinstance(item, dict):
                continue
            normalized_item = self._normalize_item(query=query, item=item)
            if normalized_item is not None:
                items.append(normalized_item)

        result.items = items
        result.completed_at = datetime.now(UTC)
        return result


class OpenLibraryProvider(BaseProvider):
    """Open Library adapter that returns standardized raw evidence items."""

    provider_name = "open_library"
    capabilities = (
        ProviderCapability.SEARCH
        | ProviderCapability.AUTHORS
        | ProviderCapability.CATEGORIES
        | ProviderCapability.PUBLISHED_DATE
    )

    def _normalize_doc(self, *, query: ProviderQuery, doc: dict[str, object]) -> RawSourceItem | None:
        title = _normalize_string(doc.get("title"), max_length=512)
        if title is None:
            return None

        source_key = _normalize_string(doc.get("key"), max_length=255)
        source_url = f"https://openlibrary.org{source_key}" if source_key else None
        subtitle = _normalize_string(doc.get("subtitle"), max_length=512)
        authors = _normalize_string_list(doc.get("author_name", []), limit=8, max_item_length=120)
        categories = _normalize_open_library_subjects(doc)
        published_date_raw = _normalize_string(doc.get("first_publish_year"), max_length=50)
        dedupe_key = source_key or f"{title.casefold()}::{(source_url or '').casefold()}"

        return self._make_raw_source_item(
            query=query,
            title=title,
            dedupe_key=dedupe_key,
            provider_item_id=source_key,
            source_url=source_url,
            subtitle=subtitle,
            authors=authors,
            categories=categories,
            description_text=None,
            published_date_raw=published_date_raw,
            average_rating=None,
            rating_count=None,
            review_count=None,
            raw_payload=doc,
        )

    def search(
        self,
        *,
        client: httpx.Client,
        query: ProviderQuery,
        policy: ProviderRequestPolicy,
    ) -> ProviderQueryResult:
        result = ProviderQueryResult(provider_name=self.provider_name, query=query)
        payload = _request_json(
            client=client,
            provider_name=self.provider_name,
            query=query,
            url="https://openlibrary.org/search.json",
            params={"q": query.text, "limit": 20},
            policy=policy,
        )

        items: list[RawSourceItem] = []
        for doc in payload.get("docs", []):
            if not isinstance(doc, dict):
                continue
            normalized_item = self._normalize_doc(query=query, doc=doc)
            if normalized_item is not None:
                items.append(normalized_item)

        result.items = items
        result.completed_at = datetime.now(UTC)
        return result


class ProviderRegistry:
    """Registry that orchestrates provider fan-out and standardized result aggregation."""

    def __init__(
        self,
        providers: Sequence[BaseProvider],
        *,
        request_policy: ProviderRequestPolicy | None = None,
        query_hooks: Sequence[QueryExpansionHook] | None = None,
    ) -> None:
        self._providers = {provider.provider_name: provider for provider in providers}
        self._request_policy = request_policy or ProviderRequestPolicy()
        self._query_hooks = tuple(query_hooks or DEFAULT_QUERY_HOOKS)

    def register(self, provider: BaseProvider) -> None:
        """Register or replace a provider instance by name."""
        self._providers[provider.provider_name] = provider

    def list_enabled(self) -> list[BaseProvider]:
        """Return enabled providers in a stable order."""
        return [self._providers[name] for name in sorted(self._providers)]

    def build_queries(self, seed_niche: str) -> list[ProviderQuery]:
        """Build the canonical query set for a research run."""
        queries: list[ProviderQuery] = []
        for hook in self._query_hooks:
            queries = hook.expand(seed_niche, queries)
        return _dedupe_queries(queries)

    def _execute_provider_query(
        self,
        *,
        task_index: int,
        provider: BaseProvider,
        query: ProviderQuery,
    ) -> _ProviderTaskExecution:
        """Execute one provider query with isolated client state."""
        try:
            with httpx.Client() as client:
                result = provider.search(client=client, query=query, policy=self._request_policy)
        except ProviderSearchError as exc:
            logger.warning(
                "Provider query failed.",
                extra={
                    "provider_name": provider.provider_name,
                    "query_text": query.text,
                    "query_kind": query.kind,
                    "retryable": exc.retryable,
                },
            )
            return _ProviderTaskExecution(
                task_index=task_index,
                failure=ProviderFailure(
                    provider_name=provider.provider_name,
                    query=query,
                    error_type=exc.__class__.__name__,
                    message=str(exc),
                    retryable=exc.retryable,
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            logger.exception(
                "Provider query failed with unexpected error.",
                extra={
                    "provider_name": provider.provider_name,
                    "query_text": query.text,
                    "query_kind": query.kind,
                },
            )
            return _ProviderTaskExecution(
                task_index=task_index,
                failure=ProviderFailure(
                    provider_name=provider.provider_name,
                    query=query,
                    error_type=exc.__class__.__name__,
                    message=str(exc),
                    retryable=False,
                ),
            )
        return _ProviderTaskExecution(task_index=task_index, result=result)

    def search(self, seed_niche: str, *, raise_on_total_failure: bool = False) -> ProviderSearchBatchResult:
        """Fan out to all providers and aggregate raw evidence items."""
        queries = self.build_queries(seed_niche)
        batch = ProviderSearchBatchResult(seed_niche=seed_niche, queries=queries)

        task_specs: list[tuple[int, BaseProvider, ProviderQuery]] = []
        for provider in self.list_enabled():
            provider_queries = _dedupe_queries(provider.expand_queries(seed_niche, queries))
            for query in provider_queries:
                task_specs.append((len(task_specs), provider, query))

        if not task_specs:
            return batch

        max_workers = min(max(1, self._request_policy.max_concurrency), len(task_specs))
        logger.info(
            "Starting provider fan-out.",
            extra={
                "seed_niche": seed_niche,
                "provider_count": len(self.list_enabled()),
                "task_count": len(task_specs),
                "max_concurrency": max_workers,
            },
        )

        task_executions: list[_ProviderTaskExecution] = []
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="provider-fanout") as executor:
            futures = [
                executor.submit(self._execute_provider_query, task_index=task_index, provider=provider, query=query)
                for task_index, provider, query in task_specs
            ]
            for future in as_completed(futures):
                task_executions.append(future.result())

        for execution in sorted(task_executions, key=lambda item: item.task_index):
            if execution.result is not None:
                batch.results.append(execution.result)
            elif execution.failure is not None:
                batch.failures.append(execution.failure)

        if raise_on_total_failure and not batch.all_items and batch.failures:
            raise RuntimeError(f"All providers failed for seed niche '{seed_niche}'.")
        return batch


DEFAULT_QUERY_HOOKS: tuple[QueryExpansionHook, ...] = (
    DefaultBookQueryExpansionHook(),
    MarketplaceIntentQueryExpansionHook(),
)

DEFAULT_PROVIDER_FACTORIES: dict[str, type[BaseProvider]] = {
    "google_books": GoogleBooksProvider,
    "open_library": OpenLibraryProvider,
}


def build_enabled_providers(enabled_provider_names: Sequence[str]) -> list[BaseProvider]:
    """Instantiate the requested provider set."""
    providers: list[BaseProvider] = []
    for provider_name in enabled_provider_names:
        normalized_name = provider_name.strip().lower()
        provider_factory = DEFAULT_PROVIDER_FACTORIES.get(normalized_name)
        if provider_factory is None:
            raise ValueError(f"Unsupported provider '{provider_name}'.")
        providers.append(provider_factory())
    return providers
