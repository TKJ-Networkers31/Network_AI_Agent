/**
 * src/platform/adaptive-experience/interactions/ActionRegistry.js
 *
 * Universal Action & Interaction Registry for VERA Adaptive Experience (VAE).
 * Enforces a strongly-typed action contract, eliminates "Tipe aksi tidak diketahui" errors,
 * provides registered handlers for all operational actions, and guarantees safe fallback.
 */

import { api } from "../../../api.js";
import { ActionGateway } from "./ActionGateway.js";

/**
 * Supported Action Types
 */
export const ACTION_TYPES = Object.freeze({
  RETRY_OPERATION: "retry_operation",
  EDIT_PARAMETERS: "edit_parameters",
  CANCEL_WORKFLOW: "cancel_workflow",
  OPEN_RESOURCE: "open_resource",
  VIEW_DETAILS: "view_details",
  REQUEST_PERMISSION: "request_permission",
  APPROVE_ACTION: "approve_action",
  REJECT_ACTION: "reject_action",
  RESUME_WORKFLOW: "resume_workflow",
  NAVIGATE_TO_RESOURCE: "navigate_to_resource",
  TOOL: "tool",
  PROMPT: "prompt",
  NAVIGATE: "navigate",
  WORKSPACE: "workspace",

  // Recovery Engine aliases
  UPDATE_EXISTING: "UPDATE_EXISTING",
  EDIT_FORM: "EDIT_FORM",
  INSPECT_RESOURCE: "INSPECT_RESOURCE",
  DIAGNOSTIC_PROBE: "DIAGNOSTIC_PROBE",
  RETRY: "RETRY",
  CANCEL: "CANCEL",
});

/**
 * Normalizes any action, capability, or raw tool call into a validated TypedAction.
 * Never throws — returns a safe object or unknown action envelope.
 */
