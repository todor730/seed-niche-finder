"""Shared API enums and envelope schemas."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class SchemaModel(BaseModel):
    """Base schema configuration for strict API validation."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=False,
        use_enum_values=True,
    )


class ResearchRunStatus(StrEnum):
    """Research run states exposed through the API."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CandidateStatus(StrEnum):
    """Keyword candidate states exposed through the API."""

    DISCOVERED = "discovered"
    REVIEWED = "reviewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ExportStatus(StrEnum):
    """Export lifecycle states exposed through the API."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExportFormat(StrEnum):
    """Supported export serialization formats."""

    CSV = "csv"
    JSON = "json"
    XLSX = "xlsx"


class ExportScope(StrEnum):
    """Supported export scope values."""

    KEYWORDS = "keywords"
    OPPORTUNITIES = "opportunities"
    FULL_RUN = "full_run"


class TrendDirection(StrEnum):
    """Supported trend direction labels."""

    UP = "up"
    FLAT = "flat"
    DOWN = "down"


class ErrorObject(SchemaModel):
    """Standard API error object."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(SchemaModel):
    """Standard API error envelope."""

    data: None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    error: ErrorObject


class PaginationMeta(SchemaModel):
    """Shared offset-pagination metadata."""

    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class SuccessEnvelope(SchemaModel, Generic[T]):
    """Generic success response envelope."""

    data: T
    meta: dict[str, Any] = Field(default_factory=dict)
    error: None = None


class PaginatedSuccessEnvelope(SchemaModel, Generic[T]):
    """Generic paginated success response envelope."""

    data: list[T]
    meta: PaginationMeta
    error: None = None
