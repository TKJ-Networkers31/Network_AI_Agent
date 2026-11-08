// src/components/topology/RouteSnapshotDiffViewer.jsx
// Semantic Route Snapshot Diff Viewer with False-Positive Removal Suppression Notice.

import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, GitCompare, ShieldAlert } from "lucide-react";
import { compareRouteSnapshots } from "./routeHistoryApi.js";

export default function RouteSnapshotDiffViewer({
  snapshots = [],
  initialBaseId = "",
  initialTargetId = "",
  pushToast,
}) {
  const [baseId, setBaseId] = useState(initialBaseId);
  const [targetId, setTargetId] = useState(initialTargetId);
  const [diff, setDiff] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (initialBaseId) setBaseId(initialBaseId);
    if (initialTargetId) setTargetId(initialTargetId);
  }, [initialBaseId, initialTargetId]);

  const runCompare = async () => {
    if (!baseId || !targetId) return;
    setLoading(true);
    try {
      const res = await compareRouteSnapshots(baseId, targetId);
      if (res.success) {
        setDiff(res.diff);
      }
    } catch (err) {
      if (typeof pushToast === "function") {
        pushToast(`Gagal membandingkan route snapshot: ${err.message}`, "error");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (baseId && targetId && baseId !== targetId) {
      runCompare();
    }
  }, [baseId, targetId]);

  return (
    <div className="flex flex-col h-full gap-3 text-xs">
      <div className="p-3 rounded-xl bg-white/[0.03] border border-white/10 flex items-center gap-2 flex-wrap">
        <select
          value={baseId}
          onChange={(e) => setBaseId(e.target.value)}
          className="flex-1 min-w-[200px] px-3 py-1.5 rounded-xl bg-neutral-900 border border-white/10 text-white font-mono text-[11px]"
        >
          <option value="">-- Pilih Base Snapshot (Sebelumnya) --</option>
          {snapshots.map((s) => (
            <option key={s.snapshot_id} value={s.snapshot_id}>
              [{s.device_identity || s.device_id}] {s.snapshot_id} ({s.completeness})
            </option>
          ))}
        </select>
        <ArrowRight className="w-4 h-4 text-neutral-500 shrink-0" />
        <select
          value={targetId}
          onChange={(e) => setTargetId(e.target.value)}
          className="flex-1 min-w-[200px] px-3 py-1.5 rounded-xl bg-neutral-900 border border-white/10 text-white font-mono text-[11px]"
        >
          <option value="">-- Pilih Target Snapshot (Sesudahnya) --</option>
          {snapshots.map((s) => (
            <option key={s.snapshot_id} value={s.snapshot_id}>
              [{s.device_identity || s.device_id}] {s.snapshot_id} ({s.completeness})
            </option>
          ))}
        </select>
        <button
          onClick={runCompare}
          disabled={!baseId || !targetId || loading}
          className="px-3.5 py-1.5 rounded-xl bg-purple-500/20 hover:bg-purple-500/30 disabled:opacity-40 border border-purple-500/40 text-purple-200 font-semibold flex items-center gap-1.5 transition"
        >
          <GitCompare className="w-3.5 h-3.5" />
          <span>{loading ? "Membandingkan..." : "Compare"}</span>
        </button>
      </div>

      {diff?.cross_device_warning && (
        <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-200 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
          <span>{diff.cross_device_warning}</span>
        </div>
      )}

      {diff?.removal_suppression_active && (
        <div className="p-2.5 rounded-xl bg-sky-500/10 border border-sky-500/30 text-sky-200 flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-sky-400 shrink-0" />
          <span>
            <strong>False-Positive Removal Protection Active ({diff.suppression_reason}):</strong>{" "}
            Rute yang tidak terlihat pada snapshot tidak lengkap diklasifikasikan sebagai{" "}
            <code className="font-mono">ROUTE_STATE_UNKNOWN</code>, bukan penghapusan terkonfirmasi.
          </span>
        </div>
      )}

      {diff && (
        <div className="flex-1 overflow-y-auto space-y-2 pr-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-neutral-300">
              Tidak berubah: <strong>{diff.unchanged_count}</strong>
            </span>
            {Object.entries(diff.summary_counts || {}).map(([ctype, cnt]) => (
              <span
                key={ctype}
                className="px-2.5 py-1 rounded-lg bg-purple-500/15 border border-purple-500/30 text-purple-200 font-mono text-[11px]"
              >
                {ctype}: <strong>{cnt}</strong>
              </span>
            ))}
          </div>

          {(diff.changes || []).map((chg, idx) => (
            <div
              key={`${chg.dst_prefix}-${chg.change_type}-${idx}`}
              className="p-3 rounded-xl bg-white/[0.03] border border-white/10 flex items-start justify-between gap-3"
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="px-2 py-0.5 rounded font-mono text-[10px] font-bold bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                    {chg.change_type}
                  </span>
                  <span className="font-mono font-semibold text-white">{chg.dst_prefix}</span>
                  <span className="text-[11px] font-mono text-purple-300">
                    table={chg.routing_table}
                  </span>
                </div>
                <p className="text-neutral-300">{chg.summary}</p>
              </div>
              <span className="font-mono text-[11px] text-neutral-400 shrink-0">
                Conf: {Math.round((chg.confidence || 0) * 100)}%
              </span>
            </div>
          ))}

          {(diff.changes || []).length === 0 && (
            <div className="p-6 text-center text-neutral-400 border border-white/10 rounded-xl">
              Tidak ada perubahan semantik antara kedua snapshot rute ini.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
