import React, { useState, useEffect } from "react";
import {
  MessageSquare,
  Search,
  Filter,
  RefreshCw,
  Eye,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";
import {
  FeedbackDetailRead,
  fetchFeedbackHistory,
  ApiError,
} from "../api";
import SourceBadge from "./SourceBadge";

interface Props {
  demoMode: boolean;
  scenarioFeedbacks: FeedbackDetailRead[];
  onInspectAdjustedDemand?: (forecastId: string, feedbackId: string) => void;
}

export const FeedbackHistory: React.FC<Props> = ({
  demoMode,
  scenarioFeedbacks,
  onInspectAdjustedDemand,
}) => {
  const [feedbackList, setFeedbackList] = useState<FeedbackDetailRead[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [filterText, setFilterText] = useState<string>("");
  const [selectedFeedbackId, setSelectedFeedbackId] = useState<string | null>(null);

  const loadBackendFeedback = async () => {
    if (demoMode) return;
    setLoading(true);
    setError(null);
    try {
      const records = await fetchFeedbackHistory();
      setFeedbackList(records);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError(
            "Authentication required (HTTP 401). Saved feedback history on the production backend requires a service Bearer token. Optimizer feedback submissions evaluated in this session are listed in Registered Network Mode."
          );
        } else {
          setError(`Failed to retrieve feedback history (${err.status}): ${err.message}`);
        }
      } else {
        setError(`Network error: ${String(err)}`);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadBackendFeedback();
  }, [demoMode]);

  const activeRecords = demoMode ? scenarioFeedbacks : feedbackList;
  const filteredRecords = activeRecords.filter(
    (r) =>
      r.feedback_id.toLowerCase().includes(filterText.toLowerCase()) ||
      r.allocation_run_id.toLowerCase().includes(filterText.toLowerCase()) ||
      r.forecast_id.toLowerCase().includes(filterText.toLowerCase()) ||
      r.scenario_id.toLowerCase().includes(filterText.toLowerCase())
  );

  const handleInspect = (item: FeedbackDetailRead) => {
    setSelectedFeedbackId(item.feedback_id);
    if (onInspectAdjustedDemand) {
      onInspectAdjustedDemand(item.forecast_id, item.feedback_id);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center">
            <MessageSquare className="w-5 h-5 mr-2 text-indigo-400" />
            Optimizer Feedback History & Coordination
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            {demoMode
              ? "Archived allocation feedback records submitted by EVCharge-Opt during this session"
              : "Authoritative allocation feedback received by the backend from EVCharge-Opt"}
          </p>
        </div>
        <div className="flex items-center space-x-3">
          <SourceBadge source={demoMode ? "demo" : "live"} />
          {!demoMode && (
            <button
              onClick={loadBackendFeedback}
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
            placeholder="Search by Feedback ID, Allocation Run ID, or Forecast ID..."
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
              <strong>Service-to-Service Contract:</strong> <code>GET /api/v1/feedback</code> requires a valid Bearer token configured between EVCharge-Predict and EVCharge-Opt.
            </div>
            <div>
              Use <strong>Registered Network Mode</strong> to test optimizer allocations and operational demand envelopes interactively.
            </div>
          </div>
        </div>
      )}

      {/* Empty State */}
      {filteredRecords.length === 0 && !loading && !error && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center text-slate-400">
          <MessageSquare className="w-10 h-10 mx-auto mb-3 text-slate-600" />
          <h3 className="text-base font-semibold text-white mb-1">No Feedback Records Found</h3>
          <p className="text-xs max-w-md mx-auto mb-4">
            {demoMode
              ? "No feedback submissions have been processed yet. Submit an allocation in the Feedback tab to generate an entry."
              : "No feedback submissions currently match the query in the backend database."}
          </p>
        </div>
      )}

      {/* Feedback Table */}
      {filteredRecords.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 font-medium bg-slate-950/40 text-xs uppercase tracking-wider">
                  <th className="py-3 px-4">Feedback ID</th>
                  <th className="py-3 px-4">Allocation Run ID</th>
                  <th className="py-3 px-4">Forecast Reference</th>
                  <th className="py-3 px-4">Scenario</th>
                  <th className="py-3 px-4">Submitted (UTC)</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-200 text-xs">
                {filteredRecords.map((item) => (
                  <tr
                    key={item.feedback_id}
                    className={`hover:bg-slate-800/40 transition-colors ${
                      selectedFeedbackId === item.feedback_id ? "bg-indigo-950/30" : ""
                    }`}
                  >
                    <td className="py-3.5 px-4 font-mono font-semibold text-indigo-400">
                      {item.feedback_id}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-amber-400">
                      {item.allocation_run_id}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-300">
                      {item.forecast_id}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-400">
                      {item.scenario_id}
                    </td>
                    <td className="py-3.5 px-4 text-slate-400 font-mono text-[11px]">
                      {new Date(item.submitted_at).toLocaleString()}
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 className="w-3 h-3 mr-1" />
                        {item.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={() => handleInspect(item)}
                        className="px-3 py-1.5 bg-indigo-600/80 hover:bg-indigo-600 text-white rounded-lg text-xs font-medium inline-flex items-center transition-colors"
                      >
                        <Eye className="w-3.5 h-3.5 mr-1" /> View Ingestion
                      </button>
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

export default FeedbackHistory;
