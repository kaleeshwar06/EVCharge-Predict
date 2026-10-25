"""Dedicated singleton service for loading, validating, and serving Phase 3 model artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import joblib
import pandas as pd
import sklearn

from app.core.config import get_settings
from app.ml.models import RandomForestDemandModel


class ModelArtifactError(Exception):
    """Raised when model artifacts cannot be found, loaded, or validated."""
    pass


class ModelService:
    """Manages loaded ML model artifacts in memory."""

    _instance: Optional["ModelService"] = None

    def __init__(self, artifact_dir: Optional[Path] = None) -> None:
        settings = get_settings()
        self.artifact_dir = artifact_dir or settings.model_artifact_dir
        self.arrival_model: Optional[RandomForestDemandModel] = None
        self.energy_model: Optional[RandomForestDemandModel] = None
        self.manifest: Optional[Dict[str, Any]] = None
        self.is_loaded: bool = False
        self.load_error: Optional[str] = None

        self.load_artifacts()

    @classmethod
    def get_instance(cls) -> "ModelService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Resets singleton instance (useful for test isolation)."""
        cls._instance = None

    def load_artifacts(self) -> None:
        """Loads and verifies models, manifest, and dependencies."""
        manifest_path = self.artifact_dir / "manifest.json"
        arrival_path = self.artifact_dir / "arrival_model.joblib"
        energy_path = self.artifact_dir / "energy_model.joblib"

        if not manifest_path.exists():
            self.load_error = f"Model manifest missing at: {manifest_path}"
            return

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                self.manifest = json.load(f)
        except Exception as e:
            self.load_error = f"Corrupted manifest JSON: {e}"
            return

        # 1. Validate scikit-learn version
        manifest_sklearn_ver = self.manifest.get("scikit_learn_version")
        current_sklearn_ver = sklearn.__version__
        if manifest_sklearn_ver and manifest_sklearn_ver != current_sklearn_ver:
            # Major/minor compatibility check
            if manifest_sklearn_ver.split(".")[:2] != current_sklearn_ver.split(".")[:2]:
                self.load_error = (
                    f"scikit-learn version mismatch: model was trained on {manifest_sklearn_ver}, "
                    f"but runtime is {current_sklearn_ver}."
                )
                return

        # 2. Load Arrival Model
        if not arrival_path.exists():
            self.load_error = f"Arrival model artifact missing at: {arrival_path}"
            return
        try:
            self.arrival_model = joblib.load(arrival_path)
        except Exception as e:
            self.load_error = f"Failed to deserialize arrival_model.joblib: {e}"
            return

        # 3. Load Energy Model
        if not energy_path.exists():
            self.load_error = f"Energy model artifact missing at: {energy_path}"
            return
        try:
            self.energy_model = joblib.load(energy_path)
        except Exception as e:
            self.load_error = f"Failed to deserialize energy_model.joblib: {e}"
            return

        # 4. Verify Feature Alignment
        expected_features = self.manifest.get("feature_names", [])
        if self.arrival_model.feature_names_ != expected_features:
            self.load_error = "Arrival model feature names do not match manifest feature definitions."
            return
        if self.energy_model.feature_names_ != expected_features:
            self.load_error = "Energy model feature names do not match manifest feature definitions."
            return

        # 5. Sanity Inference Check
        dummy_row = pd.DataFrame([{feat: 0.0 for feat in expected_features}])
        try:
            arr_pred = self.arrival_model.predict(dummy_row)
            ene_pred = self.energy_model.predict(dummy_row)
            if len(arr_pred) != 1 or len(ene_pred) != 1:
                self.load_error = "Sanity inference returned invalid prediction shape."
                return
        except Exception as e:
            self.load_error = f"Sanity test inference failed: {e}"
            return

        self.is_loaded = True
        self.load_error = None

    def get_models(self) -> tuple[RandomForestDemandModel, RandomForestDemandModel, Dict[str, Any]]:
        if not self.is_loaded:
            raise ModelArtifactError(self.load_error or "Model artifacts are not loaded.")
        return self.arrival_model, self.energy_model, self.manifest
