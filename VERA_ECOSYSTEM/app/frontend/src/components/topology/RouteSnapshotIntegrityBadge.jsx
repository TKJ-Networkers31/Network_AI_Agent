// src/components/topology/RouteSnapshotIntegrityBadge.jsx
// Orthogonal SHA-256 Integrity and Collection Completeness badge for Route Snapshots.

import { AlertCircle, AlertTriangle, CheckCircle2, Clock, ShieldCheck } from "lucide-react";
import { getRouteSnapshotBadgeState } from "./routeHistoryApi.js";

export default function RouteSnapshotIntegrityBadge({
  integrityStatus = "unverified",
  completeness = "COMPLETE",
  className = "",
}) {
  const { integrity, completeness: comp } = getRouteSnapshotBadgeState(
    integrityStatus,
    completeness
  );

  return (
    <div className={`inline-flex items-center gap-1.5 flex-wrap ${className}`}>
      {integrity.status === "compromised" ? (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-500/15 text-red-400 border border-red-500/30"
          title={integrity.tooltip}
        >
          <AlertTriangle className="w-3 h-3 text-red-400" />
          <span>{integrity.label}</span>
        </span>
      ) : integrity.status === "verified" ? (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
          title={integrity.tooltip}
        >
          <ShieldCheck className="w-3 h-3 text-emerald-400" />
          <span>{integrity.label}</span>
        </span>
      ) : (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-white/5 text-neutral-400 border border-white/10"
          title={integrity.tooltip}
        >
          <Clock className="w-3 h-3 text-neutral-400" />
          <span>{integrity.label}</span>
        </span>
      )}

      {comp.isComplete ? (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-sky-500/10 text-sky-300 border border-sky-500/20"
          title={comp.tooltip}
        >
          <CheckCircle2 className="w-3 h-3 text-sky-400" />
          <span>{comp.label}</span>
        </span>
      ) : (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30"
          title={comp.tooltip}
        >
          <AlertCircle className="w-3 h-3 text-amber-400" />
          <span>{comp.label}</span>
        </span>
      )}
    </div>
  );
}
