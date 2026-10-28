import { useState, useEffect } from "react";
import {
  Activity,
  Zap,
  Server,
  Cpu,
  BarChart3,
  MessageSquare,
  ShieldAlert,
  Layers,
  CheckCircle2,
  RefreshCw,
} from "lucide-react";
import StationTable from "./components/StationTable";
import ForecastForm from "./components/ForecastForm";
import ForecastChart from "./components/ForecastChart";
import OptimizerPreview from "./components/OptimizerPreview";
import FeedbackForm from "./components/FeedbackForm";
import SourceBadge from "./components/SourceBadge";
import { fetchStations, StationRead, ApiError, API_BASE_URL, ForecastDetailRead, AdjustedDemandResponse } from "./api";
import { DEMO_STATIONS } from "./demoService";

interface HealthResponse {
  service?: string;
  api_version?: string;
  status?: string;
  database_ready?: boolean;
  models_loaded?: boolean;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<
    "dashboard" | "stations" | "forecast" | "optimizer" | "feedback" | "health"
  >("dashboard");
  const [demoMode, setDemoMode] = useState<boolean>(true); // Default to safe demo mode

  // Global health checks
  const [healthData, setHealthData] = useState<HealthResponse | null>(null);
  const [readyData, setReadyData] = useState<HealthResponse | null>(null);

  // Stations data
  const [stations, setStations] = useState<StationRead[]>([]);
  const [stationsLoading, setStationsLoading] = useState<boolean>(false);
  const [stationsError, setStationsError] = useState<string | null>(null);

  // Forecast data
  const [forecast, setForecast] = useState<ForecastDetailRead | null>(null);
  const [forecastError, setForecastError] = useState<string | null>(null);

  // Adjusted demand data
  const [adjustedDemand, setAdjustedDemand] = useState<AdjustedDemandResponse | null>(null);

  const checkLiveApi = async () => {
    try {
      const hRes = await fetch(`${API_BASE_URL}/healthz`);
      if (hRes.ok) {
        const hJson = await hRes.json();
        setHealthData(hJson);
      }
      const rRes = await fetch(`${API_BASE_URL}/readyz`).catch(() => null);
      if (rRes && rRes.ok) {
        const rJson = await rRes.json();
        setReadyData(rJson);
      }
    } catch (e) {
      console.error("Health check error:", e);
    }
  };

  const loadStations = async () => {
    if (demoMode) {
      setStations(DEMO_STATIONS);
      setStationsError(null);
      setStationsLoading(false);
      return;
    }

    setStationsLoading(true);
    setStationsError(null);
    try {
      const data = await fetchStations();
      setStations(data);
      setStationsError(null);
    } catch (e) {
      setStations([]); // Do NOT fallback to demo stations on live API failure
      if (e instanceof ApiError) {
        if (e.status === 401) {
          setStationsError(
            "Authentication required (HTTP 401). Production API endpoints require a service token. Switch to Demo Mode for offline exploration."
          );
        } else if (e.status === 403) {
          setStationsError("Forbidden (HTTP 403): Invalid API service token.");
        } else {
          setStationsError(`Backend error (${e.status}): ${e.message}`);
        }
      } else {
        setStationsError(`Network/API error: ${String(e)}`);
      }
    } finally {
      setStationsLoading(false);
    }
  };

  useEffect(() => {
    checkLiveApi();
  }, []);

