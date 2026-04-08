"""Source query ORM model for persisted provider query traceability."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class SourceQuery(Base):
    """One successful provider query executed for a research run."""

    __tablename__ = "source_queries"
    __table_args__ = (
        UniqueConstraint("run_id", "provider_name", "query_text", "query_kind", name="uq_source_queries_run_provider_text_kind"),
        Index("ix_source_queries_run_id_provider_name", "run_id", "provider_name"),
        Index("ix_source_queries_run_id_query_kind", "run_id", "query_kind"),
        Index("ix_source_queries_run_id_created_at", "run_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    query_text: Mapped[str] = mapped_column(String(255), nullable=False)
    query_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    tags_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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

    research_run: Mapped["ResearchRun"] = relationship(back_populates="source_queries")
    source_item_links: Mapped[list["SourceItemQueryLink"]] = relationship(
        back_populates="source_query",
        cascade="all, delete-orphan",
    )

