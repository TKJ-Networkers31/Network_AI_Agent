// src/components/network-intelligence/HistoricalIntelligenceTab.jsx
import React, { useState } from "react";
import {
  Activity,
  ArrowRight,
  Clock,
  Database,
  GitCompare,
  History,
  Layers,
  RefreshCw,
  TrendingUp,
} from "lucide-react";

export default function HistoricalIntelligenceTab({
  historicalData,
  loading,
  onCompareSnapshots,
  onRefreshHistory,
}) {
  const [olderSnap, setOlderSnap] = useState("");
  const [newerSnap, setNewerSnap] = useState("");

  const data = historicalData || {
    recurring_incidents: [],
    snapshot_diff: null,
  };

  const handleCompare = (e) => {
    e.preventDefault();
    if (!olderSnap || !newerSnap || loading) return;
    onCompareSnapshots(olderSnap, newerSnap);
  };

  return (
    <div className="space-y-6">
      {/* Historical Query & Snapshot Comparison Form */}
      <div className="bg-card border border-border p-5 rounded-xl shadow-lg space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History size={18} className="text-cyan-400" />
            <h3 className="text-sm font-bold text-white tracking-wide">
              Historical Network Intelligence & Immutable Snapshot Comparison
            </h3>
          </div>
          <button
            onClick={onRefreshHistory}
            disabled={loading}
            className="p-1.5 bg-white/5 hover:bg-white/10 rounded-lg text-white/70 transition"
            title="Segarkan Riwayat"
          >
            <RefreshCw size={14} className={loading ? "animate-spin text-cyan-400" : ""} />
          </button>
        </div>

        <form onSubmit={handleCompare} className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label className="block text-[11px] font-mono text-white/50 mb-1">Older Snapshot ID</label>
            <input
              type="text"
              value={olderSnap}
              onChange={(e) => setOlderSnap(e.target.value)}
              placeholder="misal: snap_001"
              className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-xs text-white placeholder-white/30 focus:outline-none focus:border-cyan-500/50"
            />
          </div>
          <div>
            <label className="block text-[11px] font-mono text-white/50 mb-1">Newer Snapshot ID</label>
            <input
              type="text"
              value={newerSnap}
              onChange={(e) => setNewerSnap(e.target.value)}
              placeholder="misal: snap_002"
              className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-xs text-white placeholder-white/30 focus:outline-none focus:border-cyan-500/50"
            />
          </div>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={loading || !olderSnap || !newerSnap}
              className="w-full py-2 bg-cyan-500 hover:bg-cyan-400 text-black font-semibold rounded-lg text-xs flex items-center justify-center gap-1.5 transition disabled:opacity-40"
            >
              <GitCompare size={14} />
              <span>Bandingkan Snapshot</span>
            </button>
          </div>
        </form>
      </div>

      {/* Recurring Incidents & Trend Patterns */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4">
        <h4 className="text-xs font-bold text-white/90 uppercase tracking-wider flex items-center gap-2">
          <TrendingUp size={14} className="text-cyan-400" />
          <span>Pola Insiden Berulang & Flapping (Recurring Incident Detection)</span>
        </h4>

        {data.recurring_incidents && data.recurring_incidents.length > 0 ? (
          <div className="space-y-2">
            {data.recurring_incidents.map((rec, idx) => (
              <div key={idx} className="p-3 rounded-lg bg-white/5 border border-white/5 text-xs flex justify-between items-center">
                <div className="space-y-0.5">
                  <span className="font-semibold text-cyan-300">{rec.incident_type || rec.signature}</span>
                  <div className="text-[11px] text-white/50">{rec.description || "Terjadi beberapa kali dalam window historis"}</div>
                </div>
                <span className="font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[11px]">
                  {rec.frequency || rec.occurrence_count || 1}x terjadi
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-6 text-center text-xs text-white/40 italic">
            Belum terdeteksi pola insiden berulang atau flapping signifikan pada basis data historis.
          </div>
        )}
      </div>

      {/* Snapshot Diff Output */}
      {data.snapshot_diff && (
        <div className="bg-card border border-cyan-500/30 rounded-xl p-5 space-y-3">
          <div className="text-xs font-bold text-cyan-300 font-mono">Hasil Perbandingan Snapshot</div>
          <pre className="bg-black/40 p-3 rounded text-[11px] font-mono text-white/80 overflow-x-auto max-h-60">
            {JSON.stringify(data.snapshot_diff, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
