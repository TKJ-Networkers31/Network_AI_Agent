// src/components/SeverityIndicator.jsx
//
// VERA Anomaly & Incident Severity Indicator

import React from "react";
import StatusBadge from "./StatusBadge.jsx";

export const SEVERITIES = {
  P1: { level: "P1", label: "Critical", status: "critical" },
  P2: { level: "P2", label: "Major", status: "warning" },
  P3: { level: "P3", label: "Minor", status: "warning" },
  P4: { level: "P4", label: "Info", status: "info" },
};

export default function SeverityIndicator({ level = "P3", className = "" }) {
  const sev = SEVERITIES[level?.toUpperCase()] || SEVERITIES.P3;
  return (
    <StatusBadge
      status={sev.status}
      label={`${sev.level} · ${sev.label}`}
      size="sm"
      className={className}
    />
  );
}
