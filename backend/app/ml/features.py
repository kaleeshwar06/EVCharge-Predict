"""Temporal feature engineering without future data leakage."""
from __future__ import annotations

from typing import List, Tuple
import numpy as np
import pandas as pd


class FeatureEngineer:
    """Computes strictly past-only features for hourly demand forecasting."""

    LAG_HOURS = [1, 2, 3, 6, 12, 24, 48, 168]
    ROLLING_WINDOWS = [6, 24, 168]

    @classmethod
    def get_feature_names(cls) -> List[str]:
        """Return canonical list of feature columns."""
        names = [
            "hour",
            "dayofweek",
            "is_weekend",
            "sin_hour",
            "cos_hour",
            "sin_dayofweek",
            "cos_dayofweek",
        ]
        for lag in cls.LAG_HOURS:
            names.append(f"lag_arrivals_{lag}h")
            names.append(f"lag_energy_{lag}h")
        for window in cls.ROLLING_WINDOWS:
            names.append(f"rolling_arrivals_{window}h_mean")
            names.append(f"rolling_energy_{window}h_mean")
        names.append("station_code")
        return names

    @classmethod
    def create_features(
        cls,
        hourly_df: pd.DataFrame,
        station_encoder: dict[str, int] | None = None,
        drop_na_lags: bool = True,
    ) -> Tuple[pd.DataFrame, dict[str, int]]:
        """Constructs temporal and past-only autoregressive features per station."""
        if hourly_df.empty:
            return pd.DataFrame(), station_encoder or {}

        df = hourly_df.copy()
        df["interval_start"] = pd.to_datetime(df["interval_start"], utc=True)
        df = df.sort_values(by=["station_id", "interval_start"]).reset_index(drop=True)

        # 1. Calendar Features (Known in advance for interval t)
        dt_col = df["interval_start"]
        df["hour"] = dt_col.dt.hour
        df["dayofweek"] = dt_col.dt.dayofweek
        df["is_weekend"] = (df["dayofweek"] >= 5).astype(int)

        # Cyclical Encodings
        df["sin_hour"] = np.sin(2 * np.pi * df["hour"] / 24.0)
        df["cos_hour"] = np.cos(2 * np.pi * df["hour"] / 24.0)
        df["sin_dayofweek"] = np.sin(2 * np.pi * df["dayofweek"] / 7.0)
        df["cos_dayofweek"] = np.cos(2 * np.pi * df["dayofweek"] / 7.0)

        # 2. Station Categorical Code
        if station_encoder is None:
            unique_stations = sorted(df["station_id"].unique().tolist())
            station_encoder = {st: idx for idx, st in enumerate(unique_stations)}
        df["station_code"] = df["station_id"].map(station_encoder).fillna(-1).astype(int)

        # 3. Station-grouped Lags & Rolling Statistics
        # Shift(1) guarantees that for interval t, only observations prior to t are included
        station_dfs = []
        for st_id, group in df.groupby("station_id"):
            g = group.sort_values(by="interval_start").copy()

            # Lags
            for lag in cls.LAG_HOURS:
                g[f"lag_arrivals_{lag}h"] = g["arrivals"].shift(lag)
                g[f"lag_energy_{lag}h"] = g["session_start_energy_kwh"].shift(lag)

            # Rolling window statistics (closed='left' or shift(1) ensuring past-only)
            # Using shift(1) then rolling window ensures interval t's target is never seen
            past_arr = g["arrivals"].shift(1)
            past_ene = g["session_start_energy_kwh"].shift(1)

            for window in cls.ROLLING_WINDOWS:
                g[f"rolling_arrivals_{window}h_mean"] = past_arr.rolling(window=window, min_periods=1).mean()
                g[f"rolling_energy_{window}h_mean"] = past_ene.rolling(window=window, min_periods=1).mean()

            station_dfs.append(g)

        result_df = pd.concat(station_dfs, ignore_index=True)
        result_df = result_df.sort_values(by=["interval_start", "station_id"]).reset_index(drop=True)

        if drop_na_lags:
            # If historical window is shorter than 168h (e.g. synthetic test), drop rows where lag_1h is NaN
            # and backfill larger lags with nearest available lag to preserve dataset size
            result_df = result_df.dropna(subset=["lag_arrivals_1h"]).copy()
            for lag in cls.LAG_HOURS:
                result_df[f"lag_arrivals_{lag}h"] = result_df[f"lag_arrivals_{lag}h"].fillna(result_df["lag_arrivals_1h"])
                result_df[f"lag_energy_{lag}h"] = result_df[f"lag_energy_{lag}h"].fillna(result_df["lag_energy_1h"])

        return result_df, station_encoder
