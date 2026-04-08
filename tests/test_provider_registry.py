from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest

from app.services.providers import (
    BaseProvider,
    ProviderQuery,
    ProviderQueryResult,
    ProviderRegistry,
    ProviderRequestPolicy,
    ProviderSearchError,
    RawSourceItem,
)


@dataclass
class StaticQueryHook:
    queries: list[ProviderQuery]

    def expand(self, seed_niche: str, queries: list[ProviderQuery]) -> list[ProviderQuery]:
        return [*queries, *self.queries]


class FakeProvider(BaseProvider):
    def __init__(self, provider_name: str, behavior: dict[str, list[RawSourceItem] | Exception]) -> None:
        self.provider_name = provider_name
        self._behavior = behavior

    def search(self, *, client: httpx.Client, query: ProviderQuery, policy: ProviderRequestPolicy) -> ProviderQueryResult:
        outcome = self._behavior[query.text]
        if isinstance(outcome, Exception):
            raise outcome
        return ProviderQueryResult(
            provider_name=self.provider_name,
            query=query,
            items=list(outcome),
        )


def make_item(*, provider_name: str, query_text: str, dedupe_key: str, title: str) -> RawSourceItem:
    return RawSourceItem(
        provider_name=provider_name,
        query_text=query_text,
        query_kind="seed",
        dedupe_key=dedupe_key,
        title=title,
        raw_payload={"title": title},
    )


def test_provider_registry_builds_deduped_queries_in_priority_order() -> None:
    registry = ProviderRegistry(
        providers=[],
        query_hooks=(
            StaticQueryHook(
                [
                    ProviderQuery(text=" romance ", kind="seed", priority=80),
                    ProviderQuery(text="romance books", kind="books", priority=60),
                ]
            ),
            StaticQueryHook(
                [
                    ProviderQuery(text="ROMANCE", kind="seed", priority=100),
                    ProviderQuery(text="romance books", kind="books", priority=90),
                ]
            ),
        ),
    )

    queries = registry.build_queries("romance")

    assert [(query.text, query.kind, query.priority) for query in queries] == [
        ("romance", "seed", 100),
        ("romance books", "books", 90),
    ]


def test_provider_registry_collects_partial_results_without_aborting() -> None:
    query = ProviderQuery(text="romance", kind="seed")
    success_provider = FakeProvider(
        "google_books",
        {"romance": [make_item(provider_name="google_books", query_text="romance", dedupe_key="g-1", title="Book One")]},
    )
    failing_provider = FakeProvider(
        "open_library",
        {"romance": ProviderSearchError("open_library", query, "provider down", retryable=True)},
    )
    registry = ProviderRegistry(
        providers=[success_provider, failing_provider],
        query_hooks=(StaticQueryHook([query]),),
    )

    batch = registry.search("romance")

    assert len(batch.results) == 1
    assert len(batch.failures) == 1
    assert batch.total_item_count == 1
    assert batch.all_items[0].provider_name == "google_books"
    assert batch.failures[0].provider_name == "open_library"
    assert batch.failures[0].retryable is True


def test_provider_registry_raises_when_all_providers_fail_and_requested() -> None:
    query = ProviderQuery(text="romance", kind="seed")
    failing_provider = FakeProvider(
        "open_library",
        {"romance": ProviderSearchError("open_library", query, "provider down", retryable=False)},
    )
    registry = ProviderRegistry(
        providers=[failing_provider],
        query_hooks=(StaticQueryHook([query]),),
    )

    with pytest.raises(RuntimeError, match="All providers failed"):
        registry.search("romance", raise_on_total_failure=True)
