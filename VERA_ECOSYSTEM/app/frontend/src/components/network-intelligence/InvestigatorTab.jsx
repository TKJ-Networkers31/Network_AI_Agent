// src/components/network-intelligence/InvestigatorTab.jsx
import React, { useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock,
  HelpCircle,
  Layers,
  Loader2,
  Search,
  ShieldAlert,
  ShieldCheck,
  StopCircle,
  Terminal,
  Zap,
} from "lucide-react";

export default function InvestigatorTab({
  onRunInvestigation,
  onCancelInvestigation,
  activeInvestigation,
  loading,
  onProposeAction,
}) {
  const [query, setQuery] = useState("");
  const [targetIp, setTargetIp] = useState("");
  const [targetDevice, setTargetDevice] = useState("");

  const quickPrompts = [
    "Mengapa klien di VLAN 20 tidak bisa akses internet?",
    "Verifikasi rute default R1 ke upstream ISP",
    "Analisis kegagalan OSPF neighbor antar router",
    "Evaluasi anomali bandwidth dan packet drops di ether1",
  ];

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!query.trim() || loading) return;
    onRunInvestigation({
      question: query,
      user_context: {
        target_ip: targetIp.trim() || null,
        scoped_devices: targetDevice.trim() ? [targetDevice.trim()] : [],
      },
    });
  };

  const inv = activeInvestigation;

  return (
    <div className="space-y-6">
      {/* Query Intake Box */}
      <div className="bg-card border border-border p-5 rounded-xl shadow-lg space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Bot size={20} className="text-cyan-400" />
            <h3 className="text-sm font-bold text-white tracking-wide">
              Network Investigator — Penyelidikan Berbasis Bukti
            </h3>
          </div>
          <span className="text-[11px] font-mono text-cyan-400/80 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20">
            100% Read-Only Safety
          </span>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3.5 top-3.5 text-white/40" size={18} />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Tanyakan kondisi jaringan (contoh: Mengapa klien di VLAN 20 tidak bisa akses internet?)..."
              disabled={loading}
              className="w-full bg-white/5 border border-border rounded-xl pl-11 pr-32 py-3 text-sm text-white placeholder-white/40 focus:outline-none focus:border-cyan-500/60 focus:ring-1 focus:ring-cyan-500/60 transition"
            />
            <div className="absolute right-2 top-2 flex items-center gap-2">
              {loading ? (
                <button
                  type="button"
                  onClick={() => inv?.investigation_id && onCancelInvestigation(inv.investigation_id)}
                  className="px-3 py-1.5 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40 rounded-lg text-xs font-mono flex items-center gap-1.5 transition"
                >
                  <StopCircle size={14} />
                  <span>Batal</span>
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!query.trim()}
                  className="px-4 py-1.5 bg-cyan-500 hover:bg-cyan-400 text-black font-semibold rounded-lg text-xs flex items-center gap-1.5 transition disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Zap size={14} />
                  <span>Investigasi</span>
                </button>
              )}
            </div>
          </div>

          {/* Scoped Context Filters */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div>
              <label className="block text-[11px] font-mono text-white/50 mb-1">Target IP / Prefix (Opsional)</label>
              <input
                type="text"
                value={targetIp}
                onChange={(e) => setTargetIp(e.target.value)}
                placeholder="misal: 192.168.20.50 atau 8.8.8.8"
                disabled={loading}
                className="w-full bg-white/5 border border-border rounded-lg px-3 py-1.5 text-xs text-white placeholder-white/30 focus:outline-none focus:border-cyan-500/50"
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-white/50 mb-1">Perangkat Spesifik (Opsional)</label>
              <input
                type="text"
                value={targetDevice}
                onChange={(e) => setTargetDevice(e.target.value)}
                placeholder="misal: R1-Gateway"
                disabled={loading}
                className="w-full bg-white/5 border border-border rounded-lg px-3 py-1.5 text-xs text-white placeholder-white/30 focus:outline-none focus:border-cyan-500/50"
              />
            </div>
          </div>

          {/* Quick Prompts */}
          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <span className="text-[11px] font-mono text-white/40 mr-1">Contoh Cepat:</span>
            {quickPrompts.map((p, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => setQuery(p)}
                disabled={loading}
                className="text-[11px] bg-white/5 hover:bg-white/10 text-white/70 hover:text-white px-2 py-1 rounded-md border border-white/5 transition"
              >
                {p}
              </button>
            ))}
          </div>
        </form>
      </div>

      {/* Investigation Progress Loading Card */}
      {loading && (
        <div className="bg-card border border-cyan-500/30 p-6 rounded-xl flex items-center gap-4 text-cyan-300">
          <Loader2 size={24} className="animate-spin text-cyan-400" />
          <div className="space-y-1">
            <div className="text-sm font-bold">Menjalankan Pipeline 12-Tahap Penyelidikan...</div>
            <div className="text-xs text-cyan-400/70 font-mono">
              Klasifikasi niat → Pengumpulan bukti kanonikal → Analisis jalur & korelasi → Evaluasi hipotesis
            </div>
          </div>
        </div>
      )}

      {/* Investigation Results View */}
      {inv && !loading && (
        <div className="space-y-5">
          {/* Status & Scope Header */}
          <div className="bg-card border border-border p-4 rounded-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-white/40 uppercase">ID: {inv.investigation_id}</span>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                  {inv.intent}
                </span>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                  {inv.status}
                </span>
              </div>
              <p className="text-sm font-semibold text-white mt-1">"{inv.question}"</p>
            </div>
            <div className="text-xs font-mono text-white/50 text-right">
              <div>Durasi: {inv.duration_sec}s</div>
              <div>Bukti: {inv.evidence_summary?.total_records || 0} catatan</div>
            </div>
          </div>

          {/* AI Grounded Explanation Card */}
          {inv.explanation && (
            <div className="bg-gradient-to-r from-cyan-950/40 via-card to-card border border-cyan-500/40 p-5 rounded-xl space-y-3">
              <div className="flex items-center gap-2 text-cyan-300 text-xs font-bold uppercase tracking-wider">
                <Bot size={16} />
                <span>Analisis Terstruktur & Rekomendasi VERA</span>
              </div>
              <p className="text-sm text-white/90 leading-relaxed font-sans">
                {inv.explanation.summary}
              </p>

              {inv.explanation.recommended_actions && inv.explanation.recommended_actions.length > 0 && (
                <div className="pt-2 border-t border-cyan-500/20 space-y-1.5">
                  <div className="text-xs font-semibold text-cyan-400">Langkah Remediasi yang Direkomendasikan:</div>
                  <ul className="space-y-1 text-xs text-white/80">
                    {inv.explanation.recommended_actions.map((act, idx) => (
                      <li key={idx} className="flex items-start justify-between gap-2 p-1.5 rounded hover:bg-white/5 transition">
                        <div className="flex items-start gap-2">
                          <ArrowRight size={13} className="text-cyan-400 mt-0.5 shrink-0" />
                          <span>{act}</span>
                        </div>
                        {onProposeAction && (
                          <button
                            type="button"
                            onClick={() =>
                              onProposeAction({
                                description: act,
                                action_name: `Remediasi: ${act.slice(0, 40)}`,
                                reason: inv.explanation?.summary || "Rekomendasi dari hasil penyelidikan NL Investigator.",
                                target_device: inv.user_context?.scoped_devices?.[0] || "",
                              })
                            }
                            className="px-2 py-0.5 rounded bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 text-[10px] font-mono transition shrink-0 flex items-center gap-1"
                            title="Ajukan rekomendasi ini ke Action Center"
                          >
                            <span>Ajukan Action</span>
                            <ArrowRight size={10} />
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Leading Hypothesis & RCA Candidates */}
          {inv.rca && inv.rca.leading_hypothesis && (
            <div className="bg-card border border-border p-5 rounded-xl space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-bold text-white flex items-center gap-2">
                  <ShieldAlert size={16} className="text-amber-400" />
                  <span>Akar Masalah Teratas (Ranked Hypothesis #1)</span>
                </h4>
                <span className={`px-2 py-0.5 rounded text-xs font-bold font-mono ${
                  inv.rca.leading_hypothesis.confidence === "HIGH"
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                    : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                }`}>
                  Confidence: {inv.rca.leading_hypothesis.confidence}
                </span>
              </div>

              <div className="p-4 rounded-lg bg-white/5 border border-white/5 space-y-2">
                <div className="text-sm font-bold text-cyan-300">{inv.rca.leading_hypothesis.title}</div>
                <p className="text-xs text-white/80 leading-relaxed">{inv.rca.leading_hypothesis.explanation}</p>

                {inv.rca.leading_hypothesis.supporting_evidence?.length > 0 && (
                  <div className="pt-2 text-xs space-y-1">
                    <span className="font-semibold text-emerald-400">Bukti Pendukung:</span>
                    <ul className="list-disc list-inside text-white/70 space-y-0.5 pl-1">
                      {inv.rca.leading_hypothesis.supporting_evidence.map((s, idx) => (
                        <li key={idx}>{s}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Missing Evidence Warnings */}
          {inv.missing_evidence && inv.missing_evidence.length > 0 && (
            <div className="bg-amber-500/10 border border-amber-500/30 p-4 rounded-xl space-y-2">
              <div className="flex items-center gap-2 text-amber-300 text-xs font-bold">
                <AlertTriangle size={15} />
                <span>Bukti yang Kurang atau Belum Tersedia</span>
              </div>
              <ul className="list-disc list-inside text-xs text-amber-200/80 space-y-0.5">
                {inv.missing_evidence.map((m, idx) => (
                  <li key={idx}>{m}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
