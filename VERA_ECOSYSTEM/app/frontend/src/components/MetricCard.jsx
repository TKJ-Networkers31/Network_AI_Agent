// src/components/MetricCard.jsx
//
// VERA Enterprise Metric Card
// Standardized metric card designed according to Grafana observability best practices.
// Features clear units, historical trends, high-contrast typography, and WCAG accessibility.

import React from "react";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";

export default function MetricCard({
  title,
  value,
  unit = "",
  delta,
  deltaType = "neutral", // "increase" | "decrease" | "neutral"
  timeRange = "Last 1h",
  icon: Icon,
  status = "neutral", // "healthy" | "warning" | "critical" | "neutral"
  isLoading = false,
  className = "",
  onClick,
}) {
  const statusColors = {
    healthy: "text-emerald-400 border-emerald-500/30 bg-emerald-500/5",
    warning: "text-amber-400 border-amber-500/30 bg-amber-500/5",
    critical: "text-red-400 border-red-500/30 bg-red-500/5",
    neutral: "text-text-primary border-vera-navy-border bg-vera-navy-surface/80",
  };

  const deltaColors = {
    increase: deltaType === "healthy" ? "text-emerald-400" : "text-vera-cyan",
    decrease: deltaType === "critical" ? "text-red-400" : "text-amber-400",
    neutral: "text-text-secondary",
  };

  return (
    <div
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      className={`relative p-4 rounded-lg border transition-all ${statusColors[status]} ${
        onClick ? "cursor-pointer hover:border-vera-cyan/40 hover:-translate-y-0.5" : ""
      } ${className}`}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          {title}
        </span>
        {Icon && (
          <div className="p-1.5 rounded-md bg-white/5 text-vera-cyan shrink-0">
            <Icon size={16} />
          </div>
        )}
      </div>

      <div className="flex items-baseline gap-1.5 my-1">
        {isLoading ? (
          <div className="h-8 w-24 bg-white/10 animate-pulse rounded" />
        ) : (
          <>
            <span className="text-2xl font-bold font-mono text-white tracking-tight">
              {value}
            </span>
            {unit && (
              <span className="text-xs font-medium text-text-secondary font-mono">
                {unit}
              </span>
            )}
          </>
        )}
      </div>

      <div className="flex items-center justify-between text-[11px] text-text-secondary mt-2 pt-2 border-t border-white/5 font-mono">
        {delta !== undefined ? (
          <span className={`flex items-center gap-1 font-semibold ${deltaColors[deltaType]}`}>
            {deltaType === "increase" && <TrendingUp size={12} />}
            {deltaType === "decrease" && <TrendingDown size={12} />}
            {deltaType === "neutral" && <Minus size={12} />}
            {delta}
          </span>
        ) : (
          <span />
        )}
        <span className="text-[10px] text-text-secondary/70">{timeRange}</span>
      </div>
    </div>
  );
}
