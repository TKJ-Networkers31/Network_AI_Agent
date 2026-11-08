// src/components/topology/RouteSnapshotTimeline.jsx
// Chronological list of immutable per-device route snapshots with SHA-256 verification.

import { Eye, GitCompare, RefreshCw, ShieldCheck } from "lucide-react";
import RouteSnapshotIntegrityBadge from "./RouteSnapshotIntegrityBadge.jsx";
import { verifyRouteSnapshot } from "./routeHistoryApi.js";

export default function RouteSnapshotTimeline({
  snapshots = [],
  loading = false,
  onRefresh,
  onSelectForCompare,
  onInspectSnapshot,
  pushToast,
}) {
  const handleVerify = async (snapId) => {
    try {
      const res = await verifyRouteSnapshot(snapId);
      if (typeof pushToast === "function") {
        pushToast(
          res.verified
            ? `Snapshot ${snapId} terverifikasi SHA-256 (${res.completeness}).`
            : `PERINGATAN: Integritas SHA-256 gagal untuk ${snapId}!`,
          res.verified ? "success" : "error"
        );
      }
      if (typeof onRefresh === "function") onRefresh();
    } catch (err) {
      if (typeof pushToast === "function") {
        pushToast(`Gagal memverifikasi snapshot: ${err.message}`, "error");
      }
    }
  };

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="flex items-center justify-between text-xs">
        <span className="text-neutral-400">
          Menampilkan <strong>{snapshots.length}</strong> snapshot rute immutable terbaru
        </span>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="px-2.5 py-1 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-neutral-200 flex items-center gap-1.5 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>Segarkan</span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {snapshots.map((snap) => (
          <div
            key={snap.snapshot_id}
            className="p-3 rounded-xl bg-white/[0.03] hover:bg-white/[0.05] border border-white/10 flex items-center justify-between gap-3 flex-wrap transition"
          >
            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-xs font-semibold text-sky-300">
                  {snap.device_identity || snap.device_id}
                </span>
                <span className="text-[11px] font-mono text-neutral-500">
                  {snap.snapshot_id}
                </span>
                <RouteSnapshotIntegrityBadge
                  integrityStatus={snap.integrity_status}
                  completeness={snap.completeness}
                />
              </div>
              <div className="text-[11px] text-neutral-400 flex items-center gap-3 flex-wrap">
                <span>
                  Waktu: {new Date((snap.collected_at || 0) * 1000).toLocaleString()}
                </span>
                <span>
                  Rute: <strong>{snap.active_route_count}</strong> aktif / {snap.route_count} total
                </span>
                <span>
                  VRF: {(snap.routing_tables || ["main"]).join(", ")}
                </span>
                {snap.ros_version && <span>ROS: {snap.ros_version}</span>}
              </div>
            </div>

            <div className="flex items-center gap-1.5">
              <button
                onClick={() => onInspectSnapshot && onInspectSnapshot(snap.snapshot_id)}
                className="px-2.5 py-1 rounded-lg bg-sky-500/15 hover:bg-sky-500/25 border border-sky-500/30 text-sky-300 text-[11px] flex items-center gap-1"
                title="Inspeksi tabel rute historis (terisolasi dari live polling)"
              >
                <Eye className="w-3 h-3" />
                <span>Inspeksi</span>
              </button>
              <button
                onClick={() => onSelectForCompare && onSelectForCompare(snap.snapshot_id)}
                className="px-2.5 py-1 rounded-lg bg-purple-500/15 hover:bg-purple-500/25 border border-purple-500/30 text-purple-300 text-[11px] flex items-center gap-1"
                title="Pilih untuk perbandingan diff rute"
              >
                <GitCompare className="w-3 h-3" />
                <span>Compare</span>
              </button>
              <button
                onClick={() => handleVerify(snap.snapshot_id)}
                className="px-2 py-1 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-neutral-300 text-[11px] flex items-center gap-1"
                title="Verifikasi ulang hash SHA-256"
              >
                <ShieldCheck className="w-3 h-3 text-emerald-400" />
              </button>
            </div>
          </div>
        ))}

        {!loading && snapshots.length === 0 && (
          <div className="p-8 text-center text-xs text-neutral-500 border border-dashed border-white/10 rounded-xl">
            Belum ada snapshot rute historis yang tersimpan. Klik <strong>Ambil Route Snapshot</strong> untuk merekam baseline.
          </div>
        )}
      </div>
    </div>
  );
}
