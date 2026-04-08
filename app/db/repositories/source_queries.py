"""Repository queries for persisted source queries."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import SourceQuery
from app.db.repositories import PageResult
from app.schemas.evidence import SourceQueryCreate


class SourceQueryRepository:
    """Thin persistence access for source query entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, payload: SourceQueryCreate) -> SourceQuery:
        """Create and flush a source query record."""
        source_query = SourceQuery(**payload.model_dump(exclude_none=True))
        self.session.add(source_query)
        self.session.flush()
        return source_query

    def get_by_unique_key(
        self,
        *,
        run_id: UUID,
        provider_name: str,
        query_text: str,
        query_kind: str | None,
    ) -> SourceQuery | None:
        """Return a source query by its run/provider/query identity."""
        return self.session.scalar(
            select(SourceQuery).where(
                SourceQuery.run_id == run_id,
                SourceQuery.provider_name == provider_name,
                SourceQuery.query_text == query_text,
                SourceQuery.query_kind == query_kind,
            )
        )

    def get_or_create(self, payload: SourceQueryCreate) -> SourceQuery:
        """Return an existing source query or create it if absent."""
        existing = self.get_by_unique_key(
            run_id=payload.run_id,
            provider_name=payload.provider_name,
            query_text=payload.query_text,
            query_kind=payload.query_kind,
        )
        if existing is not None:
            existing.priority = payload.priority
            existing.tags_json = list(payload.tags_json)
            existing.item_count = payload.item_count
            self.session.flush()
            return existing
        return self.create(payload)

    def list_by_run(self, *, run_id: UUID, limit: int = 100, offset: int = 0) -> PageResult[SourceQuery]:
        """List persisted source queries for a research run."""
        statement: Select[tuple[SourceQuery]] = (
            select(SourceQuery)
            .where(SourceQuery.run_id == run_id)
            .order_by(SourceQuery.created_at.asc(), SourceQuery.query_text.asc())
            .limit(limit)
            .offset(offset)
        )
        count_statement = select(func.count()).select_from(SourceQuery).where(SourceQuery.run_id == run_id)
        items = list(self.session.scalars(statement))
        total = self.session.scalar(count_statement) or 0
        return PageResult(items=items, total=total, limit=limit, offset=offset)
