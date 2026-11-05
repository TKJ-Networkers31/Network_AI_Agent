// src/components/network-intelligence/RcaTimelineTab.jsx
import React from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  GitCommit,
  Layers,
  Radio,
  Server,
  ShieldAlert,
  Zap,
} from "lucide-react";

export default function RcaTimelineTab({ rcaReport, correlations = [] }) {
  const rca = rcaReport;

  if (!rca) {
    return (
      <div className="bg-card border border-border p-12 rounded-xl text-center text-xs text-white/40 space-y-2">
        <Clock size={32} className="mx-auto text-white/20" />
        <p>Jalankan penyelidikan atau autodiagnostik untuk menghasilkan timeline Root Cause Analysis.</p>
      </div>
    );
  }

  const hypotheses = rca.ranked_hypotheses || [];

  return (
    <div className="space-y-6">
      {/* RCA Summary Header */}
      <div className="bg-card border border-border p-5 rounded-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
        <div>
          <div className="flex items-center gap-2">
            <ShieldAlert size={18} className="text-amber-400" />
            <h3 className="text-sm font-bold text-white tracking-wide">
              14-Step Root Cause Analysis (Deterministic Diagnostic Pipeline)
            </h3>
          </div>
          <p className="text-xs text-white/60 mt-1">
            Menganalisis anomali, korelasi multi-perangkat, dan memisahkan gejala dari akar penyebab sejati.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono">
          <span className="px-2.5 py-1 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
            {hypotheses.length} Hipotesis Terurut
          </span>
          <span className="px-2.5 py-1 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">
            {correlations.length} Korelasi
          </span>
        </div>
      </div>

      {/* Leading Root Cause vs Symptoms Separation */}
      {rca.leading_hypothesis && (
        <div className="bg-card border border-border rounded-xl p-5 space-y-4">
          <div className="flex justify-between items-center">
            <span className="text-xs font-bold uppercase text-white/90 tracking-wider flex items-center gap-2">
              <Zap size={14} className="text-cyan-400" />
              <span>Akar Masalah Terkonfirmasi (Root Cause)</span>
            </span>
            <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
              Confidence: {rca.leading_hypothesis.confidence}
            </span>
          </div>

          <div className="p-4 rounded-lg bg-white/5 border border-white/5 space-y-2">
            <div className="text-sm font-bold text-cyan-300">{rca.leading_hypothesis.title}</div>
            <p className="text-xs text-white/80 leading-relaxed">{rca.leading_hypothesis.explanation}</p>
          </div>
        </div>
      )}

      {/* Chronological Observation Timeline */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4">
        <h4 className="text-xs font-bold text-white/90 uppercase tracking-wider flex items-center gap-2">
          <Clock size={14} className="text-cyan-400" />
          <span>Timeline Urutan Kejadian & Bukti Korelasi</span>
        </h4>

        <div className="relative pl-6 space-y-4 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-white/10">
          {hypotheses.map((h, idx) => (
            <div key={idx} className="relative group">
              <div className="absolute -left-[1.65rem] top-1 w-3 h-3 rounded-full bg-cyan-400 ring-4 ring-black/40" />
              <div className="p-3.5 rounded-lg bg-white/5 border border-white/5 space-y-1.5 hover:border-cyan-500/30 transition">
                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="font-bold text-cyan-300">{h.title}</span>
                  <span className="text-[10px] text-white/40">Step {idx + 1}</span>
                </div>
                <p className="text-xs text-white/70">{h.explanation}</p>
                {h.supporting_evidence && h.supporting_evidence.length > 0 && (
                  <div className="text-[11px] text-white/50 pt-1">
                    <span className="font-semibold text-white/70">Observasi: </span>
                    {h.supporting_evidence.join("; ")}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
