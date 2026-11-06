// src/pages/NetworkIntelligencePage.jsx
//
// AIRA OS — Network Intelligence, Incident Investigation & Autonomous Action Center
// Hybrid Multi-Tenant NOC & Operational Decision Intelligence Platform
// Section 4.1 3-Section Layout:
// 1. Overview (Health score, registered devices, reachable/unreachable, active investigations, anomalies, pending approvals, recent AI decisions)
// 2. Investigations (History, current investigation, detected issues, supporting evidence, affected devices, topology, NMS metrics, AI analysis, recommendations)
// 3. Action Center (Proposed, pending approvals, approved, rejected, executing, completed, failed, verification results)

import React, { useEffect, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { api } from "../api.js";
import { useToast } from "../components/Toast.jsx";
import RouteHistoryModal from "../components/topology/RouteHistoryModal.jsx";
import OverviewTab from "../components/network-intelligence/OverviewTab.jsx";
import InvestigatorTab from "../components/network-intelligence/InvestigatorTab.jsx";
import KnowledgeGraphTab from "../components/network-intelligence/KnowledgeGraphTab.jsx";
import PathAnalysisTab from "../components/network-intelligence/PathAnalysisTab.jsx";
import RcaTimelineTab from "../components/network-intelligence/RcaTimelineTab.jsx";
import HistoricalIntelligenceTab from "../components/network-intelligence/HistoricalIntelligenceTab.jsx";
import EvidenceInspectorTab from "../components/network-intelligence/EvidenceInspectorTab.jsx";
import ActionCenterTab from "../components/network-intelligence/ActionCenterTab.jsx";
import OnboardDeviceModal from "../components/network-intelligence/OnboardDeviceModal.jsx";
import OperationsPolicyModal from "../components/network-intelligence/OperationsPolicyModal.jsx";
import NewActionModal from "../components/network-intelligence/NewActionModal.jsx";

import {
  Activity,
  AlertCircle,
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock,
  Code2,
  Cpu,
  FileText,
  GitBranch,
  HelpCircle,
  History,
  Layers,
  Loader2,
  Network,
  Play,
  PlusCircle,
  RotateCcw,
  Search,
  Server,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  StopCircle,
  Terminal,
  Zap,
} from "lucide-react";

export default function NetworkIntelligencePage({ onOpenMenu }) {
  const { notify } = useToast();

  // Primary 3-Section Navigation: "overview" | "investigations" | "actions"
  const [activeTab, setActiveTab] = useState("overview");

  // Sub-navigation within Investigations
  const [invSubTab, setInvSubTab] = useState("details"); // details, nl_investigator, evidence, graph, paths, rca, playbook, planner

  // Core Data States
  const [overviewData, setOverviewData] = useState(null);
  const [incidents, setIncidents] = useState([]);
  const [selectedIncident, setSelectedIncident] = useState(null);
  const [evidenceItems, setEvidenceItems] = useState([]);
  const [actions, setActions] = useState([]);
  const [devices, setDevices] = useState([]);
  const [playbooks, setPlaybooks] = useState([]);
  const [activePlaybookRun, setActivePlaybookRun] = useState(null);
  const [plans, setPlans] = useState([]);
  const [selectedPlan, setSelectedPlan] = useState(null);

  // Loading States
  const [loading, setLoading] = useState(false);
  const [loadingActions, setLoadingActions] = useState(false);
  const [advancingPlaybook, setAdvancingPlaybook] = useState(false);
  const [runningAutoDiag, setRunningAutoDiag] = useState(false);
  const [investigating, setInvestigating] = useState(false);
  const [planning, setPlanning] = useState(false);

  // Investigation State
  const [autoDiagResult, setAutoDiagResult] = useState(null);
  const [autoDiagQuery, setAutoDiagQuery] = useState("");
  const [autoDiagTargetIp, setAutoDiagTargetIp] = useState("");
  const [autoDiagTable, setAutoDiagTable] = useState("main");
  const [activeInvestigation, setActiveInvestigation] = useState(null);
  const [graphData, setGraphData] = useState(null);
  const [pathResult, setPathResult] = useState(null);
  const [historicalData, setHistoricalData] = useState(null);

  // Modals
  const [showOnboardModal, setShowOnboardModal] = useState(false);
  const [showPolicyModal, setShowPolicyModal] = useState(false);
  const [showNewActionModal, setShowNewActionModal] = useState(false);
  const [prefilledActionData, setPrefilledActionData] = useState(null);
  const [routeHistoryOpen, setRouteHistoryOpen] = useState(false);
  const [showNewIncidentModal, setShowNewIncidentModal] = useState(false);
  const [showNewPlanModal, setShowNewPlanModal] = useState(false);

  // Incident & Plan Forms
  const [newIncidentForm, setNewIncidentForm] = useState({
    device_identity: "",
    related_devices: [],
    incident_type: "LAN_NO_INTERNET",
    symptoms: "",
    user_description: "",
    target_ip: "",
  });

  const [newPlanForm, setNewPlanForm] = useState({
    target_device: "",
    change_type: "ADD_STATIC_ROUTE",
    dst_address: "",
    gateway: "192.168.1.1",
    vlan_id: "100",
    interface: "bridge",
    subnet: "192.168.100.1/24",
  });

  // -------------------------------------------------------------------------
  // Data Fetching
  // -------------------------------------------------------------------------

  const fetchOverview = async () => {
    try {
      const res = await api.intelligence.getOverview();
      if (res?.overview) setOverviewData(res.overview);
    } catch (e) {
      console.warn("Overview fetch:", e);
    }
  };

  const fetchActions = async () => {
    setLoadingActions(true);
    try {
      const res = await api.intelligence.listActions(null, 50);
      if (res?.actions) {
        setActions(res.actions);
      }
    } catch (e) {
      console.warn("Actions fetch:", e);
    } finally {
      setLoadingActions(false);
    }
  };

  const fetchGraph = async (layer = null) => {
    try {
      const res = await api.intelligence.getGraph({ layer });
      if (res?.graph) setGraphData(res.graph);
    } catch (e) {
      console.warn("Graph fetch:", e);
    }
  };

  const fetchHistorical = async () => {
    try {
      const res = await api.intelligence.getHistory();
      if (res?.history) setHistoricalData(res.history);
    } catch (e) {
      console.warn("History fetch:", e);
    }
  };

  const loadInitialData = async () => {
    setLoading(true);
    try {
      const [incRes, pbRes, devRes, planRes] = await Promise.all([
        api.intelligence.listIncidents(30).catch(() => ({ incidents: [] })),
        api.intelligence.listPlaybooks().catch(() => ({ playbooks: [] })),
        api.devices().catch(() => ({ devices: [] })),
        api.intelligence.listPlans(30).catch(() => ({ plans: [] })),
      ]);

      const incs = incRes.incidents || [];
      setIncidents(incs);
      setPlaybooks(pbRes.playbooks || []);
      setDevices(devRes.devices || []);
      setPlans(planRes.plans || []);

      if (incs.length > 0 && !selectedIncident) {
        loadIncidentDetail(incs[0].incident_id);
      }
      if (planRes.plans?.length > 0 && !selectedPlan) {
        setSelectedPlan(planRes.plans[0]);
      }
      if (devRes.devices?.length > 0) {
        setNewIncidentForm((f) => ({ ...f, device_identity: devRes.devices[0].name }));
        setNewPlanForm((f) => ({ ...f, target_device: devRes.devices[0].name }));
      }
    } catch (err) {
      notify({ type: "error", message: "Gagal memuat data Network Intelligence." });
    } finally {
      setLoading(false);
    }
  };

  const loadIncidentDetail = async (incidentId) => {
    try {
      const res = await api.intelligence.getIncident(incidentId);
      if (res.success) {
        setSelectedIncident(res.incident);
        setEvidenceItems(res.evidence_items || []);
      }
    } catch {
      notify({ type: "error", message: "Gagal memuat detail insiden." });
    }
  };

  useEffect(() => {
    loadInitialData();
    fetchOverview();
    fetchActions();
    fetchGraph();
    fetchHistorical();
  }, []);

  // -------------------------------------------------------------------------
  // Action Handlers
  // -------------------------------------------------------------------------

  const handleResolveApproval = async (actionId, approved, notes = "") => {
    try {
      const res = await api.intelligence.resolveActionApproval(actionId, approved, notes);
      if (res.success) {
        notify({
          type: approved ? "success" : "info",
          message: approved ? "Tindakan berhasil disetujui." : "Tindakan ditolak.",
        });
        fetchActions();
        fetchOverview();
      }
    } catch (err) {
      notify({ type: "error", message: `Gagal memperbarui approval: ${err.message}` });
      throw err;
    }
  };

  const handleExecuteAction = async (actionId) => {
    try {
      const res = await api.intelligence.executeAction(actionId);
      if (res.success) {
        const vr = res.action?.verification_result;
        notify({
          type: res.action?.status === "SUCCESS" ? "success" : "warning",
          message: `Eksekusi selesai: ${res.action?.status}. Verifikasi: ${vr?.passed ? "LULUS" : "GAGAL"}`,
        });
        fetchActions();
        fetchOverview();
      }
    } catch (err) {
      notify({ type: "error", message: `Eksekusi gagal: ${err.message}` });
      throw err;
    }
  };

  const handleRunInvestigation = async (body) => {
    setInvestigating(true);
    try {
      const res = await api.intelligence.investigateNL(body);
      if (res?.investigation) {
        setActiveInvestigation(res.investigation);
        setInvSubTab("nl_investigator");
        notify({ type: "success", message: "Penyelidikan selesai! Hasil dan hipotesis tersedia." });
        if (res.investigation.path) setPathResult(res.investigation.path);
        fetchOverview();
      }
    } catch (err) {
      notify({ type: "error", message: `Investigasi gagal: ${err.message}` });
    } finally {
      setInvestigating(false);
    }
  };

  const handleCancelInvestigation = async (invId) => {
    try {
      await api.intelligence.cancelNLInvestigation(invId);
      notify({ type: "info", message: "Permintaan pembatalan dikirim." });
    } catch (err) {
      notify({ type: "error", message: `Gagal membatalkan: ${err.message}` });
    }
  };

  const handleRunAutoDiagnose = async () => {
    setRunningAutoDiag(true);
    try {
      notify({ type: "info", message: "Menjalankan pipeline diagnostik routing & jaringan otomatis..." });
      const res = await api.intelligence.autoDiagnose({
        symptom: autoDiagQuery || undefined,
        target_ip: autoDiagTargetIp || undefined,
        routing_table: autoDiagTable || "main",
      });
      if (res.success) {
        setAutoDiagResult(res);
        await loadInitialData();
        if (res.incident?.incident_id) {
          await loadIncidentDetail(res.incident.incident_id);
        }
        setActiveTab("investigations");
        setInvSubTab("details");
        notify({ type: "success", message: "Diagnostik otomatis selesai! Akar masalah & rekomendasi dirangkum." });
      } else {
        notify({ type: "error", message: res.error || "Diagnostik otomatis gagal." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message || "Gagal menjalankan diagnostik otomatis." });
    } finally {
      setRunningAutoDiag(false);
    }
  };

  const handleRunPathAnalysis = async ({ destinationIp, sourceDeviceId, routingTable }) => {
    setLoading(true);
    try {
      const res = await api.intelligence.getPathAnalysis({
        destinationIp,
        sourceDeviceId,
        routingTable,
      });
      if (res?.path_analysis) {
        setPathResult(res.path_analysis);
        notify({ type: "success", message: "LPM dan path hop-by-hop berhasil dievaluasi." });
      }
    } catch (err) {
      notify({ type: "error", message: `Analisis rute gagal: ${err.message}` });
    } finally {
      setLoading(false);
    }
  };

  const handleCompareSnapshots = async (older, newer) => {
    setLoading(true);
    try {
      const res = await api.intelligence.getHistory({ olderSnapshotId: older, newerSnapshotId: newer });
      if (res?.history) {
        setHistoricalData(res.history);
        notify({ type: "success", message: "Perbandingan snapshot selesai." });
      }
    } catch (err) {
      notify({ type: "error", message: `Perbandingan gagal: ${err.message}` });
    } finally {
      setLoading(false);
    }
  };

  const handleCreateIncident = async (e) => {
    e.preventDefault();
    if (!newIncidentForm.device_identity) {
      notify({ type: "error", message: "Pilih target perangkat." });
      return;
    }
    setLoading(true);
    try {
      const symptomsArray = newIncidentForm.symptoms
        ? newIncidentForm.symptoms.split(",").map((s) => s.trim()).filter(Boolean)
        : [];

      let res;
      if (newIncidentForm.related_devices && newIncidentForm.related_devices.length > 0) {
        res = await api.intelligence.createMultiDeviceInvestigation({
          primary_device: newIncidentForm.device_identity,
          related_devices: newIncidentForm.related_devices,
          symptom_description: newIncidentForm.user_description || newIncidentForm.incident_type,
          incident_type: newIncidentForm.incident_type,
          target_ip: newIncidentForm.target_ip || undefined,
          severity: "HIGH",
        });
      } else {
        res = await api.intelligence.createIncident({
          device_identity: newIncidentForm.device_identity,
          incident_type: newIncidentForm.incident_type,
          symptoms: symptomsArray,
          user_description: newIncidentForm.user_description,
          target_ip: newIncidentForm.target_ip || undefined,
          severity: "HIGH",
        });
      }

      if (res.success) {
        notify({ type: "success", message: "Investigasi insiden selesai dianalisis." });
        setShowNewIncidentModal(false);
        await loadInitialData();
        fetchOverview();
        fetchGraph();
        fetchHistorical();
        setSelectedIncident(res.incident);
        setActiveTab("investigations");
        setInvSubTab("details");
      }
    } catch (err) {
      notify({ type: "error", message: err.message || "Gagal membuat investigasi." });
    } finally {
      setLoading(false);
    }
  };

  const handleStartPlaybook = async (pbId) => {
    if (!selectedIncident) return;
    setAdvancingPlaybook(true);
    try {
      const res = await api.intelligence.startPlaybook(selectedIncident.incident_id, pbId);
      if (res.success) {
        setActivePlaybookRun(res.playbook_run);
        setInvSubTab("playbook");
        notify({ type: "success", message: "Playbook diagnostik dimulai." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message || "Gagal memulai playbook." });
    } finally {
      setAdvancingPlaybook(false);
    }
  };

  const handleAdvancePlaybook = async (action = "step") => {
    if (!activePlaybookRun) return;
    setAdvancingPlaybook(true);
    try {
      const res = await api.intelligence.advancePlaybook(activePlaybookRun.run_id, { action });
      if (res.success) {
        setActivePlaybookRun(res.playbook_run);
        if (action === "cancel") {
          notify({ type: "info", message: "Playbook dibatalkan." });
        } else {
          notify({ type: "success", message: "Langkah playbook selesai dievaluasi." });
        }
      }
    } catch (err) {
      notify({ type: "error", message: err.message || "Gagal memajukan playbook." });
    } finally {
      setAdvancingPlaybook(false);
    }
  };

  const handleCreatePlan = async (e) => {
    e.preventDefault();
    if (!newPlanForm.target_device) {
      notify({ type: "error", message: "Pilih target perangkat." });
      return;
    }
    setPlanning(true);
    try {
      let params = {};
      if (newPlanForm.change_type === "ADD_STATIC_ROUTE") {
        params = { dst_address: newPlanForm.dst_address, gateway: newPlanForm.gateway, distance: 1 };
      } else if (newPlanForm.change_type === "ADD_VLAN") {
        params = { vlan_id: newPlanForm.vlan_id, bridge: newPlanForm.interface, subnet: newPlanForm.subnet };
      } else if (newPlanForm.change_type === "CONFIGURE_NAT") {
        params = { action: "masquerade", out_interface: newPlanForm.interface };
      }

      const res = await api.intelligence.createPlan({
        target_device: newPlanForm.target_device,
        change_type: newPlanForm.change_type,
        parameters: params,
        incident_id: selectedIncident?.incident_id,
      });

      if (res.success) {
        notify({ type: "success", message: "Rencana konfigurasi & simulasi berhasil dibuat." });
        setShowNewPlanModal(false);
        setPlans((prev) => [res.plan, ...prev]);
        setSelectedPlan(res.plan);
        setActiveTab("investigations");
        setInvSubTab("planner");
      }
    } catch (err) {
      notify({ type: "error", message: err.message || "Gagal membuat rencana." });
    } finally {
      setPlanning(false);
    }
  };

  const pendingApprovalsCount = actions.filter((a) => a.status === "PENDING_APPROVAL").length;

  return (
    <div className="space-y-6">
      <TopBar
        title="Network Intelligence & Autonomous Operations"
        subtitle="Pusat Investigasi Insiden, Evaluasi Akar Masalah, Perencanaan Tindakan, & Approval Policy (Phase G)"
        onMenuClick={onOpenMenu}
      />

      {/* Action Header Banner */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-card border border-border rounded-xl">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
            <ShieldCheck size={22} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-white">Engineering Intelligence Engine</h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-semibold font-mono">
                SAFETY-LOCKED
              </span>
            </div>
            <p className="text-xs text-white/50">
              Korelasi Inventory, Topology, dan NMS terintegrasi dengan 5-Tier Risk Taxonomy & Non-bypassable Admin Approval.
            </p>
          </div>
        </div>

        {/* Quick Diagnostic Input & Actions */}
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={autoDiagQuery}
            onChange={(e) => setAutoDiagQuery(e.target.value)}
            placeholder="Tanya rute / gejala (mis. Mengapa VLAN 20 lambat?)"
            className="bg-black/40 border border-white/15 rounded-lg px-3 py-1.5 text-xs text-white w-56 outline-none focus:border-cyan-400"
          />
          <input
            type="text"
            value={autoDiagTargetIp}
            onChange={(e) => setAutoDiagTargetIp(e.target.value)}
            placeholder="Target IP/CIDR"
            className="bg-black/40 border border-white/15 rounded-lg px-2.5 py-1.5 text-xs text-white font-mono w-32 outline-none focus:border-cyan-400"
          />
          <button
            onClick={handleRunAutoDiagnose}
            disabled={runningAutoDiag}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white text-xs font-semibold shadow-lg shadow-cyan-500/20 transition disabled:opacity-50"
          >
            <Zap size={14} className={runningAutoDiag ? "animate-spin" : ""} />
            <span>{runningAutoDiag ? "Menganalisis..." : "⚡ Diagnostik Otomatis"}</span>
          </button>

          <button
            onClick={() => setShowOnboardModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/30 text-xs font-medium transition"
          >
            <PlusCircle size={14} />
            <span>Onboard Perangkat</span>
          </button>

          <button
            onClick={() => setShowPolicyModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-xs font-medium border border-white/10 transition"
          >
            <Sliders size={14} />
            <span>AI Operations Policy</span>
          </button>

          <button
            onClick={() => {
              setPrefilledActionData(null);
              setShowNewActionModal(true);
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-xs font-medium border border-white/10 transition"
          >
            <Code2 size={14} />
            <span>Propose Action</span>
          </button>

          <button
            onClick={() => setRouteHistoryOpen(true)}
            className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white/70 hover:text-white border border-white/10 transition"
            title="Riwayat Rute & Diff"
          >
            <History size={16} />
          </button>
        </div>
      </div>

      {/* 3 Primary Navigation Tabs (Section 4.1 Requirement) */}
      <div className="flex items-center gap-2 border-b border-border pb-1">
        {[
          { id: "overview", label: "1. Overview", icon: Activity },
          { id: "investigations", label: `2. Investigations (${incidents.length})`, icon: Search },
          { id: "actions", label: "3. Action Center", icon: ShieldAlert, badge: pendingApprovalsCount },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-t-xl text-sm font-semibold transition relative ${
                isActive
                  ? "bg-card text-cyan-400 border-t border-l border-r border-border shadow-sm"
                  : "text-white/60 hover:text-white hover:bg-white/5"
              }`}
            >
              <Icon size={16} />
              <span>{tab.label}</span>
              {tab.badge > 0 && (
                <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                  {tab.badge}
                </span>
              )}
              {isActive && (
                <div className="absolute bottom-[-1px] left-0 right-0 h-[2px] bg-cyan-400" />
              )}
            </button>
          );
        })}
      </div>

      {/* ------------------------------------------------------------------- */}
      {/* SECTION 1: OVERVIEW TAB */}
      {/* ------------------------------------------------------------------- */}
      {activeTab === "overview" && (
        <OverviewTab
          overview={overviewData}
          loading={loading}
          onRefresh={fetchOverview}
          onOpenOnboard={() => setShowOnboardModal(true)}
          onOpenPolicy={() => setShowPolicyModal(true)}
          onNavigateToTab={(tab) => {
            setActiveTab(tab);
            if (tab === "investigations") setInvSubTab("details");
          }}
        />
      )}

      {/* ------------------------------------------------------------------- */}
      {/* SECTION 2: INVESTIGATIONS TAB */}
      {/* ------------------------------------------------------------------- */}
      {activeTab === "investigations" && (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Left Column: Investigation History Sidebar */}
          <div className="lg:col-span-1 space-y-3">
            <div className="flex items-center justify-between px-1">
              <span className="text-xs font-semibold text-white/70 uppercase tracking-wider">
                Riwayat Investigasi ({incidents.length})
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setShowNewIncidentModal(true)}
                  className="text-xs px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 font-semibold"
                  title="Investigasi Manual"
                >
                  + Baru
                </button>
                <button onClick={loadInitialData} className="p-1 text-white/40 hover:text-white transition">
                  <RotateCcw size={13} className={loading ? "animate-spin" : ""} />
                </button>
              </div>
            </div>

            <div className="space-y-2 max-h-[720px] overflow-y-auto pr-1">
              {incidents.length === 0 ? (
                <div className="p-6 text-center text-xs text-white/40 bg-card border border-border rounded-xl">
                  Belum ada riwayat investigasi insiden.
                </div>
              ) : (
                incidents.map((inc) => {
                  const isSelected = selectedIncident?.incident_id === inc.incident_id;
                  return (
                    <div
                      key={inc.incident_id}
                      onClick={() => {
                        loadIncidentDetail(inc.incident_id);
                        setInvSubTab("details");
                      }}
                      className={`p-3.5 rounded-xl border text-left cursor-pointer transition ${
                        isSelected
                          ? "bg-cyan-500/10 border-cyan-500/40 text-white shadow-sm"
                          : "bg-card border-border hover:border-white/20 text-white/70"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-xs font-semibold text-white truncate max-w-[140px]">
                          {inc.device_identity}
                        </span>
                        <span
                          className={`text-[9px] px-1.5 py-0.5 rounded font-mono ${
                            inc.severity === "CRITICAL"
                              ? "bg-red-500/20 text-red-300"
                              : inc.severity === "HIGH"
                              ? "bg-amber-500/20 text-amber-300"
                              : "bg-blue-500/20 text-blue-300"
                          }`}
                        >
                          {inc.incident_type}
                        </span>
                      </div>

                      <p className="text-[11px] text-white/50 line-clamp-2">
                        {inc.user_description || (inc.symptoms && inc.symptoms[0]) || "Investigasi otomatis"}
                      </p>

                      <div className="flex items-center justify-between mt-2 pt-2 border-t border-white/5 text-[10px] text-white/40">
                        <span>{inc.investigation_status}</span>
                        <span>{new Date(inc.created_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Right Column: Investigation Workspace & Deep-Dive Subtabs */}
          <div className="lg:col-span-3 space-y-4">
            {/* Sub-tab Navigation within Investigations */}
            <div className="flex flex-wrap items-center gap-1.5 bg-card border border-border p-1.5 rounded-xl">
              {[
                { id: "details", label: "Laporan Investigasi", icon: FileText },
                { id: "nl_investigator", label: "NL Investigator", icon: Zap },
                { id: "evidence", label: `Bukti (${evidenceItems.length || activeInvestigation?.evidence_items?.length || 0})`, icon: Layers },
                { id: "graph", label: "Knowledge Graph", icon: Network },
                { id: "paths", label: "Path Analysis", icon: GitBranch },
                { id: "rca", label: "RCA Timeline", icon: ShieldAlert },
                { id: "history", label: "Historical Diff", icon: History },
                { id: "playbook", label: "Playbook", icon: Terminal },
                { id: "planner", label: `Planner (${plans.length})`, icon: Code2 },
              ].map((sub) => {
                const SubIcon = sub.icon;
                const isSubActive = invSubTab === sub.id;
                return (
                  <button
                    key={sub.id}
                    onClick={() => setInvSubTab(sub.id)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                      isSubActive
                        ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                        : "text-white/60 hover:text-white hover:bg-white/5"
                    }`}
                  >
                    <SubIcon size={14} />
                    <span>{sub.label}</span>
                  </button>
                );
              })}
            </div>

            {/* Subtab Content Area */}
            <div className="bg-card border border-border rounded-xl p-6 min-h-[560px]">
              {/* SUBTAB: DETAILS (Section 4.1 & 4.4 Structure) */}
              {invSubTab === "details" && (
                <div className="space-y-6">
                  {!selectedIncident ? (
                    <div className="text-center py-20 text-white/40 text-xs">
                      Pilih salah satu investigasi di bilah kiri atau jalankan Investigasi NL baru.
                    </div>
                  ) : (
                    <>
                      {/* Investigation Header */}
                      <div className="flex flex-wrap items-start justify-between gap-4 pb-4 border-b border-border">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-mono text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/30">
                              {selectedIncident.incident_id}
                            </span>
                            <h3 className="text-base font-bold text-white">
                              {selectedIncident.device_identity} — {selectedIncident.incident_type}
                            </h3>
                            <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-semibold ${
                              selectedIncident.severity === "CRITICAL"
                                ? "bg-red-500/20 text-red-300 border border-red-500/40"
                                : selectedIncident.severity === "HIGH"
                                ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                                : "bg-blue-500/20 text-blue-300 border border-blue-500/40"
                            }`}>
                              {selectedIncident.severity}
                            </span>
                          </div>
                          <p className="text-xs text-white/60 mt-1">
                            {selectedIncident.user_description || "Pemeriksaan gejala anomali jaringan berbasis bukti kanonikal."}
                          </p>
                        </div>

                        <div className="flex items-center gap-3">
                          <div className="text-right text-xs">
                            <div className="text-white/40 text-[10px]">STATUS INVESTIGASI</div>
                            <span className="font-semibold text-emerald-400">
                              {selectedIncident.investigation_status}
                            </span>
                          </div>
                          <button
                            onClick={() => {
                              setPrefilledActionData({
                                target_device: selectedIncident.device_identity,
                                action_type: "REMEDIATE_INCIDENT",
                                description: `Remediasi untuk ${selectedIncident.incident_type} pada ${selectedIncident.device_identity}`,
                                risk_level: "MEDIUM",
                                commands: selectedIncident.inferred_hypotheses?.[0]?.recommended_test
                                  ? [selectedIncident.inferred_hypotheses[0].recommended_test]
                                  : ["/ip route print"],
                              });
                              setShowNewActionModal(true);
                            }}
                            className="px-3.5 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black text-xs font-semibold flex items-center gap-1.5 transition"
                          >
                            <ShieldAlert size={14} />
                            <span>Ajukan Action Plan</span>
                          </button>
                        </div>
                      </div>

                      {/* Metadata Grid: Affected Devices, Interfaces, Topology Context */}
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div className="p-3.5 rounded-xl bg-white/5 border border-white/5 space-y-1">
                          <span className="text-[10px] font-mono text-white/40 uppercase">Perangkat Terdampak</span>
                          <div className="text-sm font-semibold text-white flex items-center gap-1.5">
                            <Server size={14} className="text-cyan-400" />
                            <span>{selectedIncident.device_identity}</span>
                          </div>
                          {selectedIncident.related_devices?.length > 0 && (
                            <div className="text-[11px] text-white/50 pt-1">
                              Terkait: {selectedIncident.related_devices.join(", ")}
                            </div>
                          )}
                        </div>

                        <div className="p-3.5 rounded-xl bg-white/5 border border-white/5 space-y-1">
                          <span className="text-[10px] font-mono text-white/40 uppercase">Konteks Topologi</span>
                          <div className="text-sm font-semibold text-indigo-300 flex items-center gap-1.5">
                            <Network size={14} className="text-indigo-400" />
                            <span>{selectedIncident.topology_context || "Single-Node Core Hop"}</span>
                          </div>
                          <div className="text-[11px] text-white/50 pt-1">
                            L2/L3 Adjacency Verified
                          </div>
                        </div>

                        <div className="p-3.5 rounded-xl bg-white/5 border border-white/5 space-y-1">
                          <span className="text-[10px] font-mono text-white/40 uppercase">Waktu Terdeteksi</span>
                          <div className="text-sm font-semibold text-white flex items-center gap-1.5">
                            <Clock size={14} className="text-emerald-400" />
                            <span>{new Date(selectedIncident.created_at * 1000).toLocaleString()}</span>
                          </div>
                          <div className="text-[11px] text-white/50 pt-1">
                            Confidence: {selectedIncident.confidence || "HIGH"}
                          </div>
                        </div>
                      </div>

                      {/* Observations & Supporting Evidence */}
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <h4 className="text-xs font-semibold text-white/80 uppercase tracking-wider flex items-center gap-1.5">
                            <Layers size={14} className="text-cyan-400" />
                            <span>Fakta Terobservasi &amp; Bukti Pendukung ({selectedIncident.observed_facts?.length || 0})</span>
                          </h4>
                          <span className="text-[10px] font-mono text-white/40">Read-Only Telemetry</span>
                        </div>

                        <div className="space-y-1.5">
                          {selectedIncident.observed_facts?.map((fact, idx) => (
                            <div key={idx} className="flex items-start gap-2 p-2.5 rounded-lg bg-white/5 border border-white/5 text-xs text-white/80">
                              <CheckCircle2 size={14} className="text-emerald-400 shrink-0 mt-0.5" />
                              <span>{fact}</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* AI Root Cause Hypotheses (Epistemic Separation: Facts vs Indications vs Hypotheses) */}
                      <div className="space-y-3">
                        <h4 className="text-xs font-semibold text-white/80 uppercase tracking-wider flex items-center gap-1.5">
                          <Bot size={14} className="text-amber-400" />
                          <span>Hipotesis Akar Masalah &amp; Analisis AI</span>
                        </h4>

                        <div className="space-y-3">
                          {selectedIncident.inferred_hypotheses?.map((h, idx) => (
                            <div key={idx} className="p-4 rounded-xl bg-white/5 border border-white/5 space-y-2">
                              <div className="flex items-center justify-between">
                                <span className="font-semibold text-sm text-cyan-300">
                                  #{idx + 1} {h.title}
                                </span>
                                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                                  Confidence: {h.confidence}
                                </span>
                              </div>
                              <p className="text-xs text-white/70 leading-relaxed">{h.explanation}</p>
                              {h.recommended_test && (
                                <div className="p-2 rounded bg-cyan-500/10 border border-cyan-500/20 text-xs text-cyan-300 font-mono">
                                  Rekomendasi verifikasi: {h.recommended_test}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Playbook Trigger Bar */}
                      <div className="p-4 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-between">
                        <div>
                          <h4 className="text-xs font-semibold text-cyan-300">Uji Diagnostik Deterministik</h4>
                          <p className="text-[11px] text-white/60">
                            Jalankan state machine terpandu untuk memvalidasi hipotesis tanpa risiko.
                          </p>
                        </div>
                        <button
                          onClick={() => handleStartPlaybook()}
                          disabled={advancingPlaybook}
                          className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black text-xs font-semibold transition"
                        >
                          <Play size={14} />
                          <span>Mulai Playbook</span>
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* SUBTAB: NATURAL LANGUAGE INVESTIGATOR */}
              {invSubTab === "nl_investigator" && (
                <InvestigatorTab
                  onRunInvestigation={handleRunInvestigation}
                  onCancelInvestigation={handleCancelInvestigation}
                  activeInvestigation={activeInvestigation}
                  loading={investigating}
                />
              )}

              {/* SUBTAB: EVIDENCE INSPECTOR */}
              {invSubTab === "evidence" && (
                <EvidenceInspectorTab
                  evidenceItems={activeInvestigation?.evidence_items?.length ? activeInvestigation.evidence_items : evidenceItems}
                />
              )}

              {/* SUBTAB: KNOWLEDGE GRAPH */}
              {invSubTab === "graph" && (
                <KnowledgeGraphTab
                  graphData={graphData}
                  loading={loading}
                  onRefreshGraph={fetchGraph}
                />
              )}

              {/* SUBTAB: PATH ANALYSIS */}
              {invSubTab === "paths" && (
                <PathAnalysisTab
                  pathResult={pathResult}
                  loading={loading}
                  onRunPathAnalysis={handleRunPathAnalysis}
                  devices={devices}
                />
              )}

              {/* SUBTAB: RCA TIMELINE */}
              {invSubTab === "rca" && (
                <RcaTimelineTab
                  rcaReport={activeInvestigation?.rca}
                  correlations={activeInvestigation?.correlations || []}
                />
              )}

              {/* SUBTAB: HISTORICAL INTELLIGENCE */}
              {invSubTab === "history" && (
                <HistoricalIntelligenceTab
                  historicalData={historicalData}
                  loading={loading}
                  onCompareSnapshots={handleCompareSnapshots}
                  onRefreshHistory={fetchHistorical}
                />
              )}

              {/* SUBTAB: PLAYBOOK RUNNER */}
              {invSubTab === "playbook" && (
                <div className="space-y-6">
                  <div className="flex items-center justify-between pb-2 border-b border-border">
                    <h3 className="text-sm font-semibold text-white">Diagnostic Playbook Runner</h3>
                    <span className="text-xs text-white/40">State Machine Deterministik</span>
                  </div>

                  {!activePlaybookRun ? (
                    <div className="text-center py-12 space-y-4">
                      <p className="text-xs text-white/50">Belum ada playbook yang sedang berjalan untuk insiden ini.</p>
                      <div className="flex flex-wrap gap-2 justify-center">
                        {playbooks.map((pb) => (
                          <button
                            key={pb.playbook_id}
                            onClick={() => handleStartPlaybook(pb.playbook_id)}
                            className="px-3.5 py-2 rounded-lg bg-white/5 hover:bg-cyan-500/20 border border-white/10 hover:border-cyan-500/40 text-xs text-white transition text-left"
                          >
                            <div className="font-semibold">{pb.name}</div>
                            <div className="text-[10px] text-white/40">{pb.playbook_id}</div>
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <div className="p-4 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-between">
                        <div>
                          <span className="text-xs font-semibold text-cyan-300">Playbook Aktif: {activePlaybookRun.playbook_id}</span>
                          <p className="text-xs text-white/60 mt-0.5">
                            Status: <strong className="text-white">{activePlaybookRun.status}</strong> | Langkah: {activePlaybookRun.current_step_id || "Selesai"}
                          </p>
                        </div>

                        <div className="flex items-center gap-2">
                          {activePlaybookRun.status === "RUNNING" && (
                            <>
                              <button
                                onClick={() => handleAdvancePlaybook("step")}
                                disabled={advancingPlaybook}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black text-xs font-semibold transition"
                              >
                                {advancingPlaybook ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                                <span>Langkah Berikutnya</span>
                              </button>

                              <button
                                onClick={() => handleAdvancePlaybook("cancel")}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/40 text-xs transition"
                              >
                                <StopCircle size={13} />
                                <span>Batalkan</span>
                              </button>
                            </>
                          )}
                        </div>
                      </div>

                      {/* Step Execution Logs */}
                      <div className="space-y-2">
                        <h4 className="text-xs font-semibold text-white/70 uppercase">Log Keputusan Langkah</h4>
                        {activePlaybookRun.step_logs?.map((log, idx) => (
                          <div key={idx} className="p-3 rounded-lg bg-white/5 border border-white/5 text-xs text-white/80 space-y-1">
                            <div className="flex items-center justify-between text-white/40 text-[10px]">
                              <span>{log.step_id || log.event}</span>
                              <span>{new Date((log.timestamp || Date.now() / 1000) * 1000).toLocaleTimeString()}</span>
                            </div>
                            <p>{log.verdict || log.message || log.objective}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* SUBTAB: CONFIGURATION PLANNER */}
              {invSubTab === "planner" && (
                <div className="space-y-6">
                  <div className="flex items-center justify-between pb-2 border-b border-border">
                    <h3 className="text-sm font-semibold text-white">Perencana Konfigurasi &amp; Simulasi Statis</h3>
                    <button
                      onClick={() => setShowNewPlanModal(true)}
                      className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-cyan-500/20 text-cyan-300 text-xs font-semibold border border-cyan-500/40 hover:bg-cyan-500/30 transition"
                    >
                      + Buat Desired State Baru
                    </button>
                  </div>

                  {!selectedPlan ? (
                    <div className="text-center py-16 text-white/40 text-xs">Pilih atau buat rencana konfigurasi.</div>
                  ) : (
                    <div className="space-y-5">
                      <div className="p-4 rounded-xl bg-white/5 border border-border flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="text-sm font-semibold text-white">
                              {selectedPlan.plan_id} — {selectedPlan.desired_state?.change_type}
                            </h4>
                            <span
                              className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                                selectedPlan.plan_status === "VALID_WITH_WARNINGS"
                                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                                  : selectedPlan.plan_status === "READY_FOR_REVIEW"
                                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                                  : "bg-red-500/20 text-red-300 border border-red-500/40"
                              }`}
                            >
                              {selectedPlan.plan_status}
                            </span>
                          </div>
                          <p className="text-xs text-white/50 mt-0.5">
                            Target: {selectedPlan.target_devices?.join(", ")} | Risk: {selectedPlan.risk_level}
                          </p>
                        </div>
                      </div>

                      {/* Diff View */}
                      <div className="space-y-2">
                        <h4 className="text-xs font-semibold text-white/70 uppercase">Diff Konfigurasi (Proposed vs Current)</h4>
                        <div className="p-4 rounded-xl bg-black/60 border border-white/10 font-mono text-xs text-white/80 overflow-x-auto">
                          <pre className="text-emerald-400">{selectedPlan.configuration_diff}</pre>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------- */}
      {/* SECTION 3: ACTION CENTER TAB */}
      {/* ------------------------------------------------------------------- */}
      {activeTab === "actions" && (
        <ActionCenterTab
          actions={actions}
          loading={loadingActions}
          onRefresh={fetchActions}
          onResolveApproval={handleResolveApproval}
          onExecuteAction={handleExecuteAction}
          onOpenPolicyModal={() => setShowPolicyModal(true)}
          onOpenNewActionModal={() => {
            setPrefilledActionData(null);
            setShowNewActionModal(true);
          }}
        />
      )}

      {/* ------------------------------------------------------------------- */}
      {/* MODALS */}
      {/* ------------------------------------------------------------------- */}

      <OnboardDeviceModal
        open={showOnboardModal}
        onClose={() => setShowOnboardModal(false)}
        onOnboardSuccess={() => {
          fetchOverview();
          loadInitialData();
        }}
      />

      <OperationsPolicyModal
        open={showPolicyModal}
        onClose={() => setShowPolicyModal(false)}
      />

      <NewActionModal
        open={showNewActionModal}
        onClose={() => {
          setShowNewActionModal(false);
          setPrefilledActionData(null);
        }}
        onActionCreated={() => {
          fetchActions();
          fetchOverview();
        }}
        devices={devices}
        initialData={prefilledActionData}
      />

      <RouteHistoryModal
        open={routeHistoryOpen}
        onClose={() => setRouteHistoryOpen(false)}
        pushToast={(msg, type) => notify({ type: type || "info", message: msg })}
      />

      {/* Modal: Investigasi Baru */}
      {showNewIncidentModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in">
          <div className="w-full max-w-lg bg-[#0b101b] border border-white/10 rounded-2xl p-6 text-white space-y-4 shadow-2xl">
            <h3 className="text-base font-semibold">Mulai Investigasi Jaringan Baru</h3>
            <form onSubmit={handleCreateIncident} className="space-y-4 text-xs">
              <div>
                <label className="block text-white/70 mb-1">Target Perangkat Router</label>
                <select
                  value={newIncidentForm.device_identity}
                  onChange={(e) => setNewIncidentForm({ ...newIncidentForm, device_identity: e.target.value })}
                  className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-white outline-none focus:border-cyan-400"
                >
                  {devices.map((d) => (
                    <option key={d.name} value={d.name} className="bg-[#0b101b]">
                      {d.name} ({d.host})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-white/70 mb-1">Klasifikasi Skenario</label>
                <select
                  value={newIncidentForm.incident_type}
                  onChange={(e) => setNewIncidentForm({ ...newIncidentForm, incident_type: e.target.value })}
                  className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-white outline-none focus:border-cyan-400"
                >
                  <option value="LAN_NO_INTERNET">LAN Client Cannot Access Internet</option>
                  <option value="DEFAULT_ROUTE_FAILS">Default Route Exists but Fails</option>
                  <option value="NAT_MISMATCH">Suspected NAT Mismatch</option>
                  <option value="FIREWALL_FORWARD_BLOCKED">Firewall Forward-Chain Block</option>
                  <option value="OSPF_ADJACENCY_FAILURE">OSPF Adjacency Failure</option>
                  <option value="BGP_PREFIXES_MISSING">BGP Established but Missing Prefixes</option>
                  <option value="VLAN_TRUNK_FAILURE">VLAN or Trunk Connectivity Failure</option>
                </select>
              </div>

              <div>
                <label className="block text-white/70 mb-1">Target IP Klien / Subnet (Opsional)</label>
                <input
                  placeholder="e.g. 192.168.1.50 atau 10.0.0.0/24"
                  value={newIncidentForm.target_ip}
                  onChange={(e) => setNewIncidentForm({ ...newIncidentForm, target_ip: e.target.value })}
                  className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-white outline-none focus:border-cyan-400 font-mono"
                />
              </div>

              <div>
                <label className="block text-white/70 mb-1">Deskripsi Gejala Masalah</label>
                <textarea
                  rows={3}
                  placeholder="Jelaskan kendala yang dilaporkan operator/user..."
                  value={newIncidentForm.user_description}
                  onChange={(e) => setNewIncidentForm({ ...newIncidentForm, user_description: e.target.value })}
                  className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-white outline-none focus:border-cyan-400"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-white/10">
                <button
                  type="button"
                  onClick={() => setShowNewIncidentModal(false)}
                  className="px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-white transition"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black font-semibold transition"
                >
                  {loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                  <span>Jalankan Analisis</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Rencana Konfigurasi Baru */}
      {showNewPlanModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in">
          <div className="w-full max-w-lg bg-[#0b101b] border border-white/10 rounded-2xl p-6 text-white space-y-4 shadow-2xl">
            <h3 className="text-base font-semibold">Buat Desired State &amp; Rencana Konfigurasi</h3>
            <form onSubmit={handleCreatePlan} className="space-y-4 text-xs">
              <div>
                <label className="block text-white/70 mb-1">Target Router</label>
                <select
                  value={newPlanForm.target_device}
                  onChange={(e) => setNewPlanForm({ ...newPlanForm, target_device: e.target.value })}
                  className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-white outline-none focus:border-cyan-400"
                >
                  {devices.map((d) => (
                    <option key={d.name} value={d.name} className="bg-[#0b101b]">
                      {d.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-white/70 mb-1">Jenis Perubahan (Change Type)</label>
                <select
                  value={newPlanForm.change_type}
                  onChange={(e) => setNewPlanForm({ ...newPlanForm, change_type: e.target.value })}
                  className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-white outline-none focus:border-cyan-400"
                >
                  <option value="ADD_STATIC_ROUTE">Tambah Rute Statis</option>
                  <option value="ADD_VLAN">Tambah VLAN &amp; Subnet</option>
                  <option value="CONFIGURE_NAT">Konfigurasi NAT Masquerade</option>
                </select>
              </div>

              {newPlanForm.change_type === "ADD_STATIC_ROUTE" && (
                <>
                  <div>
                    <label className="block text-white/70 mb-1">Destination Prefix (CIDR)</label>
                    <input
                      required
                      placeholder="e.g. 10.20.0.0/16 atau 0.0.0.0/0"
                      value={newPlanForm.dst_address}
                      onChange={(e) => setNewPlanForm({ ...newPlanForm, dst_address: e.target.value })}
                      className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-white outline-none focus:border-cyan-400 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-white/70 mb-1">Gateway IP / Interface</label>
                    <input
                      required
                      placeholder="e.g. 192.168.1.1 atau ether1"
                      value={newPlanForm.gateway}
                      onChange={(e) => setNewPlanForm({ ...newPlanForm, gateway: e.target.value })}
                      className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-white outline-none focus:border-cyan-400 font-mono"
                    />
                  </div>
                </>
              )}

              {newPlanForm.change_type === "ADD_VLAN" && (
                <>
                  <div>
                    <label className="block text-white/70 mb-1">VLAN ID (1 - 4094)</label>
                    <input
                      required
                      placeholder="e.g. 100"
                      value={newPlanForm.vlan_id}
                      onChange={(e) => setNewPlanForm({ ...newPlanForm, vlan_id: e.target.value })}
                      className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-white outline-none focus:border-cyan-400 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-white/70 mb-1">Bridge / Interface</label>
                    <input
                      required
                      placeholder="e.g. bridge atau ether2"
                      value={newPlanForm.interface}
                      onChange={(e) => setNewPlanForm({ ...newPlanForm, interface: e.target.value })}
                      className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-white outline-none focus:border-cyan-400 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-white/70 mb-1">Subnet Gateway IP (CIDR)</label>
                    <input
                      placeholder="e.g. 192.168.100.1/24"
                      value={newPlanForm.subnet}
                      onChange={(e) => setNewPlanForm({ ...newPlanForm, subnet: e.target.value })}
                      className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-white outline-none focus:border-cyan-400 font-mono"
                    />
                  </div>
                </>
              )}

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-white/10">
                <button
                  type="button"
                  onClick={() => setShowNewPlanModal(false)}
                  className="px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-white transition"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={planning}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black font-semibold transition"
                >
                  {planning ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />}
                  <span>Validasi &amp; Simulasikan Rencana</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
