// src/components/network-intelligence/PathAnalysisTab.jsx
import React, { useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  GitBranch,
  Layers,
  Loader2,
  MapPin,
  Network,
  RotateCcw,
  Search,
  ShieldAlert,
} from "lucide-react";

export default function PathAnalysisTab({
  pathResult,
  loading,
  onRunPathAnalysis,
  devices = [],
}) {
  const [destinationIp, setDestinationIp] = useState("8.8.8.8");
  const [sourceDevice, setSourceDevice] = useState("");
  const [routingTable, setRoutingTable] = useState("main");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!destinationIp.trim() || loading) return;
    onRunPathAnalysis({
      destinationIp: destinationIp.trim(),
      sourceDeviceId: sourceDevice.trim() || null,
      routingTable: routingTable.trim() || "main",
    });
  };

  const path = pathResult;

  const classificationColors = {
    FIB_CONFIRMED: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
    RIB_INFERRED: "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
    OBSERVED_FORWARDING: "bg-blue-500/20 text-blue-300 border-blue-500/40",
    PARTIAL_PATH: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    UNKNOWN_PATH: "bg-rose-500/20 text-rose-300 border-rose-500/40",
  };

  return (
    <div className="space-y-6">
      {/* Path Target Form */}
      <div className="bg-card border border-border p-5 rounded-xl shadow-lg space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GitBranch size={18} className="text-cyan-400" />
            <h3 className="text-sm font-bold text-white tracking-wide">
              Network Path Intelligence & Hop-by-Hop LPM
            </h3>
          </div>
          <span className="text-[11px] font-mono text-white/50">
            Simulasi LPM 5-Tier & Recursive Next-Hop
          </span>
        </div>

        <form onSubmit={handleSubmit} className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <div className="sm:col-span-2">
            <label className="block text-[11px] font-mono text-white/50 mb-1">Destination IP / CIDR</label>
            <input
              type="text"
              value={destinationIp}
              onChange={(e) => setDestinationIp(e.target.value)}
              placeholder="contoh: 8.8.8.8 atau 10.0.0.0/24"
              disabled={loading}
              className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-xs text-white placeholder-white/30 focus:outline-none focus:border-cyan-500/50"
            />
          </div>

          <div>
            <label className="block text-[11px] font-mono text-white/50 mb-1">Source Device (Opsional)</label>
            <input
              type="text"
              value={sourceDevice}
              onChange={(e) => setSourceDevice(e.target.value)}
              placeholder="Semua / Default"
              disabled={loading}
              className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-xs text-white placeholder-white/30 focus:outline-none focus:border-cyan-500/50"
            />
          </div>

          <div>
            <label className="block text-[11px] font-mono text-white/50 mb-1">Routing Table</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={routingTable}
                onChange={(e) => setRoutingTable(e.target.value)}
                placeholder="main"
                disabled={loading}
                className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-xs text-white placeholder-white/30 focus:outline-none focus:border-cyan-500/50"
              />
              <button
                type="submit"
                disabled={loading || !destinationIp.trim()}
                className="px-4 py-2 bg-cyan-500 hover:bg-cyan-400 text-black font-semibold rounded-lg text-xs flex items-center gap-1.5 transition disabled:opacity-40"
              >
                {loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                <span>Lacak</span>
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* Path Results */}
      {path && (
        <div className="space-y-4">
          {/* Path Header Badges */}
          <div className="bg-card border border-border p-4 rounded-xl flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className={`px-2.5 py-1 rounded-md text-xs font-mono font-bold border ${classificationColors[path.classification] || "bg-white/10 text-white"}`}>
                {path.classification}
              </span>
              <span className="text-xs font-mono text-white/60">
                Confidence: <strong className="text-cyan-300">{path.confidence || "MEDIUM"}</strong>
              </span>
            </div>

            <div className="flex items-center gap-3 text-xs font-mono">
              <div>Total Hops: <strong className="text-white">{path.hops?.length || 0}</strong></div>
              {path.has_loop && (
                <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 font-bold flex items-center gap-1">
                  <AlertTriangle size={12} /> LOOP TERDETEKSI
                </span>
              )}
              {path.is_ecmp && (
                <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30 font-bold">
                  ECMP ACTIVE
                </span>
              )}
            </div>
          </div>

          {/* Hop-by-Hop Visual Cards */}
          <div className="space-y-3">
            {path.hops && path.hops.length > 0 ? (
              path.hops.map((hop, idx) => (
                <div
                  key={idx}
                  className="bg-card border border-border p-4 rounded-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center font-mono font-bold text-xs text-cyan-300">
                      {idx + 1}
                    </div>
                    <div>
                      <div className="text-sm font-bold text-white flex items-center gap-2">
                        <span>{hop.device_id}</span>
                        {hop.is_destination_reached && (
                          <span className="text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-1.5 py-0.5 rounded">
                            DESTINATION
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-white/60 font-mono mt-0.5 flex flex-wrap gap-2">
                        <span>Egress: <strong className="text-white/80">{hop.egress_interface || "none"}</strong></span>
                        <span>•</span>
                        <span>Next-Hop: <strong className="text-cyan-300">{hop.next_hop_ip || "direct/connected"}</strong></span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 text-xs font-mono">
                    <div className="text-right">
                      <div className="text-white/40 text-[10px]">MATCHED PREFIX</div>
                      <div className="text-white font-bold">{hop.matched_prefix || "0.0.0.0/0"}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-white/40 text-[10px]">ADMIN DISTANCE</div>
                      <div className="text-white font-bold">{hop.admin_distance ?? 1}</div>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="bg-card border border-border p-6 rounded-xl text-center text-xs text-white/40 italic">
                Tidak ada hop rute yang ditemukan untuk destinasi {destinationIp}.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
