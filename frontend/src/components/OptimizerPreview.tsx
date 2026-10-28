import { Cpu, Zap, CheckCircle2 } from "lucide-react";

export default function OptimizerPreview() {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 mt-4 text-slate-200">
      <div className="flex items-center justify-between mb-4 pb-4 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-indigo-500/10 text-indigo-400 rounded-lg">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white">EVCharge-Opt Simulation</h3>
            <p className="text-sm text-slate-400">
              Mock integration showing power allocation workflows based on demand predictions
            </p>
          </div>
        </div>
        <span className="px-3 py-1 bg-amber-500/10 text-amber-400 border border-amber-500/20 text-xs font-semibold rounded-full">
          SIMULATED / DEMO
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800/80">
          <div className="text-xs text-slate-400 mb-1">Grid Transformer Cap</div>
          <div className="text-xl font-bold text-white">250 kW</div>
          <div className="text-xs text-emerald-400 mt-1 flex items-center">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1" /> Peak within limits
          </div>
        </div>
        <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800/80">
          <div className="text-xs text-slate-400 mb-1">Simulated Optimization Run</div>
          <div className="text-xl font-bold text-white">opt_run_demo_01</div>
          <div className="text-xs text-slate-400 mt-1">Status: Converged (42ms)</div>
        </div>
        <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800/80">
          <div className="text-xs text-slate-400 mb-1">Total Curtailment</div>
          <div className="text-xl font-bold text-amber-400">12.4 kWh</div>
          <div className="text-xs text-slate-400 mt-1">Fairness index: 0.96</div>
        </div>
      </div>

      <div className="bg-slate-950/40 border border-slate-800/60 rounded-lg p-4">
        <h4 className="text-sm font-semibold text-slate-300 mb-2 flex items-center">
          <Zap className="w-4 h-4 mr-1.5 text-amber-400" />
          Allocated Power Schedule Preview
        </h4>
        <div className="text-xs text-slate-400 mb-3">
          Downstream optimizer receives interval demand from EVCharge-Predict and feeds back scheduled charge profiles.
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="py-2 px-3">Interval (UTC)</th>
                <th className="py-2 px-3">Station</th>
                <th className="py-2 px-3">Predicted Demand</th>
                <th className="py-2 px-3">Optimized Allocation</th>
                <th className="py-2 px-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50 text-slate-300">
              <tr>
                <td className="py-2.5 px-3">2026-10-28 20:00</td>
                <td className="py-2.5 px-3 font-mono">ST-001</td>
                <td className="py-2.5 px-3">48.5 kW</td>
                <td className="py-2.5 px-3 text-emerald-400 font-medium">45.0 kW</td>
                <td className="py-2.5 px-3"><span className="text-emerald-400">Dispatched</span></td>
              </tr>
              <tr>
                <td className="py-2.5 px-3">2026-10-28 20:00</td>
                <td className="py-2.5 px-3 font-mono">ST-002</td>
                <td className="py-2.5 px-3">62.1 kW</td>
                <td className="py-2.5 px-3 text-emerald-400 font-medium">55.0 kW</td>
                <td className="py-2.5 px-3"><span className="text-emerald-400">Dispatched</span></td>
              </tr>
              <tr>
                <td className="py-2.5 px-3">2026-10-28 21:00</td>
                <td className="py-2.5 px-3 font-mono">ST-001</td>
                <td className="py-2.5 px-3">55.0 kW</td>
                <td className="py-2.5 px-3 text-emerald-400 font-medium">50.0 kW</td>
                <td className="py-2.5 px-3"><span className="text-slate-400">Scheduled</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
