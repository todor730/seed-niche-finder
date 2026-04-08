"""Repository queries for niche scores."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import NicheScore
from app.db.repositories import PageResult
from app.schemas.evidence import NicheScoreCreate, NicheScoreUpdate


@dataclass(slots=True)
class NicheScoreListFilters:
    """Supported filters for listing niche scores within a run."""

    score_type: str | None = None
    niche_hypothesis_id: UUID | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 100
    offset: int = 0


class NicheScoreRepository:
    """Thin persistence access for niche score entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, payload: NicheScoreCreate) -> NicheScore:
        """Create and flush a niche score record."""
        niche_score = NicheScore(**payload.model_dump(exclude_none=True))
        self.session.add(niche_score)
        self.session.flush()
        return niche_score

    def bulk_create(self, payloads: Sequence[NicheScoreCreate]) -> list[NicheScore]:
        """Create and flush many niche score records."""
        niche_scores = [NicheScore(**payload.model_dump(exclude_none=True)) for payload in payloads]
        self.session.add_all(niche_scores)
        self.session.flush()
        return niche_scores

    def get_by_id(self, niche_score_id: UUID) -> NicheScore | None:
        """Return a niche score by primary key."""
        return self.session.scalar(select(NicheScore).where(NicheScore.id == niche_score_id))

    def list_by_run(self, *, run_id: UUID, filters: NicheScoreListFilters | None = None) -> PageResult[NicheScore]:
        """List niche scores for a research run."""
        filters = filters or NicheScoreListFilters()
        statement = select(NicheScore).where(NicheScore.run_id == run_id)
        count_statement = select(func.count()).select_from(NicheScore).where(NicheScore.run_id == run_id)

        statement, count_statement = self._apply_filters(statement, count_statement, filters)
        statement = statement.order_by(NicheScore.score_type.asc(), NicheScore.score_value.desc()).limit(filters.limit).offset(filters.offset)

        items = list(self.session.scalars(statement))
        total = self.session.scalar(count_statement) or 0
        return PageResult(items=items, total=total, limit=filters.limit, offset=filters.offset)

    def list_by_hypothesis(self, *, niche_hypothesis_id: UUID) -> list[NicheScore]:
        """List all score components for one niche hypothesis."""
        statement = (
            select(NicheScore)
            .where(NicheScore.niche_hypothesis_id == niche_hypothesis_id)
            .order_by(NicheScore.score_type.asc(), NicheScore.score_value.desc())
        )
        return list(self.session.scalars(statement))

    def update(self, *, niche_score_id: UUID, payload: NicheScoreUpdate) -> NicheScore | None:
        """Update mutable fields for a niche score."""
        niche_score = self.get_by_id(niche_score_id)
        if niche_score is None:
            return None
        for field_name, value in payload.model_dump(exclude_unset=True).items():
            setattr(niche_score, field_name, value)
        self.session.flush()
        return niche_score

    @staticmethod
    def _apply_filters(
        statement: Select[tuple[NicheScore]],
        count_statement: Select[tuple[int]],
        filters: NicheScoreListFilters,
    ) -> tuple[Select[tuple[NicheScore]], Select[tuple[int]]]:
        """Apply list filters to both niche score statements."""
        if filters.score_type is not None:
            statement = statement.where(NicheScore.score_type == filters.score_type)
            count_statement = count_statement.where(NicheScore.score_type == filters.score_type)
        if filters.niche_hypothesis_id is not None:
            statement = statement.where(NicheScore.niche_hypothesis_id == filters.niche_hypothesis_id)
            count_statement = count_statement.where(NicheScore.niche_hypothesis_id == filters.niche_hypothesis_id)
        if filters.created_after is not None:
            statement = statement.where(NicheScore.created_at >= filters.created_after)
            count_statement = count_statement.where(NicheScore.created_at >= filters.created_after)
        if filters.created_before is not None:
            statement = statement.where(NicheScore.created_at <= filters.created_before)
            count_statement = count_statement.where(NicheScore.created_at <= filters.created_before)
        return statement, count_statement
