import React from "react";
import { StationRead } from "../api";
import SourceBadge from "./SourceBadge";
import { MapPin, Server, Activity, ShieldCheck, ShieldAlert, Info } from "lucide-react";

type Props = {
  stations: StationRead[];
  loading: boolean;
  error: string | null;
  demoMode: boolean;
  stationSource?: "live" | "scenario_catalog" | "scenario_catalog_empty" | "scenario_catalog_fallback";
  stationNotice?: string | null;
};

const StationTable: React.FC<Props> = ({
  stations,
  loading,
  error,
  demoMode,
  stationSource = "scenario_catalog",
  stationNotice,
}) => {
  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 bg-slate-900/60 rounded-xl border border-slate-800 text-slate-400">
        <Activity className="w-5 h-5 animate-spin mr-3 text-emerald-400" />
        <span>Loading charging station inventory...</span>
      </div>
    );
  }

  const isLive = !demoMode && stationSource === "live";

  return (
    <div className="space-y-4">
      {/* Non-blocking Status Notice for Live API Mode */}
      {!demoMode && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 text-xs text-slate-300">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center space-x-2">
              {error ? (
                <ShieldAlert className="w-4 h-4 text-amber-400 flex-shrink-0" />
              ) : (
                <Info className="w-4 h-4 text-indigo-400 flex-shrink-0" />
              )}
              <span className="font-semibold text-white">
                {isLive ? "Live Station Registry" : "Live API Authentication / Catalog Notice"}
              </span>
            </div>
            <SourceBadge source={isLive ? "live" : "demo"} />
          </div>
          <p className="text-slate-400 leading-relaxed">
            {stationNotice ||
              (isLive
                ? "Displaying active registered charging stations from production database."
                : "Live API Authentication required. The station selector has automatically loaded the scenario-planning catalog (ST-001, ST-002, ST-003) so you can continue exploring forecasting and optimization.")}
          </p>
        </div>
      )}

      {/* Station Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center">
              <Server className={`w-5 h-5 mr-2 ${isLive ? "text-emerald-400" : "text-indigo-400"}`} />
              Charging Stations ({stations.length})
            </h3>
            <p className="text-xs text-slate-400 mt-1">
              {isLive
                ? "Live station inventory returned by backend database"
                : "Campus network register from scenario-planning catalog"}
            </p>
          </div>
          <SourceBadge source={isLive ? "live" : "demo"} />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 font-medium text-xs uppercase tracking-wider">
                <th className="py-3 px-4">Station ID</th>
                <th className="py-3 px-4">Hardware Identifier</th>
                <th className="py-3 px-4">Site Location</th>
                <th className="py-3 px-4">Provenance</th>
                <th className="py-3 px-4 text-right">Operational Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-200 text-xs">
              {stations.map((s) => {
                const isCatalogStation = s.origin_source === "scenario_catalog" || !isLive;
                return (
                  <tr key={s.station_id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 font-mono font-bold text-indigo-400 flex items-center">
                      <MapPin className="w-3.5 h-3.5 mr-1 text-indigo-500" />
                      {s.station_id}
                    </td>
                    <td className="py-3 px-4 font-mono text-xs text-slate-400">{s.source_station_id}</td>
                    <td className="py-3 px-4 text-slate-300 capitalize">{s.site_id || "caltech"}</td>
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold ${
                          isCatalogStation
                            ? "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20"
                            : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        }`}
                      >
                        {isCatalogStation ? "SCENARIO CATALOG" : "LIVE REGISTRY"}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        <ShieldCheck className="w-3 h-3 mr-1" />
                        {isCatalogStation ? "SCENARIO READY" : "ACTIVE"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default StationTable;
