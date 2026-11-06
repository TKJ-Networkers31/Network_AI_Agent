import { useModalDialog } from "../context/ModalDialogContext.jsx";
// src/pages/AutomationsPage.jsx
//
// AIRA OS — Automations & Scheduled Workflows Workspace
// Master Transformation Directive Section 9:
// - Clean, understandable automation builder for network engineers
// - Interval-based and event-driven triggers
// - 10 standard action templates with parameter inputs
// - Execution history, run status, and duplicate prevention

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Copy,
  History,
  Layers,
  Loader2,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  Shield,
  Trash2,
  Wrench,
  X,
  Zap,
} from "lucide-react";
import TopBar from "../components/TopBar.jsx";
import { useToast } from "../components/Toast.jsx";

export default function AutomationsPage({ onOpenMenu }) {
  const { alert: modalAlert, confirm: modalConfirm, prompt: modalPrompt } = useModalDialog();

  const { notify } = useToast();

  const [automations, setAutomations] = useState([]);
  const [catalog, setCatalog] = useState({});
  const [loading, setLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [selectedJob, setSelectedJob] = useState(null);
  const [executions, setExecutions] = useState([]);
  const [loadingExecs, setLoadingExecs] = useState(false);

  // Form State
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formTriggerType, setFormTriggerType] = useState("INTERVAL");
  const [formInterval, setFormInterval] = useState(300);
  const [formEventType, setFormEventType] = useState("device_offline");
  const [formAction, setFormAction] = useState("check_connectivity");
  const [formApproval, setFormApproval] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const fetchCatalog = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/automations/catalog");
      const json = await res.json();
      if (json.success) setCatalog(json.actions || {});
    } catch {}
  }, []);

  const fetchAutomations = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/automations");
      const json = await res.json();
      if (json.success) setAutomations(json.automations || []);
    } catch {
      notify({ type: "error", message: "Gagal memuat daftar otomasi." });
    } finally {
      setLoading(false);
    }
  }, [notify]);

  const fetchExecutions = useCallback(async (jobId) => {
    setLoadingExecs(true);
    try {
      const res = await fetch(`/api/v1/automations/${jobId}/executions?limit=25`);
      const json = await res.json();
      if (json.success) setExecutions(json.executions || []);
    } catch {
      notify({ type: "error", message: "Gagal memuat log eksekusi." });
    } finally {
      setLoadingExecs(false);
    }
  }, [notify]);

  useEffect(() => {
    fetchCatalog();
    fetchAutomations();
  }, [fetchCatalog, fetchAutomations]);

  const handleCreateAutomation = async (e) => {
    e.preventDefault();
    if (!formName.trim()) {
      notify({ type: "error", message: "Nama otomasi wajib diisi." });
      return;
    }

    setSubmitting(true);
    try {
      const trigger_params =
        formTriggerType === "INTERVAL"
          ? { interval_seconds: Number(formInterval) }
          : { event_type: formEventType };

      const res = await fetch("/api/v1/automations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: formName.trim(),
          description: formDesc.trim(),
          trigger_type: formTriggerType,
          trigger_params,
          action_name: formAction,
          action_params: {},
          target_resources: [],
          approval_required: formApproval,
          notify_on_failure: true,
        }),
      });

      const json = await res.json();
      if (json.success) {
        notify({ type: "success", message: `Otomasi '${formName}' berhasil dibuat!` });
        setIsCreating(false);
        setFormName("");
        setFormDesc("");
        fetchAutomations();
      } else {
        notify({ type: "error", message: json.detail || "Gagal membuat otomasi." });
      }
    } catch {
      notify({ type: "error", message: "Kendala jaringan saat membuat otomasi." });
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggle = async (job) => {
    try {
      const res = await fetch(`/api/v1/automations/${job.job_id}/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_enabled: !job.is_enabled }),
      });
      const json = await res.json();
      if (json.success) {
        notify({
          type: "info",
          message: `Otomasi '${job.name}' ${!job.is_enabled ? "diaktifkan" : "dijeda"}.`,
        });
        fetchAutomations();
      }
    } catch {
      notify({ type: "error", message: "Gagal mengubah status otomasi." });
    }
  };

  const handleRunNow = async (job) => {
    notify({ type: "info", message: `Menjalankan otomasi '${job.name}' sekarang...` });
    try {
      const res = await fetch(`/api/v1/automations/${job.job_id}/run`, { method: "POST" });
      const json = await res.json();
      if (json.success) {
        notify({ type: "success", message: `Hasil: ${json.execution?.result_summary || "Selesai"}` });
        fetchAutomations();
        if (selectedJob?.job_id === job.job_id) fetchExecutions(job.job_id);
      }
    } catch {
      notify({ type: "error", message: "Gagal memicu eksekusi manual." });
    }
  };

  const handleDelete = async (job) => {
    if (!await modalConfirm({ message: `Hapus otomasi '${job.name}'?`, isDestructive: true })) return;
    try {
      const res = await fetch(`/api/v1/automations/${job.job_id}`, { method: "DELETE" });
      const json = await res.json();
      if (json.success) {
        notify({ type: "info", message: `Otomasi '${job.name}' telah dihapus.` });
        if (selectedJob?.job_id === job.job_id) setSelectedJob(null);
        fetchAutomations();
      }
    } catch {
      notify({ type: "error", message: "Gagal menghapus otomasi." });
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-app text-white">
      <TopBar title="Automations & Workflows" onOpenMenu={onOpenMenu} />

      <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 space-y-6">
        {/* Header Summary */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl bg-surface-card/60 border border-white/10 backdrop-blur-md">
          <div className="space-y-1">
            <h1 className="text-lg font-semibold tracking-tight text-white flex items-center gap-2">
              <Zap className="text-cyan-400" size={20} />
              Automasi &amp; Workflow Mandiri
            </h1>
            <p className="text-xs text-white/60 max-w-xl">
              Bangun alur pemantauan, backup konfigurasi, dan pemeriksaan terjadwal
              atau berbasis kejadian tanpa prosedur manual yang rumit.
            </p>
          </div>

          <button
            type="button"
            onClick={() => setIsCreating(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-medium text-xs shadow-lg shadow-cyan-500/20 transition shrink-0"
          >
            <Plus size={15} strokeWidth={2.5} />
            <span>Buat Otomasi Baru</span>
          </button>
        </div>

        {/* Content Area */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* List of Automations (2 Cols) */}
          <div className="lg:col-span-2 space-y-3">
            <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-white/50 px-1">
              <span>Daftar Alur Kerja ({automations.length})</span>
              <button
                type="button"
                onClick={fetchAutomations}
                className="flex items-center gap-1 hover:text-white transition"
              >
                <RefreshCw size={12} /> Segarkan
              </button>
            </div>

            {loading ? (
              <div className="p-12 text-center text-xs text-white/40 flex items-center justify-center gap-2">
                <Loader2 className="animate-spin text-cyan-400" size={16} /> Memuat alur otomasi...
              </div>
            ) : automations.length === 0 ? (
              <div className="p-12 text-center rounded-2xl border border-dashed border-white/10 text-white/40 space-y-2">
                <Clock size={32} className="mx-auto text-white/20 mb-2" />
                <p className="text-sm font-medium text-white/70">Belum ada alur otomasi aktif</p>
                <p className="text-xs">
                  Klik "Buat Otomasi Baru" atau instruksikan AIRA lewat chat untuk menyusun alur kerja terjadwal.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {automations.map((job) => (
                  <div
                    key={job.job_id}
                    onClick={() => {
                      setSelectedJob(job);
                      fetchExecutions(job.job_id);
                    }}
                    className={`p-4 rounded-xl border transition cursor-pointer ${
                      selectedJob?.job_id === job.job_id
                        ? "bg-cyan-500/10 border-cyan-500/40 shadow-lg shadow-cyan-950/20"
                        : "bg-surface-card/40 border-white/10 hover:border-white/20"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-sm text-white truncate">{job.name}</span>
                          <span
                            className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                              job.is_enabled
                                ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                                : "bg-neutral-800 text-neutral-400"
                            }`}
                          >
                            {job.is_enabled ? "Aktif" : "Dijeda"}
                          </span>
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/[0.06] text-white/70 border border-white/10">
                            {job.trigger_type === "INTERVAL"
                              ? `Setiap ${Math.round((job.trigger_params?.interval_seconds || 300) / 60)} menit`
                              : `Event: ${job.trigger_params?.event_type || "kejadian"}`}
                          </span>
                          {job.approval_required && (
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30 flex items-center gap-1">
                              <Shield size={10} /> Konfirmasi Manusia
                            </span>
                          )}
                        </div>

                        {job.description && (
                          <p className="text-xs text-white/60 line-clamp-2">{job.description}</p>
                        )}

                        <div className="flex items-center gap-4 text-[11px] text-white/40 pt-1">
                          <span>Aksi: <strong className="text-white/70">{job.action_info?.name || job.action_name}</strong></span>
                          {job.last_status && (
                            <span className="flex items-center gap-1">
                              Status terakhir:
                              <span
                                className={
                                  job.last_status === "SUCCESS"
                                    ? "text-emerald-400 font-medium"
                                    : "text-rose-400 font-medium"
                                }
                              >
                                {job.last_status}
                              </span>
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          onClick={() => handleRunNow(job)}
                          title="Jalankan Sekarang"
                          className="p-1.5 rounded-lg text-white/60 hover:text-cyan-300 hover:bg-white/10 transition"
                        >
                          <Play size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleToggle(job)}
                          title={job.is_enabled ? "Jeda" : "Aktifkan"}
                          className="p-1.5 rounded-lg text-white/60 hover:text-white hover:bg-white/10 transition"
                        >
                          <Pause size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(job)}
                          title="Hapus Otomasi"
                          className="p-1.5 rounded-lg text-white/40 hover:text-rose-400 hover:bg-rose-500/10 transition"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Execution History Inspector (1 Col) */}
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-white/50 px-1">
              <span>Riwayat Eksekusi</span>
              {selectedJob && (
                <button
                  type="button"
                  onClick={() => fetchExecutions(selectedJob.job_id)}
                  className="hover:text-white transition"
                >
                  <RefreshCw size={12} />
                </button>
              )}
            </div>

            {!selectedJob ? (
              <div className="p-8 text-center rounded-2xl bg-surface-card/30 border border-white/5 text-white/40 text-xs">
                Pilih salah satu alur kerja untuk melihat log eksekusi dan laporan hasil.
              </div>
            ) : (
              <div className="p-4 rounded-2xl bg-surface-card/40 border border-white/10 space-y-4">
                <div className="border-b border-white/10 pb-3">
                  <h3 className="font-semibold text-sm text-white">{selectedJob.name}</h3>
                  <p className="text-[11px] text-white/50 pt-0.5">
                    {selectedJob.trigger_type === "INTERVAL" ? "Interval Otomatis" : "Pemicu Kejadian"}
                  </p>
                </div>

                {loadingExecs ? (
                  <div className="p-6 text-center text-xs text-white/40 flex items-center justify-center gap-2">
                    <Loader2 className="animate-spin text-cyan-400" size={14} /> Memuat log...
                  </div>
                ) : executions.length === 0 ? (
                  <div className="p-6 text-center text-xs text-white/40">
                    Belum ada catatan eksekusi untuk alur ini.
                  </div>
                ) : (
                  <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                    {executions.map((ex) => (
                      <div
                        key={ex.execution_id}
                        className="p-2.5 rounded-xl bg-white/[0.02] border border-white/5 space-y-1 text-xs"
                      >
                        <div className="flex items-center justify-between">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                              ex.status === "SUCCESS"
                                ? "bg-emerald-500/15 text-emerald-300"
                                : ex.status === "APPROVAL_PENDING"
                                ? "bg-amber-500/15 text-amber-300"
                                : "bg-rose-500/15 text-rose-300"
                            }`}
                          >
                            {ex.status}
                          </span>
                          <span className="text-[10px] text-white/40">
                            {new Date(ex.started_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                            {ex.duration_ms ? ` (${ex.duration_ms}ms)` : ""}
                          </span>
                        </div>
                        <p className="text-[11px] text-white/80 line-clamp-2">{ex.result_summary}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Create Automation Modal */}
      {isCreating && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-150">
          <form
            onSubmit={handleCreateAutomation}
            className="w-full max-w-lg p-6 rounded-2xl bg-neutral-900 border border-white/15 shadow-2xl space-y-4 text-xs text-white max-h-[90vh] overflow-y-auto"
          >
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <div className="flex items-center gap-2">
                <Zap className="text-cyan-400" size={18} />
                <h3 className="font-semibold text-sm text-white">Buat Alur Otomasi Baru</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsCreating(false)}
                className="text-white/40 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-[11px] font-medium text-white/70 mb-1">Nama Alur Kerja</label>
                <input
                  type="text"
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="Misal: Pemeriksaan Rutin Router & Switch Cabang"
                  className="w-full px-3 py-2 rounded-xl bg-white/[0.04] border border-white/10 focus:border-cyan-400 focus:outline-none text-white text-xs"
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-white/70 mb-1">Deskripsi Tujuan</label>
                <input
                  type="text"
                  value={formDesc}
                  onChange={(e) => setFormDesc(e.target.value)}
                  placeholder="Penjelasan ringkas alur kerja ini"
                  className="w-full px-3 py-2 rounded-xl bg-white/[0.04] border border-white/10 focus:border-cyan-400 focus:outline-none text-white text-xs"
                />
              </div>

              {/* Trigger Type Selection */}
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setFormTriggerType("INTERVAL")}
                  className={`p-2.5 rounded-xl border text-left transition ${
                    formTriggerType === "INTERVAL"
                      ? "bg-cyan-500/15 border-cyan-500/40 text-cyan-300 font-medium"
                      : "bg-white/[0.02] border-white/10 text-white/60 hover:text-white"
                  }`}
                >
                  <Clock size={14} className="mb-1" />
                  <div className="font-semibold text-xs">Jadwal Berkala</div>
                  <div className="text-[10px] text-white/50">Jalankan per rentang waktu</div>
                </button>

                <button
                  type="button"
                  onClick={() => setFormTriggerType("EVENT")}
                  className={`p-2.5 rounded-xl border text-left transition ${
                    formTriggerType === "EVENT"
                      ? "bg-cyan-500/15 border-cyan-500/40 text-cyan-300 font-medium"
                      : "bg-white/[0.02] border-white/10 text-white/60 hover:text-white"
                  }`}
                >
                  <Zap size={14} className="mb-1" />
                  <div className="font-semibold text-xs">Pemicu Kejadian</div>
                  <div className="text-[10px] text-white/50">Jalankan bila status berubah</div>
                </button>
              </div>

              {formTriggerType === "INTERVAL" ? (
                <div>
                  <label className="block text-[11px] font-medium text-white/70 mb-1">Interval Frekuensi</label>
                  <select
                    value={formInterval}
                    onChange={(e) => setFormInterval(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-xl bg-neutral-800 border border-white/10 focus:border-cyan-400 focus:outline-none text-white text-xs"
                  >
                    <option value={60}>Setiap 1 menit</option>
                    <option value={300}>Setiap 5 menit</option>
                    <option value={900}>Setiap 15 menit</option>
                    <option value={3600}>Setiap 1 jam</option>
                    <option value={86400}>Setiap 1 hari (Harian)</option>
                  </select>
                </div>
              ) : (
                <div>
                  <label className="block text-[11px] font-medium text-white/70 mb-1">Jenis Kejadian Jaringan</label>
                  <select
                    value={formEventType}
                    onChange={(e) => setFormEventType(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-neutral-800 border border-white/10 focus:border-cyan-400 focus:outline-none text-white text-xs"
                  >
                    <option value="device_offline">Perangkat Tidak Merespons / Offline</option>
                    <option value="device_online">Perangkat Kembali Online</option>
                    <option value="interface_status_changed">Status Interface Berubah (Link Flap)</option>
                    <option value="cpu_threshold_exceeded">Beban CPU Melebihi Ambang Batas (&gt; 85%)</option>
                    <option value="new_device_discovered">Perangkat Baru Terdeteksi di Jaringan</option>
                    <option value="monitoring_failed">SNMP / Monitoring Mengalami Kegagalan</option>
                  </select>
                </div>
              )}

              {/* Action Catalog Selector */}
              <div>
                <label className="block text-[11px] font-medium text-white/70 mb-1">Aksi yang Dijalankan</label>
                <select
                  value={formAction}
                  onChange={(e) => setFormAction(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-neutral-800 border border-white/10 focus:border-cyan-400 focus:outline-none text-white text-xs"
                >
                  {Object.entries(catalog).map(([key, act]) => (
                    <option key={key} value={key}>
                      {act.name} {act.risk === "CATEGORY_B" ? "⚠️ (Mutasi)" : ""}
                    </option>
                  ))}
                </select>
                {catalog[formAction] && (
                  <p className="text-[11px] text-white/50 pt-1 italic">
                    {catalog[formAction].description}
                  </p>
                )}
              </div>

              {/* Approval Gate Toggle */}
              <label className="flex items-center gap-2.5 p-3 rounded-xl bg-white/[0.03] border border-white/10 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formApproval}
                  onChange={(e) => setFormApproval(e.target.checked)}
                  className="rounded text-cyan-500 focus:ring-0"
                />
                <div>
                  <span className="font-medium text-white block">Wajibkan Persetujuan Operator</span>
                  <span className="text-[11px] text-white/50 block">
                    Alur akan meminta konfirmasi manual di Approval Center sebelum perubahan diterapkan ke jaringan.
                  </span>
                </div>
              </label>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-white/10">
              <button
                type="button"
                onClick={() => setIsCreating(false)}
                className="px-3.5 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-white/70 hover:text-white transition"
              >
                Batal
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-semibold shadow-lg shadow-cyan-500/20 transition disabled:opacity-50"
              >
                {submitting && <Loader2 className="animate-spin" size={14} />}
                <span>Aktifkan Alur Kerja</span>
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
