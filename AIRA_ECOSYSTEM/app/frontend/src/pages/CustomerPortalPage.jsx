// src/pages/CustomerPortalPage.jsx
// AIRA OS — Customer Self-Service Portal (Networking VIII / WP 8.9)
//
// Dedicated, tenant-scoped portal providing:
// - Operational Dashboard & Dynamic 6-Dimension Health Scoring
// - Sites and Network Devices Inventory (Read-Only, Redacted Credentials)
// - Customer-Facing Active Incident Tracker & Acknowledgement
// - Customer SLA Performance & Availability Reports
// - Support Requests & Customer Collaboration Desk
// - Organization User Management & Notification Preferences

import React, { useState, useEffect, useCallback } from "react";
import {
  Building,
  Server,
  Radio,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  Clock,
  LifeBuoy,
  Users,
  Bell,
  FileText,
  RefreshCw,
  Plus,
  Send,
  Lock,
  Search,
  ChevronRight,
  ShieldCheck,
  CheckSquare,
} from "lucide-react";

export default function CustomerPortalPage({ onOpenMenu }) {
  // Navigation tabs
  const [activeTab, setActiveTab] = useState("dashboard"); // dashboard | sites_devices | sla | incidents | support | users | settings
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Tenant & User Context
  const [tenantInfo, setTenantInfo] = useState(null);
  const [currentUser, setCurrentUser] = useState(null);

  // Data states
  const [overview, setOverview] = useState(null);
  const [healthBreakdown, setHealthBreakdown] = useState(null);
  const [sites, setSites] = useState([]);
  const [devices, setDevices] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [slaSummary, setSlaSummary] = useState(null);
  const [supportRequests, setSupportRequests] = useState([]);
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [ticketComments, setTicketComments] = useState([]);
  const [newComment, setNewComment] = useState("");
  const [tenantUsers, setTenantUsers] = useState([]);
  const [notifPrefs, setNotifPrefs] = useState(null);

  // New ticket form modal state
  const [showNewTicketModal, setShowNewTicketModal] = useState(false);
  const [ticketForm, setTicketForm] = useState({
    category: "SERVICE_REQUEST",
    priority: "MEDIUM",
    subject: "",
    description: "",
  });

  // Fetch Current User & Organization Context
  const fetchProfile = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/portal/auth/me");
      if (res.ok) {
        const data = await res.json();
        setCurrentUser(data);
        if (data.tenant) setTenantInfo(data.tenant);
      }
    } catch (err) {
      console.warn("Failed to fetch customer profile:", err);
    }
  }, []);

  // Fetch Overview Data
  const fetchOverview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [resOv, resHlth] = await Promise.all([
        fetch("/api/v1/portal/dashboard/overview"),
        fetch("/api/v1/portal/dashboard/health"),
      ]);
      if (resOv.ok) {
        const data = await resOv.json();
        setOverview(data);
      }
      if (resHlth.ok) {
        const data = await resHlth.json();
        setHealthBreakdown(data);
      }
    } catch (err) {
      setError("Gagal memuat ringkasan operasional portal.");
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch Inventory
  const fetchInventory = useCallback(async () => {
    try {
      const [resSites, resDevs] = await Promise.all([
        fetch("/api/v1/portal/sites"),
        fetch("/api/v1/portal/devices"),
      ]);
      if (resSites.ok) {
        const sData = await resSites.json();
        setSites(sData.sites || []);
      }
      if (resDevs.ok) {
        const dData = await resDevs.json();
        setDevices(dData.devices || []);
      }
    } catch (err) {
      console.warn("Inventory fetch error:", err);
    }
  }, []);

  // Fetch Incidents
  const fetchIncidents = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/portal/incidents");
      if (res.ok) {
        const data = await res.json();
        setIncidents(data.incidents || []);
      }
    } catch (err) {
      console.warn("Incidents fetch error:", err);
    }
  }, []);

  // Fetch SLA Summary
  const fetchSla = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/portal/sla/summary");
      if (res.ok) {
        const data = await res.json();
        setSlaSummary(data);
      }
    } catch (err) {
      console.warn("SLA fetch error:", err);
    }
  }, []);

  // Fetch Support Requests
  const fetchSupportRequests = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/portal/support/requests");
      if (res.ok) {
        const data = await res.json();
        setSupportRequests(data.requests || []);
      }
    } catch (err) {
      console.warn("Support requests fetch error:", err);
    }
  }, []);

  // Fetch Ticket Details & Comments
  const fetchTicketDetails = async (requestId) => {
    try {
      const res = await fetch(`/api/v1/portal/support/requests/${requestId}`);
      if (res.ok) {
        const data = await res.json();
        setSelectedTicket(data);
        setTicketComments(data.comments || []);
      }
    } catch (err) {
      console.warn("Failed to load ticket details:", err);
    }
  };

  // Fetch Users & Notification Prefs
  const fetchSettings = useCallback(async () => {
    try {
      const [resUsers, resPrefs] = await Promise.all([
        fetch("/api/v1/portal/users"),
        fetch("/api/v1/portal/notifications/preferences"),
      ]);
      if (resUsers.ok) {
        const uData = await resUsers.json();
        setTenantUsers(uData.users || []);
      }
      if (resPrefs.ok) {
        const pData = await resPrefs.json();
        setNotifPrefs(pData);
      }
    } catch (err) {
      console.warn("Settings fetch error:", err);
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchProfile();
    fetchOverview();
  }, [fetchProfile, fetchOverview]);

  // Tab switch effect
  useEffect(() => {
    if (activeTab === "sites_devices") fetchInventory();
    if (activeTab === "incidents") fetchIncidents();
    if (activeTab === "sla") fetchSla();
    if (activeTab === "support") fetchSupportRequests();
    if (activeTab === "users" || activeTab === "settings") fetchSettings();
  }, [activeTab, fetchInventory, fetchIncidents, fetchSla, fetchSupportRequests, fetchSettings]);

  // Handle Acknowledge Incident
  const handleAcknowledgeIncident = async (incidentId) => {
    try {
      const res = await fetch(`/api/v1/portal/incidents/${incidentId}/acknowledge`, {
        method: "POST",
      });
      if (res.ok) {
        fetchIncidents();
        fetchOverview();
      }
    } catch (err) {
      console.error("Acknowledge error:", err);
    }
  };

  // Submit New Support Ticket
  const handleSubmitTicket = async (e) => {
    e.preventDefault();
    if (!ticketForm.subject || !ticketForm.description) return;
    try {
      const res = await fetch("/api/v1/portal/support/requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ticketForm),
      });
      if (res.ok) {
        setShowNewTicketModal(false);
        setTicketForm({ category: "SERVICE_REQUEST", priority: "MEDIUM", subject: "", description: "" });
        fetchSupportRequests();
      }
    } catch (err) {
      console.error("Ticket submission failed:", err);
    }
  };

  // Post Comment on Support Ticket
  const handleAddComment = async (e) => {
    e.preventDefault();
    if (!newComment.trim() || !selectedTicket) return;
    try {
      const res = await fetch(`/api/v1/portal/support/requests/${selectedTicket.request_id}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: newComment }),
      });
      if (res.ok) {
        setNewComment("");
        fetchTicketDetails(selectedTicket.request_id);
      }
    } catch (err) {
      console.error("Comment failed:", err);
    }
  };

  // Toggle Notification Preference
  const handleTogglePref = async (key, val) => {
    try {
      const res = await fetch("/api/v1/portal/notifications/preferences", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: val }),
      });
      if (res.ok) {
        const updated = await res.json();
        setNotifPrefs(updated);
      }
    } catch (err) {
      console.error("Failed to update preference:", err);
    }
  };

  // Helper badge color
  const getHealthColor = (state) => {
    switch (state) {
      case "HEALTHY":
        return "text-emerald-400 bg-emerald-500/10 border-emerald-500/20";
      case "DEGRADED":
      case "WARNING":
        return "text-amber-400 bg-amber-500/10 border-amber-500/20";
      case "CRITICAL":
      case "BREACHED":
        return "text-rose-400 bg-rose-500/10 border-rose-500/20";
      default:
        return "text-neutral-400 bg-neutral-800 border-neutral-700";
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 text-neutral-200">
      {/* 1. Tenant Organization Header */}
      <header className="flex flex-wrap items-center justify-between gap-4 py-4 border-b border-neutral-800 mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400 shadow-sm">
            <Building className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-white tracking-tight">
                {tenantInfo ? tenantInfo.name : "Customer Self-Service Portal"}
              </h1>
              <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-cyan-950/60 text-cyan-300 border border-cyan-800/50">
                Customer View
              </span>
            </div>
            <p className="text-xs text-neutral-400">
              ID: {currentUser?.tenant_id || "Demo Tenant"} • Role: {currentUser?.roles?.[0] || "CUSTOMER_OPERATOR"} • Timezone: Asia/Jakarta
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              fetchOverview();
              if (activeTab === "sites_devices") fetchInventory();
              if (activeTab === "incidents") fetchIncidents();
              if (activeTab === "sla") fetchSla();
              if (activeTab === "support") fetchSupportRequests();
            }}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800/80 hover:bg-neutral-700 border border-neutral-700 text-xs font-medium text-neutral-300 transition-colors shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </header>

      {/* 2. Portal Subsystem Tabs */}
      <nav className="flex items-center gap-1.5 overflow-x-auto pb-2 mb-6 border-b border-neutral-800/60 text-xs font-medium scrollbar-thin">
        {[
          { id: "dashboard", label: "Ringkasan & Kesehatan", icon: ShieldCheck },
          { id: "sites_devices", label: "Lokasi & Perangkat", icon: Server },
          { id: "incidents", label: "Insiden Aktif", icon: ShieldAlert },
          { id: "sla", label: "SLA & Ketersediaan", icon: CheckSquare },
          { id: "support", label: "Support Desk", icon: LifeBuoy },
          { id: "users", label: "Manajemen Pengguna", icon: Users },
          { id: "settings", label: "Preferensi Notifikasi", icon: Bell },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-lg transition-all whitespace-nowrap ${
                isActive
                  ? "bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 font-semibold shadow-sm"
                  : "text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/50"
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </nav>

      {/* 3. Tab Contents */}
      <div className="flex-1 min-h-0 overflow-y-auto pr-1">
        {/* =================================================================== */}
        {/* TAB 1: DASHBOARD & HEALTH                                           */}
        {/* =================================================================== */}
        {activeTab === "dashboard" && (
          <div className="space-y-6">
            {/* Overview Metric Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Card 1: Registered Devices */}
              <div className="p-4 rounded-xl bg-neutral-900/60 border border-neutral-800 shadow-sm">
                <div className="flex items-center justify-between text-neutral-400 mb-2">
                  <span className="text-xs uppercase font-medium">Perangkat Terdaftar</span>
                  <Server className="w-4 h-4 text-cyan-400" />
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-bold text-white">
                    {overview?.inventory?.total_devices ?? "—"}
                  </span>
                  <span className="text-xs text-emerald-400 font-medium">
                    {overview?.inventory?.online_devices ?? 0} Aktif
                  </span>
                </div>
                <div className="mt-2 text-[11px] text-neutral-400">
                  {overview?.inventory?.offline_devices ?? 0} perangkat offline/unreachable
                </div>
              </div>

              {/* Card 2: Edge Gateways */}
              <div className="p-4 rounded-xl bg-neutral-900/60 border border-neutral-800 shadow-sm">
                <div className="flex items-center justify-between text-neutral-400 mb-2">
                  <span className="text-xs uppercase font-medium">Edge Gateway Liveness</span>
                  <Radio className="w-4 h-4 text-indigo-400" />
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-bold text-white">
                    {overview?.inventory?.online_gateways ?? 0} / {overview?.inventory?.total_gateways ?? 0}
                  </span>
                  <span className="text-xs text-emerald-400 font-medium">Heartbeat OK</span>
                </div>
                <div className="mt-2 text-[11px] text-neutral-400">
                  Koneksi TLS Edge Gateway ke Central NOC aman
                </div>
              </div>

              {/* Card 3: Active Incidents */}
              <div className="p-4 rounded-xl bg-neutral-900/60 border border-neutral-800 shadow-sm">
                <div className="flex items-center justify-between text-neutral-400 mb-2">
                  <span className="text-xs uppercase font-medium">Insiden Aktif</span>
                  <ShieldAlert className="w-4 h-4 text-rose-400" />
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-bold text-white">
                    {overview?.incidents?.active_count ?? 0}
                  </span>
                  <span className="text-xs text-rose-400 font-medium">
                    {overview?.incidents?.critical_count ?? 0} Kritis
                  </span>
                </div>
                <div className="mt-2 text-[11px] text-neutral-400">
                  Dipantau secara real-time oleh NOC
                </div>
              </div>

              {/* Card 4: SLA Availability */}
              <div className="p-4 rounded-xl bg-neutral-900/60 border border-neutral-800 shadow-sm">
                <div className="flex items-center justify-between text-neutral-400 mb-2">
                  <span className="text-xs uppercase font-medium">Ketersediaan SLA (30 Hari)</span>
                  <CheckSquare className="w-4 h-4 text-emerald-400" />
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-bold text-white">
                    {overview?.sla?.measured_availability != null
                      ? `${overview.sla.measured_availability.toFixed(2)}%`
                      : "INSUFFICIENT_COVERAGE"}
                  </span>
                  <span className="text-xs text-emerald-400 font-medium">
                    Target: {overview?.sla?.target_availability ?? 99.9}%
                  </span>
                </div>
                <div className="mt-2 text-[11px] text-neutral-400">
                  Status: {overview?.sla?.status ?? "NORMAL"}
                </div>
              </div>
            </div>

            {/* Health Score Dimension Breakdown */}
            <div className="p-5 rounded-xl bg-neutral-900/60 border border-neutral-800 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white">Status Kesehatan Jaringan Terpadu</h3>
                  <p className="text-xs text-neutral-400">
                    Evaluasi multi-dimensi real-time berbasis telemetri (WP 8.5.1)
                  </p>
                </div>
                {overview?.health?.state && (
                  <span
                    className={`text-xs font-mono font-semibold px-2.5 py-1 rounded-md border ${getHealthColor(
                      overview.health.state
                    )}`}
                  >
                    {overview.health.state} ({overview.health.score != null ? `${overview.health.score.toFixed(1)} Poin` : "N/A"})
                  </span>
                )}
              </div>

              {/* Factors list */}
              {overview?.health?.contributing_factors?.length > 0 && (
                <div className="p-3 rounded-lg bg-neutral-800/50 border border-neutral-700/50 text-xs space-y-1">
                  <span className="font-medium text-neutral-300">Faktor Berkontribusi:</span>
                  <ul className="list-disc list-inside text-neutral-400 space-y-0.5">
                    {overview.health.contributing_factors.map((factor, idx) => (
                      <li key={idx}>{factor}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}

        {/* =================================================================== */}
        {/* TAB 2: SITES & DEVICES                                              */}
        {/* =================================================================== */}
        {activeTab === "sites_devices" && (
          <div className="space-y-6">
            <div className="p-5 rounded-xl bg-neutral-900/60 border border-neutral-800 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="text-sm font-semibold text-white">Inventaris Lokasi & Perangkat Tenant</h3>
                  <p className="text-xs text-neutral-400">
                    Daftar perangkat jaringan dan branch office resmi tenant Anda (Read-Only)
                  </p>
                </div>
                <div className="text-xs font-medium text-neutral-400">
                  Total: {devices.length} Perangkat di {sites.length} Lokasi
                </div>
              </div>

              {/* Devices Table */}
              <div className="overflow-x-auto border border-neutral-800 rounded-lg">
                <table className="w-full text-left text-xs">
                  <thead className="bg-neutral-800/80 text-neutral-400 uppercase font-mono text-[10px] border-b border-neutral-700/60">
                    <tr>
                      <th className="py-2.5 px-3">Nama Perangkat</th>
                      <th className="py-2.5 px-3">Alamat IP (RFC 1918)</th>
                      <th className="py-2.5 px-3">Tipe & Vendor</th>
                      <th className="py-2.5 px-3">Status</th>
                      <th className="py-2.5 px-3">Gateway</th>
                      <th className="py-2.5 px-3">Kredensial</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-800 text-neutral-300">
                    {devices.length === 0 ? (
                      <tr>
                        <td colSpan="6" className="py-8 text-center text-neutral-500">
                          Tidak ada perangkat terdaftar untuk organisasi ini.
                        </td>
                      </tr>
                    ) : (
                      devices.map((dev) => (
                        <tr key={dev.device_id} className="hover:bg-neutral-800/30">
                          <td className="py-2.5 px-3 font-medium text-white">{dev.name}</td>
                          <td className="py-2.5 px-3 font-mono">{dev.management_ip}</td>
                          <td className="py-2.5 px-3">
                            {dev.device_type} ({dev.vendor})
                          </td>
                          <td className="py-2.5 px-3">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-mono border ${
                                dev.status === "ACTIVE"
                                  ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20"
                                  : "text-rose-400 bg-rose-500/10 border-rose-500/20"
                              }`}
                            >
                              {dev.status}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 font-mono text-neutral-400">
                            {dev.gateway_id || "Direct"}
                          </td>
                          <td className="py-2.5 px-3 text-neutral-500 font-mono text-[10px]">
                            [REDACTED]
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* =================================================================== */}
        {/* TAB 3: INCIDENTS                                                    */}
        {/* =================================================================== */}
        {activeTab === "incidents" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between mb-2">
              <div>
                <h3 className="text-sm font-semibold text-white">Daftar Insiden Operasional</h3>
                <p className="text-xs text-neutral-400">
                  Insiden yang memengaruhi layanan atau konektivitas organisasi Anda
                </p>
              </div>
            </div>

            <div className="space-y-3">
              {incidents.length === 0 ? (
                <div className="p-8 rounded-xl bg-neutral-900/60 border border-neutral-800 text-center text-neutral-500 text-xs">
                  Semua layanan beroperasi normal. Tidak ada insiden aktif saat ini.
                </div>
              ) : (
                incidents.map((inc) => (
                  <div
                    key={inc.incident_id}
                    className="p-4 rounded-xl bg-neutral-900/60 border border-neutral-800 space-y-2 hover:border-neutral-700 transition-colors"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold border ${
                            inc.severity === "CRITICAL"
                              ? "text-rose-400 bg-rose-500/10 border-rose-500/20"
                              : inc.severity === "HIGH"
                              ? "text-amber-400 bg-amber-500/10 border-amber-500/20"
                              : "text-sky-400 bg-sky-500/10 border-sky-500/20"
                          }`}
                        >
                          {inc.severity}
                        </span>
                        <h4 className="text-sm font-medium text-white">{inc.title}</h4>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-neutral-800 text-neutral-300">
                          {inc.state}
                        </span>
                        {inc.state === "DETECTED" && (
                          <button
                            onClick={() => handleAcknowledgeIncident(inc.incident_id)}
                            className="px-2.5 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-[11px] font-medium transition-colors"
                          >
                            Konfirmasi (Acknowledge)
                          </button>
                        )}
                      </div>
                    </div>
                    <p className="text-xs text-neutral-300">{inc.summary}</p>
                    <div className="flex flex-wrap items-center gap-4 text-[11px] text-neutral-500 font-mono pt-1">
                      <span>ID: {inc.incident_id}</span>
                      <span>Dibuat: {new Date(inc.created_at).toLocaleString("id-ID")}</span>
                      {inc.resolved_at && <span>Selesai: {new Date(inc.resolved_at).toLocaleString("id-ID")}</span>}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* =================================================================== */}
        {/* TAB 4: SLA & AVAILABILITY                                           */}
        {/* =================================================================== */}
        {activeTab === "sla" && (
          <div className="space-y-4">
            <div className="p-5 rounded-xl bg-neutral-900/60 border border-neutral-800 space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-white">Kepatuhan Perjanjian Tingkat Layanan (SLA)</h3>
                <p className="text-xs text-neutral-400">
                  Laporan matematis ketersediaan layanan dan sisa error budget (WP 8.7)
                </p>
              </div>

              <div className="space-y-3">
                {slaSummary?.services?.map((svc) => (
                  <div
                    key={svc.service_id}
                    className="p-4 rounded-lg bg-neutral-800/40 border border-neutral-700/60 flex flex-wrap items-center justify-between gap-4"
                  >
                    <div>
                      <h4 className="text-sm font-semibold text-white">{svc.name}</h4>
                      <p className="text-xs text-neutral-400">
                        Target: {svc.target_availability}% • Criticality: {svc.criticality}
                      </p>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <span className="text-lg font-bold text-white">
                          {svc.measured_availability != null ? `${svc.measured_availability.toFixed(2)}%` : "INSUFFICIENT"}
                        </span>
                        <div className="text-[11px] text-neutral-400">
                          Sisa Budget: {svc.error_budget_remaining_percent != null ? `${svc.error_budget_remaining_percent.toFixed(1)}%` : "N/A"}
                        </div>
                      </div>
                      <span
                        className={`px-2.5 py-1 rounded text-xs font-mono font-semibold border ${getHealthColor(
                          svc.status === "COMPLIANT" ? "HEALTHY" : "CRITICAL"
                        )}`}
                      >
                        {svc.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* =================================================================== */}
        {/* TAB 5: SUPPORT REQUEST DESK                                         */}
        {/* =================================================================== */}
        {activeTab === "support" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-white">Customer Support & Tiket Layanan</h3>
                <p className="text-xs text-neutral-400">
                  Pusat komunikasi dan eskalasi teknis langsung dengan Tim NOC AIRA
                </p>
              </div>
              <button
                onClick={() => setShowNewTicketModal(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-xs font-medium text-white transition-colors shadow-sm"
              >
                <Plus className="w-3.5 h-3.5" />
                Buat Tiket Baru
              </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Ticket List */}
              <div className="lg:col-span-1 space-y-2">
                {supportRequests.length === 0 ? (
                  <div className="p-6 rounded-xl bg-neutral-900/60 border border-neutral-800 text-center text-xs text-neutral-500">
                    Belum ada tiket support yang diajukan.
                  </div>
                ) : (
                  supportRequests.map((req) => (
                    <div
                      key={req.request_id}
                      onClick={() => fetchTicketDetails(req.request_id)}
                      className={`p-3 rounded-lg border cursor-pointer transition-all ${
                        selectedTicket?.request_id === req.request_id
                          ? "bg-cyan-500/10 border-cyan-500/30 text-white"
                          : "bg-neutral-900/60 border-neutral-800 text-neutral-300 hover:border-neutral-700"
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="font-mono text-[10px] text-cyan-400">{req.category}</span>
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-neutral-800">
                          {req.status}
                        </span>
                      </div>
                      <h4 className="text-xs font-semibold line-clamp-1">{req.subject}</h4>
                      <p className="text-[11px] text-neutral-400 line-clamp-2 mt-1">{req.description}</p>
                    </div>
                  ))
                )}
              </div>

              {/* Ticket Detail & Collaboration Panel */}
              <div className="lg:col-span-2 p-5 rounded-xl bg-neutral-900/60 border border-neutral-800 flex flex-col justify-between min-h-[350px]">
                {selectedTicket ? (
                  <div className="flex-1 flex flex-col justify-between">
                    <div className="space-y-4">
                      <div className="border-b border-neutral-800 pb-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-mono text-cyan-400">ID: {selectedTicket.request_id}</span>
                          <span className="text-xs font-mono px-2 py-0.5 rounded bg-neutral-800 text-neutral-300">
                            Status: {selectedTicket.status}
                          </span>
                        </div>
                        <h3 className="text-sm font-bold text-white mt-1">{selectedTicket.subject}</h3>
                        <p className="text-xs text-neutral-300 mt-2 bg-neutral-800/40 p-2.5 rounded border border-neutral-700/40">
                          {selectedTicket.description}
                        </p>
                      </div>

                      {/* Comments Thread */}
                      <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                        <h4 className="text-[11px] font-semibold text-neutral-400 uppercase tracking-wider">
                          Percakapan & Pembaruan
                        </h4>
                        {ticketComments.length === 0 ? (
                          <p className="text-xs text-neutral-500 italic">Belum ada tanggapan.</p>
                        ) : (
                          ticketComments.map((com) => (
                            <div
                              key={com.comment_id}
                              className={`p-2.5 rounded-lg text-xs space-y-1 ${
                                com.is_internal
                                  ? "bg-indigo-950/40 border border-indigo-800/40 text-neutral-200"
                                  : "bg-neutral-800/60 border border-neutral-700/60 text-neutral-300"
                              }`}
                            >
                              <div className="flex items-center justify-between text-[10px] text-neutral-400">
                                <span className="font-semibold text-white">
                                  {com.author_name} {com.is_internal ? "(NOC Operator)" : "(Customer)"}
                                </span>
                                <span>{new Date(com.created_at).toLocaleTimeString("id-ID")}</span>
                              </div>
                              <p>{com.message}</p>
                            </div>
                          ))
                        )}
                      </div>
                    </div>

                    {/* Add Comment Input */}
                    <form onSubmit={handleAddComment} className="flex gap-2 mt-4 pt-3 border-t border-neutral-800">
                      <input
                        type="text"
                        value={newComment}
                        onChange={(e) => setNewComment(e.target.value)}
                        placeholder="Ketik balasan atau informasi tambahan..."
                        className="flex-1 px-3 py-1.5 rounded-lg bg-neutral-800 border border-neutral-700 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500"
                      />
                      <button
                        type="submit"
                        disabled={!newComment.trim()}
                        className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium transition-colors disabled:opacity-50"
                      >
                        <Send className="w-3.5 h-3.5" />
                        Kirim
                      </button>
                    </form>
                  </div>
                ) : (
                  <div className="flex-1 flex flex-col items-center justify-center text-center text-neutral-500 text-xs">
                    <LifeBuoy className="w-8 h-8 mb-2 text-neutral-600" />
                    Pilih salah satu tiket di sebelah kiri untuk melihat rincian dan berdiskusi.
                  </div>
                )}
              </div>
            </div>

            {/* Modal Create New Ticket */}
            {showNewTicketModal && (
              <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
                <div className="w-full max-w-lg rounded-xl bg-neutral-900 border border-neutral-800 p-5 space-y-4 shadow-xl animate-in fade-in duration-150">
                  <div className="flex items-center justify-between border-b border-neutral-800 pb-2">
                    <h3 className="text-sm font-bold text-white">Buat Tiket Dukungan Baru</h3>
                    <button
                      onClick={() => setShowNewTicketModal(false)}
                      className="text-neutral-400 hover:text-white text-xs"
                    >
                      Batal
                    </button>
                  </div>

                  <form onSubmit={handleSubmitTicket} className="space-y-3 text-xs">
                    <div>
                      <label className="block text-neutral-400 mb-1">Kategori Masalah</label>
                      <select
                        value={ticketForm.category}
                        onChange={(e) => setTicketForm({ ...ticketForm, category: e.target.value })}
                        className="w-full px-3 py-1.5 rounded-lg bg-neutral-800 border border-neutral-700 text-white"
                      >
                        <option value="SERVICE_REQUEST">Permintaan Layanan (Service Request)</option>
                        <option value="INCIDENT">Gangguan Koneksi (Incident)</option>
                        <option value="CHANGE">Permintaan Perubahan (Change)</option>
                        <option value="BILLING">Tagihan & SLA (Billing)</option>
                        <option value="GENERAL">Pertanyaan Umum (General)</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-neutral-400 mb-1">Prioritas Masalah</label>
                      <select
                        value={ticketForm.priority}
                        onChange={(e) => setTicketForm({ ...ticketForm, priority: e.target.value })}
                        className="w-full px-3 py-1.5 rounded-lg bg-neutral-800 border border-neutral-700 text-white"
                      >
                        <option value="LOW">Rendah (Low)</option>
                        <option value="MEDIUM">Sedang (Medium)</option>
                        <option value="HIGH">Tinggi (High)</option>
                        <option value="CRITICAL">Kritis (Critical)</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-neutral-400 mb-1">Subjek Tiket</label>
                      <input
                        type="text"
                        required
                        value={ticketForm.subject}
                        onChange={(e) => setTicketForm({ ...ticketForm, subject: e.target.value })}
                        placeholder="Contoh: Latensi tinggi pada router cabang Bandung"
                        className="w-full px-3 py-1.5 rounded-lg bg-neutral-800 border border-neutral-700 text-white placeholder-neutral-500"
                      />
                    </div>

                    <div>
                      <label className="block text-neutral-400 mb-1">Deskripsi Lengkap</label>
                      <textarea
                        required
                        rows="4"
                        value={ticketForm.description}
                        onChange={(e) => setTicketForm({ ...ticketForm, description: e.target.value })}
                        placeholder="Jelaskan kendala, gejala, dan waktu kejadian..."
                        className="w-full px-3 py-1.5 rounded-lg bg-neutral-800 border border-neutral-700 text-white placeholder-neutral-500"
                      />
                    </div>

                    <div className="flex justify-end gap-2 pt-2 border-t border-neutral-800">
                      <button
                        type="button"
                        onClick={() => setShowNewTicketModal(false)}
                        className="px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-300"
                      >
                        Batal
                      </button>
                      <button
                        type="submit"
                        className="px-4 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium shadow-sm"
                      >
                        Kirim Tiket
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}
          </div>
        )}

        {/* =================================================================== */}
        {/* TAB 6: USERS MANAGEMENT                                             */}
        {/* =================================================================== */}
        {activeTab === "users" && (
          <div className="space-y-4">
            <div className="p-5 rounded-xl bg-neutral-900/60 border border-neutral-800 space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-white">Pengguna Organisasi Resmi</h3>
                <p className="text-xs text-neutral-400">
                  Daftar akun pelanggan yang memiliki akses ke self-service portal ini (WP 8.9.2)
                </p>
              </div>

              <div className="overflow-x-auto border border-neutral-800 rounded-lg">
                <table className="w-full text-left text-xs">
                  <thead className="bg-neutral-800/80 text-neutral-400 uppercase font-mono text-[10px] border-b border-neutral-700/60">
                    <tr>
                      <th className="py-2.5 px-3">Username</th>
                      <th className="py-2.5 px-3">Email</th>
                      <th className="py-2.5 px-3">Status</th>
                      <th className="py-2.5 px-3">Dibuat Pada</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-800 text-neutral-300">
                    {tenantUsers.map((u) => (
                      <tr key={u.user_id} className="hover:bg-neutral-800/30">
                        <td className="py-2.5 px-3 font-medium text-white">{u.username}</td>
                        <td className="py-2.5 px-3 text-neutral-400">{u.email}</td>
                        <td className="py-2.5 px-3">
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20">
                            {u.is_active ? "ACTIVE" : "INACTIVE"}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-neutral-500 text-[11px]">{u.created_at}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* =================================================================== */}
        {/* TAB 7: NOTIFICATION PREFERENCES                                     */}
        {/* =================================================================== */}
        {activeTab === "settings" && (
          <div className="space-y-4">
            <div className="p-5 rounded-xl bg-neutral-900/60 border border-neutral-800 space-y-4 max-w-2xl">
              <div>
                <h3 className="text-sm font-semibold text-white">Pengaturan & Preferensi Notifikasi</h3>
                <p className="text-xs text-neutral-400">
                  Tentukan jenis pemberitahuan operasional yang ingin Anda terima (WP 8.9.8)
                </p>
              </div>

              {notifPrefs && (
                <div className="space-y-3 pt-2">
                  {[
                    { key: "notify_critical_incidents", label: "Insiden Kritis (Critical Incidents)" },
                    { key: "notify_major_incidents", label: "Insiden Tingkat Tinggi (Major / High)" },
                    { key: "notify_service_degradation", label: "Penurunan Kinerja Layanan (Service Degradation)" },
                    { key: "notify_gateway_offline", label: "Edge Gateway Terputus (Offline Event)" },
                    { key: "notify_sla_breach", label: "Peringatan Ambang Batas SLA (SLA Risk / Breach)" },
                    { key: "email_notifications", label: "Kirim Notifikasi via Email" },
                    { key: "in_app_notifications", label: "Kirim Notifikasi In-App & Dashboard" },
                  ].map((item) => (
                    <label
                      key={item.key}
                      className="flex items-center justify-between p-3 rounded-lg bg-neutral-800/40 border border-neutral-700/60 cursor-pointer hover:bg-neutral-800/70 transition-colors"
                    >
                      <span className="text-xs font-medium text-neutral-200">{item.label}</span>
                      <input
                        type="checkbox"
                        checked={Boolean(notifPrefs[item.key])}
                        onChange={(e) => handleTogglePref(item.key, e.target.checked)}
                        className="w-4 h-4 rounded text-cyan-600 focus:ring-cyan-500 focus:ring-offset-neutral-900"
                      />
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
