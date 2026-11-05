// src/components/topology/TopologyHistoryModal.jsx
// Primary Historical Topology & Change Detection container dialog in AIRA OS.

import { useEffect, useState } from "react";
import {
  Calendar,
  Camera,
  GitCompare,
  History,
  Layers,
  RefreshCw,
  Shield,
  X,
} from "lucide-react";
import SnapshotTimeline from "./SnapshotTimeline.jsx";
import SnapshotDiffViewer from "./SnapshotDiffViewer.jsx";
import TopologyChangeLog from "./TopologyChangeLog.jsx";
import { createSnapshot, listSnapshots } from "./topologyHistoryApi.js";

export default function TopologyHistoryModal({
  open,
  onClose,
  onLoadOntoCanvas,
  pushToast,
}) {
  const [activeTab, setActiveTab] = useState("timeline"); // timeline | compare | changes
  const [snapshots, setSnapshots] = useState([]);
  const [totalSnapshots, setTotalSnapshots] = useState(0);
  const [loading, setLoading] = useState(false);

  // Cross-tab compare pre-selection
  const [compareBaseId, setCompareBaseId] = useState("");
  const [compareTargetId, setCompareTargetId] = useState("");

  // Create snapshot modal
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createDesc, setCreateDesc] = useState("");
  const [creating, setCreating] = useState(false);

  const fetchSnapshots = async () => {
    setLoading(true);
    try {
      const res = await listSnapshots({ limit: 100 });
      if (res.success) {
        setSnapshots(res.snapshots || []);
        setTotalSnapshots(res.total || 0);
      }
    } catch (err) {
      if (typeof pushToast === "function") {
        pushToast(`Gagal memuat daftar snapshot: ${err.message}`, "error");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      fetchSnapshots();
    }
  }, [open]);

  const handleSelectForCompare = (snapshotId) => {
    if (!compareBaseId) {
      setCompareBaseId(snapshotId);
      if (typeof pushToast === "function") {
        pushToast(`Snapshot ${snapshotId} dipilih sebagai Base. Pilih satu lagi untuk Target.`, "info");
      }
    } else {
      setCompareTargetId(snapshotId);
      setActiveTab("compare");
    }
  };

  const handleCreateSnapshot = async (e) => {
    e?.preventDefault();
    setCreating(true);
    try {
      const res = await createSnapshot({
        description: createDesc.trim() || "Manual snapshot from Web UI",
        trigger_type: "manual",
      });
      if (res.success) {
        if (typeof pushToast === "function") {
          pushToast(res.message || "Snapshot berhasil dibuat.", "success");
        }
        setCreateModalOpen(false);
        setCreateDesc("");
        await fetchSnapshots();
      }
    } catch (err) {
      if (typeof pushToast === "function") {
        pushToast(`Gagal membuat snapshot: ${err.message}`, "error");
      }
    } finally {
      setCreating(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-black/85 backdrop-blur-md animate-in fade-in duration-200">
      <div className="bg-neutral-950 border border-white/10 rounded-2xl w-full max-w-5xl h-[88vh] flex flex-col p-5 shadow-2xl relative overflow-hidden">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-5 right-5 p-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-white transition"
          title="Tutup riwayat"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Modal Header */}
        <div className="flex items-center justify-between gap-3 pb-3 border-b border-white/10 shrink-0 pr-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
              <History className="w-5 h-5" />
            </div>

            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-text-primary tracking-wide">
                  Historical Topology & Change Detection
                </h2>
                <span className="px-2 py-0.5 rounded-full text-[11px] font-mono font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30">
                  {totalSnapshots} snapshot
                </span>
              </div>
              <p className="text-xs text-text-secondary">
                Titik waktu topologi tidak dapat diubah (immutable), perbandingan semantik diff, dan deteksi anomali.
              </p>
            </div>
          </div>

          <button
            onClick={() => setCreateModalOpen(true)}
            className="px-3 py-1.5 rounded-xl bg-sky-500/15 hover:bg-sky-500/25 border border-sky-500/30 text-sky-300 text-xs font-medium transition flex items-center gap-1.5 shadow-sm"
            title="Ambil snapshot titik waktu sekarang"
          >
            <Camera className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Ambil Snapshot</span>
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center gap-2 pt-3 pb-1 border-b border-white/[0.08] shrink-0 text-xs">
          <button
            onClick={() => setActiveTab("timeline")}
            className={`px-3.5 py-1.5 rounded-xl font-medium transition flex items-center gap-1.5 ${
              activeTab === "timeline"
                ? "bg-white/10 text-white border border-white/20 shadow-sm"
                : "text-neutral-400 hover:text-white hover:bg-white/5"
            }`}
          >
            <Calendar className="w-3.5 h-3.5 text-sky-400" />
            <span>Timeline Snapshot</span>
          </button>

          <button
            onClick={() => setActiveTab("compare")}
            className={`px-3.5 py-1.5 rounded-xl font-medium transition flex items-center gap-1.5 ${
              activeTab === "compare"
                ? "bg-white/10 text-white border border-white/20 shadow-sm"
                : "text-neutral-400 hover:text-white hover:bg-white/5"
            }`}
          >
            <GitCompare className="w-3.5 h-3.5 text-purple-400" />
            <span>Semantic Graph Diff</span>
          </button>

          <button
            onClick={() => setActiveTab("changes")}
            className={`px-3.5 py-1.5 rounded-xl font-medium transition flex items-center gap-1.5 ${
              activeTab === "changes"
                ? "bg-white/10 text-white border border-white/20 shadow-sm"
                : "text-neutral-400 hover:text-white hover:bg-white/5"
            }`}
          >
            <History className="w-3.5 h-3.5 text-cyan-400" />
            <span>Riwayat Perubahan (Audit Log)</span>
          </button>
        </div>

        {/* Tab Body Content */}
        <div className="flex-1 overflow-hidden pt-3">
          {activeTab === "timeline" && (
            <SnapshotTimeline
              snapshots={snapshots}
              loading={loading}
              onRefresh={fetchSnapshots}
              onSelectForCompare={handleSelectForCompare}
              onInspectSnapshot={(id) => {
                setCompareBaseId(id);
                setActiveTab("compare");
              }}
              onLoadOntoCanvas={onLoadOntoCanvas}
              pushToast={pushToast}
            />
          )}

          {activeTab === "compare" && (
            <SnapshotDiffViewer
              snapshots={snapshots}
              preselectedBaseId={compareBaseId}
              preselectedTargetId={compareTargetId}
              pushToast={pushToast}
            />
          )}

          {activeTab === "changes" && <TopologyChangeLog pushToast={pushToast} />}
        </div>
      </div>

      {/* Create Snapshot Dialog */}
      {createModalOpen && (
        <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-black/75">
          <div className="bg-neutral-900 border border-white/10 rounded-2xl w-full max-w-md p-5 shadow-2xl relative space-y-4">
            <button
              onClick={() => setCreateModalOpen(false)}
              className="absolute top-4 right-4 text-neutral-400 hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex items-center gap-2 text-white">
              <Camera className="w-4 h-4 text-sky-400" />
              <h3 className="text-sm font-bold">Ambil Snapshot Topologi Baru</h3>
            </div>

            <p className="text-xs text-text-secondary">
              Snapshot akan mengunci kondisi node, wiring fisik, status operasional, dan bukti penemuan terkini ke dalam
              titik waktu bertanda tangan SHA-256 yang permanen.
            </p>

            <form onSubmit={handleCreateSnapshot} className="space-y-3 text-xs">
              <div>
                <label className="text-neutral-400 block mb-1">Deskripsi / Label Snapshot</label>
                <input
                  type="text"
                  value={createDesc}
                  onChange={(e) => setCreateDesc(e.target.value)}
                  placeholder="Misal: Sebelum konfigurasi OSPF Area 0"
                  className="w-full bg-black border border-white/10 rounded-xl px-3 py-2 text-white outline-none focus:border-sky-500/50"
                  autoFocus
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setCreateModalOpen(false)}
                  className="px-3 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-neutral-300"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-4 py-1.5 rounded-xl bg-sky-500/20 hover:bg-sky-500/30 border border-sky-500/40 text-sky-300 font-semibold flex items-center gap-1.5"
                >
                  <Camera className={`w-3.5 h-3.5 ${creating ? "animate-spin" : ""}`} />
                  <span>{creating ? "Menyimpan..." : "Simpan Snapshot"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
