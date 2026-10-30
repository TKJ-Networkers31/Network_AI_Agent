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
