/**
 * src/platform/adaptive-experience/blocks/ResourceGaugeBlock.jsx
 *
 * Visual gauge / progress bar presentation for router resources (CPU, RAM, Disk).
 * Adheres to the VERA Design System with high-contrast status colors.
 */

import React from "react";
import { Cpu, HardDrive, MemoryStick, Server } from "lucide-react";

export default function ResourceGaugeBlock({ block }) {
  const data = block?.data || {};
  const device = data.device || "Router";
  const cpu = data.cpu || { value: 0, status: "healthy" };
  const memory = data.memory || { value: 0, used_mb: 0, total_mb: 0, status: "healthy" };
  const disk = data.disk || { value: 0, used_mb: 0, total_mb: 0, status: "healthy" };

  const getStatusColor = (status, val) => {
    if (status === "critical" || val > 85) return "bg-red-500 text-red-400";
    if (status === "warning" || val > 70) return "bg-amber-500 text-amber-400";
    return "bg-emerald-500 text-emerald-400";
  };

  const getBarColor = (status, val) => {
    if (status === "critical" || val > 85) return "bg-gradient-to-r from-red-600 to-red-400";
    if (status === "warning" || val > 70) return "bg-gradient-to-r from-amber-600 to-amber-400";
    return "bg-gradient-to-r from-cyan-600 to-emerald-400";
  };

  return (
    <div className="my-2 p-4 rounded-xl border border-white/10 bg-slate-900/80 backdrop-blur-md shadow-lg space-y-4 font-sans">
      <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-cyan-500/10 text-cyan-400">
            <Server size={18} />
          </div>
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-white/90">
              Kondisi Resource Perangkat
            </h4>
            <p className="text-[11px] text-white/50">{device}</p>
          </div>
        </div>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-950/60 border border-cyan-500/30 text-cyan-300">
          LIVE HARDWARE
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* CPU Load Gauge */}
        <div className="p-3 rounded-lg border border-white/5 bg-black/30 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="flex items-center gap-1.5 text-white/70">
              <Cpu size={14} className="text-cyan-400" /> CPU Load
            </span>
            <span className={`font-mono font-bold ${getStatusColor(cpu.status, cpu.value).split(" ")[1]}`}>
              {cpu.value}%
            </span>
          </div>
          <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden">
            <div
              className={`h-full ${getBarColor(cpu.status, cpu.value)} transition-all duration-500`}
              style={{ width: `${Math.min(100, Math.max(0, cpu.value))}%` }}
            />
          </div>
        </div>

        {/* Memory Gauge */}
        <div className="p-3 rounded-lg border border-white/5 bg-black/30 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="flex items-center gap-1.5 text-white/70">
              <MemoryStick size={14} className="text-emerald-400" /> RAM Terpakai
            </span>
            <span className={`font-mono font-bold ${getStatusColor(memory.status, memory.value).split(" ")[1]}`}>
              {memory.value}%
            </span>
          </div>
          <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden">
            <div
              className={`h-full ${getBarColor(memory.status, memory.value)} transition-all duration-500`}
              style={{ width: `${Math.min(100, Math.max(0, memory.value))}%` }}
            />
          </div>
          <div className="text-[10px] text-white/40 font-mono text-right">
            {memory.used_mb}MB / {memory.total_mb}MB
          </div>
        </div>

        {/* Disk Space Gauge */}
        <div className="p-3 rounded-lg border border-white/5 bg-black/30 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="flex items-center gap-1.5 text-white/70">
              <HardDrive size={14} className="text-purple-400" /> Penyimpanan
            </span>
            <span className={`font-mono font-bold ${getStatusColor(disk.status, disk.value).split(" ")[1]}`}>
              {disk.value}%
            </span>
          </div>
          <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden">
            <div
              className={`h-full ${getBarColor(disk.status, disk.value)} transition-all duration-500`}
              style={{ width: `${Math.min(100, Math.max(0, disk.value))}%` }}
            />
          </div>
          <div className="text-[10px] text-white/40 font-mono text-right">
            {disk.used_mb}MB / {disk.total_mb}MB
          </div>
        </div>
      </div>
    </div>
  );
}
