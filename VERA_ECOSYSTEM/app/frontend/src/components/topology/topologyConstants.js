// src/components/topology/topologyConstants.js
// Visual state constants, non-color-only link pattern rules, and formatting helpers for AIRA Topology Fabric V2.

import {
  Globe,
  Layers,
  Network,
  Radio,
  Server,
  Terminal,
  Wifi,
} from "lucide-react";

export const API_BASE = "/api/topology";

export const DEVICE_ICONS = {
  router: Network,
  switch: Layers,
  access_point: Wifi,
  server: Server,
  client: Terminal,
  wan: Globe,
  unknown: Radio,
};

export const DEVICE_COLORS = {
  router: { border: "border-sky-500/40", glow: "hover:shadow-glow-cyan", badge: "bg-sky-500/10 text-sky-400" },
  switch: { border: "border-purple-500/40", glow: "hover:shadow-glow-purple", badge: "bg-purple-500/10 text-purple-400" },
  access_point: { border: "border-emerald-500/40", glow: "hover:shadow-[0_0_20px_rgba(16,185,129,0.3)]", badge: "bg-emerald-500/10 text-emerald-400" },
  server: { border: "border-amber-500/40", glow: "hover:shadow-[0_0_20px_rgba(245,158,11,0.3)]", badge: "bg-amber-500/10 text-amber-400" },
  wan: { border: "border-cyan-400/50", glow: "hover:shadow-glow-cyan", badge: "bg-cyan-500/10 text-cyan-300" },
  client: { border: "border-indigo-500/40", glow: "hover:shadow-[0_0_20px_rgba(99,102,241,0.3)]", badge: "bg-indigo-500/10 text-indigo-400" },
  unknown: { border: "border-white/20", glow: "hover:shadow-white/10", badge: "bg-white/5 text-text-secondary" },
};

export const STATUS_CONFIG = {
  online: {
    label: "Online",
    color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    dot: "bg-emerald-400 shadow-[0_0_8px_#34d399]",
  },
  warning: {
    label: "Unverified / Degraded",
    color: "text-amber-400 bg-amber-500/10 border-amber-500/20",
    dot: "bg-amber-400 shadow-[0_0_8px_#fbbf24]",
  },
  offline: {
    label: "Unreachable",
    color: "text-red-400 bg-red-500/10 border-red-500/20",
    dot: "bg-red-400 shadow-[0_0_8px_#f87171] animate-pulse",
  },
};

export const OWNERSHIP_BADGES = {
  owned: {
    short: "OWNED",
    label: "Company Owned",
    className: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  },
  managed_external: {
    short: "MGD-EXT",
    label: "Managed External",
    className: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  },
  third_party: {
    short: "ISP / 3RD",
    label: "Third-Party / ISP",
    className: "bg-cyan-500/15 text-cyan-200 border-cyan-400/35",
  },
  unknown: {
    short: "REVIEW",
    label: "Unknown Ownership",
    className: "bg-amber-500/15 text-amber-300 border-amber-500/35",
  },
};

export const SCOPE_LABELS = {
  enterprise_internal: "Internal",
  enterprise_edge: "Edge",
  isp_upstream: "ISP Upstream",
  external: "External",
  vpn_remote: "VPN Remote",
  unclassified: "Unclassified",
};

export const REACHABILITY_BADGES = {
  reachable: { label: "Reachable", className: "text-emerald-300 bg-emerald-500/10 border-emerald-500/25" },
  unreachable: { label: "Unreachable", className: "text-red-300 bg-red-500/10 border-red-500/25" },
  unknown: { label: "Reachability Unknown", className: "text-amber-300 bg-amber-500/10 border-amber-500/25" },
};

export const FRESHNESS_BADGES = {
  fresh: { label: "Fresh", className: "text-emerald-400" },
  stale: { label: "Stale", className: "text-amber-400" },
  expired: { label: "Expired", className: "text-rose-400" },
  unknown: { label: "Unverified", className: "text-text-secondary" },
};

