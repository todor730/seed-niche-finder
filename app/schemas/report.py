"""Schemas for decision-grade niche summary reports."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import SchemaModel
from app.schemas.research import DepthScoreSnapshot


class ReportWarningSeverity(StrEnum):
    """Severity levels for structured run/report warnings."""

    INFO = "info"
    WARNING = "warning"


class ReportWarning(SchemaModel):
    """Structured, evidence-backed warning emitted at report level."""

    code: str = Field(min_length=1)
    severity: ReportWarningSeverity
    message: str = Field(min_length=1)
    evidence: dict[str, Any] = Field(default_factory=dict)


class SummaryScoreBreakdown(SchemaModel):
    """Top-level score snapshot for one ranked niche summary."""

    discovery_score: float = Field(ge=0.0, le=100.0)
    opportunity_score: float = Field(ge=0.0, le=100.0)
    competition_score: float = Field(ge=0.0, le=100.0)
    confidence_score: float = Field(ge=0.0, le=100.0)
    final_score: float = Field(ge=0.0, le=100.0)


class SourceAgreementSnapshot(SchemaModel):
    """Evidence agreement snapshot used in the final summary."""

    source_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    supporting_providers: list[str] = Field(default_factory=list)
    agreement_score: float = Field(ge=0.0, le=100.0)
    repeated_appearance_score: float = Field(ge=0.0, le=100.0)
    single_source_dependence_penalty: float = Field(ge=0.0, le=100.0)

    @field_validator("supporting_providers")
    @classmethod
    def _normalize_providers(cls, value: list[str]) -> list[str]:
        providers = []
        seen: set[str] = set()
        for item in value:
            cleaned = " ".join(str(item).split()).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            providers.append(cleaned)
        return providers


class CompetitionDensitySnapshot(SchemaModel):
    """Crowding snapshot extracted from the competition density model."""

    density_score: float = Field(ge=0.0, le=100.0)
    relevant_item_count: int = Field(ge=0)
    incumbent_dominance: float = Field(ge=0.0, le=100.0)
    review_rating_footprint: float = Field(ge=0.0, le=100.0)
    recency_distribution: float = Field(ge=0.0, le=100.0)
    series_dominance: float = Field(ge=0.0, le=100.0)
    direct_match_density: float = Field(ge=0.0, le=100.0)
    evidence_coverage: float = Field(ge=0.0, le=1.0)
    fallback_used: bool = False
    limitations: list[str] = Field(default_factory=list)

    @field_validator("limitations")
    @classmethod
    def _normalize_limitations(cls, value: list[str]) -> list[str]:
        limitations = []
        seen: set[str] = set()
        for item in value:
            cleaned = " ".join(str(item).split()).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            limitations.append(cleaned)
        return limitations


class SignalSummary(SchemaModel):
    """Compact signal component view for summaries and exports."""

    signal_type: str = Field(min_length=1)
    label: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    source_count: int = Field(ge=0)
    item_count: int = Field(ge=0)
    avg_confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("aliases")
    @classmethod
    def _normalize_aliases(cls, value: list[str]) -> list[str]:
        aliases = []
        seen: set[str] = set()
        for item in value:
            cleaned = " ".join(str(item).split()).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            aliases.append(cleaned)
        return aliases


class NicheOpportunitySummary(SchemaModel):
    """Decision-grade summary for one ranked niche hypothesis."""

    hypothesis_id: UUID
    rank_position: int = Field(ge=1)
    niche_label: str = Field(min_length=1)
    audience: str | None = None
    promise: str | None = None
    key_signals: list[SignalSummary] = Field(default_factory=list)
    source_agreement: SourceAgreementSnapshot
    competition_density: CompetitionDensitySnapshot
    score_breakdown: SummaryScoreBreakdown
    why_it_may_work: list[str] = Field(default_factory=list)
    why_it_may_fail: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    next_validation_queries: list[str] = Field(default_factory=list)
    rationale_summary: str | None = None
    traceability: dict[str, Any] = Field(default_factory=dict)

    @field_validator("why_it_may_work", "why_it_may_fail", "risk_flags", "next_validation_queries")
    @classmethod
    def _normalize_string_lists(cls, value: list[str]) -> list[str]:
        normalized = []
        seen: set[str] = set()
        for item in value:
            cleaned = " ".join(str(item).split()).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized


class RunSummaryReport(SchemaModel):
    """Top-level report for the strongest ranked niche opportunities in a run."""

    run_id: UUID
    seed_niche: str = Field(min_length=1)
    generated_at: datetime
    depth_score: DepthScoreSnapshot
    warnings: list[ReportWarning] = Field(default_factory=list)
    top_niche_opportunities: list[NicheOpportunitySummary] = Field(default_factory=list)
