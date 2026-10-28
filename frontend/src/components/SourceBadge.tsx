import React from "react";

type Source = "live" | "demo" | "unavailable" | "simulated";

interface Props {
  source: Source;
}

const badgeStyles: Record<Source, string> = {
  live: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  demo: "bg-blue-500/10 text-blue-400 border-blue-500/30",
  unavailable: "bg-rose-500/10 text-rose-400 border-rose-500/30",
  simulated: "bg-amber-500/10 text-amber-400 border-amber-500/30",
};

const labelMap: Record<Source, string> = {
  live: "LIVE API DATA",
  demo: "LOCAL DEMO DATA",
  unavailable: "UNAVAILABLE / AUTH REQUIRED",
  simulated: "SIMULATED",
};

const SourceBadge: React.FC<Props> = ({ source }) => {
  return (
    <span className={`inline-flex items-center px-2.5 py-1 text-xs font-semibold rounded-full border ${badgeStyles[source]}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current mr-1.5 opacity-80 animate-pulse" />
      {labelMap[source]}
    </span>
  );
};

export default SourceBadge;
