"""Service-to-service authentication dependency and security policies."""
from __future__ import annotations

import logging
import secrets
from typing import Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# HTTPBearer scheme: auto_error=False allows optional handling so we can return custom 401/403
http_bearer_scheme = HTTPBearer(auto_error=False)


async def verify_service_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(http_bearer_scheme),
) -> Optional[str]:
    """Validates the Bearer token against configured API_AUTH_TOKEN.

    Rules:
    - If APP_ENV != 'production' and API_AUTH_TOKEN is not configured:
      Authentication is disabled for local development sandbox. A warning is logged.
    - If API_AUTH_TOKEN is configured (or in production):
      - Missing credentials -> HTTP 401 Unauthorized
      - Invalid token -> HTTP 403 Forbidden
      - Valid token -> success
    """
    settings = get_settings()
    configured_token = settings.api_auth_token

    # In local development without configured token: allow open access with explicit log warning
    if not configured_token:
        if settings.app_env.lower() == "production":
            # Safety double-guard (config validator will also catch this on startup)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Production security misconfiguration: API_AUTH_TOKEN is required.",
            )
        # Sandbox mode
        logger.warning(
            "Service authentication is DISABLED because API_AUTH_TOKEN is not set. "
            "This configuration is strictly for local development and must never be used in production."
        )
        return None

    # When token is configured, enforce strictly
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header or Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    provided_token = credentials.credentials
    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(provided_token, configured_token):
        logger.warning("Rejected invalid API authorization token attempt.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired authorization token.",
        )

    return provided_token
