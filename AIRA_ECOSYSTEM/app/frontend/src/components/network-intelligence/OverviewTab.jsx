// src/components/network-intelligence/OverviewTab.jsx
import React from "react";
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Cpu,
  Layers,
  Network,
  PlusCircle,
  RefreshCw,
  Server,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Wifi,
  WifiOff,
  Zap,
} from "lucide-react";

export default function OverviewTab({
  overview,
  loading,
  onRefresh,
  onOpenOnboard,
  onOpenPolicy,
  onNavigateToTab,
}) {
  if (loading && !overview) {
    return (
      <div className="flex flex-col items-center justify-center p-16 text-white/50 space-y-3">
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
    total_registered_devices: 0,
    reachable_devices: 0,
    unreachable_devices: 0,
    active_investigations: 0,
    detected_anomalies: 0,
    pending_approvals: [],
    recent_ai_decisions: [],
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

  const pendingApprovalsCount = Array.isArray(data.pending_approvals)
    ? data.pending_approvals.length
    : (data.pending_approvals || 0);

  const recentDecisionsList = Array.isArray(data.recent_ai_decisions)
    ? data.recent_ai_decisions
    : [];

  return (
    <div className="space-y-6">
      {/* Top Banner: Condition, Score & Quick Controls */}
      <div className="bg-card border border-border p-5 rounded-xl shadow-lg flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-cyan-500/10 border border-cyan-500/30 rounded-xl text-cyan-400 shrink-0">
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
              Dianalisis secara transparan dari {data.total_evidence_records || 0} bukti kanonikal across {data.total_registered_devices || 0} perangkat terdaftar.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="text-right mr-2">
            <div className="text-[10px] uppercase font-mono text-white/50 tracking-wider">Health Index</div>
            <div className="text-2xl font-black font-mono text-cyan-300">
              {Number(data.health_score || 100).toFixed(1)}%
            </div>
          </div>

          {onOpenOnboard && (
            <button
              onClick={onOpenOnboard}
              className="px-3 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/30 text-xs font-semibold flex items-center gap-1.5 transition"
            >
              <PlusCircle size={14} />
              <span>Onboard Perangkat</span>
            </button>
          )}

          {onOpenPolicy && (
            <button
              onClick={onOpenPolicy}
              className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-xs font-semibold border border-white/10 flex items-center gap-1.5 transition"
            >
              <Sliders size={14} />
              <span>AI Operations Policy</span>
            </button>
          )}

          <button
            onClick={onRefresh}
            disabled={loading}
            className="p-2 bg-white/5 hover:bg-white/10 text-white/80 hover:text-white rounded-lg border border-border transition flex items-center gap-1 text-xs font-mono"
            title="Muat Ulang Bukti"
          >
            <RefreshCw size={14} className={loading ? "animate-spin text-cyan-400" : ""} />
            <span>Segarkan</span>
          </button>
        </div>
      </div>

      {/* 8-Part Core Network Intelligence Metrics (Section 4.1 Requirement) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-4 gap-3">
        {/* 1. Overall Network Health */}
        <div className="bg-card border border-border p-3.5 rounded-xl space-y-1">
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Overall Health</span>
            <Activity size={14} className="text-cyan-400" />
          </div>
          <div className="text-xl font-bold font-mono text-white">
            {Number(data.health_score || 100).toFixed(1)}%
          </div>
          <div className={`text-[10px] font-semibold uppercase ${badgeCls.split(" ")[0]}`}>
            Status: {cond}
          </div>
        </div>

        {/* 2. Total Registered Devices */}
        <div className="bg-card border border-border p-3.5 rounded-xl space-y-1">
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Total Devices</span>
            <Server size={14} className="text-indigo-400" />
          </div>
          <div className="text-xl font-bold font-mono text-white">
            {data.total_registered_devices ?? 0}
          </div>
          <div className="text-[10px] text-white/40">
            Inventory Database
          </div>
        </div>

        {/* 3. Reachable Devices */}
        <div className="bg-card border border-border p-3.5 rounded-xl space-y-1">
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Reachable (UP)</span>
            <Wifi size={14} className="text-emerald-400" />
          </div>
          <div className="text-xl font-bold font-mono text-emerald-400">
            {data.reachable_devices ?? 0}
          </div>
          <div className="text-[10px] text-emerald-500/70">
            NMS Active Polls
          </div>
        </div>

        {/* 4. Unreachable Devices */}
        <div className="bg-card border border-border p-3.5 rounded-xl space-y-1">
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Unreachable (DOWN)</span>
            <WifiOff size={14} className="text-rose-400" />
          </div>
          <div className="text-xl font-bold font-mono text-rose-400">
            {data.unreachable_devices ?? 0}
          </div>
          <div className="text-[10px] text-rose-400/70">
            {data.unreachable_devices > 0 ? "Memerlukan atensi" : "Semua online"}
          </div>
        </div>

        {/* 5. Active Investigations */}
        <div
          onClick={() => onNavigateToTab && onNavigateToTab("investigations")}
          className="bg-card border border-border hover:border-cyan-500/40 cursor-pointer p-3.5 rounded-xl space-y-1 transition"
        >
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Active Investigations</span>
            <ShieldAlert size={14} className="text-amber-400" />
          </div>
          <div className="text-xl font-bold font-mono text-amber-400">
            {data.active_investigations ?? data.active_incidents_count ?? 0}
          </div>
          <div className="text-[10px] text-cyan-400 flex items-center gap-1">
            <span>Buka investigasi</span>
            <ArrowRight size={10} />
          </div>
        </div>

        {/* 6. Detected Anomalies */}
        <div className="bg-card border border-border p-3.5 rounded-xl space-y-1">
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Detected Anomalies</span>
            <AlertTriangle size={14} className="text-rose-400" />
          </div>
          <div className="text-xl font-bold font-mono text-rose-400">
            {data.detected_anomalies ?? (data.major_anomalies?.length || 0)}
          </div>
          <div className="text-[10px] text-white/40">
            Telemetry &amp; Syslog
          </div>
        </div>

        {/* 7. Pending Approvals */}
        <div
          onClick={() => onNavigateToTab && onNavigateToTab("actions")}
          className="bg-card border border-border hover:border-amber-500/40 cursor-pointer p-3.5 rounded-xl space-y-1 transition"
        >
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Pending Approvals</span>
            <AlertOctagon size={14} className="text-amber-400" />
          </div>
          <div className="text-xl font-bold font-mono text-amber-400">
            {pendingApprovalsCount}
          </div>
          <div className="text-[10px] text-amber-300 flex items-center gap-1">
            <span>Tinjau Action Center</span>
            <ArrowRight size={10} />
          </div>
        </div>

        {/* 8. Recent AI Decisions */}
        <div className="bg-card border border-border p-3.5 rounded-xl space-y-1">
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Recent AI Decisions</span>
            <Bot size={14} className="text-cyan-400" />
          </div>
          <div className="text-xl font-bold font-mono text-cyan-400">
            {recentDecisionsList.length}
          </div>
          <div className="text-[10px] text-white/40">
            Audit Decoupled
          </div>
        </div>
      </div>

      {/* Mid Section: 8-Dimensional Health & Evidence Freshness */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 8-Dimensional Health Scores Grid */}
        <div className="lg:col-span-2 bg-card border border-border p-5 rounded-xl space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white/90 flex items-center gap-2">
              <Layers size={16} className="text-cyan-400" />
              <span>8 Dimensi Kesehatan Jaringan (Transparan &amp; Deterministic)</span>
            </h3>
            <span className="text-[11px] font-mono text-white/40">Bobot eksplisit tanpa black-box</span>
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

        {/* Evidence Freshness */}
        <div className="bg-card border border-border p-5 rounded-xl space-y-3">
          <div className="flex items-center justify-between text-xs font-semibold text-white/90">
            <span className="flex items-center gap-1.5">
              <ShieldCheck size={16} className="text-emerald-400" />
              <span>Evidence Freshness Profiles</span>
            </span>
            <span className="text-white/40 font-mono text-[10px]">Deterministic TTL</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs font-mono pt-1">
            <div className="p-2.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-300">
              <div className="text-[10px] text-emerald-400/70">FRESH (&lt;15m)</div>
              <div className="text-lg font-bold">{data.evidence_freshness?.FRESH || 0}</div>
            </div>
            <div className="p-2.5 rounded bg-cyan-500/10 border border-cyan-500/20 text-cyan-300">
              <div className="text-[10px] text-cyan-400/70">AGING (&lt;1h)</div>
              <div className="text-lg font-bold">{data.evidence_freshness?.AGING || 0}</div>
            </div>
            <div className="p-2.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-300">
              <div className="text-[10px] text-amber-400/70">STALE (&lt;24h)</div>
              <div className="text-lg font-bold">{data.evidence_freshness?.STALE || 0}</div>
            </div>
            <div className="p-2.5 rounded bg-rose-500/10 border border-rose-500/20 text-rose-300">
              <div className="text-[10px] text-rose-400/70">EXPIRED</div>
              <div className="text-lg font-bold">{data.evidence_freshness?.EXPIRED || 0}</div>
            </div>
          </div>
          <p className="text-[11px] text-white/40 italic">
            AIRA menolak data kadaluarsa sebagai fakta terbukti sebelum memverifikasi ulang ke NMS atau perangkat.
          </p>
        </div>
      </div>

      {/* Bottom Section: Recent AI Decisions & Pending Approvals */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent AI Decisions Panel */}
        <div className="bg-card border border-border p-5 rounded-xl space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white/90 flex items-center gap-2">
              <Bot size={16} className="text-cyan-400" />
              <span>Recent AI Decisions (Operational Decision Intelligence)</span>
            </h3>
            <span className="text-[11px] font-mono text-cyan-400/80">Audit Logged</span>
          </div>

          <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
            {recentDecisionsList.length === 0 ? (
              <div className="p-6 text-center text-xs text-white/40 bg-white/5 border border-white/5 rounded-lg">
                Belum ada catatan keputusan AI tersimpan.
              </div>
            ) : (
              recentDecisionsList.map((dec, idx) => (
                <div key={idx} className="p-3 rounded-lg bg-white/5 border border-white/5 space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-white truncate max-w-[280px]">
                      {dec.title || dec.intent || "Keputusan Operasional"}
                    </span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                      {dec.decision_type || dec.risk_level || "DECISION"}
                    </span>
                  </div>
                  <p className="text-xs text-white/70 line-clamp-2">
                    {dec.rationale || dec.summary || "Analisis observasi status perangkat dan evaluasi kebijakan operasional."}
                  </p>
                  <div className="flex items-center justify-between text-[10px] text-white/40 pt-1 border-t border-white/5">
                    <span>Target: {dec.target_device || "Network Wide"}</span>
                    <span>{dec.timestamp ? new Date(dec.timestamp * 1000).toLocaleString() : "Tercatat"}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Pending Approvals & Major Anomalies */}
        <div className="bg-card border border-border p-5 rounded-xl space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white/90 flex items-center gap-2">
              <AlertOctagon size={16} className="text-amber-400" />
              <span>Pending Approvals &amp; High Anomali</span>
            </h3>
            {pendingApprovalsCount > 0 && onNavigateToTab && (
              <button
                onClick={() => onNavigateToTab("actions")}
                className="text-xs font-semibold text-amber-400 hover:text-amber-300 flex items-center gap-1 transition"
              >
                <span>Lihat Semua ({pendingApprovalsCount})</span>
                <ArrowRight size={12} />
              </button>
            )}
          </div>

          {Array.isArray(data.pending_approvals) && data.pending_approvals.length > 0 ? (
            <div className="space-y-2">
              {data.pending_approvals.slice(0, 3).map((act) => (
                <div key={act.action_id} className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-amber-200">{act.action_name}</span>
                    <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">
                      {act.risk_level}
                    </span>
                  </div>
                  <p className="text-xs text-white/80 line-clamp-1">{act.description}</p>
                  <div className="flex items-center justify-between text-[10px] text-white/50 pt-1">
                    <span>Target: {act.target_device}</span>
                    <span className="text-amber-300 font-medium">Menunggu Persetujuan Admin</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-4 text-center text-xs text-white/40 bg-white/5 border border-white/5 rounded-lg">
              Tidak ada tindakan yang tertunda menunggu persetujuan saat ini.
            </div>
          )}

          {/* Major Anomalies */}
          {data.major_anomalies && data.major_anomalies.length > 0 && (
            <div className="pt-2 border-t border-border space-y-2">
              <div className="text-xs font-semibold text-rose-400 flex items-center gap-1.5">
                <AlertTriangle size={14} />
                <span>Anomali Terdeteksi (Kritis / Tinggi)</span>
              </div>
              <div className="space-y-1.5">
                {data.major_anomalies.slice(0, 2).map((a, idx) => (
                  <div key={idx} className="p-2.5 rounded bg-rose-500/10 border border-rose-500/20 text-xs text-rose-200 flex justify-between items-center">
                    <div>
                      <span className="font-semibold">{a.metric_name || a.entity_id}: </span>
                      <span className="text-rose-300/80">{a.description}</span>
                    </div>
                    <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 shrink-0">
                      {a.severity}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
