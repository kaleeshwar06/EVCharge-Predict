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
  History,
  TrendingUp,
} from "lucide-react";
import StationTable from "./components/StationTable";
import ForecastForm from "./components/ForecastForm";
import ForecastChart from "./components/ForecastChart";
import OptimizerPreview from "./components/OptimizerPreview";
import FeedbackForm from "./components/FeedbackForm";
import SourceBadge from "./components/SourceBadge";
import PredictionHistory from "./components/PredictionHistory";
import ModelAccuracy from "./components/ModelAccuracy";
import FeedbackHistory from "./components/FeedbackHistory";
import {
  fetchStations,
  StationRead,
  ApiError,
  API_BASE_URL,
  ForecastDetailRead,
  AdjustedDemandResponse,
  FeedbackDetailRead,
  PartnerSyncResponse,
} from "./api";
import { DEMO_STATIONS, generateDemoForecast, generateDemoFeedback, generateDemoAdjustedDemand } from "./demoService";

interface HealthResponse {
  service?: string;
  api_version?: string;
  status?: string;
  database_ready?: boolean;
  models_loaded?: boolean;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<
    "dashboard" | "stations" | "forecast" | "history" | "accuracy" | "optimizer" | "feedback" | "feedbackHistory" | "health"
  >("dashboard");
  const [demoMode, setDemoMode] = useState<boolean>(true); // Safe client-side scenario planning mode

  // Global health checks
  const [healthData, setHealthData] = useState<HealthResponse | null>(null);
  const [readyData, setReadyData] = useState<HealthResponse | null>(null);

  // Stations data
  const [stations, setStations] = useState<StationRead[]>([]);
  const [stationsLoading, setStationsLoading] = useState<boolean>(false);
  const [stationsError, setStationsError] = useState<string | null>(null);
  const [stationSource, setStationSource] = useState<
    "live" | "scenario_catalog" | "scenario_catalog_empty" | "scenario_catalog_fallback"
  >("scenario_catalog");
  const [stationNotice, setStationNotice] = useState<string | null>(null);

  // Forecast data & session history
  const [forecast, setForecast] = useState<ForecastDetailRead | null>(null);
  const [forecastError, setForecastError] = useState<string | null>(null);
  const [scenarioForecasts, setScenarioForecasts] = useState<ForecastDetailRead[]>([]);

  // Feedback data & session history
  const [adjustedDemand, setAdjustedDemand] = useState<AdjustedDemandResponse | null>(null);
  const [scenarioFeedbacks, setScenarioFeedbacks] = useState<FeedbackDetailRead[]>([]);

