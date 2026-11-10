// src/components/nms/DeviceDetailModal.jsx
//
// Modal Inspeksi Detail Telemetri Perangkat NMS & Multi-Path Management
// Menampilkan status ketersediaan, freshness telemetri, grafik historis CPU/RAM/Latency,
// pemantauan antarmuka real-time, manajemen insiden, serta selector Multi-Path MikroTik
// (SSH, API, MAC Telnet, MAC WinBox, RoMON).

import { useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Check,
  CheckCircle2,
  Clock,
  Cpu,
  HardDrive,
  Info,
  Layers,
  Loader2,
  Lock,
  Network,
  Pause,
  Play,
  Radio,
  RefreshCw,
  RotateCcw,
  Server,
  ShieldCheck,
  Terminal,
  Thermometer,
  Waypoints,
  Wrench,
  X,
  Zap,
} from "lucide-react";

function buildNmsWsUrl() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const isDev = window.location.port === "5173";
  const host = isDev ? `${window.location.hostname}:8000` : window.location.host;
  return `${proto}//${host}/ws/nms`;
}

const METHOD_META = {
  ssh_ip: { label: "SSH (IP)", proto: "TCP 22", layer: "Layer 3" },
  api_ip: { label: "RouterOS API (IP)", proto: "TCP 8728", layer: "Layer 3" },
  mac_telnet: { label: "MAC Telnet", proto: "Layer 2", layer: "Layer 2 Adjacent" },
  mac_winbox: { label: "MAC WinBox", proto: "Layer 2", layer: "Layer 2 Adjacent" },
  romon: { label: "RoMON Overlay", proto: "MikroTik Protocol", layer: "RoMON Network" },
};

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

  // Multi-Path Management states
  const [mgmtProfile, setMgmtProfile] = useState(null);
  const [loadingMgmt, setLoadingMgmt] = useState(false);
  const [testingMethod, setTestingMethod] = useState(null);
  const [romonNeighbors, setRomonNeighbors] = useState([]);
  const [loadingRomon, setLoadingRomon] = useState(false);

  // RoMON Provisioning Modal states
  const [romonPlanModalOpen, setRomonPlanModalOpen] = useState(false);
  const [romonPlan, setRomonPlan] = useState(null);
  const [romonApproved, setRomonApproved] = useState(false);
  const [romonApplying, setRomonApplying] = useState(false);

  // WebSocket Live state
  const [wsStatus, setWsStatus] = useState("connecting");
  const wsRef = useRef(null);
  const unmountedRef = useRef(false);

  const fetchDetail = async () => {
    try {
      const res = await fetch(`/api/nms/devices/${encodeURIComponent(deviceId)}`);
      const json = await res.json();
      if (json.success && !unmountedRef.current) {
        setDevice(json.device);
        if (json.device.interfaces?.length > 0 && !selectedIface) {
          setSelectedIface(json.device.interfaces[0].interface_name);
        }
      }
    } catch {
      if (!unmountedRef.current) pushToast?.("Gagal memuat detail perangkat NMS.", "error");
    } finally {
      if (!unmountedRef.current) setLoading(false);
    }
  };

  const fetchResHistory = async () => {
    try {
      const res = await fetch(
        `/api/nms/devices/${encodeURIComponent(deviceId)}/resources/history?range=${timeRange}`
      );
      const json = await res.json();
      if (json.success && !unmountedRef.current) {
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
      if (json.success && !unmountedRef.current) {
        setIfaceHistory(json.history || []);
      }
    } catch {}
  };

  // Fetch Multi-Path profile
  const fetchManagementProfile = async () => {
    setLoadingMgmt(true);
    try {
      const res = await fetch(`/api/devices/${encodeURIComponent(deviceId)}/management/paths`);
      const json = await res.json();
      if (json.success && !unmountedRef.current) {
        setMgmtProfile(json.profile);
      }
    } catch {
      if (!unmountedRef.current) pushToast?.("Gagal memuat jalur manajemen multi-path.", "error");
    } finally {
      if (!unmountedRef.current) setLoadingMgmt(false);
    }
  };

  // Fetch RoMON neighbors
  const fetchRomonNeighbors = async () => {
    setLoadingRomon(true);
    try {
      const res = await fetch(`/api/devices/${encodeURIComponent(deviceId)}/management/romon/neighbors`);
      const json = await res.json();
      if (json.success && !unmountedRef.current) {
        setRomonNeighbors(json.neighbors || []);
      }
    } catch {
      if (!unmountedRef.current) pushToast?.("Gagal memuat neighbor RoMON.", "error");
    } finally {
      if (!unmountedRef.current) setLoadingRomon(false);
    }
  };

  // Trigger RoMON discovery
  const handleDiscoverRomon = async () => {
    setLoadingRomon(true);
    try {
      const res = await fetch(`/api/devices/${encodeURIComponent(deviceId)}/management/romon/discover`, {
        method: "POST",
      });
      const json = await res.json();
      if (json.success) {
        pushToast?.(json.message || "Discovery RoMON berhasil dijalankan.", "success");
        setRomonNeighbors(json.neighbors || []);
        fetchManagementProfile();
      } else {
        pushToast?.(json.message || "Gagal menjalankan discovery RoMON.", "error");
      }
    } catch {
      pushToast?.("Error komunikasi endpoint RoMON discovery.", "error");
    } finally {
      setLoadingRomon(false);
    }
  };

  // Manual management path override
  const handleSelectPath = async (method) => {
    try {
      const res = await fetch(`/api/devices/${encodeURIComponent(deviceId)}/management/select`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ method: method || null }),
      });
      const json = await res.json();
      if (json.success) {
        pushToast?.(json.message || "Jalur manajemen berhasil diubah.", "success");
        fetchManagementProfile();
      } else {
        pushToast?.(json.message || "Gagal mengubah jalur manajemen.", "error");
      }
    } catch {
      pushToast?.("Gagal menghubungi server untuk mengubah jalur manajemen.", "error");
    }
  };

  // Test individual management path
  const handleTestPath = async (method) => {
    setTestingMethod(method);
    try {
      const res = await fetch(`/api/devices/${encodeURIComponent(deviceId)}/management/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ method }),
      });
      const json = await res.json();
      if (json.success && json.result?.reachable) {
        pushToast?.(`Tes jalur ${METHOD_META[method]?.label || method} berhasil (${json.result?.latency_ms || 0}ms).`, "success");
      } else {
        pushToast?.(`Tes jalur ${METHOD_META[method]?.label || method} gagal: ${json.result?.error || json.message || "Tidak terjangkau"}`, "error");
      }
      fetchManagementProfile();
    } catch {
      pushToast?.(`Gagal mengeksekusi tes jalur ${method}.`, "error");
    } finally {
      setTestingMethod(null);
    }
  };

  // RoMON Provisioning Plan
  const handleOpenRomonPlan = async () => {
    try {
      const res = await fetch(`/api/devices/${encodeURIComponent(deviceId)}/management/romon/plan`, {
        method: "POST",
      });
      const json = await res.json();
      if (json.success && json.plan) {
        setRomonPlan(json.plan);
        setRomonApproved(false);
        setRomonPlanModalOpen(true);
      } else {
        pushToast?.(json.message || "Gagal menyusun plan provisioning RoMON.", "error");
      }
    } catch {
      pushToast?.("Error saat menyusun plan RoMON.", "error");
    }
  };

  // Apply RoMON Plan
  const handleApplyRomonPlan = async () => {
    if (!romonApproved) {
      pushToast?.("Harap setujui rencana konfigurasi terlebih dahulu.", "warning");
      return;
    }
    setRomonApplying(true);
    try {
      const res = await fetch(`/api/devices/${encodeURIComponent(deviceId)}/management/romon/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ admin_approved: true }),
      });
      const json = await res.json();
      if (json.success) {
        pushToast?.(json.message || "RoMON berhasil diprovisi dan diverifikasi aktif!", "success");
        setRomonPlanModalOpen(false);
        fetchManagementProfile();
        fetchRomonNeighbors();
      } else {
        pushToast?.(`Provisioning RoMON gagal: ${json.message || json.detail}`, "error");
      }
    } catch {
      pushToast?.("Error komunikasi saat provisioning RoMON.", "error");
    } finally {
      setRomonApplying(false);
    }
  };

  // Rollback RoMON
  const handleRollbackRomon = async () => {
    try {
      const res = await fetch(`/api/devices/${encodeURIComponent(deviceId)}/management/romon/rollback`, {
        method: "POST",
      });
      const json = await res.json();
      if (json.success) {
        pushToast?.("Konfigurasi RoMON berhasil di-rollback.", "info");
        setRomonPlanModalOpen(false);
        fetchManagementProfile();
      } else {
        pushToast?.(json.message || "Gagal melakukan rollback RoMON.", "error");
      }
    } catch {
      pushToast?.("Error rollback RoMON.", "error");
    }
  };

  // WebSocket Live Subscription & Fallback Polling
  useEffect(() => {
    unmountedRef.current = false;

    function connectWs() {
      if (unmountedRef.current) return;
      try {
        const ws = new WebSocket(buildNmsWsUrl());
        wsRef.current = ws;

        ws.onopen = () => {
          if (!unmountedRef.current) setWsStatus("open");
        };

        ws.onmessage = (event) => {
          if (unmountedRef.current) return;
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === "nms_device_status" && msg.data?.device_id === deviceId) {
              const u = msg.data;
              setDevice((prev) => {
                if (!prev) return prev;
                return {
                  ...prev,
                  profile: {
                    ...prev.profile,
                    status: u.status,
                    latency_ms: u.latency_ms,
                    freshness_state: u.freshness_state || prev.profile?.freshness_state,
                    freshness_reason: u.freshness_reason || prev.profile?.freshness_reason,
                    metrics_summary: u.metrics || prev.profile?.metrics_summary,
                    last_check_at: u.timestamp,
                    last_polled_at: u.timestamp,
                  },
                };
              });
            }
          } catch {}
        };

        ws.onerror = () => {
          if (!unmountedRef.current) setWsStatus("closed");
        };

        ws.onclose = () => {
          if (!unmountedRef.current) setWsStatus("closed");
        };
      } catch {
        if (!unmountedRef.current) setWsStatus("closed");
      }
    }

    connectWs();
    fetchDetail();

    // Fallback polling timer (15s if ws open, 5s if ws closed)
    const pollInterval = wsStatus === "open" ? 20000 : 8000;
    const timer = setInterval(() => {
      fetchDetail();
    }, pollInterval);

    return () => {
      unmountedRef.current = true;
      clearInterval(timer);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [deviceId, wsStatus]);

  useEffect(() => {
    fetchResHistory();
    const timer = setInterval(fetchResHistory, 10000);
    return () => clearInterval(timer);
  }, [deviceId, timeRange]);

  useEffect(() => {
    if (selectedIface) {
      fetchIfaceHistory(selectedIface);
      const timer = setInterval(() => fetchIfaceHistory(selectedIface), 10000);
      return () => clearInterval(timer);
    }
  }, [deviceId, selectedIface, timeRange]);

  useEffect(() => {
    if (activeTab === "management") {
      fetchManagementProfile();
      fetchRomonNeighbors();
    }
  }, [activeTab, deviceId]);

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

  // Freshness styles
  const freshness = prof.freshness_state || "UNKNOWN";
  const freshnessColors = {
    LIVE: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
    DELAYED: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    STALE: "bg-orange-500/20 text-orange-300 border-orange-500/40",
    UNAVAILABLE: "bg-rose-500/20 text-rose-300 border-rose-500/40",
    UNKNOWN: "bg-slate-500/20 text-slate-300 border-slate-500/40",
  }[freshness] || "bg-slate-500/20 text-slate-300 border-slate-500/40";

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

                {/* Freshness Badge */}
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold flex items-center gap-1 cursor-help ${freshnessColors}`}
                  title={prof.freshness_reason || `Telemetry Freshness: ${freshness}`}
                >
                  <Activity size={10} />
                  <span>{freshness}</span>
                </span>

                {/* WebSocket Real-time Status Badge */}
                <span
                  className={`text-[9px] px-2 py-0.5 rounded-full border font-mono ${
                    wsStatus === "open"
                      ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                      : wsStatus === "connecting"
                      ? "bg-amber-500/10 text-amber-300 border-amber-500/30 animate-pulse"
                      : "bg-white/5 text-white/50 border-white/10"
                  }`}
                  title="Status koneksi WebSocket push telemetri"
                >
                  {wsStatus === "open" ? "WS LIVE" : wsStatus === "connecting" ? "WS SYNC" : "POLLING"}
                </span>

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
              { id: "management", label: "Multi-Path Management", icon: Waypoints },
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
                      <line x1="0" y1="30" x2="500" y2="30" stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
                      <line x1="0" y1="60" x2="500" y2="60" stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
                      <line x1="0" y1="90" x2="500" y2="90" stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />

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

          {/* TAB 3: MULTI-PATH MANAGEMENT */}
          {activeTab === "management" && (
            <div className="space-y-6 text-xs">
              {loadingMgmt && !mgmtProfile ? (
                <div className="p-8 text-center text-cyan-400 flex items-center justify-center gap-2">
                  <Loader2 size={16} className="animate-spin" />
                  <span>Memeriksa kapabilitas multi-path perangkat...</span>
                </div>
              ) : mgmtProfile ? (
                <>
                  {/* Active Path Overview Card */}
                  <div className="p-4 rounded-xl bg-gradient-to-r from-cyan-950/30 to-purple-950/20 border border-cyan-500/20 space-y-3">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Waypoints size={18} className="text-cyan-400" />
                        <div>
                          <span className="text-white/40 text-[11px] block">Active Management Channel:</span>
                          <span className="text-base font-bold text-cyan-300">
                            {METHOD_META[mgmtProfile.active_method]?.label || mgmtProfile.active_method?.toUpperCase()}
                          </span>
                        </div>
                      </div>

                      {/* Manual Override Selector */}
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] text-white/50">Override Jalur:</span>
                        <select
                          value={mgmtProfile.manual_override || ""}
                          onChange={(e) => handleSelectPath(e.target.value)}
                          className="bg-black/40 border border-white/20 text-white text-xs rounded-lg px-2.5 py-1 outline-none focus:border-cyan-400"
                        >
                          <option value="">Auto-Select (Precedence Engine)</option>
                          <option value="ssh_ip">SSH over IP (TCP 22)</option>
                          <option value="api_ip">RouterOS API (TCP 8728)</option>
                          <option value="romon">RoMON Overlay (Multi-Hop)</option>
                          <option value="mac_telnet">MAC Telnet (Layer 2)</option>
                          <option value="mac_winbox">MAC WinBox (Layer 2)</option>
                        </select>
                      </div>
                    </div>

                    {/* Selection Rationale */}
                    <div className="p-2.5 rounded-lg bg-black/30 border border-white/5 text-[11px] text-white/70 flex items-start gap-2">
                      <Info size={14} className="text-cyan-400 shrink-0 mt-0.5" />
                      <div>
                        <span className="font-semibold text-white/90">Rationale Keputusan Jalur: </span>
                        <span>{mgmtProfile.selection_rationale}</span>
                      </div>
                    </div>
                  </div>

                  {/* Candidate Paths Evaluation Matrix */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-white text-xs flex items-center gap-1.5">
                        <Layers size={14} className="text-cyan-400" />
                        <span>Matriks Kapabilitas Jalur Manajemen</span>
                      </h3>
                      <button
                        onClick={fetchManagementProfile}
                        className="text-[11px] text-cyan-300 hover:text-cyan-200 flex items-center gap-1 transition"
                      >
                        <RefreshCw size={11} className={loadingMgmt ? "animate-spin" : ""} />
                        <span>Refresh Jalur</span>
                      </button>
                    </div>

                    <div className="rounded-xl border border-white/10 overflow-hidden text-xs">
                      <table className="w-full text-left">
                        <thead className="bg-white/5 text-white/50 text-[11px] border-b border-white/10">
                          <tr>
                            <th className="py-2 px-3">Metode Jalur</th>
                            <th className="py-2 px-3">Layer / Protocol</th>
                            <th className="py-2 px-3">Status Kelayakan</th>
                            <th className="py-2 px-3">Endpoint / Intermediary</th>
                            <th className="py-2 px-3 text-right">Latency</th>
                            <th className="py-2 px-3 text-center">Uji Konektivitas</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                          {mgmtProfile.candidate_paths?.map((p) => {
                            const isCurrent = p.method === mgmtProfile.active_method;
                            const isTestingThis = testingMethod === p.method;
                            const meta = METHOD_META[p.method] || { label: p.method, proto: "-", layer: "-" };
                            return (
                              <tr
                                key={p.method}
                                className={`hover:bg-white/[0.03] transition ${
                                  isCurrent ? "bg-cyan-500/10 font-medium" : ""
                                }`}
                              >
                                <td className="py-2.5 px-3">
                                  <div className="flex items-center gap-2">
                                    <span className="text-white font-semibold">{meta.label}</span>
                                    {isCurrent && (
                                      <span className="text-[9px] bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 px-1.5 py-0.5 rounded font-bold uppercase">
                                        Active
                                      </span>
                                    )}
                                  </div>
                                </td>
                                <td className="py-2.5 px-3 text-white/60 font-mono text-[11px]">
                                  {meta.layer} ({meta.proto})
                                </td>
                                <td className="py-2.5 px-3">
                                  <div className="space-y-0.5">
                                    <span
                                      className={`text-[10px] px-2 py-0.5 rounded font-semibold inline-block ${
                                        p.status === "available"
                                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                                          : p.status === "unreachable"
                                          ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                                          : p.status === "unsupported"
                                          ? "bg-slate-500/20 text-slate-300 border border-slate-500/40"
                                          : "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                                      }`}
                                    >
                                      {p.status?.toUpperCase()}
                                    </span>
                                    {p.rejection_reason && (
                                      <p className="text-[10px] text-white/40 leading-tight">
                                        {p.rejection_reason}
                                      </p>
                                    )}
                                  </div>
                                </td>
                                <td className="py-2.5 px-3 text-white/70 font-mono text-[11px]">
                                  {p.target_endpoint || "-"}
                                  {p.intermediary_device_id && (
                                    <span className="block text-[10px] text-cyan-300/80">
                                      Via Intermediary: {p.intermediary_device_id} (hop: {p.hop_count})
                                    </span>
                                  )}
                                </td>
                                <td className="py-2.5 px-3 text-right font-mono text-cyan-300">
                                  {p.latency_ms != null ? `${p.latency_ms.toFixed(1)} ms` : "-"}
                                </td>
                                <td className="py-2.5 px-3 text-center">
                                  <button
                                    onClick={() => handleTestPath(p.method)}
                                    disabled={isTestingThis}
                                    className="px-2.5 py-1 rounded bg-white/10 hover:bg-white/20 text-white text-[11px] font-medium transition inline-flex items-center gap-1"
                                  >
                                    {isTestingThis ? (
                                      <>
                                        <Loader2 size={11} className="animate-spin text-cyan-300" />
                                        <span>Menguji...</span>
                                      </>
                                    ) : (
                                      <>
                                        <Zap size={11} className="text-cyan-300" />
                                        <span>Test Jalur</span>
                                      </>
                                    )}
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* RoMON Overlay & Discovery Section */}
                  <div className="p-4 rounded-xl bg-white/[0.02] border border-white/10 space-y-4">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-white/5 pb-3">
                      <div>
                        <h4 className="font-semibold text-white text-xs flex items-center gap-1.5">
                          <Radio size={14} className="text-pink-400" />
                          <span>MikroTik RoMON (Router Management Overlay Network)</span>
                        </h4>
                        <p className="text-[11px] text-white/50 mt-0.5">
                          Manajemen multi-hop independen IP melalui jaringan RouterOS RoMON neighbor discovery.
                        </p>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={handleDiscoverRomon}
                          disabled={loadingRomon}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-pink-500/10 hover:bg-pink-500/20 border border-pink-500/30 text-pink-300 text-[11px] transition"
                        >
                          <RefreshCw size={11} className={loadingRomon ? "animate-spin" : ""} />
                          <span>Discover RoMON</span>
                        </button>

                        <button
                          onClick={handleOpenRomonPlan}
                          className="flex items-center gap-1 px-3 py-1 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-300 text-[11px] font-semibold transition"
                        >
                          <ShieldCheck size={12} />
                          <span>Provision RoMON</span>
                        </button>
                      </div>
                    </div>

                    {/* RoMON Neighbors Table */}
                    {romonNeighbors.length > 0 ? (
                      <div className="rounded-lg border border-white/10 overflow-hidden text-xs">
                        <table className="w-full text-left">
                          <thead className="bg-white/5 text-white/50 text-[10px] border-b border-white/10">
                            <tr>
                              <th className="py-2 px-3">Identity Perangkat</th>
                              <th className="py-2 px-3">RoMON ID / MAC</th>
                              <th className="py-2 px-3 text-center">Hop Count</th>
                              <th className="py-2 px-3">Path / Via</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-white/5">
                            {romonNeighbors.map((nb, idx) => (
                              <tr key={idx} className="hover:bg-white/[0.02]">
                                <td className="py-2 px-3 font-semibold text-white">
                                  {nb.identity || "MikroTik Node"}
                                </td>
                                <td className="py-2 px-3 font-mono text-cyan-300 text-[11px]">
                                  {nb.romon_id || nb.mac_address || "-"}
                                </td>
                                <td className="py-2 px-3 text-center font-mono">
                                  <span className="px-1.5 py-0.5 rounded bg-white/10 text-white font-bold text-[10px]">
                                    {nb.hop_count ?? 1}
                                  </span>
                                </td>
                                <td className="py-2 px-3 text-white/60 text-[11px]">
                                  {nb.path || `Via ${nb.discovered_via_device_id || "Intermediary Router"}`}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="p-4 rounded-lg bg-black/20 text-center text-white/40 text-[11px]">
                        Belum ada neighbor RoMON yang terdeteksi untuk perangkat ini. Klik &quot;Discover RoMON&quot; untuk memindai via intermediary router.
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="p-8 text-center text-white/40">
                  Data multi-path management belum tersedia untuk perangkat ini.
                </div>
              )}
            </div>
          )}

          {/* TAB 4: INCIDENTS */}
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

          {/* TAB 5: PROFILE */}
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

      {/* Controlled RoMON Provisioning Modal Dialog */}
      {romonPlanModalOpen && romonPlan && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in">
          <div className="relative w-full max-w-2xl bg-[#0f172a] border border-cyan-500/30 rounded-2xl shadow-2xl overflow-hidden text-white flex flex-col max-h-[90vh]">
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-cyan-950/30">
              <div className="flex items-center gap-2.5">
                <ShieldCheck size={20} className="text-cyan-400" />
                <div>
                  <h3 className="font-semibold text-sm">Review Provisioning Terkendali RoMON</h3>
                  <span className="text-[11px] text-white/50">Target Perangkat: {device.name} ({device.ip})</span>
                </div>
              </div>
              <button
                onClick={() => setRomonPlanModalOpen(false)}
                className="p-1 rounded text-white/40 hover:text-white hover:bg-white/10"
              >
                <X size={16} />
              </button>
            </div>

            <div className="p-6 space-y-4 overflow-y-auto text-xs">
              {/* Security Guardrails Banner */}
              <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-200 space-y-1">
                <span className="font-semibold flex items-center gap-1.5 text-amber-300">
                  <Lock size={13} />
                  <span>Protokol Keamanan &amp; Restriksi Antarmuka WAN:</span>
                </span>
                <p className="text-[11px] leading-relaxed text-amber-200/90">
                  Untuk mencegah eksposur overlay ke publik, seluruh interface WAN akan ditandai dengan{" "}
                  <code className="bg-black/40 px-1 py-0.5 rounded font-mono text-amber-300">forbid=yes</code>.
                  Secret RoMON disamarkan secara otomatis. Jika verifikasi konektivitas pasca-eksekusi gagal, sistem akan melakukan auto-rollback instan.
                </p>
              </div>

              {/* Planned Commands Review */}
              <div>
                <span className="text-white/60 font-medium block mb-1.5 flex items-center gap-1.5">
                  <Terminal size={13} className="text-cyan-400" />
                  <span>RouterOS CLI Plan Commands (Audit Pre-Execution):</span>
                </span>
                <div className="p-3.5 rounded-xl bg-black/60 border border-white/10 font-mono text-[11px] space-y-1.5 text-cyan-300">
                  {romonPlan.commands?.map((cmd, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <span className="text-white/30 select-none">$</span>
                      <span>{cmd}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Admin Explicit Approval Checkbox */}
              <label className="flex items-start gap-3 p-3.5 rounded-xl bg-white/[0.02] border border-white/10 cursor-pointer hover:bg-white/[0.04] transition">
                <input
                  type="checkbox"
                  checked={romonApproved}
                  onChange={(e) => setRomonApproved(e.target.checked)}
                  className="mt-0.5 rounded border-white/20 text-cyan-500 focus:ring-0 focus:outline-none"
                />
                <span className="text-[11px] text-white/80 leading-relaxed">
                  <span className="font-semibold text-white block">Persetujuan Administrator Wajib (2-Stage Approval):</span>
                  Saya telah meninjau command plan di atas dan mengizinkan VERA mengaktifkan RoMON pada perangkat ini dengan restriksi interface WAN serta auto-rollback safeguard.
                </span>
              </label>
            </div>

            <div className="flex items-center justify-between px-6 py-4 border-t border-white/10 bg-white/[0.01]">
              <button
                onClick={handleRollbackRomon}
                className="px-3 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 text-xs font-medium transition flex items-center gap-1.5"
              >
                <RotateCcw size={13} />
                <span>Rollback RoMON</span>
              </button>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setRomonPlanModalOpen(false)}
                  className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-xs transition"
                >
                  Batal
                </button>

                <button
                  onClick={handleApplyRomonPlan}
                  disabled={!romonApproved || romonApplying}
                  className="px-4 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 disabled:opacity-40 disabled:cursor-not-allowed text-black font-semibold text-xs transition flex items-center gap-1.5"
                >
                  {romonApplying ? (
                    <>
                      <Loader2 size={13} className="animate-spin" />
                      <span>Menerapkan Plan...</span>
                    </>
                  ) : (
                    <>
                      <Check size={13} />
                      <span>Setujui &amp; Terapkan Plan</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
