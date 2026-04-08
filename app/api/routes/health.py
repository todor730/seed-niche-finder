"""Health endpoint definitions."""

from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from app.schemas.common import ErrorEnvelope, SchemaModel, SuccessEnvelope

router = APIRouter(tags=["health"])


class HealthData(SchemaModel):
    """Health payload contents."""

    status: Literal["ok"] = "ok"
    service: Literal["ebook-niche-research-api"] = "ebook-niche-research-api"
    version: str = Field(min_length=1)


class HealthEnvelope(SuccessEnvelope[HealthData]):
    """Standard success response envelope for the health endpoint."""


@router.get(
    "/health",
    response_model=HealthEnvelope,
    summary="Service Health",
    operation_id="get_health",
    responses={500: {"model": ErrorEnvelope}},
)
async def get_health() -> HealthEnvelope:
    """Return the current service health state."""
    return HealthEnvelope(
        data=HealthData(
            status="ok",
            service="ebook-niche-research-api",
            version="1.0.0",
        )
    )
