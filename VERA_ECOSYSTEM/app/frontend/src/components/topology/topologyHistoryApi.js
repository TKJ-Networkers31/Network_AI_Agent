// src/components/topology/topologyHistoryApi.js
// Client API for AIRA OS Phase 4.4B: Historical Topology Snapshots & Semantic Graph Diff

import { API_BASE } from "./topologyConstants.js";

/**
 * Lists historical topology snapshots with pagination and metadata.
 */
export async function listSnapshots({
  limit = 50,
  offset = 0,
  trigger_type = null,
  include_graph = false,
} = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    include_graph: String(include_graph),
  });
  if (trigger_type) {
    params.set("trigger_type", trigger_type);
  }
  const res = await fetch(`${API_BASE}/snapshots?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to list snapshots: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Retrieves a single snapshot by ID with parsed graph state.
 */
export async function getSnapshot(snapshotId, { include_graph = true } = {}) {
  const params = new URLSearchParams({ include_graph: String(include_graph) });
  const res = await fetch(`${API_BASE}/snapshots/${encodeURIComponent(snapshotId)}?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to get snapshot ${snapshotId}: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Creates an explicit point-in-time snapshot of the current network state.
 */
export async function createSnapshot({ description = "", trigger_type = "manual" } = {}) {
  const res = await fetch(`${API_BASE}/snapshots`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ description, trigger_type }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to create snapshot: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Verifies SHA-256 cryptographic integrity of a snapshot record.
 */
export async function verifySnapshotIntegrity(snapshotId) {
  const res = await fetch(`${API_BASE}/snapshots/${encodeURIComponent(snapshotId)}/verify`);
  if (!res.ok) {
    throw new Error(`Failed to verify snapshot ${snapshotId}: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Compares two snapshots using the semantic graph diff engine.
 */
export async function compareSnapshots(baseId, targetId) {
  const params = new URLSearchParams({
    base_id: baseId,
    target_id: targetId,
  });
  const res = await fetch(`${API_BASE}/snapshots/compare?${params.toString()}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to compare snapshots: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Lists chronological topology changes with optional filters and pagination.
 */
export async function listChanges({
  snapshot_id = null,
  entity_id = null,
  change_type = null,
  start_time = null,
  end_time = null,
  limit = 100,
  offset = 0,
} = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (snapshot_id) params.set("snapshot_id", snapshot_id);
  if (entity_id) params.set("entity_id", entity_id);
  if (change_type) params.set("change_type", change_type);
  if (start_time !== null && start_time !== undefined) params.set("start_time", String(start_time));
  if (end_time !== null && end_time !== undefined) params.set("end_time", String(end_time));

  const res = await fetch(`${API_BASE}/changes?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to list topology changes: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Retrieves full details of a single topology delta change with evidence.
 */
export async function getChange(changeId) {
  const res = await fetch(`${API_BASE}/changes/${encodeURIComponent(changeId)}`);
  if (!res.ok) {
    throw new Error(`Failed to get change #${changeId}: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Resolves the two orthogonal dimensions for snapshot integrity and discovery completeness.
 * Strictly guarantees that partial discovery is never presented as cryptographic compromise,
 * and valid cryptographic hash never implies complete discovery.
 */
export function getSnapshotBadgeState(status = "unverified", isComplete = true) {
  const normalizedStatus =
    status === "verified" ? "verified" : status === "compromised" ? "compromised" : "unverified";
  const complete = isComplete !== false;

  const integrity = {
    status: normalizedStatus,
    label:
      normalizedStatus === "verified"
        ? "Verified"
        : normalizedStatus === "compromised"
        ? "Compromised"
        : "Unverified",
    tooltip:
      normalizedStatus === "verified"
        ? "Terverifikasi secara kriptografis: hash SHA-256 cocok 100% dengan representasi kanonikal."
        : normalizedStatus === "compromised"
        ? "Integritas SHA-256 gagal! Snapshot mungkin telah dimodifikasi secara tidak sah."
        : "Belum diverifikasi: klik tombol Verifikasi untuk mengecek integritas SHA-256.",
  };

  const completeness = {
    isComplete: complete,
    label: complete ? "Complete" : "Partial Run",
    tooltip: complete
      ? "Discovery Lengkap: Seluruh perangkat berhasil dipindai."
      : "Discovery Parsial: Beberapa node/link tidak dapat dijangkau selama pemindaian.",
  };

  return { integrity, completeness };
}
