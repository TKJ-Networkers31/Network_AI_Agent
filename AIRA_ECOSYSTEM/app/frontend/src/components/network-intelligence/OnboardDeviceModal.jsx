// src/components/network-intelligence/OnboardDeviceModal.jsx
//
// AIRA OS — Automatic Device Onboarding Modal (Workstream D).
// Validates credentials, tests connectivity, runs read-only discovery, reconciles topology,
// registers into NMS, and produces an evidence-based AI summary.

import React, { useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Cpu,
  Eye,
  EyeOff,
  Key,
  Network,
  RefreshCw,
  Server,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { api } from "../../api.js";
import { useToast } from "../Toast.jsx";

export default function OnboardDeviceModal({ isOpen, onClose, onOnboardSuccess }) {
  const { notify } = useToast();

  const [form, setForm] = useState({
    name: "",
    host: "",
    port: 22,
    device_type: "ROUTER",
    vendor: "MikroTik",
    username: "",
    password: "",
  });

  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim() || !form.host.trim()) {
      notify({ type: "error", message: "Nama perangkat dan IP host wajib diisi." });
      return;
    }

    setLoading(true);
    setResult(null);
    try {
      const res = await api.intelligence.onboardDevice({
        name: form.name.trim(),
        host: form.host.trim(),
        port: parseInt(form.port, 10) || 22,
        device_type: form.device_type,
        vendor: form.vendor,
        username: form.username.trim() || null,
        password: form.password || null,
      });

      setResult(res);
      if (res.connection_status === "REACHABLE") {
        notify({ type: "success", message: `Perangkat ${form.name} berhasil di-onboard & di-discovery!`, duration: 3000 });
      } else {
        notify({ type: "warning", message: `Perangkat tersimpan, tetapi koneksi tidak dapat dijangkau.`, duration: 3000 });
      }
      if (onOnboardSuccess) onOnboardSuccess(res);
    } catch (err) {
      notify({ type: "error", message: `Gagal onboarding: ${err.message}` });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-xs overflow-y-auto">
      <div className="bg-card border border-border rounded-xl w-full max-w-xl p-6 shadow-2xl relative my-8 space-y-5">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-white/40 hover:text-white p-1"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Modal Header */}
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
            <Server className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white">Daftarkan & Onboard Perangkat Jaringan</h3>
            <p className="text-xs text-white/50">
              Otomatisasi pengujian koneksi, discovery kapabilitas read-only, rekonsiliasi topologi, dan pendaftaran NMS.
            </p>
          </div>
        </div>

        {!result ? (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-white/70 mb-1">Nama Perangkat (Identity)</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Mis. Core-R1 atau Dist-SW2"
                  className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-cyan-400"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-white/70 mb-1">Tipe & Vendor Perangkat</label>
                <select
                  value={form.device_type}
                  onChange={(e) => setForm({ ...form, device_type: e.target.value })}
                  className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-cyan-400"
                >
                  <option value="ROUTER" className="bg-card">Router (MikroTik RouterOS)</option>
                  <option value="SWITCH" className="bg-card">Switch (Managed Layer 2/3)</option>
                  <option value="FIREWALL" className="bg-card">Firewall / Gateway</option>
                  <option value="ACCESS_POINT" className="bg-card">Access Point (WLAN / CAPsMAN)</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div className="col-span-2">
                <label className="block text-xs font-medium text-white/70 mb-1">IP Host Manajemen</label>
                <input
                  type="text"
                  value={form.host}
                  onChange={(e) => setForm({ ...form, host: e.target.value })}
                  placeholder="192.168.88.1"
                  className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-xs text-white font-mono outline-none focus:border-cyan-400"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-white/70 mb-1">Port</label>
                <input
                  type="number"
                  value={form.port}
                  onChange={(e) => setForm({ ...form, port: e.target.value })}
                  className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-xs text-white font-mono outline-none focus:border-cyan-400"
                />
              </div>
            </div>

            {/* Credential Details */}
            <div className="bg-white/3 border border-border/60 rounded-xl p-4 space-y-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-white/80">
                <Key className="w-3.5 h-3.5 text-cyan-400" />
                <span>Kredensial Manajemen (Disimpan Aman di Vault)</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] text-white/60 mb-1">Username SSH</label>
                  <input
                    type="text"
                    value={form.username}
                    onChange={(e) => setForm({ ...form, username: e.target.value })}
                    placeholder="admin"
                    className="w-full bg-white/5 border border-border rounded-lg px-3 py-1.5 text-xs text-white outline-none focus:border-cyan-400"
                  />
                </div>

                <div>
                  <label className="block text-[11px] text-white/60 mb-1">Password</label>
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      value={form.password}
                      onChange={(e) => setForm({ ...form, password: e.target.value })}
                      placeholder="••••••••"
                      className="w-full bg-white/5 border border-border rounded-lg pl-3 pr-8 py-1.5 text-xs text-white font-mono outline-none focus:border-cyan-400"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-white/40 hover:text-white"
                    >
                      {showPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                </div>
              </div>
              <p className="text-[10px] text-white/40">
                Password dienkripsi di vault dan tidak pernah dicatat dalam log atau dimasukkan ke prompt model AI.
              </p>
            </div>

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
                disabled={loading}
                className="flex items-center gap-1.5 text-xs font-semibold px-5 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black transition-colors disabled:opacity-50"
              >
                {loading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                {loading ? "Menjalankan Onboarding..." : "Onboard Perangkat"}
              </button>
            </div>
          </form>
        ) : (
          /* Onboarding Result View */
          <div className="space-y-4">
            <div
              className={`p-4 rounded-xl border flex items-center justify-between ${
                result.connection_status === "REACHABLE"
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                  : "bg-rose-500/10 border-rose-500/30 text-rose-300"
              }`}
            >
              <div className="flex items-center gap-3">
                {result.connection_status === "REACHABLE" ? (
                  <CheckCircle2 className="w-6 h-6 text-emerald-400" />
                ) : (
                  <AlertCircle className="w-6 h-6 text-rose-400" />
                )}
                <div>
                  <h4 className="text-sm font-bold text-white">
                    {result.connection_status === "REACHABLE"
                      ? "Onboarding & Discovery Berhasil"
                      : "Perangkat Tersimpan (Koneksi Tidak Terjangkau)"}
                  </h4>
                  <p className="text-xs text-white/70">
                    {result.connectivity_message} • Durasi {result.duration_sec}s
                  </p>
                </div>
              </div>

              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-white/10">
                {result.discovery_status}
              </span>
            </div>

            {/* AI Summary Breakdown */}
            {result.ai_summary && (
              <div className="bg-white/3 border border-border rounded-xl p-4 space-y-3 text-xs">
                <div className="flex items-center gap-1.5 text-cyan-400 font-semibold">
                  <Sparkles className="w-4 h-4" />
                  <span>Ringkasan Intelijen AI (Transparan)</span>
                </div>

                <div className="space-y-2">
                  <div>
                    <span className="text-[10px] uppercase font-mono text-emerald-400 block font-semibold">
                      Fakta Terkonfirmasi:
                    </span>
                    <ul className="list-disc list-inside text-white/80 space-y-0.5 text-[11px]">
                      {(result.ai_summary.facts || []).map((f, i) => (
                        <li key={i}>{f}</li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <span className="text-[10px] uppercase font-mono text-cyan-400 block font-semibold">
                      Indikasi Observasi:
                    </span>
                    <ul className="list-disc list-inside text-white/80 space-y-0.5 text-[11px]">
                      {(result.ai_summary.indications || []).map((ind, i) => (
                        <li key={i}>{ind}</li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <span className="text-[10px] uppercase font-mono text-amber-400 block font-semibold">
                      Hipotesis:
                    </span>
                    <ul className="list-disc list-inside text-white/80 space-y-0.5 text-[11px]">
                      {(result.ai_summary.hypotheses || []).map((h, i) => (
                        <li key={i}>{h}</li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <span className="text-[10px] uppercase font-mono text-purple-400 block font-semibold">
                      Rekomendasi Tindakan:
                    </span>
                    <ul className="list-disc list-inside text-white/80 space-y-0.5 text-[11px]">
                      {(result.ai_summary.recommendations || []).map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => {
                  setResult(null);
                  setForm({
                    name: "",
                    host: "",
                    port: 22,
                    device_type: "ROUTER",
                    vendor: "MikroTik",
                    username: "",
                    password: "",
                  });
                }}
                className="text-xs px-4 py-2 rounded-lg border border-border bg-white/5 hover:bg-white/10 text-white/70 transition-colors"
              >
                Onboard Perangkat Lain
              </button>
              <button
                type="button"
                onClick={onClose}
                className="text-xs font-semibold px-5 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black transition-colors"
              >
                Selesai
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
