import { StationRead, ForecastDetailRead, FeedbackCreateResponse, AdjustedDemandResponse, FeedbackCreateRequest, ForecastCreateRequest } from "./api";

export const DEMO_STATIONS: StationRead[] = [
  {
    id: 101,
    station_id: "ST-001",
    source_station_id: "1-39-139-650",
    site_id: "caltech",
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    origin_source: "scenario_catalog",
  },
  {
    id: 102,
    station_id: "ST-002",
    source_station_id: "1-39-139-651",
    site_id: "caltech",
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    origin_source: "scenario_catalog",
  },
  {
    id: 103,
    station_id: "ST-003",
    source_station_id: "provisional-hardware-ST-003",
    site_id: "caltech-provisional",
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    origin_source: "scenario_catalog",
  },
];

export function generateDemoForecast(req: ForecastCreateRequest): ForecastDetailRead {
  const horizon = req.horizon_intervals || 6;
  const intervalMinutes = req.interval_minutes || 60;
  const startDate = new Date(req.forecast_start);

  const stations = req.station_ids.map((stId) => {
    const intervals = [];
    for (let i = 0; i < horizon; i++) {
      const iStart = new Date(startDate.getTime() + i * intervalMinutes * 60000);
      const iEnd = new Date(iStart.getTime() + intervalMinutes * 60000);
      
      // Deterministic synthetic predictions for demo simulation
      const hour = iStart.getUTCHours();
      const isPeak = hour >= 9 && hour <= 17;
      const baseArrivals = isPeak ? 3 : 1;
      const baseKwh = isPeak ? 42.5 : 14.0;

      intervals.push({
        interval_start: iStart.toISOString(),
        interval_end: iEnd.toISOString(),
        predicted_arrivals: baseArrivals,
        predicted_energy_kwh: Number((baseKwh + (i % 3) * 4.2).toFixed(2)),
      });
    }

    return {
      station_id: stId,
      intervals,
    };
  });

  const endDate = new Date(startDate.getTime() + horizon * intervalMinutes * 60000);

  return {
    contract_version: "1.0",
    forecast_id: `fc_demo_${Date.now().toString().slice(-6)}`,
    scenario_id: req.scenario_id,
    generated_at: new Date().toISOString(),
    demand_type: "demo_synthetic_model",
    stations,
    horizon: {
      start: startDate.toISOString(),
      end: endDate.toISOString(),
      interval_minutes: intervalMinutes,
      interval_count: horizon,
    },
  };
}

export function generateDemoFeedback(req: FeedbackCreateRequest): FeedbackCreateResponse {
  return {
    contract_version: "1.0",
    feedback_id: `fb_demo_${Date.now().toString().slice(-6)}`,
    allocation_run_id: req.allocation_run_id,
    forecast_id: req.forecast_id,
    scenario_id: req.scenario_id,
    status: "accepted",
    is_duplicate: false,
    received_at: new Date().toISOString(),
    feedback_url: `/api/v1/forecasts/${req.forecast_id}/adjusted-demand?feedback_id=fb_demo`,
  };
}

export function generateDemoAdjustedDemand(
  forecast: ForecastDetailRead,
  feedbackId: string,
  curtailmentPercent: number = 10
): AdjustedDemandResponse {
  const factor = 1 - curtailmentPercent / 100;

  const stations = forecast.stations.map((st) => ({
    station_id: st.station_id,
    intervals: st.intervals.map((intv) => {
      const allocated = Number((intv.predicted_energy_kwh * factor).toFixed(3));
      const unmet = Number(Math.max(0, intv.predicted_energy_kwh - allocated).toFixed(3));
      return {
        interval_start: intv.interval_start,
        interval_end: intv.interval_end,
        baseline_arrivals: intv.predicted_arrivals,
        baseline_energy_kwh: intv.predicted_energy_kwh,
        allocated_energy_kwh: allocated,
        available_capacity_kw: 50.0,
        reported_unmet_demand_kwh: unmet,
        adjusted_operational_demand_kwh: allocated,
        adjustment_status: "curtailed_by_optimization",
      };
    }),
  }));

  return {
    contract_version: "1.0",
    forecast_id: forecast.forecast_id,
    scenario_id: forecast.scenario_id,
    feedback_id: feedbackId,
    allocation_run_id: `run_opt_${Date.now().toString().slice(-6)}`,
    demand_type: "feedback-adjusted-operational",
    adjustment_policy_version: "v1-heuristic-operational-envelope",
    policy_description: "Operational demand envelope taking max(baseline_predicted_energy_kwh, allocated_energy_kwh)",
    policy_limitations: "Allocated energy reflects optimizer decisions under physical and grid constraints",
    computed_at: new Date().toISOString(),
    stations,
  };
}
