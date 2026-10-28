import React from "react";
import { StationRead } from "../api";
import SourceBadge from "./SourceBadge";
import { MapPin, Server, Activity, ShieldCheck, ShieldAlert } from "lucide-react";

type Props = {
  stations: StationRead[];
  loading: boolean;
  error: string | null;
  demoMode: boolean;
};

const StationTable: React.FC<Props> = ({ stations, loading, error, demoMode }) => {
  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 bg-slate-900/60 rounded-xl border border-slate-800 text-slate-400">
        <Activity className="w-5 h-5 animate-spin mr-3 text-emerald-400" />
        <span>Loading charging station inventory...</span>
      </div>
    );
  }

  if (demoMode) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center">
              <Server className="w-5 h-5 mr-2 text-blue-400" />
              Demo Station Inventory ({stations.length})
            </h3>
            <p className="text-xs text-slate-400 mt-1">
              Isolated mock stations running locally in browser memory for exploration
            </p>
          </div>
          <SourceBadge source="demo" />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 font-medium">
                <th className="py-3 px-4">Station ID</th>
                <th className="py-3 px-4">Source Hardware ID</th>
                <th className="py-3 px-4">Site ID</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Data Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-200">
              {stations.map((s) => (
                <tr key={s.station_id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="py-3 px-4 font-mono font-bold text-blue-400 flex items-center">
                    <MapPin className="w-3.5 h-3.5 mr-1 text-blue-500" />
                    {s.station_id}
                  </td>
                  <td className="py-3 px-4 font-mono text-xs text-slate-400">{s.source_station_id}</td>
                  <td className="py-3 px-4 text-slate-300 capitalize">{s.site_id || "caltech"}</td>
                  <td className="py-3 px-4">
                    <span className="px-2 py-0.5 rounded text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                      SIMULATED
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right">
                    <span className="text-xs font-mono text-slate-500">client-mock</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // Live Mode: Handle error explicitly, NEVER mask errors by showing demo stations
  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-red-300">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center space-x-2">
            <ShieldAlert className="w-5 h-5 text-red-400 flex-shrink-0" />
            <h3 className="font-semibold text-red-200">Live API Authentication / Connection Error</h3>
          </div>
          <SourceBadge source="unavailable" />
        </div>
        <p className="text-sm mb-4 leading-relaxed">{error}</p>
        <div className="bg-slate-950/80 p-4 rounded-lg border border-red-500/20 text-xs text-slate-400 space-y-2">
          <div className="font-semibold text-slate-300">Why did this happen?</div>
          <p>
            The production backend requires a service-to-service Bearer authorization token header on protected routes (<code>/api/v1/stations</code>, <code>/api/v1/forecasts</code>, etc.) to safeguard sensitive infrastructure and models.
          </p>
          <div className="font-semibold text-slate-300 pt-1">Recommended Action:</div>
          <p>
            Toggle <strong>Demo Mode</strong> in the upper right header to explore full multi-station forecasting and optimizer feedback with simulated data.
          </p>
        </div>
      </div>
    );
  }

  // Live Mode: Successful fetch with 0 stations
  if (stations.length === 0) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-300">
        <Server className="w-8 h-8 mx-auto mb-3 text-slate-500" />
        <h3 className="text-base font-semibold text-white mb-1">No Stations Found in Production Database</h3>
        <p className="text-xs text-slate-400 max-w-md mx-auto mb-4">
          The production database schema is migrated, but the stations table currently contains 0 records.
        </p>
        <SourceBadge source="live" />
      </div>
    );
  }

  // Live Mode: Stations loaded from database
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
        <div>
          <h3 className="text-lg font-bold text-white flex items-center">
            <Server className="w-5 h-5 mr-2 text-emerald-400" />
            Registered Charging Stations ({stations.length})
          </h3>
          <p className="text-xs text-slate-400 mt-1">Live station inventory returned by backend database</p>
        </div>
        <SourceBadge source="live" />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm border-collapse">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 font-medium">
              <th className="py-3 px-4">Internal ID</th>
              <th className="py-3 px-4">Canonical ID</th>
              <th className="py-3 px-4">Source Station ID</th>
              <th className="py-3 px-4">Site</th>
              <th className="py-3 px-4">Registered Date</th>
              <th className="py-3 px-4 text-right">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 text-slate-200">
            {stations.map((s) => (
              <tr key={s.station_id} className="hover:bg-slate-800/30 transition-colors">
                <td className="py-3 px-4 text-slate-500 font-mono text-xs">#{s.id}</td>
                <td className="py-3 px-4 font-mono font-bold text-emerald-400 flex items-center">
                  <MapPin className="w-3.5 h-3.5 mr-1 text-emerald-500" />
                  {s.station_id}
                </td>
                <td className="py-3 px-4 font-mono text-xs text-slate-400">{s.source_station_id}</td>
                <td className="py-3 px-4 text-slate-300 capitalize">{s.site_id || "default"}</td>
                <td className="py-3 px-4 text-xs text-slate-400">
                  {s.created_at ? new Date(s.created_at).toLocaleDateString() : "—"}
                </td>
                <td className="py-3 px-4 text-right">
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <ShieldCheck className="w-3 h-3 mr-1" /> ACTIVE
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default StationTable;
