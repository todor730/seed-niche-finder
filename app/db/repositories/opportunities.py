"""Repository queries for opportunities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import Opportunity, OpportunityStatus
from app.db.repositories import PageResult

OpportunitySortField = Literal["created_at", "opportunity_score"]
SortDirection = Literal["asc", "desc"]


@dataclass(slots=True)
class RunOpportunityListFilters:
    """Supported filters and sorting for run opportunities."""

    status: OpportunityStatus | None = None
    keyword_candidate_id: UUID | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    sort_by: OpportunitySortField = "opportunity_score"
    sort_direction: SortDirection = "desc"
    limit: int = 50
    offset: int = 0


class OpportunityRepository:
    """Thin persistence access for opportunity entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, opportunity_id: UUID) -> Opportunity | None:
        """Return an opportunity by primary key."""
        statement = select(Opportunity).where(Opportunity.id == opportunity_id)
        return self.session.scalar(statement)

    def list_for_run(
        self,
        *,
        run_id: UUID,
        filters: RunOpportunityListFilters | None = None,
    ) -> PageResult[Opportunity]:
        """List opportunities for a research run with sorting support."""
        filters = filters or RunOpportunityListFilters()
        statement = select(Opportunity).where(Opportunity.run_id == run_id)
        count_statement = select(func.count()).select_from(Opportunity).where(Opportunity.run_id == run_id)

        statement, count_statement = self._apply_filters(statement, count_statement, filters)
        statement = statement.order_by(self._build_sort_clause(filters)).limit(filters.limit).offset(filters.offset)

        items = list(self.session.scalars(statement))
        total = self.session.scalar(count_statement) or 0
        return PageResult(items=items, total=total, limit=filters.limit, offset=filters.offset)

    @staticmethod
    def _apply_filters(
        statement: Select[tuple[Opportunity]],
        count_statement: Select[tuple[int]],
        filters: RunOpportunityListFilters,
    ) -> tuple[Select[tuple[Opportunity]], Select[tuple[int]]]:
        """Apply list filters to both opportunity query statements."""
        if filters.status is not None:
            statement = statement.where(Opportunity.status == filters.status)
            count_statement = count_statement.where(Opportunity.status == filters.status)
        if filters.keyword_candidate_id is not None:
            statement = statement.where(Opportunity.keyword_candidate_id == filters.keyword_candidate_id)
            count_statement = count_statement.where(Opportunity.keyword_candidate_id == filters.keyword_candidate_id)
        if filters.created_after is not None:
            statement = statement.where(Opportunity.created_at >= filters.created_after)
            count_statement = count_statement.where(Opportunity.created_at >= filters.created_after)
        if filters.created_before is not None:
            statement = statement.where(Opportunity.created_at <= filters.created_before)
            count_statement = count_statement.where(Opportunity.created_at <= filters.created_before)
        return statement, count_statement

    @staticmethod
    def _build_sort_clause(filters: RunOpportunityListFilters):
        """Build the requested sort clause for opportunity listings."""
        sortable_column = Opportunity.opportunity_score if filters.sort_by == "opportunity_score" else Opportunity.created_at
        if filters.sort_direction == "asc":
            return sortable_column.asc().nulls_last()
        return sortable_column.desc().nulls_last()

