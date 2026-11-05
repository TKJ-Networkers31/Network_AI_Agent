// src/components/topology/SnapshotTimeline.jsx
// Interactive chronological timeline of immutable topology snapshots.

import { useState } from "react";
import {
  Calendar,
  Check,
  ChevronRight,
  Copy,
  ExternalLink,
  GitCompare,
  Layers,
  Network,
  RefreshCw,
  Search,
  Shield,
  ShieldCheck,
  Sparkles,
  Zap,
} from "lucide-react";
import SnapshotIntegrityBadge from "./SnapshotIntegrityBadge.jsx";
import { formatRelativeTime } from "./topologyConstants.js";
import { verifySnapshotIntegrity } from "./topologyHistoryApi.js";

export default function SnapshotTimeline({
  snapshots = [],
  loading = false,
  onRefresh,
  onSelectForCompare,
  onInspectSnapshot,
  onLoadOntoCanvas,
  pushToast,
}) {
  const [search, setSearch] = useState("");
  const [filterTrigger, setFilterTrigger] = useState("all");
  const [verifyingId, setVerifyingId] = useState(null);
  const [verificationMap, setVerificationMap] = useState({});
  const [copiedId, setCopiedId] = useState(null);

  const filteredSnapshots = snapshots.filter((s) => {
    const q = search.trim().toLowerCase();
    const matchSearch =
      !q ||
      s.snapshot_id.toLowerCase().includes(q) ||
      (s.description && s.description.toLowerCase().includes(q));
    const matchTrigger = filterTrigger === "all" || s.trigger_type === filterTrigger;
    return matchSearch && matchTrigger;
  });

  const handleVerify = async (snapshotId) => {
    setVerifyingId(snapshotId);
    try {
      const res = await verifySnapshotIntegrity(snapshotId);
      setVerificationMap((prev) => ({
        ...prev,
        [snapshotId]: res.verified ? "verified" : "compromised",
      }));
      if (res.verified) {
        if (typeof pushToast === "function") {
          pushToast(`Snapshot ${snapshotId} terverifikasi aman & utuh.`, "success");
        }
      } else {
        if (typeof pushToast === "function") {
          pushToast(`Peringatan: Hash snapshot ${snapshotId} tidak cocok!`, "error");
        }
      }
    } catch (err) {
      if (typeof pushToast === "function") {
        pushToast(`Gagal memverifikasi: ${err.message}`, "error");
      }
    } finally {
      setVerifyingId(null);
    }
  };

  const copyToClipboard = (text, id) => {
    navigator.clipboard?.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1800);
    if (typeof pushToast === "function") {
      pushToast("Checksum SHA-256 disalin ke clipboard.", "info");
    }
  };

  return (
    <div className="flex flex-col h-full space-y-3">
      {/* Search & Filter Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cari ID snapshot atau deskripsi..."
            className="w-full bg-black/60 border border-white/10 rounded-xl pl-9 pr-3 py-1.5 text-xs text-text-primary outline-none focus:border-sky-500/50"
          />
        </div>

        <div className="flex items-center gap-2">
          <select
            value={filterTrigger}
            onChange={(e) => setFilterTrigger(e.target.value)}
            className="bg-black/60 border border-white/10 rounded-xl px-2.5 py-1.5 text-xs text-text-secondary outline-none focus:border-sky-500/50"
          >
            <option value="all">Semua Tipe Trigger</option>
            <option value="manual">Manual</option>
            <option value="discovery_run">Discovery Scan</option>
            <option value="nms_sync">NMS Sync</option>
          </select>

          <button
            onClick={onRefresh}
            disabled={loading}
            className="p-1.5 rounded-xl bg-white/5 border border-white/10 text-neutral-400 hover:text-white hover:bg-white/10 transition"
            title="Muat ulang daftar snapshot"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Snapshot List Timeline */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1 custom-scrollbar">
        {loading && snapshots.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-8 text-neutral-400 space-y-2">
            <RefreshCw className="w-5 h-5 animate-spin text-sky-400" />
            <p className="text-xs">Memuat timeline snapshot...</p>
          </div>
        ) : filteredSnapshots.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-white/10 rounded-2xl">
            <Calendar className="w-8 h-8 text-neutral-600 mb-2" />
            <p className="text-sm font-semibold text-text-primary">Tidak Ada Snapshot Ditemukan</p>
            <p className="text-xs text-text-secondary mt-1">
              Gunakan tombol "Ambil Snapshot" untuk menyimpan titik waktu topologi sekarang.
            </p>
          </div>
        ) : (
          filteredSnapshots.map((s) => {
            const vStatus = verificationMap[s.snapshot_id] || "unverified";
            const dateStr = new Date((s.created_at || Date.now() / 1000) * 1000).toLocaleString("id-ID", {
              dateStyle: "medium",
              timeStyle: "medium",
            });
            const isComp = s.is_complete !== false;

            return (
              <div
                key={s.snapshot_id}
                className="group p-3 rounded-xl bg-white/[0.02] hover:bg-white/[0.05] border border-white/10 hover:border-sky-500/30 transition-all flex flex-col md:flex-row md:items-center justify-between gap-3"
              >
                {/* Snapshot Metadata Info */}
                <div className="space-y-1.5 flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-xs font-bold text-sky-400 tracking-wider">
                      {s.snapshot_id}
                    </span>

                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-mono font-bold tracking-wider ${
                        s.trigger_type === "manual"
                          ? "bg-blue-500/10 text-blue-300 border border-blue-500/20"
                          : s.trigger_type === "discovery_run"
                          ? "bg-purple-500/10 text-purple-300 border border-purple-500/20"
                          : "bg-cyan-500/10 text-cyan-300 border border-cyan-500/20"
                      }`}
                    >
                      {s.trigger_type}
                    </span>

                    <SnapshotIntegrityBadge status={vStatus} isComplete={isComp} />
                  </div>

                  <p className="text-xs text-text-primary font-medium truncate">
                    {s.description || "Titik waktu topologi terisolasi"}
                  </p>

                  <div className="flex items-center gap-3 text-[11px] text-text-secondary flex-wrap">
                    <span className="flex items-center gap-1" title={dateStr}>
                      <Calendar className="w-3 h-3 text-neutral-400" />
                      {formatRelativeTime(s.created_at)}
                    </span>

                    <span className="flex items-center gap-1" title="Jumlah Perangkat">
                      <Network className="w-3 h-3 text-sky-400" />
                      {s.node_count ?? 0} node
                    </span>

                    <span className="flex items-center gap-1" title="Jumlah Koneksi/Wiring">
                      <Layers className="w-3 h-3 text-purple-400" />
                      {s.edge_count ?? 0} link
                    </span>

                    {s.sha256_hash && (
                      <span className="flex items-center gap-1 font-mono text-[10px] text-neutral-400">
                        <span>SHA:</span>
                        <span className="text-neutral-300">{s.sha256_hash.slice(0, 10)}...</span>
                        <button
                          onClick={() => copyToClipboard(s.sha256_hash, s.snapshot_id)}
                          className="hover:text-white"
                          title="Salin SHA-256 lengkap"
                        >
                          {copiedId === s.snapshot_id ? (
                            <Check className="w-2.5 h-2.5 text-emerald-400" />
                          ) : (
                            <Copy className="w-2.5 h-2.5" />
                          )}
                        </button>
                      </span>
                    )}
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="flex items-center gap-1.5 self-end md:self-center shrink-0">
                  <button
                    onClick={() => handleVerify(s.snapshot_id)}
                    disabled={verifyingId === s.snapshot_id}
                    className="px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-emerald-500/15 border border-white/10 hover:border-emerald-500/30 text-neutral-300 hover:text-emerald-300 text-xs transition flex items-center gap-1"
                    title="Uji integritas SHA-256 snapshot"
                  >
                    <ShieldCheck className={`w-3.5 h-3.5 ${verifyingId === s.snapshot_id ? "animate-spin" : ""}`} />
                    <span className="hidden sm:inline">Verifikasi</span>
                  </button>

                  <button
                    onClick={() => onSelectForCompare?.(s.snapshot_id)}
                    className="px-2.5 py-1.5 rounded-lg bg-sky-500/10 hover:bg-sky-500/20 border border-sky-500/25 text-sky-300 text-xs transition flex items-center gap-1"
                    title="Bandingkan dengan snapshot lain"
                  >
                    <GitCompare className="w-3.5 h-3.5" />
                    <span>Compare</span>
                  </button>

                  <button
                    onClick={() => onInspectSnapshot?.(s.snapshot_id)}
                    className="px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-neutral-300 hover:text-white text-xs transition flex items-center gap-1"
                    title="Lihat detail node & edge di snapshot ini"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">Detail</span>
                  </button>

                  {typeof onLoadOntoCanvas === "function" && (
                    <button
                      onClick={() => onLoadOntoCanvas(s.snapshot_id)}
                      className="px-2 py-1.5 rounded-lg bg-purple-500/10 hover:bg-purple-500/20 border border-purple-500/25 text-purple-300 text-xs transition"
                      title="Tampilkan peta snapshot ini di kanvas topologi (read-only)"
                    >
                      Kanvas
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
