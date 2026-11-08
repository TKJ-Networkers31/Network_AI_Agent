// src/components/network-intelligence/KnowledgeGraphTab.jsx
import React, { useState } from "react";
import {
  ArrowRight,
  Database,
  Filter,
  Layers,
  Network,
  RefreshCw,
  Search,
  Server,
  Share2,
} from "lucide-react";

export default function KnowledgeGraphTab({
  graphData,
  loading,
  onRefreshGraph,
}) {
  const [selectedLayer, setSelectedLayer] = useState("ALL");
  const [searchFilter, setSearchFilter] = useState("");
  const [selectedEntity, setSelectedEntity] = useState(null);

  const layers = [
    { id: "ALL", label: "Semua Layer" },
    { id: "PHYSICAL", label: "Physical (L1)" },
    { id: "L2", label: "Data Link (L2)" },
    { id: "L3", label: "Network (L3)" },
    { id: "PROTOCOL", label: "Protocol (BGP/OSPF)" },
    { id: "DEPENDENCY", label: "Dependency" },
  ];

  const nodes = graphData?.nodes || [];
  const edges = graphData?.edges || [];

  const filteredEdges = edges.filter((e) => {
    if (selectedLayer !== "ALL" && e.layer !== selectedLayer) return false;
    if (searchFilter) {
      const q = searchFilter.toLowerCase();
      return (
        e.source_id.toLowerCase().includes(q) ||
        e.target_id.toLowerCase().includes(q) ||
        e.rel_type.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const filteredNodes = nodes.filter((n) => {
    if (searchFilter) {
      const q = searchFilter.toLowerCase();
      return (
        n.entity_id.toLowerCase().includes(q) ||
        (n.label && n.label.toLowerCase().includes(q)) ||
        n.entity_type.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div className="space-y-5">
      {/* Controls & Layer Selector */}
      <div className="bg-card border border-border p-4 rounded-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {layers.map((l) => (
            <button
              key={l.id}
              onClick={() => setSelectedLayer(l.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono transition ${
                selectedLayer === l.id
                  ? "bg-cyan-500 text-black font-bold shadow-md shadow-cyan-500/20"
                  : "bg-white/5 text-white/70 hover:text-white hover:bg-white/10"
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 w-full md:w-auto">
          <div className="relative flex-1 md:w-64">
            <Search size={14} className="absolute left-3 top-2.5 text-white/40" />
            <input
              type="text"
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              placeholder="Cari node / edge..."
              className="w-full bg-white/5 border border-border rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-white/30 focus:outline-none focus:border-cyan-500/50"
            />
          </div>
          <button
            onClick={() => onRefreshGraph(selectedLayer === "ALL" ? null : selectedLayer)}
            disabled={loading}
            className="p-2 bg-white/5 hover:bg-white/10 text-white/70 rounded-lg border border-border transition"
            title="Segarkan Graph"
          >
            <RefreshCw size={14} className={loading ? "animate-spin text-cyan-400" : ""} />
          </button>
        </div>
      </div>

      {/* Graph Summary Badges */}
      <div className="flex items-center gap-4 text-xs font-mono text-white/60">
        <div>Total Nodes: <span className="font-bold text-cyan-300">{nodes.length}</span></div>
        <div>Total Edges: <span className="font-bold text-cyan-300">{edges.length}</span></div>
        <div>Terfilter: <span className="text-white/90">{filteredNodes.length} nodes, {filteredEdges.length} edges</span></div>
      </div>

      {/* Nodes & Edges Inspection Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Nodes List */}
        <div className="bg-card border border-border rounded-xl p-4 space-y-3">
          <h4 className="text-xs font-bold text-white/90 uppercase tracking-wider flex items-center gap-2">
            <Server size={14} className="text-cyan-400" />
            <span>Entities / Nodes ({filteredNodes.length})</span>
          </h4>
          <div className="space-y-1.5 max-h-[420px] overflow-y-auto pr-1">
            {filteredNodes.length === 0 ? (
              <div className="text-center p-6 text-xs text-white/40 italic">Tidak ada node sesuai filter</div>
            ) : (
              filteredNodes.map((n) => (
                <div
                  key={n.entity_id}
                  onClick={() => setSelectedEntity(n)}
                  className={`p-2.5 rounded-lg border text-xs cursor-pointer transition ${
                    selectedEntity?.entity_id === n.entity_id
                      ? "bg-cyan-500/20 border-cyan-500/40 text-cyan-200"
                      : "bg-white/5 border-white/5 hover:bg-white/10 text-white/80"
                  }`}
                >
                  <div className="flex justify-between items-center font-mono">
                    <span className="font-semibold truncate">{n.label || n.entity_id}</span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-white/10 text-cyan-300">
                      {n.entity_type}
                    </span>
                  </div>
                  <div className="text-[11px] text-white/50 truncate mt-0.5">ID: {n.entity_id}</div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Edges List */}
        <div className="bg-card border border-border rounded-xl p-4 space-y-3">
          <h4 className="text-xs font-bold text-white/90 uppercase tracking-wider flex items-center gap-2">
            <Share2 size={14} className="text-cyan-400" />
            <span>Relationships / Edges ({filteredEdges.length})</span>
          </h4>
          <div className="space-y-1.5 max-h-[420px] overflow-y-auto pr-1">
            {filteredEdges.length === 0 ? (
              <div className="text-center p-6 text-xs text-white/40 italic">Tidak ada relasi sesuai filter</div>
            ) : (
              filteredEdges.map((e, idx) => (
                <div key={idx} className="p-2.5 rounded-lg bg-white/5 border border-white/5 text-xs space-y-1">
                  <div className="flex items-center justify-between text-[11px] font-mono">
                    <span className="text-cyan-300 font-bold truncate max-w-[40%]">{e.source_id}</span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                      {e.rel_type}
                    </span>
                    <span className="text-emerald-300 font-bold truncate max-w-[40%] text-right">{e.target_id}</span>
                  </div>
                  <div className="flex justify-between text-[10px] text-white/40 font-mono">
                    <span>Layer: {e.layer}</span>
                    <span>Confidence: {e.confidence || "HIGH"}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Selected Entity Property Inspector */}
      {selectedEntity && (
        <div className="bg-card border border-cyan-500/30 p-4 rounded-xl space-y-2">
          <div className="flex justify-between items-center text-xs">
            <span className="font-bold text-cyan-300 font-mono">Entity Inspector: {selectedEntity.entity_id}</span>
            <button
              onClick={() => setSelectedEntity(null)}
              className="text-white/40 hover:text-white text-xs font-mono"
            >
              Tutup
            </button>
          </div>
          <pre className="bg-black/40 p-3 rounded text-[11px] font-mono text-white/80 overflow-x-auto max-h-48">
            {JSON.stringify(selectedEntity, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
