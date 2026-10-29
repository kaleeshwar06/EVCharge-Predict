export interface StationRead {
  id: number;
  station_id: string;
  source_station_id: string;
  site_id?: string | null;
  created_at: string;
  updated_at: string;
  origin_source?: "live" | "scenario_catalog";
}

export interface ForecastCreateRequest {
  scenario_id: string;
  station_ids: string[];
  forecast_start: string; // ISO8601 UTC hour-aligned
  interval_minutes?: number;
  horizon_intervals?: number;
}

export interface ForecastCreateResponse {
  contract_version: string;
  forecast_id: string;
  scenario_id: string;
  status: string;
  demand_type: string;
  generated_at: string;
  interval_minutes: number;
  horizon_intervals: number;
  forecast_url: string;
}

export interface ForecastInterval {
  interval_start: string;
  interval_end: string;
  predicted_arrivals: number;
  predicted_energy_kwh: number;
}

export interface StationForecastRead {
  station_id: string;
  intervals: ForecastInterval[];
}

export interface ForecastDetailRead {
  contract_version: string;
  forecast_id: string;
  scenario_id: string;
  generated_at: string;
  demand_type: string;
  stations: StationForecastRead[];
  horizon: {
    start: string;
    end: string;
    interval_minutes: number;
    interval_count: number;
  };
}

export interface AllocationIntervalInput {
  interval_start: string;
  interval_end: string;
  allocated_energy_kwh?: number;
  available_capacity_kw?: number;
  reported_unmet_demand_kwh?: number;
}

export interface StationAllocationFeedbackInput {
  station_id: string;
  intervals: AllocationIntervalInput[];
}

export interface FeedbackCreateRequest {
  contract_version?: string;
  allocation_run_id: string;
  forecast_id: string;
  scenario_id: string;
  submitted_at: string;
  optimizer_version?: string;
  stations: StationAllocationFeedbackInput[];
}

export interface FeedbackCreateResponse {
  contract_version: string;
  feedback_id: string;
  allocation_run_id: string;
  forecast_id: string;
  scenario_id: string;
  status: string;
  is_duplicate: boolean;
  received_at: string;
  feedback_url: string;
}

export interface AdjustedDemandIntervalRead {
  interval_start: string;
  interval_end: string;
  baseline_arrivals: number;
  baseline_energy_kwh: number;
  allocated_energy_kwh?: number;
  available_capacity_kw?: number;
  reported_unmet_demand_kwh?: number;
  adjusted_operational_demand_kwh: number;
  adjustment_status: string;
}

export interface StationAdjustedDemandRead {
  station_id: string;
  intervals: AdjustedDemandIntervalRead[];
}

export interface AdjustedDemandResponse {
  contract_version: string;
  forecast_id: string;
  scenario_id: string;
  feedback_id: string;
  allocation_run_id: string;
  demand_type: string;
  adjustment_policy_version: string;
  policy_description: string;
  policy_limitations: string;
  computed_at: string;
  stations: StationAdjustedDemandRead[];
}

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// Resolve API base URL:
// 1. Explicit import.meta.env.VITE_API_BASE_URL if configured.
// 2. In production builds (import.meta.env.PROD): default to the deployed backend https://evcharge-predict.onrender.com.
// 3. In local development: default to empty string to use Vite local proxy (/api -> 127.0.0.1:8001).
const configuredBase = import.meta.env.VITE_API_BASE_URL;
export const API_BASE_URL = (
  configuredBase !== undefined && configuredBase !== ""
    ? configuredBase
    : import.meta.env.PROD
    ? "https://evcharge-predict.onrender.com"
    : ""
).replace(/\/+$/, "");

const basePath = `${API_BASE_URL}/api/v1`;

async function request(path: string, options: RequestInit = {}): Promise<any> {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
  };
  // In dev, Vite proxy adds token via server-side proxy; in client direct access, no credentials leaked.
  const resp = await fetch(basePath + path, {
    ...options,
    headers: { ...headers, ...(options.headers || {}) },
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new ApiError(txt || resp.statusText, resp.status);
  }
  return resp.json();
}

export async function fetchStations(): Promise<StationRead[]> {
  return request("/stations", { method: "GET" });
}

