import React, { useState } from "react";
import { StationRead, ForecastCreateRequest, createForecast, ApiError } from "../api";
import { DEMO_STATIONS, generateDemoForecast } from "../demoService";
import { Zap, Clock, Calendar, HelpCircle, ChevronDown, ChevronUp, Layers, Info } from "lucide-react";

interface Props {
  stations: StationRead[];
  demoMode: boolean;
  onSuccess: (data: any) => void;
  setError: (msg: string | null) => void;
}

const ForecastForm: React.FC<Props> = ({ stations, demoMode, onSuccess, setError }) => {
  const [selectedStations, setSelectedStations] = useState<string[]>(["ST-001"]);
  const [scenarioId, setScenarioId] = useState<string>(() =>
    demoMode ? "scenario_demo_001" : "scenario_live_001"
  );

  // Date & Hour selectors
  const todayStr = new Date().toISOString().split("T")[0];
  const [selectedDate, setSelectedDate] = useState<string>(todayStr);
  const [selectedHour, setSelectedHour] = useState<number>(() => (new Date().getUTCHours() + 1) % 24);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [showFeatureExplainer, setShowFeatureExplainer] = useState<boolean>(false);

  const availableStations = demoMode
    ? DEMO_STATIONS
    : stations;

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
    d.setUTCHours(d.getUTCHours() + 1);
    setSelectedDate(d.toISOString().split("T")[0]);
    setSelectedHour(d.getUTCHours());
  };

  const validate = () => {
    if (availableStations.length === 0) {
      setError("No stations available. In Live Mode, stations must exist in the database and API must be authenticated. Enable Demo Mode for offline preview.");
      return false;
    }
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
    setError(null);

    // DEMO MODE: Fully isolated client-side mock simulation without invoking backend API
    if (demoMode) {
      try {
        await new Promise((r) => setTimeout(r, 400)); // natural UI delay
        const demoResult = generateDemoForecast(req);
        onSuccess(demoResult);
      } catch (err) {
        setError(String(err));
      } finally {
        setSubmitting(false);
      }
      return;
    }

    // LIVE MODE: Call backend API
    try {
      const data = await createForecast(req);
      onSuccess(data);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError(
            "Authentication required (HTTP 401): Missing Bearer token. Production forecast generation is restricted to authorized services. Switch to Demo Mode for interactive simulation."
          );
        } else if (err.status === 403) {
          setError("Forbidden (HTTP 403): Invalid API service token.");
        } else {
          try {
            const parsed = JSON.parse(err.message);
            setError(typeof parsed.detail === "string" ? parsed.detail : err.message);
          } catch {
            setError(`Error (${err.status}): ${err.message}`);
          }
        }
      } else {
        setError(String(err));
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-slate-200 space-y-6"
    >
      {demoMode && (
        <div className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg text-xs text-blue-300 flex items-center">
          <Info className="w-4 h-4 mr-2 text-blue-400 flex-shrink-0" />
          <span>
            <strong>Simulated Forecast Generator (Demo Mode):</strong> Submissions compute client-side without reaching protected production endpoints.
          </span>
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-semibold text-white flex items-center">
            <Zap className={`w-4 h-4 mr-2 ${demoMode ? "text-blue-400" : "text-emerald-400"}`} />
            Select Charging Stations ({demoMode ? "Demo Catalog" : "Live Registered"})
          </label>
          {availableStations.length > 0 && (
            <button
              type="button"
              onClick={selectAllStations}
              className={`text-xs font-medium hover:underline ${
                demoMode ? "text-blue-400" : "text-emerald-400"
              }`}
            >
              Select All
            </button>
          )}
        </div>

        {availableStations.length === 0 ? (
          <div className="p-4 bg-slate-950/70 border border-slate-800 rounded-lg text-xs text-slate-400">
            No stations available to select. In live mode, ensure the database is seeded or switch to <strong>Demo Mode</strong> to use simulated stations.
          </div>
        ) : (
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
                      ? demoMode
                        ? "bg-blue-500/10 border-blue-500/50 text-white"
                        : "bg-emerald-500/10 border-emerald-500/50 text-white"
                      : "bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700"
                  }`}
                >
                  <div>
                    <div className="font-mono font-bold text-sm">{s.station_id}</div>
                    <div className="text-xs text-slate-400 capitalize">{s.site_id || "default"}</div>
                  </div>
                  <div
                    className={`w-4 h-4 rounded flex items-center justify-center border text-xs ${
                      isSelected
                        ? demoMode
                          ? "bg-blue-500 border-blue-500 text-black font-bold"
                          : "bg-emerald-500 border-emerald-500 text-black font-bold"
                        : "border-slate-700"
                    }`}
                  >
                    {isSelected ? "✓" : ""}
                  </div>
                </button>
              );
            })}
          </div>
        )}
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

        {/* Hour Selector */}
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

      {/* Explainer */}
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
              <li><strong className="text-white">Autoregressive Historical Lags (16 features):</strong> lag arrivals and lag energy at 1h, 2h, 3h, 6h, 12h, 24h, 48h, and 168h looked up from station history.</li>
              <li><strong className="text-white">Rolling Window Statistics (6 features):</strong> rolling mean arrivals and energy over 6-hour, 24-hour, and 168-hour windows.</li>
              <li><strong className="text-white">Categorical Encoding (1 feature):</strong> learned station categorical integer embedding.</li>
            </ul>
          </div>
        )}
      </div>

      <div className="pt-2">
        <button
          type="submit"
          disabled={submitting || availableStations.length === 0}
          className={`w-full font-semibold py-2.5 px-4 rounded-lg transition-colors flex items-center justify-center space-x-2 text-white disabled:opacity-50 ${
            demoMode ? "bg-blue-600 hover:bg-blue-500" : "bg-emerald-600 hover:bg-emerald-500"
          }`}
        >
          <Zap className="w-4 h-4" />
          <span>
            {submitting
              ? "Computing..."
              : demoMode
              ? "Generate Simulated Forecast (Demo)"
              : "Generate Neural Demand Forecast (Live API)"}
          </span>
        </button>
      </div>
    </form>
  );
};

export default ForecastForm;
