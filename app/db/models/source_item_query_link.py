"""Association ORM model linking persisted source items to provider queries."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class SourceItemQueryLink(Base):
    """Many-to-many traceability link between source items and source queries."""

    __tablename__ = "source_item_query_links"
    __table_args__ = (
        UniqueConstraint("source_query_id", "source_item_id", name="uq_source_item_query_links_query_item"),
        Index("ix_source_item_query_links_source_item_id_created_at", "source_item_id", "created_at"),
        Index("ix_source_item_query_links_source_query_id_created_at", "source_query_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source_query_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("source_queries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_item_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("source_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    source_query: Mapped["SourceQuery"] = relationship(back_populates="source_item_links")
    source_item: Mapped["SourceItem"] = relationship(back_populates="source_query_links")
