// src/components/DeviceStatusIndicator.jsx
//
// VERA Device Availability & Connectivity Status Indicator
// Features independent verification of reachability and operational status.

import React from "react";
import StatusBadge from "./StatusBadge.jsx";

export default function DeviceStatusIndicator({
  isOnline,
  status = "unknown",
  lastSeen,
  size = "md",
  className = "",
}) {
  let computedStatus = "unknown";
  let label = "Unknown";

  if (isOnline === true || status === "online" || status === "up") {
    computedStatus = "healthy";
    label = "Online";
  } else if (isOnline === false || status === "offline" || status === "down") {
    computedStatus = "critical";
    label = "Offline";
  } else if (status === "degraded" || status === "warning") {
    computedStatus = "warning";
    label = "Degraded";
  }

  return (
    <div className={`inline-flex items-center gap-2 ${className}`}>
      <StatusBadge status={computedStatus} label={label} size={size} />
      {lastSeen && (
        <span className="text-[11px] text-text-secondary/70 font-mono">
          seen {lastSeen}
        </span>
      )}
    </div>
  );
}
