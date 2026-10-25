"""Unit tests for Render deployment configuration.

Covers:
1. normalize_database_url() — all URL format variants (pure function, no DB connection).
2. Settings.clean_database_url validator — normalization wired through pydantic.
3. Production fail-closed behaviour — Settings raises when API_AUTH_TOKEN is absent.
4. Local development defaults — Settings loads cleanly with no env vars set.
"""
from __future__ import annotations

import os
import pytest

from app.core.config import normalize_database_url, Settings


# ---------------------------------------------------------------------------
# 1. normalize_database_url — pure function, parametrised
# ---------------------------------------------------------------------------

class TestNormalizeDatabaseUrl:
    """Validates all URL format variants handled by normalize_database_url."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            # Render injects postgres:// — must become postgresql+asyncpg://
            (
                "postgres://user:pass@host:5432/db",
                "postgresql+asyncpg://user:pass@host:5432/db",
            ),
            # Generic postgresql:// without driver — must become postgresql+asyncpg://
            (
                "postgresql://user:pass@host:5432/db",
                "postgresql+asyncpg://user:pass@host:5432/db",
            ),
            # Already-correct URL — must be left untouched
            (
                "postgresql+asyncpg://user:pass@host:5432/db",
                "postgresql+asyncpg://user:pass@host:5432/db",
            ),
            # SQLite (test / local) — must be left untouched
            (
                "sqlite+aiosqlite:///./evcharge_predict.db",
                "sqlite+aiosqlite:///./evcharge_predict.db",
            ),
            # SQLite in-memory — must be left untouched
            (
                "sqlite+aiosqlite://",
                "sqlite+aiosqlite://",
            ),
            # Leading / trailing whitespace is stripped
            (
                "  postgres://user:pass@host/db  ",
                "postgresql+asyncpg://user:pass@host/db",
            ),
            # Render URL with query params preserved
            (
                "postgres://user:pass@host:5432/db?sslmode=require",
                "postgresql+asyncpg://user:pass@host:5432/db?sslmode=require",
            ),
        ],
    )
    def test_url_normalization(self, raw: str, expected: str) -> None:
        assert normalize_database_url(raw) == expected

    def test_empty_string_returns_empty(self) -> None:
        assert normalize_database_url("") == ""

    def test_none_coerced_to_empty(self) -> None:
        # The function guards against None via (url or "")
        assert normalize_database_url(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 2. Settings.clean_database_url validator — normalization wired through pydantic
# ---------------------------------------------------------------------------

class TestSettingsDatabaseUrlValidator:
    """Settings must normalise DATABASE_URL env-var before storing it."""

    def test_postgres_url_normalised_by_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgres://u:p@host:5432/mydb")
        monkeypatch.setenv("APP_ENV", "development")
        # Bypass lru_cache
        settings = Settings()
        assert settings.database_url.startswith("postgresql+asyncpg://")

    def test_postgresql_url_normalised_by_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/mydb")
        monkeypatch.setenv("APP_ENV", "development")
        settings = Settings()
        assert settings.database_url.startswith("postgresql+asyncpg://")

    def test_asyncpg_url_unchanged_by_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        url = "postgresql+asyncpg://u:p@host:5432/mydb"
        monkeypatch.setenv("DATABASE_URL", url)
        monkeypatch.setenv("APP_ENV", "development")
        settings = Settings()
        assert settings.database_url == url

    def test_sqlite_url_unchanged_by_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        url = "sqlite+aiosqlite:///./test.db"
        monkeypatch.setenv("DATABASE_URL", url)
        monkeypatch.setenv("APP_ENV", "development")
        settings = Settings()
        assert settings.database_url == url


# ---------------------------------------------------------------------------
# 3. Production fail-closed — missing API_AUTH_TOKEN must raise at startup
# ---------------------------------------------------------------------------

class TestProductionFailClosed:
    """Validates that Settings refuses to initialise in production without a token."""

    def test_production_raises_without_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
        with pytest.raises(Exception, match="api_auth_token"):
            Settings()

    def test_production_raises_with_placeholder_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("API_AUTH_TOKEN", "replace-with-service-token")
        with pytest.raises(Exception, match="api_auth_token"):
            Settings()

    def test_production_starts_with_valid_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("API_AUTH_TOKEN", "a-real-secret-token-that-is-long-enough")
        # Should not raise
        settings = Settings()
        assert settings.app_env == "production"
        assert settings.api_auth_token == "a-real-secret-token-that-is-long-enough"


# ---------------------------------------------------------------------------
# 4. Local development defaults — no env vars required
# ---------------------------------------------------------------------------

class TestLocalDevelopmentDefaults:
    """Settings must load cleanly in development without any env vars set."""

    def test_dev_loads_without_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        settings = Settings()
        assert settings.app_env == "development"
        assert settings.api_auth_token is None

    def test_dev_database_url_is_sqlite(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        settings = Settings()
        assert "sqlite" in settings.database_url