export const MANAGEMENT_LABELS = {
  managed: "SSH Managed",
  management_unavailable: "Mgmt Unavailable",
  not_attempted: "Mgmt Not Attempted",
  not_authorized: "Not Authorized",
};

export const DISCOVERY_MODES = [
  { value: "seed_only", label: "Seed Only (1-Hop Safe)" },
  { value: "enterprise_managed", label: "Enterprise Managed (Multi-Hop)" },
  { value: "authorized_expansion", label: "Authorized Expansion" },
];

export const VIEW_MODES = [
  { value: "internal_only", label: "Internal Only" },
  { value: "internal_and_edge", label: "Internal + Edge" },
  { value: "all_observed", label: "All Observed" },
];

// -----------------------------------------------------------------------------
// Phase 4.5: Multi-Layer Relationship Classes & Visual Taxonomy
// -----------------------------------------------------------------------------

export const RELATIONSHIP_CLASSES = {
  physical: {
    id: "physical",
    label: "Physical Adjacency",
    shortLabel: "Physical",
    color: "#10b981", // Emerald
    strokeColor: "#34d399",
    description: "Confirmed physical cabling (copper, fiber, direct attachment).",
    badgeClass: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  },
  layer2: {
    id: "layer2",
    label: "Layer 2 Adjacency",
    shortLabel: "Layer 2",
    color: "#0284c7", // Sky
    strokeColor: "#38bdf8",
    description: "Switch-port, bridge, VLAN, and MAC learning adjacency.",
    badgeClass: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  },
  layer3: {
    id: "layer3",
    label: "Layer 3 Reachability",
    shortLabel: "Layer 3",
    color: "#a855f7", // Purple
    strokeColor: "#c084fc",
    description: "Routed next-hop, gateway, and connected subnet reachability.",
    badgeClass: "bg-purple-500/15 text-purple-300 border-purple-500/30",
  },
  logical: {
    id: "logical",
    label: "Logical Relationship",
    shortLabel: "Logical",
    color: "#f59e0b", // Amber
    strokeColor: "#fbbf24",
    description: "VPN, overlay tunnel, VRRP, and logical dependencies.",
    badgeClass: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  },
};

