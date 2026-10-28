import React, { useState } from "react";
import { StationRead, ForecastCreateRequest, createForecast, ApiError } from "../api";
import { Zap, Clock, Calendar, HelpCircle, ChevronDown, ChevronUp, Layers } from "lucide-react";

interface Props {
  stations: StationRead[];
  demoMode: boolean;
  onSuccess: (data: any) => void;
  setError: (msg: string | null) => void;
}

const ForecastForm: React.FC<Props> = ({ stations, demoMode, onSuccess, setError }) => {
  const [selectedStations, setSelectedStations] = useState<string[]>([]);
  const [scenarioId, setScenarioId] = useState<string>("scenario_live_001");
  
  // Date & Hour selectors
  const todayStr = new Date().toISOString().split("T")[0];
  const [selectedDate, setSelectedDate] = useState<string>(todayStr);
  const [selectedHour, setSelectedHour] = useState<number>(() => (new Date().getHours() + 1) % 24);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [showFeatureExplainer, setShowFeatureExplainer] = useState<boolean>(false);

  const toggleStation = (id: string) => {
    setSelectedStations((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
    );
  };

  const selectAllStations = () => {
    const all = availableStations.map((s) => s.station_id);
    setSelectedStations(all);
  };

  const setNextAlignedHour = () => {
    const d = new Date();
    d.setHours(d.getHours() + 1);
    setSelectedDate(d.toISOString().split("T")[0]);
    setSelectedHour(d.getHours());
  };

  const validate = () => {
    if (selectedStations.length === 0) {
      setError("Please select at least one charging station.");
      return false;
    }
    if (!scenarioId.trim()) {
      setError("Please provide a Scenario ID.");
      return false;
    }
    if (!selectedDate) {
      setError("Please choose a valid forecast start date.");
      return false;
    }
    setError(null);
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    // Guaranteed hour-aligned UTC boundary: YYYY-MM-DDTXX:00:00Z
    const pad = (n: number) => n.toString().padStart(2, "0");
    const isoStart = `${selectedDate}T${pad(selectedHour)}:00:00Z`;

    const req: ForecastCreateRequest = {
      scenario_id: scenarioId.trim(),
      station_ids: selectedStations,
      forecast_start: isoStart,
      interval_minutes: 60,
      horizon_intervals: 6,
    };
    setSubmitting(true);
    try {
      const data = await createForecast(req);
      onSuccess(data);
    } catch (err) {
      if (err instanceof ApiError) {
        try {
          const parsed = JSON.parse(err.message);
          setError(typeof parsed.detail === "string" ? parsed.detail : err.message);
        } catch {
          setError(`${err.status}: ${err.message}`);
        }
      } else {
        setError(String(err));
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (demoMode) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-slate-300">
        <p className="text-sm">Demo mode is active — interactive forecast generation disabled.</p>
      </div>
    );
  }

  const availableStations = stations.length > 0 ? stations : [
    { station_id: "ST-001", source_station_id: "src-1", site_id: "caltech", id: 1, created_at: "", updated_at: "" },
    { station_id: "ST-002", source_station_id: "src-2", site_id: "caltech", id: 2, created_at: "", updated_at: "" },
    { station_id: "ST-003", source_station_id: "demo-src-ST-003", site_id: "demo-site", id: 3, created_at: "", updated_at: "" },
  ];

  return (
    <form onSubmit={handleSubmit} className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-slate-200 space-y-6">
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-semibold text-white flex items-center">
            <Zap className="w-4 h-4 mr-2 text-emerald-400" /> Select Charging Stations for Forecast
          </label>
          <button
            type="button"
            onClick={selectAllStations}
            className="text-xs text-emerald-400 hover:text-emerald-300 font-medium"
          >
            Select All
          </button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {availableStations.map((s) => {
            const isSelected = selectedStations.includes(s.station_id);
            return (
              <button
                type="button"
                key={s.station_id}
                onClick={() => toggleStation(s.station_id)}
                className={`p-3 rounded-lg border text-left transition-all flex items-center justify-between ${
                  isSelected
                    ? "bg-emerald-500/10 border-emerald-500/50 text-white"
                    : "bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700"
                }`}
              >
                <div>
                  <div className="font-mono font-bold text-sm">{s.station_id}</div>
                  <div className="text-xs text-slate-400 capitalize">{s.site_id || "default"}</div>
                </div>
                <div className={`w-4 h-4 rounded flex items-center justify-center border text-xs ${
                  isSelected ? "bg-emerald-500 border-emerald-500 text-black font-bold" : "border-slate-700"
                }`}>
                  {isSelected ? "✓" : ""}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Scenario ID */}
        <div>
          <label className="block text-sm font-semibold text-white mb-1.5 flex items-center">
            <Layers className="w-4 h-4 mr-2 text-amber-400" /> Scenario Identifier
          </label>
          <input
            type="text"
            value={scenarioId}
            onChange={(e) => setScenarioId(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
            placeholder="scenario_001"
            required
          />
        </div>

        {/* Date Selector */}
        <div>
          <label className="block text-sm font-semibold text-white mb-1.5 flex items-center">
            <Calendar className="w-4 h-4 mr-2 text-indigo-400" /> Forecast Date
          </label>
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 [color-scheme:dark]"
          />
        </div>

        {/* Hour Selector (Enforces clean 00-23 hour alignment) */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-sm font-semibold text-white flex items-center">
              <Clock className="w-4 h-4 mr-2 text-indigo-400" /> Start Hour (UTC)
            </label>
            <button
              type="button"
              onClick={setNextAlignedHour}
              className="text-xs text-indigo-400 hover:text-indigo-300 underline"
            >
              Current+1
            </button>
          </div>
          <select
            value={selectedHour}
            onChange={(e) => setSelectedHour(parseInt(e.target.value, 10))}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            {Array.from({ length: 24 }).map((_, h) => {
              const pad = (n: number) => n.toString().padStart(2, "0");
              return (
                <option key={h} value={h}>
                  {pad(h)}:00 UTC ({h < 12 ? `${h === 0 ? 12 : h} AM` : `${h === 12 ? 12 : h - 12} PM`})
                </option>
              );
            })}
          </select>
        </div>
      </div>

      {/* Explainer for the 30 ML Features */}
      <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-3 text-xs">
        <button
          type="button"
          onClick={() => setShowFeatureExplainer(!showFeatureExplainer)}
          className="w-full flex items-center justify-between text-slate-300 hover:text-white"
        >
          <span className="flex items-center space-x-1.5">
            <HelpCircle className="w-4 h-4 text-emerald-400" />
            <span className="font-semibold text-emerald-400">Why are there only 2 input parameters here?</span>
            <span className="text-slate-400">(How the 30 ML features are constructed)</span>
          </span>
          {showFeatureExplainer ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>

        {showFeatureExplainer && (
          <div className="mt-3 pt-3 border-t border-slate-800 text-slate-400 space-y-2 leading-relaxed">
            <p>
              When you submit a request with <strong className="text-slate-200">Station ID</strong> and <strong className="text-slate-200">Forecast Start Date/Time</strong>, the ML engine dynamically computes the complete <strong className="text-emerald-400">30 engineered features</strong> in the backend without requiring manual user input:
            </p>
            <ul className="list-disc list-inside space-y-1 pl-1 text-slate-300">
              <li><strong className="text-white">Calendar & Temporal (7 features):</strong> hour, day-of-week, is_weekend, cyclical harmonic encodings (sin_hour, cos_hour, sin_dayofweek, cos_dayofweek).</li>
              <li><strong className="text-white">Autoregressive Historical Lags (16 features):</strong> lag arrivals and lag energy at 1h, 2h, 3h, 6h, 12h, 24h, 48h, and 168h (past week) looked up from the station history.</li>
              <li><strong className="text-white">Rolling Window Statistics (6 features):</strong> rolling mean arrivals and energy over 6-hour, 24-hour, and 168-hour windows.</li>
              <li><strong className="text-white">Categorical Encoding (1 feature):</strong> learned station categorical integer embedding.</li>
            </ul>
          </div>
        )}
      </div>

      <div className="pt-2">
        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold py-2.5 px-4 rounded-lg transition-colors flex items-center justify-center space-x-2"
        >
          <Zap className="w-4 h-4" />
          <span>{submitting ? "Computing Inference..." : "Generate Neural Demand Forecast"}</span>
        </button>
      </div>
    </form>
  );
};

export default ForecastForm;
