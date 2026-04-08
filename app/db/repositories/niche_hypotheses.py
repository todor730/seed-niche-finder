"""Repository queries for niche hypotheses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import NicheHypothesis, NicheHypothesisStatus
from app.db.repositories import PageResult
from app.schemas.evidence import NicheHypothesisCreate, NicheHypothesisRankingUpdate


@dataclass(slots=True)
class NicheHypothesisListFilters:
    """Supported filters for listing niche hypotheses within a run."""

    status: NicheHypothesisStatus | None = None
    primary_cluster_id: UUID | None = None
    min_overall_score: float | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 100
    offset: int = 0


class NicheHypothesisRepository:
    """Thin persistence access for niche hypothesis entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, payload: NicheHypothesisCreate) -> NicheHypothesis:
        """Create and flush a niche hypothesis record."""
        hypothesis = NicheHypothesis(**payload.model_dump(exclude_none=True))
        self.session.add(hypothesis)
        self.session.flush()
        return hypothesis

    def bulk_create(self, payloads: Sequence[NicheHypothesisCreate]) -> list[NicheHypothesis]:
        """Create and flush many niche hypothesis records."""
        hypotheses = [NicheHypothesis(**payload.model_dump(exclude_none=True)) for payload in payloads]
        self.session.add_all(hypotheses)
        self.session.flush()
        return hypotheses

    def get_by_id(self, hypothesis_id: UUID) -> NicheHypothesis | None:
        """Return a niche hypothesis by primary key."""
        return self.session.scalar(select(NicheHypothesis).where(NicheHypothesis.id == hypothesis_id))

    def list_by_run(self, *, run_id: UUID, filters: NicheHypothesisListFilters | None = None) -> PageResult[NicheHypothesis]:
        """List niche hypotheses for a research run."""
        filters = filters or NicheHypothesisListFilters()
        statement = select(NicheHypothesis).where(NicheHypothesis.run_id == run_id)
        count_statement = select(func.count()).select_from(NicheHypothesis).where(NicheHypothesis.run_id == run_id)

        statement, count_statement = self._apply_filters(statement, count_statement, filters)
        statement = statement.order_by(NicheHypothesis.rank_position.asc().nulls_last(), NicheHypothesis.overall_score.desc().nulls_last()).limit(filters.limit).offset(filters.offset)

        items = list(self.session.scalars(statement))
        total = self.session.scalar(count_statement) or 0
        return PageResult(items=items, total=total, limit=filters.limit, offset=filters.offset)

    def update_status(self, *, hypothesis_id: UUID, status: NicheHypothesisStatus) -> NicheHypothesis | None:
        """Update the status of a single niche hypothesis."""
        hypothesis = self.get_by_id(hypothesis_id)
        if hypothesis is None:
            return None
        hypothesis.status = status
        self.session.flush()
        return hypothesis

    def update_ranking(self, *, hypothesis_id: UUID, payload: NicheHypothesisRankingUpdate) -> NicheHypothesis | None:
        """Update ranking and rationale fields for a niche hypothesis."""
        hypothesis = self.get_by_id(hypothesis_id)
        if hypothesis is None:
            return None
        for field_name, value in payload.model_dump(exclude_unset=True).items():
            setattr(hypothesis, field_name, value)
        self.session.flush()
        return hypothesis

    @staticmethod
    def _apply_filters(
        statement: Select[tuple[NicheHypothesis]],
        count_statement: Select[tuple[int]],
        filters: NicheHypothesisListFilters,
    ) -> tuple[Select[tuple[NicheHypothesis]], Select[tuple[int]]]:
        """Apply list filters to both niche hypothesis statements."""
        if filters.status is not None:
            statement = statement.where(NicheHypothesis.status == filters.status)
            count_statement = count_statement.where(NicheHypothesis.status == filters.status)
        if filters.primary_cluster_id is not None:
            statement = statement.where(NicheHypothesis.primary_cluster_id == filters.primary_cluster_id)
            count_statement = count_statement.where(NicheHypothesis.primary_cluster_id == filters.primary_cluster_id)
        if filters.min_overall_score is not None:
            statement = statement.where(NicheHypothesis.overall_score >= filters.min_overall_score)
            count_statement = count_statement.where(NicheHypothesis.overall_score >= filters.min_overall_score)
        if filters.created_after is not None:
            statement = statement.where(NicheHypothesis.created_at >= filters.created_after)
            count_statement = count_statement.where(NicheHypothesis.created_at >= filters.created_after)
        if filters.created_before is not None:
            statement = statement.where(NicheHypothesis.created_at <= filters.created_before)
            count_statement = count_statement.where(NicheHypothesis.created_at <= filters.created_before)
        return statement, count_statement
