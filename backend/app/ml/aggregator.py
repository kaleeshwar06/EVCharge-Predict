"""Hourly station-level aggregation for EV charging arrivals and energy targets."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
import numpy as np
import pandas as pd


class DemandAggregator:
    """Aggregates discrete charging sessions into regular hourly intervals per station.

    Target Definitions:
    - Target A (arrivals): Count of valid sessions with connection_time in [interval_start, interval_end).
    - Target B (session_start_energy_kwh): Sum of kwh_delivered for sessions starting in the interval.
    """

    @staticmethod
    def aggregate_hourly(
        sessions_df: pd.DataFrame,
        station_filter: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Constructs an unbroken hourly time series for each station across its observed lifespan."""
        if sessions_df.empty:
            return pd.DataFrame(columns=[
                "station_id", "interval_start", "interval_end", "arrivals", "session_start_energy_kwh", "energy_measured_count"
            ])

        df = sessions_df.copy()
        if station_filter:
            df = df[df["station_id"].isin(station_filter)]
            if df.empty:
                return pd.DataFrame(columns=[
                    "station_id", "interval_start", "interval_end", "arrivals", "session_start_energy_kwh", "energy_measured_count"
                ])

        # Floor timestamps to UTC hour: [interval_start, interval_start + 1h)
        df["interval_start"] = pd.to_datetime(df["connection_time"], utc=True).dt.floor("h")

        station_dfs = []
        for st_id, group in df.groupby("station_id"):
            min_hour = group["interval_start"].min()
            max_hour = group["interval_start"].max()

            # Continuous hourly range within station's observation window
            full_hourly_index = pd.date_range(start=min_hour, end=max_hour, freq="1h", tz=timezone.utc, name="interval_start")

            # Aggregate actual events
            # For energy, sum only non-null values
            agg_actual = group.groupby("interval_start").agg(
                arrivals=("session_id", "count"),
                session_start_energy_kwh=("kwh_delivered", "sum"),
                energy_measured_count=("kwh_delivered", lambda s: s.notna().sum()),
            )

            # Reindex to fill unobserved intermediate hours with 0 arrivals & 0 energy
            station_hourly = agg_actual.reindex(full_hourly_index)
            station_hourly["arrivals"] = station_hourly["arrivals"].fillna(0).astype(int)
            station_hourly["session_start_energy_kwh"] = station_hourly["session_start_energy_kwh"].fillna(0.0).astype(float)
            station_hourly["energy_measured_count"] = station_hourly["energy_measured_count"].fillna(0).astype(int)

            station_hourly = station_hourly.reset_index()
            station_hourly["station_id"] = st_id
            station_hourly["interval_end"] = station_hourly["interval_start"] + pd.Timedelta(hours=1)
            station_dfs.append(station_hourly)

        if not station_dfs:
            return pd.DataFrame()

        combined = pd.concat(station_dfs, ignore_index=True)
        # Order chronologically and by station
        combined = combined.sort_values(by=["interval_start", "station_id"]).reset_index(drop=True)
        return combined[[
            "station_id",
            "interval_start",
            "interval_end",
            "arrivals",
            "session_start_energy_kwh",
            "energy_measured_count",
        ]]
