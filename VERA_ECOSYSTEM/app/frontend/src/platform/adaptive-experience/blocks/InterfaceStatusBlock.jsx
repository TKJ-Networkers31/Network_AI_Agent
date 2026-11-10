/**
 * src/platform/adaptive-experience/blocks/InterfaceStatusBlock.jsx
 *
 * Tabular dashboard of network interface operational states.
 */

import React from "react";
import { Activity, Network, ArrowUpRight, ArrowDownLeft } from "lucide-react";

export default function InterfaceStatusBlock({ block }) {
  const data = block?.data || {};
  const device = data.device || "Router";
  const interfaces = data.interfaces || [];
  const totalCount = data.total_count ?? interfaces.length;
  const upCount = data.up_count ?? interfaces.filter((i) => i.status === "UP").length;

  return (
    <div className="my-2 p-4 rounded-xl border border-white/10 bg-slate-900/80 backdrop-blur-md shadow-lg space-y-3 font-sans">
      <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400">
            <Network size={18} />
          </div>
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-white/90">
              Daftar Antarmuka Jaringan
            </h4>
            <p className="text-[11px] text-white/50">{device}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950/60 border border-emerald-500/30 text-emerald-300">
            {upCount} / {totalCount} LINK AKTIF
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-white/10 text-white/40 text-[10px] uppercase font-mono">
              <th className="py-1.5 px-2">Status</th>
              <th className="py-1.5 px-2">Antarmuka</th>
              <th className="py-1.5 px-2">Tipe</th>
              <th className="py-1.5 px-2">Keadaan</th>
              <th className="py-1.5 px-2 text-right">Rincian</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 font-mono">
            {interfaces.map((iface, idx) => {
              const isUp = iface.status === "UP" || iface.running;
              return (
                <tr key={idx} className="hover:bg-white/5 transition-colors">
                  <td className="py-2 px-2">
                    <span
                      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        isUp
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                          : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                      }`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${isUp ? "bg-emerald-400 animate-pulse" : "bg-rose-400"}`} />
                      {isUp ? "UP" : "DOWN"}
                    </span>
                  </td>
                  <td className="py-2 px-2 font-semibold text-white/90">{iface.name}</td>
                  <td className="py-2 px-2 text-white/60 capitalize">{iface.type || "ether"}</td>
                  <td className="py-2 px-2 text-white/50 text-[11px]">
                    {iface.running ? "RUNNING" : "DISABLED/IDLE"}
                  </td>
                  <td className="py-2 px-2 text-right text-[10px] text-white/40">
                    {iface.mtu ? `MTU: ${iface.mtu}` : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
