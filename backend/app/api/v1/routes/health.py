"""Health-check endpoint — GET /api/v1/healthz."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns the service name and API version. No auth required.",
)
async def healthz() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        service="evcharge-predict",
        api_version=settings.api_version,
        status="ok",
    )
