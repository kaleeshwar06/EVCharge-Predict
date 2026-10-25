"""Strict chronological time-series train/validation/test splitting."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Tuple
import pandas as pd


@dataclass
class SplitWindow:
    name: str
    start_time: datetime
    end_time: datetime
    row_count: int


@dataclass
class ChronologicalSplit:
    train_df: pd.DataFrame
    val_df: pd.DataFrame
    test_df: pd.DataFrame
    train_window: SplitWindow
    val_window: SplitWindow
    test_window: SplitWindow


def chronological_split(
    df: pd.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
) -> ChronologicalSplit:
    """Splits dataset on strict chronological time boundaries across all stations.

    Boundary rule:
    - Train: [min_time, t_val_start)
    - Validation: [t_val_start, t_test_start)
    - Test: [t_test_start, max_time]
    """
    if df.empty:
        raise ValueError("Cannot split an empty dataframe")

    unique_times = sorted(df["interval_start"].unique())
    n_times = len(unique_times)

    if n_times < 10:
        raise ValueError(f"Insufficient unique time periods for chronological split: {n_times} (minimum 10 required)")

    train_end_idx = int(n_times * train_ratio)
    val_end_idx = int(n_times * (train_ratio + val_ratio))

    # Ensure each set has at least 1 timestamp
    train_end_idx = max(1, min(train_end_idx, n_times - 2))
    val_end_idx = max(train_end_idx + 1, min(val_end_idx, n_times - 1))

    t_val_start = unique_times[train_end_idx]
    t_test_start = unique_times[val_end_idx]

    train_mask = df["interval_start"] < t_val_start
    val_mask = (df["interval_start"] >= t_val_start) & (df["interval_start"] < t_test_start)
    test_mask = df["interval_start"] >= t_test_start

    train_df = df[train_mask].copy()
    val_df = df[val_mask].copy()
    test_df = df[test_mask].copy()

    train_w = SplitWindow("train", train_df["interval_start"].min(), train_df["interval_start"].max(), len(train_df))
    val_w = SplitWindow("validation", val_df["interval_start"].min(), val_df["interval_start"].max(), len(val_df))
    test_w = SplitWindow("test", test_df["interval_start"].min(), test_df["interval_start"].max(), len(test_df))

    return ChronologicalSplit(
        train_df=train_df,
        val_df=val_df,
        test_df=test_df,
        train_window=train_w,
        val_window=val_w,
        test_window=test_w,
    )
