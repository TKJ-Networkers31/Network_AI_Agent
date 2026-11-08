// src/components/topology/HistoricalRouteTable.jsx
// Read-only bounded route table inspector for immutable historical route snapshots.

import { useMemo, useState } from "react";
import { Filter, Lock, Search } from "lucide-react";
import RouteSnapshotIntegrityBadge from "./RouteSnapshotIntegrityBadge.jsx";

export default function HistoricalRouteTable({ snapshot, onExitHistorical }) {
  const [search, setSearch] = useState("");
  const [tableFilter, setTableFilter] = useState("ALL");
  const [activeOnly, setActiveOnly] = useState(false);

  const routes = useMemo(() => (Array.isArray(snapshot?.routes) ? snapshot.routes : []), [snapshot]);
  const tables = useMemo(() => {
    const set = new Set(routes.map((r) => r.routing_table || "main"));
    return ["ALL", ...Array.from(set).sort()];
  }, [routes]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return routes.filter((r) => {
      if (tableFilter !== "ALL" && (r.routing_table || "main") !== tableFilter) return false;
      if (activeOnly && (!r.active || r.disabled)) return false;
      if (!q) return true;
      return (
        String(r.dst_prefix || "").toLowerCase().includes(q) ||
        String(r.gateway || "").toLowerCase().includes(q) ||
        String(r.interface_name || "").toLowerCase().includes(q) ||
        String(r.protocol || "").toLowerCase().includes(q)
      );
    });
  }, [routes, search, tableFilter, activeOnly]);

  if (!snapshot) {
    return (
      <div className="p-6 text-center text-xs text-neutral-400">
        Pilih salah satu snapshot dari Timeline untuk memeriksa tabel rute historis.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Isolation Banner */}
      <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-xs text-amber-200">
          <Lock className="w-4 h-4 text-amber-400 shrink-0" />
          <span>
            <strong>Historical View Isolated:</strong> Menampilkan snapshot immutable{" "}
            <code className="font-mono text-amber-300">{snapshot.snapshot_id}</code> (
            {snapshot.device_identity || snapshot.device_id}) — tidak akan ditimpa oleh live polling.
          </span>
        </div>
        <div className="flex items-center gap-2">
          <RouteSnapshotIntegrityBadge
            integrityStatus={snapshot.integrity_status}
            completeness={snapshot.completeness}
          />
          {typeof onExitHistorical === "function" && (
            <button
              onClick={onExitHistorical}
              className="px-2.5 py-1 rounded-lg bg-white/10 hover:bg-white/15 text-[11px] text-white transition"
            >
              Kembali ke Live
            </button>
          )}
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex items-center gap-2 flex-wrap text-xs">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="w-3.5 h-3.5 text-neutral-400 absolute left-3 top-2.5" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter prefix, gateway, interface, protokol..."
            className="w-full pl-8 pr-3 py-1.5 rounded-xl bg-white/5 border border-white/10 text-white placeholder:text-neutral-500 focus:outline-none focus:border-sky-500/50"
          />
        </div>
        <div className="flex items-center gap-1.5">
          <Filter className="w-3.5 h-3.5 text-neutral-400" />
          <select
            value={tableFilter}
            onChange={(e) => setTableFilter(e.target.value)}
            className="px-2.5 py-1.5 rounded-xl bg-neutral-900 border border-white/10 text-white"
          >
            {tables.map((t) => (
              <option key={t} value={t}>
                {t === "ALL" ? "Semua VRF/Table" : `Table: ${t}`}
              </option>
            ))}
          </select>
        </div>
        <label className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-white/5 border border-white/10 text-neutral-300 cursor-pointer">
          <input
            type="checkbox"
            checked={activeOnly}
            onChange={(e) => setActiveOnly(e.target.checked)}
          />
          <span>Active saja</span>
        </label>
      </div>

      {/* Bounded Table */}
      <div className="flex-1 overflow-auto rounded-xl border border-white/10 bg-black/30">
        <table className="w-full text-left text-xs border-collapse">
          <thead className="bg-white/5 text-neutral-400 sticky top-0">
            <tr>
              <th className="p-2.5 font-semibold">VRF / Table</th>
              <th className="p-2.5 font-semibold">Destination Prefix</th>
              <th className="p-2.5 font-semibold">Gateway / ECMP</th>
              <th className="p-2.5 font-semibold">Interface</th>
              <th className="p-2.5 font-semibold">Protocol</th>
              <th className="p-2.5 font-semibold">Dist</th>
              <th className="p-2.5 font-semibold">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 font-mono text-[11px]">
            {filtered.slice(0, 300).map((r, idx) => (
              <tr key={`${r.routing_table}-${r.dst_prefix}-${r.gateway}-${idx}`} className="hover:bg-white/[0.03]">
                <td className="p-2.5 text-purple-300">{r.routing_table || "main"}</td>
                <td className="p-2.5 text-sky-300 font-semibold">{r.dst_prefix}</td>
                <td className="p-2.5 text-neutral-200">
                  {Array.isArray(r.gateways) && r.gateways.length > 1
                    ? r.gateways.join(", ")
                    : r.gateway || "-"}
                </td>
                <td className="p-2.5 text-neutral-300">{r.interface_name || "-"}</td>
                <td className="p-2.5 text-cyan-300 uppercase">{r.protocol}</td>
                <td className="p-2.5 text-neutral-300">{r.distance}</td>
                <td className="p-2.5">
                  {r.disabled ? (
                    <span className="px-1.5 py-0.5 rounded bg-neutral-700/40 text-neutral-400">Disabled</span>
                  ) : r.unreachable ? (
                    <span className="px-1.5 py-0.5 rounded bg-red-500/20 text-red-300">Unreachable</span>
                  ) : r.active ? (
                    <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300">Active</span>
                  ) : (
                    <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300">Backup RIB</span>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="p-6 text-center text-neutral-500 font-sans">
                  Tidak ada entri rute yang cocok dengan filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
