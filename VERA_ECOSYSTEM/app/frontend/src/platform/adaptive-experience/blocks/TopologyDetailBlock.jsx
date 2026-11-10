/**
 * src/platform/adaptive-experience/blocks/TopologyDetailBlock.jsx
 *
 * Detailed Node & Edge Inspection Panel for Network Topology.
 */

import React from "react";
import { Server, Link2, ShieldCheck, Cpu, HardDrive } from "lucide-react";

export default function TopologyDetailBlock({ block }) {
  const data = block?.data || {};
  const isNode = data.target_type !== "edge";
  const name = data.name || data.id || "Elemen Topologi";

  return (
    <div className="my-2 p-4 rounded-xl border border-white/10 bg-slate-900/80 backdrop-blur-md shadow-lg space-y-3 font-sans">
      <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-cyan-500/10 text-cyan-400">
            {isNode ? <Server size={18} /> : <Link2 size={18} />}
          </div>
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-white/90">
              {isNode ? "Rincian Simpul (Node Detail)" : "Rincian Tautan (Edge Detail)"}
            </h4>
            <p className="text-[11px] text-white/50">{name}</p>
          </div>
        </div>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-950/60 border border-cyan-500/30 text-cyan-300 font-bold">
          {data.relationship_class || data.device_type || "TOPOLOGY"}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs font-mono">
        {isNode ? (
          <>
            <div className="p-2 rounded bg-black/30 border border-white/5">
              <span className="text-white/40 block text-[10px]">Management IP</span>
              <span className="text-white/90 font-semibold">{data.management_ip || data.ip || "-"}</span>
            </div>
            <div className="p-2 rounded bg-black/30 border border-white/5">
              <span className="text-white/40 block text-[10px]">Vendor / Model</span>
              <span className="text-white/90">{data.vendor || "MikroTik"} / {data.model || "-"}</span>
            </div>
            <div className="p-2 rounded bg-black/30 border border-white/5">
              <span className="text-white/40 block text-[10px]">Status Operasional</span>
              <span className="text-emerald-400 font-semibold">{data.status || "ACTIVE"}</span>
            </div>
          </>
        ) : (
          <>
            <div className="p-2 rounded bg-black/30 border border-white/5">
              <span className="text-white/40 block text-[10px]">Sumber & Port</span>
              <span className="text-white/90 font-semibold">{data.source_node} : {data.source_port || "ether1"}</span>
            </div>
            <div className="p-2 rounded bg-black/30 border border-white/5">
              <span className="text-white/40 block text-[10px]">Tujuan & Port</span>
              <span className="text-white/90 font-semibold">{data.target_node} : {data.target_port || "ether1"}</span>
            </div>
            <div className="p-2 rounded bg-black/30 border border-white/5">
              <span className="text-white/40 block text-[10px]">Discovery Method</span>
              <span className="text-cyan-400 font-semibold">{data.discovery_method || "CDP/MNDP"}</span>
            </div>
          </>
        )}
      </div>

      {data.confidence_rationale && (
        <div className="p-2.5 rounded bg-black/40 border border-white/5 text-[11px] text-white/70">
          <span className="font-semibold text-white/50 block text-[10px] uppercase font-mono">Dasar Bukti (Rationale):</span>
          {data.confidence_rationale}
        </div>
      )}
    </div>
  );
}
