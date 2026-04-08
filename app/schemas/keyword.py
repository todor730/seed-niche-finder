"""Keyword-related API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import CandidateStatus, PaginatedSuccessEnvelope, SchemaModel, SuccessEnvelope, TrendDirection


class KeywordMetrics(SchemaModel):
    """Combined keyword metrics payload for keyword list and detail views."""

    provider_name: str | None = Field(default=None, min_length=1, max_length=100)
    search_volume: int | None = Field(default=None, ge=0)
    cpc_usd: float | None = Field(default=None, ge=0)
    demand_score: float | None = Field(default=None, ge=0.0, le=100.0)
    trend_score: float | None = Field(default=None, ge=0.0, le=100.0)
    competition_score: float | None = Field(default=None, ge=0.0, le=100.0)
    opportunity_score: float | None = Field(default=None, ge=0.0, le=100.0)
    trend_change_30d: float | None = None
    trend_change_90d: float | None = None
    seasonality_score: float | None = Field(default=None, ge=0.0, le=100.0)
    trend_direction: TrendDirection | None = None
    collected_at: datetime | None = None

    @field_validator("provider_name")
    @classmethod
    def normalize_provider_name(cls, value: str | None) -> str | None:
        """Trim provider names while preserving optionality."""
        return value.strip() if value is not None else None


class KeywordListItem(SchemaModel):
    """List payload for a keyword candidate within a research run."""

    id: UUID
    run_id: UUID
    keyword_text: str = Field(min_length=1, max_length=255)
    status: CandidateStatus
    metrics: KeywordMetrics = Field(default_factory=KeywordMetrics)
    opportunity_count: int = Field(default=0, ge=0)
    competitor_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime


class KeywordDetails(KeywordListItem):
    """Detailed keyword candidate payload."""

    notes: str | None = Field(default=None, max_length=5000)


class KeywordListResponse(PaginatedSuccessEnvelope[KeywordListItem]):
    """Paginated success envelope for run keyword listings."""


class KeywordResponse(SuccessEnvelope[KeywordDetails]):
    """Success envelope for a single keyword record."""


KEYWORD_LIST_ITEM_EXAMPLE: dict[str, Any] = {
    "id": "f40f0460-5ce4-4a21-9ef3-c8b3c89bfa30",
    "run_id": "6ab63a24-60a8-46c2-9f97-cf9d47bbfd52",
    "keyword_text": "stoic journal for entrepreneurs",
    "status": "accepted",
    "metrics": {
        "provider_name": "google-trends",
        "search_volume": 4400,
        "cpc_usd": 1.75,
        "demand_score": 78.0,
        "trend_score": 74.5,
        "competition_score": 36.0,
        "opportunity_score": 81.2,
        "trend_change_30d": 12.4,
        "trend_change_90d": 18.7,
        "seasonality_score": 42.0,
        "trend_direction": "up",
        "collected_at": "2026-04-08T10:07:00Z",
    },
    "opportunity_count": 3,
    "competitor_count": 11,
    "created_at": "2026-04-08T10:03:00Z",
    "updated_at": "2026-04-08T10:07:00Z",
}

KEYWORD_DETAILS_EXAMPLE: dict[str, Any] = {
    **KEYWORD_LIST_ITEM_EXAMPLE,
    "notes": "High-intent niche with clear creator audience and healthy search momentum.",
}
