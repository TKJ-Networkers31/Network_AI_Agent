// src/components/topology/RouteChangeLog.jsx
// Chronological RouteChangeType audit log & Stability/Flapping analytics panel.

import { useEffect, useState } from "react";
import { Activity, RefreshCw } from "lucide-react";
import { getRouteHistoricalAnalytics, listRouteChanges } from "./routeHistoryApi.js";

export default function RouteChangeLog({ deviceFilter = "", pushToast }) {
  const [changes, setChanges] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [typeFilter, setTypeFilter] = useState("");
  const [loading, setLoading] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [chgRes, anaRes] = await Promise.all([
        listRouteChanges({
          device_id: deviceFilter || null,
          change_type: typeFilter || null,
          limit: 100,
        }),
        getRouteHistoricalAnalytics({
          device_id: deviceFilter || null,
          limit: 200,
        }),
      ]);
      if (chgRes.success) setChanges(chgRes.changes || []);
      if (anaRes.success) setAnalytics(anaRes.analytics || null);
    } catch (err) {
      if (typeof pushToast === "function") {
        pushToast(`Gagal memuat riwayat perubahan rute: ${err.message}`, "error");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [deviceFilter, typeFilter]);

  return (
    <div className="flex flex-col h-full gap-3 text-xs overflow-hidden">
      {analytics && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 shrink-0">
          <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
            <div className="text-[10px] text-emerald-300/80 uppercase">Stability Score</div>
            <div className="text-base font-bold font-mono text-emerald-300">
              {Math.round((analytics.route_stability_score ?? 1) * 100)}%
            </div>
          </div>
          <div className="p-2.5 rounded-xl bg-sky-500/10 border border-sky-500/20">
            <div className="text-[10px] text-sky-300/80 uppercase">Churn / Snapshot</div>
            <div className="text-base font-bold font-mono text-sky-300">
              {analytics.route_churn_per_snapshot ?? 0}
            </div>
          </div>
          <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20">
            <div className="text-[10px] text-amber-300/80 uppercase">Flapping Prefixes</div>
            <div className="text-base font-bold font-mono text-amber-300">
              {(analytics.flapping_prefixes || []).length}
            </div>
          </div>
          <div className="p-2.5 rounded-xl bg-purple-500/10 border border-purple-500/20">
            <div className="text-[10px] text-purple-300/80 uppercase">Temporal Correlations</div>
            <div className="text-base font-bold font-mono text-purple-300">
              {(analytics.correlated_topology_and_nms_events || []).length}
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-2 shrink-0">
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="px-3 py-1.5 rounded-xl bg-neutral-900 border border-white/10 text-white font-mono text-[11px]"
        >
          <option value="">Semua RouteChangeType</option>
          <option value="ROUTE_ADDED">ROUTE_ADDED</option>
          <option value="ROUTE_REMOVED">ROUTE_REMOVED</option>
          <option value="ROUTE_REAPPEARED">ROUTE_REAPPEARED</option>
          <option value="GATEWAY_CHANGED">GATEWAY_CHANGED</option>
          <option value="NEXT_HOP_CHANGED">NEXT_HOP_CHANGED</option>
          <option value="ECMP_CHANGED">ECMP_CHANGED</option>
          <option value="ROUTING_TABLE_CHANGED">ROUTING_TABLE_CHANGED</option>
          <option value="ROUTE_ACTIVATED">ROUTE_ACTIVATED</option>
          <option value="ROUTE_DEACTIVATED">ROUTE_DEACTIVATED</option>
          <option value="ROUTE_STATE_UNKNOWN">ROUTE_STATE_UNKNOWN (Suppressed)</option>
        </select>

        <button
          onClick={loadData}
          disabled={loading}
          className="px-2.5 py-1.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-neutral-200 flex items-center gap-1.5"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>Muat Ulang</span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {changes.map((c) => (
          <div
            key={c.change_id || `${c.to_snapshot_id}-${c.dst_prefix}`}
            className="p-3 rounded-xl bg-white/[0.03] border border-white/10 space-y-1"
          >
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-2 flex-wrap">
                <Activity className="w-3.5 h-3.5 text-cyan-400" />
                <span className="px-2 py-0.5 rounded font-mono text-[10px] font-semibold bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                  {c.change_type}
                </span>
                <span className="font-mono text-sky-300 font-semibold">{c.device_id}</span>
                <span className="font-mono text-white">{c.dst_prefix}</span>
                <span className="font-mono text-[11px] text-purple-300">[{c.routing_table}]</span>
              </div>
              <span className="text-[11px] text-neutral-500">
                {new Date((c.detected_at || 0) * 1000).toLocaleString()}
              </span>
            </div>
            <p className="text-neutral-300">{c.summary}</p>
          </div>
        ))}

        {!loading && changes.length === 0 && (
          <div className="p-6 text-center text-neutral-500 border border-dashed border-white/10 rounded-xl">
            Belum ada perubahan rute yang tercatat untuk filter ini.
          </div>
        )}
      </div>
    </div>
  );
}
