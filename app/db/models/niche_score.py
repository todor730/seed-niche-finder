"""Niche score ORM model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class NicheScore(Base):
    """Explainable scoring component for a niche hypothesis."""

    __tablename__ = "niche_scores"
    __table_args__ = (
        UniqueConstraint("niche_hypothesis_id", "score_type", name="uq_niche_scores_hypothesis_id_score_type"),
        CheckConstraint("score_value >= 0 AND score_value <= 100", name="score_value_range"),
        CheckConstraint("weight >= 0 AND weight <= 1", name="weight_range"),
        CheckConstraint("weighted_score IS NULL OR (weighted_score >= 0 AND weighted_score <= 100)", name="weighted_score_range"),
        CheckConstraint("evidence_count >= 0", name="evidence_count_non_negative"),
        Index("ix_niche_scores_run_id_score_type", "run_id", "score_type"),
        Index("ix_niche_scores_run_id_score_value", "run_id", "score_value"),
        Index("ix_niche_scores_hypothesis_id_score_value", "niche_hypothesis_id", "score_value"),
        Index("ix_niche_scores_run_id_created_at", "run_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    niche_hypothesis_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("niche_hypotheses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    score_value: Mapped[float] = mapped_column(Float, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    weighted_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
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

    research_run: Mapped["ResearchRun"] = relationship(back_populates="niche_scores")
    niche_hypothesis: Mapped["NicheHypothesis"] = relationship(back_populates="niche_scores")
