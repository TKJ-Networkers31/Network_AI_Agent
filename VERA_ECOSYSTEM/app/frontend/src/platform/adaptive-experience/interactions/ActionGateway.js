/**
 * src/platform/adaptive-experience/interactions/ActionGateway.js
 *
 * Centralized Action Execution & Invocation Gateway for VERA Adaptive Experience (VAE).
 * Enforces unified error normalization, permission verification, and audit telemetry.
 */

import { api } from "../../../api.js";

/**
 * Normalizes backend error responses into a consistent user-safe shape.
 */
function normalizeActionError(err) {
  if (err?.response?.data?.detail) {
    const detail = err.response.data.detail;
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  }
  return err?.message || "Terjadi kesalahan internal saat memproses aksi.";
}

/**
 * Simulates permission check for a given resource and action.
 *
 * @param {{ resource: string, action: string }} req
 * @returns {Promise<{ allowed: boolean, reason?: string, raw?: any }>}
 */
export async function simulatePermission({ resource, action }) {
  try {
    const res = await api.post("/api/v1/admin/permissions/simulate", {
      resource,
      action: action || "EXECUTE",
    });

    const allowed = Boolean(res?.simulation?.allowed);
    const reason = res?.simulation?.reason || (allowed ? "Diizinkan oleh kebijakan RBAC" : "Ditolak oleh kebijakan RBAC");

    return {
      allowed,
      reason,
      raw: res,
    };
  } catch (err) {
    return {
      allowed: false,
      reason: normalizeActionError(err),
      error: err,
    };
  }
}

/**
 * Executes a verified remediation action or capability.
 *
 * @param {{ actionId: string, payload?: any, context?: any }} req
 * @returns {Promise<{ success: boolean, result?: any, error?: string }>}
 */
export async function executeAction({ actionId, payload = {}, context = {} }) {
  try {
    const res = await api.post("/api/v1/actions/execute", {
      action_id: actionId,
      payload,
      context,
    });

    return {
      success: true,
      result: res,
    };
  } catch (err) {
    return {
      success: false,
      error: normalizeActionError(err),
    };
  }
}

/**
 * Submits an approval or rejection decision for a pending workflow/DIO plan.
 *
 * @param {{ actionId: string, decision: "APPROVE" | "REJECT", reason?: string }} req
 * @returns {Promise<{ success: boolean, decision: string, error?: string }>}
 */
export async function submitApproval({ actionId, decision, reason = "" }) {
  try {
    const res = await api.post("/api/v1/actions/approval", {
      action_id: actionId,
      decision,
      reason,
    });

    return {
      success: true,
      decision,
      result: res,
    };
  } catch (err) {
    return {
      success: false,
      decision,
      error: normalizeActionError(err),
    };
  }
}

export const ActionGateway = Object.freeze({
  simulatePermission,
  executeAction,
  submitApproval,
  normalizeActionError,
});

export default ActionGateway;
