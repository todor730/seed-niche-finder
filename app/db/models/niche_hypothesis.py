"""Niche hypothesis ORM model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class NicheHypothesisStatus(StrEnum):
    """Supported niche hypothesis lifecycle states."""

    IDENTIFIED = "identified"
    SCORED = "scored"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"


class NicheHypothesis(Base):
    """Explainable niche candidate derived from one or more signal clusters."""

    __tablename__ = "niche_hypotheses"
    __table_args__ = (
        UniqueConstraint("run_id", "hypothesis_label", name="uq_niche_hypotheses_run_hypothesis_label"),
        CheckConstraint("evidence_count >= 0", name="evidence_count_non_negative"),
        CheckConstraint("source_count >= 0", name="source_count_non_negative"),
        CheckConstraint("overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)", name="overall_score_range"),
        CheckConstraint("rank_position IS NULL OR rank_position >= 1", name="rank_position_positive"),
        Index("ix_niche_hypotheses_run_id_status", "run_id", "status"),
        Index("ix_niche_hypotheses_run_id_overall_score", "run_id", "overall_score"),
        Index("ix_niche_hypotheses_run_id_rank_position", "run_id", "rank_position"),
        Index("ix_niche_hypotheses_primary_cluster_id_status", "primary_cluster_id", "status"),
        Index("ix_niche_hypotheses_run_id_created_at", "run_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    primary_cluster_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("signal_clusters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hypothesis_label: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    rank_position: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[NicheHypothesisStatus] = mapped_column(
        Enum(NicheHypothesisStatus, name="niche_hypothesis_status", native_enum=False, validate_strings=True),
        default=NicheHypothesisStatus.IDENTIFIED,
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

    research_run: Mapped["ResearchRun"] = relationship(back_populates="niche_hypotheses")
    primary_signal_cluster: Mapped["SignalCluster"] = relationship(back_populates="niche_hypotheses")
    niche_scores: Mapped[list["NicheScore"]] = relationship(
        back_populates="niche_hypothesis",
        cascade="all, delete-orphan",
    )
