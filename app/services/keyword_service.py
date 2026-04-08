"""Keyword read service backed by persisted SQLAlchemy models."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.api.dependencies import CurrentUser
from app.core.errors import KeywordNotFoundError, RunNotFoundError
from app.db.models import KeywordCandidate, KeywordCandidateStatus, ResearchRun
from app.services.shared import ListResult, resolve_user_id, to_keyword_details, to_keyword_list_item


class KeywordService:
    """Query service for keyword list/detail API operations."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_run_keywords(
        self,
        *,
        current_user: CurrentUser,
        run_id: UUID,
        status,
        min_demand_score: float | None,
        max_competition_score: float | None,
        sort_by: str,
        sort_order: str,
        page: int,
        page_size: int,
    ) -> ListResult:
        """List persisted keywords for a given run."""
        with self._session_factory() as session:
            self._assert_owned_run(session, current_user, run_id)
            statement = (
                select(KeywordCandidate)
                .where(KeywordCandidate.run_id == run_id)
                .options(
                    selectinload(KeywordCandidate.keyword_metrics),
                    selectinload(KeywordCandidate.trend_metrics),
                    selectinload(KeywordCandidate.opportunities),
                    selectinload(KeywordCandidate.competitors),
                )
            )
            if status is not None:
                statement = statement.where(
                    KeywordCandidate.status == KeywordCandidateStatus(status.value if hasattr(status, "value") else status)
                )

            items = [to_keyword_list_item(keyword) for keyword in session.scalars(statement)]
            if min_demand_score is not None:
                items = [item for item in items if item.metrics.demand_score is not None and item.metrics.demand_score >= min_demand_score]
            if max_competition_score is not None:
                items = [
                    item
                    for item in items
                    if item.metrics.competition_score is not None and item.metrics.competition_score <= max_competition_score
                ]

            items.sort(key=lambda item: self._sort_value(item, sort_by), reverse=sort_order == "desc")
            total = len(items)
            offset = (page - 1) * page_size
            return ListResult(items=items[offset : offset + page_size], total=total, limit=page_size, offset=offset)

    def get_keyword(self, *, current_user: CurrentUser, keyword_id: UUID):
        """Return a persisted keyword detail payload."""
        with self._session_factory() as session:
            statement = (
                select(KeywordCandidate)
                .where(KeywordCandidate.id == keyword_id)
                .options(
                    selectinload(KeywordCandidate.keyword_metrics),
                    selectinload(KeywordCandidate.trend_metrics),
                    selectinload(KeywordCandidate.opportunities),
                    selectinload(KeywordCandidate.competitors),
                    selectinload(KeywordCandidate.research_run),
                )
            )
            keyword = session.scalar(statement)
            if keyword is None or keyword.research_run.user_id != resolve_user_id(current_user):
                raise KeywordNotFoundError(str(keyword_id))
            return to_keyword_details(keyword)

    @staticmethod
    def _assert_owned_run(session: Session, current_user: CurrentUser, run_id: UUID) -> None:
        run = session.scalar(select(ResearchRun).where(ResearchRun.id == run_id, ResearchRun.user_id == resolve_user_id(current_user)))
        if run is None:
            raise RunNotFoundError(str(run_id))

    @staticmethod
    def _sort_value(item, sort_by: str):
        if sort_by == "keyword_text":
            return item.keyword_text.lower()
        if sort_by == "demand_score":
            return item.metrics.demand_score if item.metrics.demand_score is not None else -1.0
        if sort_by == "competition_score":
            return item.metrics.competition_score if item.metrics.competition_score is not None else 101.0
        if sort_by == "opportunity_score":
            return item.metrics.opportunity_score if item.metrics.opportunity_score is not None else -1.0
        return item.created_at
