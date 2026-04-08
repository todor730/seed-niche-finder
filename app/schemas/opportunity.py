"""Opportunity-related API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.common import PaginatedSuccessEnvelope, SchemaModel, SuccessEnvelope


class ScoreBreakdown(SchemaModel):
    """Normalized opportunity scoring breakdown."""

    demand_score: float = Field(ge=0.0, le=100.0)
    trend_score: float = Field(ge=0.0, le=100.0)
    intent_score: float = Field(ge=0.0, le=100.0)
    hook_score: float = Field(ge=0.0, le=100.0)
    monetization_score: float = Field(ge=0.0, le=100.0)
    competition_score: float = Field(ge=0.0, le=100.0)
    opportunity_score: float = Field(ge=0.0, le=100.0)


class OpportunityRationale(SchemaModel):
    """Structured rationale behind an opportunity recommendation."""

    rationale_summary: str = Field(min_length=1, max_length=1000)
    positives: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    landing_page_angles: list[str] = Field(default_factory=list)

    @field_validator("positives", "risks", "landing_page_angles")
    @classmethod
    def normalize_string_lists(cls, values: list[str]) -> list[str]:
        """Trim list entries and reject blank items."""
        normalized_values = [value.strip() for value in values if value.strip()]
        return normalized_values


class MarketSnapshot(SchemaModel):
    """Optional market context shown alongside an opportunity."""

    search_volume: int | None = Field(default=None, ge=0)
    average_rating: float | None = Field(default=None, ge=0.0, le=5.0)
    review_count: int | None = Field(default=None, ge=0)
    competitor_count: int | None = Field(default=None, ge=0)
    seasonality_score: float | None = Field(default=None, ge=0.0, le=100.0)
    cpc_usd: float | None = Field(default=None, ge=0.0)


class OpportunityListItem(SchemaModel):
    """List payload for a ranked opportunity."""

    id: UUID
    run_id: UUID
    keyword_id: UUID
    keyword_text: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    summary: str | None = Field(default=None, max_length=5000)
    recommended: bool = False
    score_breakdown: ScoreBreakdown
    rationale_summary: str = Field(min_length=1, max_length=1000)
    positives: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    landing_page_angles: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("positives", "risks", "landing_page_angles")
    @classmethod
    def normalize_summary_lists(cls, values: list[str]) -> list[str]:
        """Trim and remove blank values from list response fields."""
        return [value.strip() for value in values if value.strip()]


class OpportunityDetails(OpportunityListItem):
    """Detailed opportunity payload."""

    rationale: OpportunityRationale
    market_snapshot: MarketSnapshot | None = None

    @model_validator(mode="after")
    def validate_rationale_summary_alignment(self) -> "OpportunityDetails":
        """Keep top-level and nested rationale summaries aligned."""
        if self.rationale.rationale_summary != self.rationale_summary:
            raise ValueError("rationale_summary must match rationale.rationale_summary.")
        return self


class OpportunityListResponse(PaginatedSuccessEnvelope[OpportunityListItem]):
    """Paginated success envelope for opportunity listings."""


class OpportunityResponse(SuccessEnvelope[OpportunityDetails]):
    """Success envelope for a single opportunity."""


OPPORTUNITY_LIST_ITEM_EXAMPLE: dict[str, Any] = {
    "id": "5f8f39fd-9574-4acd-8af3-7d45ae1e74e6",
    "run_id": "6ab63a24-60a8-46c2-9f97-cf9d47bbfd52",
    "keyword_id": "f40f0460-5ce4-4a21-9ef3-c8b3c89bfa30",
    "keyword_text": "stoic journal for entrepreneurs",
    "title": "Founders Stoic Reflection Journal",
    "summary": "A practical stoic journaling concept tailored to startup founders and indie builders.",
    "recommended": True,
    "score_breakdown": {
        "demand_score": 78.0,
        "trend_score": 74.5,
        "intent_score": 82.0,
        "hook_score": 88.0,
        "monetization_score": 76.0,
        "competition_score": 36.0,
        "opportunity_score": 81.2,
    },
    "rationale_summary": "Strong audience-market fit with a clear positioning hook and manageable competition.",
    "positives": [
        "Clear audience identity for founders and indie builders.",
        "High-intent search demand around journaling and stoicism.",
    ],
    "risks": [
        "General stoicism space is crowded if messaging is too broad.",
        "Requires a differentiated angle to avoid generic productivity framing.",
    ],
    "landing_page_angles": [
        "Build resilience in 10 minutes a day.",
        "A founder-focused reflection habit for better decisions.",
    ],
    "created_at": "2026-04-08T10:10:00Z",
    "updated_at": "2026-04-08T10:12:00Z",
}

OPPORTUNITY_DETAILS_EXAMPLE: dict[str, Any] = {
    **OPPORTUNITY_LIST_ITEM_EXAMPLE,
    "rationale": {
        "rationale_summary": "Strong audience-market fit with a clear positioning hook and manageable competition.",
        "positives": [
            "Clear audience identity for founders and indie builders.",
            "High-intent search demand around journaling and stoicism.",
        ],
        "risks": [
            "General stoicism space is crowded if messaging is too broad.",
            "Requires a differentiated angle to avoid generic productivity framing.",
        ],
        "landing_page_angles": [
            "Build resilience in 10 minutes a day.",
            "A founder-focused reflection habit for better decisions.",
        ],
    },
    "market_snapshot": {
        "search_volume": 4400,
        "average_rating": 4.6,
        "review_count": 318,
        "competitor_count": 11,
        "seasonality_score": 42.0,
        "cpc_usd": 1.75,
    },
}
