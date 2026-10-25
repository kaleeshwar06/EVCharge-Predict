import { useState, useEffect } from "react";

interface HealthStatus {
  service: string;
  api_version: string;
  status: string;
}

export default function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastChecked, setLastChecked] = useState<string>("");

  const checkHealth = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/healthz");
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      const data: HealthStatus = await res.json();
      setHealth(data);
      setLastChecked(new Date().toISOString());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to connect to backend");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkHealth();
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6">
      <div className="max-w-md w-full bg-slate-900 border border-slate-800 rounded-xl shadow-2xl p-6">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div>
            <h1 className="text-xl font-bold text-emerald-400">EVCharge-Predict</h1>
            <p className="text-xs text-slate-400">Demand Prediction System — Phase 1</p>
          </div>
          <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            Phase 1 Live
          </span>
        </div>

        <div className="mt-6 space-y-4">
          <div className="p-4 bg-slate-950 rounded-lg border border-slate-800/80">
            <h2 className="text-sm font-semibold text-slate-300 mb-2">Backend Service Health</h2>
            {loading && <p className="text-xs text-slate-400">Querying backend /healthz...</p>}
            {error && (
              <div className="text-xs text-rose-400 bg-rose-500/10 p-2.5 rounded border border-rose-500/20">
                <p className="font-semibold">Backend Unreachable</p>
                <p className="mt-0.5">{error}</p>
                <p className="mt-1 text-slate-400">Ensure backend is running at http://127.0.0.1:8001</p>
              </div>
            )}
            {health && (
              <dl className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <dt className="text-slate-400">Service:</dt>
                  <dd className="font-mono text-emerald-300 font-medium">{health.service}</dd>
                </div>
                <div>
                  <dt className="text-slate-400">API Version:</dt>
                  <dd className="font-mono text-emerald-300 font-medium">v{health.api_version}</dd>
                </div>
                <div>
                  <dt className="text-slate-400">Status:</dt>
                  <dd className="font-mono text-emerald-300 font-semibold uppercase">{health.status}</dd>
                </div>
                <div>
                  <dt className="text-slate-400">Endpoint:</dt>
                  <dd className="font-mono text-slate-300">/healthz</dd>
                </div>
              </dl>
            )}
          </div>

          <div className="p-4 bg-slate-950 rounded-lg border border-slate-800/80 text-xs space-y-1">
            <div className="flex justify-between text-slate-400">
              <span>Integration Contract:</span>
              <span className="font-mono text-slate-200">v1.0 (60m / 6 intervals)</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>Partner:</span>
              <span className="font-mono text-slate-200">EVCharge-Opt</span>
            </div>
            {lastChecked && (
              <div className="flex justify-between text-slate-500 pt-1">
                <span>Last verified:</span>
                <span className="font-mono">{lastChecked}</span>
              </div>
            )}
          </div>

          <button
            onClick={checkHealth}
            disabled={loading}
            className="w-full py-2 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium text-xs transition duration-150"
          >
            {loading ? "Checking..." : "Re-check Health"}
          </button>
        </div>
      </div>
    </div>
  );
}
