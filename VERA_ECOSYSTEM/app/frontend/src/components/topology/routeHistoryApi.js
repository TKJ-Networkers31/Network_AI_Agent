// src/components/topology/routeHistoryApi.js
// Client API & Pure Epistemic State Helpers for WP 4.6.4 Historical Route Analytics

import { API_BASE } from "./topologyConstants.js";

/**
 * Lists immutable historical route snapshots with pagination and optional filters.
 */
export async function listRouteSnapshots({
  device_id = null,
  batch_id = null,
  trigger_type = null,
  completeness = null,
  include_routes = false,
  limit = 50,
  offset = 0,
} = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    include_routes: String(include_routes),
  });
  if (device_id) params.set("device_id", device_id);
  if (batch_id) params.set("batch_id", batch_id);
  if (trigger_type) params.set("trigger_type", trigger_type);
  if (completeness) params.set("completeness", completeness);

  const res = await fetch(`${API_BASE}/route-snapshots?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to list route snapshots: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Retrieves a single immutable route snapshot by ID.
 */
export async function getRouteSnapshot(snapshotId, { include_routes = true } = {}) {
  const params = new URLSearchParams({ include_routes: String(include_routes) });
  const res = await fetch(
    `${API_BASE}/route-snapshots/${encodeURIComponent(snapshotId)}?${params.toString()}`
  );
  if (!res.ok) {
    throw new Error(`Failed to get route snapshot ${snapshotId}: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Captures immutable route snapshots for selected or all registered devices.
 */
export async function createRouteSnapshots({
  device_ids = null,
  description = "",
  trigger_type = "manual",
  topology_snapshot_id = null,
  collect_if_missing = false,
} = {}) {
  const res = await fetch(`${API_BASE}/route-snapshots`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      device_ids,
      description,
      trigger_type,
      topology_snapshot_id,
      collect_if_missing,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to create route snapshot: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Verifies cryptographic SHA-256 integrity of a route snapshot independently of completeness.
 */
export async function verifyRouteSnapshot(snapshotId) {
  const res = await fetch(
    `${API_BASE}/route-snapshots/${encodeURIComponent(snapshotId)}/verify`
  );
  if (!res.ok) {
    throw new Error(`Failed to verify route snapshot ${snapshotId}: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Compares two route snapshots using semantic diff with incomplete-collection removal suppression.
 */
export async function compareRouteSnapshots(baseId, targetId) {
  const params = new URLSearchParams({
    base_id: baseId,
    target_id: targetId,
  });
  const res = await fetch(`${API_BASE}/route-snapshots/compare?${params.toString()}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to compare route snapshots: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Lists semantic route change records with optional filters.
 */
export async function listRouteChanges({
  device_id = null,
  snapshot_id = null,
  change_type = null,
  dst_prefix = null,
  start_time = null,
  end_time = null,
  limit = 100,
  offset = 0,
} = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (device_id) params.set("device_id", device_id);
  if (snapshot_id) params.set("snapshot_id", snapshot_id);
  if (change_type) params.set("change_type", change_type);
  if (dst_prefix) params.set("dst_prefix", dst_prefix);
  if (start_time !== null && start_time !== undefined) params.set("start_time", String(start_time));
  if (end_time !== null && end_time !== undefined) params.set("end_time", String(end_time));

  const res = await fetch(`${API_BASE}/route-snapshots/changes?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to list route changes: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Retrieves full details for a single route change record.
 */
export async function getRouteChangeDetail(changeId) {
  const res = await fetch(
    `${API_BASE}/route-snapshots/changes/${encodeURIComponent(changeId)}`
  );
  if (!res.ok) {
    throw new Error(`Failed to get route change #${changeId}: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Retrieves historical route churn, stability, flapping, and temporal correlation analytics.
 */
export async function getRouteHistoricalAnalytics({
  device_id = null,
  start_time = null,
  end_time = null,
  correlation_window_sec = 120,
  limit = 200,
} = {}) {
  const params = new URLSearchParams({
    correlation_window_sec: String(correlation_window_sec),
    limit: String(limit),
  });
  if (device_id) params.set("device_id", device_id);
  if (start_time !== null && start_time !== undefined) params.set("start_time", String(start_time));
  if (end_time !== null && end_time !== undefined) params.set("end_time", String(end_time));

  const res = await fetch(`${API_BASE}/route-snapshots/analytics?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to get route historical analytics: HTTP ${res.status}`);
  }
  return await res.json();
}

/**
 * Orthogonal badge state resolver for SHA-256 Integrity vs. Collection Completeness.
 * Guarantees a valid SHA-256 checksum never implies COMPLETE collection, and
 * incomplete/unreachable collection never implies compromised cryptographic integrity.
 */
export function getRouteSnapshotBadgeState(
  integrityStatus = "unverified",
  completeness = "COMPLETE"
) {
  const normIntegrity =
    integrityStatus === "verified"
      ? "verified"
      : integrityStatus === "compromised"
      ? "compromised"
      : "unverified";

  const normComp = String(completeness || "COMPLETE").toUpperCase();
  const isComplete = normComp === "COMPLETE";

  const integrity = {
    status: normIntegrity,
    label:
      normIntegrity === "verified"
        ? "SHA-256 Verified"
        : normIntegrity === "compromised"
        ? "Tampered / Compromised"
        : "Unverified",
    tooltip:
      normIntegrity === "verified"
        ? "Hash SHA-256 cocok 100% dengan serialisasi kanonikal snapshot rute."
        : normIntegrity === "compromised"
        ? "Integritas kriptografis gagal! Data snapshot rute tidak sesuai hash SHA-256."
        : "Belum diverifikasi secara kriptografis.",
  };

  const completenessMeta = {
    status: normComp,
    isComplete,
    label: isComplete ? "Complete RIB" : `Incomplete (${normComp})`,
    tooltip: isComplete
      ? "Seluruh tabel rute berhasil dikumpulkan tanpa pemotongan."
      : `Koleksi rute berstatus ${normComp}; penghapusan rute dikonfirmasi ditekan (suppressed) untuk mencegah false positive.`,
  };

  return { integrity, completeness: completenessMeta };
}

/**
 * Historical View Isolation Guard (Section 8.8 & 11.9).
 * Prevents background live route polling from overwriting historical snapshot inspection!
 */
export function applyLiveRoutePollingUpdate(viewState, livePayload) {
  const current = viewState || {
    mode: "live",
    displayedRoutes: [],
    cachedLiveRoutes: [],
    activeSnapshot: null,
  };
  const incomingRoutes = Array.isArray(livePayload?.routes) ? livePayload.routes : [];

  if (current.mode === "historical" && current.activeSnapshot) {
    return {
      ...current,
      cachedLiveRoutes: incomingRoutes,
      liveUpdatedAt: livePayload?.timestamp || Date.now(),
      // Strictly preserve displayedRoutes and activeSnapshot in historical mode!
      displayedRoutes: current.displayedRoutes,
      activeSnapshot: current.activeSnapshot,
    };
  }

  return {
    ...current,
    mode: "live",
    displayedRoutes: incomingRoutes,
    cachedLiveRoutes: incomingRoutes,
    liveUpdatedAt: livePayload?.timestamp || Date.now(),
  };
}
