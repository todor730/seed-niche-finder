"""Repository queries for signal clusters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import SignalCluster
from app.db.repositories import PageResult
from app.schemas.evidence import SignalClusterCreate, SignalClusterUpdate


@dataclass(slots=True)
class SignalClusterListFilters:
    """Supported filters for listing signal clusters within a run."""

    signal_type: str | None = None
    min_source_count: int | None = None
    min_avg_confidence: float | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 100
    offset: int = 0


class SignalClusterRepository:
    """Thin persistence access for signal cluster entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, payload: SignalClusterCreate) -> SignalCluster:
        """Create and flush a signal cluster record."""
        cluster = SignalCluster(**payload.model_dump(exclude_none=True))
        self.session.add(cluster)
        self.session.flush()
        return cluster

    def bulk_create(self, payloads: Sequence[SignalClusterCreate]) -> list[SignalCluster]:
        """Create and flush many signal cluster records."""
        clusters = [SignalCluster(**payload.model_dump(exclude_none=True)) for payload in payloads]
        self.session.add_all(clusters)
        self.session.flush()
        return clusters

    def get_by_id(self, cluster_id: UUID) -> SignalCluster | None:
        """Return a signal cluster by primary key."""
        return self.session.scalar(select(SignalCluster).where(SignalCluster.id == cluster_id))

    def get_by_label(self, *, run_id: UUID, signal_type: str, canonical_label: str) -> SignalCluster | None:
        """Return a signal cluster by its canonical label within a run."""
        statement = select(SignalCluster).where(
            SignalCluster.run_id == run_id,
            SignalCluster.signal_type == signal_type,
            SignalCluster.canonical_label == canonical_label,
        )
        return self.session.scalar(statement)

    def list_by_run(self, *, run_id: UUID, filters: SignalClusterListFilters | None = None) -> PageResult[SignalCluster]:
        """List signal clusters for a research run."""
        filters = filters or SignalClusterListFilters()
        statement = select(SignalCluster).where(SignalCluster.run_id == run_id)
        count_statement = select(func.count()).select_from(SignalCluster).where(SignalCluster.run_id == run_id)

        statement, count_statement = self._apply_filters(statement, count_statement, filters)
        statement = statement.order_by(SignalCluster.source_count.desc(), SignalCluster.avg_confidence.desc()).limit(filters.limit).offset(filters.offset)

        items = list(self.session.scalars(statement))
        total = self.session.scalar(count_statement) or 0
        return PageResult(items=items, total=total, limit=filters.limit, offset=filters.offset)

    def update(self, *, cluster_id: UUID, payload: SignalClusterUpdate) -> SignalCluster | None:
        """Update mutable aggregate fields for a signal cluster."""
        cluster = self.get_by_id(cluster_id)
        if cluster is None:
            return None
        for field_name, value in payload.model_dump(exclude_unset=True).items():
            setattr(cluster, field_name, value)
        self.session.flush()
        return cluster

    @staticmethod
    def _apply_filters(
        statement: Select[tuple[SignalCluster]],
        count_statement: Select[tuple[int]],
        filters: SignalClusterListFilters,
    ) -> tuple[Select[tuple[SignalCluster]], Select[tuple[int]]]:
        """Apply list filters to both signal cluster statements."""
        if filters.signal_type is not None:
            statement = statement.where(SignalCluster.signal_type == filters.signal_type)
            count_statement = count_statement.where(SignalCluster.signal_type == filters.signal_type)
        if filters.min_source_count is not None:
            statement = statement.where(SignalCluster.source_count >= filters.min_source_count)
            count_statement = count_statement.where(SignalCluster.source_count >= filters.min_source_count)
        if filters.min_avg_confidence is not None:
            statement = statement.where(SignalCluster.avg_confidence >= filters.min_avg_confidence)
            count_statement = count_statement.where(SignalCluster.avg_confidence >= filters.min_avg_confidence)
        if filters.created_after is not None:
            statement = statement.where(SignalCluster.created_at >= filters.created_after)
            count_statement = count_statement.where(SignalCluster.created_at >= filters.created_after)
        if filters.created_before is not None:
            statement = statement.where(SignalCluster.created_at <= filters.created_before)
            count_statement = count_statement.where(SignalCluster.created_at <= filters.created_before)
        return statement, count_statement
