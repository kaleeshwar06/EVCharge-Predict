"""API routes for ingesting and retrieving EVCharge-Opt allocation feedback."""
from __future__ import annotations

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.feedback import (
    FeedbackCreateRequest,
    FeedbackCreateResponse,
    FeedbackDetailRead,
)
from app.services.feedback_service import (
    FeedbackConflictError,
    FeedbackIntervalAlignmentError,
    FeedbackService,
    FeedbackStationError,
    ForecastNotFoundError,
    ScenarioMismatchError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post(
    "",
    response_model=FeedbackCreateResponse,
    summary="Submit optimizer allocation feedback",
    description=(
        "Accepts, validates, and persists allocation feedback from EVCharge-Opt. "
        "Enforces deterministic idempotency using allocation_run_id and request payload hashing."
    ),
    responses={
        201: {"description": "Feedback newly accepted and persisted"},
        200: {"description": "Idempotent duplicate request recognized, original record returned"},
        400: {"description": "Validation failure, scenario mismatch, or interval alignment error"},
        404: {"description": "Referenced forecast or station not found"},
        409: {"description": "Conflict: same allocation_run_id submitted with differing payload"},
    },
)
async def submit_feedback(
    request: FeedbackCreateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    try:
        service = FeedbackService(db=db)
        resp, status_code = await service.submit_feedback(request)
        return JSONResponse(status_code=status_code, content=resp.model_dump(mode="json"))
    except ForecastNotFoundError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except FeedbackStationError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
    except ScenarioMismatchError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except FeedbackIntervalAlignmentError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except FeedbackConflictError as err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))
    except Exception as err:
        logger.exception("Unexpected error during feedback processing")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Feedback ingestion failed: {str(err)}",
        )


@router.get(
    "",
    response_model=List[FeedbackDetailRead],
    summary="List feedback submissions",
    description="Lists feedback records optionally filtered by forecast_id and/or scenario_id.",
)
async def list_feedback(
    forecast_id: Optional[str] = Query(None, description="Filter by originating forecast ID"),
    scenario_id: Optional[str] = Query(None, description="Filter by scenario ID"),
    db: AsyncSession = Depends(get_db_session),
) -> List[FeedbackDetailRead]:
    service = FeedbackService(db=db)
    return await service.list_feedback(forecast_id=forecast_id, scenario_id=scenario_id)


@router.get(
    "/{feedback_id}",
    response_model=FeedbackDetailRead,
    summary="Get feedback by ID",
    description="Retrieves feedback metadata, submission status, and associated forecast references.",
)
async def get_feedback(
    feedback_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> FeedbackDetailRead:
    service = FeedbackService(db=db)
    fbk = await service.get_feedback_by_id(feedback_id=feedback_id)
    if not fbk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback record '{feedback_id}' not found.",
        )
    return fbk
