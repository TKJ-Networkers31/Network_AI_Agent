// src/components/network-intelligence/OverviewTab.jsx
import React from "react";
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Layers,
  Network,
  RefreshCw,
  Server,
  ShieldCheck,
  Zap,
} from "lucide-react";

export default function OverviewTab({ overview, loading, onRefresh }) {
  if (loading && !overview) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-white/50 space-y-3">
        <RefreshCw className="animate-spin text-cyan-400" size={32} />
        <p className="text-sm font-mono">Memuat ringkasan intelijen jaringan...</p>
      </div>
    );
  }

  const data = overview || {
    network_condition: "UNKNOWN",
    health_score: 100.0,
    dimension_scores: {},
    device_health: {},
    active_incidents_count: 0,
    recent_incidents: [],
    major_anomalies: [],
    recurring_incidents: [],
    evidence_freshness: { FRESH: 0, AGING: 0, STALE: 0, EXPIRED: 0 },
    total_evidence_records: 0,
    observed_devices: [],
  };

  const statusColors = {
    HEALTHY: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
    DEGRADED: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    CRITICAL: "text-rose-400 border-rose-500/30 bg-rose-500/10",
    UNKNOWN: "text-white/60 border-white/20 bg-white/5",
  };

  const cond = data.network_condition || "UNKNOWN";
  const badgeCls = statusColors[cond] || statusColors.UNKNOWN;

  return (
    <div className="space-y-6">
      {/* Top Banner: Condition & Score */}
      <div className="bg-card border border-border p-5 rounded-xl shadow-lg flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-cyan-500/10 border border-cyan-500/30 rounded-xl text-cyan-400">
            <Activity size={28} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white tracking-wide">Kondisi Jaringan Keseluruhan</h2>
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wider border ${badgeCls}`}>
                {cond}
              </span>
            </div>
            <p className="text-xs text-white/60 mt-0.5">
              Dianalisis secara transparan dari {data.total_evidence_records} bukti kanonikal across {data.observed_devices?.length || 0} perangkat.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-xs uppercase font-mono text-white/50 tracking-wider">Health Index</div>
            <div className="text-2xl font-black font-mono text-cyan-300">
              {Number(data.health_score || 100).toFixed(1)}%
            </div>
          </div>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="p-2.5 bg-white/5 hover:bg-white/10 text-white/80 hover:text-white rounded-lg border border-border transition flex items-center gap-1.5 text-xs font-mono"
            title="Muat Ulang Bukti"
          >
            <RefreshCw size={14} className={loading ? "animate-spin text-cyan-400" : ""} />
            <span>Segarkan</span>
          </button>
        </div>
      </div>

      {/* 8-Dimensional Health Scores Grid */}
      <div className="bg-card border border-border p-5 rounded-xl space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white/90 flex items-center gap-2">
            <Layers size={16} className="text-cyan-400" />
            <span>8 Dimensi Kesehatan Jaringan (Transparan & Deterministic)</span>
          </h3>
          <span className="text-[11px] font-mono text-white/40">Bobot eksplisit tanpa penyamaran</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Object.entries(data.dimension_scores || {}).map(([dim, score]) => {
            const sc = Number(score || 100);
            const isDegraded = sc < 80;
            const isCrit = sc < 60;
            const barColor = isCrit ? "bg-rose-500" : isDegraded ? "bg-amber-500" : "bg-emerald-500";
            return (
              <div key={dim} className="bg-white/5 p-3 rounded-lg border border-white/5 space-y-1.5">
                <div className="flex justify-between items-center text-xs">
                  <span className="font-mono text-white/70 text-[11px] truncate" title={dim}>
                    {dim.replace(/_/g, " ")}
                  </span>
                  <span className={`font-mono font-bold text-xs ${isCrit ? "text-rose-400" : isDegraded ? "text-amber-400" : "text-emerald-400"}`}>
                    {sc.toFixed(1)}%
                  </span>
                </div>
                <div className="w-full bg-black/40 h-1.5 rounded-full overflow-hidden">
                  <div className={`h-full ${barColor}`} style={{ width: `${Math.min(100, Math.max(0, sc))}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Freshness, Incidents & Anomalies Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Freshness Status */}
        <div className="bg-card border border-border p-4 rounded-xl space-y-2">
          <div className="flex items-center justify-between text-xs font-semibold text-white/90">
            <span className="flex items-center gap-1.5">
              <ShieldCheck size={14} className="text-emerald-400" />
              <span>Evidence Freshness</span>
            </span>
            <span className="text-white/40 font-mono text-[10px]">TTL Profiles</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs font-mono pt-1">
            <div className="p-2 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-300">
              <div className="text-[10px] text-emerald-400/70">FRESH</div>
              <div className="text-base font-bold">{data.evidence_freshness?.FRESH || 0}</div>
            </div>
            <div className="p-2 rounded bg-cyan-500/10 border border-cyan-500/20 text-cyan-300">
              <div className="text-[10px] text-cyan-400/70">AGING</div>
              <div className="text-base font-bold">{data.evidence_freshness?.AGING || 0}</div>
            </div>
            <div className="p-2 rounded bg-amber-500/10 border border-amber-500/20 text-amber-300">
              <div className="text-[10px] text-amber-400/70">STALE</div>
              <div className="text-base font-bold">{data.evidence_freshness?.STALE || 0}</div>
            </div>
            <div className="p-2 rounded bg-rose-500/10 border border-rose-500/20 text-rose-300">
              <div className="text-[10px] text-rose-400/70">EXPIRED</div>
              <div className="text-base font-bold">{data.evidence_freshness?.EXPIRED || 0}</div>
            </div>
          </div>
        </div>

        {/* Active Incidents & Recurring */}
        <div className="bg-card border border-border p-4 rounded-xl space-y-2">
          <div className="flex items-center justify-between text-xs font-semibold text-white/90">
            <span className="flex items-center gap-1.5">
              <AlertTriangle size={14} className="text-amber-400" />
              <span>Insiden & Pola Berulang</span>
            </span>
            <span className="text-white/40 font-mono text-[10px]">Active</span>
          </div>
          <div className="space-y-1.5 pt-1 text-xs">
            <div className="flex justify-between items-center p-2 rounded bg-white/5 border border-white/5">
              <span className="text-white/70">Insiden Terbuka:</span>
              <span className="font-mono font-bold text-amber-300">{data.active_incidents_count || 0}</span>
            </div>
            <div className="flex justify-between items-center p-2 rounded bg-white/5 border border-white/5">
              <span className="text-white/70">Pola Insiden Berulang:</span>
              <span className="font-mono font-bold text-cyan-300">{data.recurring_incidents?.length || 0}</span>
            </div>
          </div>
        </div>

        {/* Major Anomalies */}
        <div className="bg-card border border-border p-4 rounded-xl space-y-2">
          <div className="flex items-center justify-between text-xs font-semibold text-white/90">
            <span className="flex items-center gap-1.5">
              <Zap size={14} className="text-rose-400" />
              <span>Anomali Kritis / Tinggi</span>
            </span>
            <span className="text-white/40 font-mono text-[10px]">MAD & Z-Score</span>
          </div>
          <div className="space-y-1.5 pt-1 text-xs">
            {data.major_anomalies && data.major_anomalies.length > 0 ? (
              data.major_anomalies.slice(0, 2).map((a, idx) => (
                <div key={idx} className="p-2 rounded bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">
                  <div className="font-semibold truncate">{a.metric_name || a.entity_id}</div>
                  <div className="text-[11px] text-rose-400/80 truncate">{a.description}</div>
                </div>
              ))
            ) : (
              <div className="p-3 text-center text-white/40 italic font-mono text-[11px] rounded bg-white/5">
                Tidak ada anomali kritis aktif
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
