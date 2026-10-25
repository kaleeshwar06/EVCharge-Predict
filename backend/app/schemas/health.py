"""Pydantic schemas for the health endpoint."""
from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    service: str = Field(..., examples=["evcharge-predict"])
    api_version: str = Field(..., examples=["1.0"])
    status: str = Field("ok", examples=["ok"])
