// src/pages/NmsPage.jsx
//
// Halaman Utama Network Management System (NMS) AIRA OS
// Terinspirasi dari The Dude & LibreNMS: Pemantauan ketersediaan kontinu,
// telemetri performa RouterOS/SNMP, laju bandwidth antarmuka, dan manajemen insiden terpusat.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

function buildNmsWsUrl() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const isDev = window.location.port === "5173";
  const host = isDev ? `${window.location.hostname}:8000` : window.location.host;
  return `${proto}//${host}/ws/nms`;
}
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  Clock,
  Cpu,
  Eye,
  Filter,
  HardDrive,
  Loader2,
  Network,
  Pause,
  Play,
  RefreshCw,
  Search,
  Server,
  Settings as SettingsIcon,
  Shield,
  ShieldCheck,
  Wrench,
  Zap,
} from "lucide-react";
import TopBar from "../components/TopBar.jsx";
import { useToast } from "../components/Toast.jsx";
import SnmpSetupWizardModal from "../components/nms/SnmpSetupWizardModal.jsx";
import DeviceDetailModal from "../components/nms/DeviceDetailModal.jsx";

const STATUS_FILTERS = [
  { id: "all", label: "Semua Status" },
  { id: "UP", label: "UP (Normal)" },
  { id: "DEGRADED", label: "Degraded" },
  { id: "SUSPECTED_DOWN", label: "Suspected Down" },
  { id: "DOWN", label: "DOWN (Mati)" },
  { id: "MONITORING_UNAVAILABLE", label: "Monitoring Unavailable" },
  { id: "UNKNOWN", label: "Unknown" },
];

const MODE_FILTERS = [
  { id: "all", label: "Semua Mode" },
  { id: "managed", label: "Managed (SNMP)" },
  { id: "unmanaged", label: "Unmanaged (Ping)" },
];

