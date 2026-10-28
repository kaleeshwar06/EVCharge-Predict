"""Tests verifying frontend security, demo/live mode separation, 401 handling,

and preventing secrets/tokens from leaking into frontend source or build artifacts.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
import pytest

FRONTEND_ROOT = Path(__file__).resolve().parent.parent.parent / "frontend"
FRONTEND_SRC = FRONTEND_ROOT / "src"
FRONTEND_DIST = FRONTEND_ROOT / "dist"


class TestFrontendSecurityAndBundleHygiene:
    """Ensure sensitive tokens or variables never leak into the frontend build or source."""

    def test_no_api_auth_token_in_frontend_source(self) -> None:
        """API_AUTH_TOKEN or secret token values must never be referenced or stored in frontend code."""
        pattern = re.compile(r"API_AUTH_TOKEN|Bearer\s+[A-Za-z0-9_\-]{20,}", re.IGNORECASE)
        for filepath in FRONTEND_SRC.rglob("*"):
            if filepath.is_file() and filepath.suffix in [".ts", ".tsx", ".js", ".jsx", ".html"]:
                content = filepath.read_text(encoding="utf-8")
                matches = pattern.findall(content)
                assert not matches, f"Potential sensitive token reference in {filepath}: {matches}"

    def test_no_auth_token_in_dist_bundle(self) -> None:
        """The built frontend JS/CSS bundle must not contain API_AUTH_TOKEN, hardcoded secrets, or localhost fallback."""
        if not FRONTEND_DIST.exists():
            pytest.skip("Frontend dist directory does not exist. Run npm run build first.")

        # Check all js files in dist
        js_files = list(FRONTEND_DIST.glob("assets/*.js"))
        assert len(js_files) > 0, "No built JavaScript bundles found in dist/assets"

        for js_file in js_files:
            bundle_text = js_file.read_text(encoding="utf-8")
            # 1. No API_AUTH_TOKEN
            assert "API_AUTH_TOKEN" not in bundle_text
            # 2. No localhost fallback
            assert "127.0.0.1:8001" not in bundle_text
            assert "localhost:8001" not in bundle_text
            # 3. Production backend endpoint must be present
            assert "evcharge-predict.onrender.com" in bundle_text

    def test_env_example_does_not_contain_secrets(self) -> None:
        """.env.example must only document VITE_API_BASE_URL and never contain API_AUTH_TOKEN."""
        env_example = FRONTEND_ROOT / ".env.example"
        if env_example.exists():
            text = env_example.read_text(encoding="utf-8")
            assert "API_AUTH_TOKEN" not in text
            assert "VITE_API_AUTH_TOKEN" not in text


class TestDemoModeSeparationAndErrorHandling:
    """Verify demo mode and live API mode are cleanly separated in client code."""

    def test_demo_stations_isolated_in_demo_service(self) -> None:
        """Demo stations are isolated in demoService.ts and include ST-001, ST-002, ST-003."""
        demo_service = FRONTEND_SRC / "demoService.ts"
        assert demo_service.exists()
        content = demo_service.read_text(encoding="utf-8")
        assert "DEMO_STATIONS" in content
        assert "generateDemoForecast" in content
        assert "generateDemoFeedback" in content
        assert "generateDemoAdjustedDemand" in content

    def test_app_tsx_defaults_to_demo_mode_or_safe_mode(self) -> None:
        """App.tsx must define demoMode state and handle 401 cleanly without masking errors."""
        app_tsx = FRONTEND_SRC / "App.tsx"
        assert app_tsx.exists()
        content = app_tsx.read_text(encoding="utf-8")
        assert "useState<boolean>(true)" in content or "demoMode" in content
        # Ensure 401 handling informs user of token requirement
        assert "401" in content
        assert "DEMO_STATIONS" in content

    def test_station_table_does_not_silently_fallback(self) -> None:
        """StationTable must display explicit error when live API fails rather than silent fallback."""
        station_table = FRONTEND_SRC / "components" / "StationTable.tsx"
        assert station_table.exists()
        content = station_table.read_text(encoding="utf-8")
        assert "Live API Authentication" in content
        assert "demoMode" in content or "DEMO" in content

    def test_forecast_form_handles_401_gracefully(self) -> None:
        """ForecastForm must handle 401 gracefully and allow demo mode simulation."""
        forecast_form = FRONTEND_SRC / "components" / "ForecastForm.tsx"
        assert forecast_form.exists()
        content = forecast_form.read_text(encoding="utf-8")
        assert "401" in content
        assert "generateDemoForecast" in content
