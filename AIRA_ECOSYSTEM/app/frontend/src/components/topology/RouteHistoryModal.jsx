// src/components/topology/RouteHistoryModal.jsx
// Integrated Historical Route Analytics Modal (WP 4.6.4).
// Strictly isolates historical route snapshot inspection from live background polling.

import { useEffect, useState } from "react";
import { Calendar, Camera, GitCompare, History, Table2, X } from "lucide-react";
import RouteSnapshotTimeline from "./RouteSnapshotTimeline.jsx";
import RouteSnapshotDiffViewer from "./RouteSnapshotDiffViewer.jsx";
import RouteChangeLog from "./RouteChangeLog.jsx";
import HistoricalRouteTable from "./HistoricalRouteTable.jsx";
import {
  createRouteSnapshots,
  getRouteSnapshot,
  listRouteSnapshots,
} from "./routeHistoryApi.js";

export default function RouteHistoryModal({
  open,
  onClose,
  initialDeviceId = "",
  pushToast,
}) {
  const [activeTab, setActiveTab] = useState("timeline"); // timeline | compare | changes | table
  const [snapshots, setSnapshots] = useState([]);
  const [totalSnapshots, setTotalSnapshots] = useState(0);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);

  const [compareBaseId, setCompareBaseId] = useState("");
  const [compareTargetId, setCompareTargetId] = useState("");
  const [inspectedSnapshot, setInspectedSnapshot] = useState(null);

  const fetchSnapshots = async () => {
    setLoading(true);
    try {
      const res = await listRouteSnapshots({
        device_id: initialDeviceId || null,
        limit: 100,
      });
      if (res.success) {
        setSnapshots(res.snapshots || []);
        setTotalSnapshots(res.total || 0);
      }
    } catch (err) {
      if (typeof pushToast === "function") {
        pushToast(`Gagal memuat daftar route snapshot: ${err.message}`, "error");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      fetchSnapshots();
    }
  }, [open, initialDeviceId]);

  const handleInspectSnapshot = async (snapshotId) => {
    try {
      const res = await getRouteSnapshot(snapshotId, { include_routes: true });
      if (res.success && res.snapshot) {
        setInspectedSnapshot(res.snapshot);
        setActiveTab("table");
      }
    } catch (err) {
      if (typeof pushToast === "function") {
        pushToast(`Gagal membuka snapshot ${snapshotId}: ${err.message}`, "error");
      }
    }
  };

  const handleSelectForCompare = (snapshotId) => {
    if (!compareBaseId) {
      setCompareBaseId(snapshotId);
      if (typeof pushToast === "function") {
        pushToast(`Base snapshot rute dipilih (${snapshotId}). Pilih satu lagi untuk Target.`, "info");
      }
    } else {
      setCompareTargetId(snapshotId);
      setActiveTab("compare");
    }
  };

  const handleCaptureRouteSnapshots = async () => {
    setCreating(true);
    try {
      const res = await createRouteSnapshots({
        device_ids: initialDeviceId ? [initialDeviceId] : null,
        description: "Manual route snapshot from AIRA UI",
        trigger_type: "manual",
        collect_if_missing: true,
      });
      if (res.success) {
        if (typeof pushToast === "function") {
          pushToast(res.message || "Route snapshot berhasil direkam.", "success");
        }
        await fetchSnapshots();
      }
    } catch (err) {
      if (typeof pushToast === "function") {
        pushToast(`Gagal merekam route snapshot: ${err.message}`, "error");
      }
    } finally {
      setCreating(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-black/85 backdrop-blur-md">
      <div className="bg-neutral-950 border border-white/10 rounded-2xl w-full max-w-5xl h-[88vh] flex flex-col p-5 shadow-2xl relative overflow-hidden">
        <button
          onClick={onClose}
          className="absolute top-5 right-5 p-1.5 rounded-xl bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-white transition"
          title="Tutup riwayat rute"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Header */}
        <div className="flex items-center justify-between gap-3 pb-3 border-b border-white/10 shrink-0 pr-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
              <History className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white tracking-wide">
                  Historical Route Analytics & Immutable RIB Snapshots
                </h2>
                <span className="px-2 py-0.5 rounded-full text-[11px] font-mono font-semibold bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                  {totalSnapshots} snapshots
                </span>
              </div>
              <p className="text-xs text-neutral-400">
                Verifikasi SHA-256 independen dari kelengkapan koleksi, proteksi false-positive penghapusan, dan analisis flapping.
              </p>
            </div>
          </div>

          <button
            onClick={handleCaptureRouteSnapshots}
            disabled={creating}
            className="px-3 py-1.5 rounded-xl bg-sky-500/15 hover:bg-sky-500/25 border border-sky-500/30 text-sky-300 text-xs font-medium transition flex items-center gap-1.5"
          >
            <Camera className="w-3.5 h-3.5" />
            <span>{creating ? "Menyimpan..." : "Ambil Route Snapshot"}</span>
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center gap-2 pt-3 pb-1 border-b border-white/[0.08] shrink-0 text-xs overflow-x-auto">
          <button
            onClick={() => setActiveTab("timeline")}
            className={`px-3.5 py-1.5 rounded-xl font-medium transition flex items-center gap-1.5 ${
              activeTab === "timeline"
                ? "bg-white/10 text-white border border-white/20"
                : "text-neutral-400 hover:text-white hover:bg-white/5"
            }`}
          >
            <Calendar className="w-3.5 h-3.5 text-sky-400" />
            <span>Timeline</span>
          </button>
          <button
            onClick={() => setActiveTab("compare")}
            className={`px-3.5 py-1.5 rounded-xl font-medium transition flex items-center gap-1.5 ${
              activeTab === "compare"
                ? "bg-white/10 text-white border border-white/20"
                : "text-neutral-400 hover:text-white hover:bg-white/5"
            }`}
          >
            <GitCompare className="w-3.5 h-3.5 text-purple-400" />
            <span>Diff Snapshot</span>
          </button>
          <button
            onClick={() => setActiveTab("changes")}
            className={`px-3.5 py-1.5 rounded-xl font-medium transition flex items-center gap-1.5 ${
              activeTab === "changes"
                ? "bg-white/10 text-white border border-white/20"
                : "text-neutral-400 hover:text-white hover:bg-white/5"
            }`}
          >
            <History className="w-3.5 h-3.5 text-cyan-400" />
            <span>Audit & Stabilitas</span>
          </button>
          <button
            onClick={() => setActiveTab("table")}
            className={`px-3.5 py-1.5 rounded-xl font-medium transition flex items-center gap-1.5 ${
              activeTab === "table"
                ? "bg-white/10 text-white border border-white/20"
                : "text-neutral-400 hover:text-white hover:bg-white/5"
            }`}
          >
            <Table2 className="w-3.5 h-3.5 text-amber-400" />
            <span>Tabel Historis (Isolated)</span>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-hidden pt-3">
          {activeTab === "timeline" && (
            <RouteSnapshotTimeline
              snapshots={snapshots}
              loading={loading}
              onRefresh={fetchSnapshots}
              onSelectForCompare={handleSelectForCompare}
              onInspectSnapshot={handleInspectSnapshot}
              pushToast={pushToast}
            />
          )}
          {activeTab === "compare" && (
            <RouteSnapshotDiffViewer
              snapshots={snapshots}
              initialBaseId={compareBaseId}
              initialTargetId={compareTargetId}
              pushToast={pushToast}
            />
          )}
          {activeTab === "changes" && (
            <RouteChangeLog deviceFilter={initialDeviceId} pushToast={pushToast} />
          )}
          {activeTab === "table" && (
            <HistoricalRouteTable
              snapshot={inspectedSnapshot}
              onExitHistorical={() => {
                setInspectedSnapshot(null);
                setActiveTab("timeline");
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
