// src/components/network-intelligence/OperationsPolicyModal.jsx
//
// AIRA OS — AI Operations Policy Management Modal (Workstream E).
// Controls automatic investigation, discovery, and approvals policy.
// High-Risk and Critical actions are hard-locked to require human approval.

import React, { useEffect, useState } from "react";
import {
  CheckCircle2,
  Lock,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  X,
} from "lucide-react";
import { api } from "../../api.js";
import { useToast } from "../Toast.jsx";

export default function OperationsPolicyModal({ isOpen, open, onClose }) {
  const { notify } = useToast();
  const isVisible = open !== undefined ? open : isOpen;

  const [policy, setPolicy] = useState({
    enable_auto_investigation: true,
    enable_auto_discovery: true,
    enable_auto_data_collection: true,
    enable_auto_recommendations: true,
    enable_auto_low_risk: false,
    require_medium_risk_approval: true,
    require_high_risk_approval: true,
    require_critical_approval: true,
  });

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isVisible) return;
    setLoading(true);
    api.intelligence
      .getOperationsPolicy()
      .then((res) => {
        if (res.success && res.policy) {
          setPolicy((prev) => ({ ...prev, ...res.policy }));
        }
      })
      .catch((err) => {
        notify({ type: "error", message: `Gagal memuat kebijakan: ${err.message}` });
      })
      .finally(() => setLoading(false));
  }, [isVisible, notify]);

  if (!isVisible) return null;

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await api.intelligence.updateOperationsPolicy({
        enable_auto_low_risk: policy.enable_auto_low_risk,
        require_medium_risk_approval: policy.require_medium_risk_approval,
      });
      if (res.success) {
        notify({ type: "success", message: "Kebijakan Operasi AI berhasil diperbarui.", duration: 2500 });
        onClose();
      }
    } catch (err) {
      notify({ type: "error", message: `Gagal menyimpan: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg p-6 shadow-2xl relative space-y-5">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-white/40 hover:text-white p-1"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
            <Sliders className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white">Kebijakan Operasi AI (AI Operations Policy)</h3>
            <p className="text-xs text-white/50">
              Konfigurasi batasan otonom, investigasi otomatis, dan aturan persetujuan bertingkat.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="py-8 text-center text-xs text-white/50 flex items-center justify-center gap-2">
            <RefreshCw className="w-4 h-4 animate-spin text-cyan-400" />
            Memuat kebijakan...
          </div>
        ) : (
          <form onSubmit={handleSave} className="space-y-4 text-xs">
            {/* Autonomous Capabilities */}
            <div className="space-y-2">
              <span className="text-[11px] font-semibold uppercase text-white/40 tracking-wider">
                Otonomi Investigasi & Observasi
              </span>
              <div className="bg-white/3 border border-border/60 rounded-xl p-3 space-y-2.5">
                <label className="flex items-center justify-between cursor-pointer">
                  <span className="text-white/80">Investigasi & Analisis Root Cause Otomatis</span>
                  <input
                    type="checkbox"
                    checked={policy.enable_auto_investigation}
                    onChange={(e) => setPolicy({ ...policy, enable_auto_investigation: e.target.checked })}
                    className="accent-cyan-400"
                  />
                </label>
                <label className="flex items-center justify-between cursor-pointer">
                  <span className="text-white/80">Discovery Read-Only Saat Pendaftaran Perangkat</span>
                  <input
                    type="checkbox"
                    checked={policy.enable_auto_discovery}
                    onChange={(e) => setPolicy({ ...policy, enable_auto_discovery: e.target.checked })}
                    className="accent-cyan-400"
                  />
                </label>
                <label className="flex items-center justify-between cursor-pointer">
                  <span className="text-white/80">Pengumpulan Telemetri Metrik Berkala (NMS)</span>
                  <input
                    type="checkbox"
                    checked={policy.enable_auto_data_collection}
                    onChange={(e) => setPolicy({ ...policy, enable_auto_data_collection: e.target.checked })}
                    className="accent-cyan-400"
                  />
                </label>
              </div>
            </div>

            {/* Action Approval Tiers */}
            <div className="space-y-2">
              <span className="text-[11px] font-semibold uppercase text-white/40 tracking-wider">
                Kebijakan Persetujuan Tindakan Jaringan
              </span>
              <div className="bg-white/3 border border-border/60 rounded-xl p-3 space-y-2.5">
                <label className="flex items-center justify-between cursor-pointer">
                  <div>
                    <span className="text-white/80 block">Izinkan Tindakan Low-Risk Otomatis</span>
                    <span className="text-[10px] text-white/40">Refresh cache inventory, sinkronisasi metadata</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={policy.enable_auto_low_risk}
                    onChange={(e) => setPolicy({ ...policy, enable_auto_low_risk: e.target.checked })}
                    className="accent-cyan-400"
                  />
                </label>

                <label className="flex items-center justify-between cursor-pointer pt-1 border-t border-white/5">
                  <div>
                    <span className="text-white/80 block">Wajib Persetujuan untuk Tindakan Medium-Risk</span>
                    <span className="text-[10px] text-white/40">Perubahan interval polling, monitoring, threshold alert</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={policy.require_medium_risk_approval}
                    onChange={(e) => setPolicy({ ...policy, require_medium_risk_approval: e.target.checked })}
                    className="accent-cyan-400"
                  />
                </label>

                {/* Locked High Risk */}
                <div className="flex items-center justify-between pt-1 border-t border-white/5 opacity-80">
                  <div>
                    <span className="text-orange-300 flex items-center gap-1.5 font-medium">
                      <Lock className="w-3 h-3 text-orange-400" />
                      Wajib Persetujuan untuk Tindakan High-Risk (Locked)
                    </span>
                    <span className="text-[10px] text-white/40">Routing, VLAN, Firewall, QoS, Interface link state</span>
                  </div>
                  <span className="text-[10px] font-mono text-orange-400 bg-orange-500/10 border border-orange-500/20 px-2 py-0.5 rounded">
                    ENFORCED
                  </span>
                </div>

                {/* Locked Critical Risk */}
                <div className="flex items-center justify-between pt-1 border-t border-white/5 opacity-80">
                  <div>
                    <span className="text-rose-300 flex items-center gap-1.5 font-medium">
                      <Lock className="w-3 h-3 text-rose-400" />
                      Wajib Persetujuan untuk Tindakan Critical (Locked)
                    </span>
                    <span className="text-[10px] text-white/40">Kredensial manajemen, reset konfigurasi, reboot sistem</span>
                  </div>
                  <span className="text-[10px] font-mono text-rose-400 bg-rose-500/10 border border-rose-500/20 px-2 py-0.5 rounded">
                    ENFORCED
                  </span>
                </div>
              </div>
            </div>

            <p className="text-[10px] text-white/40 leading-relaxed">
              Aturan non-negotiable: Tindakan tingkat High dan Critical tidak dapat dilewati melalui toggle global.
            </p>

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
                {saving ? "Menyimpan..." : "Terapkan Kebijakan"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
