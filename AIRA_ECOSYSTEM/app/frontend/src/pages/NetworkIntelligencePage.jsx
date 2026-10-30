// src/pages/NetworkIntelligencePage.jsx
//
// AIRA OS — Network Intelligence, Incident Investigation & Configuration Planning Copilot
// Menampilkan ringkasan insiden, penjelajah bukti observasi, panel hipotesis terurut,
// playbooks diagnostik deterministik, perencana konfigurasi desired-state, validasi statis,
// dan simulasi forwarding. Strictly Read-Only.

import React, { useEffect, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { api } from "../api.js";
import { useToast } from "../components/Toast.jsx";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Code2,
  Cpu,
  FileText,
  HelpCircle,
  History,
  Layers,
  Loader2,
  Network,
  Play,
  RotateCcw,
  Search,
  Server,
  ShieldAlert,
  ShieldCheck,
  StopCircle,
  Terminal,
  Zap,
} from "lucide-react";

export default function NetworkIntelligencePage({ onOpenMenu }) {
  const { notify } = useToast();

  const [activeTab, setActiveTab] = useState("overview"); // overview, evidence, hypotheses, playbook, planner, timeline
  const [incidents, setIncidents] = useState([]);
  const [selectedIncident, setSelectedIncident] = useState(null);
  const [evidenceItems, setEvidenceItems] = useState([]);
  const [playbooks, setPlaybooks] = useState([]);
  const [activePlaybookRun, setActivePlaybookRun] = useState(null);
  const [loading, setLoading] = useState(false);
  const [advancingPlaybook, setAdvancingPlaybook] = useState(false);

  // New incident form state
  const [devices, setDevices] = useState([]);
  const [showNewIncidentModal, setShowNewIncidentModal] = useState(false);
  const [newIncidentForm, setNewIncidentForm] = useState({
    device_identity: "",
    incident_type: "LAN_NO_INTERNET",
    symptoms: "",
    user_description: "",
    target_ip: "",
  });

  // Planner state
  const [plans, setPlans] = useState([]);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [showNewPlanModal, setShowNewPlanModal] = useState(false);
  const [newPlanForm, setNewPlanForm] = useState({
    target_device: "",
    change_type: "ADD_STATIC_ROUTE",
    dst_address: "",
    gateway: "192.168.1.1",
    vlan_id: "100",
    interface: "bridge",
    subnet: "192.168.100.1/24",
  });
  const [planning, setPlanning] = useState(false);

  const loadInitialData = async () => {
    setLoading(true);
    try {
      const [incRes, pbRes, devRes, planRes] = await Promise.all([
        api.intelligence.listIncidents(30).catch(() => ({ incidents: [] })),
        api.intelligence.listPlaybooks().catch(() => ({ playbooks: [] })),
        api.devices().catch(() => ({ devices: [] })),
        api.intelligence.listPlans(30).catch(() => ({ plans: [] })),
      ]);

      setIncidents(incRes.incidents || []);
      setPlaybooks(pbRes.playbooks || []);
      setDevices(devRes.devices || []);
      setPlans(planRes.plans || []);

      if (incRes.incidents?.length > 0 && !selectedIncident) {
        loadIncidentDetail(incRes.incidents[0].incident_id);
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
  }, []);

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

      const res = await api.intelligence.createIncident({
        device_identity: newIncidentForm.device_identity,
        incident_type: newIncidentForm.incident_type,
        symptoms: symptomsArray,
        user_description: newIncidentForm.user_description,
        target_ip: newIncidentForm.target_ip || undefined,
        severity: "HIGH",
      });

      if (res.success) {
        notify({ type: "success", message: "Investigasi insiden selesai dianalisis." });
        setShowNewIncidentModal(false);
        loadInitialData();
        setSelectedIncident(res.incident);
        setActiveTab("overview");
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
        setActiveTab("playbook");
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
        setActiveTab("planner");
      }
    } catch (err) {
      notify({ type: "error", message: err.message || "Gagal membuat rencana." });
    } finally {
      setPlanning(false);
    }
  };

  return (
    <div className="space-y-6">
      <TopBar
        title="Network Intelligence Copilot"
        subtitle="Investigasi Insiden Berbasis Bukti, Diagnostic Playbook & Simulasi Konfigurasi (Read-Only)"
        onMenuClick={onOpenMenu}
      />

      {/* Action Header Banner */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-card border border-border rounded-xl2">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
            <ShieldCheck size={22} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-white">Engineering Intelligence Engine</h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-semibold">
                STRICTLY READ-ONLY
              </span>
            </div>
            <p className="text-xs text-white/50">
              Analisis deterministik router, validasi rule-order, pelacakan rute, dan mitigasi risiko.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowNewIncidentModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black text-xs font-semibold transition"
          >
            <Search size={14} />
            <span>Investigasi Baru</span>
          </button>

          <button
            onClick={() => setShowNewPlanModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-xs font-medium border border-white/10 transition"
          >
            <FileText size={14} />
            <span>Rencana Konfigurasi</span>
          </button>
        </div>
      </div>

      {/* Main Grid: Incident Selector Sidebar & Intelligence Tab Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left Col: Incidents List */}
        <div className="lg:col-span-1 space-y-3">
          <div className="flex items-center justify-between px-1">
            <span className="text-xs font-semibold text-white/70 uppercase tracking-wider">
              Daftar Investigasi ({incidents.length})
            </span>
            <button onClick={loadInitialData} className="text-white/40 hover:text-white transition">
              <RotateCcw size={13} className={loading ? "animate-spin" : ""} />
            </button>
          </div>

          <div className="space-y-2 max-h-[680px] overflow-y-auto pr-1">
            {incidents.length === 0 ? (
              <div className="p-6 text-center text-xs text-white/40 bg-card border border-border rounded-xl">
                Belum ada investigasi insiden.
              </div>
            ) : (
              incidents.map((inc) => {
                const isSelected = selectedIncident?.incident_id === inc.incident_id;
                return (
                  <div
                    key={inc.incident_id}
                    onClick={() => loadIncidentDetail(inc.incident_id)}
                    className={`p-3.5 rounded-xl border text-left cursor-pointer transition ${
                      isSelected
                        ? "bg-cyan-500/10 border-cyan-500/40 text-white"
                        : "bg-card border-border hover:border-white/20 text-white/70"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-xs font-semibold text-white truncate">
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
                      <span>Status: {inc.investigation_status}</span>
                      <span>{new Date(inc.created_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Col: 6-Section Intelligence Workspace */}
        <div className="lg:col-span-3 space-y-4">
          {/* Tab Navigation */}
          <div className="flex items-center gap-1 bg-card border border-border p-1.5 rounded-xl">
            {[
              { id: "overview", label: "A. Overview Insiden", icon: AlertCircle },
              { id: "evidence", label: `B. Bukti Observasi (${evidenceItems.length})`, icon: Layers },
              { id: "hypotheses", label: `C. Hipotesis (${selectedIncident?.inferred_hypotheses?.length || 0})`, icon: Zap },
              { id: "playbook", label: "D. Diagnostic Playbook", icon: Terminal },
              { id: "planner", label: `E. Configuration Planner (${plans.length})`, icon: Code2 },
              { id: "timeline", label: "F. Audit Timeline", icon: History },
            ].map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition ${
                    activeTab === tab.id
                      ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                      : "text-white/60 hover:text-white hover:bg-white/5"
                  }`}
                >
                  <Icon size={14} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {/* Tab Content */}
          <div className="bg-card border border-border rounded-xl2 p-6 min-h-[520px]">
            {/* A. INCIDENT OVERVIEW */}
            {activeTab === "overview" && (
              <div className="space-y-6">
                {!selectedIncident ? (
                  <div className="text-center py-16 text-white/40 text-xs">Pilih insiden untuk melihat overview.</div>
                ) : (
                  <>
                    <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-border">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-base font-semibold text-white">
                            {selectedIncident.device_identity} — {selectedIncident.incident_type}
                          </h3>
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-mono">
                            {selectedIncident.incident_id}
                          </span>
                        </div>
                        <p className="text-xs text-white/50 mt-1">
                          {selectedIncident.user_description || "Pemeriksaan gejala jaringan berbasis bukti."}
                        </p>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-xs text-white/50">Confidence:</span>
                        <span className="text-xs px-2.5 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-semibold">
                          {selectedIncident.confidence}
                        </span>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="p-4 rounded-xl bg-white/[0.02] border border-border">
                        <span className="text-[11px] text-white/50 uppercase">Investigation Status</span>
                        <p className="text-sm font-semibold text-white mt-1">{selectedIncident.investigation_status}</p>
                      </div>
                      <div className="p-4 rounded-xl bg-white/[0.02] border border-border">
                        <span className="text-[11px] text-white/50 uppercase">Tingkat Keparahan</span>
                        <p className="text-sm font-semibold text-amber-400 mt-1">{selectedIncident.severity}</p>
                      </div>
                      <div className="p-4 rounded-xl bg-white/[0.02] border border-border">
                        <span className="text-[11px] text-white/50 uppercase">Waktu Observasi</span>
                        <p className="text-sm font-semibold text-white mt-1">
                          {new Date(selectedIncident.created_at * 1000).toLocaleString()}
                        </p>
                      </div>
                    </div>

                    {/* Facts Quick View */}
                    <div className="space-y-3">
                      <h4 className="text-xs font-semibold text-white/70 uppercase">Fakta Terkonfirmasi (Observed Facts)</h4>
                      <div className="space-y-2">
                        {selectedIncident.observed_facts?.map((fact, idx) => (
                          <div key={idx} className="flex items-start gap-2 p-2.5 rounded-lg bg-white/[0.02] border border-white/5 text-xs text-white/80">
                            <CheckCircle2 size={15} className="text-emerald-400 shrink-0 mt-0.5" />
                            <span>{fact}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Playbook Trigger Bar */}
                    <div className="p-4 rounded-xl bg-cyan-500/5 border border-cyan-500/20 flex items-center justify-between">
                      <div>
                        <h4 className="text-xs font-semibold text-cyan-300">Jalankan Diagnostic Playbook</h4>
                        <p className="text-[11px] text-white/50">
                          Mulai rangkaian pengujian berurutan untuk memverifikasi akar masalah.
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

            {/* B. EVIDENCE EXPLORER */}
            {activeTab === "evidence" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-border">
                  <h3 className="text-sm font-semibold text-white">Item Bukti Observasi Read-Only</h3>
                  <span className="text-xs text-white/40">{evidenceItems.length} artefak terkumpul</span>
                </div>

                {evidenceItems.length === 0 ? (
                  <div className="text-center py-16 text-white/40 text-xs">Belum ada data bukti yang tersimpan.</div>
                ) : (
                  <div className="space-y-3">
                    {evidenceItems.map((item) => (
                      <div key={item.evidence_id} className="p-4 rounded-xl bg-white/[0.02] border border-border space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-white">{item.observation_type}</span>
                            <span className="text-[10px] px-2 py-0.5 rounded bg-white/5 text-white/60 font-mono">
                              {item.source_command}
                            </span>
                          </div>
                          <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                            {item.collection_status}
                          </span>
                        </div>

                        {/* Raw excerpt with redaction */}
                        <div className="p-3 rounded-lg bg-black/50 border border-white/5 font-mono text-xs text-white/70 overflow-x-auto max-h-40">
                          <pre>{item.raw_excerpt || JSON.stringify(item.normalized_value, null, 2)}</pre>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* C. HYPOTHESES PANEL */}
            {activeTab === "hypotheses" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-border">
                  <h3 className="text-sm font-semibold text-white">Hipotesis Akar Masalah Terurut</h3>
                  <span className="text-xs text-white/40">Berdasarkan fakta deterministik</span>
                </div>

                {!selectedIncident?.inferred_hypotheses?.length ? (
                  <div className="text-center py-16 text-white/40 text-xs">Tidak ada hipotesis aktif.</div>
                ) : (
                  <div className="space-y-4">
                    {selectedIncident.inferred_hypotheses.map((h, idx) => (
                      <div key={idx} className="p-5 rounded-xl bg-white/[0.02] border border-border space-y-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="w-5 h-5 rounded-full bg-cyan-500/20 text-cyan-300 text-xs flex items-center justify-center font-bold">
                              {idx + 1}
                            </span>
                            <h4 className="text-sm font-semibold text-white">{h.title}</h4>
                          </div>
                          <span className="text-xs px-2.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
                            Confidence: {h.confidence}
                          </span>
                        </div>

                        <p className="text-xs text-white/70">{h.explanation}</p>

                        {h.confidence_explanation && (
                          <p className="text-[11px] text-cyan-400/80 italic">{h.confidence_explanation}</p>
                        )}

                        {h.alternative_explanations?.length > 0 && (
                          <div className="text-[11px] text-white/50 space-y-0.5">
                            <span className="font-semibold text-white/70">Alternatif dianalisis: </span>
                            <span>{h.alternative_explanations.join(", ")}</span>
                          </div>
                        )}

                        {h.recommended_test && (
                          <div className="p-3 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-xs text-cyan-300 flex items-start gap-2">
                            <Zap size={14} className="shrink-0 mt-0.5" />
                            <span>Rekomendasi Uji Lanjutan: {h.recommended_test}</span>
                          </div>
                        )}

                        {h.known_limitations?.length > 0 && (
                          <div className="p-2.5 rounded-lg bg-amber-500/5 border border-amber-500/20 text-[11px] text-amber-300/80">
                            <span className="font-semibold text-amber-300">Batasan Observasi: </span>
                            {h.known_limitations.join(" ")}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* D. DIAGNOSTIC PLAYBOOK */}
            {activeTab === "playbook" && (
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
                        <div key={idx} className="p-3 rounded-lg bg-white/[0.02] border border-white/5 text-xs text-white/80 space-y-1">
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

            {/* E. CONFIGURATION PLANNER & SIMULATOR */}
            {activeTab === "planner" && (
              <div className="space-y-6">
                <div className="flex items-center justify-between pb-2 border-b border-border">
                  <h3 className="text-sm font-semibold text-white">Perencana Konfigurasi & Simulasi Statis</h3>
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
                    {/* Plan Header */}
                    <div className="p-4 rounded-xl bg-white/[0.02] border border-border flex flex-wrap items-center justify-between gap-3">
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

                      {selectedPlan.management_connectivity_risk && (
                        <div className="p-2.5 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-300 text-xs flex items-center gap-2">
                          <AlertTriangle size={15} />
                          <span>Risiko Jalur Manajemen Terdeteksi</span>
                        </div>
                      )}
                    </div>

                    {/* Diff View */}
                    <div className="space-y-2">
                      <h4 className="text-xs font-semibold text-white/70 uppercase">Diff Konfigurasi (Proposed vs Current)</h4>
                      <div className="p-4 rounded-xl bg-black/60 border border-white/10 font-mono text-xs text-white/80 overflow-x-auto">
                        <pre className="text-emerald-400">{selectedPlan.configuration_diff}</pre>
                      </div>
                    </div>

                    {/* Validation Findings */}
                    <div className="space-y-2">
                      <h4 className="text-xs font-semibold text-white/70 uppercase">Hasil Validasi Statis Deterministik</h4>
                      {selectedPlan.validation_results?.length === 0 ? (
                        <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300">
                          Validasi statis lulus tanpa temuan memblokir.
                        </div>
                      ) : (
                        selectedPlan.validation_results.map((f, idx) => (
                          <div
                            key={idx}
                            className={`p-3 rounded-lg border text-xs ${
                              f.severity === "ERROR"
                                ? "bg-red-500/10 border-red-500/30 text-red-300"
                                : "bg-amber-500/10 border-amber-500/30 text-amber-300"
                            }`}
                          >
                            <span className="font-semibold uppercase font-mono mr-2">[{f.rule_id}]</span>
                            <span>{f.description}</span>
                          </div>
                        ))
                      )}
                    </div>

                    {/* Forwarding Simulation */}
                    {selectedPlan.simulation_results && (
                      <div className="space-y-3 p-4 rounded-xl bg-white/[0.02] border border-border">
                        <div className="flex items-center justify-between">
                          <h4 className="text-xs font-semibold text-white/70 uppercase">Simulasi Forwarding LPM</h4>
                          <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 font-mono">
                            {selectedPlan.simulation_results.simulation_status}
                          </span>
                        </div>

                        {/* Unmodeled Disclosures Notice */}
                        <div className="p-3 rounded-lg bg-white/5 border border-white/10 text-xs text-white/60 space-y-1">
                          <div className="font-semibold text-white/80">Batasan Model Forwarding Statis:</div>
                          <ul className="list-disc list-inside space-y-0.5 text-[11px]">
                            {selectedPlan.simulation_results.unmodeled_behavior?.slice(0, 3).map((u, i) => (
                              <li key={i}>{u}</li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* F. AUDIT TIMELINE */}
            {activeTab === "timeline" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-border">
                  <h3 className="text-sm font-semibold text-white">Jejak Audit Investigasi & Perencanaan</h3>
                  <span className="text-xs text-white/40">Immutable Audit Trail</span>
                </div>

                <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-white/10">
                  <div className="relative">
                    <span className="absolute -left-6 top-1 w-3 h-3 rounded-full bg-cyan-400 ring-4 ring-[#0b101b]" />
                    <div className="text-xs font-semibold text-white">Investigasi Dibuat</div>
                    <p className="text-[11px] text-white/50">
                      Target {selectedIncident?.device_identity} diresolusi via CanonicalNetworkRegistry.
                    </p>
                  </div>

                  <div className="relative">
                    <span className="absolute -left-6 top-1 w-3 h-3 rounded-full bg-emerald-400 ring-4 ring-[#0b101b]" />
                    <div className="text-xs font-semibold text-white">Pengumpulan Bukti Read-Only Selesai</div>
                    <p className="text-[11px] text-white/50">
                      {evidenceItems.length} tabel RouterOS dinormalisasi tanpa membebani CPU router.
                    </p>
                  </div>

                  <div className="relative">
                    <span className="absolute -left-6 top-1 w-3 h-3 rounded-full bg-purple-400 ring-4 ring-[#0b101b]" />
                    <div className="text-xs font-semibold text-white">Evaluasi Hipotesis & Simulasi Rencana</div>
                    <p className="text-[11px] text-white/50">
                      Perintah kandidat divalidasi terhadap subnet overlap dan risiko jalur manajemen.
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

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
            <h3 className="text-base font-semibold">Buat Desired State & Rencana Konfigurasi</h3>
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
                  <option value="ADD_VLAN">Tambah VLAN & Subnet</option>
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
                  <span>Validasi & Simulasikan Rencana</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
