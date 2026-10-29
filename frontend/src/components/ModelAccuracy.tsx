import React, { useState } from "react";
import {
  BarChart3,
  Info,
  Cpu,
  TrendingUp,
  Database,
} from "lucide-react";
import SourceBadge from "./SourceBadge";

export const ModelAccuracy: React.FC = () => {
  const [activeMetricTab, setActiveMetricTab] = useState<"arrivals" | "energy">("arrivals");

  // Accurate ground truth metrics directly sourced from artifacts/models/manifest.json
  const arrivalMetrics = {
    targetName: "Charging Session Arrivals",
    targetUnit: "sessions / hour",
    rfTestMae: 0.403,
    rfTestRmse: 0.5574,
    baselineTestMae: 0.3356,
    baselineTestRmse: 0.6854,
    rfValMae: 0.4069,
    rfValRmse: 0.5387,
    baselineValMae: 0.380,
    baselineValRmse: 0.6683,
    perStation: [
      { stationId: "ST-001", samples: 50, rfMae: 0.352, baselineMae: 0.240 },
      { stationId: "ST-002", samples: 49, rfMae: 0.398, baselineMae: 0.3061 },
      { stationId: "ST-003", samples: 50, rfMae: 0.4588, baselineMae: 0.460 },
    ],
  };

  const energyMetrics = {
    targetName: "Session Start Energy Demand",
    targetUnit: "kWh / hour",
    rfTestMae: 8.4448,
    rfTestRmse: 11.862,
    baselineTestMae: 7.0487,
    baselineTestRmse: 13.8718,
    rfValMae: 8.6472,
    rfValRmse: 11.8642,
    baselineValMae: 9.0933,
    baselineValRmse: 16.7973,
    perStation: [
      { stationId: "ST-001", samples: 50, rfMae: 7.141, baselineMae: 5.3112 },
      { stationId: "ST-002", samples: 49, rfMae: 9.2926, baselineMae: 7.3459 },
      { stationId: "ST-003", samples: 50, rfMae: 8.9178, baselineMae: 8.4948 },
    ],
  };

  const currentMetrics = activeMetricTab === "arrivals" ? arrivalMetrics : energyMetrics;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center">
            <BarChart3 className="w-5 h-5 mr-2 text-indigo-400" />
            Model Architecture & Evaluation Metrics
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Standard offline benchmark performance from the trained scikit-learn Random Forest ensemble and lag baselines
          </p>
        </div>
        <SourceBadge source="demo" />
      </div>

      {/* Model Spec Card */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-xs text-slate-400 mb-1">Architecture</div>
          <div className="text-base font-bold text-white font-mono">RandomForestRegressor</div>
          <div className="text-[11px] text-slate-500 mt-1">100 estimators • Recursive 6h horizon</div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-xs text-slate-400 mb-1">Feature Space</div>
          <div className="text-base font-bold text-indigo-400 font-mono">30 Lag & Cyclic Features</div>
          <div className="text-[11px] text-slate-500 mt-1">Lags (1-168h) • Sin/Cos temporal • Station encoder</div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-xs text-slate-400 mb-1">Validation Split</div>
          <div className="text-base font-bold text-emerald-400 font-mono">Chronological (70/15/15)</div>
          <div className="text-[11px] text-slate-500 mt-1">Strict time ordering • Zero future leakage</div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-xs text-slate-400 mb-1">Model Version</div>
          <div className="text-base font-bold text-amber-400 font-mono">v1.0 (scikit-learn 1.9.1)</div>
          <div className="text-[11px] text-slate-500 mt-1">Verified artifact manifest</div>
        </div>
      </div>

      {/* Metric Selector Tabs */}
      <div className="flex space-x-2 border-b border-slate-800 pb-2">
        <button
          onClick={() => setActiveMetricTab("arrivals")}
          className={`px-4 py-2 rounded-lg text-xs font-semibold transition-colors flex items-center space-x-2 ${
            activeMetricTab === "arrivals"
              ? "bg-indigo-600 text-white"
              : "bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800"
          }`}
        >
          <TrendingUp className="w-3.5 h-3.5" />
          <span>Arrival Prediction (Sessions/hr)</span>
        </button>
        <button
          onClick={() => setActiveMetricTab("energy")}
          className={`px-4 py-2 rounded-lg text-xs font-semibold transition-colors flex items-center space-x-2 ${
            activeMetricTab === "energy"
              ? "bg-indigo-600 text-white"
              : "bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800"
          }`}
        >
          <Cpu className="w-3.5 h-3.5" />
          <span>Energy Demand (kWh)</span>
        </button>
      </div>

      {/* Main Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Test Set Evaluation */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div>
              <h3 className="font-semibold text-white text-sm">Test Dataset Evaluation (Out-of-Sample)</h3>
              <p className="text-[11px] text-slate-400">149 hourly evaluation windows</p>
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300">
              Holdout Split
            </span>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800">
              <div className="text-[11px] text-slate-400">Random Forest MAE</div>
              <div className="text-xl font-bold text-indigo-400 font-mono mt-0.5">
                {currentMetrics.rfTestMae} <span className="text-xs text-slate-500 font-normal">{currentMetrics.targetUnit}</span>
              </div>
              <div className="text-[10px] text-slate-500 mt-1">RMSE: {currentMetrics.rfTestRmse}</div>
            </div>

            <div className="bg-slate-950/70 p-3 rounded-lg border border-slate-800">
              <div className="text-[11px] text-slate-400">Baseline Model MAE</div>
              <div className="text-xl font-bold text-slate-300 font-mono mt-0.5">
                {currentMetrics.baselineTestMae} <span className="text-xs text-slate-500 font-normal">{currentMetrics.targetUnit}</span>
              </div>
              <div className="text-[10px] text-slate-500 mt-1">RMSE: {currentMetrics.baselineTestRmse}</div>
            </div>
          </div>

          {/* Validation Metrics Comparison */}
          <div className="text-xs text-slate-400 pt-2 border-t border-slate-800/80">
            <div className="flex justify-between py-1">
              <span>Validation Split RF MAE:</span>
              <span className="font-mono text-slate-200">{currentMetrics.rfValMae} {currentMetrics.targetUnit}</span>
            </div>
            <div className="flex justify-between py-1">
              <span>Validation Split RF RMSE:</span>
              <span className="font-mono text-slate-200">{currentMetrics.rfValRmse} {currentMetrics.targetUnit}</span>
            </div>
          </div>
        </div>

        {/* Per-Station Breakdown */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div>
              <h3 className="font-semibold text-white text-sm">Per-Station Error Breakdown</h3>
              <p className="text-[11px] text-slate-400">Station-specific MAE comparison</p>
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300">
              ST-001 • ST-002 • ST-003
            </span>
          </div>

          <div className="space-y-2.5">
            {currentMetrics.perStation.map((st) => (
              <div
                key={st.stationId}
                className="bg-slate-950/70 p-3 rounded-lg border border-slate-800 flex items-center justify-between"
              >
                <div>
                  <div className="font-mono font-bold text-sm text-indigo-400">{st.stationId}</div>
                  <div className="text-[10px] text-slate-500">{st.samples} test windows</div>
                </div>
                <div className="text-right">
                  <div className="text-xs font-mono font-semibold text-white">
                    RF MAE: <span className="text-indigo-400">{st.rfMae}</span>
                  </div>
                  <div className="text-[11px] font-mono text-slate-500">
                    Baseline: {st.baselineMae}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Production Live Operational Telemetry Notice */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <div className="flex items-start space-x-3">
          <div className="p-2 bg-slate-800 rounded-lg text-slate-400 mt-0.5">
            <Database className="w-5 h-5 text-indigo-400" />
          </div>
          <div className="flex-1 space-y-2">
            <h4 className="text-sm font-semibold text-white">Production Operational Telemetry & Online Accuracy</h4>
            <p className="text-xs text-slate-400 leading-relaxed">
              In real-world deployment, operational accuracy is tracked by comparing forecasted hourly intervals against actual charging session metering telemetry.
              The production database currently maintains 0 uncalibrated live physical session records; continuous telemetry ingestion will activate real-time MAE/MAPE error trajectory tracking.
            </p>
            <div className="inline-flex items-center space-x-2 text-xs font-mono text-slate-400 bg-slate-950 px-3 py-1.5 rounded border border-slate-800 mt-2">
              <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
              <span>Awaiting Continuous Operational Telemetry Stream</span>
            </div>
          </div>
        </div>
      </div>

      {/* Explicit Grounding Limitation Banner */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 text-xs text-slate-400 flex items-start space-x-3">
        <Info className="w-4 h-4 text-slate-400 flex-shrink-0 mt-0.5" />
        <div className="leading-relaxed">
          <span className="font-semibold text-slate-200">Model Artifact Limitation:</span>{" "}
          The current model artifacts were trained on calibrated historical session fixtures. In accordance with academic and engineering standards, these metrics reflect validation benchmark performance and do not represent continuous real-world field measurements.
        </div>
      </div>
    </div>
  );
};

export default ModelAccuracy;