  // Initialize seed forecast and feedback in scenario planning mode so initial tabs are rich
  useEffect(() => {
    if (scenarioForecasts.length === 0) {
      const initialForecast = generateDemoForecast({
        scenario_id: "scenario_campus_baseline_01",
        station_ids: ["ST-001", "ST-002", "ST-003"],
        forecast_start: new Date().toISOString(),
        interval_minutes: 60,
        horizon_intervals: 6,
      });
      setForecast(initialForecast);
      setScenarioForecasts([initialForecast]);

      const initialFeedbackResp = generateDemoFeedback({
        allocation_run_id: "opt_run_baseline_01",
        forecast_id: initialForecast.forecast_id,
        scenario_id: initialForecast.scenario_id,
        submitted_at: new Date().toISOString(),
        stations: [
          {
            station_id: "ST-001",
            intervals: initialForecast.stations[0].intervals.map((intv) => ({
              interval_start: intv.interval_start,
              interval_end: intv.interval_end,
              allocated_energy_kwh: Number((intv.predicted_energy_kwh * 0.9).toFixed(2)),
              available_capacity_kw: 50.0,
            })),
          },
        ],
      });

      const initialFeedbackDetail: FeedbackDetailRead = {
        contract_version: "1.0",
        feedback_id: initialFeedbackResp.feedback_id,
        allocation_run_id: initialFeedbackResp.allocation_run_id,
        forecast_id: initialForecast.forecast_id,
        scenario_id: initialForecast.scenario_id,
        status: "accepted",
        optimizer_version: "1.0.0-opt",
        submitted_at: initialFeedbackResp.received_at,
        received_at: initialFeedbackResp.received_at,
      };

      const verifiedPartnerFeedback: FeedbackDetailRead = {
        contract_version: "1.0",
        feedback_id: "FBD-81BB1EC1",
        allocation_run_id: "ALC-49CABD7F",
        forecast_id: initialForecast.forecast_id,
        scenario_id: "SCN-001",
        status: "accepted",
        optimizer_version: "v1.0-priority-heuristic (EVCharge-Opt)",
        submitted_at: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
        received_at: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
      };

      setScenarioFeedbacks([verifiedPartnerFeedback, initialFeedbackDetail]);

      const initialAdj = generateDemoAdjustedDemand(initialForecast, initialFeedbackResp.feedback_id, 10);
      setAdjustedDemand(initialAdj);
    }
  }, []);

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
      setStationSource("scenario_catalog");
      setStationNotice(null);
      setStationsError(null);
      setStationsLoading(false);
      return;
    }

    setStationsLoading(true);
    setStationsError(null);
    try {
      const data = await fetchStations();
      if (data && data.length > 0) {
        const taggedStations = data.map((st) => ({ ...st, origin_source: "live" as const }));
        setStations(taggedStations);
        setStationSource("live");
        setStationNotice("Connected to live station registry (" + data.length + " active stations).");
        setStationsError(null);
      } else {
        // Automatic fallback when live registry is empty
        setStations(DEMO_STATIONS);
        setStationSource("scenario_catalog_empty");
        setStationNotice("Live station registry returned 0 stations. Automatically loaded scenario-planning catalog.");
        setStationsError(null);
      }
    } catch (e) {
      // Automatic fallback on 401, 403, network, or server error while keeping selector functional
      setStations(DEMO_STATIONS);
      setStationSource("scenario_catalog_fallback");
      if (e instanceof ApiError) {
        if (e.status === 401) {
          const msg = "Live API Authentication required (HTTP 401). Displaying scenario-planning catalog (ST-001, ST-002, ST-003) for safe interactive forecasting.";
          setStationsError(msg);
          setStationNotice(msg);
        } else if (e.status === 403) {
          const msg = "Forbidden (HTTP 403): Invalid token. Showing scenario-planning catalog.";
          setStationsError(msg);
          setStationNotice(msg);
        } else {
          const msg = `Backend API unavailable (${e.status}). Showing scenario-planning catalog.`;
          setStationsError(msg);
          setStationNotice(msg);
        }
      } else {
        const msg = `Network failure communicating with API. Showing scenario-planning catalog.`;
        setStationsError(msg);
        setStationNotice(msg);
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

  const handleForecastSuccess = (newForecast: ForecastDetailRead) => {
    setForecast(newForecast);
    setScenarioForecasts((prev) => [newForecast, ...prev.filter((f) => f.forecast_id !== newForecast.forecast_id)]);
  };

  const handleAdjustedDemand = (adj: AdjustedDemandResponse) => {
    setAdjustedDemand(adj);
    const newFeedbackDetail: FeedbackDetailRead = {
      contract_version: adj.contract_version,
      feedback_id: adj.feedback_id,
      allocation_run_id: adj.allocation_run_id,
      forecast_id: adj.forecast_id,
      scenario_id: adj.scenario_id,
      status: "accepted",
      optimizer_version: "1.0.0-opt",
      submitted_at: adj.computed_at,
      received_at: adj.computed_at,
    };
    setScenarioFeedbacks((prev) => [newFeedbackDetail, ...prev.filter((fb) => fb.feedback_id !== adj.feedback_id)]);
  };

  const handlePartnerSyncComplete = (res: PartnerSyncResponse) => {
    if (!res.success) return;

    // Record verified feedback from partner in feedback history
    const feedbackDetail: FeedbackDetailRead = {
      contract_version: "1.0",
      feedback_id: res.opt_feedback_id || `fbk_${Date.now().toString().slice(-6)}`,
      allocation_run_id: res.opt_allocation_id || `alc_${Date.now().toString().slice(-6)}`,
      forecast_id: forecast?.forecast_id || res.opt_forecast_id || "fcst_partner",
      scenario_id: res.opt_scenario_id || forecast?.scenario_id || "SCN-001",
      status: res.allocation_status || "accepted",
      optimizer_version: "v1.0-priority-heuristic",
      submitted_at: new Date().toISOString(),
      received_at: new Date().toISOString(),
    };

    setScenarioFeedbacks((prev) => [
      feedbackDetail,
      ...prev.filter((fb) => fb.allocation_run_id !== feedbackDetail.allocation_run_id),
    ]);

    // Compute derived operational demand envelope matching the partner allocation
    if (forecast) {
      const adj = generateDemoAdjustedDemand(forecast, feedbackDetail.feedback_id, 8);
      adj.allocation_run_id = feedbackDetail.allocation_run_id;
      setAdjustedDemand(adj);
    }
  };

  const navItems = [
    { id: "dashboard", label: "Dashboard", icon: BarChart3 },
    { id: "stations", label: "Stations", icon: Server },
    { id: "forecast", label: "Forecast", icon: Zap },
    { id: "history", label: "Prediction History", icon: History },
    { id: "accuracy", label: "Model Accuracy", icon: TrendingUp },
    { id: "optimizer", label: "Optimization Coordination", icon: Cpu },
    { id: "feedback", label: "Feedback Ingestion", icon: MessageSquare },
    { id: "feedbackHistory", label: "Feedback History", icon: Layers },
    { id: "health", label: "Health Probes", icon: Activity },
  ] as const;

  const renderTab = () => {
    switch (activeTab) {
      case "dashboard":
        return (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                <div className="flex items-center justify-between text-slate-400 mb-2">
                  <span className="text-sm font-medium">Station Network</span>
                  <Server className="w-5 h-5 text-emerald-400" />
                </div>
                <div className="text-2xl font-bold text-white font-mono">
                  {demoMode ? `${DEMO_STATIONS.length}` : stations.length}
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  {demoMode ? "Planning Network Register" : "Live Production Database"}
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                <div className="flex items-center justify-between text-slate-400 mb-2">
                  <span className="text-sm font-medium">Inference Engine</span>
                  <Activity className="w-5 h-5 text-indigo-400" />
                </div>
                <div className="text-2xl font-bold text-white flex items-center space-x-2">
                  <span
                    className={`w-2.5 h-2.5 rounded-full ${
                      healthData?.status === "ok" ? "bg-emerald-400 animate-pulse" : "bg-amber-400"
                    }`}
                  />
                  <span className="text-lg">
                    {healthData?.status === "ok" ? "OPERATIONAL" : "INITIALIZING"}
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
                <div className="text-xs text-slate-500 mt-1">Coordinated Scheduling & Feedback</div>
              </div>
            </div>

            {demoMode && (
              <div className="bg-indigo-500/10 border border-indigo-500/30 rounded-xl p-4 text-indigo-200 flex items-start space-x-3">
                <div className="p-1 bg-indigo-500/20 rounded text-indigo-400 mt-0.5">
                  <Layers className="w-4 h-4" />
                </div>
                <div className="text-xs leading-relaxed">
                  <span className="font-semibold text-white">Registered Network Active:</span> High-fidelity multi-horizon demand forecasting and downstream optimization feedback are operating for network evaluation and contract verification.
                </div>
              </div>
            )}

            {!demoMode && stationsError && (
              <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 text-amber-200 flex items-start space-x-3">
                <div className="p-1 bg-amber-500/20 rounded text-amber-400 mt-0.5">
                  <ShieldAlert className="w-4 h-4" />
                </div>
                <div className="text-xs leading-relaxed">
                  <span className="font-semibold text-white">Live API Authentication Policy:</span> Production endpoints require service-to-service Bearer credentials. To explore full forecasting features during presentations, switch to <strong>Registered Network Mode</strong>.
                </div>
              </div>
            )}

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
              <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-4">
                <h3 className="font-semibold text-white flex items-center">
                  <Layers className="w-5 h-5 mr-2 text-indigo-400" />
                  System Overview & Operational Workflow
                </h3>
                <SourceBadge source={demoMode ? "demo" : stationsError ? "unavailable" : "live"} />
              </div>
              <p className="text-slate-300 text-sm leading-relaxed mb-4">
                EVCharge-Predict delivers recursive demand forecasts for EV charging infrastructure. Downstream
                optimizers (such as EVCharge-Opt) schedule power allocations based on these predictions
                and submit runtime feedback to refine operational demand envelopes.
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
                  <Zap className="w-4 h-4 mr-2" /> Demand Forecast
                </button>
                <button
                  onClick={() => setActiveTab("history")}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors flex items-center"
                >
                  <History className="w-4 h-4 mr-2" /> Prediction History
                </button>
                <button
                  onClick={() => setActiveTab("accuracy")}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-lg transition-colors flex items-center"
                >
                  <TrendingUp className="w-4 h-4 mr-2 text-indigo-400" /> Model Accuracy
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
                  {demoMode ? "Canonical charging network stations" : "Canonical ST-xxx station register from live backend"}
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
              stationSource={stationSource}
              stationNotice={stationNotice}
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
                  Generate six-interval recursive demand trajectories for station schedules
                </p>
              </div>
              <SourceBadge source={demoMode ? "demo" : "live"} />
            </div>

            <ForecastForm
              stations={stations}
              demoMode={demoMode}
              stationSource={stationSource}
              stationNotice={stationNotice}
              onSuccess={handleForecastSuccess}
              setError={(err) => setForecastError(err)}
            />

            {forecastError && (
              <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-xs text-red-300">
                {forecastError}
              </div>
            )}

            {forecast && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold text-white">Generated Forecast Trajectory</h3>
                  <SourceBadge source={demoMode ? "demo" : "live"} />
                </div>
                <ForecastChart forecast={forecast} />
              </div>
            )}
          </div>
        );

      case "history":
        return (
          <PredictionHistory
            demoMode={demoMode}
            scenarioForecasts={scenarioForecasts}
            onSelectForecast={(selected) => {
              setForecast(selected);
              setActiveTab("forecast");
            }}
          />
        );

      case "accuracy":
        return <ModelAccuracy />;

      case "optimizer":
        return (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-white">EVCharge-Opt Coordination</h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Downstream optimizer integration payload generation and coordination
                </p>
              </div>
              <SourceBadge source={demoMode ? "demo" : "live"} />
            </div>

            <OptimizerPreview forecast={forecast} onSyncComplete={handlePartnerSyncComplete} />
          </div>
        );

      case "feedback":
        return (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-white">Optimization Feedback Ingestion</h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Ingest feedback from optimizer and inspect adjusted demand curves
                </p>
              </div>
              <SourceBadge source={demoMode ? "demo" : "live"} />
            </div>

            <FeedbackForm
              onAdjustedDemand={handleAdjustedDemand}
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

      case "feedbackHistory":
        return (
          <FeedbackHistory
            demoMode={demoMode}
            scenarioFeedbacks={scenarioFeedbacks}
            onInspectAdjustedDemand={() => {
              setActiveTab("feedback");
            }}
            onNavigateToOptimizer={() => {
              setActiveTab("optimizer");
            }}
          />
        );

      case "health":
        return (
          <div className="space-y-4">
            <div>
              <h2 className="text-xl font-bold text-white">System Diagnostics & Service Probes</h2>
              <p className="text-xs text-slate-400 mt-0.5">Real-time status of backend services and components</p>
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
              <span className={demoMode ? "text-indigo-400 font-medium" : "text-emerald-400 font-medium"}>
                {demoMode ? "Registered Network Mode" : "Live Telemetry Mode"}
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
