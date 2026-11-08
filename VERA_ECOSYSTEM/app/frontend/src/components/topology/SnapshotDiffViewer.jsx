// src/components/topology/SnapshotDiffViewer.jsx
// Semantic graph diff comparison interface across historical snapshots.

import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowLeftRight,
  ArrowRight,
  CheckCircle2,
  Clock,
  ExternalLink,
  GitCompare,
  Layers,
  Network,
  RefreshCw,
  Shield,
  ShieldAlert,
  Sparkles,
  Zap,
} from "lucide-react";
import { compareSnapshots } from "./topologyHistoryApi.js";

export default function SnapshotDiffViewer({
  snapshots = [],
  preselectedBaseId = "",
  preselectedTargetId = "",
  pushToast,
}) {
  const [baseId, setBaseId] = useState(preselectedBaseId || (snapshots[1]?.snapshot_id || snapshots[0]?.snapshot_id || ""));
  const [targetId, setTargetId] = useState(preselectedTargetId || (snapshots[0]?.snapshot_id || ""));
  const [loading, setLoading] = useState(false);
  const [diffReport, setDiffReport] = useState(null);
  const [activeCategory, setActiveCategory] = useState("all");

  // Keep synced if preselected changes
  useEffect(() => {
    if (preselectedBaseId) setBaseId(preselectedBaseId);
  }, [preselectedBaseId]);

  useEffect(() => {
    if (preselectedTargetId) setTargetId(preselectedTargetId);
  }, [preselectedTargetId]);

  const handleRunDiff = async () => {
    if (!baseId || !targetId) {
      if (typeof pushToast === "function") {
        pushToast("Pilih snapshot awal (Base) dan target untuk dibandingkan.", "warning");
      }
      return;
    }
    setLoading(true);
    try {
      const res = await compareSnapshots(baseId, targetId);
      if (res.success && res.diff) {
        setDiffReport(res.diff);
      }
    } catch (err) {
      if (typeof pushToast === "function") {
        pushToast(`Gagal membandingkan snapshot: ${err.message}`, "error");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSwap = () => {
    const tmp = baseId;
    setBaseId(targetId);
    setTargetId(tmp);
  };

  const summary = diffReport?.summary || {};
  const telemetry = diffReport?.telemetry || {};

  // Combine items according to active filter
  const allChanges = [];
  if (diffReport) {
    (diffReport.structural_changes || []).forEach((c) => allChanges.push({ ...c, category: "structural" }));
    (diffReport.operational_changes || []).forEach((c) => allChanges.push({ ...c, category: "operational" }));
    (diffReport.evidence_changes || []).forEach((c) => allChanges.push({ ...c, category: "evidence" }));
    (diffReport.freshness_changes || []).forEach((c) => allChanges.push({ ...c, category: "freshness" }));
  }

  const displayedChanges = allChanges.filter((item) => {
    if (activeCategory === "all") return true;
    return item.category === activeCategory;
  });

  const indeterminateItems = diffReport?.indeterminate_items || [];

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Snapshot Pickers & Compare Action Bar */}
      <div className="p-3.5 rounded-2xl bg-white/[0.02] border border-white/10 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-2 flex-1 flex-wrap">
          <div className="flex-1 min-w-[200px]">
            <label className="text-[10px] text-text-secondary uppercase font-semibold block mb-1">
              Base Snapshot (Referensi/Lama)
            </label>
            <select
              value={baseId}
              onChange={(e) => setBaseId(e.target.value)}
              className="w-full bg-black/80 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-sky-300 font-mono outline-none focus:border-sky-500/50"
            >
              <option value="">Pilih Base...</option>
              {snapshots.map((s) => (
                <option key={s.snapshot_id} value={s.snapshot_id}>
                  {s.snapshot_id} ({s.node_count}n, {s.edge_count}e) - {s.description?.slice(0, 24)}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={handleSwap}
            className="self-end mb-1 p-2 rounded-xl bg-white/5 border border-white/10 text-neutral-400 hover:text-white hover:bg-white/10 transition"
            title="Tukar Base & Target"
          >
            <ArrowLeftRight className="w-3.5 h-3.5" />
          </button>

          <div className="flex-1 min-w-[200px]">
            <label className="text-[10px] text-text-secondary uppercase font-semibold block mb-1">
              Target Snapshot (Baru/Pembanding)
            </label>
            <select
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              className="w-full bg-black/80 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-purple-300 font-mono outline-none focus:border-purple-500/50"
            >
              <option value="">Pilih Target...</option>
              {snapshots.map((s) => (
                <option key={s.snapshot_id} value={s.snapshot_id}>
                  {s.snapshot_id} ({s.node_count}n, {s.edge_count}e) - {s.description?.slice(0, 24)}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button
          onClick={handleRunDiff}
          disabled={loading || !baseId || !targetId}
          className="self-end md:self-center px-4 py-2 rounded-xl bg-gradient-to-r from-sky-500/20 to-purple-500/20 hover:from-sky-500/30 hover:to-purple-500/30 border border-sky-500/30 text-white font-medium text-xs transition flex items-center gap-1.5 disabled:opacity-40 shadow-sm"
        >
          <GitCompare className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>{loading ? "Menghitung Diff..." : "Bandingkan"}</span>
        </button>
      </div>

      {/* Diff Output Container */}
      {diffReport ? (
        <div className="flex-1 overflow-y-auto space-y-4 pr-1 custom-scrollbar">
          {/* Metric Summary Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
            <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/10 text-center">
              <span className="text-[10px] text-neutral-400 block">Nodes Added</span>
              <span className={`text-sm font-bold ${summary.nodes_added > 0 ? "text-emerald-400" : "text-neutral-500"}`}>
                +{summary.nodes_added || 0}
              </span>
            </div>

            <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/10 text-center">
              <span className="text-[10px] text-neutral-400 block">Nodes Removed</span>
              <span className={`text-sm font-bold ${summary.nodes_removed > 0 ? "text-red-400" : "text-neutral-500"}`}>
                -{summary.nodes_removed || 0}
              </span>
            </div>

            <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/10 text-center">
              <span className="text-[10px] text-neutral-400 block">Nodes Modified</span>
              <span className={`text-sm font-bold ${summary.nodes_modified > 0 ? "text-amber-400" : "text-neutral-500"}`}>
                ~{summary.nodes_modified || 0}
              </span>
            </div>

            <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/10 text-center">
              <span className="text-[10px] text-neutral-400 block">Edges Added</span>
              <span className={`text-sm font-bold ${summary.edges_added > 0 ? "text-emerald-400" : "text-neutral-500"}`}>
                +{summary.edges_added || 0}
              </span>
            </div>

            <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/10 text-center">
              <span className="text-[10px] text-neutral-400 block">Edges Removed</span>
              <span className={`text-sm font-bold ${summary.edges_removed > 0 ? "text-red-400" : "text-neutral-500"}`}>
                -{summary.edges_removed || 0}
              </span>
            </div>

            <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/10 text-center">
              <span className="text-[10px] text-neutral-400 block">Status / Oper</span>
              <span className={`text-sm font-bold ${summary.operational_changes > 0 ? "text-cyan-400" : "text-neutral-500"}`}>
                {summary.operational_changes || 0}
              </span>
            </div>

            <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/10 text-center">
              <span className="text-[10px] text-neutral-400 block">Indeterminate</span>
              <span className={`text-sm font-bold ${summary.indeterminate_count > 0 ? "text-amber-400" : "text-neutral-500"}`}>
                {summary.indeterminate_count || 0}
              </span>
            </div>
          </div>

          {/* Telemetry info */}
          <div className="flex items-center justify-between text-[11px] text-neutral-400 px-1">
            <span>
              Perbandingan selesai dalam{" "}
              <span className="text-sky-400 font-mono">{telemetry.total_duration_ms || 0}ms</span> (DB Read:{" "}
              {telemetry.db_query_ms || 0}ms, Diff CPU: {telemetry.diff_compute_ms || 0}ms)
            </span>
            <span>
              Base: {telemetry.base_graph_size?.nodes || 0}n / {telemetry.base_graph_size?.edges || 0}e ➔ Target:{" "}
              {telemetry.target_graph_size?.nodes || 0}n / {telemetry.target_graph_size?.edges || 0}e
            </span>
          </div>

          {/* Indeterminate Warning Banner if any */}
          {indeterminateItems.length > 0 && (
            <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/25 space-y-2">
              <div className="flex items-center gap-2 text-amber-300 font-semibold text-xs">
                <ShieldAlert className="w-4 h-4 text-amber-400" />
                <span>Epistemic False-Positive Protection: {indeterminateItems.length} Status Indeterminate</span>
              </div>
              <p className="text-[11px] text-amber-200/80">
                Item di bawah ini tidak dapat diuji sepenuhnya selama pemindaian target (perangkat tidak terjangkau atau
                informasi interface belum lengkap). AIRA OS sengaja <strong>TIDAK menghapus</strong> item ini dari
                topologi guna mencegah alarm palsu.
              </p>
              <div className="space-y-1.5 mt-2">
                {indeterminateItems.map((item, idx) => (
                  <div
                    key={idx}
                    className="p-2 rounded-lg bg-black/40 border border-amber-500/20 text-[11px] flex items-center justify-between gap-2"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-amber-400/10 text-amber-400 border border-amber-400/20 font-bold">
                        {item.indeterminate_type}
                      </span>
                      <span className="font-mono text-white">{item.entity_id}</span>
                      <span className="text-neutral-400">({item.reason})</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Category Tabs */}
          <div className="flex items-center gap-1.5 border-b border-white/10 pb-2">
            {[
              { id: "all", label: `Semua Perubahan (${allChanges.length})` },
              { id: "structural", label: `Struktural (${summary.nodes_added + summary.nodes_removed + summary.edges_added + summary.edges_removed || 0})` },
              { id: "operational", label: `Operasional (${summary.operational_changes || 0})` },
              { id: "evidence", label: `Bukti & Confidence (${summary.evidence_changes || 0})` },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveCategory(tab.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                  activeCategory === tab.id
                    ? "bg-white/10 text-white border border-white/20"
                    : "text-neutral-400 hover:text-white hover:bg-white/5"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Change Items List */}
          <div className="space-y-2">
            {displayedChanges.length === 0 ? (
              <div className="p-8 text-center text-neutral-400 text-xs border border-dashed border-white/10 rounded-xl">
                Tidak ada perubahan dalam kategori ini.
              </div>
            ) : (
              displayedChanges.map((c, idx) => {
                const isAdd = c.change_type.includes("ADDED");
                const isRem = c.change_type.includes("REMOVED");
                const isMod = c.change_type.includes("MODIFIED") || c.change_type.includes("CHANGED");

                return (
                  <div
                    key={idx}
                    className="p-3 rounded-xl bg-white/[0.02] border border-white/10 hover:border-white/20 transition flex flex-col sm:flex-row sm:items-center justify-between gap-2"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold tracking-wider ${
                            isAdd
                              ? "bg-emerald-500/10 text-emerald-300 border border-emerald-500/25"
                              : isRem
                              ? "bg-red-500/10 text-red-300 border border-red-500/25"
                              : "bg-sky-500/10 text-sky-300 border border-sky-500/25"
                          }`}
                        >
                          {c.change_type}
                        </span>

                        <span className="font-mono text-xs font-bold text-text-primary">
                          {c.entity_id}
                        </span>

                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-white/5 text-neutral-400 uppercase">
                          {c.entity_type || "entity"}
                        </span>
                      </div>

                      <p className="text-xs text-text-secondary">{c.change_reason}</p>
                    </div>

                    {/* Value Transition */}
                    {(c.before_value !== undefined || c.after_value !== undefined) && (
                      <div className="flex items-center gap-2 text-xs font-mono self-end sm:self-center bg-black/40 px-2.5 py-1.5 rounded-lg border border-white/5">
                        <span className="text-neutral-400 line-through">
                          {typeof c.before_value === "object" ? JSON.stringify(c.before_value)?.slice(0, 16) : String(c.before_value ?? "none")}
                        </span>
                        <ArrowRight className="w-3 h-3 text-sky-400" />
                        <span className="text-emerald-400 font-semibold">
                          {typeof c.after_value === "object" ? JSON.stringify(c.after_value)?.slice(0, 16) : String(c.after_value ?? "none")}
                        </span>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center p-12 text-center border border-dashed border-white/10 rounded-2xl">
          <GitCompare className="w-8 h-8 text-neutral-600 mb-2" />
          <p className="text-sm font-semibold text-text-primary">Pilih Dua Titik Snapshot untuk Dibandingkan</p>
          <p className="text-xs text-text-secondary mt-1 max-w-md">
            Semantic Graph Diff Engine akan membandingkan node, wiring fisik, status operasional, kesegaran observasi,
            serta membuktikan integritas perubahan tanpa mengunci database.
          </p>
        </div>
      )}
    </div>
  );
}
