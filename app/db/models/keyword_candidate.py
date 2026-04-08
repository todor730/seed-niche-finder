"""Keyword candidate ORM model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class KeywordCandidateStatus(StrEnum):
    """Supported keyword candidate lifecycle states."""

    DISCOVERED = "discovered"
    REVIEWED = "reviewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class KeywordCandidate(Base):
    """Keyword candidate generated within a research run."""

    __tablename__ = "keyword_candidates"
    __table_args__ = (
        Index("ix_keyword_candidates_run_id_status", "run_id", "status"),
        Index("ix_keyword_candidates_run_id_created_at", "run_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    keyword_text: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[KeywordCandidateStatus] = mapped_column(
        Enum(KeywordCandidateStatus, name="keyword_candidate_status", native_enum=False, validate_strings=True),
        default=KeywordCandidateStatus.DISCOVERED,
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    research_run: Mapped["ResearchRun"] = relationship(back_populates="keyword_candidates")
    keyword_metrics: Mapped[list["KeywordMetrics"]] = relationship(
        back_populates="keyword_candidate",
        cascade="all, delete-orphan",
    )
    trend_metrics: Mapped[list["TrendMetrics"]] = relationship(
        back_populates="keyword_candidate",
        cascade="all, delete-orphan",
    )
    competitors: Mapped[list["Competitor"]] = relationship(
        back_populates="keyword_candidate",
        cascade="all, delete-orphan",
    )
    opportunities: Mapped[list["Opportunity"]] = relationship(
        back_populates="keyword_candidate",
        cascade="all, delete-orphan",
    )
