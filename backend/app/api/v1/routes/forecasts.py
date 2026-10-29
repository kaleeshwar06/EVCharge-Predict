"""Forecast API endpoints exposing the EVCharge-Predict <-> EVCharge-Opt interface."""
from __future__ import annotations

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.feedback import AdjustedDemandResponse
from app.schemas.forecast import (
    ForecastCreateRequest,
    ForecastCreateResponse,
    ForecastDetailRead,
    ForecastSummaryRead,
)
from app.services.feedback_service import FeedbackService
from app.services.forecasting import (
    ForecastingEngine,
    InsufficientHistoryError,
    StationNotFoundError,
)
from app.services.model_loader import ModelArtifactError, ModelService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.post(
    "",
    response_model=ForecastCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate 6-hour charging demand forecast",
    description="Generates and persists a six-hour recursive demand forecast for requested canonical stations.",
)
async def create_forecast(
    request: ForecastCreateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ForecastCreateResponse:
    try:
        engine = ForecastingEngine(db=db)
        response = await engine.generate_and_persist_forecast(request)
        return response
    except StationNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        )
    except InsufficientHistoryError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )
    except ModelArtifactError as err:
        logger.error(f"Model service unavailable: {err}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Forecasting model service unavailable: {err}",
        )
    except Exception as err:
        logger.exception("Unexpected error during forecast generation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Forecast generation failed: {str(err)}",
        )


@router.get(
    "",
    response_model=List[ForecastSummaryRead],
    summary="List saved forecasts",
    description="Retrieves a summarized history of saved demand forecasts with optional filtering.",
)
async def list_forecasts(
    scenario_id: Optional[str] = Query(None, description="Filter by scenario ID"),
    station_id: Optional[str] = Query(None, description="Filter by station ID"),
    limit: int = Query(50, ge=1, le=100, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Records offset"),
    db: AsyncSession = Depends(get_db_session),
) -> List[ForecastSummaryRead]:
    return await ForecastingEngine.list_forecasts(
        db, scenario_id=scenario_id, station_id=station_id, limit=limit, offset=offset
    )


@router.get(
    "/latest",
    response_model=ForecastDetailRead,
    summary="Get latest baseline forecast for scenario",
    description="Retrieves the newest completed baseline forecast for the specified scenario ID.",
)
async def get_latest_forecast(
    scenario_id: str = Query(..., min_length=1, description="Scenario identifier"),
    db: AsyncSession = Depends(get_db_session),
) -> ForecastDetailRead:
    forecast = await ForecastingEngine.get_latest_baseline_forecast(db, scenario_id=scenario_id)
    if not forecast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No completed baseline forecast found for scenario: {scenario_id}",
        )
    return forecast


@router.get(
    "/{forecast_id}",
    response_model=ForecastDetailRead,
    summary="Get forecast by ID",
    description="Retrieves the full multi-station, six-interval prediction payload for a specific forecast.",
)
async def get_forecast(
    forecast_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> ForecastDetailRead:
    forecast = await ForecastingEngine.get_forecast_by_id(db, forecast_id=forecast_id)
    if not forecast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Forecast '{forecast_id}' not found.",
        )
    return forecast


@router.get(
    "/{forecast_id}/adjusted-demand",
    response_model=AdjustedDemandResponse,
    summary="Get feedback-adjusted operational demand",
    description=(
        "Retrieves the derived operational demand envelope comparing baseline predictions "
        "against an accepted allocation feedback submission."
    ),
)
async def get_adjusted_demand(
    forecast_id: str,
    feedback_id: str = Query(..., description="Unique feedback ID (fbk_...) to retrieve derived demand for"),
    db: AsyncSession = Depends(get_db_session),
) -> AdjustedDemandResponse:
    service = FeedbackService(db=db)
    result = await service.get_adjusted_demand(forecast_id=forecast_id, feedback_id=feedback_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No adjusted demand found for forecast '{forecast_id}' with feedback '{feedback_id}'.",
        )
    return result

