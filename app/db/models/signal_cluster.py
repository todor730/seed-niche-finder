"""Signal cluster ORM model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class SignalCluster(Base):
    """Canonical cluster of extracted signals for a research run."""

    __tablename__ = "signal_clusters"
    __table_args__ = (
        UniqueConstraint("run_id", "signal_type", "canonical_label", name="uq_signal_clusters_run_type_canonical_label"),
        CheckConstraint("source_count >= 0", name="source_count_non_negative"),
        CheckConstraint("item_count >= 0", name="item_count_non_negative"),
        CheckConstraint("avg_confidence >= 0 AND avg_confidence <= 1", name="avg_confidence_range"),
        CheckConstraint("saturation_score >= 0 AND saturation_score <= 100", name="saturation_score_range"),
        CheckConstraint("novelty_score >= 0 AND novelty_score <= 100", name="novelty_score_range"),
        Index("ix_signal_clusters_run_id_signal_type", "run_id", "signal_type"),
        Index("ix_signal_clusters_run_id_source_count", "run_id", "source_count"),
        Index("ix_signal_clusters_run_id_avg_confidence", "run_id", "avg_confidence"),
        Index("ix_signal_clusters_run_id_novelty_score", "run_id", "novelty_score"),
        Index("ix_signal_clusters_run_id_created_at", "run_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    signal_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    canonical_label: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    saturation_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    novelty_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
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

    research_run: Mapped["ResearchRun"] = relationship(back_populates="signal_clusters")
    extracted_signals: Mapped[list["ExtractedSignal"]] = relationship(back_populates="signal_cluster")
    niche_hypotheses: Mapped[list["NicheHypothesis"]] = relationship(back_populates="primary_signal_cluster")
