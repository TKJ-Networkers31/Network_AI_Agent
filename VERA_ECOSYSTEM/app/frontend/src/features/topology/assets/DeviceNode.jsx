import React from "react";
import { Handle, Position } from "@xyflow/react";
import DeviceAssetRenderer from "./DeviceAssetRenderer.jsx";
import DeviceStatusIndicator, { getDeviceStatusStyle } from "./DeviceStatusIndicator.jsx";
import { resolveDeviceAsset } from "./deviceAssetRegistry.js";
import { Shield, ShieldAlert, Cpu, Activity, Hash } from "lucide-react";

/**
 * Enterprise Custom React Flow Device Node
 * Combines centralized vector assets, orthogonal status indicators, and network telemetry.
 */
export default function DeviceNode({ data = {}, selected = false }) {
  const asset = resolveDeviceAsset(data);
  const status = data.status || data.oper_status || "unknown";
  const statusStyle = getDeviceStatusStyle(status);

  const displayName = data.label || data.name || data.id || "Unnamed Device";
  const ipAddress = data.ip || data.management_ip || data.host || "-";
  const vendor = data.vendor || (asset.tags.includes("mikrotik") ? "MikroTik" : "");
  const model = data.model || asset.label;
  const isManaged = data.is_managed !== false && data.managed !== false && asset.key !== "unmanaged-device";

  return (
    <div
      className={`group relative rounded-2xl bg-slate-950/95 border backdrop-blur-md p-3.5 min-w-[220px] max-w-[270px] text-left transition-all duration-200 select-none ${
        statusStyle.containerBorder
      } ${statusStyle.haloShadow} ${
        selected
          ? "!border-cyan-400 ring-2 ring-cyan-400/80 shadow-[0_0_25px_rgba(34,211,238,0.45)]"
          : "hover:border-sky-400/50"
      }`}
      role="treeitem"
      aria-selected={selected}
      aria-label={`${displayName} (${asset.label}) - ${statusStyle.label}`}
    >
      {/* Visual Connection Handles for Multi-directional graph layout */}
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2.5 !h-2.5 !bg-cyan-500 !border-2 !border-slate-950 transition-transform group-hover:scale-125"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2.5 !h-2.5 !bg-cyan-500 !border-2 !border-slate-950 transition-transform group-hover:scale-125"
      />
      <Handle
        type="target"
        position={Position.Left}
        id="left"
        className="!w-2.5 !h-2.5 !bg-cyan-500 !border-2 !border-slate-950 transition-transform group-hover:scale-125"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="right"
        className="!w-2.5 !h-2.5 !bg-cyan-500 !border-2 !border-slate-950 transition-transform group-hover:scale-125"
      />

      {/* Top Header: Device Illustration & Status Indicator */}
      <div className="flex items-start justify-between gap-2.5 mb-2.5">
        <div className="flex items-center gap-2.5">
          {/* Vector Device Illustration */}
          <DeviceAssetRenderer
            device={data}
            size={42}
            status={status}
            showGlow={true}
            className="p-1 rounded-xl bg-slate-900/90 border border-slate-800"
          />
          <div className="flex flex-col">
            <span className="text-[10px] font-mono uppercase tracking-wider text-sky-400/80 truncate max-w-[100px]">
              {vendor || asset.category}
            </span>
            <span className="text-[11px] font-medium text-slate-300 truncate max-w-[100px]" title={model}>
              {model}
            </span>
          </div>
        </div>

        {/* Orthogonal Status Pill */}
        <DeviceStatusIndicator status={status} size="sm" showLabel={true} />
      </div>

      {/* Primary Device Identity: Name & Hostname */}
      <div className="pt-1 border-t border-slate-800/80">
        <div className="font-semibold text-xs text-white truncate tracking-wide" title={displayName}>
          {displayName}
        </div>
        <div className="mt-0.5 flex items-center justify-between text-[11px] font-mono text-slate-400">
          <span className="truncate">{ipAddress}</span>
          {data.role && (
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-800/80 text-sky-300 uppercase">
              {data.role}
            </span>
          )}
        </div>
      </div>

      {/* Bottom Metadata & Telemetry */}
      <div className="mt-2.5 pt-2 border-t border-slate-800/50 flex items-center justify-between text-[10px] font-mono text-slate-400">
        {/* Managed / Unmanaged Flag */}
        <div className="flex items-center gap-1">
          {isManaged ? (
            <span className="inline-flex items-center gap-1 text-emerald-400/90">
              <Shield size={11} /> Managed
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-slate-500">
              <ShieldAlert size={11} /> Unmanaged
            </span>
          )}
        </div>

        {/* Telemetry pill */}
        <div className="flex items-center gap-2">
          {data.ports_count != null ? (
            <span className="flex items-center gap-0.5 text-slate-400" title="Ports">
              <Hash size={10} /> {data.ports_count}
            </span>
          ) : asset.defaultPorts > 0 ? (
            <span className="flex items-center gap-0.5 text-slate-500" title="Default Ports">
              <Hash size={10} /> {asset.defaultPorts}
            </span>
          ) : null}

          {data.cpu_load != null && (
            <span className="flex items-center gap-0.5 text-amber-400" title="CPU Load">
              <Cpu size={10} /> {data.cpu_load}%
            </span>
          )}

          {data.latency_ms != null && (
            <span className="flex items-center gap-0.5 text-cyan-400" title="Ping Latency">
              <Activity size={10} /> {Math.round(data.latency_ms)}ms
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
