// src/components/topology/TopologyChangeLog.jsx
// Chronological topology delta change audit log with multi-field filters & JSON inspection.

import { useEffect, useState } from "react";
import {
  ArrowRight,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Clock,
  Code,
  ExternalLink,
  Filter,
  History,
  Layers,
  Network,
  RefreshCw,
  Search,
  Shield,
  X,
} from "lucide-react";
import { formatRelativeTime } from "./topologyConstants.js";
import { getChange, listChanges } from "./topologyHistoryApi.js";

export default function TopologyChangeLog({ pushToast }) {
  const [changes, setChanges] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(0);
  const limit = 25;

  // Filters
  const [searchEntity, setSearchEntity] = useState("");
  const [filterType, setFilterType] = useState("");
  const [filterSnapshot, setFilterSnapshot] = useState("");

  // Inspect detail dialog
  const [selectedChange, setSelectedChange] = useState(null);
  const [inspectLoading, setInspectLoading] = useState(false);

  const fetchChanges = async () => {
    setLoading(true);
    try {
      const res = await listChanges({
        entity_id: searchEntity.trim() || null,
        change_type: filterType || null,
        snapshot_id: filterSnapshot.trim() || null,
        limit,
        offset: page * limit,
      });
      if (res.success) {
        setChanges(res.changes || []);
        setTotal(res.total || 0);
      }
    } catch (err) {
      if (typeof pushToast === "function") {
        pushToast(`Gagal memuat riwayat perubahan: ${err.message}`, "error");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchChanges();
  }, [page, filterType]);

  const handleApplyFilter = (e) => {
    e?.preventDefault();
    setPage(0);
    fetchChanges();
  };

  const handleInspect = async (changeId) => {
    setInspectLoading(true);
    try {
      const res = await getChange(changeId);
      if (res.success && res.change) {
        setSelectedChange(res.change);
      }
    } catch (err) {
      if (typeof pushToast === "function") {
        pushToast(`Gagal memuat detail change #${changeId}: ${err.message}`, "error");
      }
    } finally {
      setInspectLoading(false);
    }
  };

  const totalPages = Math.ceil(total / limit) || 1;

  return (
    <div className="flex flex-col h-full space-y-3">
      {/* Filter Toolbar */}
      <form onSubmit={handleApplyFilter} className="flex items-center gap-2 flex-wrap text-xs">
        <div className="relative flex-1 min-w-[160px]">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <input
            type="text"
            value={searchEntity}
            onChange={(e) => setSearchEntity(e.target.value)}
            placeholder="Filter ID Perangkat / Edge..."
            className="w-full bg-black/60 border border-white/10 rounded-xl pl-9 pr-3 py-1.5 text-text-primary outline-none focus:border-sky-500/50"
          />
        </div>

        <select
          value={filterType}
          onChange={(e) => {
            setFilterType(e.target.value);
            setPage(0);
          }}
          className="bg-black/60 border border-white/10 rounded-xl px-2.5 py-1.5 text-text-secondary outline-none focus:border-sky-500/50"
        >
          <option value="">Semua Kategori</option>
          <option value="STATUS_CHANGED">STATUS_CHANGED</option>
          <option value="NODE_ADDED">NODE_ADDED</option>
          <option value="NODE_REMOVED">NODE_REMOVED</option>
          <option value="NODE_MODIFIED">NODE_MODIFIED</option>
          <option value="EDGE_ADDED">EDGE_ADDED</option>
          <option value="EDGE_REMOVED">EDGE_REMOVED</option>
          <option value="CONFIDENCE_CHANGED">CONFIDENCE_CHANGED</option>
          <option value="EVIDENCE_CHANGED">EVIDENCE_CHANGED</option>
          <option value="EVIDENCE_EXPIRED">EVIDENCE_EXPIRED</option>
        </select>

        <button
          type="submit"
          className="px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-white font-medium transition"
        >
          Terapkan
        </button>

        <button
          type="button"
          onClick={() => {
            setSearchEntity("");
            setFilterType("");
            setFilterSnapshot("");
            setPage(0);
            fetchChanges();
          }}
          className="px-2.5 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-white transition"
          title="Reset filter"
        >
          Reset
        </button>
      </form>

      {/* Changes Table / List */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1 custom-scrollbar">
        {loading && changes.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-8 text-neutral-400 space-y-2">
            <RefreshCw className="w-5 h-5 animate-spin text-sky-400" />
            <p className="text-xs">Memuat riwayat perubahan topologi...</p>
          </div>
        ) : changes.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-white/10 rounded-2xl">
            <History className="w-8 h-8 text-neutral-600 mb-2" />
            <p className="text-sm font-semibold text-text-primary">Tidak Ada Riwayat Perubahan</p>
            <p className="text-xs text-text-secondary mt-1">
              Perubahan topologi (status link, penambahan node, bukti lldp) akan tercatat otomatis di sini.
            </p>
          </div>
        ) : (
          changes.map((c) => {
            const isAdd = c.change_type.includes("ADDED");
            const isRem = c.change_type.includes("REMOVED");

            return (
              <div
                key={c.id}
                className="p-3 rounded-xl bg-white/[0.02] hover:bg-white/[0.05] border border-white/10 hover:border-white/20 transition flex flex-col md:flex-row md:items-center justify-between gap-2"
              >
                <div className="space-y-1 flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-[10px] text-neutral-500 font-bold">#{c.id}</span>

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

                    <span className="font-mono text-xs font-bold text-white truncate">{c.entity_id}</span>

                    {c.attribute_name && (
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-white/5 text-neutral-400">
                        attr: {c.attribute_name}
                      </span>
                    )}
                  </div>

                  <p className="text-xs text-text-secondary truncate">{c.change_reason}</p>

                  <div className="flex items-center gap-3 text-[11px] text-text-secondary flex-wrap">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3 text-neutral-400" />
                      {formatRelativeTime(c.detected_at)}
                    </span>

                    {c.snapshot_id && (
                      <span className="font-mono text-[10px] text-neutral-400">
                        Snap: {c.snapshot_id}
                      </span>
                    )}
                  </div>
                </div>

                {/* Before / After & Action */}
                <div className="flex items-center gap-2 self-end md:self-center shrink-0">
                  {(c.before_value !== undefined || c.after_value !== undefined) && (
                    <div className="hidden sm:flex items-center gap-1.5 text-xs font-mono bg-black/40 px-2 py-1 rounded-lg border border-white/5">
                      <span className="text-neutral-400 line-through">
                        {typeof c.before_value === "object" ? JSON.stringify(c.before_value)?.slice(0, 10) : String(c.before_value ?? "none")}
                      </span>
                      <ArrowRight className="w-3 h-3 text-sky-400" />
                      <span className="text-emerald-400 font-semibold">
                        {typeof c.after_value === "object" ? JSON.stringify(c.after_value)?.slice(0, 10) : String(c.after_value ?? "none")}
                      </span>
                    </div>
                  )}

                  <button
                    onClick={() => handleInspect(c.id)}
                    className="px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-xs text-neutral-300 hover:text-white transition flex items-center gap-1"
                    title="Inspeksi detail JSON & bukti terkait"
                  >
                    <Code className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">Inspeksi</span>
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Pagination Footer */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-text-secondary border-t border-white/10 pt-2 px-1">
          <span>
            Menampilkan {changes.length} dari {total} perubahan
          </span>

          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="p-1 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 disabled:opacity-30"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>

            <span className="px-2 font-mono text-[11px]">
              Hal {page + 1} / {totalPages}
            </span>

            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="p-1 rounded-lg bg-white/5 border border-white/10 hover:bg-white/10 disabled:opacity-30"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Detail Inspector Modal */}
      {selectedChange && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-neutral-950 border border-white/10 rounded-2xl w-full max-w-2xl p-5 shadow-2xl relative max-h-[85vh] overflow-y-auto space-y-4">
            <button
              onClick={() => setSelectedChange(null)}
              className="absolute top-4 right-4 p-1 rounded-lg text-neutral-400 hover:text-white hover:bg-white/10"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex items-center gap-2">
              <span className="font-mono text-xs px-2 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/20 font-bold">
                {selectedChange.change_type}
              </span>
              <h3 className="text-sm font-bold text-white">Perubahan #{selectedChange.id}</h3>
            </div>

            <div className="space-y-2 text-xs">
              <div>
                <span className="text-neutral-400 block mb-0.5">Entitas Target:</span>
                <span className="font-mono text-white bg-black/50 px-2 py-1 rounded border border-white/10 inline-block">
                  {selectedChange.entity_id}
                </span>
              </div>

              <div>
                <span className="text-neutral-400 block mb-0.5">Alasan Perubahan:</span>
                <p className="text-white bg-black/40 p-2.5 rounded-xl border border-white/10">
                  {selectedChange.change_reason}
                </p>
              </div>

              {/* State JSON Inspector */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2">
                <div>
                  <span className="text-neutral-400 text-[11px] block mb-1">State Sebelumnya (Before):</span>
                  <pre className="bg-black p-2.5 rounded-xl border border-white/10 text-[11px] font-mono text-red-300 max-h-48 overflow-auto">
                    {JSON.stringify(selectedChange.before_value, null, 2) || "null"}
                  </pre>
                </div>

                <div>
                  <span className="text-neutral-400 text-[11px] block mb-1">State Sesudahnya (After):</span>
                  <pre className="bg-black p-2.5 rounded-xl border border-white/10 text-[11px] font-mono text-emerald-300 max-h-48 overflow-auto">
                    {JSON.stringify(selectedChange.after_value, null, 2) || "null"}
                  </pre>
                </div>
              </div>

              {/* Related Evidence if any */}
              {selectedChange.related_evidence?.length > 0 && (
                <div className="pt-2">
                  <span className="text-neutral-400 text-[11px] block mb-1">
                    Bukti Terkait ({selectedChange.related_evidence.length}):
                  </span>
                  <div className="space-y-1.5">
                    {selectedChange.related_evidence.map((ev, i) => (
                      <div
                        key={i}
                        className="p-2 rounded-lg bg-black/40 border border-white/10 text-[11px] flex items-center justify-between"
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-sky-400 font-mono">{ev.protocol || ev.evidence_type}</span>
                          <span className="text-neutral-300">{ev.local_interface}</span>
                          <span className="text-neutral-500">({ev.explanation || "Empirical discovery"})</span>
                        </div>
                        <span className="text-[10px] text-neutral-400 font-mono">
                          freshness: {ev.is_active ? "active" : "inactive"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
