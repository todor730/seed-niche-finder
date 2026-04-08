"""Competitor ORM model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class CompetitorStatus(StrEnum):
    """Supported competitor analysis states."""

    DISCOVERED = "discovered"
    ANALYZED = "analyzed"
    EXCLUDED = "excluded"


class Competitor(Base):
    """Competitor record associated with a keyword candidate."""

    __tablename__ = "competitors"
    __table_args__ = (
        Index("ix_competitors_run_id_status", "run_id", "status"),
        Index("ix_competitors_keyword_candidate_id_status", "keyword_candidate_id", "status"),
        Index("ix_competitors_run_id_created_at", "run_id", "created_at"),
        Index("ix_competitors_keyword_candidate_id_created_at", "keyword_candidate_id", "created_at"),
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
    competitor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    marketplace: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[CompetitorStatus] = mapped_column(
        Enum(CompetitorStatus, name="competitor_status", native_enum=False, validate_strings=True),
        default=CompetitorStatus.DISCOVERED,
        nullable=False,
        index=True,
    )
    average_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
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

    research_run: Mapped["ResearchRun"] = relationship(back_populates="competitors")
    keyword_candidate: Mapped["KeywordCandidate"] = relationship(back_populates="competitors")

