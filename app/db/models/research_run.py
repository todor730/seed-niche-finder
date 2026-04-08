"""Research run ORM model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class ResearchRunStatus(StrEnum):
    """Supported research run lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchRun(Base):
    """Central orchestration entity for an ebook niche research workflow."""

    __tablename__ = "research_runs"
    __table_args__ = (
        Index("ix_research_runs_user_id_status", "user_id", "status"),
        Index("ix_research_runs_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ResearchRunStatus] = mapped_column(
        Enum(ResearchRunStatus, name="research_run_status", native_enum=False, validate_strings=True),
        default=ResearchRunStatus.PENDING,
        nullable=False,
        index=True,
    )
    seed_niche: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    config_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    user: Mapped["User"] = relationship(back_populates="research_runs")
    keyword_candidates: Mapped[list["KeywordCandidate"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    keyword_metrics: Mapped[list["KeywordMetrics"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    trend_metrics: Mapped[list["TrendMetrics"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    competitors: Mapped[list["Competitor"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    opportunities: Mapped[list["Opportunity"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    exports: Mapped[list["Export"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    source_items: Mapped[list["SourceItem"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    extracted_signals: Mapped[list["ExtractedSignal"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    signal_clusters: Mapped[list["SignalCluster"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    niche_hypotheses: Mapped[list["NicheHypothesis"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    niche_scores: Mapped[list["NicheScore"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
