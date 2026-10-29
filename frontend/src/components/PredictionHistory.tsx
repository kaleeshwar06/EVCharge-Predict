import React, { useState, useEffect } from "react";
import {
  History,
  Clock,
  Search,
  Filter,
  RefreshCw,
  Eye,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";
import {
  ForecastSummaryRead,
  ForecastDetailRead,
  fetchForecastHistory,
  fetchForecast,
  ApiError,
} from "../api";
import SourceBadge from "./SourceBadge";

interface Props {
  demoMode: boolean;
  scenarioForecasts: ForecastDetailRead[];
  onSelectForecast: (forecast: ForecastDetailRead) => void;
}

export const PredictionHistory: React.FC<Props> = ({
  demoMode,
  scenarioForecasts,
  onSelectForecast,
}) => {
  const [historyList, setHistoryList] = useState<ForecastSummaryRead[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [filterText, setFilterText] = useState<string>("");
  const [selectedForecastId, setSelectedForecastId] = useState<string | null>(null);
  const [inspectLoading, setInspectLoading] = useState<boolean>(false);

  const loadBackendHistory = async () => {
    if (demoMode) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const records = await fetchForecastHistory();
      setHistoryList(records);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError(
            "Authentication required (HTTP 401). Saved forecast history on the production backend requires a service Bearer token. Forecasts evaluated during this session are available in Registered Network Mode."
          );
        } else {
          setError(`Failed to retrieve forecast history (${err.status}): ${err.message}`);
        }
      } else {
        setError(`Network error: ${String(err)}`);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadBackendHistory();
  }, [demoMode]);

  const handleInspectBackend = async (forecastId: string) => {
    setSelectedForecastId(forecastId);
    setInspectLoading(true);
    try {
      const detail = await fetchForecast(forecastId);
      onSelectForecast(detail);
    } catch (err) {
      alert(`Could not load forecast details: ${String(err)}`);
    } finally {
      setInspectLoading(false);
    }
  };

  const handleInspectScenario = (item: ForecastDetailRead) => {
    setSelectedForecastId(item.forecast_id);
    onSelectForecast(item);
  };

  // Convert scenario forecasts to summary-like view
  const scenarioSummaries: ForecastSummaryRead[] = scenarioForecasts.map((f) => ({
    contract_version: f.contract_version,
    forecast_id: f.forecast_id,
    scenario_id: f.scenario_id,
    status: "completed",
    demand_type: f.demand_type,
    generated_at: f.generated_at,
    forecast_start: f.horizon.start,
    forecast_end: f.horizon.end,
    interval_minutes: f.horizon.interval_minutes,
    horizon_intervals: f.horizon.interval_count,
    station_count: f.stations.length,
    station_ids: f.stations.map((s) => s.station_id),
  }));

  const activeRecords = demoMode ? scenarioSummaries : historyList;
  const filteredRecords = activeRecords.filter(
    (r) =>
      r.forecast_id.toLowerCase().includes(filterText.toLowerCase()) ||
      r.scenario_id.toLowerCase().includes(filterText.toLowerCase()) ||
      r.station_ids.some((s) => s.toLowerCase().includes(filterText.toLowerCase()))
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center">
            <History className="w-5 h-5 mr-2 text-indigo-400" />
            Prediction History & Forecast Registry
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            {demoMode
              ? "Archived scenario forecasts generated during this session"
              : "Authoritative demand forecasts persisted in the backend database"}
          </p>
        </div>
        <div className="flex items-center space-x-3">
          <SourceBadge source={demoMode ? "demo" : "live"} />
          {!demoMode && (
            <button
              onClick={loadBackendHistory}
              disabled={loading}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded-lg flex items-center transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
          )}
        </div>
      </div>

      {/* Filter / Search Bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="Search by Forecast ID, Scenario ID, or Station (e.g. ST-001)..."
            className="w-full pl-9 pr-4 py-2 bg-slate-900 border border-slate-800 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
          />
        </div>
        <div className="flex items-center text-xs text-slate-400 px-3 bg-slate-900 border border-slate-800 rounded-lg">
          <Filter className="w-3.5 h-3.5 mr-1.5 text-slate-400" />
          <span>{filteredRecords.length} records</span>
        </div>
      </div>

      {/* Backend 401 Notice */}
      {!demoMode && error && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-5 text-amber-200">
          <div className="flex items-center space-x-2 mb-2">
            <AlertCircle className="w-5 h-5 text-amber-400" />
            <h4 className="font-semibold text-amber-100">Live API Authentication Notice</h4>
          </div>
          <p className="text-xs leading-relaxed text-amber-200/90">{error}</p>
          <div className="mt-3 text-xs bg-slate-950/60 p-3 rounded-lg border border-amber-500/20 text-slate-300 space-y-1">
            <div>
              <strong>Why this happens:</strong> The backend <code>GET /api/v1/forecasts</code> route
              is a protected service endpoint reserved for backend orchestration and optimizer
              pipelines.
            </div>
            <div>
              Switch to <strong>Registered Network Mode</strong> in the header toggle to generate,
              archive, and inspect forecasts locally.
            </div>
          </div>
        </div>
      )}

      {/* Empty State */}
      {filteredRecords.length === 0 && !loading && !error && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center text-slate-400">
          <History className="w-10 h-10 mx-auto mb-3 text-slate-600" />
          <h3 className="text-base font-semibold text-white mb-1">No Forecasts Recorded</h3>
          <p className="text-xs max-w-md mx-auto mb-4">
            {demoMode
              ? "No demand forecasts have been executed in this session yet. Navigate to the Forecast tab to run a scenario."
              : "No persisted forecasts match the current query criteria on the live backend database."}
          </p>
        </div>
      )}

      {/* Forecast Table */}
      {filteredRecords.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 font-medium bg-slate-950/40 text-xs uppercase tracking-wider">
                  <th className="py-3 px-4">Forecast ID</th>
                  <th className="py-3 px-4">Scenario</th>
                  <th className="py-3 px-4">Stations</th>
                  <th className="py-3 px-4">Horizon Window</th>
                  <th className="py-3 px-4">Generated (UTC)</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-200 text-xs">
                {filteredRecords.map((item) => (
                  <tr
                    key={item.forecast_id}
                    className={`hover:bg-slate-800/40 transition-colors ${
                      selectedForecastId === item.forecast_id ? "bg-indigo-950/30" : ""
                    }`}
                  >
                    <td className="py-3.5 px-4 font-mono font-semibold text-indigo-400">
                      {item.forecast_id}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-300">
                      {item.scenario_id}
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="flex flex-wrap gap-1">
                        {item.station_ids.map((st) => (
                          <span
                            key={st}
                            className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 font-mono text-[11px] text-slate-300"
                          >
                            {st}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-3.5 px-4 text-slate-400">
                      <div className="flex items-center space-x-1">
                        <Clock className="w-3.5 h-3.5 text-slate-500" />
                        <span>
                          {item.horizon_intervals}h ({item.interval_minutes}m intervals)
                        </span>
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5 font-mono">
                        {new Date(item.forecast_start).toLocaleDateString()} -{" "}
                        {new Date(item.forecast_end).toLocaleDateString()}
                      </div>
                    </td>
                    <td className="py-3.5 px-4 text-slate-400 font-mono text-[11px]">
                      {new Date(item.generated_at).toLocaleString()}
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 className="w-3 h-3 mr-1" />
                        {item.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      {demoMode ? (
                        <button
                          onClick={() => {
                            const found = scenarioForecasts.find(
                              (x) => x.forecast_id === item.forecast_id
                            );
                            if (found) handleInspectScenario(found);
                          }}
                          className="px-3 py-1.5 bg-indigo-600/80 hover:bg-indigo-600 text-white rounded-lg text-xs font-medium inline-flex items-center transition-colors"
                        >
                          <Eye className="w-3.5 h-3.5 mr-1" /> Inspect
                        </button>
                      ) : (
                        <button
                          onClick={() => handleInspectBackend(item.forecast_id)}
                          disabled={inspectLoading && selectedForecastId === item.forecast_id}
                          className="px-3 py-1.5 bg-indigo-600/80 hover:bg-indigo-600 text-white rounded-lg text-xs font-medium inline-flex items-center transition-colors disabled:opacity-50"
                        >
                          <Eye className="w-3.5 h-3.5 mr-1" /> Inspect
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default PredictionHistory;
