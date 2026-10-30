// src/components/nms/DeviceDetailModal.jsx
//
// Modal Inspeksi Detail Telemetri Perangkat NMS
// Menampilkan status ketersediaan, grafik historis CPU/RAM/Latency, daftar antarmuka
// dengan laju bandwidth real-time, riwayat insiden, serta kontrol profil pemantauan.

import { useEffect, useState } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  Clock,
  Cpu,
  HardDrive,
  Loader2,
  Network,
  Pause,
  Play,
  Radio,
  Server,
  ShieldCheck,
  Thermometer,
  Wrench,
  X,
  Zap,
} from "lucide-react";

export default function DeviceDetailModal({
  deviceId,
  onClose,
  onOpenWizard,
  pushToast,
}) {
  const [device, setDevice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("resources");
  const [timeRange, setTimeRange] = useState("1h");
  const [resHistory, setResHistory] = useState([]);
  const [selectedIface, setSelectedIface] = useState(null);
  const [ifaceHistory, setIfaceHistory] = useState([]);
  const [testing, setTesting] = useState(false);

  const fetchDetail = async () => {
    try {
      const res = await fetch(`/api/nms/devices/${encodeURIComponent(deviceId)}`);
      const json = await res.json();
      if (json.success) {
        setDevice(json.device);
        if (json.device.interfaces?.length > 0 && !selectedIface) {
          setSelectedIface(json.device.interfaces[0].interface_name);
        }
      }
    } catch {
      pushToast?.("Gagal memuat detail perangkat NMS.", "error");
    } finally {
      setLoading(false);
    }
  };

  const fetchResHistory = async () => {
    try {
      const res = await fetch(
        `/api/nms/devices/${encodeURIComponent(deviceId)}/resources/history?range=${timeRange}`
      );
      const json = await res.json();
      if (json.success) {
        setResHistory(json.history || []);
      }
    } catch {}
  };

  const fetchIfaceHistory = async (iface) => {
    if (!iface) return;
    try {
      const res = await fetch(
        `/api/nms/devices/${encodeURIComponent(deviceId)}/interfaces/${encodeURIComponent(
          iface
        )}/history?range=${timeRange}`
      );
      const json = await res.json();
      if (json.success) {
        setIfaceHistory(json.history || []);
      }
    } catch {}
  };

  useEffect(() => {
    fetchDetail();
  }, [deviceId]);

  useEffect(() => {
    fetchResHistory();
  }, [deviceId, timeRange]);

  useEffect(() => {
    if (selectedIface) {
      fetchIfaceHistory(selectedIface);
    }
  }, [deviceId, selectedIface, timeRange]);

  const handleTestNow = async () => {
    setTesting(true);
    try {
      const res = await fetch(`/api/nms/devices/${encodeURIComponent(deviceId)}/test`, {
        method: "POST",
      });
      const json = await res.json();
      if (json.success) {
        setDevice(json.device);
        pushToast?.("Pemeriksaan perangkat selesai diperbarui!", "success");
        fetchResHistory();
      }
    } catch {
      pushToast?.("Gagal menjalankan uji konektivitas.", "error");
    } finally {
      setTesting(false);
    }
  };

  const handleTogglePause = async () => {
    if (!device?.profile) return;
    const nextState = !device.profile.is_paused;
    try {
      const res = await fetch(`/api/nms/devices/${encodeURIComponent(deviceId)}/profile`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_paused: nextState }),
      });
      const json = await res.json();
      if (json.success) {
        pushToast?.(
          nextState ? "Monitoring perangkat dijeda." : "Monitoring perangkat dilanjutkan.",
          "info"
        );
        fetchDetail();
      }
    } catch {
      pushToast?.("Gagal mengubah status pemantauan.", "error");
    }
  };

  const formatBps = (bps) => {
    if (!bps || bps <= 0) return "0 bps";
    if (bps >= 1_000_000_000) return `${(bps / 1_000_000_000).toFixed(2)} Gbps`;
    if (bps >= 1_000_000) return `${(bps / 1_000_000).toFixed(2)} Mbps`;
    if (bps >= 1_000) return `${(bps / 1_000).toFixed(1)} kbps`;
    return `${Math.round(bps)} bps`;
  };

  const formatBytes = (b) => {
    if (!b || b <= 0) return "0 B";
    if (b >= 1024 * 1024 * 1024) return `${(b / (1024 * 1024 * 1024)).toFixed(2)} GB`;
    if (b >= 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(1)} MB`;
    if (b >= 1024) return `${(b / 1024).toFixed(0)} KB`;
    return `${b} B`;
  };

  const formatUptime = (sec) => {
    if (!sec || sec <= 0) return "-";
    const d = Math.floor(sec / 86400);
    const h = Math.floor((sec % 86400) / 3600);
    const m = Math.floor((sec % 3600) / 60);
    if (d > 0) return `${d}h ${h}j ${m}m`;
    if (h > 0) return `${h}j ${m}m`;
    return `${m}m ${sec % 60}s`;
  };

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
        <div className="p-8 rounded-2xl bg-[#0b101b] border border-white/10 flex items-center gap-3 text-cyan-400">
          <Loader2 size={24} className="animate-spin" />
          <span className="text-sm">Memuat detail telemetri NMS...</span>
        </div>
      </div>
    );
  }

  if (!device) return null;

  const prof = device.profile || {};
  const latM = device.latest_metrics || {};
  const status = prof.status || "UNKNOWN";

  const statusColors = {
    UP: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
    DEGRADED: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    SUSPECTED_DOWN: "bg-orange-500/20 text-orange-300 border-orange-500/40",
    DOWN: "bg-red-500/20 text-red-300 border-red-500/40 animate-pulse",
    MONITORING_UNAVAILABLE: "bg-purple-500/20 text-purple-300 border-purple-500/40",
    UNKNOWN: "bg-slate-500/20 text-slate-300 border-slate-500/40",
  }[status] || "bg-white/10 text-white/60 border-white/20";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-4xl max-h-[90vh] flex flex-col bg-[#0b101b] border border-white/10 rounded-2xl shadow-2xl overflow-hidden text-white">
        {/* Header Bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-white/[0.02]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
              <Server size={22} />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-base font-semibold">{device.name}</h2>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold ${statusColors}`}>
                  {status}
                </span>
                {prof.is_stale && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 font-semibold" title="Data pemantauan kedaluwarsa">
                    STALE
                  </span>
                )}
                {device.name_source && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-white/50 font-mono uppercase">
                    {device.name_source.replace("_", " ")}
                  </span>
                )}
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-white/50">
                  {prof.management_mode === "managed" ? `Managed (${prof.monitoring_method || "SNMP"})` : "Unmanaged (Ping)"}
                </span>
              </div>
              <p className="text-xs text-white/50 font-mono mt-0.5 flex flex-wrap gap-x-2">
                <span>IP: {device.ip || "-"}</span>
                <span>MAC: {device.mac || "-"}</span>
                <span>Latency: {prof.latency_ms?.toFixed(1) || "0.0"} ms</span>
                {device.identity && <span>Identity: {device.identity}</span>}
                {prof.routeros_model && <span>Model: {prof.routeros_model}</span>}
                {prof.routeros_version && <span>ROS: {prof.routeros_version}</span>}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                onClose();
                try {
                  sessionStorage.setItem("aira_focus_topology_node", device.id);
                } catch {}
                window.dispatchEvent(new CustomEvent("aira:navigate", { detail: "topology" }));
              }}
              title="Buka dan lihat perangkat di graf topologi"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-500/10 hover:bg-sky-500/20 border border-sky-500/30 text-sky-300 text-xs font-medium transition"
            >
              <Network size={13} />
              <span className="hidden sm:inline">Topologi</span>
            </button>

            <button
              onClick={handleTestNow}
              disabled={testing}
              title="Periksa sekarang"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 text-cyan-300 text-xs transition"
            >
              {testing ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
              <span>Test Now</span>
            </button>

            {prof.management_mode !== "managed" && onOpenWizard && (
              <button
                onClick={() => {
                  onClose();
                  onOpenWizard(device);
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-300 text-xs font-semibold transition"
              >
                <ShieldCheck size={14} />
                <span>Setup SNMP</span>
              </button>
            )}

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-white/50 hover:text-white hover:bg-white/10 transition"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Tab Selector */}
        <div className="flex items-center justify-between px-6 bg-white/[0.01] border-b border-white/5">
          <div className="flex gap-2">
            {[
              { id: "resources", label: "Resource Telemetry", icon: Cpu },
              { id: "interfaces", label: `Interfaces (${device.interfaces?.length || 0})`, icon: Network },
              { id: "incidents", label: `Incidents (${device.incidents?.length || 0})`, icon: AlertTriangle },
              { id: "profile", label: "Monitoring Profile", icon: Wrench },
            ].map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-1.5 py-3 px-3 text-xs font-medium border-b-2 transition ${
                    activeTab === tab.id
                      ? "border-cyan-400 text-cyan-300"
                      : "border-transparent text-white/50 hover:text-white"
                  }`}
                >
                  <Icon size={14} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {(activeTab === "resources" || activeTab === "interfaces") && (
            <div className="flex items-center gap-1 py-2">
              <span className="text-[11px] text-white/40 mr-1">Range:</span>
              {["15m", "1h", "24h", "7d"].map((r) => (
                <button
                  key={r}
                  onClick={() => setTimeRange(r)}
                  className={`px-2 py-0.5 rounded text-[11px] transition ${
                    timeRange === r
                      ? "bg-cyan-500/20 border border-cyan-400/40 text-cyan-300 font-semibold"
                      : "bg-white/5 text-white/50 hover:text-white"
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Body Container */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* TAB 1: RESOURCES */}
          {activeTab === "resources" && (
            <div className="space-y-6">
              {/* Summary Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/10 space-y-1">
                  <span className="text-white/40 flex items-center gap-1">
                    <Cpu size={14} className="text-cyan-400" />
                    <span>CPU Load</span>
                  </span>
                  <div className="text-lg font-bold text-cyan-300">
                    {latM.cpu_load_percent != null ? `${latM.cpu_load_percent}%` : "-"}
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/10 space-y-1">
                  <span className="text-white/40 flex items-center gap-1">
                    <Server size={14} className="text-purple-400" />
                    <span>Memory Usage</span>
                  </span>
                  <div className="text-lg font-bold text-purple-300">
                    {latM.memory_used_percent != null ? `${latM.memory_used_percent}%` : "-"}
                  </div>
                  <div className="text-[10px] text-white/50">
                    {formatBytes(latM.memory_used_bytes)} / {formatBytes(latM.memory_total_bytes)}
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/10 space-y-1">
                  <span className="text-white/40 flex items-center gap-1">
                    <Clock size={14} className="text-emerald-400" />
                    <span>Uptime</span>
                  </span>
                  <div className="text-sm font-semibold text-emerald-300">
                    {formatUptime(latM.uptime_seconds)}
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-white/[0.03] border border-white/10 space-y-1">
                  <span className="text-white/40 flex items-center gap-1">
                    <Thermometer size={14} className="text-pink-400" />
                    <span>Temperature</span>
                  </span>
                  <div className="text-lg font-bold text-pink-300">
                    {latM.temperature_celsius != null ? `${latM.temperature_celsius}°C` : "-"}
                  </div>
                </div>
              </div>

              {/* Historical Resource SVG Chart */}
              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/10 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-semibold text-white/80">Grafik Historis CPU &amp; Memory (%)</h3>
                  <div className="flex items-center gap-3 text-[11px]">
                    <span className="flex items-center gap-1.5 text-cyan-300">
                      <span className="w-2.5 h-2.5 rounded-sm bg-cyan-400" /> CPU
                    </span>
                    <span className="flex items-center gap-1.5 text-purple-300">
                      <span className="w-2.5 h-2.5 rounded-sm bg-purple-400" /> Memory
                    </span>
                  </div>
                </div>

                {resHistory.length > 1 ? (
                  <div className="relative h-44 w-full">
                    <svg className="w-full h-full overflow-visible" viewBox="0 0 500 120" preserveAspectRatio="none">
                      {/* Grid lines */}
                      <line x1="0" y1="30" x2="500" y2="30" stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
                      <line x1="0" y1="60" x2="500" y2="60" stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
                      <line x1="0" y1="90" x2="500" y2="90" stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />

                      {/* CPU Path */}
                      <polyline
                        fill="none"
                        stroke="#38bdf8"
                        strokeWidth="2.5"
                        points={resHistory
                          .map((d, i) => {
                            const x = (i / (resHistory.length - 1)) * 500;
                            const y = 120 - ((d.cpu_load_percent || 0) / 100) * 120;
                            return `${x},${y}`;
                          })
                          .join(" ")}
                      />

                      {/* Memory Path */}
                      <polyline
                        fill="none"
                        stroke="#c084fc"
                        strokeWidth="2"
                        strokeDasharray="4 2"
                        points={resHistory
                          .map((d, i) => {
                            const x = (i / (resHistory.length - 1)) * 500;
                            const y = 120 - ((d.memory_used_percent || 0) / 100) * 120;
                            return `${x},${y}`;
                          })
                          .join(" ")}
                      />
                    </svg>
                  </div>
                ) : (
                  <div className="h-32 flex items-center justify-center text-xs text-white/40">
                    Belum cukup data historis untuk rentang waktu ini.
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 2: INTERFACES */}
          {activeTab === "interfaces" && (
            <div className="space-y-6">
              {/* Interfaces Table */}
              <div className="rounded-xl border border-white/10 overflow-hidden text-xs">
                <table className="w-full text-left">
                  <thead className="bg-white/5 text-white/50 text-[11px] border-b border-white/10">
                    <tr>
                      <th className="py-2.5 px-3 font-medium">Interface</th>
                      <th className="py-2.5 px-3 font-medium">Status (Admin/Oper)</th>
                      <th className="py-2.5 px-3 font-medium">Link Speed &amp; Duplex</th>
                      <th className="py-2.5 px-3 font-medium text-right">RX Rate</th>
                      <th className="py-2.5 px-3 font-medium text-right">TX Rate</th>
                      <th className="py-2.5 px-3 font-medium text-center">Drops/Errors</th>
                      <th className="py-2.5 px-3 font-medium text-center">Aksi</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {device.interfaces?.map((iface) => {
                      const isSel = selectedIface === iface.interface_name;
                      return (
                        <tr
                          key={iface.interface_name}
                          className={`hover:bg-white/[0.04] transition ${
                            isSel ? "bg-cyan-500/10" : ""
                          }`}
                        >
                          <td className="py-2.5 px-3 font-semibold text-white">
                            <div>{iface.interface_name}</div>
                            {iface.interface_type && iface.interface_type !== "unknown" && (
                              <span className="text-[10px] text-white/40 block font-normal font-mono">{iface.interface_type}</span>
                            )}
                          </td>
                          <td className="py-2.5 px-3">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span
                                className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                                  iface.oper_status === "up"
                                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                                    : iface.oper_status === "disabled"
                                    ? "bg-slate-500/20 text-slate-300 border border-slate-500/40"
                                    : "bg-red-500/20 text-red-300 border border-red-500/40"
                                }`}
                              >
                                {iface.oper_status?.toUpperCase() || "UNKNOWN"}
                              </span>
                              {iface.admin_status === "disabled" && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/30">
                                  ADMIN DOWN
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="py-2.5 px-3 text-white/70">
                            {iface.negotiated_speed_bps ? (
                              <div className="font-mono text-xs">
                                <span>{formatBps(iface.negotiated_speed_bps)}</span>
                                {iface.duplex && iface.duplex !== "unknown" && (
                                  <span className="text-[10px] text-white/40 ml-1">({iface.duplex})</span>
                                )}
                              </div>
                            ) : (
                              <span className="text-white/30 font-mono">-</span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono text-cyan-300">
                            <div>{formatBps(iface.rx_rate_bps)}</div>
                            {iface.rx_utilization_percent != null && (
                              <div className="text-[10px] text-cyan-400/70">{iface.rx_utilization_percent.toFixed(1)}% util</div>
                            )}
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono text-purple-300">
                            <div>{formatBps(iface.tx_rate_bps)}</div>
                            {iface.tx_utilization_percent != null && (
                              <div className="text-[10px] text-purple-400/70">{iface.tx_utilization_percent.toFixed(1)}% util</div>
                            )}
                          </td>
                          <td className="py-2.5 px-3 text-center text-[10px] font-mono text-white/50">
                            {(iface.in_errors || 0) + (iface.out_errors || 0) > 0 ? (
                              <span className="text-red-400 font-semibold">Err: {(iface.in_errors || 0) + (iface.out_errors || 0)}</span>
                            ) : (
                              <span>0 err</span>
                            )}
                            {(iface.in_drops || 0) + (iface.out_drops || 0) > 0 && (
                              <span className="text-amber-400 block">Drop: {(iface.in_drops || 0) + (iface.out_drops || 0)}</span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 text-center">
                            <button
                              onClick={() => setSelectedIface(iface.interface_name)}
                              className={`px-2 py-1 rounded text-[10px] font-medium transition ${
                                isSel
                                  ? "bg-cyan-500 text-black font-bold"
                                  : "bg-white/10 hover:bg-white/20 text-white/80"
                              }`}
                            >
                              {isSel ? "Grafik Aktif" : "Lihat Grafik"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Interface Traffic Historical Graph */}
              {selectedIface && (
                <div className="p-4 rounded-xl bg-white/[0.02] border border-white/10 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-semibold text-white/80">
                      Grafik Traffic: <span className="text-cyan-300 font-mono">{selectedIface}</span>
                    </h3>
                    <div className="flex items-center gap-3 text-[11px]">
                      <span className="flex items-center gap-1.5 text-cyan-300 font-mono">
                        <ArrowDown size={12} /> RX Rate (bps)
                      </span>
                      <span className="flex items-center gap-1.5 text-purple-300 font-mono">
                        <ArrowUp size={12} /> TX Rate (bps)
                      </span>
                    </div>
                  </div>

                  {ifaceHistory.length > 1 ? (
                    <div className="relative h-44 w-full">
                      <svg className="w-full h-full overflow-visible" viewBox="0 0 500 120" preserveAspectRatio="none">
                        {/* Grid lines */}
                        <line x1="0" y1="30" x2="500" y2="30" stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
                        <line x1="0" y1="60" x2="500" y2="60" stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
                        <line x1="0" y1="90" x2="500" y2="90" stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />

                        {(() => {
                          const maxBps = Math.max(
                            ...ifaceHistory.map((d) => Math.max(d.rx_rate_bps || 0, d.tx_rate_bps || 0)),
                            1000
                          );
                          return (
                            <>
                              {/* RX Rate Line */}
                              <polyline
                                fill="none"
                                stroke="#38bdf8"
                                strokeWidth="2.5"
                                points={ifaceHistory
                                  .map((d, i) => {
                                    const x = (i / (ifaceHistory.length - 1)) * 500;
                                    const y = 120 - ((d.rx_rate_bps || 0) / maxBps) * 110;
                                    return `${x},${y}`;
                                  })
                                  .join(" ")}
                              />
                              {/* TX Rate Line */}
                              <polyline
                                fill="none"
                                stroke="#c084fc"
                                strokeWidth="2"
                                points={ifaceHistory
                                  .map((d, i) => {
                                    const x = (i / (ifaceHistory.length - 1)) * 500;
                                    const y = 120 - ((d.tx_rate_bps || 0) / maxBps) * 110;
                                    return `${x},${y}`;
                                  })
                                  .join(" ")}
                              />
                            </>
                          );
                        })()}
                      </svg>
                    </div>
                  ) : (
                    <div className="h-32 flex items-center justify-center text-xs text-white/40">
                      Belum ada data sampel traffic historis untuk interface {selectedIface}.
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* TAB 3: INCIDENTS */}
          {activeTab === "incidents" && (
            <div className="space-y-4 text-xs">
              {device.incidents?.length > 0 ? (
                <div className="space-y-2">
                  {device.incidents.map((inc) => (
                    <div
                      key={inc.id}
                      className={`p-3 rounded-xl border flex items-start gap-3 ${
                        inc.status === "open"
                          ? "bg-red-950/20 border-red-500/30 text-red-200"
                          : "bg-white/[0.02] border-white/10 text-white/70"
                      }`}
                    >
                      <AlertCircle
                        size={16}
                        className={inc.status === "open" ? "text-red-400 mt-0.5 shrink-0" : "text-emerald-400 mt-0.5 shrink-0"}
                      />
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-white">{inc.title}</span>
                          <span className="text-[10px] text-white/40">
                            {new Date(inc.started_at * 1000).toLocaleString("id-ID")}
                          </span>
                        </div>
                        <p className="text-[11px] leading-relaxed text-white/70 whitespace-pre-line">
                          {inc.details}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-8 rounded-xl bg-white/[0.02] border border-white/10 text-center text-white/40 space-y-1">
                  <CheckCircle2 size={24} className="mx-auto text-emerald-400" />
                  <p>Tidak ada catatan insiden aktif pada perangkat ini.</p>
                </div>
              )}
            </div>
          )}

          {/* TAB 4: PROFILE */}
          {activeTab === "profile" && (
            <div className="space-y-4 text-xs">
              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/10 space-y-3">
                <h3 className="font-semibold text-white">Pengaturan Pemantauan Perangkat</h3>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <span className="text-white/40 block mb-0.5">Mode Manajemen:</span>
                    <span className="font-semibold capitalize text-cyan-300">
                      {prof.management_mode}
                    </span>
                  </div>
                  <div>
                    <span className="text-white/40 block mb-0.5">SNMP Service:</span>
                    <span className="font-semibold text-white">
                      {prof.snmp_enabled ? `Aktif (${prof.snmp_version}, port ${prof.snmp_port})` : "Mati"}
                    </span>
                  </div>
                  <div>
                    <span className="text-white/40 block mb-0.5">Status Pause:</span>
                    <span className="font-semibold text-white">
                      {prof.is_paused ? "Dijeda (Paused)" : "Berjalan Aktif"}
                    </span>
                  </div>
                  <div>
                    <span className="text-white/40 block mb-0.5">Maintenance Mode:</span>
                    <span className="font-semibold text-white">
                      {prof.maintenance_mode ? "Ya (Alert Dibisukan)" : "Tidak"}
                    </span>
                  </div>
                </div>

                <div className="pt-3 border-t border-white/10 flex items-center gap-3">
                  <button
                    onClick={handleTogglePause}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white font-medium transition"
                  >
                    {prof.is_paused ? <Play size={13} /> : <Pause size={13} />}
                    <span>{prof.is_paused ? "Lanjutkan Monitoring" : "Jeda Monitoring"}</span>
                  </button>

                  {onOpenWizard && (
                    <button
                      onClick={() => {
                        onClose();
                        onOpenWizard(device);
                      }}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-300 font-semibold transition"
                    >
                      <Wrench size={13} />
                      <span>Re-konfigurasi SNMP</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
