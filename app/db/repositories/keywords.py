"""Repository queries for keyword candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import KeywordCandidate, KeywordCandidateStatus
from app.db.repositories import PageResult


@dataclass(slots=True)
class RunKeywordListFilters:
    """Supported filters for listing keywords within a run."""

    status: KeywordCandidateStatus | None = None
    keyword_text: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 50
    offset: int = 0


class KeywordRepository:
    """Thin persistence access for keyword candidate entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, keyword_id: UUID) -> KeywordCandidate | None:
        """Return a keyword candidate by primary key."""
        statement = select(KeywordCandidate).where(KeywordCandidate.id == keyword_id)
        return self.session.scalar(statement)

    def list_for_run(
        self,
        *,
        run_id: UUID,
        filters: RunKeywordListFilters | None = None,
    ) -> PageResult[KeywordCandidate]:
        """List keyword candidates for a research run."""
        filters = filters or RunKeywordListFilters()
        statement = select(KeywordCandidate).where(KeywordCandidate.run_id == run_id)
        count_statement = select(func.count()).select_from(KeywordCandidate).where(KeywordCandidate.run_id == run_id)

        statement, count_statement = self._apply_filters(statement, count_statement, filters)
        statement = statement.order_by(KeywordCandidate.created_at.desc()).limit(filters.limit).offset(filters.offset)

        items = list(self.session.scalars(statement))
        total = self.session.scalar(count_statement) or 0
        return PageResult(items=items, total=total, limit=filters.limit, offset=filters.offset)

    @staticmethod
    def _apply_filters(
        statement: Select[tuple[KeywordCandidate]],
        count_statement: Select[tuple[int]],
        filters: RunKeywordListFilters,
    ) -> tuple[Select[tuple[KeywordCandidate]], Select[tuple[int]]]:
        """Apply list filters to both keyword query statements."""
        if filters.status is not None:
            statement = statement.where(KeywordCandidate.status == filters.status)
            count_statement = count_statement.where(KeywordCandidate.status == filters.status)
        if filters.keyword_text:
            pattern = f"%{filters.keyword_text.strip()}%"
            statement = statement.where(KeywordCandidate.keyword_text.ilike(pattern))
            count_statement = count_statement.where(KeywordCandidate.keyword_text.ilike(pattern))
        if filters.created_after is not None:
            statement = statement.where(KeywordCandidate.created_at >= filters.created_after)
            count_statement = count_statement.where(KeywordCandidate.created_at >= filters.created_after)
        if filters.created_before is not None:
            statement = statement.where(KeywordCandidate.created_at <= filters.created_before)
            count_statement = count_statement.where(KeywordCandidate.created_at <= filters.created_before)
        return statement, count_statement

