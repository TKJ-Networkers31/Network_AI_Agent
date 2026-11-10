/**
 * src/platform/adaptive-experience/blocks/RouteTableViewBlock.jsx
 *
 * Structured Routing Table View with flags, gateway, and status pills.
 */

import React from "react";
import { Signpost, Compass } from "lucide-react";

export default function RouteTableViewBlock({ block }) {
  const data = block?.data || {};
  const device = data.device || "Router";
  const routes = data.routes || [];

  return (
    <div className="my-2 p-4 rounded-xl border border-white/10 bg-slate-900/80 backdrop-blur-md shadow-lg space-y-3 font-sans">
      <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-cyan-500/10 text-cyan-400">
            <Signpost size={18} />
          </div>
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-white/90">
              Tabel Routing (RIB / FIB)
            </h4>
            <p className="text-[11px] text-white/50">{device}</p>
          </div>
        </div>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-950/60 border border-cyan-500/30 text-cyan-300">
          {routes.length} RUTE TERDAFTAR
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-white/10 text-white/40 text-[10px] uppercase font-mono">
              <th className="py-1.5 px-2">Flags</th>
              <th className="py-1.5 px-2">Dst. Address</th>
              <th className="py-1.5 px-2">Gateway</th>
              <th className="py-1.5 px-2 text-right">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 font-mono">
            {routes.map((rt, idx) => {
              const isActive = rt.status === "ACTIVE" || (rt.flags && rt.flags.includes("A"));
              return (
                <tr key={idx} className="hover:bg-white/5 transition-colors">
                  <td className="py-2 px-2 text-cyan-400 font-bold text-[11px]">
                    {rt.flags || "A S"}
                  </td>
                  <td className="py-2 px-2 font-semibold text-white/90">
                    {rt.dst_address || "0.0.0.0/0"}
                  </td>
                  <td className="py-2 px-2 text-white/70">
                    {rt.gateway || "connected"}
                  </td>
                  <td className="py-2 px-2 text-right">
                    <span
                      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        isActive
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                          : "bg-white/5 text-white/40 border border-white/10"
                      }`}
                    >
                      {isActive ? "ACTIVE" : "INACTIVE"}
                    </span>
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
