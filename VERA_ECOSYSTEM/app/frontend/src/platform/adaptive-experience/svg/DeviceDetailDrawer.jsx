/**
 * src/platform/adaptive-experience/svg/DeviceDetailDrawer.jsx
 *
 * Contextual Detail Drawer displayed when an interactive SVG node is selected.
 * Presents device identity, management IP, vendor, status, telemetry, and actions.
 */

import React from "react";
import { X, Server, Router, Shield, Activity, Terminal, ExternalLink, RefreshCw } from "lucide-react";

export default function DeviceDetailDrawer({ node, onClose, onAction }) {
  if (!node) return null;

  const isVrrp = node.kind === "vrrp_virtual";
  const isCluster = Boolean(node.isCluster);
  const metadata = node.metadata || {};

  const handlePing = () => {
    if (onAction && node.ip) {
      onAction("tool", { tool: "network_ping", args: { target: node.ip, count: 4 } });
    }
  };

  const handleTerminal = () => {
    window.dispatchEvent(new CustomEvent("vera:navigate", { detail: "akane" }));
  };

  const handleOpenWebFig = () => {
    if (node.ip) {
      window.open(`http://${node.ip}`, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-sm bg-slate-900/95 backdrop-blur-xl border-l border-white/10 shadow-2xl p-5 flex flex-col font-sans animate-in slide-in-from-right duration-200">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400">
            {isVrrp ? <Shield size={20} /> : <Router size={20} />}
          </div>
          <div>
            <h3 className="text-sm font-bold text-white tracking-wide">{node.title}</h3>
            <span className="text-[11px] font-mono text-white/50">{node.subtitle || node.ip || "Node Details"}</span>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1 rounded-lg hover:bg-white/10 text-white/40 hover:text-white transition"
          aria-label="Tutup panel detail"
        >
          <X size={18} />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto py-4 space-y-4 text-xs">
        {/* Status & Identity Card */}
        <div className="p-3.5 rounded-xl border border-white/5 bg-black/40 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-white/40 uppercase tracking-wider text-[10px]">Status Operasional</span>
            <span
              className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase font-mono ${
                node.status === "online" || node.status === "master" || node.status === "up"
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                  : node.status === "backup"
                  ? "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20"
                  : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
              }`}
            >
              {node.status}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-white/80 pt-1 font-mono">
            <div>
              <span className="text-white/40 block text-[10px]">Vendor</span>
              <span>{node.vendor || "MikroTik"}</span>
            </div>
            <div>
              <span className="text-white/40 block text-[10px]">Model</span>
              <span>{node.model || "RouterOS"}</span>
            </div>
            <div>
              <span className="text-white/40 block text-[10px]">Management IP</span>
              <span className="text-cyan-400">{node.ip || "-"}</span>
            </div>
            <div>
              <span className="text-white/40 block text-[10px]">Kind</span>
              <span className="capitalize">{node.kind}</span>
            </div>
          </div>
        </div>

        {/* VRRP Specific Metadata */}
        {isVrrp && (
          <div className="p-3.5 rounded-xl border border-cyan-500/20 bg-cyan-950/20 space-y-2">
            <h4 className="text-[11px] font-semibold text-cyan-300 uppercase tracking-wider">
              Parameter Virtual Router
            </h4>
            <div className="grid grid-cols-2 gap-2 font-mono text-white/80 text-[11px]">
              <div>
                <span className="text-white/40 block text-[10px]">VRID</span>
                <span>{metadata.vrid || 10}</span>
              </div>
              <div>
                <span className="text-white/40 block text-[10px]">Virtual IP</span>
                <span className="text-cyan-300">{metadata.virtual_ip || node.ip}</span>
              </div>
              <div className="col-span-2">
                <span className="text-white/40 block text-[10px]">Pemilik Master Saat Ini</span>
                <span className="text-emerald-400 font-bold">{metadata.active_owner || "R1-Master"}</span>
              </div>
            </div>
          </div>
        )}

        {/* Cluster Information */}
        {isCluster && (
          <div className="p-3.5 rounded-xl border border-purple-500/20 bg-purple-950/20 space-y-2">
            <h4 className="text-[11px] font-semibold text-purple-300 uppercase tracking-wider">
              Anggota Cluster ({node.memberCount} Perangkat)
            </h4>
            <div className="space-y-1 font-mono text-[11px] text-white/70">
              {node.members && node.members.length > 0 ? (
                node.members.map((m, idx) => (
                  <div key={idx} className="flex items-center justify-between py-0.5 border-b border-white/5">
                    <span>{m.name || m}</span>
                    <span className="text-emerald-400">ONLINE</span>
                  </div>
                ))
              ) : (
                <p className="text-white/40 italic">Unit terkelola dalam kelompok redundansi.</p>
              )}
            </div>
          </div>
        )}

        {/* Badges */}
        {node.badges && node.badges.length > 0 && (
          <div className="space-y-1.5">
            <span className="text-white/40 uppercase tracking-wider text-[10px] block">Label & Karakteristik</span>
            <div className="flex flex-wrap gap-1.5">
              {node.badges.map((b, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 rounded-md bg-white/5 border border-white/10 text-white/70 text-[10px] font-mono font-medium"
                >
                  {b}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Operational Actions */}
      <div className="border-t border-white/10 pt-4 space-y-2">
        <h4 className="text-[10px] font-semibold uppercase tracking-wider text-white/40">Aksi Operasional Cepat</h4>
        <div className="grid grid-cols-2 gap-2">
          {node.ip && (
            <button
              type="button"
              onClick={handlePing}
              className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-cyan-600/20 hover:bg-cyan-600/30 border border-cyan-500/30 text-cyan-300 font-semibold text-xs transition"
            >
              <Activity size={13} />
              <span>Ping Probe</span>
            </button>
          )}
          <button
            type="button"
            onClick={handleTerminal}
            className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-white/80 font-medium text-xs transition"
          >
            <Terminal size={13} />
            <span>Terminal</span>
          </button>
          {node.ip && !isVrrp && (
            <button
              type="button"
              onClick={handleOpenWebFig}
              className="col-span-2 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 border border-white/10 text-white/80 font-medium text-xs transition"
            >
              <ExternalLink size={13} />
              <span>Buka WebFig ({node.ip})</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