  useEffect(() => {
    loadStations();
  }, [demoMode]);

  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: BarChart3 },
    { id: "stations", label: "Stations", icon: Server },
    { id: "forecast", label: "Forecast", icon: Zap },
    { id: "optimizer", label: "Optimizer", icon: Cpu },
    { id: "feedback", label: "Feedback", icon: MessageSquare },
    { id: "health", label: "Health", icon: Activity },
  ] as const;

  const renderTab = () => {
    switch (activeTab) {
      case "dashboard":
        return (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                <div className="flex items-center justify-between text-slate-400 mb-2">
                  <span className="text-sm font-medium">Station Inventory</span>
                  <Server className="w-5 h-5 text-emerald-400" />
                </div>
                <div className="text-2xl font-bold text-white font-mono">
                  {demoMode ? `${DEMO_STATIONS.length} (Demo)` : stations.length}
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  {demoMode ? "Isolated Simulated Register" : "Live Production Database"}
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                <div className="flex items-center justify-between text-slate-400 mb-2">
                  <span className="text-sm font-medium">Inference Backend</span>
                  <Activity className="w-5 h-5 text-indigo-400" />
                </div>
                <div className="text-2xl font-bold text-white flex items-center space-x-2">
                  <span
                    className={`w-2.5 h-2.5 rounded-full ${
                      healthData?.status === "ok" ? "bg-emerald-400 animate-pulse" : "bg-amber-400"
                    }`}
                  />
                  <span className="text-lg">
                    {healthData?.status === "ok" ? "ONLINE" : "CHECKING"}
                  </span>
                </div>
                <div className="text-xs text-slate-500 mt-1 font-mono">v{healthData?.api_version || "1.0"}</div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                <div className="flex items-center justify-between text-slate-400 mb-2">
                  <span className="text-sm font-medium">Downstream Partner</span>
                  <Cpu className="w-5 h-5 text-amber-400" />
                </div>
                <div className="text-xl font-bold text-amber-400 font-mono">EVCharge-Opt</div>
                <div className="text-xs text-slate-500 mt-1">Simulated Feedback Contract</div>
              </div>
            </div>

            {demoMode && (
              <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4 text-blue-200 flex items-start space-x-3">
                <div className="p-1 bg-blue-500/20 rounded text-blue-400 mt-0.5">
                  <Layers className="w-4 h-4" />
                </div>
                <div className="text-xs leading-relaxed">
                  <span className="font-semibold text-white">Demo Mode Active:</span> All forecast and feedback operations run entirely client-side using deterministic simulation models. No protected backend endpoints are invoked, ensuring zero unauthorized calls or credential leakage.
                </div>
              </div>
            )}

            {!demoMode && stationsError && (
              <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 text-amber-200 flex items-start space-x-3">
                <div className="p-1 bg-amber-500/20 rounded text-amber-400 mt-0.5">
                  <ShieldAlert className="w-4 h-4" />
                </div>
                <div className="text-xs leading-relaxed">
                  <span className="font-semibold text-white">Live API Authentication Notice:</span> Protected endpoints require service-to-service Bearer authentication. For browser demonstration without credentials, enable <strong>Demo Mode</strong> in the top-right toggle.
                </div>
              </div>
            )}

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
              <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-4">
                <h3 className="font-semibold text-white flex items-center">
                  <Layers className="w-5 h-5 mr-2 text-indigo-400" />
                  System Overview & Active Workflow
                </h3>
                <SourceBadge source={demoMode ? "demo" : stationsError ? "unavailable" : "live"} />
              </div>
              <p className="text-slate-300 text-sm leading-relaxed mb-4">
                EVCharge-Predict delivers neural demand predictions for charging stations. Downstream
                optimizers (such as EVCharge-Opt) schedule power allocations based on these predictions
                and submit runtime feedback back to refine demand trajectories.
              </p>
              <div className="flex flex-wrap gap-3">
                <button
                  onClick={() => setActiveTab("stations")}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-lg transition-colors flex items-center"
                >
                  <Server className="w-4 h-4 mr-2 text-emerald-400" /> View Stations
                </button>
                <button
                  onClick={() => setActiveTab("forecast")}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors flex items-center"
                >
                  <Zap className="w-4 h-4 mr-2" /> Run Forecast
                </button>
                <button
                  onClick={() => setActiveTab("optimizer")}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors flex items-center"
                >
                  <Cpu className="w-4 h-4 mr-2" /> Optimizer Dispatches
                </button>
              </div>
            </div>
          </div>
        );

      case "stations":
        return (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-white">Charging Stations</h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  {demoMode ? "Simulated ST-xxx station catalog (Demo Mode)" : "Canonical ST-xxx station register from live backend"}
                </p>
              </div>
              <button
                onClick={loadStations}
                disabled={stationsLoading}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded-lg flex items-center disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${stationsLoading ? "animate-spin" : ""}`} /> Refresh
              </button>
            </div>
            <StationTable
              stations={stations}
              loading={stationsLoading}
              error={stationsError}
              demoMode={demoMode}
            />
          </div>
        );

      case "forecast":
        return (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-white">Demand Forecast Generator</h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Generate hour-aligned multi-horizon arrival and energy predictions
                </p>
              </div>
              <SourceBadge source={demoMode ? "demo" : forecastError ? "unavailable" : "live"} />
            </div>

            {forecastError && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-300 flex items-center">
                <ShieldAlert className="w-4 h-4 mr-2 text-red-400 flex-shrink-0" />
                <span>{forecastError}</span>
              </div>
            )}

            <ForecastForm
              stations={stations}
              demoMode={demoMode}
              onSuccess={(data) => {
                setForecast(data);
                setForecastError(null);
              }}
              setError={setForecastError}
            />

            {forecast && <ForecastChart forecast={forecast} demoMode={demoMode} />}
          </div>
        );

      case "optimizer":
        return (
          <div className="space-y-4">
            <div>
              <h2 className="text-xl font-bold text-white">EVCharge-Opt Integration</h2>
              <p className="text-xs text-slate-400 mt-0.5">Simulated power allocation and grid curtailment schedules</p>
            </div>
            <OptimizerPreview />
          </div>
        );

      case "feedback":
        return (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-white">Optimization Feedback</h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Ingest feedback from optimizer and inspect adjusted demand curves
                </p>
              </div>
              <SourceBadge source={demoMode ? "demo" : "live"} />
            </div>

            <FeedbackForm
              onAdjustedDemand={(data) => setAdjustedDemand(data)}
              demoMode={demoMode}
              forecast={forecast}
            />

            {adjustedDemand && (
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-slate-200">
                <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800">
                  <h3 className="font-semibold text-emerald-400">Adjusted Demand Profile</h3>
                  <SourceBadge source={demoMode ? "demo" : "live"} />
                </div>
                <pre className="p-4 bg-slate-950 rounded-lg text-xs font-mono text-emerald-300 overflow-x-auto border border-slate-800/80">
                  {JSON.stringify(adjustedDemand, null, 2)}
                </pre>
              </div>
            )}
          </div>
        );

      case "health":
        return (
          <div className="space-y-4">
            <div>
              <h2 className="text-xl font-bold text-white">System Probes & Health Status</h2>
              <p className="text-xs text-slate-400 mt-0.5">Real-time status of backend orchestrator and components (Public probe endpoints)</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                <div className="flex items-center justify-between mb-3 pb-2 border-b border-slate-800">
                  <h3 className="font-semibold text-white flex items-center">
                    <CheckCircle2 className="w-4 h-4 mr-2 text-emerald-400" />
                    Liveness (/healthz)
                  </h3>
                  <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-mono">
                    {healthData?.status === "ok" ? "200 OK" : "CHECKING"}
                  </span>
                </div>
                <pre className="text-xs font-mono bg-slate-950 p-3 rounded-lg border border-slate-800/60 text-slate-300 overflow-x-auto">
                  {JSON.stringify(healthData, null, 2)}
                </pre>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                <div className="flex items-center justify-between mb-3 pb-2 border-b border-slate-800">
                  <h3 className="font-semibold text-white flex items-center">
                    <CheckCircle2 className="w-4 h-4 mr-2 text-indigo-400" />
                    Readiness (/readyz)
                  </h3>
                  <span className="text-xs px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 font-mono">
                    {readyData?.status === "ready" ? "200 OK" : "UNREADY / 503"}
                  </span>
                </div>
                <pre className="text-xs font-mono bg-slate-950 p-3 rounded-lg border border-slate-800/60 text-slate-300 overflow-x-auto">
                  {JSON.stringify(readyData, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        );
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-400 to-indigo-600 flex items-center justify-center font-black text-black text-lg">
              ⚡
            </div>
            <div>
              <h1 className="font-bold text-lg text-white leading-tight">EVCharge-Predict</h1>
              <div className="text-[10px] text-slate-400 uppercase tracking-widest font-mono">
                Demand Forecasting & Optimization
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            <label className="flex items-center space-x-2 text-xs bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg cursor-pointer hover:border-slate-700 transition-colors">
              <input
                type="checkbox"
                checked={demoMode}
                onChange={(e) => setDemoMode(e.target.checked)}
                className="rounded accent-emerald-500"
              />
              <span className={demoMode ? "text-blue-400 font-medium" : "text-slate-400"}>
                {demoMode ? "Demo Mode (Active)" : "Live API Mode"}
              </span>
            </label>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        <nav className="flex space-x-1 border-b border-slate-800/80 pb-3 mb-6 overflow-x-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                  isActive
                    ? "bg-slate-800 text-white border border-slate-700/60 shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? "text-emerald-400" : "text-slate-500"}`} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <main>{renderTab()}</main>
      </div>
    </div>
  );
}
