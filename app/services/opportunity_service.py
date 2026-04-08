"""Opportunity read service backed by persisted SQLAlchemy models."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.api.dependencies import CurrentUser
from app.core.errors import OpportunityNotFoundError, RunNotFoundError
from app.db.models import Opportunity, ResearchRun
from app.services.shared import ListResult, resolve_user_id, to_opportunity_details, to_opportunity_list_item


class OpportunityService:
    """Query service for opportunity list/detail API operations."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_run_opportunities(
        self,
        *,
        current_user: CurrentUser,
        run_id: UUID,
        min_score: float | None,
        sort_by: str,
        sort_order: str,
        page: int,
        page_size: int,
    ) -> ListResult:
        """List persisted opportunities for a given run."""
        with self._session_factory() as session:
            run = session.scalar(select(ResearchRun).where(ResearchRun.id == run_id, ResearchRun.user_id == resolve_user_id(current_user)))
            if run is None:
                raise RunNotFoundError(str(run_id))

            statement = (
                select(Opportunity)
                .where(Opportunity.run_id == run_id)
                .options(selectinload(Opportunity.keyword_candidate), selectinload(Opportunity.research_run))
            )
            items = [to_opportunity_list_item(opportunity) for opportunity in session.scalars(statement)]
            if min_score is not None:
                items = [item for item in items if item.score_breakdown.opportunity_score >= min_score]

            items.sort(key=lambda item: self._sort_value(item, sort_by), reverse=sort_order == "desc")
            total = len(items)
            offset = (page - 1) * page_size
            return ListResult(items=items[offset : offset + page_size], total=total, limit=page_size, offset=offset)

    def get_opportunity(self, *, current_user: CurrentUser, opportunity_id: UUID):
        """Return a persisted opportunity detail payload."""
        with self._session_factory() as session:
            statement = (
                select(Opportunity)
                .where(Opportunity.id == opportunity_id)
                .options(selectinload(Opportunity.keyword_candidate), selectinload(Opportunity.research_run))
            )
            opportunity = session.scalar(statement)
            if opportunity is None or opportunity.research_run.user_id != resolve_user_id(current_user):
                raise OpportunityNotFoundError(str(opportunity_id))
            return to_opportunity_details(opportunity)

    @staticmethod
    def _sort_value(item, sort_by: str):
        if sort_by == "demand_score":
            return item.score_breakdown.demand_score
        if sort_by == "competition_score":
            return item.score_breakdown.competition_score
        if sort_by == "opportunity_score":
            return item.score_breakdown.opportunity_score
        return item.created_at
