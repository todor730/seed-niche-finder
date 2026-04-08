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
        if self.status == ResearchRunStatus.COMPLETED and self.percent_complete < 100:
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
