"""Research-related API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.common import PaginatedSuccessEnvelope, ResearchRunStatus, SchemaModel, SuccessEnvelope


class ResearchConfig(SchemaModel):
    """Configurable parameters for a research run."""

    max_candidates: int = Field(default=100, ge=10, le=500)
    top_k: int = Field(default=25, ge=1, le=100)


class CreateResearchRunRequest(SchemaModel):
    """Request payload for starting a research run."""

    seed_niche: str = Field(min_length=2, max_length=120)
    config: ResearchConfig = Field(default_factory=ResearchConfig)

    @field_validator("seed_niche")
    @classmethod
    def normalize_seed_niche(cls, value: str) -> str:
        """Trim surrounding whitespace and reject empty post-trim values."""
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("seed_niche must contain at least 2 characters.")
        return normalized


class ResearchRunSummary(SchemaModel):
    """Aggregated counts for a research run."""

    keyword_count: int = Field(default=0, ge=0)
    accepted_keyword_count: int = Field(default=0, ge=0)
    opportunity_count: int = Field(default=0, ge=0)
    export_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> "ResearchRunSummary":
        """Ensure nested summary counts remain internally consistent."""
        if self.accepted_keyword_count > self.keyword_count:
            raise ValueError("accepted_keyword_count cannot exceed keyword_count.")
        return self


class DepthScoreBreakdown(SchemaModel):
    """Explainable factor scores behind the run depth score."""

    query_breadth: float = Field(ge=0.0, le=100.0)
    provider_coverage: float = Field(ge=0.0, le=100.0)
    evidence_volume: float = Field(ge=0.0, le=100.0)
    signal_depth: float = Field(ge=0.0, le=100.0)
    cluster_diversity: float = Field(ge=0.0, le=100.0)
    hypothesis_support: float = Field(ge=0.0, le=100.0)
    failure_adjustment: float = Field(ge=0.0, le=20.0)
    query_success_rate: float | None = Field(default=None, ge=0.0, le=1.0)


class DepthScoreSnapshot(SchemaModel):
    """Explainable run-level depth score and the persisted metrics behind it."""

    score: float = Field(ge=0.0, le=100.0)
    source_queries_count: int = Field(ge=0)
    successful_queries_count: int = Field(ge=0)
    attempted_queries_count: int = Field(ge=0)
    source_items_count: int = Field(ge=0)
    extracted_signals_count: int = Field(ge=0)
    signal_clusters_count: int = Field(ge=0)
    niche_hypotheses_count: int = Field(ge=0)
    provider_failures_count: int = Field(ge=0)
    evidence_provider_count: int = Field(ge=0)
    breakdown: DepthScoreBreakdown


class ResearchProgress(SchemaModel):
    """Progress snapshot for a running or completed research run."""

    status: ResearchRunStatus
    current_stage: str | None = Field(default=None, min_length=1, max_length=100)
    completed_steps: int = Field(default=0, ge=0)
    total_steps: int = Field(default=0, ge=0)
    percent_complete: float = Field(default=0.0, ge=0.0, le=100.0)
    message: str | None = Field(default=None, min_length=1, max_length=500)
    started_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_progress(self) -> "ResearchProgress":
        """Ensure progress values remain coherent."""
        if self.total_steps and self.completed_steps > self.total_steps:
            raise ValueError("completed_steps cannot exceed total_steps.")
        if self.status in {ResearchRunStatus.COMPLETED, ResearchRunStatus.COMPLETED_NO_EVIDENCE} and self.percent_complete < 100:
            raise ValueError("Completed runs must report percent_complete as 100.")
        return self


class ResearchRun(SchemaModel):
    """Core research run representation."""

    id: UUID
    user_id: UUID
    seed_niche: str = Field(min_length=2, max_length=120)
    status: ResearchRunStatus
    config: ResearchConfig
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    depth_score: DepthScoreSnapshot | None = None


class ResearchRunListItem(ResearchRun):
    """List-friendly research run payload."""

    summary: ResearchRunSummary = Field(default_factory=ResearchRunSummary)


class ResearchRunDetails(ResearchRun):
    """Detailed research run payload."""

    summary: ResearchRunSummary = Field(default_factory=ResearchRunSummary)
    progress: ResearchProgress


class CancelRunData(SchemaModel):
    """Payload returned after a cancel request is accepted."""

    run_id: UUID
    status: ResearchRunStatus


class CreateResearchRunResponse(SuccessEnvelope[ResearchRun]):
    """Success envelope for research run creation."""


class ResearchRunResponse(SuccessEnvelope[ResearchRunDetails]):
    """Success envelope for a single research run."""


class ResearchRunListResponse(PaginatedSuccessEnvelope[ResearchRunListItem]):
    """Paginated success envelope for research run listings."""


class ResearchProgressResponse(SuccessEnvelope[ResearchProgress]):
    """Success envelope for research progress polling."""


class CancelRunResponse(SuccessEnvelope[CancelRunData]):
    """Success envelope for run cancellation."""


RESEARCH_RUN_CREATE_EXAMPLE: dict[str, Any] = {
    "seed_niche": "stoic journaling for entrepreneurs",
    "config": {
        "max_candidates": 120,
        "top_k": 20,
    },
}

RESEARCH_RUN_DETAILS_EXAMPLE: dict[str, Any] = {
    "id": "6ab63a24-60a8-46c2-9f97-cf9d47bbfd52",
    "user_id": "7ce10f56-66e6-4452-96ba-8fcf56e65c6a",
    "seed_niche": "stoic journaling for entrepreneurs",
    "status": "running",
    "config": {
        "max_candidates": 120,
        "top_k": 20,
    },
    "created_at": "2026-04-08T10:00:00Z",
    "updated_at": "2026-04-08T10:05:00Z",
    "started_at": "2026-04-08T10:00:10Z",
    "completed_at": None,
    "error_message": None,
    "depth_score": {
        "score": 74.5,
        "source_queries_count": 8,
        "successful_queries_count": 7,
        "attempted_queries_count": 8,
        "source_items_count": 14,
        "extracted_signals_count": 41,
        "signal_clusters_count": 11,
        "niche_hypotheses_count": 5,
        "provider_failures_count": 1,
        "evidence_provider_count": 2,
        "breakdown": {
            "query_breadth": 96.2,
            "provider_coverage": 100.0,
            "evidence_volume": 100.0,
            "signal_depth": 89.1,
            "cluster_diversity": 92.3,
            "hypothesis_support": 77.4,
            "failure_adjustment": 6.9,
            "query_success_rate": 0.88,
        },
    },
    "summary": {
        "keyword_count": 48,
        "accepted_keyword_count": 12,
        "opportunity_count": 7,
        "export_count": 0,
    },
    "progress": {
        "status": "running",
        "current_stage": "opportunity_scoring",
        "completed_steps": 3,
        "total_steps": 5,
        "percent_complete": 60.0,
        "message": "Scoring shortlisted opportunities.",
        "started_at": "2026-04-08T10:00:10Z",
        "updated_at": "2026-04-08T10:05:00Z",
        "completed_at": None,
    },
}
