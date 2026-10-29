"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root: backend/app/core/ -> 3 levels up -> EVCharge-Predict/
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def normalize_database_url(url: str) -> str:
    """Normalizes database URLs for async SQLAlchemy.

    Render and managed cloud providers inject PostgreSQL URLs starting with
    'postgres://' or 'postgresql://'. Async SQLAlchemy requires the asyncpg driver
    prefix 'postgresql+asyncpg://'.

    Rules:
    - 'postgres://' -> 'postgresql+asyncpg://'
    - 'postgresql://' -> 'postgresql+asyncpg://' (if '+asyncpg' not already present)
    - SQLite URLs (e.g. 'sqlite+aiosqlite:///...') are preserved untouched.
    - Already-correct 'postgresql+asyncpg://' URLs are preserved untouched.
    """
    clean_url = (url or "").strip()
    if clean_url.startswith("postgres://"):
        return clean_url.replace("postgres://", "postgresql+asyncpg://", 1)
    if clean_url.startswith("postgresql://") and not clean_url.startswith("postgresql+asyncpg://"):
        return clean_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return clean_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: str = Field("development", description="development | production | testing")
    api_version: str = Field("1.0")
    log_level: str = Field("INFO")

    # Server (Render provides $PORT; host should bind to 0.0.0.0 in production)
    host: str = Field("127.0.0.1", description="Server bind host (127.0.0.1 locally, 0.0.0.0 in deployment)")
    port: int = Field(8001, description="Server listen port (8001 locally, $PORT on Render)")

    # Database
    database_url: str = Field(
        f"sqlite+aiosqlite:///{PROJECT_ROOT / 'evcharge_predict.db'}",
        description="Async database connection string. e.g. postgresql+asyncpg://user:pass@host/db or sqlite+aiosqlite:///path"
    )

    # Station mapping persistence file
    station_map_file: Path = Field(
        PROJECT_ROOT / "data" / "processed" / "station_mapping.json",
        description="Persistent JSON dictionary mapping source station IDs to canonical ST-xxx IDs."
    )

    # Model Artifact Directory
    model_artifact_dir: Path = Field(
        PROJECT_ROOT / "artifacts" / "models",
        description="Directory containing trained model joblib files and manifest.json."
    )

    # Partner API
    evcharge_opt_base_url: str = Field(
        "https://evcharge-opt-api.onrender.com",
        description="Base URL for EVCharge-Opt service."
    )
    evcharge_opt_api_key: str = Field("replace-me")
    opt_service_token: Optional[str] = Field(
        None,
        description="Dedicated service token for EVCharge-Opt partner communication."
    )

    # CORS
    frontend_origin: str = Field("http://127.0.0.1:5173", description="Allowed CORS origin (e.g. https://my-frontend.onrender.com or comma-separated origins)")

    # Security & Service Authentication
    secret_key: str = Field("replace-with-a-long-random-string")
    api_auth_token: Optional[str] = Field(None, description="Shared secret bearer token for service-to-service auth.")
    enable_docs: bool = Field(True, description="Expose /docs and /openapi.json publicly. Set False in production.")

    @field_validator("frontend_origin", mode="before")
    @classmethod
    def clean_frontend_origin(cls, v: str) -> str:
        """Strips surrounding whitespace/quotes from frontend origin."""
        return str(v).strip().strip("'\"") if v else "http://127.0.0.1:5173"

    @field_validator("database_url", mode="before")
    @classmethod
    def clean_database_url(cls, v: str) -> str:
        """Automatically normalizes Render/PostgreSQL connection strings to asyncpg driver dialect."""
        return normalize_database_url(str(v))

    def get_allowed_cors_origins(self) -> list[str]:
        """Resolves allowed origins for CORS.

        Rules:
        - In production: only explicitly configured origins in frontend_origin are permitted.
          Default localhost origins are NEVER added automatically.
          Wildcards ('*') are rejected to prevent combination with allow_credentials=True.
        - In development/testing: parses frontend_origin, and additionally includes
          convenient localhost/127.0.0.1 origins for local UI development.
        """
        raw_origins = [orig.strip() for orig in (self.frontend_origin or "").split(",") if orig.strip()]
        # Strip trailing slashes and quotes
        clean_origins = [orig.rstrip("/").strip("'\"") for orig in raw_origins if orig.rstrip("/")]

        is_prod = (self.app_env or "").lower().strip() == "production"
        if is_prod:
            # Production: only explicitly listed origins, no wildcards
            safe_origins = [o for o in clean_origins if o != "*"]
            return safe_origins

        # Development / sandbox: include clean origins plus standard localhost ports
        dev_defaults = ["http://localhost:5173", "http://127.0.0.1:5173"]
        for default in dev_defaults:
            if default not in clean_origins:
                clean_origins.append(default)
        return clean_origins

    @model_validator(mode="after")
    def validate_production_security(self) -> Settings:
        """Fail closed in production if API_AUTH_TOKEN is not configured or unsafe CORS origins are set."""
        env_clean = (self.app_env or "").lower().strip()
        if env_clean == "production":
            token_clean = (self.api_auth_token or "").strip()
            if not token_clean or token_clean == "replace-with-service-token":
                raise ValueError(
                    "Production configuration violation: 'api_auth_token' must be set to a secure, "
                    "non-default secret token when APP_ENV=production. The service will not start in an insecure state."
                )
            # Validate CORS safety in production: do not allow wildcard origin
            raw_origins = [orig.strip() for orig in (self.frontend_origin or "").split(",") if orig.strip()]
            if "*" in raw_origins:
                raise ValueError(
                    "Production configuration violation: wildcard '*' is not permitted in 'frontend_origin' "
                    "when allow_credentials=True."
                )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
