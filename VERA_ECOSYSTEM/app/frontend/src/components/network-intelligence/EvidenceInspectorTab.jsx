// src/components/network-intelligence/EvidenceInspectorTab.jsx
import React, { useState } from "react";
import {
  Code,
  Eye,
  Filter,
  Layers,
  Search,
  ShieldCheck,
  Terminal,
} from "lucide-react";

export default function EvidenceInspectorTab({ evidenceItems = [] }) {
  const [filterType, setFilterType] = useState("ALL");
  const [filterDevice, setFilterDevice] = useState("ALL");
  const [search, setSearch] = useState("");
  const [selectedItem, setSelectedItem] = useState(null);

  const items = evidenceItems || [];

  const types = ["ALL", ...Array.from(new Set(items.map((i) => i.observation_type || i.type).filter(Boolean)))];
  const devices = ["ALL", ...Array.from(new Set(items.map((i) => i.device_id || i.device_identity).filter(Boolean)))];

  const filtered = items.filter((it) => {
    const itType = it.observation_type || it.type;
    const itDev = it.device_id || it.device_identity;
    if (filterType !== "ALL" && itType !== filterType) return false;
    if (filterDevice !== "ALL" && itDev !== filterDevice) return false;
    if (search) {
      const q = search.toLowerCase();
      const idMatch = (it.evidence_id || "").toLowerCase().includes(q);
      const cmdMatch = (it.source_command || "").toLowerCase().includes(q);
      return idMatch || cmdMatch;
    }
    return true;
  });

  const freshnessPill = (f) => {
    const val = (f || "FRESH").toUpperCase();
    if (val === "FRESH") return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
    if (val === "AGING") return "bg-cyan-500/20 text-cyan-300 border-cyan-500/30";
    if (val === "STALE") return "bg-amber-500/20 text-amber-300 border-amber-500/30";
    return "bg-rose-500/20 text-rose-300 border-rose-500/30";
  };

  return (
    <div className="space-y-5">
      {/* Search and Filters */}
      <div className="bg-card border border-border p-4 rounded-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5 text-xs font-mono">
            <span className="text-white/40">Tipe:</span>
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="bg-white/5 border border-border rounded px-2 py-1 text-xs text-white focus:outline-none"
            >
              {types.map((t) => (
                <option key={t} value={t} className="bg-zinc-900 text-white">
                  {t}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5 text-xs font-mono">
            <span className="text-white/40">Perangkat:</span>
            <select
              value={filterDevice}
              onChange={(e) => setFilterDevice(e.target.value)}
              className="bg-white/5 border border-border rounded px-2 py-1 text-xs text-white focus:outline-none"
            >
              {devices.map((d) => (
                <option key={d} value={d} className="bg-zinc-900 text-white">
                  {d}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="relative w-full md:w-64">
          <Search size={14} className="absolute left-3 top-2.5 text-white/40" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cari command / ID..."
            className="w-full bg-white/5 border border-border rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-white/30 focus:outline-none focus:border-cyan-500/50"
          />
        </div>
      </div>

      {/* Evidence Items Table/Cards */}
      <div className="bg-card border border-border rounded-xl p-4 space-y-3">
        <div className="flex justify-between items-center text-xs">
          <span className="font-bold text-white/90 uppercase tracking-wider flex items-center gap-2">
            <ShieldCheck size={14} className="text-cyan-400" />
            <span>Katalog Bukti Observasi Kanonikal ({filtered.length} items)</span>
          </span>
          <span className="text-white/40 font-mono text-[11px]">Strictly Invariant & Inspectable</span>
        </div>

        <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
          {filtered.length === 0 ? (
            <div className="p-8 text-center text-xs text-white/40 italic">
              Tidak ada bukti kanonikal yang sesuai kriteria filter.
            </div>
          ) : (
            filtered.map((it, idx) => {
              const dev = it.device_id || it.device_identity;
              const obsType = it.observation_type || it.type;
              return (
                <div
                  key={idx}
                  onClick={() => setSelectedItem(it)}
                  className={`p-3 rounded-lg border text-xs cursor-pointer transition flex flex-col md:flex-row justify-between items-start md:items-center gap-2 ${
                    selectedItem === it
                      ? "bg-cyan-500/20 border-cyan-500/40 text-cyan-200"
                      : "bg-white/5 border-white/5 hover:bg-white/10 text-white/80"
                  }`}
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 font-mono">
                      <span className="font-bold text-white">{dev}</span>
                      <span className="text-white/40">•</span>
                      <span className="text-cyan-300 font-semibold">{obsType}</span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] border ${freshnessPill(it.freshness)}`}>
                        {it.freshness || "FRESH"}
                      </span>
                    </div>
                    <div className="text-[11px] text-white/50 font-mono truncate max-w-md">
                      Cmd: <code className="text-white/70">{it.source_command || "/read-only-check"}</code>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 text-xs font-mono self-end md:self-center">
                    <span className="text-[11px] text-white/40">
                      Confidence: <strong className="text-white/80">{it.confidence || "HIGH"}</strong>
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedItem(it);
                      }}
                      className="p-1.5 bg-white/5 hover:bg-cyan-500/20 rounded border border-white/10 hover:border-cyan-500/40 text-white/70 hover:text-cyan-300 transition"
                      title="Lihat Detail Bukti"
                    >
                      <Eye size={13} />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Selected Evidence Item Detail Drawer */}
      {selectedItem && (
        <div className="bg-card border border-cyan-500/30 p-5 rounded-xl space-y-3">
          <div className="flex justify-between items-center text-xs">
            <span className="font-bold text-cyan-300 font-mono">
              Evidence Detail: {selectedItem.evidence_id || "Kanonikal"}
            </span>
            <button onClick={() => setSelectedItem(null)} className="text-white/40 hover:text-white text-xs font-mono">
              Tutup
            </button>
          </div>

          {selectedItem.limitations && (
            <div className="text-xs text-amber-300/80 bg-amber-500/10 border border-amber-500/20 p-2.5 rounded font-mono">
              <strong>Keterbatasan Terbuka: </strong>
              {Array.isArray(selectedItem.limitations)
                ? selectedItem.limitations.join("; ")
                : String(selectedItem.limitations)}
            </div>
          )}

          <pre className="bg-black/40 p-3 rounded text-[11px] font-mono text-white/80 overflow-x-auto max-h-60">
            {JSON.stringify(selectedItem.normalized_payload || selectedItem.normalized_value || selectedItem, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
