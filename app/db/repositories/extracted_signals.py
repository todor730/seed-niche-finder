"""Repository queries for extracted signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.db.models import ExtractedSignal
from app.db.repositories import PageResult
from app.schemas.evidence import ExtractedSignalCreate


@dataclass(slots=True)
class ExtractedSignalListFilters:
    """Supported filters for listing extracted signals within a run."""

    signal_type: str | None = None
    cluster_id: UUID | None = None
    source_item_id: UUID | None = None
    normalized_value: str | None = None
    min_confidence: float | None = None
    limit: int = 100
    offset: int = 0


class ExtractedSignalRepository:
    """Thin persistence access for extracted signal entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, payload: ExtractedSignalCreate) -> ExtractedSignal:
        """Create and flush an extracted signal record."""
        signal = ExtractedSignal(**payload.model_dump(exclude_none=True))
        self.session.add(signal)
        self.session.flush()
        return signal

    def bulk_create(self, payloads: Sequence[ExtractedSignalCreate]) -> list[ExtractedSignal]:
        """Create and flush many extracted signal records."""
        signals = [ExtractedSignal(**payload.model_dump(exclude_none=True)) for payload in payloads]
        self.session.add_all(signals)
        self.session.flush()
        return signals

    def get_by_id(self, extracted_signal_id: UUID) -> ExtractedSignal | None:
        """Return an extracted signal by primary key."""
        return self.session.scalar(select(ExtractedSignal).where(ExtractedSignal.id == extracted_signal_id))

    def list_by_run(self, *, run_id: UUID, filters: ExtractedSignalListFilters | None = None) -> PageResult[ExtractedSignal]:
        """List extracted signals for a research run."""
        filters = filters or ExtractedSignalListFilters()
        statement = select(ExtractedSignal).where(ExtractedSignal.run_id == run_id)
        count_statement = select(func.count()).select_from(ExtractedSignal).where(ExtractedSignal.run_id == run_id)

        statement, count_statement = self._apply_filters(statement, count_statement, filters)
        statement = statement.order_by(ExtractedSignal.confidence.desc(), ExtractedSignal.created_at.desc()).limit(filters.limit).offset(filters.offset)

        items = list(self.session.scalars(statement))
        total = self.session.scalar(count_statement) or 0
        return PageResult(items=items, total=total, limit=filters.limit, offset=filters.offset)

    def list_by_source_item(self, *, source_item_id: UUID) -> list[ExtractedSignal]:
        """List extracted signals for one source item."""
        statement = (
            select(ExtractedSignal)
            .where(ExtractedSignal.source_item_id == source_item_id)
            .order_by(ExtractedSignal.confidence.desc(), ExtractedSignal.created_at.desc())
        )
        return list(self.session.scalars(statement))

    def update_cluster(self, *, extracted_signal_id: UUID, cluster_id: UUID | None) -> ExtractedSignal | None:
        """Assign or clear a cluster reference for one extracted signal."""
        signal = self.get_by_id(extracted_signal_id)
        if signal is None:
            return None
        signal.cluster_id = cluster_id
        self.session.flush()
        return signal

    def bulk_assign_cluster(self, *, extracted_signal_ids: Sequence[UUID], cluster_id: UUID | None) -> int:
        """Assign or clear a cluster reference for many extracted signals."""
        if not extracted_signal_ids:
            return 0
        statement = update(ExtractedSignal).where(ExtractedSignal.id.in_(list(extracted_signal_ids))).values(cluster_id=cluster_id)
        result = self.session.execute(statement)
        self.session.flush()
        return result.rowcount or 0

    @staticmethod
    def _apply_filters(
        statement: Select[tuple[ExtractedSignal]],
        count_statement: Select[tuple[int]],
        filters: ExtractedSignalListFilters,
    ) -> tuple[Select[tuple[ExtractedSignal]], Select[tuple[int]]]:
        """Apply list filters to both extracted signal statements."""
        if filters.signal_type is not None:
            statement = statement.where(ExtractedSignal.signal_type == filters.signal_type)
            count_statement = count_statement.where(ExtractedSignal.signal_type == filters.signal_type)
        if filters.cluster_id is not None:
            statement = statement.where(ExtractedSignal.cluster_id == filters.cluster_id)
            count_statement = count_statement.where(ExtractedSignal.cluster_id == filters.cluster_id)
        if filters.source_item_id is not None:
            statement = statement.where(ExtractedSignal.source_item_id == filters.source_item_id)
            count_statement = count_statement.where(ExtractedSignal.source_item_id == filters.source_item_id)
        if filters.normalized_value is not None:
            statement = statement.where(ExtractedSignal.normalized_value == filters.normalized_value)
            count_statement = count_statement.where(ExtractedSignal.normalized_value == filters.normalized_value)
        if filters.min_confidence is not None:
            statement = statement.where(ExtractedSignal.confidence >= filters.min_confidence)
            count_statement = count_statement.where(ExtractedSignal.confidence >= filters.min_confidence)
        return statement, count_statement
