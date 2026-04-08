"""Repository queries for research runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import ResearchRun, ResearchRunStatus
from app.db.repositories import PageResult


@dataclass(slots=True)
class ResearchRunListFilters:
    """Supported filters for listing research runs."""

    user_id: UUID | None = None
    status: ResearchRunStatus | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 50
    offset: int = 0


class ResearchRunRepository:
    """Thin persistence access for research run entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        user_id: UUID,
        title: str | None = None,
        status: ResearchRunStatus = ResearchRunStatus.PENDING,
    ) -> ResearchRun:
        """Create and flush a research run record."""
        research_run = ResearchRun(
            user_id=user_id,
            title=title,
            status=status,
        )
        self.session.add(research_run)
        self.session.flush()
        self.session.refresh(research_run)
        return research_run

    def get_by_id(self, run_id: UUID) -> ResearchRun | None:
        """Return a research run by primary key."""
        statement = select(ResearchRun).where(ResearchRun.id == run_id)
        return self.session.scalar(statement)

    def list(self, filters: ResearchRunListFilters | None = None) -> PageResult[ResearchRun]:
        """List research runs using common orchestration filters."""
        filters = filters or ResearchRunListFilters()
        statement = select(ResearchRun)
        count_statement = select(func.count()).select_from(ResearchRun)

        statement, count_statement = self._apply_filters(statement, count_statement, filters)
        statement = statement.order_by(ResearchRun.created_at.desc()).limit(filters.limit).offset(filters.offset)

        items = list(self.session.scalars(statement))
        total = self.session.scalar(count_statement) or 0
        return PageResult(items=items, total=total, limit=filters.limit, offset=filters.offset)

    @staticmethod
    def _apply_filters(
        statement: Select[tuple[ResearchRun]],
        count_statement: Select[tuple[int]],
        filters: ResearchRunListFilters,
    ) -> tuple[Select[tuple[ResearchRun]], Select[tuple[int]]]:
        """Apply common list filters to both query and count statements."""
        if filters.user_id is not None:
            statement = statement.where(ResearchRun.user_id == filters.user_id)
            count_statement = count_statement.where(ResearchRun.user_id == filters.user_id)
        if filters.status is not None:
            statement = statement.where(ResearchRun.status == filters.status)
            count_statement = count_statement.where(ResearchRun.status == filters.status)
        if filters.created_after is not None:
            statement = statement.where(ResearchRun.created_at >= filters.created_after)
            count_statement = count_statement.where(ResearchRun.created_at >= filters.created_after)
        if filters.created_before is not None:
            statement = statement.where(ResearchRun.created_at <= filters.created_before)
            count_statement = count_statement.where(ResearchRun.created_at <= filters.created_before)
        return statement, count_statement

