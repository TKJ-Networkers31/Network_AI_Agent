import React from "react";
import DeviceAssetRenderer from "./DeviceAssetRenderer.jsx";
import DeviceStatusIndicator, { getDeviceStatusStyle } from "./DeviceStatusIndicator.jsx";
import { resolveDeviceAsset } from "./deviceAssetRegistry.js";
import {
  X,
  Terminal,
  Activity,
  Sliders,
  Shield,
  ShieldAlert,
  Server,
  Cpu,
  HardDrive,
  Network,
  Clock,
  ExternalLink,
} from "lucide-react";

/**
 * Enterprise Topology Device Inspector Panel
 * Provides detailed hardware, OS, and telemetry inspection for selected network nodes.
 */
export default function DeviceInspectorPanel({
  device = null,
  onClose = () => {},
  onOpenTerminal = null,
  onTroubleshoot = null,
  onEdit = null,
  className = "",
}) {
  if (!device) return null;

  const asset = resolveDeviceAsset(device);
  const status = device.status || device.oper_status || "unknown";
  const statusStyle = getDeviceStatusStyle(status);

  const displayName = device.label || device.name || device.id || "Unnamed Device";
  const ipAddress = device.ip || device.management_ip || device.host || "-";
  const macAddress = device.mac || device.mac_address || "-";
  const vendor = device.vendor || (asset.tags.includes("mikrotik") ? "MikroTik" : "Generic");
  const model = device.model || asset.label;
  const osVersion = device.os_version || device.firmware || device.version || "-";
  const isManaged = device.is_managed !== false && device.managed !== false && asset.key !== "unmanaged-device";

  return (
    <div
      className={`w-80 sm:w-96 bg-slate-950/95 border-l border-slate-800 text-slate-200 flex flex-col h-full shadow-2xl backdrop-blur-xl select-none z-30 transition-all ${className}`}
      role="region"
      aria-label={`Device Details: ${displayName}`}
    >
      {/* Top Header */}
      <div className="p-4 border-b border-slate-800/80 flex items-start justify-between gap-3 bg-slate-900/40">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-2xl bg-slate-900 border border-slate-800 relative">
            <DeviceAssetRenderer
              device={device}
              size={52}
              status={status}
              showGlow={true}
            />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono uppercase text-sky-400 tracking-wider">
                {asset.category}
              </span>
              <DeviceStatusIndicator status={status} size="xs" showLabel={true} />
            </div>
            <h3 className="font-bold text-sm text-white truncate max-w-[180px]" title={displayName}>
              {displayName}
            </h3>
            <p className="text-xs text-slate-400 truncate max-w-[180px]">{model}</p>
          </div>
        </div>

        <button
          onClick={onClose}
          className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/80 transition"
          title="Tutup Inspector"
          aria-label="Close Inspector"
        >
          <X size={16} />
        </button>
      </div>

      {/* Scrollable Details Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs font-sans custom-scrollbar">
        {/* Hardware & Identity Card */}
        <div className="rounded-xl bg-slate-900/60 border border-slate-800/80 p-3.5 space-y-2">
          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Server size={12} className="text-sky-400" /> Device Architecture
          </span>

          <div className="grid grid-cols-2 gap-2 pt-1 border-t border-slate-800/50 text-[11px]">
            <div>
              <span className="text-slate-500 block text-[10px]">Vendor</span>
              <span className="font-medium text-slate-200">{vendor}</span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px]">Model</span>
              <span className="font-medium text-slate-200 truncate block" title={model}>
                {model}
              </span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px]">Asset Profile</span>
              <span className="font-mono text-[10px] text-sky-300">{asset.key}</span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px]">OS / Firmware</span>
              <span className="font-medium text-slate-200">{osVersion}</span>
            </div>
          </div>
        </div>

        {/* Network & Addressing Card */}
        <div className="rounded-xl bg-slate-900/60 border border-slate-800/80 p-3.5 space-y-2">
          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Network size={12} className="text-emerald-400" /> Addressing & Interfaces
          </span>

          <div className="space-y-1.5 pt-1 border-t border-slate-800/50 text-[11px]">
            <div className="flex justify-between items-center">
              <span className="text-slate-500">Management IP</span>
              <span className="font-mono text-white bg-slate-800/80 px-1.5 py-0.5 rounded text-[10px]">
                {ipAddress}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-500">Hardware MAC</span>
              <span className="font-mono text-slate-300 text-[10px]">{macAddress}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-500">Default Ports</span>
              <span className="font-mono text-slate-300">
                {device.ports_count != null ? device.ports_count : asset.defaultPorts}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-500">Management Mode</span>
              <span
                className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${
                  isManaged ? "bg-emerald-500/10 text-emerald-400" : "bg-slate-800 text-slate-400"
                }`}
              >
                {isManaged ? <Shield size={10} /> : <ShieldAlert size={10} />}
                {isManaged ? "Managed" : "Unmanaged"}
              </span>
            </div>
          </div>
        </div>

        {/* Live Telemetry & Metrics (if available) */}
        {(device.cpu_load != null || device.latency_ms != null || device.uptime != null) && (
          <div className="rounded-xl bg-slate-900/60 border border-slate-800/80 p-3.5 space-y-2">
            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <Activity size={12} className="text-amber-400" /> Live Telemetry
            </span>

            <div className="grid grid-cols-2 gap-2 pt-1 border-t border-slate-800/50 text-[11px]">
              {device.latency_ms != null && (
                <div>
                  <span className="text-slate-500 block text-[10px]">Roundtrip Latency</span>
                  <span className="font-mono text-cyan-400">{Math.round(device.latency_ms)} ms</span>
                </div>
              )}
              {device.cpu_load != null && (
                <div>
                  <span className="text-slate-500 block text-[10px]">CPU Utilization</span>
                  <span className="font-mono text-amber-400">{device.cpu_load}%</span>
                </div>
              )}
              {device.uptime && (
                <div className="col-span-2">
                  <span className="text-slate-500 block text-[10px]">Uptime</span>
                  <span className="font-mono text-slate-300">{device.uptime}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Action Toolbar Bottom */}
      <div className="p-3 border-t border-slate-800/80 bg-slate-900/30 flex items-center gap-2">
        {onOpenTerminal && isManaged && (
          <button
            onClick={() => onOpenTerminal(device)}
            className="flex-1 py-1.5 px-2.5 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 text-[11px] font-semibold flex items-center justify-center gap-1.5 transition"
            title="Buka Sesi SSH AKANE Terminal"
          >
            <Terminal size={12} />
            <span>AKANE Terminal</span>
          </button>
        )}

        {onTroubleshoot && (
          <button
            onClick={() => onTroubleshoot(device.id)}
            className="flex-1 py-1.5 px-2.5 rounded-xl bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 border border-purple-500/40 text-[11px] font-semibold flex items-center justify-center gap-1.5 transition"
            title="Jalankan Diagnostik AI"
          >
            <Activity size={12} />
            <span>Diagnosa</span>
          </button>
        )}

        {onEdit && (
          <button
            onClick={() => onEdit(device)}
            className="p-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition"
            title="Edit Parameter Perangkat"
          >
            <Sliders size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
