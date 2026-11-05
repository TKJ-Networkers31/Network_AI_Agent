// src/components/topology/SnapshotIntegrityBadge.jsx
// Visual integrity and completeness badge for topology snapshots.
// Cryptographic integrity (SHA-256) and Discovery Completeness are strictly orthogonal dimensions.

import { AlertCircle, AlertTriangle, CheckCircle2, Clock, ShieldCheck } from "lucide-react";
import { getSnapshotBadgeState } from "./topologyHistoryApi.js";

export { getSnapshotBadgeState };

export default function SnapshotIntegrityBadge({ status = "unverified", isComplete = true, className = "" }) {
  const { integrity, completeness } = getSnapshotBadgeState(status, isComplete);

  return (
    <div className={`inline-flex items-center gap-1.5 flex-wrap ${className}`}>
      {/* 1. Cryptographic Integrity Dimension */}
      {integrity.status === "compromised" ? (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-500/15 text-red-400 border border-red-500/30"
          title={integrity.tooltip}
          data-testid="badge-integrity-compromised"
        >
          <AlertTriangle className="w-3 h-3 text-red-400" />
          <span>{integrity.label}</span>
        </span>
      ) : integrity.status === "verified" ? (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
          title={integrity.tooltip}
          data-testid="badge-integrity-verified"
        >
          <ShieldCheck className="w-3 h-3 text-emerald-400" />
          <span>{integrity.label}</span>
        </span>
      ) : (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-white/5 text-neutral-400 border border-white/10"
          title={integrity.tooltip}
          data-testid="badge-integrity-unverified"
        >
          <Clock className="w-3 h-3 text-neutral-400" />
          <span>{integrity.label}</span>
        </span>
      )}

      {/* 2. Discovery Completeness Dimension (Strictly Independent) */}
      {!completeness.isComplete ? (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30"
          title={completeness.tooltip}
          data-testid="badge-discovery-partial"
        >
          <AlertCircle className="w-3 h-3 text-amber-400" />
          <span>{completeness.label}</span>
        </span>
      ) : (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-sky-500/10 text-sky-300 border border-sky-500/20"
          title={completeness.tooltip}
          data-testid="badge-discovery-complete"
        >
          <CheckCircle2 className="w-3 h-3 text-sky-400" />
          <span>{completeness.label}</span>
        </span>
      )}
    </div>
  );
}
