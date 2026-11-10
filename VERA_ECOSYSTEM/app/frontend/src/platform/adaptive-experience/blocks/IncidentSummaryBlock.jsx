/**
 * src/platform/adaptive-experience/blocks/IncidentSummaryBlock.jsx
 *
 * Incident report, blast radius, and Root Cause Analysis (RCA) breakdown.
 */

import React from "react";
import { AlertTriangle, CheckCircle, ShieldAlert, Cpu } from "lucide-react";

export default function IncidentSummaryBlock({ block }) {
  const data = block?.data || {};
  const incidentId = data.incident_id || "INC-VERA";
  const title = data.title || "Insiden Jaringan Terdeteksi";
  const severity = (data.severity || "P2").toUpperCase();
  const rootCause = data.root_cause || data.cause || "Investigasi otomatis sedang berlangsung.";
  const confidence = data.confidence ? Math.round(data.confidence * 100) : 85;
  const recommendations = data.recommendations || data.remediation_steps || [];

  const getSeverityPill = (sev) => {
    if (sev === "P1") {
      return (
        <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-rose-500/20 text-rose-400 border border-rose-500/30">
          P1 - KRITIS
        </span>
      );
    }
    if (sev === "P2") {
      return (
        <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-amber-500/20 text-amber-400 border border-amber-500/30">
          P2 - TINGGI
        </span>
      );
    }
    return (
      <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-blue-500/20 text-blue-400 border border-blue-500/30">
        P3 - SEDANG
      </span>
    );
  };

  return (
    <div className="my-2 p-4 rounded-xl border border-rose-500/20 bg-slate-900/90 backdrop-blur-md shadow-lg space-y-3 font-sans">
      <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-rose-500/10 text-rose-400">
            <ShieldAlert size={18} />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-white/90">{title}</h4>
            <p className="text-[10px] text-white/40 font-mono">{incidentId}</p>
          </div>
        </div>
        {getSeverityPill(severity)}
      </div>

      <div className="p-3 rounded-lg border border-white/5 bg-black/40 space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-white/60 font-medium">Analisis Akar Masalah (RCA):</span>
          <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/60 px-1.5 py-0.5 rounded border border-cyan-500/20">
            Confidence: {confidence}%
          </span>
        </div>
        <p className="text-xs text-white/80 leading-relaxed font-sans">{rootCause}</p>
      </div>

      {recommendations && recommendations.length > 0 && (
        <div className="space-y-1.5">
          <h5 className="text-[11px] font-semibold text-white/60 uppercase tracking-wider font-mono">
            Rekomendasi Tindakan:
          </h5>
          <ul className="space-y-1 text-xs text-white/70">
            {recommendations.map((rec, idx) => (
              <li key={idx} className="flex items-start gap-1.5">
                <span className="text-emerald-400 font-bold shrink-0 mt-0.5">✓</span>
                <span>{typeof rec === "string" ? rec : rec.title || JSON.stringify(rec)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
