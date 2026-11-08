// src/components/StatusBadge.jsx
//
// VERA Accessible Operational Status Badge
// Conforms strictly to WCAG 2.2 Criterion 1.4.1: Color is NEVER the sole indicator of status.
// Every status includes an explicit icon + textual label.

import React from "react";
import { CheckCircle2, AlertTriangle, XCircle, Info, HelpCircle } from "lucide-react";

export const STATUS_VARIANTS = {
  healthy: {
    label: "Healthy",
    icon: CheckCircle2,
    badgeClass: "bg-emerald-500/15 border-emerald-500/40 text-emerald-400",
  },
  warning: {
    label: "Warning",
    icon: AlertTriangle,
    badgeClass: "bg-amber-500/15 border-amber-500/40 text-amber-400",
  },
  critical: {
    label: "Critical",
    icon: XCircle,
    badgeClass: "bg-red-500/15 border-red-500/40 text-red-400",
  },
  info: {
    label: "Info",
    icon: Info,
    badgeClass: "bg-blue-500/15 border-blue-500/40 text-blue-400",
  },
  unknown: {
    label: "Unknown",
    icon: HelpCircle,
    badgeClass: "bg-slate-500/15 border-slate-500/40 text-slate-400",
  },
};

export default function StatusBadge({
  status = "unknown",
  label,
  size = "md", // "sm" | "md" | "lg"
  showIcon = true,
  className = "",
}) {
  const normStatus = (status || "unknown").toLowerCase();
  const config = STATUS_VARIANTS[normStatus] || STATUS_VARIANTS.unknown;
  const Icon = config.icon;
  const displayLabel = label || config.label;

  const sizeClasses = {
    sm: "px-1.5 py-0.5 text-[10px] gap-1",
    md: "px-2 py-0.5 text-xs gap-1.5",
    lg: "px-2.5 py-1 text-sm gap-2",
  };

  const iconSizes = {
    sm: 11,
    md: 13,
    lg: 15,
  };

  return (
    <span
      className={`inline-flex items-center font-medium font-mono rounded-full border ${config.badgeClass} ${sizeClasses[size]} ${className}`}
    >
      {showIcon && <Icon size={iconSizes[size]} strokeWidth={2.2} className="shrink-0" />}
      <span>{displayLabel}</span>
    </span>
  );
}
