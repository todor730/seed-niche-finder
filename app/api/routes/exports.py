"""Export API routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, status

from app.api.dependencies import CurrentUser, ServicePlaceholder, get_current_user, get_export_service
from app.core.errors import ExportNotFoundError
from app.schemas.common import ErrorEnvelope, ExportStatus
from app.schemas.export import (
    EXPORT_RESOURCE_EXAMPLE,
    CreateExportRequest,
    CreateExportResponse,
    ExportListResponse,
    ExportResource,
    ExportResponse,
)

router = APIRouter(tags=["exports"])


@dataclass(slots=True)
class ExportListResult:
    """Simple service-layer result for export listings."""

    items: list[ExportResource]
    total: int
    limit: int
    offset: int


class ExportRouteService(Protocol):
    """Route-facing export service contract."""

    def create_export(
        self,
        *,
        current_user: CurrentUser,
        run_id: UUID,
        payload: CreateExportRequest,
    ) -> ExportResource: ...

    def list_run_exports(
        self,
        *,
        current_user: CurrentUser,
        run_id: UUID,
        limit: int,
        offset: int,
    ) -> ExportListResult: ...

    def get_export(self, *, current_user: CurrentUser, export_id: UUID) -> ExportResource: ...


def get_export_route_service(
    export_service=Depends(get_export_service),
) -> ExportRouteService:
    """Resolve the configured export service or fall back to a stub implementation."""
    if isinstance(export_service, ServicePlaceholder):
        return _stub_export_service
    return export_service


@router.post(
    "/research-runs/{run_id}/exports",
    response_model=CreateExportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Export",
    operation_id="create_export",
    responses={404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}},
)
async def create_export(
    run_id: UUID,
    payload: CreateExportRequest,
    current_user: CurrentUser = Depends(get_current_user),
    export_service: ExportRouteService = Depends(get_export_route_service),
) -> CreateExportResponse:
    """Create an export request for a research run."""
    export_resource = export_service.create_export(
        current_user=current_user,
        run_id=run_id,
        payload=payload,
    )
    return CreateExportResponse(data=export_resource, meta={}, error=None)


@router.get(
    "/research-runs/{run_id}/exports",
    response_model=ExportListResponse,
    summary="List Run Exports",
    operation_id="list_run_exports",
    responses={404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}},
)
async def list_run_exports(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    export_service: ExportRouteService = Depends(get_export_route_service),
) -> ExportListResponse:
    """List exports for a research run."""
    result = export_service.list_run_exports(
        current_user=current_user,
        run_id=run_id,
        limit=100,
        offset=0,
    )
    return ExportListResponse(
        data=result.items,
        meta={"total": result.total, "limit": result.limit, "offset": result.offset},
        error=None,
    )


@router.get(
    "/exports/{export_id}",
    response_model=ExportResponse,
    summary="Get Export",
    operation_id="get_export",
    responses={404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}},
)
async def get_export(
    export_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    export_service: ExportRouteService = Depends(get_export_route_service),
) -> ExportResponse:
    """Return a single export resource."""
    export_resource = export_service.get_export(current_user=current_user, export_id=export_id)
    return ExportResponse(data=export_resource, meta={}, error=None)


class _StubExportService:
    """Small in-memory fallback service used until the real export service is wired."""

    def __init__(self) -> None:
        example_export = ExportResource.model_validate(EXPORT_RESOURCE_EXAMPLE)
        self._exports: dict[UUID, ExportResource] = {example_export.id: example_export}

    def create_export(
        self,
        *,
        current_user: CurrentUser,
        run_id: UUID,
        payload: CreateExportRequest,
    ) -> ExportResource:
        now = datetime.now(UTC)
        export_id = uuid4()
        file_stub = f"{run_id}-{payload.scope}.{payload.format}"
        export_resource = ExportResource(
            id=export_id,
            run_id=run_id,
            format=payload.format,
            scope=payload.scope,
            status=ExportStatus.PENDING,
            file_name=file_stub,
            storage_uri=None,
            download_url=None,
            created_at=now,
            updated_at=now,
        )
        self._exports[export_id] = export_resource
        return export_resource

    def list_run_exports(
        self,
        *,
        current_user: CurrentUser,
        run_id: UUID,
        limit: int,
        offset: int,
    ) -> ExportListResult:
        items = [export for export in self._exports.values() if export.run_id == run_id]
        items.sort(key=lambda export: export.created_at, reverse=True)
        total = len(items)
        paged_items = items[offset : offset + limit]
        return ExportListResult(items=paged_items, total=total, limit=limit, offset=offset)

    def get_export(self, *, current_user: CurrentUser, export_id: UUID) -> ExportResource:
        export_resource = self._exports.get(export_id)
        if export_resource is None:
            raise ExportNotFoundError(str(export_id))
        return export_resource


_stub_export_service = _StubExportService()
