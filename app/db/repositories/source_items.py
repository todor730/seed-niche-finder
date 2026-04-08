"""Repository queries for source items."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.db.models import SourceItem, SourceItemStatus
from app.db.repositories import PageResult
from app.schemas.evidence import SourceItemCreate


@dataclass(slots=True)
class SourceItemListFilters:
    """Supported filters for listing source items within a run."""

    provider_name: str | None = None
    status: SourceItemStatus | None = None
    query_text: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    fetched_after: datetime | None = None
    fetched_before: datetime | None = None
    limit: int = 100
    offset: int = 0


class SourceItemRepository:
    """Thin persistence access for source item entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, payload: SourceItemCreate) -> SourceItem:
        """Create and flush a source item record."""
        source_item = SourceItem(**payload.model_dump(exclude_none=True))
        self.session.add(source_item)
        self.session.flush()
        return source_item

    def bulk_create(self, payloads: Sequence[SourceItemCreate]) -> list[SourceItem]:
        """Create and flush many source item records."""
        items = [SourceItem(**payload.model_dump(exclude_none=True)) for payload in payloads]
        self.session.add_all(items)
        self.session.flush()
        return items

    def get_by_id(self, source_item_id: UUID) -> SourceItem | None:
        """Return a source item by primary key."""
        return self.session.scalar(select(SourceItem).where(SourceItem.id == source_item_id))

    def get_by_dedupe_key(self, *, run_id: UUID, provider_name: str, dedupe_key: str) -> SourceItem | None:
        """Return a source item by run/provider/dedupe key."""
        statement = select(SourceItem).where(
            SourceItem.run_id == run_id,
            SourceItem.provider_name == provider_name,
            SourceItem.dedupe_key == dedupe_key,
        )
        return self.session.scalar(statement)

    def list_existing_dedupe_keys(self, *, run_id: UUID, provider_name: str, dedupe_keys: Sequence[str]) -> set[str]:
        """Return existing dedupe keys for a run/provider pair."""
        if not dedupe_keys:
            return set()
        statement = select(SourceItem.dedupe_key).where(
            SourceItem.run_id == run_id,
            SourceItem.provider_name == provider_name,
            SourceItem.dedupe_key.in_(list(dedupe_keys)),
        )
        return set(self.session.scalars(statement))

    def list_by_run(self, *, run_id: UUID, filters: SourceItemListFilters | None = None) -> PageResult[SourceItem]:
        """List source items for a research run."""
        filters = filters or SourceItemListFilters()
        statement = select(SourceItem).where(SourceItem.run_id == run_id)
        count_statement = select(func.count()).select_from(SourceItem).where(SourceItem.run_id == run_id)

        statement, count_statement = self._apply_filters(statement, count_statement, filters)
        statement = statement.order_by(SourceItem.fetched_at.desc(), SourceItem.created_at.desc()).limit(filters.limit).offset(filters.offset)

        items = list(self.session.scalars(statement))
        total = self.session.scalar(count_statement) or 0
        return PageResult(items=items, total=total, limit=filters.limit, offset=filters.offset)

    def update_status(self, *, source_item_id: UUID, status: SourceItemStatus) -> SourceItem | None:
        """Update the status of a single source item."""
        source_item = self.get_by_id(source_item_id)
        if source_item is None:
            return None
        source_item.status = status
        self.session.flush()
        return source_item

    def bulk_update_status(self, *, source_item_ids: Sequence[UUID], status: SourceItemStatus) -> int:
        """Update the status of many source items."""
        if not source_item_ids:
            return 0
        statement = update(SourceItem).where(SourceItem.id.in_(list(source_item_ids))).values(status=status)
        result = self.session.execute(statement)
        self.session.flush()
        return result.rowcount or 0

    @staticmethod
    def _apply_filters(
        statement: Select[tuple[SourceItem]],
        count_statement: Select[tuple[int]],
        filters: SourceItemListFilters,
    ) -> tuple[Select[tuple[SourceItem]], Select[tuple[int]]]:
        """Apply list filters to both source item statements."""
        if filters.provider_name is not None:
            statement = statement.where(SourceItem.provider_name == filters.provider_name)
            count_statement = count_statement.where(SourceItem.provider_name == filters.provider_name)
        if filters.status is not None:
            statement = statement.where(SourceItem.status == filters.status)
            count_statement = count_statement.where(SourceItem.status == filters.status)
        if filters.query_text:
            statement = statement.where(SourceItem.query_text == filters.query_text)
            count_statement = count_statement.where(SourceItem.query_text == filters.query_text)
        if filters.created_after is not None:
            statement = statement.where(SourceItem.created_at >= filters.created_after)
            count_statement = count_statement.where(SourceItem.created_at >= filters.created_after)
        if filters.created_before is not None:
            statement = statement.where(SourceItem.created_at <= filters.created_before)
            count_statement = count_statement.where(SourceItem.created_at <= filters.created_before)
        if filters.fetched_after is not None:
            statement = statement.where(SourceItem.fetched_at >= filters.fetched_after)
            count_statement = count_statement.where(SourceItem.fetched_at >= filters.fetched_after)
        if filters.fetched_before is not None:
            statement = statement.where(SourceItem.fetched_at <= filters.fetched_before)
            count_statement = count_statement.where(SourceItem.fetched_at <= filters.fetched_before)
        return statement, count_statement
