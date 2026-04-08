"""Opportunity ORM model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class OpportunityStatus(StrEnum):
    """Supported opportunity lifecycle states."""

    IDENTIFIED = "identified"
    RANKED = "ranked"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"


class Opportunity(Base):
    """Ranked opportunity derived from a keyword candidate."""

    __tablename__ = "opportunities"
    __table_args__ = (
        Index("ix_opportunities_run_id_status", "run_id", "status"),
        Index("ix_opportunities_keyword_candidate_id_status", "keyword_candidate_id", "status"),
        Index("ix_opportunities_run_id_created_at", "run_id", "created_at"),
        Index("ix_opportunities_keyword_candidate_id_created_at", "keyword_candidate_id", "created_at"),
        Index("ix_opportunities_run_id_opportunity_score", "run_id", "opportunity_score"),
        Index("ix_opportunities_keyword_candidate_id_opportunity_score", "keyword_candidate_id", "opportunity_score"),
        Index("ix_opportunities_status_opportunity_score", "status", "opportunity_score"),
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
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[OpportunityStatus] = mapped_column(
        Enum(OpportunityStatus, name="opportunity_status", native_enum=False, validate_strings=True),
        default=OpportunityStatus.IDENTIFIED,
        nullable=False,
        index=True,
    )
    demand_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    trend_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    intent_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hook_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    monetization_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    competition_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    opportunity_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    rationale_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
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

    research_run: Mapped["ResearchRun"] = relationship(back_populates="opportunities")
    keyword_candidate: Mapped["KeywordCandidate"] = relationship(back_populates="opportunities")

