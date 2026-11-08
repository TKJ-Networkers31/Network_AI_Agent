// src/components/topology/routeOverlayApi.js
// AIRA OS — Cross-Device Route Intelligence & Topology Route Overlay Client (WP 4.6.5)

import { API_BASE } from "./topologyConstants.js";

export const ROUTE_OVERLAY_SEGMENT_TYPES = {
  INFERRED_ROUTE_PATH: "INFERRED_ROUTE_PATH",
  RECURSIVE_NEXT_HOP_DEPENDENCY: "RECURSIVE_NEXT_HOP_DEPENDENCY",
  ROUTE_UNCERTAINTY: "ROUTE_UNCERTAINTY",
};

/**
 * Returns visually distinct SVG styling for ephemeral route overlay segments.
 * Guarantees every inferred path segment is visually distinguishable from
 * confirmed PHYSICAL_ADJACENCY and LAYER2_ADJACENCY topology edges.
 */
export function getOverlaySegmentVisualStyle(segment, isSelected = false) {
  const segType = segment?.overlay_segment_type || ROUTE_OVERLAY_SEGMENT_TYPES.INFERRED_ROUTE_PATH;

  if (segType === ROUTE_OVERLAY_SEGMENT_TYPES.ROUTE_UNCERTAINTY) {
    return {
      segmentType: segType,
      isPhysicalLink: false,
      stroke: isSelected ? "#fde047" : "#f59e0b",
      strokeWidth: isSelected ? 3.2 : 2.2,
      strokeDasharray: "5 5",
      opacity: isSelected ? 1.0 : 0.88,
      markerEnd: "url(#arrow-route-uncertain)",
      badge: `HOP ${segment?.hop_index ?? "?"} · UNCERTAIN`,
      dotColor: "#fbbf24",
      label: "Uncertain / Incomplete Route Segment",
    };
  }

  if (segType === ROUTE_OVERLAY_SEGMENT_TYPES.RECURSIVE_NEXT_HOP_DEPENDENCY) {
    return {
      segmentType: segType,
      isPhysicalLink: false,
      stroke: isSelected ? "#e879f9" : "#c084fc",
      strokeWidth: isSelected ? 3.2 : 2.3,
      strokeDasharray: "3 3",
      opacity: isSelected ? 1.0 : 0.9,
      markerEnd: "url(#arrow-route-recursive)",
      badge: `HOP ${segment?.hop_index ?? "?"} · RECURSIVE`,
      dotColor: "#c084fc",
      label: "Recursive Next-Hop Dependency",
    };
  }

  return {
    segmentType: ROUTE_OVERLAY_SEGMENT_TYPES.INFERRED_ROUTE_PATH,
    isPhysicalLink: false,
    stroke: isSelected ? "#67e8f9" : "#22d3ee",
    strokeWidth: isSelected ? 3.4 : 2.4,
    strokeDasharray: "8 4",
    opacity: isSelected ? 1.0 : 0.92,
    markerEnd: "url(#arrow-route-inferred)",
    badge: `HOP ${segment?.hop_index ?? 1} · ROUTE`,
    dotColor: "#22d3ee",
    label: "Inferred L3 Route Path Segment",
  };
}

export async function fetchTopologyRouteOverlay({
  sourceDevice = "",
  destination = "",
  routingTable = "main",
  sourcePrefixForReturn = "",
  signal,
} = {}) {
  const qs = new URLSearchParams();
  if (sourceDevice) qs.set("source_device", sourceDevice);
  if (destination) qs.set("destination", destination);
  if (routingTable) qs.set("routing_table", routingTable);
  if (sourcePrefixForReturn) qs.set("source_prefix_for_return", sourcePrefixForReturn);

  const res = await fetch(`${API_BASE}/route-overlay?${qs.toString()}`, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Gagal memuat route overlay (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchCrossDeviceRouteIntelligence(payload = {}, { signal } = {}) {
  const res = await fetch(`/api/intelligence/routes/cross-device`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Gagal menganalisis cross-device routing (HTTP ${res.status})`);
  }
  return res.json();
}
