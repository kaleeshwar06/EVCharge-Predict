"""Baseline and Random Forest regression model implementations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error


@dataclass
class MetricScores:
    mae: float
    rmse: float
    sample_count: int


@dataclass
class ModelEvaluationReport:
    target_name: str
    target_unit: str
    baseline_val: MetricScores
    baseline_test: MetricScores
    rf_val: MetricScores
    rf_test: MetricScores
    rf_outperformed_baseline: bool
    per_station_test: Dict[str, Dict[str, float]]


class HistoricalAverageBaseline:
    """Historical average baseline predictor calculated strictly from past observations.

    Strategy:
    Predicts using the historical mean for (station_id, dayofweek, hour) computed over the training set.
    Falls back to station mean, then global training mean if unobserved.
    """

    def __init__(self, target_col: str) -> None:
        self.target_col = target_col
        self.global_mean: float = 0.0
        self.station_means: Dict[str, float] = {}
        self.cell_means: Dict[tuple[str, int, int], float] = {}

    def fit(self, train_df: pd.DataFrame) -> "HistoricalAverageBaseline":
        if train_df.empty:
            return self

        self.global_mean = float(train_df[self.target_col].mean())
        self.station_means = train_df.groupby("station_id")[self.target_col].mean().to_dict()

        cell_group = train_df.groupby(["station_id", "dayofweek", "hour"])[self.target_col].mean()
        self.cell_means = cell_group.to_dict()
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        preds = []
        for _, row in df.iterrows():
            st = row["station_id"]
            dow = int(row["dayofweek"])
            hr = int(row["hour"])
            key = (st, dow, hr)

            if key in self.cell_means:
                val = self.cell_means[key]
            elif st in self.station_means:
                val = self.station_means[st]
            else:
                val = self.global_mean
            preds.append(max(0.0, float(val)))
        return np.array(preds)


class RandomForestDemandModel:
    """Random Forest regressor with nonnegative output constraints."""

    def __init__(
        self,
        target_col: str,
        n_estimators: int = 100,
        max_depth: Optional[int] = 12,
        min_samples_split: int = 5,
        random_state: int = 42,
    ) -> None:
        self.target_col = target_col
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.random_state = random_state
        self.model = RandomForestRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_split=self.min_samples_split,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self.feature_names_: List[str] = []

    def fit(self, train_df: pd.DataFrame, feature_cols: List[str]) -> "RandomForestDemandModel":
        self.feature_names_ = feature_cols
        X = train_df[self.feature_names_]
        y = train_df[self.target_col]
        self.model.fit(X, y)
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        X = df[self.feature_names_]
        preds = self.model.predict(X)
        # Enforce nonnegative lower bound
        return np.clip(preds, a_min=0.0, a_max=None)


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> MetricScores:
    """Calculate MAE and RMSE metrics."""
    if len(y_true) == 0:
        return MetricScores(mae=0.0, rmse=0.0, sample_count=0)
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(root_mean_squared_error(y_true, y_pred))
    return MetricScores(mae=round(mae, 4), rmse=round(rmse, 4), sample_count=len(y_true))
