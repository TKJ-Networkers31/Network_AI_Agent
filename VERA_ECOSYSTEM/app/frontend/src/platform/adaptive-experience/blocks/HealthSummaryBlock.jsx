/**
 * src/platform/adaptive-experience/blocks/HealthSummaryBlock.jsx
 *
 * Transparent Device and Subsystem Health Overview.
 * Transparently exposes the indicators and methodology behind scores.
 */

import React from "react";
import { Activity, ShieldCheck, AlertCircle, HeartPulse } from "lucide-react";

export default function HealthSummaryBlock({ block }) {
  const data = block?.data || {};
  const device = data.device || "Sistem";
  const status = (data.status || "HEALTHY").toUpperCase();
  const score = data.score ?? 95;
  const indicators = data.indicators || [];

  const getStatusStyle = (st) => {
    if (st === "CRITICAL" || st === "FAILED") return "text-rose-400 bg-rose-950/60 border-rose-500/30";
    if (st === "WARNING" || st === "DEGRADED") return "text-amber-400 bg-amber-950/60 border-amber-500/30";
    return "text-emerald-400 bg-emerald-950/60 border-emerald-500/30";
  };

  return (
    <div className="my-2 p-4 rounded-xl border border-white/10 bg-slate-900/80 backdrop-blur-md shadow-lg space-y-3 font-sans">
      <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400">
            <HeartPulse size={18} />
          </div>
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-white/90">
              Evaluasi Kesehatan Sistem (Health Summary)
            </h4>
            <p className="text-[11px] text-white/50">{device}</p>
          </div>
        </div>
        <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border font-bold ${getStatusStyle(status)}`}>
          {status} ({score}/100)
        </span>
      </div>

      {indicators.length > 0 && (
        <div className="space-y-1.5">
          <h5 className="text-[10px] font-semibold text-white/40 uppercase tracking-wider font-mono">
            Faktor Penilaian:
          </h5>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
            {indicators.map((ind, idx) => (
              <div key={idx} className="flex items-center justify-between p-2 rounded-lg border border-white/5 bg-black/25">
                <span className="text-white/80">{ind.name || ind.factor}</span>
                <span className={`font-mono text-[11px] font-semibold ${ind.passed ? "text-emerald-400" : "text-amber-400"}`}>
                  {ind.passed ? "NORMAL" : "PERHATIAN"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
