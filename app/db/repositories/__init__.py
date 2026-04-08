"""Persistence-focused repository helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class PageResult(Generic[T]):
    """Simple paginated result container for repository queries."""

    items: list[T]
    total: int
    limit: int
    offset: int


from app.db.repositories.extracted_signals import ExtractedSignalListFilters, ExtractedSignalRepository
from app.db.repositories.niche_hypotheses import NicheHypothesisListFilters, NicheHypothesisRepository
from app.db.repositories.niche_scores import NicheScoreListFilters, NicheScoreRepository
from app.db.repositories.provider_failures import ProviderFailureRepository
from app.db.repositories.signal_clusters import SignalClusterListFilters, SignalClusterRepository
from app.db.repositories.source_items import SourceItemListFilters, SourceItemRepository
from app.db.repositories.source_item_query_links import SourceItemQueryLinkRepository
from app.db.repositories.source_queries import SourceQueryRepository

__all__ = [
    "ExtractedSignalListFilters",
    "ExtractedSignalRepository",
    "NicheHypothesisListFilters",
    "NicheHypothesisRepository",
    "NicheScoreListFilters",
    "NicheScoreRepository",
    "PageResult",
    "ProviderFailureRepository",
    "SignalClusterListFilters",
    "SignalClusterRepository",
    "SourceItemListFilters",
    "SourceItemQueryLinkRepository",
    "SourceItemRepository",
    "SourceQueryRepository",
]
