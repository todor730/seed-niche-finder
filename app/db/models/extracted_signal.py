"""Extracted signal ORM model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class ExtractedSignal(Base):
    """Normalized signal extracted from raw provider evidence."""

    __tablename__ = "extracted_signals"
    __table_args__ = (
        UniqueConstraint(
            "source_item_id",
            "signal_type",
            "normalized_value",
            "extraction_method",
            name="uq_extracted_signals_source_item_type_normalized_method",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        Index("ix_extracted_signals_run_id_signal_type", "run_id", "signal_type"),
        Index("ix_extracted_signals_run_id_normalized_value", "run_id", "normalized_value"),
        Index("ix_extracted_signals_run_id_confidence", "run_id", "confidence"),
        Index("ix_extracted_signals_cluster_id_confidence", "cluster_id", "confidence"),
        Index("ix_extracted_signals_run_id_created_at", "run_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_item_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("source_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cluster_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("signal_clusters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    signal_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    signal_value: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_span: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    research_run: Mapped["ResearchRun"] = relationship(back_populates="extracted_signals")
    source_item: Mapped["SourceItem"] = relationship(back_populates="extracted_signals")
    signal_cluster: Mapped["SignalCluster | None"] = relationship(back_populates="extracted_signals")
