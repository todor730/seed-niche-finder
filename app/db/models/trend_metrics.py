"""Trend metrics ORM model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class TrendMetricsStatus(StrEnum):
    """Supported trend metrics collection states."""

    PENDING = "pending"
    COLLECTED = "collected"
    FAILED = "failed"


class TrendMetrics(Base):
    """Trend and momentum metrics for a keyword candidate."""

    __tablename__ = "trend_metrics"
    __table_args__ = (
        Index("ix_trend_metrics_run_id_status", "run_id", "status"),
        Index("ix_trend_metrics_keyword_candidate_id_status", "keyword_candidate_id", "status"),
        Index("ix_trend_metrics_run_id_created_at", "run_id", "created_at"),
        Index("ix_trend_metrics_keyword_candidate_id_created_at", "keyword_candidate_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    keyword_candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("keyword_candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[TrendMetricsStatus] = mapped_column(
        Enum(TrendMetricsStatus, name="trend_metrics_status", native_enum=False, validate_strings=True),
        default=TrendMetricsStatus.PENDING,
        nullable=False,
        index=True,
    )
    trend_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend_change_30d: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend_change_90d: Mapped[float | None] = mapped_column(Float, nullable=True)
    seasonality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    research_run: Mapped["ResearchRun"] = relationship(back_populates="trend_metrics")
    keyword_candidate: Mapped["KeywordCandidate"] = relationship(back_populates="trend_metrics")

