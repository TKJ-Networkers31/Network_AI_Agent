// src/components/network-intelligence/NewActionModal.jsx
//
// AIRA OS — Action Proposal Modal (Workstream E).
// Allows proposing an evidence-backed network configuration or remediation action.

import React, { useState } from "react";
import {
  FileCode2,
  Plus,
  Server,
  ShieldAlert,
  Sparkles,
  X,
} from "lucide-react";
import { api } from "../../api.js";
import { useToast } from "../Toast.jsx";

export default function NewActionModal({
  isOpen,
  open,
  onClose,
  onActionCreated,
  devices = [],
  initialData = null,
}) {
  const { notify } = useToast();
  const isVisible = open !== undefined ? open : isOpen;

  const [form, setForm] = useState({
    action_name: "",
    target_devices: "",
    description: "",
    reason: "",
    diff_text: "",
    verification_plan: "",
    rollback_plan: "",
    rollback_supported: true,
  });

  const [saving, setSaving] = useState(false);

  React.useEffect(() => {
    if (initialData) {
      setForm((prev) => ({
        ...prev,
        action_name: initialData.action_name || (initialData.action_type ? `${initialData.action_type} - ${initialData.target_device || ""}` : prev.action_name),
        target_devices: Array.isArray(initialData.target_devices)
          ? initialData.target_devices.join(", ")
          : (initialData.target_device || prev.target_devices),
        description: initialData.description || prev.description,
        reason: initialData.reason || initialData.rationale || prev.reason,
        diff_text: initialData.diff_text || (initialData.commands ? initialData.commands.join("\n") : prev.diff_text),
      }));
    }
  }, [initialData, isVisible]);

  if (!isVisible) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.action_name.trim() || !form.description.trim() || !form.reason.trim()) {
      notify({ type: "error", message: "Nama tindakan, deskripsi, dan alasan wajib diisi." });
      return;
    }

    setSaving(true);
    try {
      const devices = form.target_devices
        .split(",")
        .map((d) => d.trim())
        .filter(Boolean);

      const res = await api.intelligence.proposeAction({
        action_name: form.action_name.trim(),
        target_devices: devices,
        description: form.description.trim(),
        reason: form.reason.trim(),
        diff_text: form.diff_text.trim(),
        verification_plan: form.verification_plan.trim() || "Pemeriksaan telemetri NMS dan routing table",
        rollback_plan: form.rollback_plan.trim() || "Kembalikan konfigurasi via backup snapshot",
        rollback_supported: form.rollback_supported,
      });

      if (res.success) {
        notify({ type: "success", message: "Tindakan berhasil diusulkan dan masuk ke antrean.", duration: 2500 });
        if (onActionCreated) onActionCreated(res.action);
        onClose();
      }
    } catch (err) {
      notify({ type: "error", message: `Gagal mengusulkan: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs overflow-y-auto">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg p-6 shadow-2xl relative my-8 space-y-4">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-white/40 hover:text-white p-1"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white">Usulkan Tindakan Jaringan Baru</h3>
            <p className="text-xs text-white/50">
              Setiap tindakan akan dievaluasi tingkat risikonya dan dikontrol melalui policy approval.
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3.5 text-xs">
          <div>
            <label className="block text-xs font-medium text-white/70 mb-1">Nama Tindakan</label>
            <input
              type="text"
              value={form.action_name}
              onChange={(e) => setForm({ ...form, action_name: e.target.value })}
              placeholder="Mis. Reroute Traffic ke Gateway Cadangan atau Aktifkan Link Uplink sfp2"
              className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-cyan-400"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-white/70 mb-1">Target Perangkat (Pisahkan Koma)</label>
            <input
              type="text"
              value={form.target_devices}
              onChange={(e) => setForm({ ...form, target_devices: e.target.value })}
              placeholder="Core-R1, Edge-SW2"
              className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-xs text-white font-mono outline-none focus:border-cyan-400"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-white/70 mb-1">Deskripsi Perubahan</label>
              <textarea
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                rows={3}
                placeholder="Ubah default route gateway dari 10.0.0.1 ke 10.0.0.254..."
                className="w-full bg-white/5 border border-border rounded-lg p-2.5 text-xs text-white outline-none focus:border-cyan-400"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-white/70 mb-1">Alasan & Bukti Pendukung</label>
              <textarea
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
                rows={3}
                placeholder="Gateway primer mengalami packet loss 45% dan latency spike 180ms..."
                className="w-full bg-white/5 border border-border rounded-lg p-2.5 text-xs text-white outline-none focus:border-cyan-400"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-white/70 mb-1">Perubahan Konfigurasi yang Direncanakan (Diff)</label>
            <textarea
              value={form.diff_text}
              onChange={(e) => setForm({ ...form, diff_text: e.target.value })}
              rows={3}
              placeholder="+ /ip route set [find dst-address=0.0.0.0/0] gateway=10.0.0.254 distance=1&#10;- /ip route set [find dst-address=0.0.0.0/0] gateway=10.0.0.1"
              className="w-full bg-black/40 border border-border rounded-lg p-2.5 text-[11px] font-mono text-emerald-300 outline-none focus:border-cyan-400"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-white/70 mb-1">Rencana Verifikasi Pasca-Tindakan</label>
              <input
                type="text"
                value={form.verification_plan}
                onChange={(e) => setForm({ ...form, verification_plan: e.target.value })}
                placeholder="Ping ke 8.8.8.8 & cek route active status"
                className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-cyan-400"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-white/70 mb-1">Rencana Pemulihan (Rollback)</label>
              <input
                type="text"
                value={form.rollback_plan}
                onChange={(e) => setForm({ ...form, rollback_plan: e.target.value })}
                placeholder="Kembalikan gateway ke 10.0.0.1"
                className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-cyan-400"
              />
            </div>
          </div>

          <label className="flex items-center gap-2 cursor-pointer pt-1">
            <input
              type="checkbox"
              checked={form.rollback_supported}
              onChange={(e) => setForm({ ...form, rollback_supported: e.target.checked })}
              className="accent-cyan-400"
            />
            <span className="text-white/80 text-[11px]">Dukungan Rollback Otomatis Tersedia</span>
          </label>

          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="text-xs px-4 py-2 rounded-lg border border-border bg-white/5 hover:bg-white/10 text-white/70 transition-colors"
            >
              Batal
            </button>
            <button
              type="submit"
              disabled={saving}
              className="text-xs font-semibold px-5 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black transition-colors disabled:opacity-50"
            >
              {saving ? "Menyimpan..." : "Usulkan Tindakan"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
