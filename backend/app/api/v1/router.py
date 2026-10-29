"""v1 API router aggregating all versioned route modules."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from .routes import feedback, forecasts, health, imports, partner_sync, ready, sessions, stations
from ...core.security import verify_service_token

api_router = APIRouter()

# Public operational probe endpoints (exempt from auth so orchestrators can probe without tokens)
api_router.include_router(health.router)
api_router.include_router(ready.router)

# Outbound Partner Synchronization routes (connects EVCharge-Predict to EVCharge-Opt)
api_router.include_router(partner_sync.router)

# Protected business & partner integration endpoints (secured by verify_service_token)
api_router.include_router(stations.router, dependencies=[Depends(verify_service_token)])
api_router.include_router(sessions.router, dependencies=[Depends(verify_service_token)])
api_router.include_router(imports.router, dependencies=[Depends(verify_service_token)])
api_router.include_router(forecasts.router, dependencies=[Depends(verify_service_token)])
api_router.include_router(feedback.router, dependencies=[Depends(verify_service_token)])
