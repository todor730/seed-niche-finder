"""Research run API routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import CurrentUser, ServicePlaceholder, get_current_user, get_research_service
from app.core.errors import RunNotFoundError
from app.schemas.common import ErrorEnvelope
from app.schemas.research import (
    CancelRunData,
    CancelRunResponse,
    CreateResearchRunRequest,
    CreateResearchRunResponse,
    ResearchConfig,
    ResearchProgress,
    ResearchProgressResponse,
    ResearchRun,
    ResearchRunDetails,
    ResearchRunListItem,
    ResearchRunListResponse,
    ResearchRunResponse,
    ResearchRunStatus,
    ResearchRunSummary,
)

router = APIRouter(prefix="/research-runs", tags=["research_runs"])

ANONYMOUS_USER_ID = UUID("00000000-0000-0000-0000-000000000000")


@dataclass(slots=True)
class ResearchRunListResult:
    """Simple service-layer result for research run listings."""

    items: list[ResearchRunListItem]
    total: int
    limit: int
    offset: int


class ResearchRunService(Protocol):
    """Route-facing research run service contract."""

    def create_run(self, *, current_user: CurrentUser, payload: CreateResearchRunRequest) -> ResearchRun: ...

    def list_runs(
        self,
        *,
        current_user: CurrentUser,
        status: ResearchRunStatus | None,
        limit: int,
        offset: int,
    ) -> ResearchRunListResult: ...

    def get_run(self, *, current_user: CurrentUser, run_id: UUID) -> ResearchRunDetails: ...

    def get_progress(self, *, current_user: CurrentUser, run_id: UUID) -> ResearchProgress: ...

    def cancel_run(self, *, current_user: CurrentUser, run_id: UUID) -> CancelRunData: ...


def get_research_run_service(
    research_service=Depends(get_research_service),
) -> ResearchRunService:
    """Resolve the configured research service or fall back to a stub implementation."""
    if isinstance(research_service, ServicePlaceholder):
        return _stub_research_run_service
    return research_service


@router.post(
    "",
    response_model=CreateResearchRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Research Run",
    operation_id="create_research_run",
    responses={422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}},
)
async def create_research_run(
    payload: CreateResearchRunRequest,
    current_user: CurrentUser = Depends(get_current_user),
    research_service: ResearchRunService = Depends(get_research_run_service),
) -> CreateResearchRunResponse:
    """Create a research run and return the created run envelope."""
    research_run = research_service.create_run(current_user=current_user, payload=payload)
    return CreateResearchRunResponse(data=research_run, meta={}, error=None)


@router.get(
    "",
    response_model=ResearchRunListResponse,
    summary="List Research Runs",
    operation_id="list_research_runs",
    responses={422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}},
)
async def list_research_runs(
    status: ResearchRunStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
    research_service: ResearchRunService = Depends(get_research_run_service),
) -> ResearchRunListResponse:
    """List research runs using the configured service layer."""
    result = research_service.list_runs(
        current_user=current_user,
        status=status,
        limit=limit,
        offset=offset,
    )
    return ResearchRunListResponse(
        data=result.items,
        meta={"total": result.total, "limit": result.limit, "offset": result.offset},
        error=None,
    )


@router.get(
    "/{run_id}",
    response_model=ResearchRunResponse,
    summary="Get Research Run",
    operation_id="get_research_run",
    responses={404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}},
)
async def get_research_run(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    research_service: ResearchRunService = Depends(get_research_run_service),
) -> ResearchRunResponse:
    """Return a detailed research run payload."""
    research_run = research_service.get_run(current_user=current_user, run_id=run_id)
    return ResearchRunResponse(data=research_run, meta={}, error=None)


@router.get(
    "/{run_id}/progress",
    response_model=ResearchProgressResponse,
    summary="Get Research Run Progress",
    operation_id="get_research_run_progress",
    responses={404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}},
)
async def get_research_run_progress(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    research_service: ResearchRunService = Depends(get_research_run_service),
) -> ResearchProgressResponse:
    """Return the progress payload for a research run."""
    progress = research_service.get_progress(current_user=current_user, run_id=run_id)
    return ResearchProgressResponse(data=progress, meta={}, error=None)


@router.post(
    "/{run_id}/cancel",
    response_model=CancelRunResponse,
    summary="Cancel Research Run",
    operation_id="cancel_research_run",
    responses={404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}},
)
async def cancel_research_run(
    run_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    research_service: ResearchRunService = Depends(get_research_run_service),
) -> CancelRunResponse:
    """Cancel a research run through the configured service layer."""
    cancel_data = research_service.cancel_run(current_user=current_user, run_id=run_id)
    return CancelRunResponse(data=cancel_data, meta={}, error=None)


class _StubResearchRunService:
    """Small in-memory fallback service used until the real research service is wired."""

    def __init__(self) -> None:
        self._runs: dict[UUID, ResearchRunDetails] = {}

    def create_run(self, *, current_user: CurrentUser, payload: CreateResearchRunRequest) -> ResearchRun:
        now = datetime.now(UTC)
        run_id = uuid4()
        user_id = current_user.id or ANONYMOUS_USER_ID
        progress = ResearchProgress(
            status=ResearchRunStatus.PENDING,
            current_stage="queued",
            completed_steps=0,
            total_steps=5,
            percent_complete=0.0,
            message="Research run queued.",
            started_at=None,
            updated_at=now,
            completed_at=None,
        )
        run_details = ResearchRunDetails(
            id=run_id,
            user_id=user_id,
            seed_niche=payload.seed_niche,
            status=ResearchRunStatus.PENDING,
            config=payload.config,
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
            error_message=None,
            summary=ResearchRunSummary(),
            progress=progress,
        )
        self._runs[run_id] = run_details
        return self._to_research_run(run_details)

    def list_runs(
        self,
        *,
        current_user: CurrentUser,
        status: ResearchRunStatus | None,
        limit: int,
        offset: int,
    ) -> ResearchRunListResult:
        user_id = current_user.id or ANONYMOUS_USER_ID
        runs = [run for run in self._runs.values() if run.user_id == user_id]
        if status is not None:
            runs = [run for run in runs if run.status == status]

        runs.sort(key=lambda run: run.created_at, reverse=True)
        total = len(runs)
        paged_runs = runs[offset : offset + limit]
        items = [self._to_list_item(run) for run in paged_runs]
        return ResearchRunListResult(items=items, total=total, limit=limit, offset=offset)

    def get_run(self, *, current_user: CurrentUser, run_id: UUID) -> ResearchRunDetails:
        return self._get_owned_run(current_user=current_user, run_id=run_id)

    def get_progress(self, *, current_user: CurrentUser, run_id: UUID) -> ResearchProgress:
        run = self._get_owned_run(current_user=current_user, run_id=run_id)
        return run.progress

    def cancel_run(self, *, current_user: CurrentUser, run_id: UUID) -> CancelRunData:
        run = self._get_owned_run(current_user=current_user, run_id=run_id)
        now = datetime.now(UTC)
        cancelled_progress = run.progress.model_copy(
            update={
                "status": ResearchRunStatus.CANCELLED,
                "current_stage": "cancelled",
                "message": "Research run cancelled.",
                "updated_at": now,
                "completed_at": now,
                "percent_complete": run.progress.percent_complete,
            }
        )
        cancelled_run = run.model_copy(
            update={
                "status": ResearchRunStatus.CANCELLED,
                "updated_at": now,
                "completed_at": now,
                "progress": cancelled_progress,
            }
        )
        self._runs[run_id] = cancelled_run
        return CancelRunData(run_id=run_id, status=ResearchRunStatus.CANCELLED)

    def _get_owned_run(self, *, current_user: CurrentUser, run_id: UUID) -> ResearchRunDetails:
        run = self._runs.get(run_id)
        if run is None:
            raise RunNotFoundError(str(run_id))

        user_id = current_user.id or ANONYMOUS_USER_ID
        if run.user_id != user_id:
            raise RunNotFoundError(str(run_id))
        return run

    @staticmethod
    def _to_research_run(run: ResearchRunDetails) -> ResearchRun:
        return ResearchRun(
            id=run.id,
            user_id=run.user_id,
            seed_niche=run.seed_niche,
            status=run.status,
            config=ResearchConfig(**run.config.model_dump()),
            created_at=run.created_at,
            updated_at=run.updated_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            error_message=run.error_message,
        )

    @staticmethod
    def _to_list_item(run: ResearchRunDetails) -> ResearchRunListItem:
        return ResearchRunListItem(
            id=run.id,
            user_id=run.user_id,
            seed_niche=run.seed_niche,
            status=run.status,
            config=ResearchConfig(**run.config.model_dump()),
            created_at=run.created_at,
            updated_at=run.updated_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            error_message=run.error_message,
            summary=ResearchRunSummary(**run.summary.model_dump()),
        )


_stub_research_run_service = _StubResearchRunService()
