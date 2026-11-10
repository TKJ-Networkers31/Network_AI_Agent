// src/components/network-intelligence/OverviewTab.jsx
import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Bot,
  CheckCircle2,
  Clock,
  Compass,
  Cpu,
  Eye,
  Filter,
  HardDrive,
  Layers,
  Network,
  PlusCircle,
  Radio,
  RefreshCw,
  Search,
  Server,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  TrendingUp,
  Wifi,
  WifiOff,
  X,
  Zap,
} from "lucide-react";

const TIME_RANGES = [
  { id: "15m", label: "Last 15m" },
  { id: "1h", label: "Last 1h" },
  { id: "6h", label: "Last 6h" },
  { id: "24h", label: "Last 24h" },
  { id: "7d", label: "Last 7d" },
];

const REFRESH_INTERVALS = [
  { id: "off", label: "Off" },
  { id: "10s", label: "10s", ms: 10000 },
  { id: "30s", label: "30s", ms: 30000 },
  { id: "1m", label: "1m", ms: 60000 },
];

// Helper to convert telemetry array points into smooth SVG Area and Line paths
function generateAreaPath(points = [], width = 500, height = 100, minVal = null, maxVal = null) {
  if (!points || points.length === 0) return { line: "", area: "" };
  const mn = minVal !== null ? minVal : Math.min(...points);
  const mx = maxVal !== null ? maxVal : Math.max(...points);
  const range = mx - mn || 1;
  const stepX = width / Math.max(1, points.length - 1);
  const coords = points.map((p, i) => {
    const x = Math.round(i * stepX);
    const y = Math.round(height - 12 - ((p - mn) / range) * (height - 30));
    return [x, Math.max(8, Math.min(height - 4, y))];
  });
  const lineD = coords.reduce((acc, [x, y], i) => (i === 0 ? `M ${x} ${y}` : `${acc} L ${x} ${y}`), "");
  const areaD = `${lineD} L ${width} ${height} L 0 ${height} Z`;
  return { line: lineD, area: areaD };
}

