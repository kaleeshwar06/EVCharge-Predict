"""Observability middleware: safe correlation ID validation, latency tracking, and structured logging."""
from __future__ import annotations

import logging
import re
import time
from uuid import uuid4
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.access")

# Strict regex for incoming request ID: alphanumeric, hyphen, underscore, 8 to 64 chars.
# Rejects multiline strings, SQL fragments, control characters, or excessively long payloads.
REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{8,64}$")


def sanitize_for_log(value: str) -> str:
    """Strips control chars, newlines, and carriage returns to prevent log injection."""
    return re.sub(r"[\r\n\t\x00-\x1f]", "_", value)[:128]


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Middleware managing request correlation IDs, latency measurement, and structured logging."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()

        # 1. Inspect incoming headers for request correlation ID
        raw_req_id = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID")

        if raw_req_id and REQUEST_ID_REGEX.match(raw_req_id.strip()):
            request_id = raw_req_id.strip()
        else:
            # Generate fresh UUID if missing, invalid format, or injection-like
            request_id = str(uuid4())

        # Store in request state for downstream handlers
        request.state.request_id = request_id

        # 2. Execute inner application pipeline
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            sanitized_path = sanitize_for_log(request.url.path)
            logger.error(
                f'request_id="{request_id}" method="{request.method}" path="{sanitized_path}" '
                f'status="500" duration_ms="{duration_ms:.2f}" outcome="unhandled_exception"'
            )
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        sanitized_path = sanitize_for_log(request.url.path)

        # 3. Always set the single canonical X-Request-ID on the response
        response.headers["X-Request-ID"] = request_id

        # 4. Safe structured logging without logging request bodies, headers, or secrets
        logger.info(
            f'request_id="{request_id}" method="{request.method}" path="{sanitized_path}" '
            f'status="{response.status_code}" duration_ms="{duration_ms:.2f}" outcome="completed"'
        )

        return response
