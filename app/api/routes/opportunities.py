"""Opportunity API routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import CurrentUser, ServicePlaceholder, get_current_user, get_opportunity_service
from app.core.errors import OpportunityNotFoundError
from app.schemas.common import ErrorEnvelope
from app.schemas.opportunity import (
    OPPORTUNITY_DETAILS_EXAMPLE,
    OpportunityDetails,
    OpportunityListItem,
    OpportunityListResponse,
    OpportunityResponse,
    ScoreBreakdown,
)

router = APIRouter(tags=["opportunities"])

OpportunitySortField = Literal["created_at", "opportunity_score", "demand_score", "competition_score"]
SortOrder = Literal["asc", "desc"]


@dataclass(slots=True)
class OpportunityListResult:
    """Simple service-layer result for opportunity listings."""

    items: list[OpportunityListItem]
    total: int
    limit: int
    offset: int


class OpportunityRouteService(Protocol):
    """Route-facing opportunity service contract."""

    def list_run_opportunities(
        self,
        *,
        current_user: CurrentUser,
        run_id: UUID,
        min_score: float | None,
        sort_by: OpportunitySortField,
        sort_order: SortOrder,
        page: int,
        page_size: int,
    ) -> OpportunityListResult: ...

    def get_opportunity(self, *, current_user: CurrentUser, opportunity_id: UUID) -> OpportunityDetails: ...


def get_opportunity_route_service(
    opportunity_service=Depends(get_opportunity_service),
) -> OpportunityRouteService:
    """Resolve the configured opportunity service or fall back to a stub implementation."""
    if isinstance(opportunity_service, ServicePlaceholder):
        return _stub_opportunity_service
    return opportunity_service


@router.get(
    "/research-runs/{run_id}/opportunities",
    response_model=OpportunityListResponse,
    summary="List Run Opportunities",
    operation_id="list_run_opportunities",
    responses={404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}},
)
async def list_run_opportunities(
    run_id: UUID,
    min_score: float | None = Query(default=None, ge=0.0, le=100.0),
    sort_by: OpportunitySortField = Query(default="opportunity_score"),
    sort_order: SortOrder = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    opportunity_service: OpportunityRouteService = Depends(get_opportunity_route_service),
) -> OpportunityListResponse:
    """List opportunities for a research run."""
    result = opportunity_service.list_run_opportunities(
        current_user=current_user,
        run_id=run_id,
        min_score=min_score,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return OpportunityListResponse(
        data=result.items,
        meta={"total": result.total, "limit": result.limit, "offset": result.offset},
        error=None,
    )


@router.get(
    "/opportunities/{opportunity_id}",
    response_model=OpportunityResponse,
    summary="Get Opportunity",
    operation_id="get_opportunity",
    responses={404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}},
)
async def get_opportunity(
    opportunity_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    opportunity_service: OpportunityRouteService = Depends(get_opportunity_route_service),
) -> OpportunityResponse:
    """Return a single opportunity detail payload."""
    opportunity = opportunity_service.get_opportunity(current_user=current_user, opportunity_id=opportunity_id)
    return OpportunityResponse(data=opportunity, meta={}, error=None)


class _StubOpportunityService:
    """Small in-memory fallback service used until the real opportunity service is wired."""

    def __init__(self) -> None:
        self._opportunities: dict[UUID, OpportunityDetails] = {
            UUID(str(OPPORTUNITY_DETAILS_EXAMPLE["id"])): OpportunityDetails.model_validate(OPPORTUNITY_DETAILS_EXAMPLE)
        }

    def list_run_opportunities(
        self,
        *,
        current_user: CurrentUser,
        run_id: UUID,
        min_score: float | None,
        sort_by: OpportunitySortField,
        sort_order: SortOrder,
        page: int,
        page_size: int,
    ) -> OpportunityListResult:
        items = [
            self._to_list_item(opportunity)
            for opportunity in self._opportunities.values()
            if opportunity.run_id == run_id
        ]
        if min_score is not None:
            items = [
                item
                for item in items
                if item.score_breakdown.opportunity_score >= min_score
            ]

        items.sort(key=lambda item: self._sort_value(item, sort_by), reverse=sort_order == "desc")

        total = len(items)
        offset = (page - 1) * page_size
        paged_items = items[offset : offset + page_size]
        return OpportunityListResult(items=paged_items, total=total, limit=page_size, offset=offset)

    def get_opportunity(self, *, current_user: CurrentUser, opportunity_id: UUID) -> OpportunityDetails:
        opportunity = self._opportunities.get(opportunity_id)
        if opportunity is None:
            raise OpportunityNotFoundError(str(opportunity_id))
        return opportunity

    @staticmethod
    def _to_list_item(opportunity: OpportunityDetails) -> OpportunityListItem:
        return OpportunityListItem(
            id=opportunity.id,
            run_id=opportunity.run_id,
            keyword_id=opportunity.keyword_id,
            keyword_text=opportunity.keyword_text,
            title=opportunity.title,
            summary=opportunity.summary,
            recommended=opportunity.recommended,
            score_breakdown=ScoreBreakdown(**opportunity.score_breakdown.model_dump()),
            rationale_summary=opportunity.rationale_summary,
            positives=list(opportunity.positives),
            risks=list(opportunity.risks),
            landing_page_angles=list(opportunity.landing_page_angles),
            created_at=opportunity.created_at,
            updated_at=opportunity.updated_at,
        )

    @staticmethod
    def _sort_value(item: OpportunityListItem, sort_by: OpportunitySortField):
        if sort_by == "demand_score":
            return item.score_breakdown.demand_score
        if sort_by == "competition_score":
            return item.score_breakdown.competition_score
        if sort_by == "opportunity_score":
            return item.score_breakdown.opportunity_score
        return item.created_at


_stub_opportunity_service = _StubOpportunityService()
