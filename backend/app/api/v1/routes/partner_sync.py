"""API route for EVCharge-Opt Partner Sync and Status."""
from __future__ import annotations

import logging
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, status
import httpx

from app.core.config import get_settings
from app.schemas.partner_sync import PartnerSyncRequest, PartnerSyncResponse
from app.services.partner_sync_service import PartnerSyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/partner", tags=["partner"])


@router.post(
    "/sync",
    response_model=PartnerSyncResponse,
    summary="Execute EVCharge-Opt Partner Sync",
    description=(
        "Executes a verified end-to-end exchange with EVCharge-Opt: "
        "dispatches demand forecast, requests priority grid allocation, and submits allocation feedback. "
        "Returns the real HTTP response, allocation ID, feedback ID, and station allocation metrics."
    ),
)
async def sync_with_partner(request: PartnerSyncRequest) -> PartnerSyncResponse:
    try:
        service = PartnerSyncService()
        return await service.execute_sync(request)
    except Exception as err:
        logger.exception("Unexpected error during partner sync execution")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Partner synchronization failed: {str(err)}",
        )


@router.get(
    "/status",
    summary="Check EVCharge-Opt Connection Status",
    description="Probes the deployed EVCharge-Opt partner service to verify live connectivity.",
)
async def partner_status() -> Dict[str, Any]:
    settings = get_settings()
    base_url = settings.evcharge_opt_base_url.rstrip("/")
    probe_url = f"{base_url}/api/v1/integration/health"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(probe_url)
            if res.status_code == 200:
                return {
                    "connected": True,
                    "partner_base_url": base_url,
                    "http_status": 200,
                    "partner_details": res.json(),
                }
            return {
                "connected": False,
                "partner_base_url": base_url,
                "http_status": res.status_code,
                "error": res.text[:200],
            }
    except Exception as exc:
        return {
            "connected": False,
            "partner_base_url": base_url,
            "error": str(exc),
        }
