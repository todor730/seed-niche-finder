"""Pydantic schemas for the evidence persistence layer."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field

from app.schemas.common import SchemaModel


class EvidenceSchemaModel(SchemaModel):
    """Strict schema base with ORM attribute support for persistence reads."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=False,
        use_enum_values=True,
        from_attributes=True,
    )


class SourceItemStatus(StrEnum):
    """Source item lifecycle states."""

    FETCHED = "fetched"
    EXTRACTED = "extracted"
    CLUSTERED = "clustered"
    DISCARDED = "discarded"


class NicheHypothesisStatus(StrEnum):
    """Niche hypothesis lifecycle states."""

    IDENTIFIED = "identified"
    SCORED = "scored"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"


class SourceItemCreate(EvidenceSchemaModel):
    """Write schema for persisting raw provider evidence."""

    run_id: UUID
    provider_name: str = Field(min_length=1, max_length=100)
    query_text: str = Field(min_length=1, max_length=255)
    query_kind: str | None = Field(default=None, max_length=50)
    provider_item_id: str | None = Field(default=None, max_length=255)
    dedupe_key: str = Field(min_length=1, max_length=255)
    source_url: str | None = Field(default=None, max_length=1024)
    title: str = Field(min_length=1, max_length=512)
    subtitle: str | None = Field(default=None, max_length=512)
    authors_json: list[str] = Field(default_factory=list)
    categories_json: list[str] = Field(default_factory=list)
    description_text: str | None = None
    content_text: str = ""
    published_date_raw: str | None = Field(default=None, max_length=50)
    average_rating: float | None = Field(default=None, ge=0.0, le=5.0)
    rating_count: int | None = Field(default=None, ge=0)
    review_count: int | None = Field(default=None, ge=0)
    raw_payload_json: dict[str, Any] = Field(default_factory=dict)
    status: SourceItemStatus = SourceItemStatus.FETCHED
    fetched_at: datetime | None = None


class SourceItemStatusUpdate(EvidenceSchemaModel):
    """Write schema for updating source item status."""

    status: SourceItemStatus


class SourceItemRead(EvidenceSchemaModel):
    """Read schema for raw provider evidence."""

    id: UUID
    run_id: UUID
    provider_name: str
    query_text: str
    query_kind: str | None = None
    provider_item_id: str | None = None
    dedupe_key: str
    source_url: str | None = None
    title: str
    subtitle: str | None = None
    authors_json: list[str]
    categories_json: list[str]
    description_text: str | None = None
    content_text: str
    published_date_raw: str | None = None
    average_rating: float | None = None
    rating_count: int | None = None
    review_count: int | None = None
    raw_payload_json: dict[str, Any]
    status: SourceItemStatus
    fetched_at: datetime
    created_at: datetime
    updated_at: datetime


class SourceQueryCreate(EvidenceSchemaModel):
    """Write schema for persisted provider queries."""

    run_id: UUID
    provider_name: str = Field(min_length=1, max_length=100)
    query_text: str = Field(min_length=1, max_length=255)
    query_kind: str | None = Field(default=None, max_length=50)
    priority: int = Field(default=100)
    tags_json: list[str] = Field(default_factory=list)
    item_count: int = Field(default=0, ge=0)


class SourceQueryRead(EvidenceSchemaModel):
    """Read schema for persisted provider queries."""

    id: UUID
    run_id: UUID
    provider_name: str
    query_text: str
    query_kind: str | None = None
    priority: int
    tags_json: list[str]
    item_count: int
    created_at: datetime
    updated_at: datetime


class SourceItemQueryLinkCreate(EvidenceSchemaModel):
    """Write schema for source item/query traceability links."""

    source_query_id: UUID
    source_item_id: UUID


class SourceItemQueryLinkRead(EvidenceSchemaModel):
    """Read schema for source item/query traceability links."""

    id: UUID
    source_query_id: UUID
    source_item_id: UUID
    created_at: datetime
    updated_at: datetime


class ProviderFailureCreate(EvidenceSchemaModel):
    """Write schema for persisted provider failures."""

    run_id: UUID
    provider_name: str = Field(min_length=1, max_length=100)
    query_text: str = Field(min_length=1, max_length=255)
    query_kind: str | None = Field(default=None, max_length=50)
    error_type: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1)
    retryable: bool = False
    occurred_at: datetime


class ProviderFailureRead(EvidenceSchemaModel):
    """Read schema for persisted provider failures."""

    id: UUID
    run_id: UUID
    provider_name: str
    query_text: str
    query_kind: str | None = None
    error_type: str
    message: str
    retryable: bool
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime


class ExtractedSignalCreate(EvidenceSchemaModel):
    """Write schema for extracted signals."""

    run_id: UUID
    source_item_id: UUID
    cluster_id: UUID | None = None
    signal_type: str = Field(min_length=1, max_length=100)
    signal_value: str = Field(min_length=1, max_length=512)
    normalized_value: str = Field(min_length=1, max_length=255)
    confidence: float = Field(ge=0.0, le=1.0)
    extraction_method: str = Field(min_length=1, max_length=100)
    evidence_span: str | None = None


