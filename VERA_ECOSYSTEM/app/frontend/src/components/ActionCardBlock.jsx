import { useState } from "react";
import { Shield, Play, Copy, Check, CheckCircle2, AlertTriangle, ArrowRight } from "lucide-react";
import { copyText } from "../utils/clipboard.js";
import { useToast } from "./Toast.jsx";
import { api } from "../api.js";

export default function ActionCardBlock({ code }) {
  const { showToast } = useToast();
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [actionStatus, setActionStatus] = useState(null);

  let data = null;
  try {
    data = JSON.parse(code);
  } catch (e) {
    // Fallback if raw text
    data = {
      action_name: "Custom Action",
      target_device: "network_node",
      risk_level: "HIGH",
      syntax: code,
    };
  }

  const actionName = data.action_name || data.title || "Remediation Action";
  const device = data.target_device || data.target || (data.target_devices ? data.target_devices.join(", ") : "All Devices");
  const risk = (data.risk_level || data.risk || "MEDIUM").toUpperCase();
  const syntax = data.syntax || data.syntax_snippet || data.command || "";

  const riskBadgeColors = {
    READ_ONLY: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    LOW: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    MEDIUM: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    HIGH: "bg-orange-500/10 text-orange-400 border-orange-500/20",
    CRITICAL: "bg-rose-500/10 text-rose-400 border-rose-500/20",
  };

  const handleCopy = async () => {
    if (!syntax) return;
    const ok = await copyText(syntax);
    if (ok) {
      setCopied(true);
      showToast("Perintah berhasil disalin ke clipboard", "success");
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleSimulate = async () => {
    setLoading(true);
    try {
      const res = await api.post("/api/v1/admin/permissions/simulate", {
        resource: `device:${device}`,
        action: risk === "HIGH" || risk === "CRITICAL" ? "APPROVE" : "EXECUTE",
      });
      if (res && res.simulation) {
        const allowed = res.simulation.allowed;
        setActionStatus({
          type: allowed ? "success" : "denied",
          message: allowed
            ? "Simulasi Izin: DIIZINKAN (Akun memiliki wewenang untuk tindakan ini)"
            : "Simulasi Izin: DITOLAK (Memerlukan eskalasi kredensial administrator)",
        });
      }
    } catch (err) {
      setActionStatus({
        type: "error",
        message: "Gagal menjalankan simulasi izin: " + (err.message || "Network error"),
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="my-3 rounded-xl border border-white/10 bg-[#090d16] p-4 text-xs font-sans text-white/90 shadow-xl">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-2.5">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-cyan-400" />
          <span className="font-semibold text-white tracking-wide">{actionName}</span>
          <span className="text-white/40">·</span>
          <span className="text-white/60 font-mono text-[11px]">{device}</span>
        </div>
        <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-semibold border ${riskBadgeColors[risk] || riskBadgeColors.MEDIUM}`}>
          {risk} RISK
        </span>
      </div>

      {data.description && (
        <p className="mt-2 text-white/70 text-xs leading-relaxed">{data.description}</p>
      )}

      {syntax && (
        <div className="mt-2.5 rounded-lg bg-black/40 border border-white/5 p-2 font-mono text-[11px] text-cyan-300 overflow-x-auto">
          <code>{syntax}</code>
        </div>
      )}

      {actionStatus && (
        <div className={`mt-2.5 rounded-md p-2 text-xs flex items-center gap-2 ${actionStatus.type === "success" ? "bg-emerald-500/10 text-emerald-300 border border-emerald-500/20" : "bg-rose-500/10 text-rose-300 border border-rose-500/20"}`}>
          {actionStatus.type === "success" ? <CheckCircle2 className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
          <span>{actionStatus.message}</span>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2 pt-2 border-t border-white/5">
        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex items-center gap-1.5 rounded-md bg-white/5 px-2.5 py-1.5 text-[11px] font-medium text-white/80 hover:bg-white/10 hover:text-white transition"
        >
          {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
          {copied ? "Tersalin" : "Salin Script"}
        </button>

        <button
          type="button"
          onClick={handleSimulate}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-md bg-cyan-500/10 border border-cyan-500/20 px-2.5 py-1.5 text-[11px] font-medium text-cyan-300 hover:bg-cyan-500/20 transition disabled:opacity-50"
        >
          <Play className="h-3 w-3" />
          {loading ? "Memeriksa..." : "Simulasi Otorisasi"}
        </button>
      </div>
    </div>
  );
}
