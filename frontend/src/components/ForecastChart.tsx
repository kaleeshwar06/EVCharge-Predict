import React from "react";
import { ForecastDetailRead } from "../api";
import SourceBadge from "./SourceBadge";
import { TrendingUp } from "lucide-react";

type Props = {
  forecast: ForecastDetailRead;
};

const ForecastChart: React.FC<Props> = ({ forecast }) => {
  if (!forecast || !forecast.stations || forecast.stations.length === 0) return null;

  // Aggregate stats across all requested stations
  let totalEnergy = 0;
  let totalArrivals = 0;
  let totalIntervals = 0;

  forecast.stations.forEach((st) => {
    st.intervals.forEach((i) => {
      totalEnergy += i.predicted_energy_kwh || 0;
      totalArrivals += i.predicted_arrivals || 0;
      totalIntervals += 1;
    });
  });

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 mt-6 text-slate-200">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 mb-4 border-b border-slate-800 gap-2">
        <div>
          <div className="flex items-center space-x-2">
            <TrendingUp className="w-5 h-5 text-emerald-400" />
            <h3 className="text-lg font-bold text-white">Prediction Results</h3>
            <span className="font-mono text-xs text-slate-400 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
              {forecast.forecast_id}
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-1">
            Scenario: <span className="text-amber-400 font-mono font-medium">{forecast.scenario_id}</span> • Model: <span className="text-slate-300 font-mono">{forecast.demand_type}</span>
          </div>
        </div>
        <SourceBadge source="live" />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-6">
        <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
          <div className="text-xs text-slate-400">Total Expected Energy</div>
          <div className="text-lg font-bold text-cyan-300 font-mono mt-1">{totalEnergy.toFixed(2)} kWh</div>
        </div>
        <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
          <div className="text-xs text-slate-400">Total Expected Arrivals</div>
          <div className="text-lg font-bold text-emerald-400 font-mono mt-1">{totalArrivals} vehicles</div>
        </div>
        <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/80 col-span-2 sm:col-span-1">
          <div className="text-xs text-slate-400">Station Forecasts</div>
          <div className="text-lg font-bold text-indigo-400 font-mono mt-1">{forecast.stations.length} stations</div>
        </div>
      </div>

      <div className="space-y-6">
        {forecast.stations.map((st) => (
          <div key={st.station_id} className="border border-slate-800/80 rounded-lg overflow-hidden">
            <div className="bg-slate-950 px-4 py-2 text-xs font-mono font-bold text-emerald-400 border-b border-slate-800/80 flex items-center justify-between">
              <span>Station: {st.station_id}</span>
              <span className="text-slate-400 font-normal">{st.intervals.length} intervals (60m step)</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm border-collapse">
                <thead>
                  <tr className="border-b border-slate-800/60 text-slate-400 font-medium text-xs bg-slate-900/50">
                    <th className="py-2.5 px-3">Interval Start (UTC)</th>
                    <th className="py-2.5 px-3">Interval End (UTC)</th>
                    <th className="py-2.5 px-3 text-right">Predicted Arrivals</th>
                    <th className="py-2.5 px-3 text-right">Expected Energy (kWh)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-300">
                  {st.intervals.map((intv, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/30 font-mono text-xs">
                      <td className="py-2 px-3 text-slate-300">{intv.interval_start}</td>
                      <td className="py-2 px-3 text-slate-400">{intv.interval_end}</td>
                      <td className="py-2 px-3 text-right text-emerald-400 font-semibold">{intv.predicted_arrivals}</td>
                      <td className="py-2 px-3 text-right text-cyan-300 font-bold">{intv.predicted_energy_kwh.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ForecastChart;
