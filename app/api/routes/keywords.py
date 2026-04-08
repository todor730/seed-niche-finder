"""Keyword API routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import CurrentUser, ServicePlaceholder, get_current_user, get_keyword_service
from app.core.errors import KeywordNotFoundError
from app.schemas.common import CandidateStatus, ErrorEnvelope
from app.schemas.keyword import (
    KEYWORD_DETAILS_EXAMPLE,
    KeywordDetails,
    KeywordListItem,
    KeywordListResponse,
    KeywordMetrics,
    KeywordResponse,
)

router = APIRouter(tags=["keywords"])

KeywordSortField = Literal["created_at", "keyword_text", "demand_score", "competition_score", "opportunity_score"]
SortOrder = Literal["asc", "desc"]


@dataclass(slots=True)
class KeywordListResult:
    """Simple service-layer result for keyword listings."""

    items: list[KeywordListItem]
    total: int
    limit: int
    offset: int


class KeywordRouteService(Protocol):
    """Route-facing keyword service contract."""

    def list_run_keywords(
        self,
        *,
        current_user: CurrentUser,
        run_id: UUID,
        status: CandidateStatus | None,
        min_demand_score: float | None,
        max_competition_score: float | None,
        sort_by: KeywordSortField,
        sort_order: SortOrder,
        page: int,
        page_size: int,
    ) -> KeywordListResult: ...

    def get_keyword(self, *, current_user: CurrentUser, keyword_id: UUID) -> KeywordDetails: ...


def get_keyword_route_service(
    keyword_service=Depends(get_keyword_service),
) -> KeywordRouteService:
    """Resolve the configured keyword service or fall back to a stub implementation."""
    if isinstance(keyword_service, ServicePlaceholder):
        return _stub_keyword_service
    return keyword_service


@router.get(
    "/research-runs/{run_id}/keywords",
    response_model=KeywordListResponse,
    summary="List Run Keywords",
    operation_id="list_run_keywords",
    responses={404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}},
)
async def list_run_keywords(
    run_id: UUID,
    status: CandidateStatus | None = Query(default=None),
    min_demand_score: float | None = Query(default=None, ge=0.0, le=100.0),
    max_competition_score: float | None = Query(default=None, ge=0.0, le=100.0),
    sort_by: KeywordSortField = Query(default="created_at"),
    sort_order: SortOrder = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    keyword_service: KeywordRouteService = Depends(get_keyword_route_service),
) -> KeywordListResponse:
    """List keyword candidates for a research run."""
    result = keyword_service.list_run_keywords(
        current_user=current_user,
        run_id=run_id,
        status=status,
        min_demand_score=min_demand_score,
        max_competition_score=max_competition_score,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return KeywordListResponse(
        data=result.items,
        meta={"total": result.total, "limit": result.limit, "offset": result.offset},
        error=None,
    )


@router.get(
    "/keywords/{keyword_id}",
    response_model=KeywordResponse,
    summary="Get Keyword",
    operation_id="get_keyword",
    responses={404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}},
)
async def get_keyword(
    keyword_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    keyword_service: KeywordRouteService = Depends(get_keyword_route_service),
) -> KeywordResponse:
    """Return a single keyword candidate detail payload."""
    keyword = keyword_service.get_keyword(current_user=current_user, keyword_id=keyword_id)
    return KeywordResponse(data=keyword, meta={}, error=None)


class _StubKeywordService:
    """Small in-memory fallback service used until the real keyword service is wired."""

    def __init__(self) -> None:
        self._keywords: dict[UUID, KeywordDetails] = {
            UUID(str(KEYWORD_DETAILS_EXAMPLE["id"])): KeywordDetails.model_validate(KEYWORD_DETAILS_EXAMPLE)
        }

    def list_run_keywords(
        self,
        *,
        current_user: CurrentUser,
        run_id: UUID,
        status: CandidateStatus | None,
        min_demand_score: float | None,
        max_competition_score: float | None,
        sort_by: KeywordSortField,
        sort_order: SortOrder,
        page: int,
        page_size: int,
    ) -> KeywordListResult:
        items = [
            self._to_list_item(keyword)
            for keyword in self._keywords.values()
            if keyword.run_id == run_id
        ]
        if status is not None:
            items = [item for item in items if item.status == status]
        if min_demand_score is not None:
            items = [
                item for item in items if item.metrics.demand_score is not None and item.metrics.demand_score >= min_demand_score
            ]
        if max_competition_score is not None:
            items = [
                item
                for item in items
                if item.metrics.competition_score is not None and item.metrics.competition_score <= max_competition_score
            ]

        items.sort(key=lambda item: self._sort_value(item, sort_by), reverse=sort_order == "desc")

        total = len(items)
        offset = (page - 1) * page_size
        paged_items = items[offset : offset + page_size]
        return KeywordListResult(items=paged_items, total=total, limit=page_size, offset=offset)

    def get_keyword(self, *, current_user: CurrentUser, keyword_id: UUID) -> KeywordDetails:
        keyword = self._keywords.get(keyword_id)
        if keyword is None:
            raise KeywordNotFoundError(str(keyword_id))
        return keyword

    @staticmethod
    def _to_list_item(keyword: KeywordDetails) -> KeywordListItem:
        return KeywordListItem(
            id=keyword.id,
            run_id=keyword.run_id,
            keyword_text=keyword.keyword_text,
            status=keyword.status,
            metrics=KeywordMetrics(**keyword.metrics.model_dump()),
            opportunity_count=keyword.opportunity_count,
            competitor_count=keyword.competitor_count,
            created_at=keyword.created_at,
            updated_at=keyword.updated_at,
        )

    @staticmethod
    def _sort_value(item: KeywordListItem, sort_by: KeywordSortField):
        if sort_by == "keyword_text":
            return item.keyword_text.lower()
        if sort_by == "demand_score":
            return item.metrics.demand_score if item.metrics.demand_score is not None else -1.0
        if sort_by == "competition_score":
            return item.metrics.competition_score if item.metrics.competition_score is not None else 101.0
        if sort_by == "opportunity_score":
            return item.metrics.opportunity_score if item.metrics.opportunity_score is not None else -1.0
        return item.created_at


_stub_keyword_service = _StubKeywordService()