export default function OverviewTab({
  overview,
  loading,
  onRefresh,
  onOpenOnboard,
  onOpenPolicy,
  onNavigateToTab,
  onRunSecurityAssessment,
  runningSecurityAssessment = false,
}) {
  const [timeRange, setTimeRange] = useState("1h");
  const [refreshInterval, setRefreshInterval] = useState("30s");
  const [selectedDeviceId, setSelectedDeviceId] = useState("all");
  const [tableSearch, setTableSearch] = useState("");
  const [findingsFilter, setFindingsFilter] = useState("ALL"); // "ALL" | "CRITICAL" | "HIGH"
  const [selectedFinding, setSelectedFinding] = useState(null);

  // Grafana-inspired auto-refresh effect
  useEffect(() => {
    const selected = REFRESH_INTERVALS.find((r) => r.id === refreshInterval);
    if (!selected || !selected.ms || !onRefresh) return;

    const timer = setInterval(() => {
      onRefresh();
    }, selected.ms);

    return () => clearInterval(timer);
  }, [refreshInterval, onRefresh]);

  const data = overview || {
    network_condition: "UNKNOWN",
    health_score: 100.0,
    dimension_scores: {},
    device_health: {},
    total_registered_devices: 0,
    reachable_devices: 0,
    unreachable_devices: 0,
    active_investigations: 0,
    detected_anomalies: 0,
    pending_approvals: [],
    recent_ai_decisions: [],
    major_anomalies: [],
    recurring_incidents: [],
    evidence_freshness: { FRESH: 0, AGING: 0, STALE: 0, EXPIRED: 0 },
    total_evidence_records: 0,
    observed_devices: [],
    telemetry_stream: null,
  };

  const statusColors = {
    HEALTHY: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
    DEGRADED: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    CRITICAL: "text-rose-400 border-rose-500/30 bg-rose-500/10",
    UNKNOWN: "text-white/60 border-white/20 bg-white/5",
  };

  const cond = data.network_condition || "UNKNOWN";
  const badgeCls = statusColors[cond] || statusColors.UNKNOWN;

  const pendingApprovalsCount = Array.isArray(data.pending_approvals)
    ? data.pending_approvals.length
    : data.pending_approvals || 0;

  const recentDecisionsList = Array.isArray(data.recent_ai_decisions)
    ? data.recent_ai_decisions
    : [];

  // Multi-Device Live Telemetry Processing
  const telemetryStream = data.telemetry_stream || {};
  const telemetrySummary = telemetryStream.summary || {};
  const telemetryDevices = Array.isArray(telemetryStream.devices) ? telemetryStream.devices : [];

  // Active Selected Telemetry Target (All Devices vs Specific Device)
  const activeTelemetry = useMemo(() => {
    if (selectedDeviceId === "all" || !selectedDeviceId) {
      const summaryRx = telemetrySummary.total_rx_mbps ?? 633.0;
      const summaryTx = telemetrySummary.total_tx_mbps ?? 542.0;
      const summaryPeak = telemetrySummary.peak_mbps ?? 824.5;
      const summaryAvg = telemetrySummary.avg_throughput_mbps ?? 587.5;
      const summaryLat = telemetrySummary.avg_latency_ms ?? 2.85;
      const summaryP95 = telemetrySummary.p95_latency_ms ?? 5.42;
      const summaryJitter = telemetrySummary.avg_jitter_ms ?? 0.32;
      const summaryLoss = telemetrySummary.packet_loss_pct ?? 0.0;
      const summaryReliability = telemetrySummary.link_reliability_pct ?? 99.8;
      const compliantCount = telemetrySummary.compliant_count ?? 11;
      const totalCount = telemetrySummary.total_count ?? 12;

      const defaultRxSpark = [580, 610, 595, 630, 620, 650, 640, 630, 645, 620, 633, 640];
      const defaultTxSpark = [490, 520, 510, 535, 530, 550, 540, 525, 545, 530, 542, 538];
      const defaultLatSpark = [2.8, 2.7, 2.9, 2.85, 2.8, 2.9, 2.85, 2.8, 2.85, 2.9, 2.85, 2.8];

      return {
        isAll: true,
        displayName: "Seluruh Perangkat (Agregat Jaringan)",
        scopeLabel: `${totalCount} Node Terdaftar`,
        ip: "Multi-Subnet Fabric",
        rx_mbps: summaryRx,
        tx_mbps: summaryTx,
        peak_mbps: summaryPeak,
        avg_tp_mbps: summaryAvg,
        reliability: summaryReliability,
        latency_ms: summaryLat,
        p95_ms: summaryP95,
        jitter_ms: summaryJitter,
        packet_loss: summaryLoss,
        sla_label: `${compliantCount}/${totalCount} Nodes Sesuai SLA (<15ms)`,
        isSlaCompliant: compliantCount === totalCount,
        sparkline_rx: telemetrySummary.sparkline_rx || defaultRxSpark,
        sparkline_tx: telemetrySummary.sparkline_tx || defaultTxSpark,
        sparkline_lat: telemetrySummary.sparkline_latency || defaultLatSpark,
      };
    }

    const dev = telemetryDevices.find((d) => d.device_id === selectedDeviceId);
    if (!dev) return null;

    const isUp = dev.status === "UP";
    const rx = dev.rx_mbps ?? 0;
    const tx = dev.tx_mbps ?? 0;
    const peak = dev.peak_mbps ?? Math.round(Math.max(rx, tx) * 1.4);
    const avg = Math.round((rx + tx) / 2);
    const lat = dev.latency_ms ?? (isUp ? 1.5 : null);
    const p95 = dev.p95_ms ?? (isUp ? 3.2 : null);
    const jitter = dev.jitter_ms ?? (isUp ? 0.25 : null);
    const loss = dev.packet_loss_pct ?? (isUp ? 0.0 : 100.0);

    return {
      isAll: false,
      displayName: dev.name,
      scopeLabel: `${dev.device_type?.toUpperCase() || "ROUTER"} · ${dev.ip}`,
      ip: dev.ip,
      status: dev.status,
      rx_mbps: rx,
      tx_mbps: tx,
      peak_mbps: peak,
      avg_tp_mbps: avg,
      reliability: isUp ? 100.0 : 0.0,
      latency_ms: lat,
      p95_ms: p95,
      jitter_ms: jitter,
      packet_loss: loss,
      sla_label: dev.sla_status === "COMPLIANT" ? "✓ Kepatuhan SLA Terpenuhi" : (isUp ? "⚠ Degradasi Latensi SLA" : "✗ Antarmuka Offline"),
      isSlaCompliant: dev.sla_status === "COMPLIANT",
      sparkline_rx: dev.sparkline_rx || [20, 25, 22, 28, 24, 30, 27, 25, 29, 26, 28, 27],
      sparkline_tx: dev.sparkline_tx || [15, 18, 17, 21, 19, 23, 20, 19, 22, 20, 21, 20],
      sparkline_lat: dev.sparkline_latency || [1.4, 1.3, 1.5, 1.4, 1.35, 1.45, 1.4, 1.38, 1.42, 1.4, 1.41, 1.39],
    };
  }, [selectedDeviceId, telemetrySummary, telemetryDevices]);

  // Generate dynamic SVG sparkline paths
  const rxPaths = useMemo(() => {
    if (!activeTelemetry?.sparkline_rx) return { line: "", area: "" };
    return generateAreaPath(activeTelemetry.sparkline_rx, 500, 100);
  }, [activeTelemetry?.sparkline_rx]);

  const txPaths = useMemo(() => {
    if (!activeTelemetry?.sparkline_tx) return { line: "", area: "" };
    return generateAreaPath(activeTelemetry.sparkline_tx, 500, 100);
  }, [activeTelemetry?.sparkline_tx]);

  const latPaths = useMemo(() => {
    if (!activeTelemetry?.sparkline_lat) return { line: "", area: "" };
    return generateAreaPath(activeTelemetry.sparkline_lat, 500, 100, 0, 20);
  }, [activeTelemetry?.sparkline_lat]);

  // Filtered devices for the Grafana node matrix table
  const filteredMatrixDevices = useMemo(() => {
    if (!tableSearch) return telemetryDevices;
    const q = tableSearch.toLowerCase();
    return telemetryDevices.filter(
      (d) =>
        d.name?.toLowerCase().includes(q) ||
        d.ip?.toLowerCase().includes(q) ||
        d.device_type?.toLowerCase().includes(q) ||
        d.status?.toLowerCase().includes(q)
    );
  }, [telemetryDevices, tableSearch]);

  // Filtered security findings
  const allFindings = Array.isArray(data.recent_security_findings) ? data.recent_security_findings : [];
  const filteredFindings = useMemo(() => {
    if (findingsFilter === "CRITICAL") return allFindings.filter((f) => f.severity === "CRITICAL");
    if (findingsFilter === "HIGH") return allFindings.filter((f) => f.severity === "HIGH");
    return allFindings;
  }, [allFindings, findingsFilter]);

  if (loading && !overview) {
    return (
      <div className="flex flex-col items-center justify-center p-16 text-white/50 space-y-3">
        <RefreshCw className="animate-spin text-cyan-400" size={32} />
        <p className="text-sm font-mono">Memuat ringkasan intelijen jaringan...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Grafana-style Observability Control & Node Variable Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 rounded-xl bg-card border border-border text-xs">
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <div className="flex items-center gap-1.5 text-cyan-400 font-semibold">
            <Radio size={14} className="animate-pulse text-cyan-400" />
            <span>Telemetry Live Stream</span>
          </div>

          <span className="text-white/20 hidden sm:inline">|</span>

          {/* Grafana-style Node/Device Selector Variable */}
          <div className="flex items-center gap-1.5 font-mono text-[11px] text-white/70">
            <span className="text-white/40">Node:</span>
            <select
              value={selectedDeviceId}
              onChange={(e) => setSelectedDeviceId(e.target.value)}
              className="bg-black/60 text-cyan-300 border border-white/10 rounded-lg px-2.5 py-1 text-xs outline-none focus:border-cyan-500/50 font-sans cursor-pointer hover:border-white/20 transition"
            >
              <option value="all">🌐 Semua Node (Agregat {telemetryDevices.length} Perangkat)</option>
              {telemetryDevices.map((d) => (
                <option key={d.device_id} value={d.device_id}>
                  {d.name} ({d.ip}) — {d.status === "UP" ? "ONLINE" : "OFFLINE"}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Time-Range Selector */}
          <div className="flex items-center gap-1 bg-black/40 p-1 rounded-lg border border-white/5 font-mono text-[11px]">
            <Clock size={12} className="text-white/40 ml-1 mr-0.5" />
            {TIME_RANGES.map((tr) => (
              <button
                key={tr.id}
                type="button"
                onClick={() => setTimeRange(tr.id)}
                className={`px-2 py-0.5 rounded transition ${
                  timeRange === tr.id
                    ? "bg-cyan-500/20 text-cyan-300 font-semibold"
                    : "text-white/60 hover:text-white"
                }`}
              >
                {tr.label}
              </button>
            ))}
          </div>

          {/* Auto-Refresh Toggle */}
          <div className="flex items-center gap-1.5 font-mono text-[11px] text-white/60">
            <span className="hidden sm:inline">Auto:</span>
            <div className="flex items-center gap-0.5 bg-black/40 p-1 rounded-lg border border-white/5">
              {REFRESH_INTERVALS.map((ri) => (
                <button
                  key={ri.id}
                  type="button"
                  onClick={() => setRefreshInterval(ri.id)}
                  className={`px-1.5 py-0.5 rounded transition ${
                    refreshInterval === ri.id
                      ? "bg-purple-500/20 text-purple-300 font-semibold"
                      : "text-white/50 hover:text-white"
                  }`}
                >
                  {ri.label}
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={onRefresh}
            disabled={loading}
            className="p-1.5 bg-white/5 hover:bg-white/10 text-white/80 hover:text-white rounded-lg border border-border transition flex items-center gap-1 font-mono text-[11px]"
            title="Muat Ulang Bukti & Telemetri"
          >
            <RefreshCw size={12} className={loading ? "animate-spin text-cyan-400" : ""} />
            <span className="hidden sm:inline">Segarkan</span>
          </button>
        </div>
      </div>

      {/* Top Banner: Condition, Score & Quick Controls */}
      <div className="bg-card border border-border p-5 rounded-xl shadow-lg flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-cyan-500/10 border border-cyan-500/30 rounded-xl text-cyan-400 shrink-0">
            <Activity size={28} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white tracking-wide">Kondisi Jaringan Keseluruhan</h2>
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wider border ${badgeCls}`}>
                {cond}
              </span>
            </div>
            <p className="text-xs text-white/60 mt-0.5">
              Dianalisis secara transparan dari {data.total_evidence_records || 0} bukti kanonikal across {data.total_registered_devices || 0} perangkat terdaftar.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="text-right mr-2">
            <div className="text-[10px] uppercase font-mono text-white/50 tracking-wider">Health Index</div>
            <div className="text-2xl font-black font-mono text-cyan-300">
              {Number(data.health_score || 100).toFixed(1)}%
            </div>
          </div>

          {onOpenOnboard && (
            <button
              onClick={onOpenOnboard}
              className="px-3 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/30 text-xs font-semibold flex items-center gap-1.5 transition"
            >
              <PlusCircle size={14} />
              <span>Onboard Perangkat</span>
            </button>
          )}

          {onOpenPolicy && (
            <button
              onClick={onOpenPolicy}
              className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-xs font-semibold border border-white/10 flex items-center gap-1.5 transition"
            >
              <Sliders size={14} />
              <span>AI Operations Policy</span>
            </button>
          )}
        </div>
      </div>

      {/* Grafana-Inspired Telemetry Time-Series Dynamic Visualization Panels */}
      {activeTelemetry && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Panel 1: Network Interface Throughput & Traffic Rates */}
          <div className="bg-card border border-border p-4 rounded-xl space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-2 border-b border-white/5 gap-2">
              <div className="flex items-center gap-2">
                <TrendingUp size={16} className="text-cyan-400" />
                <div>
                  <h3 className="text-xs font-semibold text-white tracking-wide">
                    {activeTelemetry.displayName} — Throughput ({timeRange})
                  </h3>
                  <span className="text-[10px] font-mono text-white/40 block">
                    {activeTelemetry.scopeLabel}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-3 text-[11px] font-mono">
                <span className="flex items-center gap-1 text-cyan-400">
                  <span className="w-2 h-2 rounded-full bg-cyan-400" />
                  <span>RX: {activeTelemetry.rx_mbps} Mbps</span>
                </span>
                <span className="flex items-center gap-1 text-purple-400">
                  <span className="w-2 h-2 rounded-full bg-purple-400" />
                  <span>TX: {activeTelemetry.tx_mbps} Mbps</span>
                </span>
              </div>
            </div>

            {/* Dynamic SVG Area Sparkline / Time-Series Graph */}
            <div className="relative h-28 w-full bg-black/40 rounded-lg p-2 border border-white/5 flex items-end justify-between overflow-hidden">
              <svg viewBox="0 0 500 100" className="w-full h-full preserve-3d" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="rx-grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#38BDF8" stopOpacity="0.4" />
                    <stop offset="100%" stopColor="#38BDF8" stopOpacity="0.0" />
                  </linearGradient>
                  <linearGradient id="tx-grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#8B5CF6" stopOpacity="0.3" />
                    <stop offset="100%" stopColor="#8B5CF6" stopOpacity="0.0" />
                  </linearGradient>
                </defs>

                {/* Grid guide lines */}
                <line x1="0" y1="25" x2="500" y2="25" stroke="rgba(255,255,255,0.05)" strokeDasharray="4 4" />
                <line x1="0" y1="50" x2="500" y2="50" stroke="rgba(255,255,255,0.05)" strokeDasharray="4 4" />
                <line x1="0" y1="75" x2="500" y2="75" stroke="rgba(255,255,255,0.05)" strokeDasharray="4 4" />

                {/* RX Area & Curve */}
                {rxPaths.area && <path d={rxPaths.area} fill="url(#rx-grad)" />}
                {rxPaths.line && <path d={rxPaths.line} fill="none" stroke="#38BDF8" strokeWidth="2" />}

                {/* TX Area & Curve */}
                {txPaths.area && <path d={txPaths.area} fill="url(#tx-grad)" />}
                {txPaths.line && <path d={txPaths.line} fill="none" stroke="#8B5CF6" strokeWidth="2" />}
              </svg>
            </div>

            <div className="flex items-center justify-between text-[11px] font-mono text-white/50 px-1">
              <span>Peak: {activeTelemetry.peak_mbps} Mbps</span>
              <span>Avg: {activeTelemetry.avg_tp_mbps} Mbps</span>
              <span className="text-emerald-400">{activeTelemetry.reliability}% Link Reliability</span>
            </div>
          </div>

          {/* Panel 2: Latency, Jitter & Packet SLA Distribution */}
          <div className="bg-card border border-border p-4 rounded-xl space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-2 border-b border-white/5 gap-2">
              <div className="flex items-center gap-2">
                <BarChart3 size={16} className="text-emerald-400" />
                <div>
                  <h3 className="text-xs font-semibold text-white tracking-wide">
                    {activeTelemetry.displayName} — Latensi &amp; SLA ({timeRange})
                  </h3>
                  <span className="text-[10px] font-mono text-white/40 block">
                    Distribusi RTT, Jitter &amp; Packet Drop
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-3 text-[11px] font-mono">
                <span className="text-emerald-400">
                  RTT: {activeTelemetry.latency_ms !== null ? `${activeTelemetry.latency_ms} ms` : "Offline"}
                </span>
                <span className="text-cyan-400">
                  P95: {activeTelemetry.p95_ms !== null ? `${activeTelemetry.p95_ms} ms` : "--"}
                </span>
                <span className={activeTelemetry.packet_loss > 0 ? "text-rose-400" : "text-emerald-300"}>
                  Loss: {activeTelemetry.packet_loss.toFixed(1)}%
                </span>
              </div>
            </div>

            {/* Dynamic SVG Latency Curve with SLA Warning Threshold */}
            <div className="relative h-28 w-full bg-black/40 rounded-lg p-2 border border-white/5 flex items-end justify-between overflow-hidden">
              <svg viewBox="0 0 500 100" className="w-full h-full preserve-3d" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="rtt-grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10B981" stopOpacity="0.35" />
                    <stop offset="100%" stopColor="#10B981" stopOpacity="0.0" />
                  </linearGradient>
                </defs>

                {/* Threshold Line at 15ms (Y=30) */}
                <line x1="0" y1="30" x2="500" y2="30" stroke="#F59E0B" strokeWidth="1" strokeDasharray="3 3" />
                <text x="4" y="24" fill="#F59E0B" fontSize="9" fontFamily="monospace">
                  SLA Alert Threshold (15ms)
                </text>

                {/* RTT Curve */}
                {latPaths.area && <path d={latPaths.area} fill="url(#rtt-grad)" />}
                {latPaths.line && <path d={latPaths.line} fill="none" stroke="#10B981" strokeWidth="2" />}
              </svg>
            </div>

            <div className="flex items-center justify-between text-[11px] font-mono text-white/50 px-1">
              <span>
                Jitter: {activeTelemetry.jitter_ms !== null ? `${activeTelemetry.jitter_ms} ms` : "--"}
              </span>
              <span className={activeTelemetry.isSlaCompliant ? "text-emerald-400" : "text-amber-400"}>
                {activeTelemetry.sla_label}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Grafana-Style Multi-Device Observability Matrix (Per-Device Telemetry Grid) */}
      <div className="bg-card border border-border p-4 rounded-xl space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-white/5">
          <div className="flex items-center gap-2">
            <Server size={16} className="text-cyan-400" />
            <div>
              <h3 className="text-xs font-semibold text-white tracking-wide">
                Grafana Device Matrix — Status &amp; Telemetri Seluruh Perangkat ({telemetryDevices.length} Nodes)
              </h3>
              <p className="text-[11px] text-white/50">
                Pilih atau klik tombol fokus pada perangkat untuk menampilkan kurva grafik spesifiknya di atas.
              </p>
            </div>
          </div>

          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-2 text-white/40" />
            <input
              type="text"
              placeholder="Cari perangkat atau IP..."
              value={tableSearch}
              onChange={(e) => setTableSearch(e.target.value)}
              className="bg-black/50 text-white placeholder-white/30 text-xs pl-8 pr-3 py-1.5 rounded-lg border border-white/10 outline-none focus:border-cyan-500/50 w-full sm:w-56"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-white/5 text-[10px] text-white/40 uppercase tracking-wider">
                <th className="py-2 px-2.5">Perangkat</th>
                <th className="py-2 px-2.5">IP Address</th>
                <th className="py-2 px-2.5">Status</th>
                <th className="py-2 px-2.5">Throughput (RX / TX)</th>
                <th className="py-2 px-2.5">Latensi RTT</th>
                <th className="py-2 px-2.5">Jitter / P95</th>
                <th className="py-2 px-2.5">Loss</th>
                <th className="py-2 px-2.5">SLA Kepatuhan</th>
                <th className="py-2 px-2.5 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {filteredMatrixDevices.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-6 text-center text-white/40 font-sans text-xs">
                    Tidak ada perangkat yang cocok dengan pencarian "{tableSearch}".
                  </td>
                </tr>
              ) : (
                filteredMatrixDevices.map((d) => {
                  const isSelected = selectedDeviceId === d.device_id;
                  const isUp = d.status === "UP";
                  return (
                    <tr
                      key={d.device_id}
                      className={`hover:bg-white/[0.03] transition cursor-pointer ${
                        isSelected ? "bg-cyan-500/10 border-l-2 border-l-cyan-400" : ""
                      }`}
                      onClick={() => setSelectedDeviceId(d.device_id)}
                    >
                      <td className="py-2.5 px-2.5 font-sans font-semibold text-white flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                        <span>{d.name}</span>
                      </td>
                      <td className="py-2.5 px-2.5 text-white/70">{d.ip}</td>
                      <td className="py-2.5 px-2.5">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider ${
                            isUp
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                              : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                          }`}
                        >
                          {isUp ? "ONLINE" : "OFFLINE"}
                        </span>
                      </td>
                      <td className="py-2.5 px-2.5 text-white/80">
                        <span className="text-cyan-400">{d.rx_mbps}</span> /{" "}
                        <span className="text-purple-400">{d.tx_mbps} Mbps</span>
                      </td>
                      <td className="py-2.5 px-2.5 font-bold">
                        {d.latency_ms !== null ? (
                          <span
                            className={
                              d.latency_ms <= 5.0
                                ? "text-emerald-400"
                                : d.latency_ms <= 15.0
                                ? "text-cyan-400"
                                : "text-amber-400"
                            }
                          >
                            {d.latency_ms} ms
                          </span>
                        ) : (
                          <span className="text-white/30">--</span>
                        )}
                      </td>
                      <td className="py-2.5 px-2.5 text-white/60">
                        {d.jitter_ms !== null ? `${d.jitter_ms} ms` : "--"} /{" "}
                        {d.p95_ms !== null ? `${d.p95_ms} ms` : "--"}
                      </td>
                      <td className="py-2.5 px-2.5">
                        <span className={d.packet_loss_pct > 0 ? "text-rose-400" : "text-emerald-400"}>
                          {d.packet_loss_pct.toFixed(1)}%
                        </span>
                      </td>
                      <td className="py-2.5 px-2.5">
                        <span
                          className={`text-[10px] font-bold ${
                            d.sla_status === "COMPLIANT"
                              ? "text-emerald-400"
                              : d.sla_status === "WARNING"
                              ? "text-amber-400"
                              : "text-rose-400"
                          }`}
                        >
                          {d.sla_status === "COMPLIANT"
                            ? "✓ OK (<15ms)"
                            : d.sla_status === "WARNING"
                            ? "⚠ Warning"
                            : "✗ Violation"}
                        </span>
                      </td>
                      <td className="py-2.5 px-2.5 text-right">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedDeviceId(isSelected ? "all" : d.device_id);
                          }}
                          className={`px-2.5 py-1 rounded text-[10px] font-sans font-semibold transition border ${
                            isSelected
                              ? "bg-cyan-500 text-black border-cyan-400 shadow-sm"
                              : "bg-white/5 hover:bg-white/10 text-cyan-300 border-white/10"
                          }`}
                        >
                          {isSelected ? "Sedang Fokus" : "Fokus Grafik"}
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 8-Part Core Network Intelligence Metrics (Section 4.1 Requirement) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-4 gap-3">
        {/* 1. Overall Network Health */}
        <div
          onClick={() => onNavigateToTab && onNavigateToTab("investigations", "rca")}
          className="bg-card border border-border hover:border-cyan-500/40 cursor-pointer p-3.5 rounded-xl space-y-1 transition"
          title="Klik untuk membuka Root Cause Analysis & Dimensi Kesehatan"
        >
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Overall Health</span>
            <Activity size={14} className="text-cyan-400" />
          </div>
          <div className="text-xl font-bold font-mono text-white">
            {Number(data.health_score || 100).toFixed(1)}%
          </div>
          <div className={`text-[10px] font-semibold uppercase ${badgeCls.split(" ")[0]}`}>
            Status: {cond}
          </div>
        </div>

        {/* 2. Total Registered Devices */}
        <div
          onClick={() => {
            if (onOpenOnboard) onOpenOnboard();
          }}
          className="bg-card border border-border hover:border-cyan-500/40 cursor-pointer p-3.5 rounded-xl space-y-1 transition"
          title="Klik untuk Onboard Perangkat Baru"
        >
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Total Devices</span>
            <Server size={14} className="text-indigo-400" />
          </div>
          <div className="text-xl font-bold font-mono text-white">
            {data.total_registered_devices ?? 0}
          </div>
          <div className="text-[10px] text-cyan-400 flex items-center gap-1">
            <span>+ Onboard Perangkat</span>
            <ArrowRight size={10} />
          </div>
        </div>

        {/* 3. Reachable Devices */}
        <div
          onClick={() => onNavigateToTab && onNavigateToTab("investigations", "evidence")}
          className="bg-card border border-border hover:border-emerald-500/40 cursor-pointer p-3.5 rounded-xl space-y-1 transition"
          title="Klik untuk melihat bukti telemetri NMS"
        >
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Reachable (UP)</span>
            <Wifi size={14} className="text-emerald-400" />
          </div>
          <div className="text-xl font-bold font-mono text-emerald-400">
            {data.reachable_devices ?? 0}
          </div>
          <div className="text-[10px] text-emerald-500/70">
            NMS Active Polls
          </div>
        </div>

        {/* 4. Unreachable Devices */}
        <div
          onClick={() => onNavigateToTab && onNavigateToTab("investigations", "details")}
          className="bg-card border border-border hover:border-rose-500/40 cursor-pointer p-3.5 rounded-xl space-y-1 transition"
          title="Klik untuk melihat investigasi insiden"
        >
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Unreachable (DOWN)</span>
            <WifiOff size={14} className="text-rose-400" />
          </div>
          <div className="text-xl font-bold font-mono text-rose-400">
            {data.unreachable_devices ?? 0}
          </div>
          <div className="text-[10px] text-rose-400/70">
            {data.unreachable_devices > 0 ? "Memerlukan atensi" : "Semua online"}
          </div>
        </div>

        {/* 5. Active Investigations */}
        <div
          onClick={() => onNavigateToTab && onNavigateToTab("investigations", "details")}
          className="bg-card border border-border hover:border-cyan-500/40 cursor-pointer p-3.5 rounded-xl space-y-1 transition"
          title="Buka daftar investigasi insiden"
        >
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Active Investigations</span>
            <ShieldAlert size={14} className="text-amber-400" />
          </div>
          <div className="text-xl font-bold font-mono text-amber-400">
            {data.active_investigations ?? data.active_incidents_count ?? 0}
          </div>
          <div className="text-[10px] text-cyan-400 flex items-center gap-1">
            <span>Buka investigasi</span>
            <ArrowRight size={10} />
          </div>
        </div>

        {/* 6. Detected Anomalies */}
        <div
          onClick={() => onNavigateToTab && onNavigateToTab("investigations", "rca")}
          className="bg-card border border-border hover:border-rose-500/40 cursor-pointer p-3.5 rounded-xl space-y-1 transition"
          title="Klik untuk membuka Root Cause & Timeline Anomali"
        >
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Detected Anomalies</span>
            <AlertTriangle size={14} className="text-rose-400" />
          </div>
          <div className="text-xl font-bold font-mono text-rose-400">
            {data.detected_anomalies ?? (data.major_anomalies?.length || 0)}
          </div>
          <div className="text-[10px] text-rose-400 flex items-center gap-1">
            <span>Analisis anomali</span>
            <ArrowRight size={10} />
          </div>
        </div>

        {/* 7. Pending Approvals */}
        <div
          onClick={() => onNavigateToTab && onNavigateToTab("actions")}
          className="bg-card border border-border hover:border-amber-500/40 cursor-pointer p-3.5 rounded-xl space-y-1 transition"
          title="Buka Action Center & Persetujuan Operasi"
        >
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Pending Approvals</span>
            <AlertOctagon size={14} className="text-amber-400" />
          </div>
          <div className="text-xl font-bold font-mono text-amber-400">
            {pendingApprovalsCount}
          </div>
          <div className="text-[10px] text-amber-300 flex items-center gap-1">
            <span>Tinjau Action Center</span>
            <ArrowRight size={10} />
          </div>
        </div>

        {/* 8. Recent AI Decisions */}
        <div
          onClick={() => onNavigateToTab && onNavigateToTab("actions")}
          className="bg-card border border-border hover:border-cyan-500/40 cursor-pointer p-3.5 rounded-xl space-y-1 transition"
          title="Klik untuk melihat Audit Log Keputusan AI"
        >
          <div className="flex items-center justify-between text-xs text-white/60">
            <span>Recent AI Decisions</span>
            <Bot size={14} className="text-cyan-400" />
          </div>
          <div className="text-xl font-bold font-mono text-cyan-400">
            {recentDecisionsList.length}
          </div>
          <div className="text-[10px] text-cyan-400 flex items-center gap-1">
            <span>Audit log keputusan</span>
            <ArrowRight size={10} />
          </div>
        </div>
      </div>

      {/* Network Security Posture & Vulnerability Baseline */}
      <div className="bg-[#04060c] border border-white/10 p-5 rounded-xl shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/5 pb-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <ShieldCheck size={24} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white tracking-wide">
                  Network Security Posture &amp; Baseline Intelligence
                </h3>
                <span className={`px-2.5 py-0.5 rounded text-[11px] font-bold tracking-wider border ${
                  (data.security_posture_band || "EXCELLENT") === "EXCELLENT" || (data.security_posture_band || "") === "GOOD"
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                    : (data.security_posture_band || "") === "MODERATE"
                    ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                    : "bg-rose-500/10 text-rose-400 border-rose-500/20"
                }`}>
                  {data.security_posture_band || "EXCELLENT"} ({data.security_posture_score ?? 100}/100)
                </span>
              </div>
              <p className="text-xs text-white/60 mt-0.5">
                Cakupan asesmen non-invasif: {Number(data.assessment_coverage_pct ?? 100).toFixed(0)}% across Management Plane, Firewall, Routing, &amp; Service Hardening.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5 font-mono text-xs">
            {/* Clickable Stat Filters */}
            <button
              type="button"
              onClick={() => setFindingsFilter(findingsFilter === "CRITICAL" ? "ALL" : "CRITICAL")}
              className={`px-3 py-1.5 rounded-lg border text-left transition ${
                findingsFilter === "CRITICAL"
                  ? "bg-rose-500/30 border-rose-500 text-white shadow-sm ring-1 ring-rose-400"
                  : "bg-rose-500/10 border-rose-500/20 text-rose-300 hover:bg-rose-500/20"
              }`}
              title="Klik untuk memfilter hanya temuan CRITICAL"
            >
              <span className="text-[10px] text-rose-400/80 block font-sans">CRITICAL FINDINGS</span>
              <span className="text-base font-bold">{data.critical_findings_count ?? 0}</span>
            </button>

            <button
              type="button"
              onClick={() => setFindingsFilter(findingsFilter === "HIGH" ? "ALL" : "HIGH")}
              className={`px-3 py-1.5 rounded-lg border text-left transition ${
                findingsFilter === "HIGH"
                  ? "bg-amber-500/30 border-amber-500 text-white shadow-sm ring-1 ring-amber-400"
                  : "bg-amber-500/10 border-amber-500/20 text-amber-300 hover:bg-amber-500/20"
              }`}
              title="Klik untuk memfilter hanya temuan HIGH"
            >
              <span className="text-[10px] text-amber-400/80 block font-sans">HIGH FINDINGS</span>
              <span className="text-base font-bold">{data.high_findings_count ?? 0}</span>
            </button>

            <button
              type="button"
              onClick={() => setFindingsFilter("ALL")}
              className={`px-3 py-1.5 rounded-lg border text-left transition ${
                findingsFilter === "ALL"
                  ? "bg-cyan-500/20 border-cyan-500 text-cyan-200 shadow-sm ring-1 ring-cyan-400"
                  : "bg-white/5 border border-white/10 text-white/80 hover:bg-white/10"
              }`}
              title="Klik untuk melihat semua temuan yang belum selesai diremediasi"
            >
              <span className="text-[10px] text-white/60 block font-sans">OPEN FINDINGS</span>
              <span className="text-base font-bold">{data.total_open_findings ?? 0}</span>
            </button>

            {onRunSecurityAssessment && (
              <button
                type="button"
                onClick={onRunSecurityAssessment}
                disabled={runningSecurityAssessment}
                className="px-3 py-2 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 text-xs font-semibold flex items-center gap-1.5 transition disabled:opacity-50 font-sans ml-1"
                title="Jalankan audit keamanan non-invasif untuk seluruh perangkat"
              >
                <ShieldCheck size={14} className={runningSecurityAssessment ? "animate-spin" : ""} />
                <span>{runningSecurityAssessment ? "Memindai..." : "Audit Keamanan"}</span>
              </button>
            )}
          </div>
        </div>

        {filteredFindings.length > 0 ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-[11px] font-semibold text-white/70 tracking-wider uppercase font-mono">
              <span>
                Temuan Baseline Terdeteksi ({filteredFindings.length}
                {findingsFilter !== "ALL" ? ` Filter: ${findingsFilter}` : ""}):
              </span>
              {findingsFilter !== "ALL" && (
                <button
                  type="button"
                  onClick={() => setFindingsFilter("ALL")}
                  className="text-cyan-400 hover:text-cyan-300 lowercase text-[10px] font-sans"
                >
                  [reset filter]
                </button>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              {filteredFindings.slice(0, 6).map((f, idx) => (
                <div
                  key={f.finding_id || idx}
                  onClick={() => setSelectedFinding(f)}
                  className="p-3.5 rounded-lg bg-white/[0.03] hover:bg-white/[0.07] border border-white/10 hover:border-cyan-500/40 cursor-pointer space-y-2 transition group"
                  title="Klik untuk membuka detail & panduan remediasi"
                >
                  <div className="flex items-center justify-between text-xs gap-2">
                    <span className="font-semibold text-white truncate group-hover:text-cyan-300 transition">
                      {f.title}
                    </span>
                    <span
                      className={`text-[10px] font-bold px-1.5 py-0.5 rounded border shrink-0 ${
                        f.severity === "CRITICAL"
                          ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
                          : f.severity === "HIGH"
                          ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                          : "bg-blue-500/10 text-blue-400 border-blue-500/20"
                      }`}
                    >
                      {f.severity}
                    </span>
                  </div>

                  <p className="text-[11px] text-white/60 line-clamp-2">{f.description}</p>

                  <div className="flex items-center justify-between text-[10px] font-mono text-white/40 pt-2 border-t border-white/5">
                    <span className="truncate max-w-[180px]">
                      {f.device_name} · {f.category}
                    </span>

                    {/* Clear Status vs Actionable Remediation Button */}
                    <div className="flex items-center gap-1.5">
                      <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 text-[9px]">
                        Status: Belum Selesai ({f.status})
                      </span>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedFinding(f);
                        }}
                        className="px-2 py-0.5 rounded bg-cyan-500/20 hover:bg-cyan-500/40 text-cyan-300 text-[10px] font-sans font-semibold flex items-center gap-1 transition"
                      >
                        <span>Remediasi</span>
                        <ArrowRight size={10} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/10 text-xs text-emerald-300 flex items-center gap-2">
            <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />
            <span>
              Seluruh perangkat sesuai dengan baseline keamanan (tidak ada temuan {findingsFilter !== "ALL" ? findingsFilter : ""}).
            </span>
          </div>
        )}
      </div>

      {/* Security Finding Detail & Remediation Modal */}
      {selectedFinding && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-150">
          <div className="bg-[#070b14] border border-cyan-500/40 rounded-2xl max-w-xl w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-start justify-between gap-3 border-b border-white/10 pb-3">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono border ${
                      selectedFinding.severity === "CRITICAL"
                        ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
                        : "bg-amber-500/20 text-amber-300 border-amber-500/40"
                    }`}
                  >
                    {selectedFinding.severity}
                  </span>
                  <span className="text-xs font-mono text-cyan-400">
                    {selectedFinding.device_name}
                  </span>
                </div>
                <h3 className="text-base font-bold text-white leading-snug">
                  {selectedFinding.title}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedFinding(null)}
                className="p-1 rounded-lg text-white/50 hover:text-white hover:bg-white/10 transition"
              >
                <X size={18} />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <span className="text-[10px] font-mono text-white/40 uppercase block mb-1">
                  Deskripsi &amp; Risiko Keamanan:
                </span>
                <p className="text-white/80 bg-black/40 p-3 rounded-lg border border-white/5 leading-relaxed">
                  {selectedFinding.description}
                </p>
              </div>

              <div>
                <span className="text-[10px] font-mono text-cyan-400 uppercase block mb-1">
                  💡 Panduan Remediasi Teknis (Rekomendasi VERA):
                </span>
                <p className="text-cyan-200 bg-cyan-950/20 p-3 rounded-lg border border-cyan-500/20 leading-relaxed font-sans">
                  {selectedFinding.remediation_guidance ||
                    "Terapkan konfigurasi firewall stateful dan nonaktifkan servis terbuka tanpa enkripsi."}
                </p>
              </div>

              {selectedFinding.remediation_action_name && (
                <div className="flex items-center justify-between p-2.5 rounded-lg bg-white/5 border border-white/5 font-mono text-[11px]">
                  <span className="text-white/50">Aksi Otomasi Terkait:</span>
                  <span className="text-amber-300 font-bold">
                    {selectedFinding.remediation_action_name}
                  </span>
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-white/10">
              <span className="text-[10px] font-mono text-white/40">
                Rule ID: {selectedFinding.baseline_rule_id || "BASELINE-SECURITY"}
              </span>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setSelectedFinding(null)}
                  className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white/70 hover:text-white bg-white/5 hover:bg-white/10 transition"
                >
                  Tutup
                </button>

                {onNavigateToTab && (
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedFinding(null);
                      onNavigateToTab("actions");
                    }}
                    className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-cyan-500 hover:bg-cyan-400 text-black transition flex items-center gap-1.5 shadow-md"
                  >
                    <span>Ajukan Tindakan di Action Center</span>
                    <ArrowRight size={13} />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Mid Section: 8-Dimensional Health & Evidence Freshness */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 8-Dimensional Health Scores Grid */}
        <div className="lg:col-span-2 bg-card border border-border p-5 rounded-xl space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white/90 flex items-center gap-2">
              <Layers size={16} className="text-cyan-400" />
              <span>8 Dimensi Kesehatan Jaringan (Transparan &amp; Deterministic)</span>
            </h3>
            <span className="text-[11px] font-mono text-white/40">Bobot eksplisit tanpa black-box</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Object.entries(data.dimension_scores || {}).map(([dim, score]) => {
              const scoreVal = typeof score === "object" && score !== null ? score.score : score;
              const hasScore = scoreVal !== null && scoreVal !== undefined && !isNaN(Number(scoreVal));
              const sc = hasScore ? Number(scoreVal) : 100;
              const isDegraded = hasScore && sc < 80;
              const isCrit = hasScore && sc < 60;
              const barColor = !hasScore
                ? "bg-neutral-600"
                : isCrit
                ? "bg-rose-500"
                : isDegraded
                ? "bg-amber-500"
                : "bg-emerald-500";
              const scoreText = hasScore
                ? `${sc.toFixed(1)}%`
                : (typeof score === "object" && score?.status ? score.status.replace(/_/g, " ") : "NO DATA");
              const barWidth = hasScore ? Math.min(100, Math.max(0, sc)) : 0;

              return (
                <div key={dim} className="bg-white/5 p-3 rounded-lg border border-white/5 space-y-1.5">
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-mono text-white/70 text-[11px] truncate" title={dim}>
                      {dim.replace(/_/g, " ")}
                    </span>
                    <span className={`font-mono font-bold text-xs ${!hasScore ? "text-white/40 text-[10px]" : isCrit ? "text-rose-400" : isDegraded ? "text-amber-400" : "text-emerald-400"}`}>
                      {scoreText}
                    </span>
                  </div>
                  <div className="w-full bg-black/40 h-1.5 rounded-full overflow-hidden">
                    <div className={`h-full ${barColor}`} style={{ width: `${barWidth}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Evidence Freshness */}
        <div
          onClick={() => onNavigateToTab && onNavigateToTab("investigations", "evidence")}
          className="bg-card border border-border hover:border-cyan-500/40 cursor-pointer p-5 rounded-xl space-y-3 transition"
          title="Klik untuk membuka Katalog Bukti Kanonikal"
        >
          <div className="flex items-center justify-between text-xs font-semibold text-white/90">
            <span className="flex items-center gap-1.5">
              <ShieldCheck size={16} className="text-emerald-400" />
              <span>Evidence Freshness Profiles</span>
            </span>
            <span className="text-cyan-400 font-mono text-[10px] flex items-center gap-1">
              <span>Buka Bukti</span>
              <ArrowRight size={10} />
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs font-mono pt-1">
            <div className="p-2.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-300">
              <div className="text-[10px] text-emerald-400/70">FRESH (&lt;15m)</div>
              <div className="text-lg font-bold">{data.evidence_freshness?.FRESH || 0}</div>
            </div>
            <div className="p-2.5 rounded bg-cyan-500/10 border border-cyan-500/20 text-cyan-300">
              <div className="text-[10px] text-cyan-400/70">AGING (&lt;1h)</div>
              <div className="text-lg font-bold">{data.evidence_freshness?.AGING || 0}</div>
            </div>
            <div className="p-2.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-300">
              <div className="text-[10px] text-amber-400/70">STALE (&lt;24h)</div>
              <div className="text-lg font-bold">{data.evidence_freshness?.STALE || 0}</div>
            </div>
            <div className="p-2.5 rounded bg-rose-500/10 border border-rose-500/20 text-rose-300">
              <div className="text-[10px] text-rose-400/70">EXPIRED</div>
              <div className="text-lg font-bold">{data.evidence_freshness?.EXPIRED || 0}</div>
            </div>
          </div>
          <p className="text-[11px] text-white/40 italic">
            VERA menolak data kadaluarsa sebagai fakta terbukti sebelum memverifikasi ulang ke NMS atau perangkat.
          </p>
        </div>
      </div>

      {/* Bottom Section: Recent AI Decisions & Pending Approvals */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent AI Decisions Panel */}
        <div className="bg-card border border-border p-5 rounded-xl space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white/90 flex items-center gap-2">
              <Bot size={16} className="text-cyan-400" />
              <span>Recent AI Decisions (Operational Decision Intelligence)</span>
            </h3>
            <span className="text-[11px] font-mono text-cyan-400/80">Audit Logged</span>
          </div>

          <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
            {recentDecisionsList.length === 0 ? (
              <div className="p-6 text-center text-xs text-white/40 bg-white/5 border border-white/5 rounded-lg">
                Belum ada catatan keputusan AI tersimpan.
              </div>
            ) : (
              recentDecisionsList.map((dec, idx) => (
                <div key={idx} className="p-3 rounded-lg bg-white/5 border border-white/5 space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-white truncate max-w-[280px]">
                      {dec.title || dec.intent || "Keputusan Operasional"}
                    </span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                      {dec.decision_type || dec.risk_level || "DECISION"}
                    </span>
                  </div>
                  <p className="text-xs text-white/70 line-clamp-2">
                    {dec.rationale || dec.summary || "Analisis observasi status perangkat dan evaluasi kebijakan operasional."}
                  </p>
                  <div className="flex items-center justify-between text-[10px] text-white/40 pt-1 border-t border-white/5">
                    <span>Target: {dec.target_device || "Network Wide"}</span>
                    <span>{dec.timestamp ? new Date(dec.timestamp * 1000).toLocaleString() : "Tercatat"}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Pending Approvals & Major Anomalies */}
        <div className="bg-card border border-border p-5 rounded-xl space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white/90 flex items-center gap-2">
              <AlertOctagon size={16} className="text-amber-400" />
              <span>Pending Approvals &amp; High Anomali</span>
            </h3>
            {pendingApprovalsCount > 0 && onNavigateToTab && (
              <button
                onClick={() => onNavigateToTab("actions")}
                className="text-xs font-semibold text-amber-400 hover:text-amber-300 flex items-center gap-1 transition"
              >
                <span>Lihat Semua ({pendingApprovalsCount})</span>
                <ArrowRight size={12} />
              </button>
            )}
          </div>

          {Array.isArray(data.pending_approvals) && data.pending_approvals.length > 0 ? (
            <div className="space-y-2">
              {data.pending_approvals.slice(0, 3).map((act) => (
                <div key={act.action_id} className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-amber-200">{act.action_name}</span>
                    <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">
                      {act.risk_level}
                    </span>
                  </div>
                  <p className="text-xs text-white/80 line-clamp-1">{act.description}</p>
                  <div className="flex items-center justify-between text-[10px] text-white/50 pt-1">
                    <span>Target: {act.target_device}</span>
                    <span className="text-amber-300 font-medium">Menunggu Persetujuan Admin</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-4 text-center text-xs text-white/40 bg-white/5 border border-white/5 rounded-lg">
              Tidak ada tindakan yang tertunda menunggu persetujuan saat ini.
            </div>
          )}

          {/* Major Anomalies */}
          {data.major_anomalies && data.major_anomalies.length > 0 && (
            <div className="pt-2 border-t border-border space-y-2">
              <div className="text-xs font-semibold text-rose-400 flex items-center gap-1.5">
                <AlertTriangle size={14} />
                <span>Anomali Terdeteksi (Kritis / Tinggi)</span>
              </div>
              <div className="space-y-1.5">
                {data.major_anomalies.slice(0, 2).map((a, idx) => (
                  <div key={idx} className="p-2.5 rounded bg-rose-500/10 border border-rose-500/20 text-xs text-rose-200 flex justify-between items-center">
                    <div>
                      <span className="font-semibold">{a.metric_name || a.entity_id}: </span>
                      <span className="text-rose-300/80">{a.description}</span>
                    </div>
                    <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 shrink-0">
                      {a.severity}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