export default function NmsPage({ onOpenMenu }) {
  const { notify } = useToast();

  const [activeTab, setActiveTab] = useState("inventory");
  const [overview, setOverview] = useState(null);
  const [devices, setDevices] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [pollingNow, setPollingNow] = useState(false);
  const [wsStatus, setWsStatus] = useState("connecting");

  // Filters with 300ms debounce on search
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [modeFilter, setModeFilter] = useState("all");

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  // Sorting
  const [sortField, setSortField] = useState("name");
  const [sortDir, setSortDir] = useState("asc");

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  };

  const sortedDevices = useMemo(() => {
    return [...devices].sort((a, b) => {
      let valA, valB;
      if (sortField === "name") {
        valA = (a.name || "").toLowerCase();
        valB = (b.name || "").toLowerCase();
      } else if (sortField === "status") {
        valA = a.status || "";
        valB = b.status || "";
      } else if (sortField === "latency") {
        valA = Number(a.latency_ms) || 0;
        valB = Number(b.latency_ms) || 0;
      } else if (sortField === "ip") {
        valA = a.ip || "";
        valB = b.ip || "";
      } else {
        return 0;
      }

      if (valA < valB) return sortDir === "asc" ? -1 : 1;
      if (valA > valB) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
  }, [devices, sortField, sortDir]);

  // Modals
  const [wizardDevice, setWizardDevice] = useState(null);
  const [detailDeviceId, setDetailDeviceId] = useState(null);

  // Form Settings State
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingForm, setSettingForm] = useState({
    auto_monitoring_enabled: true,
    default_interval_sec: 15,
    failure_threshold: 3,
    recovery_threshold: 2,
    history_retention_days: 7,
  });

  const pushToast = (message, type = "info") => {
    notify({ message, type });
  };

  // References for single-flight scheduling and unmount protection
  const abortDevicesRef = useRef(null);
  const inFlightRef = useRef(false);
  const scheduleTimerRef = useRef(null);
  const unmountedRef = useRef(false);
  const wsRef = useRef(null);
  const wsRetryRef = useRef(0);
  const wsReconnectTimerRef = useRef(null);

  const fetchOverview = useCallback(async () => {
    try {
      const res = await fetch("/api/nms/overview");
      const json = await res.json();
      if (json.success) setOverview(json.overview);
    } catch {}
  }, []);

  const fetchDevices = useCallback(async (signal) => {
    try {
      const params = new URLSearchParams();
      if (statusFilter !== "all") params.append("status", statusFilter);
      if (modeFilter !== "all") params.append("management_mode", modeFilter);
      if (debouncedSearch.trim()) params.append("search", debouncedSearch.trim());

      const res = await fetch(`/api/nms/devices?${params.toString()}`, { signal });
      const json = await res.json();
      if (json.success) setDevices(json.devices || []);
    } catch (err) {
      if (err.name !== "AbortError") {
        // Silently tolerate transient network hiccups
      }
    }
  }, [statusFilter, modeFilter, debouncedSearch]);

  const fetchIncidents = useCallback(async () => {
    try {
      const res = await fetch("/api/nms/incidents?status=all&limit=40");
      const json = await res.json();
      if (json.success) setIncidents(json.incidents || []);
    } catch {}
  }, []);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch("/api/nms/settings");
      const json = await res.json();
      if (json.success) {
        setSettings(json.settings);
        setSettingForm({
          auto_monitoring_enabled: json.settings.auto_monitoring_enabled,
          default_interval_sec: json.settings.default_interval_sec,
          failure_threshold: json.settings.failure_threshold,
          recovery_threshold: json.settings.recovery_threshold,
          history_retention_days: json.settings.history_retention_days,
        });
      }
    } catch {}
  }, []);

  // Filter change: cancel pending request and fetch immediately
  useEffect(() => {
    if (abortDevicesRef.current) abortDevicesRef.current.abort();
    const controller = new AbortController();
    abortDevicesRef.current = controller;
    fetchDevices(controller.signal);
  }, [fetchDevices]);

  // Single-flight recursive poll cycle (60s reconciliation with WS, 30s fallback without WS)
  const pollCycle = useCallback(async (isInitial = false) => {
    if (inFlightRef.current || unmountedRef.current) return;
    inFlightRef.current = true;
    if (!isInitial) setIsSyncing(true);

    try {
      if (!document.hidden || isInitial) {
        await Promise.allSettled([
          fetchOverview(),
          fetchDevices(),
          fetchIncidents(),
          isInitial ? fetchSettings() : Promise.resolve(),
        ]);
      }
    } finally {
      inFlightRef.current = false;
      if (!unmountedRef.current) {
        if (isInitial) setLoading(false);
        setIsSyncing(false);
        const nextInterval = wsStatus === "open" ? 60_000 : 30_000;
        clearTimeout(scheduleTimerRef.current);
        scheduleTimerRef.current = setTimeout(() => pollCycle(false), nextInterval);
      }
    }
  }, [fetchOverview, fetchDevices, fetchIncidents, fetchSettings, wsStatus]);

  // Initial load and tab visibility listener
  useEffect(() => {
    unmountedRef.current = false;
    pollCycle(true);

    function onVisibility() {
      if (!document.hidden && !unmountedRef.current) {
        clearTimeout(scheduleTimerRef.current);
        pollCycle(false);
      }
    }
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      unmountedRef.current = true;
      clearTimeout(scheduleTimerRef.current);
      document.removeEventListener("visibilitychange", onVisibility);
      if (abortDevicesRef.current) abortDevicesRef.current.abort();
    };
  }, [pollCycle]);

  // Hybrid Real-Time WebSocket Connection to /ws/nms
  useEffect(() => {
    function connectWs() {
      if (unmountedRef.current) return;
      const existing = wsRef.current;
      if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
        return;
      }
      setWsStatus("connecting");
      const ws = new WebSocket(buildNmsWsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        if (wsRef.current !== ws) return;
        wsRetryRef.current = 0;
        setWsStatus("open");
      };

      ws.onmessage = (event) => {
        if (wsRef.current !== ws) return;
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "nms_snapshot" || msg.type === "nms_cycle_completed") {
            if (msg.data?.overview) {
              setOverview(msg.data.overview);
            }
          } else if (msg.type === "nms_device_status") {
            const update = msg.data;
            if (!update || !update.device_id) return;
            // Normalized in-place delta update: avoid full-table rerenders
            setDevices((prev) => {
              const idx = prev.findIndex((d) => d.id === update.device_id);
              if (idx === -1) return prev;
              const dev = prev[idx];
              if (dev.status === update.status && dev.latency_ms === update.latency_ms) {
                return prev;
              }
              const next = [...prev];
              next[idx] = {
                ...dev,
                status: update.status,
                latency_ms: update.latency_ms,
                last_check_at: update.timestamp,
                last_polled_at: update.timestamp,
              };
              return next;
            });
          } else if (msg.type === "nms_incident") {
            fetchIncidents();
          }
        } catch {}
      };

      ws.onclose = () => {
        if (wsRef.current !== ws) return;
        setWsStatus("closed");
        if (unmountedRef.current) return;
        const delay = Math.min(1000 * 2 ** wsRetryRef.current + Math.random() * 500, 15000);
        wsRetryRef.current += 1;
        clearTimeout(wsReconnectTimerRef.current);
        wsReconnectTimerRef.current = setTimeout(connectWs, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connectWs();

    return () => {
      clearTimeout(wsReconnectTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onopen = null;
        wsRef.current.onmessage = null;
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        try { wsRef.current.close(); } catch {}
      }
    };
  }, [fetchIncidents]);

  const handlePollNow = async () => {
    setPollingNow(true);
    try {
      const res = await fetch("/api/nms/scheduler/poll-now", { method: "POST" });
      const json = await res.json();
      if (json.success) {
        pushToast("Siklus polling NMS dimulai di latar belakang.", "info");
        setTimeout(() => pollCycle(false), 2000);
      }
    } catch {
      pushToast("Gagal memicu polling NMS.", "error");
    } finally {
      setPollingNow(false);
    }
  };

  const handleToggleScheduler = async () => {
    if (!overview) return;
    const isRunning = overview.is_running;
    const endpoint = isRunning ? "/api/nms/scheduler/stop" : "/api/nms/scheduler/start";
    try {
      const res = await fetch(endpoint, { method: "POST" });
      const json = await res.json();
      if (json.success) {
        pushToast(
          isRunning ? "Monitoring NMS dihentikan." : "Monitoring NMS aktif berjalan.",
          "info"
        );
        fetchOverview();
      }
    } catch {
      pushToast("Gagal mengubah status scheduler.", "error");
    }
  };

  const handleSaveSettings = async (e) => {
    e.preventDefault();
    setSavingSettings(true);
    try {
      const res = await fetch("/api/nms/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settingForm),
      });
      const json = await res.json();
      if (json.success) {
        pushToast("Pengaturan NMS berhasil disimpan!", "success");
        fetchSettings();
        fetchOverview();
      }
    } catch {
      pushToast("Gagal menyimpan pengaturan NMS.", "error");
    } finally {
      setSavingSettings(false);
    }
  };

  const handleAcknowledgeIncident = async (incId) => {
    try {
      const res = await fetch(`/api/nms/incidents/${incId}/acknowledge`, { method: "POST" });
      const json = await res.json();
      if (json.success) {
        pushToast("Insiden berhasil diakui (acknowledged).", "success");
        fetchIncidents();
        fetchOverview();
      }
    } catch {
      pushToast("Gagal mengakui insiden.", "error");
    }
  };

  const formatBps = (bps) => {
    if (!bps || bps <= 0) return "0 bps";
    if (bps >= 1_000_000_000) return `${(bps / 1_000_000_000).toFixed(2)} Gbps`;
    if (bps >= 1_000_000) return `${(bps / 1_000_000).toFixed(2)} Mbps`;
    if (bps >= 1_000) return `${(bps / 1_000).toFixed(1)} kbps`;
    return `${Math.round(bps)} bps`;
  };

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 text-white">
      <TopBar
        title="Network Management System (NMS)"
        subtitle="Live Availability, SNMP Telemetry & Bandwidth Monitoring"
        wsStatus={wsStatus}
        onMenuClick={onOpenMenu}
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={handlePollNow}
              disabled={pollingNow}
              title="Polling status sekarang"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 text-cyan-300 text-xs font-medium transition disabled:opacity-50"
            >
              <RefreshCw size={13} className={pollingNow ? "animate-spin" : ""} />
              <span className="hidden sm:inline">Poll Now</span>
            </button>

            <button
              onClick={handleToggleScheduler}
              title={overview?.is_running ? "Hentikan Scheduler" : "Jalankan Scheduler"}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition ${
                overview?.is_running
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/20"
                  : "bg-amber-500/10 border-amber-500/30 text-amber-300 hover:bg-amber-500/20"
              }`}
            >
              {overview?.is_running ? <Pause size={13} /> : <Play size={13} />}
              <span className="hidden sm:inline">
                {overview?.is_running ? "Scheduler: Active" : "Scheduler: Paused"}
              </span>
            </button>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto space-y-6 pt-3 pb-8">
        {/* SECTION 1: OVERVIEW KPI CARDS */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3 text-xs">
          <div className="p-3 rounded-xl bg-white/[0.03] border border-white/10 space-y-1">
            <span className="text-white/40">Total Devices</span>
            <div className="text-xl font-bold text-white">{overview?.total_devices ?? 0}</div>
          </div>

          <div className="p-3 rounded-xl bg-emerald-950/20 border border-emerald-500/30 space-y-1">
            <span className="text-emerald-300 flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-400" /> UP (Normal)
            </span>
            <div className="text-xl font-bold text-emerald-400">{overview?.up ?? 0}</div>
          </div>

          <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-500/30 space-y-1">
            <span className="text-amber-300 flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-amber-400" /> Degraded
            </span>
            <div className="text-xl font-bold text-amber-400">{overview?.degraded ?? 0}</div>
          </div>

          <div className="p-3 rounded-xl bg-orange-950/20 border border-orange-500/30 space-y-1">
            <span className="text-orange-300 flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-orange-400" /> Suspected Down
            </span>
            <div className="text-xl font-bold text-orange-400">{overview?.suspected_down ?? 0}</div>
          </div>

          <div className="p-3 rounded-xl bg-red-950/20 border border-red-500/30 space-y-1">
            <span className="text-red-300 flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-red-400 animate-pulse" /> DOWN
            </span>
            <div className="text-xl font-bold text-red-400">{overview?.down ?? 0}</div>
          </div>

          <div className="p-3 rounded-xl bg-cyan-950/20 border border-cyan-500/30 space-y-1">
            <span className="text-cyan-300 flex items-center gap-1">
              <ShieldCheck size={13} /> Managed (SNMP)
            </span>
            <div className="text-xl font-bold text-cyan-400">{overview?.managed ?? 0}</div>
          </div>

          <div className="p-3 rounded-xl bg-purple-950/20 border border-purple-500/30 space-y-1">
            <span className="text-purple-300 flex items-center gap-1">
              <AlertCircle size={13} /> Active Alerts
            </span>
            <div className="text-xl font-bold text-purple-400">{overview?.active_incidents ?? 0}</div>
          </div>

          <div className="p-3 rounded-xl bg-slate-900/40 border border-slate-500/30 space-y-1">
            <span className="text-slate-300 flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-slate-400" /> Unknown / Unavail
            </span>
            <div className="text-xl font-bold text-slate-300">
              {(overview?.unknown ?? 0) + (overview?.monitoring_unavailable ?? 0)}
            </div>
          </div>
        </div>

        {/* SECTION 2: TABS NAVIGATION */}
        <div className="flex items-center gap-2 border-b border-white/10 pb-2 text-xs">
          {[
            { id: "inventory", label: "Device Inventory", icon: Server },
            { id: "incidents", label: `Alerts & Incidents (${incidents.filter((i) => i.status === "open").length})`, icon: AlertTriangle },
            { id: "settings", label: "Monitoring Settings", icon: SettingsIcon },
          ].map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg font-medium transition ${
                  activeTab === tab.id
                    ? "bg-cyan-500/20 border border-cyan-400/40 text-cyan-300"
                    : "text-white/50 hover:text-white hover:bg-white/5"
                }`}
              >
                <Icon size={14} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* TAB 1: DEVICE INVENTORY */}
        {activeTab === "inventory" && (
          <div className="space-y-4">
            {/* Filter Bar */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 text-xs">
              <div className="flex items-center gap-2 flex-1 max-w-md">
                <div className="relative w-full">
                  <Search size={14} className="absolute left-3 top-2.5 text-white/40" />
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Cari nama perangkat, IP, atau identitas..."
                    className="w-full pl-9 pr-3 py-2 rounded-xl bg-white/5 border border-white/10 text-white placeholder-white/40 focus:border-cyan-400 outline-none text-xs"
                  />
                </div>
              </div>

              <div className="flex items-center gap-2">
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-white text-xs outline-none focus:border-cyan-400"
                >
                  {STATUS_FILTERS.map((f) => (
                    <option key={f.id} value={f.id} className="bg-[#0b101b]">
                      {f.label}
                    </option>
                  ))}
                </select>

                <select
                  value={modeFilter}
                  onChange={(e) => setModeFilter(e.target.value)}
                  className="px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-white text-xs outline-none focus:border-cyan-400"
                >
                  {MODE_FILTERS.map((f) => (
                    <option key={f.id} value={f.id} className="bg-[#0b101b]">
                      {f.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Devices Table */}
            <div className="rounded-xl border border-white/10 overflow-hidden text-xs bg-white/[0.01]">
              <table className="w-full text-left">
                <thead className="bg-white/5 text-white/50 text-[11px] border-b border-white/10">
                  <tr>
                    <th className="py-3 px-4 font-medium cursor-pointer hover:text-white transition" onClick={() => handleSort("name")}>
                      <div className="flex items-center gap-1">
                        <span>Perangkat</span>
                        {sortField === "name" && (sortDir === "asc" ? <ArrowUp size={12} className="text-cyan-400" /> : <ArrowDown size={12} className="text-cyan-400" />)}
                      </div>
                    </th>
                    <th className="py-3 px-3 font-medium cursor-pointer hover:text-white transition" onClick={() => handleSort("ip")}>
                      <div className="flex items-center gap-1">
                        <span>IP Address</span>
                        {sortField === "ip" && (sortDir === "asc" ? <ArrowUp size={12} className="text-cyan-400" /> : <ArrowDown size={12} className="text-cyan-400" />)}
                      </div>
                    </th>
                    <th className="py-3 px-3 font-medium cursor-pointer hover:text-white transition" onClick={() => handleSort("status")}>
                      <div className="flex items-center gap-1">
                        <span>Status Ketersediaan</span>
                        {sortField === "status" && (sortDir === "asc" ? <ArrowUp size={12} className="text-cyan-400" /> : <ArrowDown size={12} className="text-cyan-400" />)}
                      </div>
                    </th>
                    <th className="py-3 px-3 font-medium">Mode Manajemen</th>
                    <th className="py-3 px-3 font-medium cursor-pointer hover:text-white transition" onClick={() => handleSort("latency")}>
                      <div className="flex items-center gap-1">
                        <span>Latency</span>
                        {sortField === "latency" && (sortDir === "asc" ? <ArrowUp size={12} className="text-cyan-400" /> : <ArrowDown size={12} className="text-cyan-400" />)}
                      </div>
                    </th>
                    <th className="py-3 px-3 font-medium">CPU / RAM</th>
                    <th className="py-3 px-3 font-medium">Terakhir Dicek</th>
                    <th className="py-3 px-4 font-medium text-right">Aksi</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {sortedDevices.map((dev) => {
                    const statusColors = {
                      UP: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
                      DEGRADED: "bg-amber-500/20 text-amber-300 border-amber-500/40",
                      SUSPECTED_DOWN: "bg-orange-500/20 text-orange-300 border-orange-500/40",
                      DOWN: "bg-red-500/20 text-red-300 border-red-500/40 animate-pulse",
                      MONITORING_UNAVAILABLE: "bg-purple-500/20 text-purple-300 border-purple-500/40",
                      UNKNOWN: "bg-slate-500/20 text-slate-300 border-slate-500/40",
                    }[dev.status] || "bg-white/10 text-white/60";

                    return (
                      <tr key={dev.id} className="hover:bg-white/[0.03] transition">
                        <td className="py-3 px-4 font-semibold text-white">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <button
                              onClick={() => setDetailDeviceId(dev.id)}
                              className="hover:text-cyan-400 hover:underline text-left font-semibold"
                            >
                              {dev.name}
                            </button>
                            {dev.name_source && (
                              <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/5 text-white/50 border border-white/10 uppercase tracking-wider font-mono">
                                {dev.name_source.replace("_", " ")}
                              </span>
                            )}
                          </div>
                          {dev.identity && dev.identity !== dev.name && (
                            <span className="text-[10px] text-white/50 block font-normal mt-0.5">
                              ID: {dev.identity}
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-3 font-mono text-white/70">{dev.ip || "-"}</td>
                        <td className="py-3 px-3">
                          <div className="flex items-center gap-1 flex-wrap">
                            <span className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold ${statusColors}`}>
                              {dev.status}
                            </span>
                            {dev.is_stale && (
                              <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-semibold" title="Data pemantauan belum diperbarui lebih dari 3x interval">
                                STALE
                              </span>
                            )}
                          </div>
                          {dev.consecutive_failures > 0 && (
                            <span className="text-[10px] text-red-400 block font-mono mt-0.5">
                              Gagal berturut-turut: {dev.consecutive_failures}x
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-3">
                          <span
                            className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                              dev.management_mode === "managed"
                                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                                : "bg-white/5 text-white/40 border border-white/10"
                            }`}
                          >
                            {dev.management_mode === "managed" ? "Managed" : "Unmanaged"}
                          </span>
                          <span className="text-[10px] text-white/40 block font-mono mt-0.5">
                            {dev.monitoring_method || "icmp_ping"}
                          </span>
                        </td>
                        <td className="py-3 px-3 font-mono text-cyan-300">
                          {dev.latency_ms > 0 ? `${dev.latency_ms.toFixed(1)} ms` : "-"}
                        </td>
                        <td className="py-3 px-3 text-white/70">
                          {dev.metrics_summary?.cpu_load_percent != null ? (
                            <span className="font-mono text-xs">
                              {dev.metrics_summary.cpu_load_percent}% / {dev.metrics_summary.memory_used_percent ?? "-"}%
                            </span>
                          ) : (
                            <span className="text-white/30">-</span>
                          )}
                        </td>
                        <td className="py-3 px-3 text-white/50 text-[11px]">
                          {dev.last_check_at || dev.last_polled_at
                            ? new Date((dev.last_check_at || dev.last_polled_at) * 1000).toLocaleString()
                            : "Belum dicek"}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => {
                                try {
                                  sessionStorage.setItem("aira_focus_topology_node", dev.id);
                                } catch {}
                                window.dispatchEvent(new CustomEvent("aira:navigate", { detail: "topology" }));
                              }}
                              title="Buka di Canvas Topologi"
                              className="flex items-center gap-1 px-2 py-1 rounded-lg bg-sky-500/10 hover:bg-sky-500/20 border border-sky-500/30 text-sky-300 text-[11px] font-medium transition"
                            >
                              <Network size={12} />
                              <span className="hidden xl:inline">Topologi</span>
                            </button>

                            <button
                              onClick={() => setDetailDeviceId(dev.id)}
                              title="Inspeksi Telemetri"
                              className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white/70 hover:text-white transition"
                            >
                              <Eye size={13} />
                            </button>

                            {dev.management_mode !== "managed" ? (
                              <button
                                onClick={() => setWizardDevice(dev)}
                                title="Setup SNMP Monitoring"
                                className="flex items-center gap-1 px-2 py-1 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-300 text-[11px] font-semibold transition"
                              >
                                <ShieldCheck size={13} />
                                <span>Setup SNMP</span>
                              </button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {devices.length === 0 && (
                    <tr>
                      <td colSpan={8} className="py-8 text-center text-white/40 text-xs">
                        Tidak ada perangkat yang sesuai dengan filter.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 2: INCIDENTS & ALERTS */}
        {activeTab === "incidents" && (
          <div className="space-y-4">
            <div className="rounded-xl border border-white/10 overflow-hidden text-xs bg-white/[0.01]">
              <table className="w-full text-left">
                <thead className="bg-white/5 text-white/50 text-[11px] border-b border-white/10">
                  <tr>
                    <th className="py-3 px-4 font-medium">Status</th>
                    <th className="py-3 px-3 font-medium">Waktu Kejadian</th>
                    <th className="py-3 px-3 font-medium">Perangkat</th>
                    <th className="py-3 px-4 font-medium">Insiden &amp; Rincian</th>
                    <th className="py-3 px-4 font-medium text-right">Tindakan</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {incidents.map((inc) => (
                    <tr
                      key={inc.id}
                      className={`hover:bg-white/[0.03] transition ${
                        inc.status === "open" ? "bg-red-950/10" : ""
                      }`}
                    >
                      <td className="py-3 px-4">
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase ${
                            inc.status === "open"
                              ? "bg-red-500/20 text-red-300 border border-red-500/30 animate-pulse"
                              : inc.status === "acknowledged"
                              ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                              : "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          }`}
                        >
                          {inc.status}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-white/50 text-[11px]">
                        {new Date(inc.started_at * 1000).toLocaleString("id-ID")}
                      </td>
                      <td className="py-3 px-3 font-semibold text-white">
                        {inc.device_name} ({inc.device_ip || "-"})
                      </td>
                      <td className="py-3 px-4 text-white/80">
                        <div className="font-semibold">{inc.title}</div>
                        <div className="text-[11px] text-white/60 whitespace-pre-line">{inc.details}</div>
                      </td>
                      <td className="py-3 px-4 text-right">
                        {inc.status === "open" && (
                          <button
                            onClick={() => handleAcknowledgeIncident(inc.id)}
                            className="px-2.5 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-300 text-[11px] font-semibold transition"
                          >
                            Acknowledge
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {incidents.length === 0 && (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-white/40 text-xs">
                        Tidak ada catatan insiden pemantauan saat ini.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 3: MONITORING SETTINGS */}
        {activeTab === "settings" && (
          <form onSubmit={handleSaveSettings} className="max-w-2xl space-y-4 text-xs">
            <div className="p-5 rounded-xl bg-white/[0.02] border border-white/10 space-y-4">
              <h3 className="text-sm font-semibold text-white">Konfigurasi Scheduler Pemantauan NMS</h3>
              <p className="text-white/50 text-[11px]">
                Mengatur frekuensi polling otomatis ketersediaan perangkat, batas toleransi kegagalan down-detection, dan retensi riwayat sampel.
              </p>

              <div className="space-y-4 pt-2">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settingForm.auto_monitoring_enabled}
                    onChange={(e) =>
                      setSettingForm((f) => ({ ...f, auto_monitoring_enabled: e.target.checked }))
                    }
                    className="w-4 h-4 rounded text-cyan-500 accent-cyan-500"
                  />
                  <div>
                    <span className="font-semibold block text-white">Aktifkan Auto-Monitoring di Latar Belakang</span>
                    <span className="text-[11px] text-white/50">
                      Scheduler berjalan secara mandiri di background server tanpa harus merefresh browser.
                    </span>
                  </div>
                </label>

                <div>
                  <label className="block text-white/60 mb-1.5 font-medium">
                    Interval Polling Ketersediaan (Detik)
                  </label>
                  <div className="flex items-center gap-2 mb-2">
                    {[5, 10, 15, 30, 60].map((sec) => (
                      <button
                        type="button"
                        key={sec}
                        onClick={() => setSettingForm((f) => ({ ...f, default_interval_sec: sec }))}
                        className={`px-3 py-1.5 rounded-lg border text-xs font-semibold transition ${
                          settingForm.default_interval_sec === sec
                            ? "bg-cyan-500 text-black border-cyan-400"
                            : "bg-white/5 border-white/10 text-white/70 hover:text-white"
                        }`}
                      >
                        {sec}s
                      </button>
                    ))}
                  </div>
                  <input
                    type="number"
                    min="5"
                    max="3600"
                    value={settingForm.default_interval_sec}
                    onChange={(e) =>
                      setSettingForm((f) => ({ ...f, default_interval_sec: Number(e.target.value) }))
                    }
                    className="w-full px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-white outline-none focus:border-cyan-400"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-white/60 mb-1 font-medium">Batas Kegagalan (DOWN Threshold)</label>
                    <input
                      type="number"
                      min="1"
                      max="10"
                      value={settingForm.failure_threshold}
                      onChange={(e) =>
                        setSettingForm((f) => ({ ...f, failure_threshold: Number(e.target.value) }))
                      }
                      className="w-full px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-white outline-none focus:border-cyan-400"
                    />
                    <span className="text-[10px] text-white/40 mt-1 block">
                      Jumlah kegagalan berturut-turut sebelum dinyatakan DOWN (mencegah false alarm).
                    </span>
                  </div>

                  <div>
                    <label className="block text-white/60 mb-1 font-medium">Batas Pemulihan (UP Threshold)</label>
                    <input
                      type="number"
                      min="1"
                      max="10"
                      value={settingForm.recovery_threshold}
                      onChange={(e) =>
                        setSettingForm((f) => ({ ...f, recovery_threshold: Number(e.target.value) }))
                      }
                      className="w-full px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-white outline-none focus:border-cyan-400"
                    />
                    <span className="text-[10px] text-white/40 mt-1 block">
                      Jumlah keberhasilan berturut-turut sebelum dinyatakan pulih (UP).
                    </span>
                  </div>
                </div>

                <div>
                  <label className="block text-white/60 mb-1 font-medium">Retensi Sampel Metrik (Hari)</label>
                  <input
                    type="number"
                    min="1"
                    max="90"
                    value={settingForm.history_retention_days}
                    onChange={(e) =>
                      setSettingForm((f) => ({ ...f, history_retention_days: Number(e.target.value) }))
                    }
                    className="w-full px-3 py-2 rounded-xl bg-white/5 border border-white/10 text-white outline-none focus:border-cyan-400"
                  />
                </div>
              </div>

              <div className="pt-3 border-t border-white/10">
                <button
                  type="submit"
                  disabled={savingSettings}
                  className="px-5 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-semibold text-xs transition shadow-lg shadow-cyan-500/20 disabled:opacity-50"
                >
                  {savingSettings ? "Menyimpan..." : "Simpan Pengaturan NMS"}
                </button>
              </div>
            </div>
          </form>
        )}
      </div>

      {/* MODAL 1: SNMP SETUP WIZARD */}
      {wizardDevice && (
        <SnmpSetupWizardModal
          device={wizardDevice}
          onClose={() => setWizardDevice(null)}
          onSuccess={() => {
            setWizardDevice(null);
            refreshAll();
          }}
          pushToast={pushToast}
        />
      )}

      {/* MODAL 2: DEVICE TELEMETRY DETAIL */}
      {detailDeviceId && (
        <DeviceDetailModal
          deviceId={detailDeviceId}
          onClose={() => setDetailDeviceId(null)}
          onOpenWizard={(dev) => setWizardDevice(dev)}
          pushToast={pushToast}
        />
      )}
    </div>
  );
}
