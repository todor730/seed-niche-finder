"""Export-related API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import ExportFormat, ExportScope, ExportStatus, PaginatedSuccessEnvelope, SchemaModel, SuccessEnvelope


class CreateExportRequest(SchemaModel):
    """Request payload for creating an export."""

    format: ExportFormat
    scope: ExportScope


class ExportResource(SchemaModel):
    """Export resource returned by export endpoints."""

    id: UUID
    run_id: UUID
    format: ExportFormat
    scope: ExportScope
    status: ExportStatus
    file_name: str | None = Field(default=None, min_length=1, max_length=255)
    storage_uri: str | None = Field(default=None, min_length=1, max_length=2048)
    download_url: str | None = Field(default=None, min_length=1, max_length=2048)
    created_at: datetime
    updated_at: datetime

    @field_validator("file_name", "storage_uri", "download_url")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        """Trim optional string fields while preserving nulls."""
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class CreateExportResponse(SuccessEnvelope[ExportResource]):
    """Success envelope for export creation."""


class ExportResponse(SuccessEnvelope[ExportResource]):
    """Success envelope for a single export resource."""


class ExportListResponse(PaginatedSuccessEnvelope[ExportResource]):
    """Paginated success envelope for export listings."""


CREATE_EXPORT_REQUEST_EXAMPLE: dict[str, Any] = {
    "format": "csv",
    "scope": "opportunities",
}

EXPORT_RESOURCE_EXAMPLE: dict[str, Any] = {
    "id": "9d115619-f5de-4e0e-bc9a-c4229144c4f4",
    "run_id": "6ab63a24-60a8-46c2-9f97-cf9d47bbfd52",
    "format": "xlsx",
    "scope": "full_run",
    "status": "completed",
    "file_name": "ebook-niche-research-full-run.xlsx",
    "storage_uri": "s3://ebook-niche-research-dev/exports/ebook-niche-research-full-run.xlsx",
    "download_url": "https://downloads.example.com/exports/ebook-niche-research-full-run.xlsx",
    "created_at": "2026-04-08T10:20:00Z",
    "updated_at": "2026-04-08T10:21:30Z",
}
