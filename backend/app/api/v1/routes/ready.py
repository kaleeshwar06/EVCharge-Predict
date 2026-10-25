"""Readiness check endpoint — GET /readyz and GET /api/v1/readyz."""
from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine
from app.services.model_loader import ModelService

router = APIRouter(tags=["readiness"])


@router.get(
    "/readyz",
    summary="Readiness check",
    description="Checks whether the database connection and model artifacts are ready to serve forecasts.",
)
async def readyz():
    settings = get_settings()
    model_service = ModelService.get_instance()

    db_ready = False
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            db_ready = True
    except Exception:
        db_ready = False

    is_ready = db_ready and model_service.is_loaded

    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if is_ready else "not_ready",
            "service": "evcharge-predict",
            "api_version": settings.api_version,
            "database_ready": db_ready,
            "models_loaded": model_service.is_loaded,
            "model_error": model_service.load_error if not model_service.is_loaded else None,
        },
    )
