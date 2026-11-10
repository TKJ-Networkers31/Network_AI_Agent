/**
 * src/platform/adaptive-experience/blocks/WorkflowRecoveryBlock.jsx
 *
 * Universal Workflow Recovery Component.
 * Transforms dead-end tool failures (such as duplicate router registration)
 * into actionable, contextual recovery paths with prefilled data forms.
 */

import React, { useState } from "react";
import { AlertCircle, ArrowRight, CheckCircle2, Edit3, RefreshCw, Eye, X, ShieldAlert } from "lucide-react";
import Renderer from "../../../components/dio/Renderer.jsx";

export default function WorkflowRecoveryBlock({ block, onInteractionSubmit, onActionInvoke }) {
  const data = block?.data || {};
  const category = data.category || "OPERATIONAL_ERROR";
  const userMessage = data.user_message || data.summary || "Operasi mengalami kendala.";
  const summary = data.summary || "";
  const actions = data.recovery_actions || [];
  const existingResource = data.existing_resource;
  const originalInput = data.original_input || {};

  const [activeAction, setActiveAction] = useState(null);
  const [resolved, setResolved] = useState(false);

  const handleActionSelect = (action) => {
    if (action.action_type === "CANCEL") {
      setActiveAction(null);
      return;
    }

    if (action.schema) {
      // Open embedded interactive form
      setActiveAction(action);
    } else if (onActionInvoke) {
      onActionInvoke(action);
      setResolved(true);
    } else if (onInteractionSubmit) {
      onInteractionSubmit(action.action_id, action.prefilled_data);
      setResolved(true);
    }
  };

  const handleFormSubmit = (actionId, formValues) => {
    if (onActionInvoke) {
      onActionInvoke({
        ...activeAction,
        type: "tool",
        action_type: "TOOL",
        target_tool: activeAction?.target_tool,
        prefilled_data: formValues,
        payload: formValues,
      });
    } else if (onInteractionSubmit) {
      onInteractionSubmit(actionId, formValues);
    }
    setActiveAction(null);
    setResolved(true);
  };

  return (
    <div className="my-3 p-4 rounded-xl border border-amber-500/30 bg-slate-900/90 backdrop-blur-md shadow-xl space-y-4 font-sans animate-fadeIn">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400">
            <AlertCircle size={20} />
          </div>
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-amber-300">
              Kendala Operasi & Opsi Pemulihan
            </h4>
            <p className="text-xs text-white/80 mt-0.5">{userMessage}</p>
          </div>
        </div>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-950/60 border border-amber-500/30 text-amber-300 font-bold">
          {category}
        </span>
      </div>

      {/* Existing Resource Context Card (if available) */}
      {existingResource && (
        <div className="p-3 rounded-lg border border-white/5 bg-black/40 text-xs space-y-1.5 font-mono">
          <div className="flex items-center justify-between text-white/50 text-[10px] uppercase">
            <span>Data Terdaftar di Inventaris Saat Ini:</span>
            <span>ID: {existingResource.id || "N/A"}</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-white/80">
            <div>
              <span className="text-white/40">Nama: </span>
              <span className="font-bold text-cyan-400">{existingResource.name}</span>
            </div>
            <div>
              <span className="text-white/40">Host: </span>
              <span>{existingResource.host || "-"}</span>
            </div>
            <div>
              <span className="text-white/40">Tipe: </span>
              <span className="capitalize">{existingResource.device_type || "mikrotik"}</span>
            </div>
          </div>
        </div>
      )}

      {/* Active Embedded Form (Modal / Expander) */}
      {activeAction && activeAction.schema && (
        <div className="p-3.5 rounded-lg border border-cyan-500/30 bg-slate-800/90 space-y-3">
          <div className="flex items-center justify-between border-b border-white/10 pb-2">
            <h5 className="text-xs font-semibold text-cyan-300 flex items-center gap-1.5">
              <Edit3 size={14} /> {activeAction.label}
            </h5>
            <button
              type="button"
              onClick={() => setActiveAction(null)}
              className="p-1 rounded hover:bg-white/10 text-white/40 hover:text-white"
            >
              <X size={14} />
            </button>
          </div>
          <Renderer
            schema={activeAction.schema}
            onSubmitAction={(actionId, values) => handleFormSubmit(actionId, values)}
          />
        </div>
      )}

      {/* Actionable Recovery Choices */}
      {!activeAction && !resolved && actions.length > 0 && (
        <div className="space-y-2">
          <h5 className="text-[11px] font-semibold text-white/60 uppercase tracking-wider font-mono">
            Pilih Tindakan Lanjutan:
          </h5>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {actions.map((act) => {
              const isPrimary = act.is_primary;
              return (
                <button
                  key={act.action_id}
                  type="button"
                  onClick={() => handleActionSelect(act)}
                  className={`flex flex-col text-left p-3 rounded-lg border transition-all text-xs ${
                    isPrimary
                      ? "border-cyan-500/40 bg-cyan-950/30 hover:bg-cyan-900/40 text-cyan-200 hover:border-cyan-400"
                      : "border-white/10 bg-black/30 hover:bg-white/5 text-white/80 hover:border-white/20"
                  }`}
                >
                  <div className="flex items-center justify-between font-semibold">
                    <span className="flex items-center gap-1.5">
                      {act.action_type === "UPDATE_EXISTING" && <Edit3 size={13} className="text-cyan-400" />}
                      {act.action_type === "EDIT_FORM" && <RefreshCw size={13} className="text-amber-400" />}
                      {act.action_type === "INSPECT_RESOURCE" && <Eye size={13} className="text-emerald-400" />}
                      {act.label}
                    </span>
                    <ArrowRight size={12} className="opacity-60" />
                  </div>
                  <span className="text-[11px] text-white/50 mt-1">{act.description}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Resolved Confirmation */}
      {resolved && (
        <div className="flex items-center gap-2 text-xs text-emerald-400 bg-emerald-950/40 border border-emerald-500/30 p-2.5 rounded-lg font-medium">
          <CheckCircle2 size={16} />
          <span>Tindakan pemulihan telah dikirim dan sedang diproses.</span>
        </div>
      )}
    </div>
  );
}
