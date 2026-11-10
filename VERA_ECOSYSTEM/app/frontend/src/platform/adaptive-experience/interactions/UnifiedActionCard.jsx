/**
 * src/platform/adaptive-experience/interactions/UnifiedActionCard.jsx
 *
 * Unified Action Card for VERA Adaptive Experience (VAE).
 * Consolidates Action Plan presentation, Permission Simulation, Impact/Risk Badges,
 * and Approval/Rejection workflows into a single cohesive component.
 */

import { useState } from "react";
import {
  Shield,
  Play,
  Copy,
  Check,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Terminal,
} from "lucide-react";
import { copyText } from "../../../utils/clipboard.js";
import { useToast } from "../../../components/Toast.jsx";
import { ActionGateway } from "./ActionGateway.js";

const RISK_BADGES = {
  READ_ONLY: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  LOW: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  MEDIUM: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  HIGH: "bg-orange-500/10 text-orange-400 border-orange-500/20",
  CRITICAL: "bg-rose-500/10 text-rose-400 border-rose-500/20",
};

export default function UnifiedActionCard(props) {
  const { showToast } = useToast();
  const [copied, setCopied] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [decisionState, setDecisionState] = useState(null); // 'APPROVED' | 'REJECTED'
  const [simulationResult, setSimulationResult] = useState(null);

  // Normalize incoming props: may receive `code` string from Markdown or structured props from VAE
  let cardData = {};
  if (typeof props.code === "string") {
    try {
      cardData = JSON.parse(props.code);
    } catch {
      cardData = {
        title: "Action Proposal",
        syntax: props.code,
        risk: "MEDIUM",
      };
    }
  } else {
    cardData = props.data || props;
  }

  const actionId = cardData.action_id || cardData.id || "act_" + Math.random().toString(36).slice(2, 8);
  const title = cardData.title || cardData.action_name || "Remediation Action";
  const device =
    cardData.target_device ||
    cardData.target ||
    (cardData.target_devices ? cardData.target_devices.join(", ") : "Network Infrastructure");
  const risk = (cardData.risk_level || cardData.risk || "MEDIUM").toUpperCase();
  const syntax = cardData.syntax || cardData.syntax_snippet || cardData.command || "";
  const description = cardData.description || "";
  const isApprovalRequired = Boolean(cardData.requires_approval || risk === "HIGH" || risk === "CRITICAL");

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
    setSimulating(true);
    const res = await ActionGateway.simulatePermission({
      resource: `device:${device}`,
      action: isApprovalRequired ? "APPROVE" : "EXECUTE",
    });

    setSimulationResult(res);
    setSimulating(false);
  };

  const handleDecision = async (decision) => {
    setSubmitting(true);
    const res = await ActionGateway.submitApproval({
      actionId,
      decision,
      reason: `User decision via VERA Adaptive Experience: ${decision}`,
    });

    if (res.success) {
      setDecisionState(decision);
      showToast(
        decision === "APPROVE"
          ? "Tindakan berhasil disetujui untuk dieksekusi"
          : "Tindakan ditolak oleh pengguna",
        decision === "APPROVE" ? "success" : "warning"
      );
    } else {
      showToast("Gagal mengirim persetujuan: " + res.error, "error");
    }
    setSubmitting(false);
  };

  return (
    <div className="my-3 rounded-xl border border-white/10 bg-[#04060c] p-4 text-xs font-sans text-white/90 shadow-xl transition-all">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-2.5">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-cyan-400" />
          <span className="font-semibold text-white tracking-wide">{title}</span>
          <span className="text-white/40">·</span>
          <span className="font-mono text-[11px] text-white/60">{device}</span>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-semibold border ${
              RISK_BADGES[risk] || RISK_BADGES.MEDIUM
            }`}
          >
            {risk} RISK
          </span>
          {decisionState && (
            <span
              className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-semibold ${
                decisionState === "APPROVE"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                  : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
              }`}
            >
              {decisionState === "APPROVE" ? "DISETUJUI" : "DITOLAK"}
            </span>
          )}
        </div>
      </div>

      {/* Description */}
      {description && (
        <p className="mt-2 text-white/70 text-xs leading-relaxed">{description}</p>
      )}

      {/* Syntax Box */}
      {syntax && (
        <div className="mt-2.5 rounded-lg bg-[#050B14] border border-white/5 p-2.5 font-mono text-[11px] text-cyan-300 overflow-x-auto flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 overflow-x-auto">
            <Terminal className="h-3.5 w-3.5 text-white/40 shrink-0" />
            <code>{syntax}</code>
          </div>
          <button
            type="button"
            onClick={handleCopy}
            className="shrink-0 p-1 text-white/50 hover:text-white transition"
            title="Salin sintaks"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
          </button>
        </div>
      )}

      {/* Simulation Result */}
      {simulationResult && (
        <div
          className={`mt-2.5 rounded-md p-2.5 text-xs flex items-center gap-2 border ${
            simulationResult.allowed
              ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/20"
              : "bg-rose-500/10 text-rose-300 border-rose-500/20"
          }`}
        >
          {simulationResult.allowed ? (
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
          ) : (
            <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
          )}
          <span>
            {simulationResult.allowed
              ? "Simulasi Otorisasi: DIIZINKAN (Akun memiliki wewenang eksekusi)"
              : "Simulasi Otorisasi: DITOLAK — " + simulationResult.reason}
          </span>
        </div>
      )}

      {/* Actions Toolbar */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 pt-2.5 border-t border-white/5">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleSimulate}
            disabled={simulating}
            className="inline-flex items-center gap-1.5 rounded-md bg-white/5 border border-white/10 px-2.5 py-1.5 text-[11px] font-medium text-white/80 hover:bg-white/10 hover:text-white transition disabled:opacity-50"
          >
            <Play className="h-3 w-3 text-cyan-400" />
            <span>{simulating ? "Memeriksa..." : "Simulasi Otorisasi"}</span>
          </button>
        </div>

        {isApprovalRequired && !decisionState && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => handleDecision("REJECT")}
              disabled={submitting}
              className="inline-flex items-center gap-1 rounded-md bg-rose-500/10 border border-rose-500/20 px-2.5 py-1.5 text-[11px] font-medium text-rose-300 hover:bg-rose-500/20 transition disabled:opacity-50"
            >
              <XCircle className="h-3 w-3" />
              <span>Tolak</span>
            </button>
            <button
              type="button"
              onClick={() => handleDecision("APPROVE")}
              disabled={submitting}
              className="inline-flex items-center gap-1 rounded-md bg-emerald-500/15 border border-emerald-500/30 px-3 py-1.5 text-[11px] font-medium text-emerald-200 hover:bg-emerald-500/25 transition disabled:opacity-50"
            >
              <CheckCircle2 className="h-3 w-3 text-emerald-400" />
              <span>Setujui Eksekusi</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
