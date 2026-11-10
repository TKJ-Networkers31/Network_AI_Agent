// src/components/network-intelligence/ActionCenterTab.jsx
//
// AIRA OS — Action Center (Workstream B & E).
// Manages Proposed Actions, Pending Approvals, Executions, and Post-Verification.
// Enforces 5-tier risk taxonomy (READ_ONLY, LOW, MEDIUM, HIGH, CRITICAL) and admin policies.

import React, { useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Eye,
  FileCode2,
  Play,
  RefreshCw,
  RotateCcw,
  Server,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Trash2,
  X,
  XCircle,
} from "lucide-react";

export default function ActionCenterTab({
  actions = [],
  loading = false,
  onRefresh,
  onResolveApproval,
  onExecuteAction,
  onOpenPolicyModal,
  onOpenNewActionModal,
}) {
  const [filterStatus, setFilterStatus] = useState("ALL");
  const [selectedAction, setSelectedAction] = useState(null);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [confirmType, setConfirmType] = useState("APPROVE"); // APPROVE, REJECT, EXECUTE
  const [reviewNotes, setReviewNotes] = useState("");
  const [processing, setProcessing] = useState(false);

  const riskColors = {
    READ_ONLY: "text-blue-400 border-blue-500/30 bg-blue-500/10",
    LOW: "text-white/70 border-white/20 bg-white/5",
    MEDIUM: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    HIGH: "text-orange-400 border-orange-500/30 bg-orange-500/10",
    CRITICAL: "text-rose-400 border-rose-500/30 bg-rose-500/10",
  };

  const statusBadges = {
    PROPOSED: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10",
    PENDING_APPROVAL: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    APPROVED: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
    REJECTED: "text-white/50 border-white/20 bg-white/5",
    EXECUTING: "text-cyan-300 border-cyan-400/40 bg-cyan-500/20 animate-pulse",
    SUCCESS: "text-emerald-300 border-emerald-500/40 bg-emerald-500/20",
    PARTIAL_SUCCESS: "text-amber-300 border-amber-500/40 bg-amber-500/20",
    FAILED: "text-rose-400 border-rose-500/40 bg-rose-500/20",
    VERIFICATION_REQUIRED: "text-orange-400 border-orange-500/40 bg-orange-500/20",
    RECOVERY_REQUIRED: "text-rose-300 border-rose-600/50 bg-rose-600/20",
  };

  const filteredActions = actions.filter((act) => {
    if (filterStatus === "ALL") return true;
    if (filterStatus === "PENDING") return act.status === "PENDING_APPROVAL";
    if (filterStatus === "APPROVED") return act.status === "APPROVED";
    if (filterStatus === "EXECUTED") return ["SUCCESS", "PARTIAL_SUCCESS", "EXECUTING"].includes(act.status);
    if (filterStatus === "FAILED") return ["FAILED", "REJECTED", "RECOVERY_REQUIRED"].includes(act.status);
    return true;
  });

  const pendingCount = actions.filter((a) => a.status === "PENDING_APPROVAL").length;

  const handleOpenConfirm = (act, type) => {
    setSelectedAction(act);
    setConfirmType(type);
    setReviewNotes("");
    setShowConfirmModal(true);
  };

  const handleConfirmSubmit = async () => {
    if (!selectedAction) return;
    setProcessing(true);
    try {
      if (confirmType === "APPROVE") {
        await onResolveApproval(selectedAction.action_id, true, reviewNotes);
      } else if (confirmType === "REJECT") {
        await onResolveApproval(selectedAction.action_id, false, reviewNotes);
      } else if (confirmType === "EXECUTE") {
        await onExecuteAction(selectedAction.action_id);
      }
      setShowConfirmModal(false);
      setSelectedAction(null);
      if (onRefresh) onRefresh();
    } catch (err) {
      console.error(err);
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Controls Bar */}
      <div className="bg-card border border-border p-5 rounded-xl shadow-lg flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-white tracking-wide">Action Center & Persetujuan Operasi</h2>
            {pendingCount > 0 && (
              <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                {pendingCount} Menunggu Persetujuan
              </span>
            )}
          </div>
          <p className="text-xs text-white/60 mt-0.5">
            Pemisahan ketat antara observasi, keputusan AI, dan eksekusi jaringan. Tindakan High/Critical wajib persetujuan manusia.
          </p>
        </div>

        <div className="flex items-center gap-2 self-stretch md:self-auto">
          <button
            onClick={onOpenPolicyModal}
            className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg border border-border bg-white/5 hover:bg-white/10 text-white transition-colors"
          >
            <Sliders className="w-3.5 h-3.5 text-cyan-400" />
            AI Operations Policy
          </button>
          <button
            onClick={onOpenNewActionModal}
            className="flex items-center gap-1.5 text-xs font-semibold px-4 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black transition-colors"
          >
            + Usulkan Tindakan
          </button>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="p-2 rounded-lg border border-border bg-white/5 hover:bg-white/10 text-white/60 hover:text-white transition-colors"
            title="Refresh Actions"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-cyan-400" : ""}`} />
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {[
          { id: "ALL", label: `Semua Tindakan (${actions.length})` },
          { id: "PENDING", label: `Menunggu Persetujuan (${pendingCount})` },
          { id: "APPROVED", label: "Disetujui" },
          { id: "EXECUTED", label: "Selesai Dieksekusi" },
          { id: "FAILED", label: "Ditolak / Gagal" },
        ].map((f) => (
          <button
            key={f.id}
            onClick={() => setFilterStatus(f.id)}
            className={`text-xs px-3 py-1.5 rounded-lg whitespace-nowrap transition-colors border ${
              filterStatus === f.id
                ? "bg-cyan-500/15 border-cyan-500 text-white font-medium"
                : "bg-white/5 border-border text-white/60 hover:bg-white/10"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Action Cards List */}
      <div className="space-y-4">
        {loading && actions.length === 0 ? (
          <div className="bg-card border border-border p-8 rounded-xl text-center text-xs text-white/50">
            <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-cyan-400" />
            Memuat daftar tindakan operasional...
          </div>
        ) : filteredActions.length === 0 ? (
          <div className="bg-card border border-border p-10 rounded-xl text-center">
            <div className="w-12 h-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-white/40 mx-auto mb-3">
              <ShieldCheck className="w-6 h-6 text-emerald-400" />
            </div>
            <h3 className="text-sm font-semibold text-white mb-1">Tidak Ada Tindakan dalam Kategori Ini</h3>
            <p className="text-xs text-white/50 max-w-md mx-auto">
              Seluruh usulan perubahan konfigurasi, perbaikan routing, atau pemeliharaan interface akan muncul di sini bersama bukti dan rencana verifikasi.
            </p>
          </div>
        ) : (
          filteredActions.map((act) => (
            <div
              key={act.action_id}
              className="bg-card border border-border hover:border-cyan-500/30 p-5 rounded-xl transition-colors space-y-4 shadow-md"
            >
              {/* Card Header */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-white/5 pb-3">
                <div className="flex items-center gap-3">
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-bold tracking-wider uppercase border ${
                      riskColors[act.risk_level] || riskColors.LOW
                    }`}
                  >
                    {act.risk_level}
                  </span>
                  <div>
                    <h3 className="text-sm font-bold text-white">{act.action_name}</h3>
                    <div className="flex items-center gap-2 text-[11px] text-white/50 font-mono mt-0.5">
                      <span>ID: {act.action_id}</span>
                      <span>•</span>
                      <span>Target: {(act.target_devices || []).join(", ") || "Global"}</span>
                    </div>
                  </div>
                </div>

                <span
                  className={`px-2.5 py-1 rounded-full text-xs font-semibold tracking-wider uppercase border self-start sm:self-auto ${
                    statusBadges[act.status] || statusBadges.PROPOSED
                  }`}
                >
                  {act.status.replace("_", " ")}
                </span>
              </div>

              {/* Description & Reason */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                <div className="bg-white/5 border border-border/50 rounded-lg p-3">
                  <span className="text-[10px] uppercase font-mono text-white/40 block mb-1">Deskripsi Tindakan</span>
                  <p className="text-white/80 leading-relaxed">{act.description}</p>
                </div>
                <div className="bg-white/5 border border-border/50 rounded-lg p-3">
                  <span className="text-[10px] uppercase font-mono text-white/40 block mb-1">Alasan & Bukti Pendukung</span>
                  <p className="text-white/80 leading-relaxed">{act.reason}</p>
                </div>
              </div>

              {/* Diff / Configuration Changes */}
              {act.diff_text && (
                <div className="bg-black/40 border border-border/70 rounded-lg p-3">
                  <span className="text-[10px] uppercase font-mono text-cyan-400 block mb-1 flex items-center gap-1.5">
                    <FileCode2 className="w-3 h-3" />
                    Perubahan Konfigurasi yang Direncanakan (Diff)
                  </span>
                  <pre className="text-[11px] font-mono text-emerald-300 overflow-x-auto whitespace-pre-wrap leading-relaxed">
                    {act.diff_text}
                  </pre>
                </div>
              )}

              {/* Verification & Rollback Plans */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs bg-white/2 rounded-lg p-3 border border-white/5">
                <div>
                  <span className="text-[10px] uppercase font-mono text-white/40 block">Rencana Verifikasi:</span>
                  <span className="text-white/70 font-mono text-[11px]">{act.verification_plan || "Pemeriksaan telemetri otomatis"}</span>
                </div>
                <div>
                  <span className="text-[10px] uppercase font-mono text-white/40 block">Dukungan Rollback:</span>
                  <span className={`font-mono text-[11px] ${act.rollback_supported ? "text-emerald-400" : "text-amber-400"}`}>
                    {act.rollback_supported ? "Tersedia Otomatis" : "Prosedur Manual Diperlukan"}
                  </span>
                </div>
              </div>

              {/* Verification Results if Executed */}
              {act.verification_result && (
                <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-3 text-xs">
                  <div className="flex items-center gap-1.5 text-emerald-400 font-semibold mb-1">
                    <CheckCircle2 className="w-4 h-4" />
                    Hasil Verifikasi Pasca-Eksekusi: Status Berhasil
                  </div>
                  <div className="text-[11px] text-white/70 font-mono">
                    Pemeriksaan selesai pada {act.verification_result.verified_at}. Kondisi aktual sesuai spesifikasi.
                  </div>
                </div>
              )}

              {/* Controls Footer */}
              <div className="flex items-center justify-between pt-2 border-t border-white/5 text-xs">
                <span className="text-white/40 text-[11px]">
                  Diajukan oleh: {act.requester_id} • {act.created_at ? new Date(act.created_at).toLocaleTimeString("id-ID") : "-"}
                </span>

                <div className="flex items-center gap-2">
                  {act.status === "PENDING_APPROVAL" && (
                    <>
                      <button
                        onClick={() => handleOpenConfirm(act, "REJECT")}
                        className="px-3 py-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 font-medium transition-colors"
                      >
                        Tolak
                      </button>
                      <button
                        onClick={() => handleOpenConfirm(act, "APPROVE")}
                        className="px-4 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black font-semibold transition-colors"
                      >
                        Setujui Tindakan
                      </button>
                    </>
                  )}

                  {act.status === "APPROVED" && (
                    <button
                      onClick={() => handleOpenConfirm(act, "EXECUTE")}
                      className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black font-semibold transition-colors"
                    >
                      <Play className="w-3.5 h-3.5 fill-current" />
                      Eksekusi Sekarang
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Confirmation Modal */}
      {showConfirmModal && selectedAction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs">
          <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 shadow-2xl relative space-y-4">
            <button
              onClick={() => setShowConfirmModal(false)}
              className="absolute top-4 right-4 text-white/40 hover:text-white p-1"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex items-center gap-3">
              <div
                className={`p-2.5 rounded-xl border ${
                  confirmType === "APPROVE"
                    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                    : confirmType === "REJECT"
                    ? "bg-rose-500/10 border-rose-500/30 text-rose-400"
                    : "bg-cyan-500/10 border-cyan-500/30 text-cyan-400"
                }`}
              >
                {confirmType === "APPROVE" ? (
                  <CheckCircle2 className="w-6 h-6" />
                ) : confirmType === "REJECT" ? (
                  <XCircle className="w-6 h-6" />
                ) : (
                  <Play className="w-6 h-6" />
                )}
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">
                  {confirmType === "APPROVE"
                    ? "Konfirmasi Persetujuan Tindakan"
                    : confirmType === "REJECT"
                    ? "Konfirmasi Penolakan Tindakan"
                    : "Konfirmasi Eksekusi Jaringan"}
                </h3>
                <span className="text-xs text-white/50">{selectedAction.action_name}</span>
              </div>
            </div>

            <p className="text-xs text-white/70 leading-relaxed">
              {confirmType === "APPROVE"
                ? `Anda akan menyetujui tindakan [${selectedAction.risk_level}] pada perangkat ${(selectedAction.target_devices || []).join(", ")}. Tindakan ini akan diberi izin untuk dieksekusi.`
                : confirmType === "REJECT"
                ? "Tindakan ini akan ditolak dan dibatalkan dari antrean operasional."
                : `VERA akan menjalankan perubahan konfigurasi pada ${(selectedAction.target_devices || []).join(", ")} dan langsung memverifikasi hasilnya.`}
            </p>

            {confirmType !== "EXECUTE" && (
              <div>
                <label className="block text-xs font-medium text-white/70 mb-1">Catatan Operator / Reviewer</label>
                <input
                  type="text"
                  value={reviewNotes}
                  onChange={(e) => setReviewNotes(e.target.value)}
                  placeholder="Alasan persetujuan/penolakan..."
                  className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-cyan-400"
                />
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowConfirmModal(false)}
                className="text-xs px-4 py-2 rounded-lg border border-border bg-white/5 hover:bg-white/10 text-white/70 transition-colors"
              >
                Batal
              </button>
              <button
                type="button"
                disabled={processing}
                onClick={handleConfirmSubmit}
                className={`text-xs font-semibold px-4 py-2 rounded-lg transition-colors text-black disabled:opacity-50 ${
                  confirmType === "APPROVE"
                    ? "bg-emerald-500 hover:bg-emerald-400"
                    : confirmType === "REJECT"
                    ? "bg-rose-500 hover:bg-rose-400 text-white"
                    : "bg-cyan-500 hover:bg-cyan-400"
                }`}
              >
                {processing ? "Memproses..." : confirmType === "APPROVE" ? "Ya, Setujui" : confirmType === "REJECT" ? "Tolak Tindakan" : "Jalankan Sekarang"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
