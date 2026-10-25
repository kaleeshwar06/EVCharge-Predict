"""EVCharge-Predict FastAPI Application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router as api_v1_router
from app.api.v1.routes.health import healthz
from app.api.v1.routes.ready import readyz
from app.core.config import get_settings
from app.core.middleware import RequestCorrelationMiddleware

settings = get_settings()

# Configure /docs and /openapi.json dynamically based on settings.enable_docs
docs_url = "/docs" if settings.enable_docs else None
openapi_url = "/openapi.json" if settings.enable_docs else None

app = FastAPI(
    title="EVCharge-Predict API",
    description="Electric Vehicle Charging Demand Prediction System",
    version=settings.api_version,
    docs_url=docs_url,
    openapi_url=openapi_url,
)

# Request correlation, latency tracking, and structured logging middleware
app.add_middleware(RequestCorrelationMiddleware)

# CORS setup: Parse frontend_origin (supports single origin or comma-separated list)
cors_origins = [orig.strip() for orig in settings.frontend_origin.split(",") if orig.strip()]
for default_origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
    if default_origin not in cors_origins:
        cors_origins.append(default_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root-level health and readiness aliases (exempt from auth for deployment orchestrators)
app.get(
    "/healthz",
    tags=["health"],
    summary="Health check (root alias)",
    description="Alias to /api/v1/healthz returning minimal operational status.",
)(healthz)

app.get(
    "/readyz",
    tags=["readiness"],
    summary="Readiness check (root alias)",
    description="Alias to /api/v1/readyz checking database and model readiness without heavy inference.",
)(readyz)

# Mount /api/v1 prefix
app.include_router(api_v1_router, prefix="/api/v1")
