import React from "react";
import { StationRead } from "../api";
import SourceBadge from "./SourceBadge";
import { MapPin, Server, Activity, ShieldCheck } from "lucide-react";

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

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-red-300">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-red-200">Unable to Fetch Stations</h3>
          <SourceBadge source="unavailable" />
        </div>
        <p className="text-sm">{error}</p>
      </div>
    );
  }

  if (demoMode) {
    const demoStations = [
      { station_id: "ST-001", source_station_id: "1-39-139-650", site_id: "caltech", status: "ONLINE", totalEnergy: 1420.5 },
      { station_id: "ST-002", source_station_id: "1-39-139-651", site_id: "caltech", status: "ONLINE", totalEnergy: 1890.2 },
      { station_id: "ST-003", source_station_id: "demo-src-ST-003", site_id: "demo-site", status: "MAINTENANCE", totalEnergy: 432.8 }
    ];

    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center">
              <Server className="w-5 h-5 mr-2 text-blue-400" />
              Demo Station Inventory
            </h3>
            <p className="text-xs text-slate-400 mt-1">Local static mock stations for offline testing</p>
          </div>
          <SourceBadge source="demo" />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 font-medium">
                <th className="py-3 px-4">Station ID</th>
                <th className="py-3 px-4">Source HW ID</th>
                <th className="py-3 px-4">Site ID</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Energy (kWh)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-200">
              {demoStations.map((s) => (
                <tr key={s.station_id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="py-3 px-4 font-mono font-semibold text-emerald-400">{s.station_id}</td>
                  <td className="py-3 px-4 font-mono text-xs text-slate-400">{s.source_station_id}</td>
                  <td className="py-3 px-4 text-slate-300">{s.site_id}</td>
                  <td className="py-3 px-4">
                    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${s.status === "ONLINE" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-amber-500/10 text-amber-400 border border-amber-500/20"}`}>
                      {s.status}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right font-mono">{s.totalEnergy.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

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
                  {new Date(s.created_at).toLocaleDateString()}
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
