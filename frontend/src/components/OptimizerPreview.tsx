import { useState } from "react";
import { Cpu, CheckCircle2, ArrowRightLeft, RefreshCw, AlertCircle, ShieldCheck, Layers } from "lucide-react";
import { ForecastDetailRead, PartnerSyncResponse, syncWithPartner } from "../api";

interface Props {
  forecast: ForecastDetailRead | null;
  onSyncComplete?: (result: PartnerSyncResponse) => void;
}

export default function OptimizerPreview({ forecast, onSyncComplete }: Props) {
  const [syncing, setSyncing] = useState<boolean>(false);
  const [syncResult, setSyncResult] = useState<PartnerSyncResponse | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  const handlePartnerSync = async () => {
    if (!forecast || syncing) return;

    setSyncing(true);
    setSyncError(null);

    try {
      const firstStation = forecast.stations[0];
      const firstInterval = firstStation?.intervals[0];

      const res = await syncWithPartner({
        forecast_id: forecast.forecast_id,
        scenario_id: forecast.scenario_id || "SCN-001",
        forecast_start: firstInterval?.interval_start,
        interval_start: firstInterval?.interval_start,
        interval_end: firstInterval?.interval_end,
      });

      setSyncResult(res);
      if (!res.success) {
        setSyncError(res.error || "Partner sync did not complete successfully.");
      } else {
        if (onSyncComplete) {
          onSyncComplete(res);
        }
      }
    } catch (err: any) {
      setSyncError(err?.message || String(err));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Partner Sync Action Card */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-slate-200">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 mb-4 border-b border-slate-800">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-indigo-500/10 text-indigo-400 rounded-xl border border-indigo-500/20">
              <ArrowRightLeft className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                Partner Sync — EVCharge-Opt Integration
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-semibold">
                  LIVE SERVICE
                </span>
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Executes cross-service exchange: dispatches demand forecast, receives grid-constrained allocation, and submits feedback
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={handlePartnerSync}
            disabled={!forecast || syncing}
            className={`px-5 py-2.5 rounded-lg text-xs font-semibold flex items-center justify-center space-x-2 transition-all ${
              !forecast
                ? "bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700/40"
                : syncing
                ? "bg-indigo-600/50 text-indigo-200 cursor-wait border border-indigo-500/40"
                : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/20 border border-indigo-500"
            }`}
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${syncing ? "animate-spin" : ""}`} />
            <span>
              {syncing
                ? "Synchronizing with EVCharge-Opt..."
                : !forecast
                ? "Generate Forecast to Enable Sync"
                : "Execute Partner Sync"}
            </span>
          </button>
        </div>

        {/* Sync Info / Guidance */}
        {!syncResult && !syncing && (
          <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800/80 text-xs text-slate-400 flex items-start space-x-2.5">
            <Layers className="w-4 h-4 text-indigo-400 flex-shrink-0 mt-0.5" />
            <div className="leading-relaxed">
              Target Partner Service: <strong className="text-slate-200 font-mono">https://evcharge-opt-api.onrender.com</strong>.
              When executed, EVCharge-Predict makes server-to-server calls to ingest predictions into EVCharge-Opt, computes priority power allocation, and logs feedback with real correlation tracking.
            </div>
          </div>
        )}

        {/* Error Notification */}
        {syncError && (
          <div className="mt-4 p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-300 flex items-start space-x-3">
            <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
            <div>
              <strong className="block text-rose-200 mb-0.5">Partner Communication Error</strong>
              <span>{syncError}</span>
            </div>
          </div>
        )}

        {/* Live Partner Sync Results Card */}
        {syncResult && syncResult.success && (
          <div className="mt-4 space-y-4">
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-xs text-slate-300">
              <div className="flex items-center justify-between pb-3 mb-3 border-b border-emerald-500/20">
                <div className="flex items-center space-x-2">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  <span className="font-bold text-white text-sm">Cross-Service Exchange Verified</span>
                </div>
                <span className="font-mono text-[11px] text-emerald-400">
                  HTTP 201 Created • {syncResult.roundtrip_duration_ms} ms roundtrip
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-3">
                <div className="p-2.5 bg-slate-950/80 rounded-lg border border-slate-800">
                  <div className="text-[10px] text-slate-400 uppercase font-mono">Allocation ID</div>
                  <div className="font-mono font-bold text-indigo-400 text-xs mt-0.5 truncate">
                    {syncResult.opt_allocation_id || "N/A"}
                  </div>
                </div>
                <div className="p-2.5 bg-slate-950/80 rounded-lg border border-slate-800">
                  <div className="text-[10px] text-slate-400 uppercase font-mono">Feedback ID</div>
                  <div className="font-mono font-bold text-emerald-400 text-xs mt-0.5 truncate">
                    {syncResult.opt_feedback_id || "Submitted"}
                  </div>
                </div>
                <div className="p-2.5 bg-slate-950/80 rounded-lg border border-slate-800">
                  <div className="text-[10px] text-slate-400 uppercase font-mono">Allocated Power</div>
                  <div className="font-mono font-bold text-white text-xs mt-0.5">
                    {syncResult.total_allocated_power_kw} kW
                  </div>
                </div>
                <div className="p-2.5 bg-slate-950/80 rounded-lg border border-slate-800">
                  <div className="text-[10px] text-slate-400 uppercase font-mono">Served / Unserved EVs</div>
                  <div className="font-mono font-bold text-amber-400 text-xs mt-0.5">
                    {syncResult.total_served_vehicles} / {syncResult.total_unserved_vehicles}
                  </div>
                </div>
              </div>

              {/* Station Allocation Result Table from EVCharge-Opt */}
              {syncResult.allocation_results.length > 0 && (
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 font-mono text-[11px]">
                        <th className="py-2 px-3">Station</th>
                        <th className="py-2 px-3">Allocated Power</th>
                        <th className="py-2 px-3">Est. Served</th>
                        <th className="py-2 px-3">Unserved</th>
                        <th className="py-2 px-3">Wait Time</th>
                        <th className="py-2 px-3 text-right">Charger Util.</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono text-slate-200">
                      {syncResult.allocation_results.map((st) => (
                        <tr key={st.station_id} className="hover:bg-slate-800/30">
                          <td className="py-2 px-3 font-semibold text-indigo-400">
                            {st.station_id} <span className="text-[10px] text-slate-400 font-normal">({st.station_name})</span>
                          </td>
                          <td className="py-2 px-3 text-emerald-400 font-bold">{st.allocated_power_kw} kW</td>
                          <td className="py-2 px-3">{st.estimated_served} EVs</td>
                          <td className="py-2 px-3 text-amber-400">{st.estimated_unserved} EVs</td>
                          <td className="py-2 px-3">{st.estimated_wait_minutes} min</td>
                          <td className="py-2 px-3 text-right">{st.charger_utilization_pct}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Grid Capability Summary Preview */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-slate-200">
        <div className="flex items-center space-x-3 pb-3 mb-4 border-b border-slate-800">
          <div className="p-2 bg-indigo-500/10 text-indigo-400 rounded-lg">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-sm font-semibold text-white">Downstream Optimization Architecture</h4>
            <p className="text-xs text-slate-400">EVCharge-Opt linear optimization model parameters</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800/80">
            <div className="text-xs text-slate-400 mb-1">Substation Feeder Limit</div>
            <div className="text-xl font-bold text-white">600 kW</div>
            <div className="text-xs text-emerald-400 mt-1 flex items-center">
              <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Residual constraint active
            </div>
          </div>
          <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800/80">
            <div className="text-xs text-slate-400 mb-1">Priority Hierarchy</div>
            <div className="text-sm font-bold text-white mt-1">Multi-Objective LP</div>
            <div className="text-xs text-slate-400 mt-1">1: Served arrivals, 2: Grid limits</div>
          </div>
          <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800/80">
            <div className="text-xs text-slate-400 mb-1">Feedback Policy</div>
            <div className="text-sm font-bold text-indigo-400 mt-1">v1-heuristic-envelope</div>
            <div className="text-xs text-slate-400 mt-1">max(baseline, allocated)</div>
          </div>
        </div>
      </div>
    </div>
  );
}
