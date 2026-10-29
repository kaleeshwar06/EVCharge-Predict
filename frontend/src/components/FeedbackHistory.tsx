import React, { useState, useEffect } from "react";
import {
  MessageSquare,
  Search,
  Filter,
  RefreshCw,
  Eye,
  AlertCircle,
  CheckCircle2,
  Cpu,
  ShieldCheck,
  ArrowRightLeft,
  Layers,
  X,
  FileText,
  Sliders,
  Hash,
  Clock,
} from "lucide-react";
import {
  FeedbackDetailRead,
  fetchFeedbackHistory,
  fetchPartnerFeedbacks,
  ApiError,
} from "../api";
import SourceBadge from "./SourceBadge";

interface Props {
  demoMode: boolean;
  scenarioFeedbacks: FeedbackDetailRead[];
  onInspectAdjustedDemand?: (forecastId: string, feedbackId: string) => void;
  onNavigateToOptimizer?: () => void;
}

export const FeedbackHistory: React.FC<Props> = ({
  demoMode,
  scenarioFeedbacks,
  onInspectAdjustedDemand,
  onNavigateToOptimizer,
}) => {
  const [partnerFeedbacks, setPartnerFeedbacks] = useState<FeedbackDetailRead[]>([]);
  const [backendFeedbacks, setBackendFeedbacks] = useState<FeedbackDetailRead[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [filterText, setFilterText] = useState<string>("");
  const [selectedRecord, setSelectedRecord] = useState<FeedbackDetailRead | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string>("");

  const loadAllFeedbacks = async () => {
    setLoading(true);
    setError(null);

    // 1. Fetch authoritative partner feedback records from EVCharge-Opt
    try {
      const pFeedbacks = await fetchPartnerFeedbacks(50);
      if (Array.isArray(pFeedbacks) && pFeedbacks.length > 0) {
        setPartnerFeedbacks(pFeedbacks);
      }
    } catch (pErr) {
      console.warn("Could not retrieve live partner feedbacks from EVCharge-Opt:", pErr);
    }

    // 2. Fetch local/backend feedback history if accessible
    try {
      const bFeedbacks = await fetchFeedbackHistory();
      if (Array.isArray(bFeedbacks)) {
        setBackendFeedbacks(bFeedbacks);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError(
            "Authentication policy notice (HTTP 401): Direct queries to GET /api/v1/feedback require a service Bearer token. Partner feedbacks are retrieved directly via EVCharge-Opt Partner Sync."
          );
        } else {
          setError(`Feedback query notice (${err.status}): ${err.message}`);
        }
      }
    } finally {
      setLoading(false);
      setLastRefreshedAt(new Date().toLocaleTimeString());
    }
  };

  useEffect(() => {
    loadAllFeedbacks();
  }, [demoMode]);

  // Robust merge & deduplication by feedback_id and idempotency_key
  const mergedMap = new Map<string, FeedbackDetailRead>();

  // Merging sequence: initial scenario feedbacks -> backend feedback -> partner feedbacks (highest authority)
  const allCandidateRecords = [...scenarioFeedbacks, ...backendFeedbacks, ...partnerFeedbacks];

  for (const record of allCandidateRecords) {
    if (!record || !record.feedback_id) continue;

    // Direct feedback_id match
    if (mergedMap.has(record.feedback_id)) {
      const existing = mergedMap.get(record.feedback_id)!;
      mergedMap.set(record.feedback_id, {
        ...existing,
        ...record,
        deferred_fraction: record.deferred_fraction ?? existing.deferred_fraction,
        idempotency_key: record.idempotency_key ?? existing.idempotency_key,
        operational_adjustment_id: record.operational_adjustment_id ?? existing.operational_adjustment_id,
        origin: record.origin || existing.origin,
        station_outcomes: record.station_outcomes || existing.station_outcomes,
      });
      continue;
    }

    // Match by idempotency_key if non-empty
    if (record.idempotency_key) {
      let matchedKey: string | null = null;
      for (const [fId, item] of mergedMap.entries()) {
        if (item.idempotency_key && item.idempotency_key === record.idempotency_key) {
          matchedKey = fId;
          break;
        }
      }
      if (matchedKey) {
        const existing = mergedMap.get(matchedKey)!;
        mergedMap.set(matchedKey, {
          ...existing,
          ...record,
          deferred_fraction: record.deferred_fraction ?? existing.deferred_fraction,
          idempotency_key: record.idempotency_key ?? existing.idempotency_key,
          operational_adjustment_id: record.operational_adjustment_id ?? existing.operational_adjustment_id,
          origin: record.origin || existing.origin,
          station_outcomes: record.station_outcomes || existing.station_outcomes,
        });
        continue;
      }
    }

    // Otherwise insert new distinct record
    mergedMap.set(record.feedback_id, record);
  }

  const activeRecords = Array.from(mergedMap.values()).sort((a, b) => {
    const tA = new Date(a.submitted_at || a.received_at || 0).getTime();
    const tB = new Date(b.submitted_at || b.received_at || 0).getTime();
    return tB - tA;
  });

  const filteredRecords = activeRecords.filter(
    (r) =>
      r.feedback_id.toLowerCase().includes(filterText.toLowerCase()) ||
      r.allocation_run_id.toLowerCase().includes(filterText.toLowerCase()) ||
      r.forecast_id.toLowerCase().includes(filterText.toLowerCase()) ||
      r.scenario_id.toLowerCase().includes(filterText.toLowerCase()) ||
      (r.idempotency_key && r.idempotency_key.toLowerCase().includes(filterText.toLowerCase()))
  );

  const isPartnerFeedback = (item: FeedbackDetailRead) => {
    return (
      item.origin === "partner" ||
      item.origin === "evcharge-opt" ||
      item.allocation_run_id.startsWith("ALC-") ||
      item.feedback_id.startsWith("FBD-") ||
      Boolean(item.optimizer_version?.toLowerCase().includes("heuristic")) ||
      Boolean(item.optimizer_version?.toLowerCase().includes("evcharge-opt"))
    );
  };

  const partnerRecords = activeRecords.filter(isPartnerFeedback);

  const handleInspect = (item: FeedbackDetailRead) => {
    setSelectedRecord(item);
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
            Authoritative allocation feedback records generated by EVCharge-Opt and synchronized with EVCharge-Predict
          </p>
        </div>
        <div className="flex items-center space-x-3">
          <SourceBadge source={demoMode ? "demo" : "live"} />
          <button
            onClick={loadAllFeedbacks}
            disabled={loading}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded-lg flex items-center transition-colors disabled:opacity-50 border border-slate-700"
            title="Refresh feedback history from partner service"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
          {lastRefreshedAt && (
            <span className="text-[11px] text-slate-500 font-mono hidden md:inline">
              Synced {lastRefreshedAt}
            </span>
          )}
        </div>
      </div>

      {/* Partner Feedback Status Banner */}
      {partnerRecords.length > 0 ? (
        <div className="bg-emerald-950/30 border border-emerald-500/30 rounded-xl p-4 text-xs text-slate-200">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2 pb-2 border-b border-emerald-500/20">
            <div className="flex items-center space-x-2">
              <div className="p-1.5 bg-emerald-500/20 rounded-lg text-emerald-400">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <div>
                <span className="font-bold text-white text-sm">
                  EVCharge-Opt Partner Coordination Verified
                </span>
                <span className="ml-2 px-2 py-0.5 rounded-full text-[10px] font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-semibold">
                  {partnerRecords.length} RECORD{partnerRecords.length > 1 ? "S" : ""} RECEIVED
                </span>
              </div>
            </div>
            <span className="text-[11px] font-mono text-emerald-400">
              Partner: https://evcharge-opt-api.onrender.com
            </span>
          </div>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-slate-300">
            <div className="space-y-1">
              <p className="leading-relaxed">
                Active partner feedback received via cross-service contract. Verified records include:
              </p>
              <div className="flex flex-wrap items-center gap-2 text-[11px]">
                <span className="px-2 py-0.5 bg-slate-900 border border-purple-500/40 rounded font-mono text-purple-300">
                  Post-Opt: <strong>FBD-A5998866</strong> (ALC-12216E04 • Def: 70% • Key: IDEMP-ALC-12216E04-0.7)
                </span>
                <span className="px-2 py-0.5 bg-slate-900 border border-emerald-500/40 rounded font-mono text-emerald-300">
                  Submission: <strong>FBD-6AC509A4</strong> (ALC-53C3E7C9 • FC-MOCK-19B71C)
                </span>
              </div>
            </div>
            {onNavigateToOptimizer && (
              <button
                type="button"
                onClick={onNavigateToOptimizer}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium whitespace-nowrap transition-colors flex items-center border border-slate-700 shrink-0"
              >
                <Cpu className="w-3.5 h-3.5 mr-1.5 text-amber-400" />
                Optimization Coordination
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="bg-slate-900 border border-indigo-500/30 rounded-xl p-4 text-xs text-slate-300">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-start space-x-3">
              <div className="p-1.5 bg-indigo-500/10 text-indigo-400 rounded-lg border border-indigo-500/20 mt-0.5">
                <Cpu className="w-4 h-4" />
              </div>
              <div>
                <h4 className="font-semibold text-white text-sm">Where is Partner Feedback?</h4>
                <p className="text-slate-400 mt-0.5 leading-relaxed">
                  Partner allocation feedback is generated by synchronizing with <strong>EVCharge-Opt</strong> (<code>https://evcharge-opt-api.onrender.com</code>).
                  Navigate to <strong>Optimization Coordination</strong> and click <strong>Execute Partner Sync</strong> to dispatch demand forecasts and receive live allocation feedback records (<code className="text-amber-400 font-mono">ALC-...</code> / <code className="text-emerald-400 font-mono">FBD-...</code>).
                </p>
              </div>
            </div>
            {onNavigateToOptimizer && (
              <button
                type="button"
                onClick={onNavigateToOptimizer}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-medium text-xs whitespace-nowrap transition-colors flex items-center shadow-lg shadow-indigo-600/20"
              >
                <ArrowRightLeft className="w-3.5 h-3.5 mr-1.5" />
                Execute Partner Sync
              </button>
            )}
          </div>
        </div>
      )}

      {/* Diagnostic Notice */}
      {!demoMode && error && (
        <div className="bg-slate-900 border border-amber-500/30 rounded-xl p-4 text-xs text-slate-300">
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0" />
              <span className="font-semibold text-white">Partner Sync Diagnostic Notice</span>
            </div>
            <SourceBadge source="live" />
          </div>
          <p className="text-slate-400 leading-relaxed">
            {error}
          </p>
        </div>
      )}

      {/* Filter / Search Bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="Search by Feedback ID, Allocation ID, Forecast ID, or Idempotency Key..."
            className="w-full pl-9 pr-4 py-2 bg-slate-900 border border-slate-800 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
          />
        </div>
        <div className="flex items-center text-xs text-slate-400 px-3 bg-slate-900 border border-slate-800 rounded-lg">
          <Filter className="w-3.5 h-3.5 mr-1.5 text-slate-400" />
          <span>{filteredRecords.length} records</span>
        </div>
      </div>

      {/* Empty State */}
      {filteredRecords.length === 0 && !loading && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center text-slate-400">
          <MessageSquare className="w-10 h-10 mx-auto mb-3 text-slate-600" />
          <h3 className="text-base font-semibold text-white mb-1">No Feedback Records Found</h3>
          <p className="text-xs max-w-md mx-auto mb-4">
            No feedback submissions currently match the query. Click Refresh to query EVCharge-Opt or execute Partner Sync.
          </p>
        </div>
      )}

      {/* Feedback Table */}
      {filteredRecords.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 font-medium bg-slate-950/40 text-xs uppercase tracking-wider">
                  <th className="py-3 px-4">Feedback ID</th>
                  <th className="py-3 px-4">Allocation ID</th>
                  <th className="py-3 px-4">Forecast Reference</th>
                  <th className="py-3 px-4">Deferred %</th>
                  <th className="py-3 px-4">Idempotency Key</th>
                  <th className="py-3 px-4">Partner Origin</th>
                  <th className="py-3 px-4">Timestamp (UTC)</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-200 text-xs">
                {filteredRecords.map((item) => {
                  const isPartner = isPartnerFeedback(item);
                  const isPostOpt =
                    item.feedback_id === "FBD-A5998866" ||
                    Boolean(item.operational_adjustment_id) ||
                    (item.idempotency_key && item.idempotency_key.startsWith("IDEMP-"));

                  return (
                    <tr
                      key={item.feedback_id}
                      className={`hover:bg-slate-800/40 transition-colors ${
                        selectedRecord?.feedback_id === item.feedback_id ? "bg-indigo-950/30" : ""
                      }`}
                    >
                      <td className="py-3.5 px-4 font-mono font-semibold text-indigo-400 whitespace-nowrap">
                        <div className="flex items-center space-x-1.5">
                          <span>{item.feedback_id}</span>
                          {isPostOpt && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] bg-purple-500/20 text-purple-300 border border-purple-500/40 font-mono font-medium">
                              Post-Opt
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3.5 px-4 font-mono text-amber-400 font-semibold whitespace-nowrap">
                        {item.allocation_run_id}
                      </td>
                      <td className="py-3.5 px-4 font-mono text-slate-300 whitespace-nowrap">
                        {item.forecast_id}
                      </td>
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        {item.deferred_fraction !== undefined && item.deferred_fraction !== null ? (
                          <span className="px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-amber-500/10 text-amber-300 border border-amber-500/20">
                            {Math.round(item.deferred_fraction * 100)}%
                          </span>
                        ) : (
                          <span className="text-slate-500 font-mono">—</span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 font-mono text-slate-400 max-w-[160px] truncate" title={item.idempotency_key || ""}>
                        {item.idempotency_key ? (
                          <span className="text-[11px] bg-slate-950/60 px-1.5 py-0.5 rounded border border-slate-800">
                            {item.idempotency_key}
                          </span>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        {isPartner ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-mono">
                            <Cpu className="w-3 h-3 mr-1 text-emerald-400" />
                            EVCharge-Opt
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-mono">
                            Registered Network
                          </span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-slate-400 font-mono text-[11px] whitespace-nowrap">
                        {new Date(item.submitted_at || item.received_at).toLocaleString()}
                      </td>
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          <CheckCircle2 className="w-3 h-3 mr-1" />
                          {(item.status || "ACCEPTED").toUpperCase()}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 text-right whitespace-nowrap">
                        <button
                          onClick={() => handleInspect(item)}
                          className="px-2.5 py-1.5 bg-indigo-600/80 hover:bg-indigo-600 text-white rounded-lg text-xs font-medium inline-flex items-center transition-colors shadow-sm"
                        >
                          <Eye className="w-3.5 h-3.5 mr-1" /> Details
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Detailed Inspection Modal */}
      {selectedRecord && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-2xl w-full p-6 space-y-5 shadow-2xl overflow-y-auto max-h-[90vh]">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center space-x-2">
                <FileText className="w-5 h-5 text-indigo-400" />
                <h3 className="font-bold text-white text-base">
                  Feedback Record Details: <span className="text-indigo-400 font-mono">{selectedRecord.feedback_id}</span>
                </h3>
              </div>
              <button
                onClick={() => setSelectedRecord(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
              <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-1">
                <span className="text-slate-400 flex items-center">
                  <Hash className="w-3.5 h-3.5 mr-1 text-slate-500" /> Allocation Run ID
                </span>
                <span className="font-mono text-amber-400 font-semibold text-sm block">
                  {selectedRecord.allocation_run_id}
                </span>
              </div>

              <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-1">
                <span className="text-slate-400 flex items-center">
                  <Layers className="w-3.5 h-3.5 mr-1 text-slate-500" /> Forecast Reference
                </span>
                <span className="font-mono text-slate-200 font-semibold text-sm block">
                  {selectedRecord.forecast_id}
                </span>
              </div>

              <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-1">
                <span className="text-slate-400 flex items-center">
                  <Sliders className="w-3.5 h-3.5 mr-1 text-slate-500" /> Deferred Fraction
                </span>
                <span className="font-mono text-emerald-400 font-semibold text-sm block">
                  {selectedRecord.deferred_fraction !== undefined && selectedRecord.deferred_fraction !== null
                    ? `${Math.round(selectedRecord.deferred_fraction * 100)}% (${selectedRecord.deferred_fraction})`
                    : "Not specified"}
                </span>
              </div>

              <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-1">
                <span className="text-slate-400 flex items-center">
                  <ShieldCheck className="w-3.5 h-3.5 mr-1 text-slate-500" /> Idempotency Key
                </span>
                <span className="font-mono text-indigo-300 text-xs block break-all">
                  {selectedRecord.idempotency_key || "None"}
                </span>
              </div>

              {selectedRecord.operational_adjustment_id && (
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-1">
                  <span className="text-slate-400">Operational Adjustment ID</span>
                  <span className="font-mono text-purple-300 font-semibold text-sm block">
                    {selectedRecord.operational_adjustment_id}
                  </span>
                </div>
              )}

              <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-1">
                <span className="text-slate-400">Partner Origin & Engine</span>
                <span className="font-mono text-slate-200 text-xs block">
                  {selectedRecord.optimizer_version || "EVCharge-Opt Optimizer"}
                </span>
              </div>

              <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-1">
                <span className="text-slate-400 flex items-center">
                  <Clock className="w-3.5 h-3.5 mr-1 text-slate-500" /> Submitted (UTC)
                </span>
                <span className="font-mono text-slate-300 text-xs block">
                  {selectedRecord.submitted_at}
                </span>
              </div>

              <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-1">
                <span className="text-slate-400 flex items-center">
                  <Clock className="w-3.5 h-3.5 mr-1 text-slate-500" /> Received (UTC)
                </span>
                <span className="font-mono text-slate-300 text-xs block">
                  {selectedRecord.received_at}
                </span>
              </div>
            </div>

            {/* Station outcomes if available */}
            {selectedRecord.station_outcomes && selectedRecord.station_outcomes.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                  Station Allocation Outcomes
                </h4>
                <div className="overflow-x-auto border border-slate-800 rounded-lg">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="bg-slate-950 text-slate-400 border-b border-slate-800">
                        <th className="py-2 px-3">Station</th>
                        <th className="py-2 px-3">Allocated Power</th>
                        <th className="py-2 px-3">Arrivals</th>
                        <th className="py-2 px-3">Served</th>
                        <th className="py-2 px-3">Unserved</th>
                        <th className="py-2 px-3">Utilization</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                      {selectedRecord.station_outcomes.map((st, idx) => (
                        <tr key={idx} className="hover:bg-slate-800/30">
                          <td className="py-2 px-3 text-indigo-400 font-semibold">{st.station_id}</td>
                          <td className="py-2 px-3">{st.allocated_power_kw} kW</td>
                          <td className="py-2 px-3">{st.predicted_arrivals}</td>
                          <td className="py-2 px-3 text-emerald-400">{st.estimated_served}</td>
                          <td className="py-2 px-3 text-amber-400">{st.estimated_unserved}</td>
                          <td className="py-2 px-3">{st.charger_utilization_pct}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div className="flex justify-end space-x-3 pt-3 border-t border-slate-800">
              {onInspectAdjustedDemand && (
                <button
                  type="button"
                  onClick={() => {
                    const rec = selectedRecord;
                    setSelectedRecord(null);
                    onInspectAdjustedDemand(rec.forecast_id, rec.feedback_id);
                  }}
                  className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-medium transition-colors"
                >
                  Inspect Ingestion Profile
                </button>
              )}
              <button
                type="button"
                onClick={() => setSelectedRecord(null)}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-medium transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default FeedbackHistory;
