import React, { useState } from "react";
import {
  FeedbackCreateRequest,
  submitFeedback,
  ApiError,
  fetchAdjustedDemand,
  ForecastDetailRead,
  AdjustedDemandResponse,
} from "../api";
import { MessageSquare, CheckCircle2, AlertTriangle, ArrowRight, Zap } from "lucide-react";

interface Props {
  demoMode: boolean;
  forecast?: ForecastDetailRead | null;
  onAdjustedDemand?: (data: AdjustedDemandResponse) => void;
}

const FeedbackForm: React.FC<Props> = ({ demoMode, forecast, onAdjustedDemand }) => {
  const [allocationRunId, setAllocationRunId] = useState<string>("opt_run_" + Date.now().toString().slice(-6));
  const [curtailmentPercent, setCurtailmentPercent] = useState<number>(10);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (demoMode) {
      setError("Feedback ingestion is disabled while Demo Mode is active.");
      return;
    }
    if (!forecast || !forecast.stations || forecast.stations.length === 0) {
      setError("Please generate a forecast first (in the Forecast tab) so optimizer feedback can align to its intervals.");
      return;
    }

    // Build contract-compliant feedback matching the forecast intervals
    const factor = 1 - curtailmentPercent / 100;
    const feedbackStations = forecast.stations.map((st) => ({
      station_id: st.station_id,
      intervals: st.intervals.map((intv) => {
        const allocated = Math.round(intv.predicted_energy_kwh * factor * 1000) / 1000;
        const unmet = Math.max(0, Math.round((intv.predicted_energy_kwh - allocated) * 1000) / 1000);
        return {
          interval_start: intv.interval_start,
          interval_end: intv.interval_end,
          allocated_energy_kwh: allocated,
          available_capacity_kw: 50.0,
          reported_unmet_demand_kwh: unmet,
        };
      }),
    }));

    const req: FeedbackCreateRequest = {
      contract_version: "1.0",
      allocation_run_id: allocationRunId.trim(),
      forecast_id: forecast.forecast_id,
      scenario_id: forecast.scenario_id,
      submitted_at: new Date().toISOString(),
      optimizer_version: "opt-core-2.4.1",
      stations: feedbackStations,
    };

    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const resp = await submitFeedback(req);
      setSuccess(
        `Feedback successfully ingested (ID: ${resp.feedback_id}, Status: ${resp.status}${
          resp.is_duplicate ? " - Idempotent Duplicate" : ""
        })`
      );
      if (onAdjustedDemand) {
        const adj = await fetchAdjustedDemand(forecast.forecast_id, resp.feedback_id);
        onAdjustedDemand(adj);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        try {
          const parsed = JSON.parse(err.message);
          setError(typeof parsed.detail === "string" ? parsed.detail : err.message);
        } catch {
          setError(`${err.status}: ${err.message}`);
        }
      } else {
        setError(String(err));
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (demoMode) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-slate-400">
        <p className="text-sm">Demo mode active — optimizer feedback submission is disabled.</p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-slate-200 space-y-5">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center space-x-2">
          <MessageSquare className="w-5 h-5 text-indigo-400" />
          <h3 className="font-semibold text-white">Post-Optimization Feedback Ingestion</h3>
        </div>
        {forecast && (
          <span className="text-xs bg-slate-950 px-2.5 py-1 rounded border border-slate-800 text-slate-400 font-mono">
            Linked to: <strong className="text-emerald-400">{forecast.forecast_id}</strong>
          </span>
        )}
      </div>

      {!forecast && (
        <div className="p-3.5 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs text-amber-300">
          ⚠️ No active forecast detected. Please go to the <strong>Forecast</strong> tab and generate a forecast first, so feedback intervals align to real forecast targets.
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">Allocation Run ID (Unique Idempotency Key):</label>
          <input
            type="text"
            value={allocationRunId}
            onChange={(e) => setAllocationRunId(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-sm font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
            required
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">
            Simulated Grid Curtailment Directive:
          </label>
          <select
            value={curtailmentPercent}
            onChange={(e) => setCurtailmentPercent(parseInt(e.target.value, 10))}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            <option value={0}>0% Curtailment (Full dispatch)</option>
            <option value={10}>10% Curtailment (Peak shaving)</option>
            <option value={20}>20% Curtailment (Grid constraint)</option>
            <option value={30}>30% Curtailment (Emergency DR)</option>
          </select>
        </div>
      </div>

      {forecast && (
        <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800/80 text-xs text-slate-400 space-y-1">
          <div className="flex items-center text-slate-300 font-medium">
            <Zap className="w-3.5 h-3.5 mr-1 text-emerald-400" /> Contract Schema Validation:
          </div>
          <div>Originating Scenario: <strong className="text-white font-mono">{forecast.scenario_id}</strong></div>
          <div>Target Stations: <strong className="text-white font-mono">{forecast.stations.map((s) => s.station_id).join(", ")}</strong></div>
          <div>Aligned Intervals: <strong className="text-white font-mono">{forecast.stations[0]?.intervals.length || 0} consecutive hours</strong></div>
        </div>
      )}

      {error && (
        <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-xs text-red-300 flex items-center">
          <AlertTriangle className="w-4 h-4 mr-2 text-red-400 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-xs text-emerald-300 flex items-center">
          <CheckCircle2 className="w-4 h-4 mr-2 text-emerald-400 flex-shrink-0" />
          <span>{success}</span>
        </div>
      )}

      <button
        type="submit"
        disabled={submitting || !forecast}
        className="w-full sm:w-auto bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold py-2 px-6 rounded-lg transition-colors flex items-center justify-center space-x-2"
      >
        <span>{submitting ? "Ingesting Feedback..." : "Submit Allocation Feedback"}</span>
        <ArrowRight className="w-4 h-4" />
      </button>
    </form>
  );
};

export default FeedbackForm;
