"""Repository queries for source item/query traceability links."""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import SourceItemQueryLink
from app.db.repositories import PageResult
from app.schemas.evidence import SourceItemQueryLinkCreate


class SourceItemQueryLinkRepository:
    """Thin persistence access for source item/query link entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, payload: SourceItemQueryLinkCreate) -> SourceItemQueryLink:
        """Create and flush one source item/query link."""
        link = SourceItemQueryLink(**payload.model_dump())
        self.session.add(link)
        self.session.flush()
        return link

    def create_if_missing(self, payload: SourceItemQueryLinkCreate) -> SourceItemQueryLink:
        """Create a link if it does not already exist."""
        existing = self.session.scalar(
            select(SourceItemQueryLink).where(
                SourceItemQueryLink.source_query_id == payload.source_query_id,
                SourceItemQueryLink.source_item_id == payload.source_item_id,
            )
        )
        if existing is not None:
            return existing
        return self.create(payload)

    def bulk_create_if_missing(self, payloads: Sequence[SourceItemQueryLinkCreate]) -> list[SourceItemQueryLink]:
        """Create multiple links while preserving uniqueness."""
        links: list[SourceItemQueryLink] = []
        for payload in payloads:
            links.append(self.create_if_missing(payload))
        return links

    def list_by_source_item(self, *, source_item_id: UUID, limit: int = 100, offset: int = 0) -> PageResult[SourceItemQueryLink]:
        """List query links for a given source item."""
        statement: Select[tuple[SourceItemQueryLink]] = (
            select(SourceItemQueryLink)
            .where(SourceItemQueryLink.source_item_id == source_item_id)
            .order_by(SourceItemQueryLink.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        count_statement = select(func.count()).select_from(SourceItemQueryLink).where(
            SourceItemQueryLink.source_item_id == source_item_id
        )
        items = list(self.session.scalars(statement))
        total = self.session.scalar(count_statement) or 0
        return PageResult(items=items, total=total, limit=limit, offset=offset)