class ExtractedSignalClusterUpdate(EvidenceSchemaModel):
    """Write schema for assigning a cluster to extracted signals."""

    cluster_id: UUID | None = None


class ExtractedSignalRead(EvidenceSchemaModel):
    """Read schema for extracted signals."""

    id: UUID
    run_id: UUID
    source_item_id: UUID
    cluster_id: UUID | None = None
    signal_type: str
    signal_value: str
    normalized_value: str
    confidence: float
    extraction_method: str
    evidence_span: str | None = None
    created_at: datetime
    updated_at: datetime


class SignalClusterCreate(EvidenceSchemaModel):
    """Write schema for signal clusters."""

    run_id: UUID
    signal_type: str = Field(min_length=1, max_length=100)
    canonical_label: str = Field(min_length=1, max_length=255)
    aliases_json: list[str] = Field(default_factory=list)
    source_count: int = Field(default=0, ge=0)
    item_count: int = Field(default=0, ge=0)
    avg_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    saturation_score: float = Field(default=0.0, ge=0.0, le=100.0)
    novelty_score: float = Field(default=0.0, ge=0.0, le=100.0)


class SignalClusterUpdate(EvidenceSchemaModel):
    """Write schema for updating cluster aggregate metrics."""

    aliases_json: list[str] | None = None
    source_count: int | None = Field(default=None, ge=0)
    item_count: int | None = Field(default=None, ge=0)
    avg_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    saturation_score: float | None = Field(default=None, ge=0.0, le=100.0)
    novelty_score: float | None = Field(default=None, ge=0.0, le=100.0)


class SignalClusterRead(EvidenceSchemaModel):
    """Read schema for signal clusters."""

    id: UUID
    run_id: UUID
    signal_type: str
    canonical_label: str
    aliases_json: list[str]
    source_count: int
    item_count: int
    avg_confidence: float
    saturation_score: float
    novelty_score: float
    created_at: datetime
    updated_at: datetime


class NicheHypothesisCreate(EvidenceSchemaModel):
    """Write schema for explainable niche hypotheses."""

    run_id: UUID
    primary_cluster_id: UUID
    hypothesis_label: str = Field(min_length=1, max_length=255)
    summary: str | None = None
    rationale_json: dict[str, Any] = Field(default_factory=dict)
    evidence_count: int = Field(default=0, ge=0)
    source_count: int = Field(default=0, ge=0)
    overall_score: float | None = Field(default=None, ge=0.0, le=100.0)
    rank_position: int | None = Field(default=None, ge=1)
    status: NicheHypothesisStatus = NicheHypothesisStatus.IDENTIFIED


class NicheHypothesisStatusUpdate(EvidenceSchemaModel):
    """Write schema for updating niche hypothesis status."""

    status: NicheHypothesisStatus


class NicheHypothesisRankingUpdate(EvidenceSchemaModel):
    """Write schema for updating hypothesis ranking fields."""

    summary: str | None = None
    rationale_json: dict[str, Any] | None = None
    evidence_count: int | None = Field(default=None, ge=0)
    source_count: int | None = Field(default=None, ge=0)
    overall_score: float | None = Field(default=None, ge=0.0, le=100.0)
    rank_position: int | None = Field(default=None, ge=1)


class NicheHypothesisRead(EvidenceSchemaModel):
    """Read schema for explainable niche hypotheses."""

    id: UUID
    run_id: UUID
    primary_cluster_id: UUID
    hypothesis_label: str
    summary: str | None = None
    rationale_json: dict[str, Any]
    evidence_count: int
    source_count: int
    overall_score: float | None = None
    rank_position: int | None = None
    status: NicheHypothesisStatus
    created_at: datetime
    updated_at: datetime


class NicheScoreCreate(EvidenceSchemaModel):
    """Write schema for niche score components."""

    run_id: UUID
    niche_hypothesis_id: UUID
    score_type: str = Field(min_length=1, max_length=100)
    score_value: float = Field(ge=0.0, le=100.0)
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    weighted_score: float | None = Field(default=None, ge=0.0, le=100.0)
    evidence_count: int = Field(default=0, ge=0)
    rationale: str | None = None
    evidence_json: dict[str, Any] = Field(default_factory=dict)


class NicheScoreUpdate(EvidenceSchemaModel):
    """Write schema for updating niche score values."""

    score_value: float | None = Field(default=None, ge=0.0, le=100.0)
    weight: float | None = Field(default=None, ge=0.0, le=1.0)
    weighted_score: float | None = Field(default=None, ge=0.0, le=100.0)
    evidence_count: int | None = Field(default=None, ge=0)
    rationale: str | None = None
    evidence_json: dict[str, Any] | None = None


class NicheScoreRead(EvidenceSchemaModel):
    """Read schema for niche score components."""

    id: UUID
    run_id: UUID
    niche_hypothesis_id: UUID
    score_type: str
    score_value: float
    weight: float
    weighted_score: float | None = None
    evidence_count: int
    rationale: str | None = None
    evidence_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
