// src/components/models/Badges.jsx
import React from "react";

const PROVIDER_COLORS = {
  ollama: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",
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
