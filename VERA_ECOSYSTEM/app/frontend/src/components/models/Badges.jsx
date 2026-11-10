// src/components/models/Badges.jsx
import React from "react";

const PROVIDER_COLORS = {
  openrouter: "bg-fuchsia-500/10 text-fuchsia-300 border-fuchsia-500/20",
  gemini: "bg-sky-500/10 text-sky-300 border-sky-500/20",
  nvidia: "bg-lime-500/10 text-lime-300 border-lime-500/20",
};

const LABEL_COLORS = {
  general: "bg-white/10 text-white/80 border-white/20",
  reasoning: "bg-purple-500/10 text-purple-300 border-purple-500/20",
  coding: "bg-blue-500/10 text-blue-300 border-blue-500/20",
  networking: "bg-cyan-500/10 text-cyan-300 border-cyan-500/20",
  vision: "bg-amber-500/10 text-amber-300 border-amber-500/20",
  voice: "bg-pink-500/10 text-pink-300 border-pink-500/20",
  retrieval: "bg-indigo-500/10 text-indigo-300 border-indigo-500/20",
  automation: "bg-teal-500/10 text-teal-300 border-teal-500/20",
};

export function ProviderBadge({ provider }) {
  const color = PROVIDER_COLORS[provider] || "bg-white/5 text-white/50 border-white/10";
  return (
    <span className={`text-[10px] uppercase font-mono font-medium tracking-wide px-2 py-0.5 rounded-full border ${color}`}>
      {provider}
    </span>
  );
}

export function LabelBadge({ label }) {
  const color = LABEL_COLORS[label] || "bg-white/5 text-white/50 border-white/10";
  return (
    <span className={`text-[10px] font-medium tracking-wide px-2 py-0.5 rounded-full border capitalize ${color}`}>
      {label}
    </span>
  );
}

export function StatusBadge({ enabled }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-[11px] font-medium px-2 py-0.5 rounded-full border ${
        enabled
          ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/20"
          : "bg-red-500/10 text-red-300 border-red-500/20"
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${enabled ? "bg-emerald-400" : "bg-red-400"}`} />
      {enabled ? "Enabled" : "Disabled"}
    </span>
  );
}

export function CapabilityBadge({ capability }) {
  const capMap = {
    tool_calling: { label: "Tools", color: "bg-blue-500/10 text-blue-300 border-blue-500/20" },
    streaming: { label: "Stream", color: "bg-cyan-500/10 text-cyan-300 border-cyan-500/20" },
    vision: { label: "Vision", color: "bg-amber-500/10 text-amber-300 border-amber-500/20" },
    audio: { label: "Audio", color: "bg-pink-500/10 text-pink-300 border-pink-500/20" },
    video: { label: "Video", color: "bg-purple-500/10 text-purple-300 border-purple-500/20" },
    structured_output: { label: "JSON", color: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20" },
    reasoning: { label: "Reasoning", color: "bg-indigo-500/10 text-indigo-300 border-indigo-500/20" },
    code_generation: { label: "Code", color: "bg-sky-500/10 text-sky-300 border-sky-500/20" },
  };

  const item = capMap[capability] || { label: capability, color: "bg-white/5 text-white/60 border-white/10" };

  return (
    <span className={`text-[9px] font-mono font-medium px-1.5 py-0.5 rounded border ${item.color}`}>
      {item.label}
    </span>
  );
}

export function LifecycleBadge({ status = "ACTIVE" }) {
  const norm = String(status || "ACTIVE").toUpperCase();
  const styles = {
    ACTIVE: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",
    EXPERIMENTAL: "bg-amber-500/10 text-amber-300 border-amber-500/20",
    DEPRECATED_PENDING: "bg-orange-500/10 text-orange-300 border-orange-500/20",
    DEPRECATED: "bg-red-500/10 text-red-300 border-red-500/20",
    UNVERIFIED: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
  };
  const color = styles[norm] || "bg-white/5 text-white/50 border-white/10";
  return (
    <span className={`text-[10px] font-mono tracking-wide px-2 py-0.5 rounded-full border ${color}`}>
      {norm}
    </span>
  );
}

export function HealthBadge({ status = "HEALTHY" }) {
  const norm = String(status || "HEALTHY").toUpperCase();
  const isHealthy = norm === "HEALTHY";
  const isDegraded = norm === "DEGRADED" || norm === "RECOVERING";

  const color = isHealthy
    ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/20"
    : isDegraded
    ? "bg-amber-500/10 text-amber-300 border-amber-500/20"
    : "bg-red-500/10 text-red-300 border-red-500/20";

  return (
    <span className={`inline-flex items-center gap-1.5 text-[10px] font-medium px-2 py-0.5 rounded-full border ${color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${isHealthy ? "bg-emerald-400" : isDegraded ? "bg-amber-400" : "bg-red-400"}`} />
      {norm}
    </span>
  );
}

export function CircuitBadge({ state = "CLOSED" }) {
  const norm = String(state || "CLOSED").toUpperCase();
  const isClosed = norm === "CLOSED";
  const isHalfOpen = norm === "HALF_OPEN";

  const color = isClosed
    ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/20"
    : isHalfOpen
    ? "bg-amber-500/10 text-amber-300 border-amber-500/20"
    : "bg-rose-500/10 text-rose-300 border-rose-500/20";

  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full border ${color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${isClosed ? "bg-emerald-400" : isHalfOpen ? "bg-amber-400 animate-pulse" : "bg-rose-400"}`} />
      {norm === "CLOSED" ? "Normal" : norm === "HALF_OPEN" ? "Testing (Half-Open)" : "Tripped (Open)"}
    </span>
  );
}