export function normalizeAction(actionOrCapability, optionalPayload = {}) {
  if (!actionOrCapability) {
    return {
      isValid: false,
      type: "unknown",
      error: "Aksi kosong atau tidak terdefinisi.",
    };
  }

  // Case 1: Raw tool name passed as string: e.g. ("update_device", { name: "CHR", ... })
  if (typeof actionOrCapability === "string") {
    const toolName = actionOrCapability.trim();
    return {
      isValid: true,
      id: `act_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      type: ACTION_TYPES.TOOL,
      targetTool: toolName,
      payload: optionalPayload && typeof optionalPayload === "object" ? optionalPayload : {},
      label: `Jalankan ${toolName}`,
      description: `Eksekusi langsung tool ${toolName}`,
    };
  }

  // Case 2: RecoveryAction object from WorkflowRecoveryBlock:
  // { action_id, action_type, label, description, target_tool, prefilled_data, schema, is_primary }
  if (actionOrCapability.action_type || actionOrCapability.target_tool) {
    const rawType = actionOrCapability.action_type || ACTION_TYPES.TOOL;
    return {
      isValid: true,
      id: actionOrCapability.action_id || `act_${Date.now()}`,
      type: rawType,
      targetTool: actionOrCapability.target_tool,
      payload: actionOrCapability.prefilled_data || optionalPayload || {},
      schema: actionOrCapability.schema || null,
      label: actionOrCapability.label || "Tindakan Pemulihan",
      description: actionOrCapability.description || "",
      isPrimary: Boolean(actionOrCapability.is_primary),
      requiresConfirmation: Boolean(actionOrCapability.requires_confirmation),
    };
  }

  // Case 3: Legacy Capability envelope: { action: { type, prompt, tool, args, href, ... } }
  if (actionOrCapability.action && typeof actionOrCapability.action === "object") {
    const act = actionOrCapability.action;
    return {
      isValid: Boolean(act.type),
      id: actionOrCapability.id || `act_${Date.now()}`,
      type: act.type || "unknown",
      prompt: act.prompt,
      tool: act.tool,
      args: act.args,
      href: act.href,
      workspaceOp: act.workspace_op,
      filePath: act.file_path,
      payload: act.payload || optionalPayload,
      label: actionOrCapability.label || act.label || "Aksi",
      description: actionOrCapability.description || act.description || "",
    };
  }

  // Case 4: Typed Action object: { id, type, ... }
  if (actionOrCapability.type) {
    return {
      isValid: true,
      id: actionOrCapability.id || `act_${Date.now()}`,
      type: actionOrCapability.type,
      targetTool: actionOrCapability.target_tool || actionOrCapability.targetTool || actionOrCapability.tool,
      payload: actionOrCapability.payload || actionOrCapability.prefilled_data || optionalPayload,
      schema: actionOrCapability.schema || null,
      prompt: actionOrCapability.prompt,
      href: actionOrCapability.href,
      label: actionOrCapability.label || "Aksi",
      description: actionOrCapability.description || "",
      isPrimary: Boolean(actionOrCapability.is_primary || actionOrCapability.isPrimary),
    };
  }

  // Fallback for unparseable input
  return {
    isValid: false,
    type: "unknown",
    raw: actionOrCapability,
    error: "Struktur aksi tidak dikenali.",
  };
}

/**
 * Executes a normalized action safely across the appropriate subsystem.
 *
 * @param {Object} action - The action object or capability
 * @param {Object} helpers - Callbacks { onSend, notify, onOpenForm, onWorkspaceChange, onNavigate }
 */
export async function executeTypedAction(action, helpers = {}) {
  const {
    onSend,
    notify,
    onOpenForm,
    onWorkspaceChange,
    onNavigate,
    context = {},
  } = helpers;

  const normalized = normalizeAction(action);

  if (!normalized.isValid || normalized.type === "unknown") {
    const errMsg = "Aksi ini tidak memiliki eksekusi yang valid atau belum didaftarkan.";
    console.warn("[ActionRegistry] Rejected unsupported action:", action);
    notify?.({
      type: "warning",
      message: errMsg,
      duration: 4000,
    });
    return { success: false, error: errMsg };
  }

  try {
    switch (normalized.type) {
      // 1. Tool execution via Chat pipeline or direct invocation
      case ACTION_TYPES.TOOL:
      case "tool": {
        const tool = normalized.targetTool || normalized.tool;
        if (!tool) throw new Error("Nama tool target tidak ditemukan pada aksi ini.");

        if (onSend) {
          // If payload is non-empty, format as JSON or CLI args
          const argsStr = normalized.payload && Object.keys(normalized.payload).length > 0
            ? JSON.stringify(normalized.payload)
            : (normalized.args || "");
          await onSend(`/${tool} ${argsStr}`.trim());
          return { success: true };
        } else {
          // Fallback to ActionGateway execute endpoint
          const res = await ActionGateway.executeAction({
            actionId: normalized.id,
            payload: { tool, args: normalized.payload },
            context,
          });
          return res;
        }
      }

      // 2. Chat Prompt submission
      case ACTION_TYPES.PROMPT:
      case "prompt": {
        if (!normalized.prompt) throw new Error("Aksi tidak menyertakan prompt.");
        if (!onSend) throw new Error("Saluran chat tidak tersedia untuk menjalankan prompt.");
        await onSend(normalized.prompt);
        return { success: true };
      }

      // 3. Update Existing Resource (Recovery Route A)
      case ACTION_TYPES.UPDATE_EXISTING: {
        if (normalized.schema && onOpenForm) {
          onOpenForm(normalized);
          return { success: true };
        }
        if (onSend && normalized.payload) {
          const payloadJson = JSON.stringify(normalized.payload);
          await onSend(`/update_device ${payloadJson}`);
          return { success: true };
        }
        throw new Error("Formulir pembaruan tidak dapat dibuka.");
      }

      // 4. Edit Parameters / Form (Recovery Route B)
      case ACTION_TYPES.EDIT_PARAMETERS:
      case ACTION_TYPES.EDIT_FORM: {
        if (normalized.schema && onOpenForm) {
          onOpenForm(normalized);
          return { success: true };
        }
        if (onSend && normalized.targetTool && normalized.payload) {
          await onSend(`/${normalized.targetTool} ${JSON.stringify(normalized.payload)}`);
          return { success: true };
        }
        return { success: true };
      }

      // 5. Inspect Resource (Recovery Route C)
      case ACTION_TYPES.VIEW_DETAILS:
      case ACTION_TYPES.INSPECT_RESOURCE:
      case ACTION_TYPES.OPEN_RESOURCE: {
        const devName = normalized.payload?.name || normalized.payload?.device_name || normalized.payload?.device;
        if (devName && onSend) {
          await onSend(`/get_device ${JSON.stringify({ name: devName })}`);
          return { success: true };
        }
        if (onNavigate) {
          onNavigate("devices", { device: devName });
          return { success: true };
        }
        window.dispatchEvent(new CustomEvent("vera:navigate", { detail: "devices" }));
        return { success: true };
      }

      // 6. Retry Operation
      case ACTION_TYPES.RETRY_OPERATION:
      case ACTION_TYPES.RETRY: {
        if (normalized.targetTool && onSend) {
          await onSend(`/${normalized.targetTool} ${JSON.stringify(normalized.payload || {})}`);
          return { success: true };
        }
        notify?.({ type: "info", message: "Mencoba kembali operasi..." });
        return { success: true };
      }

      // 7. Diagnostic Probe (e.g. Ping)
      case ACTION_TYPES.DIAGNOSTIC_PROBE: {
        const target = normalized.payload?.target || normalized.payload?.host || "target";
        if (onSend) {
          await onSend(`/network_ping ${JSON.stringify({ target, count: 4 })}`);
          return { success: true };
        }
        return { success: true };
      }

      // 8. Cancel Workflow
      case ACTION_TYPES.CANCEL_WORKFLOW:
      case ACTION_TYPES.CANCEL: {
        notify?.({ type: "info", message: "Alur kerja dibatalkan." });
        return { success: true, cancelled: true };
      }

      // 9. Navigation
      case ACTION_TYPES.NAVIGATE_TO_RESOURCE:
      case ACTION_TYPES.NAVIGATE:
      case "navigate": {
        if (normalized.href) {
          window.open(normalized.href, "_blank", "noopener,noreferrer");
          return { success: true };
        }
        if (normalized.payload?.page) {
          const page = normalized.payload.page;
          window.dispatchEvent(new CustomEvent("vera:navigate", { detail: page }));
          return { success: true };
        }
        throw new Error("Target navigasi tidak valid.");
      }

      // 10. Approval & Rejection
      case ACTION_TYPES.APPROVE_ACTION: {
        const res = await ActionGateway.submitApproval({
          actionId: normalized.id,
          decision: "APPROVE",
          reason: normalized.payload?.reason || "",
        });
        if (res.success) {
          notify?.({ type: "success", message: "Aksi berhasil disetujui." });
        }
        return res;
      }

      case ACTION_TYPES.REJECT_ACTION: {
        const res = await ActionGateway.submitApproval({
          actionId: normalized.id,
          decision: "REJECT",
          reason: normalized.payload?.reason || "",
        });
        if (res.success) {
          notify?.({ type: "info", message: "Aksi ditolak." });
        }
        return res;
      }

      // 11. Request Permission
      case ACTION_TYPES.REQUEST_PERMISSION: {
        const res = await ActionGateway.simulatePermission({
          resource: normalized.payload?.resource || "system",
          action: normalized.payload?.action || "EXECUTE",
        });
        notify?.({
          type: res.allowed ? "success" : "warning",
          message: res.reason,
        });
        return res;
      }

      // 12. Workspace Operation
      case ACTION_TYPES.WORKSPACE:
      case "workspace": {
        const op = normalized.workspaceOp || normalized.payload?.workspace_op;
        await runWorkspaceOperation(op, normalized);
        onWorkspaceChange?.();
        notify?.({ type: "success", message: "Operasi berkas berhasil diselesaikan." });
        return { success: true };
      }

      default:
        throw new Error(`Tipe aksi '${normalized.type}' tidak terdaftar pada registry.`);
    }
  } catch (err) {
    const errorMsg = err.message || "Gagal mengeksekusi aksi.";
    console.error("[ActionRegistry] Execution failed:", err);
    notify?.({ type: "error", message: errorMsg });
    return { success: false, error: errorMsg };
  }
}

async function runWorkspaceOperation(op, action) {
  switch (op) {
    case "delete":
      return api.workspace.delete(action.filePath || action.payload?.file_path);
    case "restore":
      return api.workspace.restore(action.payload?.trash_id);
    case "move":
      return api.workspace.move(action.filePath || action.payload?.file_path, action.payload?.destination);
    case "copy":
      return api.workspace.copy(action.filePath || action.payload?.file_path, action.payload?.destination);
    case "mkdir":
      return api.workspace.mkdir(action.payload?.path);
    default:
      throw new Error(`Operasi workspace '${op}' tidak dikenal.`);
  }
}
