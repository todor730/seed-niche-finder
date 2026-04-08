"""Source item ORM model for raw provider evidence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class SourceItemStatus(StrEnum):
    """Supported source item lifecycle states."""

    FETCHED = "fetched"
    EXTRACTED = "extracted"
    CLUSTERED = "clustered"
    DISCARDED = "discarded"


class SourceItem(Base):
    """Raw provider evidence captured for a research run."""

    __tablename__ = "source_items"
    __table_args__ = (
        UniqueConstraint("run_id", "provider_name", "dedupe_key", name="uq_source_items_run_provider_dedupe_key"),
        CheckConstraint("average_rating IS NULL OR (average_rating >= 0 AND average_rating <= 5)", name="average_rating_range"),
        CheckConstraint("rating_count IS NULL OR rating_count >= 0", name="rating_count_non_negative"),
        CheckConstraint("review_count IS NULL OR review_count >= 0", name="review_count_non_negative"),
        Index("ix_source_items_run_id_provider_name", "run_id", "provider_name"),
        Index("ix_source_items_run_id_status", "run_id", "status"),
        Index("ix_source_items_run_id_fetched_at", "run_id", "fetched_at"),
        Index("ix_source_items_run_id_query_text", "run_id", "query_text"),
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
    provider_item_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(512), nullable=True)
    authors_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    categories_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    description_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    published_date_raw: Mapped[str | None] = mapped_column(String(50), nullable=True)
    average_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_payload_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[SourceItemStatus] = mapped_column(
        Enum(SourceItemStatus, name="source_item_status", native_enum=False, validate_strings=True),
        default=SourceItemStatus.FETCHED,
        nullable=False,
        index=True,
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
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

    research_run: Mapped["ResearchRun"] = relationship(back_populates="source_items")
    extracted_signals: Mapped[list["ExtractedSignal"]] = relationship(
        back_populates="source_item",
        cascade="all, delete-orphan",
    )