export async function createForecast(req: ForecastCreateRequest): Promise<ForecastDetailRead> {
  const created: ForecastCreateResponse = await request("/forecasts", { method: "POST", body: JSON.stringify(req) });
  // Immediately retrieve the complete multi-station forecast detail
  return fetchForecast(created.forecast_id);
}

export async function fetchLatestForecast(scenarioId: string): Promise<ForecastDetailRead> {
  return request(`/forecasts/latest?scenario_id=${encodeURIComponent(scenarioId)}`, { method: "GET" });
}

export async function fetchForecast(id: string): Promise<ForecastDetailRead> {
  return request(`/forecasts/${id}`, { method: "GET" });
}

export async function fetchAdjustedDemand(forecastId: string, feedbackId: string): Promise<AdjustedDemandResponse> {
  return request(`/forecasts/${forecastId}/adjusted-demand?feedback_id=${feedbackId}`, { method: "GET" });
}

export async function submitFeedback(req: FeedbackCreateRequest): Promise<FeedbackCreateResponse> {
  return request("/feedback", { method: "POST", body: JSON.stringify(req) });
}

export interface ForecastSummaryRead {
  contract_version: string;
  forecast_id: string;
  scenario_id: string;
  status: string;
  demand_type: string;
  generated_at: string;
  forecast_start: string;
  forecast_end: string;
  interval_minutes: number;
  horizon_intervals: number;
  station_count: number;
  station_ids: string[];
}

export interface FeedbackDetailRead {
  contract_version: string;
  feedback_id: string;
  allocation_run_id: string;
  forecast_id: string;
  scenario_id: string;
  status: string;
  optimizer_version?: string;
  submitted_at: string;
  received_at: string;
}

export async function fetchForecastHistory(params?: {
  scenario_id?: string;
  station_id?: string;
  limit?: number;
  offset?: number;
}): Promise<ForecastSummaryRead[]> {
  const q = new URLSearchParams();
  if (params?.scenario_id) q.set("scenario_id", params.scenario_id);
  if (params?.station_id) q.set("station_id", params.station_id);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  const queryStr = q.toString() ? `?${q.toString()}` : "";
  return request(`/forecasts${queryStr}`, { method: "GET" });
}

export async function fetchFeedbackHistory(params?: {
  forecast_id?: string;
  scenario_id?: string;
}): Promise<FeedbackDetailRead[]> {
  const q = new URLSearchParams();
  if (params?.forecast_id) q.set("forecast_id", params.forecast_id);
  if (params?.scenario_id) q.set("scenario_id", params.scenario_id);
  const queryStr = q.toString() ? `?${q.toString()}` : "";
  return request(`/feedback${queryStr}`, { method: "GET" });
}

export interface StationAllocationSummary {
  station_id: string;
  station_name: string;
  predicted_arrivals: number;
  predicted_energy_kwh: number;
  estimated_served: number;
  estimated_unserved: number;
  allocated_power_kw: number;
  estimated_wait_minutes: number;
  charger_utilization_pct: number;
  warnings?: string[];
}

export interface PartnerSyncRequest {
  forecast_id: string;
  scenario_id?: string;
  forecast_start?: string;
  station_ids?: string[];
  interval_start?: string;
  interval_end?: string;
  deferred_fraction?: number;
}

export interface PartnerSyncResponse {
  success: boolean;
  partner_service: string;
  partner_base_url: string;
  stage_reached: string;
  opt_forecast_id?: string;
  opt_scenario_id?: string;
  opt_allocation_id?: string;
  opt_feedback_id?: string;
  allocation_status?: string;
  feedback_status?: string;
  total_stations: number;
  total_allocated_power_kw: number;
  total_served_vehicles: number;
  total_unserved_vehicles: number;
  average_wait_minutes: number;
  allocation_results: StationAllocationSummary[];
  feedback_outcomes: any[];
  roundtrip_duration_ms: number;
  error?: string | null;
  correlation_id?: string;
}

export async function syncWithPartner(req: PartnerSyncRequest): Promise<PartnerSyncResponse> {
  return request("/partner/sync", { method: "POST", body: JSON.stringify(req) });
}

export async function fetchPartnerStatus(): Promise<{
  connected: boolean;
  partner_base_url: string;
  http_status?: number;
  partner_details?: any;
  error?: string;
}> {
  return request("/partner/status", { method: "GET" });
}

export { ApiError };
