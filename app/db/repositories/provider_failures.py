"""Repository queries for persisted provider failures."""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import ProviderFailureRecord
from app.db.repositories import PageResult
from app.schemas.evidence import ProviderFailureCreate


class ProviderFailureRepository:
    """Thin persistence access for provider failure records."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, payload: ProviderFailureCreate) -> ProviderFailureRecord:
        """Create and flush one provider failure record."""
        record = ProviderFailureRecord(**payload.model_dump(exclude_none=True))
        self.session.add(record)
        self.session.flush()
        return record

    def bulk_create(self, payloads: Sequence[ProviderFailureCreate]) -> list[ProviderFailureRecord]:
        """Create and flush many provider failure records."""
        records = [ProviderFailureRecord(**payload.model_dump(exclude_none=True)) for payload in payloads]
        self.session.add_all(records)
        self.session.flush()
        return records

    def list_by_run(self, *, run_id: UUID, limit: int = 100, offset: int = 0) -> PageResult[ProviderFailureRecord]:
        """List provider failure records for a run."""
        statement: Select[tuple[ProviderFailureRecord]] = (
            select(ProviderFailureRecord)
            .where(ProviderFailureRecord.run_id == run_id)
            .order_by(ProviderFailureRecord.occurred_at.asc(), ProviderFailureRecord.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        count_statement = select(func.count()).select_from(ProviderFailureRecord).where(
            ProviderFailureRecord.run_id == run_id
        )
        items = list(self.session.scalars(statement))
        total = self.session.scalar(count_statement) or 0
        return PageResult(items=items, total=total, limit=limit, offset=offset)