export const CONFIDENCE_TIERS = {
  CONFIRMED: { label: "Confirmed", scoreMin: 0.9, badgeClass: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" },
  HIGH: { label: "High Confidence", scoreMin: 0.75, badgeClass: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30" },
  MEDIUM: { label: "Medium Confidence", scoreMin: 0.5, badgeClass: "bg-sky-500/15 text-sky-300 border-sky-500/30" },
  LOW: { label: "Low / Single Source", scoreMin: 0.25, badgeClass: "bg-amber-500/15 text-amber-300 border-amber-500/30" },
  INFERRED: { label: "Inferred", scoreMin: 0.0, badgeClass: "bg-slate-500/15 text-slate-300 border-slate-500/30" },
};

/**
 * Normalizes any legacy link or Phase 4.1 TopologyEdge dictionary into a
 * canonical multi-layer edge format.
 */
export function normalizeEdge(item) {
  if (!item) return null;
  const id = item.id || `${item.source_node_id || item.source}->${item.target_node_id || item.target}`;
  const source = item.source_node_id || item.source || item.local_node_id || "";
  const target = item.target_node_id || item.target || item.remote_node_id || "";
  const sourcePort = item.source_interface || item.source_port || item.local_interface_name || "";
  const targetPort = item.target_interface || item.target_port || item.remote_interface_name || "";

  // Resolve relationship class (Never infer physical adjacency without explicit evidence)
  let relationshipClass = item.relationship_class || "";
  if (!relationshipClass && item.link_type) {
    const lt = String(item.link_type).toLowerCase().trim();
    if (lt === "routed" || lt === "layer3_reachability" || lt === "layer3" || lt === "inferred" || lt === "arp") {
      relationshipClass = "layer3";
    } else if (lt === "layer2_adjacency" || lt === "layer2" || lt === "wireless" || lt === "bridge") {
      relationshipClass = "layer2";
    } else if (lt === "vpn" || lt === "tunnel" || lt === "logical" || lt === "overlay") {
      relationshipClass = "logical";
    } else if (lt === "physical" || lt === "ethernet" || lt === "fiber" || lt === "direct") {
      relationshipClass = "physical";
    } else {
      relationshipClass = "layer3"; // Conservative epistemic default: never assume physical cabling
    }
  }
  if (!relationshipClass) {
    relationshipClass = "layer3";
  }

  const operStatus = item.oper_status || item.status || "up";
  const verificationStatus = item.verification_status || "unknown";
  const confidenceTier = (item.confidence_tier || item.confidence || "MEDIUM").toUpperCase();
  const confidenceScore = typeof item.confidence_score === "number" ? item.confidence_score : 0.5;
  const confidenceRationale = item.confidence_rationale || item.confidence_reason || "";
  const direction = item.direction || (relationshipClass === "layer3" ? "directed" : "bidirectional");

  return {
    ...item,
    id,
    source,
    target,
    source_port: sourcePort,
    target_port: targetPort,
    source_interface: sourcePort,
    target_interface: targetPort,
    relationship_class: relationshipClass,
    relationship_subtype: item.relationship_subtype || (relationshipClass === "physical" ? "direct_copper" : "standard"),
    oper_status: operStatus,
    admin_status: item.admin_status || "enabled",
    verification_status: verificationStatus,
    confidence_tier: confidenceTier,
    confidence_score: confidenceScore,
    confidence_rationale: confidenceRationale,
    direction,
    vlan_id: item.vlan_id || null,
    is_lag_member: !!item.is_lag_member,
    bandwidth_bps: item.bandwidth_bps || 0,
    bandwidth: item.bandwidth || (item.bandwidth_bps ? `${Math.round(item.bandwidth_bps / 1e6)} Mbps` : ""),
    first_seen: item.first_seen || null,
    last_seen: item.last_seen || null,
    last_verified: item.last_verified || null,
    observation_freshness: item.observation_freshness || "fresh",
    provenance: item.provenance || "discovery_managed",
    evidence: Array.isArray(item.evidence) ? item.evidence : [],
  };
}

/**
 * Calculates Quadratic Bezier curved SVG paths for parallel multi-layer edges
 * between identical node pairs, preventing line collisions.
 */
export function computeCurvedEdgePath(x1, y1, x2, y2, bundleIndex = 0, bundleSize = 1) {
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.hypot(dx, dy) || 1;

  // Unit normal vector perpendicular to edge line
  const nx = -dy / len;
  const ny = dx / len;

  if (bundleSize <= 1) {
    return {
      pathD: `M ${x1} ${y1} L ${x2} ${y2}`,
      labelX: mx,
      labelY: my,
      cx: mx,
      cy: my,
      isCurved: false,
    };
  }

  // Symmetric offset spacing (30px per parallel line)
  const offset = (bundleIndex - (bundleSize - 1) / 2) * 32;
  const cx = mx + nx * offset;
  const cy = my + ny * offset;

  // Midpoint of quadratic bezier curve at t = 0.5: B(0.5) = (P0 + 2*P1 + P2) / 4
  const qx = (x1 + 2 * cx + x2) / 4;
  const qy = (y1 + 2 * cy + x2 ? (y1 + 2 * cy + y2) / 4 : my);

  return {
    pathD: `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`,
    labelX: qx,
    labelY: (y1 + 2 * cy + y2) / 4,
    cx,
    cy,
    isCurved: true,
  };
}

/**
 * Computes accessible, progressive visual styling for multi-layer topology edges.
 */
export function getMultiLayerEdgeVisualConfig(edge, src, dst, isSelected = false) {
  const norm = normalizeEdge(edge);
  const rc = norm.relationship_class;
  const oper = norm.oper_status;
  const vs = norm.verification_status;
  const isDown = oper === "down" || src?.reachability_status === "unreachable" || dst?.reachability_status === "unreachable";
  const isDegraded = oper === "degraded" || oper === "warning";

  // 1. Conflict State (Top Priority)
  if (vs === "conflicting") {
    return {
      stroke: "#f43f5e",
      strokeWidth: isSelected ? "3.5" : "2.4",
      strokeDasharray: "4,3",
      opacity: 0.95,
      glow: true,
      badge: "⚠ Conflict",
      badgeColor: "#f43f5e",
      markerEnd: undefined,
    };
  }

  // 2. Operational Down
  if (isDown) {
    return {
      stroke: "#ef4444",
      strokeWidth: isSelected ? "3.0" : "1.8",
      strokeDasharray: "5,4",
      opacity: 0.7,
      glow: false,
      badge: "✕ Down",
      badgeColor: "#ef4444",
      markerEnd: undefined,
    };
  }

  // 3. Operational Degraded
  if (isDegraded) {
    return {
      stroke: "#f59e0b",
      strokeWidth: isSelected ? "3.2" : "2.0",
      strokeDasharray: "6,3",
      opacity: 0.85,
      glow: isSelected,
      badge: "⚠ Degraded",
      badgeColor: "#f59e0b",
      markerEnd: undefined,
    };
  }

  // 3.5. Operational Link Saturation / Bandwidth Utilization Overlay (WP 5.6)
  const util = norm.utilization_percent ?? norm.rx_utilization_percent;
  if (typeof util === "number" && util >= 85) {
    return {
      stroke: "#ef4444",
      strokeWidth: isSelected ? "3.8" : "2.8",
      strokeDasharray: "none",
      opacity: 0.95,
      glow: true,
      badge: `🔥 ${Math.round(util)}% Saturated`,
      badgeColor: "#ef4444",
      markerEnd: rc === "layer3" ? "url(#arrow-layer3)" : undefined,
    };
  } else if (typeof util === "number" && util >= 60) {
    return {
      stroke: "#f59e0b",
      strokeWidth: isSelected ? "3.4" : "2.4",
      strokeDasharray: "none",
      opacity: 0.9,
      glow: isSelected,
      badge: `⚡ ${Math.round(util)}% Elevated`,
      badgeColor: "#f59e0b",
      markerEnd: rc === "layer3" ? "url(#arrow-layer3)" : undefined,
    };
  }

  // 4. Layer-Specific Taxonomy
  switch (rc) {
    case "physical": {
      const isConfirmed = vs === "confirmed" || vs === "manual";
      return {
        stroke: isConfirmed ? "url(#link-gradient-physical)" : "#10b981",
        strokeWidth: isSelected ? "3.8" : isConfirmed ? "2.8" : "2.0",
        strokeDasharray: "none",
        opacity: isConfirmed ? 0.95 : 0.8,
        glow: isConfirmed || isSelected,
        badge: isConfirmed ? (vs === "manual" ? "✓ Phys (Manual)" : "✓ Phys Confirmed") : "Phys Observed",
        badgeColor: "#34d399",
        markerEnd: undefined,
      };
    }

    case "layer2": {
      const isObserved = vs === "observed" || vs === "inferred";
      const vlanLabel = norm.vlan_id ? `VLAN ${norm.vlan_id}` : "L2 Bridge";
      return {
        stroke: "#38bdf8",
        strokeWidth: isSelected ? "3.4" : "2.2",
        strokeDasharray: isObserved ? "7,4" : "none",
        opacity: 0.88,
        glow: isSelected,
        badge: isObserved ? `L2 (${vlanLabel})` : `✓ L2 ${vlanLabel}`,
        badgeColor: "#38bdf8",
        markerEnd: undefined,
      };
    }

    case "layer3": {
      return {
        stroke: "#c084fc",
        strokeWidth: isSelected ? "3.0" : "1.9",
        strokeDasharray: "5,4",
        opacity: 0.85,
        glow: isSelected,
        badge: "L3 Routed",
        badgeColor: "#c084fc",
        markerEnd: "url(#arrow-layer3)",
      };
    }

    case "logical": {
      const subtype = norm.relationship_subtype ? norm.relationship_subtype.replace(/_/g, " ").toUpperCase() : "VPN";
      return {
        stroke: "#fbbf24",
        strokeWidth: isSelected ? "3.2" : "2.0",
        strokeDasharray: "10,4,2,4",
        opacity: 0.85,
        glow: isSelected,
        badge: `Logical: ${subtype}`,
        badgeColor: "#fbbf24",
        markerEnd: norm.direction === "directed" ? "url(#arrow-logical)" : undefined,
      };
    }

    default:
      return {
        stroke: "#94a3b8",
        strokeWidth: isSelected ? "2.6" : "1.6",
        strokeDasharray: "6,4",
        opacity: 0.75,
        glow: false,
        badge: "Inferred",
        badgeColor: "#94a3b8",
        markerEnd: undefined,
      };
  }
}

/**
 * Computes accessible, non-color-only visual styling for SVG links:
 * - confirmed / manual -> thick solid line + "✓ Verified" / "✓ Manual"
 * - observed -> medium solid line + "Observed" (with "?" port marker if remote port is missing)
 * - inferred / routed -> dashed ("6,4") + "Inferred" / "Routed"
 * - vpn -> dot-dash ("10,4,2,4") + "VPN"
 * - conflicting -> warning dashed ("4,3") + "⚠ Conflict"
 */
export function getLinkVisualConfig(link, src, dst) {
  const isDown =
    link.status === "down" ||
    link.oper_status === "down" ||
    src?.reachability_status === "unreachable" ||
    dst?.reachability_status === "unreachable";

  const vStatus = link.verification_status || "unknown";
  const lType = link.link_type || "physical";

  if (vStatus === "conflicting") {
    return {
      stroke: "#f43f5e",
      strokeWidth: "2.2",
      strokeDasharray: "4,3",
      opacity: 0.95,
      glow: false,
      badge: "⚠ Conflict",
      badgeFill: "#be123c",
      dotColor: "#f43f5e",
    };
  }

  if (isDown) {
    return {
      stroke: "#ef4444",
      strokeWidth: "1.6",
      strokeDasharray: "5,5",
      opacity: 0.7,
      glow: false,
      badge: "✕ Down",
      badgeFill: "#991b1b",
      dotColor: "#ef4444",
    };
  }

  if (lType === "vpn") {
    return {
      stroke: "#c084fc",
      strokeWidth: "2",
      strokeDasharray: "10,4,2,4",
      opacity: 0.85,
      glow: false,
      badge: "VPN",
      badgeFill: "#6b21a8",
      dotColor: "#c084fc",
    };
  }

  if (vStatus === "confirmed" || vStatus === "manual") {
    return {
      stroke: "url(#link-gradient-up)",
      strokeWidth: "2.6",
      strokeDasharray: "none",
      opacity: 0.95,
      glow: true,
      badge: vStatus === "manual" ? "✓ Manual" : "✓ Verified",
      badgeFill: "#065f46",
      dotColor: "#34d399",
    };
  }

  if (vStatus === "observed") {
    return {
      stroke: "#38bdf8",
      strokeWidth: "1.9",
      strokeDasharray: "none",
      opacity: 0.82,
      glow: false,
      badge: link.target_port ? "Observed" : "Observed (?)",
      badgeFill: "#075985",
      dotColor: "#38bdf8",
    };
  }

  // inferred, routed, or unknown
  return {
    stroke: "#94a3b8",
    strokeWidth: "1.5",
    strokeDasharray: "6,4",
    opacity: 0.72,
    glow: false,
    badge: lType === "routed" ? "Routed" : "Inferred",
    badgeFill: "#334155",
    dotColor: "#94a3b8",
  };
}

export function formatRelativeTime(epochSec) {
  if (!epochSec) return "Never";
  const diffSec = Math.max(0, Math.round(Date.now() / 1000 - Number(epochSec)));
  if (diffSec < 10) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}
